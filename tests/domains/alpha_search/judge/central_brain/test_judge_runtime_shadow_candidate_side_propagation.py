from __future__ import annotations

import json

import pytest

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (
    JudgeShadowCalibrationRowV1,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_capture_writer import (
    JudgeShadowCaptureWriter,
)
from tests.domains.alpha_search.judge.central_brain.test_judge_runtime_shadow_capture_writer import (
    paths,
)
from tests.domains.alpha_search.judge.central_brain.test_judge_runtime_shadow_pipeline import (
    aurora_payload,
    build,
    candidate,
)


def test_pipeline_preserves_buy_side_from_candidate_context():
    artifacts = build(candidate_context=candidate(side="BUY"), strategy_payload=aurora_payload(side="BUY"))
    assert artifacts.calibration_row.side == "BUY"
    assert "candidate_side_source:candidate_context.side" in artifacts.calibration_row.diagnostics.reason_codes


def test_pipeline_preserves_sell_side_from_candidate_context():
    artifacts = build(candidate_context=candidate(side="SELL"), strategy_payload=aurora_payload(side="SELL"))
    assert artifacts.calibration_row.side == "SELL"
    assert artifacts.bridge_decision.no_effect is True


def test_pipeline_preserves_side_from_signal_payload_if_candidate_side_missing():
    artifacts = build(candidate_context=candidate(side=None), strategy_payload=aurora_payload(side="SELL"))
    assert artifacts.calibration_row.side == "SELL"
    assert "candidate_side_source:strategy_payload.side" in artifacts.calibration_row.diagnostics.reason_codes


def test_side_none_remains_unknown_when_no_source_exists():
    artifacts = build(candidate_context=candidate(side=None), strategy_payload=aurora_payload(side=None))
    assert artifacts.calibration_row.side == "NONE"
    assert "candidate_side_missing" in artifacts.calibration_row.diagnostics.reason_codes


def test_conflicting_side_sources_fail_closed():
    with pytest.raises(ValueError, match="CANDIDATE_SIDE_CONFLICT"):
        build(candidate_context=candidate(side="BUY"), strategy_payload=aurora_payload(side="SELL"))


def test_side_is_not_inferred_from_rid():
    artifacts = build(
        candidate_context=candidate(side=None, rid="aurora_ETHUSDT_SELL_1779968400764"),
        strategy_payload=aurora_payload(side=None, rid="aurora_ETHUSDT_SELL_1779968400764"),
    )
    assert artifacts.calibration_row.side == "NONE"
    assert "candidate_side_missing" in artifacts.calibration_row.diagnostics.reason_codes


def test_side_is_not_inferred_from_price_movement():
    artifacts = build(
        candidate_context=candidate(side=None),
        strategy_payload=aurora_payload(side=None, scoring={"decision_score": -0.9, "pillar_sum": -0.5}),
    )
    assert artifacts.calibration_row.side == "NONE"


def test_calibration_row_carries_side_after_propagation():
    artifacts = build(candidate_context=candidate(side="SELL"), strategy_payload=aurora_payload(side="SELL"))
    row = JudgeShadowCalibrationRowV1.model_validate(artifacts.calibration_row.model_dump(mode="json"))
    assert row.side == "SELL"
    assert row.verdict.applied is False
    assert row.bridge.no_effect is True
    assert row.bridge.bridge_action in {"record_only", "skip", "blocked"}


def test_writer_output_preserves_side(tmp_path):
    artifacts = build(candidate_context=candidate(side="SELL"), strategy_payload=aurora_payload(side="SELL"))
    writer = JudgeShadowCaptureWriter(enabled=True, paths=paths(tmp_path))
    result = writer.write_capture(
        envelope=artifacts.envelope,
        verdict=artifacts.verdict,
        bridge_decision=artifacts.bridge_decision,
        calibration_row=artifacts.calibration_row,
    )
    payload = json.loads(open(result.paths["calibration_row_file"], encoding="utf-8").readline())["payload"]
    assert payload["side"] == "SELL"
