from __future__ import annotations

import json

from apps.reference.domains.alpha_search.judge.central_brain.shadow_capture_writer import (
    JudgeShadowCaptureWriter,
    ShadowCapturePaths,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    JudgeShadowCalibrationRowV1,
    to_phase8_calibration_row,
)
from tests.domains.alpha_search.judge.central_brain.test_judge_runtime_shadow_pipeline import (
    aurora_payload,
    build,
    candidate,
)


def paths(tmp_path):
    return ShadowCapturePaths(
        output_dir=str(tmp_path),
        evidence_envelope_file="judge_evidence_envelope_v2.jsonl",
        policy_verdict_file="judge_policy_verdict_v2.jsonl",
        bridge_decision_file="judge_bridge_decision_v1.jsonl",
        calibration_row_file="judge_shadow_calibration_row_v1.jsonl",
    )


def test_writer_writes_all_shadow_jsonl_files(tmp_path):
    artifacts = build()
    writer = JudgeShadowCaptureWriter(enabled=True, paths=paths(tmp_path))
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    assert sum(result.written.values()) == 4
    for file_name in result.paths.values():
        row = json.loads(open(file_name, encoding="utf-8").readline())
        assert row["event_name"].startswith("EVT:JUDGE_")
        assert isinstance(row["payload"], dict)


def test_writer_disabled_writes_nothing(tmp_path):
    artifacts = build()
    writer = JudgeShadowCaptureWriter(enabled=False, paths=paths(tmp_path))
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    assert result.written == {}
    assert not (tmp_path / "judge_evidence_envelope_v2.jsonl").exists()
    assert not (tmp_path / "judge_shadow_calibration_row_v1.jsonl").exists()


def test_written_shadow_row_can_feed_phase8_conversion(tmp_path):
    artifacts = build()
    writer = JudgeShadowCaptureWriter(enabled=True, paths=paths(tmp_path))
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    row_path = result.paths["calibration_row_file"]
    row = json.loads(open(row_path, encoding="utf-8").readline())["payload"]
    converted = to_phase8_calibration_row(JudgeShadowCalibrationRowV1.model_validate(row))
    assert converted.verdict == artifacts.verdict.verdict


def test_writer_writes_all_files_for_observed_missing_symbol_shape(tmp_path):
    artifacts = build(
        strategy_payload=aurora_payload(symbol="ETHUSDT", rid="aurora_ETHUSDT_1779918604693"),
        regime_payload={
            "ts_ms": 1779918600000,
            "regime": "LOW_VOLATILITY",
            "confidence": 0.8,
            "rid": "regime-rid",
        },
        candidate_context=candidate(symbol="ETHUSDT", rid="aurora_ETHUSDT_1779918604693"),
        market_context={
            "symbol": "ETHUSDT",
            "ts_ms": 1779918600000,
            "data_freshness_state": "FRESH",
            "source_refs": {"fixture": "market"},
        },
    )
    writer = JudgeShadowCaptureWriter(enabled=True, paths=paths(tmp_path))
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    assert set(result.written.values()) == {1}
    assert len(result.paths) == 4
    assert artifacts.verdict.applied is False
    assert artifacts.bridge_decision.no_effect is True
