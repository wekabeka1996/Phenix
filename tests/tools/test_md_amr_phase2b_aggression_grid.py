from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from calibrators.strategies import calibrate_md_amr_weights as calibrator
from calibrators.strategies import run_md_amr_phase2b_aggression_grid as phase2b


def test_phase2b_count_malformed_csv_rows_detects_bad_line(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "timestamp,open,close\n"
        "1,100,101\n"
        "2,100,101,extra\n"
        "3,100,101\n",
        encoding="utf-8",
    )

    result = phase2b._count_malformed_csv_rows(csv_path)

    assert result == {"data_rows": 3, "malformed_rows": 1}


def test_phase2b_resolve_common_window_uses_latest_common_days(tmp_path: Path) -> None:
    recorder_dir = tmp_path / "recorder"
    recorder_dir.mkdir(parents=True, exist_ok=True)
    targets = [
        phase2b.SymbolTarget(
            symbol="XRPUSDT", expected_live_status=calibrator.LIVE_ASSIGNED, artifact_slug="xrp"),
        phase2b.SymbolTarget(
            symbol="ETHUSDT", expected_live_status=calibrator.NOT_LIVE_ASSIGNED, artifact_slug="eth"),
        phase2b.SymbolTarget(
            symbol="SOLUSDT", expected_live_status=calibrator.NOT_LIVE_ASSIGNED, artifact_slug="sol"),
    ]
    for day in [date(2026, 4, 25), date(2026, 4, 26), date(2026, 4, 27), date(2026, 4, 28), date(2026, 4, 29), date(2026, 4, 30)]:
        day_dir = recorder_dir / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        for target in targets:
            (day_dir / f"{target.symbol}_900.csv").write_text(
                "timestamp,open,high,low,close\n", encoding="utf-8")

    start, end, common_days = phase2b._resolve_common_window(
        recorder_dir=recorder_dir,
        targets=targets,
        tf_sec=900,
        start=None,
        end=None,
        analysis_days=4,
        validation_days=1,
        forward_days=1,
        min_train_days=2,
    )

    assert start == date(2026, 4, 27)
    assert end == date(2026, 5, 1)
    assert common_days[-4:] == ["2026-04-27",
                                "2026-04-28", "2026-04-29", "2026-04-30"]


def test_phase2b_label_candidate_shadow_only_on_data_warnings() -> None:
    manifest = {
        "status": "completed",
        "guardrails": {"min_trades": 5},
    }
    validation = {
        "all_passed": True,
        "baseline": {"profit_factor": 1.0},
        "candidate": {"total_trades": 6, "profit_factor": 1.2},
        "delta": {"net_return_ratio": 0.01, "total_trades": 1, "avg_trade_return_ratio": 0.001},
        "warnings": [],
    }
    forward = {
        "all_passed": True,
        "baseline": {"profit_factor": 1.0},
        "candidate": {"total_trades": 6, "profit_factor": 1.1},
        "delta": {"net_return_ratio": 0.005, "total_trades": 1, "avg_trade_return_ratio": 0.001},
        "warnings": [],
    }
    data_quality = {"warnings": ["gap_count=1"]}

    label, reasons = phase2b._label_candidate(
        manifest=manifest,
        validation_artifact=validation,
        forward_artifact=forward,
        per_regime_payload={"candidate_regime_concentration": {
            "single_positive_regime_only": False}},
        data_quality=data_quality,
        requested_dimensions=("threshold_z",),
        allowed_dimensions=calibrator._BASE_PARAM_MUTATION_ORDER,
    )

    assert label == "SHADOW_ONLY"
    assert reasons == ["gap_count=1"]


def test_phase2b_label_candidate_operator_review_when_clean_and_passing() -> None:
    manifest = {
        "status": "completed",
        "guardrails": {"min_trades": 5},
    }
    validation = {
        "all_passed": True,
        "baseline": {"profit_factor": 1.0},
        "candidate": {"total_trades": 7, "profit_factor": 1.3},
        "delta": {"net_return_ratio": 0.01, "total_trades": 2, "avg_trade_return_ratio": 0.001},
        "warnings": [],
    }
    forward = {
        "all_passed": True,
        "baseline": {"profit_factor": 1.0},
        "candidate": {"total_trades": 7, "profit_factor": 1.2},
        "delta": {"net_return_ratio": 0.006, "total_trades": 1, "avg_trade_return_ratio": 0.001},
        "warnings": [],
    }

    label, reasons = phase2b._label_candidate(
        manifest=manifest,
        validation_artifact=validation,
        forward_artifact=forward,
        per_regime_payload={"candidate_regime_concentration": {
            "single_positive_regime_only": False}},
        data_quality={"warnings": []},
        requested_dimensions=("threshold_z", "thr_base"),
        allowed_dimensions=calibrator._BASE_PARAM_MUTATION_ORDER,
    )

    assert label == "CANDIDATE_FOR_OPERATOR_REVIEW"
    assert reasons == ["validation_and_forward_guardrails_passed"]
