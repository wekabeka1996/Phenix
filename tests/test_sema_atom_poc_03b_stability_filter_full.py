from __future__ import annotations

import json
from pathlib import Path

import SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL as poc03b


def _sample_context(
    *,
    context_key: str,
    verdict: str,
    validation_result: str,
    validation_reason: str,
    support_quality: str,
    low_power_reason: str,
    train_count: int,
    validation_count: int,
    train_net_score: float,
    validation_net_score: float,
    train_outcomes: dict[str, int],
    validation_outcomes: dict[str, int],
) -> dict:
    symbol, side, strategy_id, regime, confidence_bucket = context_key.split(
        "|")
    return {
        "context_key": context_key,
        "symbol": symbol,
        "side": side,
        "strategy_id": strategy_id,
        "regime": regime,
        "confidence_bucket": confidence_bucket,
        "verdict": verdict,
        "recommendation": "review_policy_thresholds" if verdict == "POLICY_TOO_STRICT_CANDIDATE" else "monitor",
        "validation_result": validation_result,
        "validation_reason": validation_reason,
        "train_count": train_count,
        "validation_count": validation_count,
        "train_outcomes": train_outcomes,
        "validation_outcomes": validation_outcomes,
        "train_net_score": train_net_score,
        "validation_net_score": validation_net_score,
        "train_rates": {
            "policy_too_strict_rate": 0.8 if verdict == "POLICY_TOO_STRICT_CANDIDATE" else 0.0,
            "negative_rate": 1.0 if verdict == "TOXIC_CONTEXT" else 0.0,
            "favorable_rate": 0.0,
        },
        "validation_rates": {
            "policy_too_strict_rate": 0.727273 if verdict == "POLICY_TOO_STRICT_CANDIDATE" else 0.0,
            "negative_rate": 0.666667 if verdict == "TOXIC_CONTEXT" else 0.0,
            "favorable_rate": 0.0,
        },
        "support_quality": support_quality,
        "support_counts": {
            "raw_total_count": train_count + validation_count,
            "train_count": train_count,
            "validation_count": validation_count,
            "effective_total_count": None,
            "decay_applied": False,
        },
        "low_power_reason": low_power_reason,
        "timestamp_range": {
            "earliest_atom_ts_ms": 1,
            "latest_atom_ts_ms": 2,
            "train_window_end_ts_ms": 1,
            "validation_window_start_ts_ms": 2,
        },
    }


def _sample_sidecar() -> dict:
    contexts = [
        _sample_context(
            context_key="BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50",
            verdict="POLICY_TOO_STRICT_CANDIDATE",
            validation_result="CONFIRMED",
            validation_reason="validation_high_missed_positive_rate",
            support_quality="STRONG",
            low_power_reason="NONE",
            train_count=10,
            validation_count=11,
            train_net_score=-16.461044,
            validation_net_score=-11.844887,
            train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 8},
            validation_outcomes={
                "POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 8},
        ),
        _sample_context(
            context_key="ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25",
            verdict="TOXIC_CONTEXT",
            validation_result="CONFIRMED",
            validation_reason="validation_negative_profile",
            support_quality="BORDERLINE",
            low_power_reason="TRAIN_AND_VALIDATION_BELOW_PRIMARY_MINIMUM",
            train_count=3,
            validation_count=3,
            train_net_score=-22.481593,
            validation_net_score=-2.589772,
            train_outcomes={"CLEAN_LOSS": 3},
            validation_outcomes={"CLEAN_LOSS": 2, "GOOD_DECISION": 1},
        ),
        _sample_context(
            context_key="XRPUSDT|SELL|aurora|MEAN_REVERSION|0.50..0.75",
            verdict="LOW_SUPPORT",
            validation_result="SKIPPED_LOW_SUPPORT",
            validation_reason="train_or_validation_support_below_threshold",
            support_quality="INSUFFICIENT",
            low_power_reason="TRAIN_BELOW_DISPLAY_MINIMUM",
            train_count=1,
            validation_count=1,
            train_net_score=27.393798,
            validation_net_score=9.156211,
            train_outcomes={"GOOD_DECISION": 1},
            validation_outcomes={},
        ),
    ]
    return {
        "schema_id": "SemaAtomPoc03EvaluationSidecarV01",
        "schema_version": "1.0.0",
        "generated_at_utc": "2026-05-15T00:00:00Z",
        "saf_path": "Sema_Atom/aurora_real_logs_v02.saf.jsonl",
        "total_atoms": 8,
        "contexts_total": len(contexts),
        "split_config": {
            "split_method": "chronological_50_50",
            "min_train_atoms": 5,
            "min_validation_atoms": 5,
            "display_min_train_atoms": 2,
            "display_min_validation_atoms": 1,
        },
        "final_verdict": "VALIDATION_PASSED",
        "residual_status": "LOW_POWER_RESIDUALS",
        "summary": {
            "contexts_total": len(contexts),
            "contexts_tested": 2,
            "contexts_skipped_low_support": 1,
            "contexts_confirmed": 2,
            "contexts_contradicted": 0,
            "contexts_inconclusive": 0,
            "confirmation_rate": 1.0,
            "false_positive_verdicts": 0,
            "false_negative_verdicts": 0,
            "residual_status": "LOW_POWER_RESIDUALS",
        },
        "contexts": contexts,
    }


def test_apply_stability_filter_marks_policy_too_strict_ready() -> None:
    ctx = _sample_sidecar()["contexts"][0]
    assert poc03b.apply_stability_filter(ctx) == "READY_FOR_COUNTERFACTUAL_SIM"


def test_apply_stability_filter_never_promotes_borderline_to_ready() -> None:
    ctx = _sample_sidecar()["contexts"][1]
    assert poc03b.apply_stability_filter(ctx) == "PROMISING_LOW_SUPPORT"


def test_run_consumes_json_and_preserves_bucket_counts(tmp_path: Path) -> None:
    input_sidecar = tmp_path / "SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json"
    output_manifest = tmp_path / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    output_report = tmp_path / "SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT.md"
    input_sidecar.write_text(json.dumps(_sample_sidecar()), encoding="utf-8")
    result = poc03b.run(
        input_sidecar=input_sidecar,
        output_manifest=output_manifest,
        output_report=output_report,
    )
    assert result["status"] == "COMPLETED"
    assert result["sidecar_validation"]["parsed_contexts_total"] == 3
    assert result["manifest_total_contexts"] == 3
    manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert sum(len(items) for items in manifest.values()) == 3
    assert len(manifest["READY_FOR_COUNTERFACTUAL_SIM"]) == 1
    assert len(manifest["PROMISING_LOW_SUPPORT"]) == 1
    assert len(manifest["INCONCLUSIVE_LOW_POWER"]) == 1
    assert manifest["READY_FOR_COUNTERFACTUAL_SIM"][0]["context_id"] == "BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50"


def test_run_fails_closed_when_sidecar_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    result = poc03b.run(
        input_sidecar=missing_path,
        output_manifest=tmp_path / "manifest.json",
        output_report=tmp_path / "report.md",
    )
    assert result["status"] == "FAILED_SIDECAR_SCHEMA_VALIDATION"
    assert result["manifest_total_contexts"] == 0
    assert result["sidecar_validation"]["errors"] == [
        f"missing_input_sidecar:{missing_path}"]


def test_run_fails_closed_on_schema_version_mismatch(tmp_path: Path) -> None:
    bad_sidecar = _sample_sidecar()
    bad_sidecar["schema_version"] = "2.0.0"
    input_sidecar = tmp_path / "bad.json"
    input_sidecar.write_text(json.dumps(bad_sidecar), encoding="utf-8")
    result = poc03b.run(
        input_sidecar=input_sidecar,
        output_manifest=tmp_path / "manifest.json",
        output_report=tmp_path / "report.md",
    )
    assert result["status"] == "FAILED_SIDECAR_SCHEMA_VALIDATION"
    assert result["manifest_total_contexts"] == 0
    assert "schema_version_mismatch:2.0.0" in result["sidecar_validation"]["errors"]


def test_run_fails_closed_on_schema_id_mismatch(tmp_path: Path) -> None:
    bad_sidecar = _sample_sidecar()
    bad_sidecar["schema_id"] = "SomeOtherSchema"
    input_sidecar = tmp_path / "bad_id.json"
    input_sidecar.write_text(json.dumps(bad_sidecar), encoding="utf-8")
    result = poc03b.run(
        input_sidecar=input_sidecar,
        output_manifest=tmp_path / "manifest.json",
        output_report=tmp_path / "report.md",
    )
    assert result["status"] == "FAILED_SIDECAR_SCHEMA_VALIDATION"
    assert result["manifest_total_contexts"] == 0
    assert "schema_id_mismatch:SomeOtherSchema" in result["sidecar_validation"]["errors"]
