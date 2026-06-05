from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (
    CalibrationDatasetSummary,
    CalibrationGates,
    CalibrationProposalSourceRefs,
    CalibrationWindow,
    ConfidenceBandCandidate,
    ConfidenceBands,
    JudgeCalibrationOutcome,
    JudgeCalibrationOutcomeRow,
    JudgeCalibrationSourceRefs,
    JudgeConfidenceCalibrationProposalV1,
    RecommendedPolicy,
    AntiLeakageReport,
)


SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/schemas/"
    "judge_confidence_calibration_proposal_v1.json"
)


def valid_row(**overrides) -> JudgeCalibrationOutcomeRow:
    payload = {
        "row_id": "row-1",
        "decision_ts_ms": 1000,
        "outcome_ts_ms": 2000,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "regime_label": "TREND_UP",
        "regime_confidence": 0.8,
        "verdict": "OPEN_LONG",
        "judge_confidence": 0.72,
        "bridge_action": "record_only",
        "authority_mode": "shadow",
        "applied": False,
        "missingness_state": "COMPLETE",
        "freshness_state": "FRESH",
        "outcome": {
            "horizon_sec": 300,
            "gross_pnl_usd": 1.5,
            "net_pnl_usd": 1.2,
            "fees_usd": 0.2,
            "slippage_usd": 0.1,
            "max_favorable_usd": 2.0,
            "max_adverse_usd": -0.5,
            "terminal_status": "closed",
        },
        "source_refs": {
            "verdict_id": "verdict-1",
            "envelope_id": "env-1",
            "decision_id": "decision-1",
            "rid": "rid-1",
            "lifecycle_id": None,
        },
    }
    payload.update(overrides)
    return JudgeCalibrationOutcomeRow.model_validate(payload)


def valid_proposal() -> JudgeConfidenceCalibrationProposalV1:
    return JudgeConfidenceCalibrationProposalV1(
        proposal_id="proposal-1",
        created_ts_ms=3000,
        calibration_window=CalibrationWindow(
            train_start_ts_ms=1000,
            train_end_ts_ms=2000,
            holdout_start_ts_ms=None,
            holdout_end_ts_ms=None,
            cadence_days=4,
        ),
        dataset_summary=CalibrationDatasetSummary(
            total_rows=2,
            usable_rows=2,
            unresolved_rows=0,
            symbols=["BTCUSDT"],
            regimes=["TREND_UP"],
            sides=["BUY"],
        ),
        gates=CalibrationGates(
            min_rows_required=2,
            min_symbols_required=1,
            min_usable_rows_passed=True,
            min_symbols_passed=True,
            holdout_present=False,
        ),
        confidence_bands=ConfidenceBands(
            candidates=[
                ConfidenceBandCandidate(
                    band_id="conf_0.70_0.80",
                    min_confidence=0.7,
                    max_confidence=0.8,
                    action="allow",
                    rows=2,
                    win_rate=1.0,
                    avg_net_pnl_usd=1.0,
                    total_net_pnl_usd=2.0,
                    expectancy_net_usd=1.0,
                    max_drawdown_usd=0.0,
                    ci_low=None,
                    ci_high=None,
                    status="CANDIDATE",
                    reason_codes=["positive_expectancy"],
                )
            ]
        ),
        breakdowns={
            "by_symbol": {},
            "by_regime": {},
            "by_side": {},
            "by_symbol_regime_side": {},
        },
        recommended_policy=RecommendedPolicy(config_patch=None),
        anti_leakage=AntiLeakageReport(
            train_holdout_split_valid=True,
            no_future_outcome_in_train_features=True,
            leakage_warnings=[],
        ),
        source_refs=CalibrationProposalSourceRefs(input_paths=[], report_path=None),
    )


def test_valid_outcome_row_validates():
    row = valid_row()
    assert row.schema_version == "1.0.0"
    assert row.outcome.net_pnl_usd == pytest.approx(1.2)


def test_extra_row_fields_rejected():
    payload = valid_row().model_dump()
    payload["hidden"] = "field"
    with pytest.raises(ValidationError):
        JudgeCalibrationOutcomeRow.model_validate(payload)


def test_outcome_ts_before_decision_ts_rejected():
    with pytest.raises(ValidationError):
        valid_row(outcome_ts_ms=999)


def test_judge_confidence_none_accepted():
    assert valid_row(judge_confidence=None).judge_confidence is None


def test_valid_proposal_validates():
    proposal = valid_proposal()
    dumped = proposal.model_dump(mode="json", by_alias=True)
    assert dumped["recommended_policy"]["proposal_only"] is True
    assert dumped["recommended_policy"]["auto_apply"] is False
    assert dumped["gates"]["promotion_allowed"] is False


def test_promotion_allowed_cannot_be_true():
    payload = valid_proposal().model_dump(mode="json", by_alias=True)
    payload["gates"]["promotion_allowed"] = True
    with pytest.raises(ValidationError):
        JudgeConfidenceCalibrationProposalV1.model_validate(payload)


def test_auto_apply_cannot_be_true():
    payload = valid_proposal().model_dump(mode="json", by_alias=True)
    payload["recommended_policy"]["auto_apply"] = True
    with pytest.raises(ValidationError):
        JudgeConfidenceCalibrationProposalV1.model_validate(payload)


def test_proposal_only_cannot_be_false():
    payload = valid_proposal().model_dump(mode="json", by_alias=True)
    payload["recommended_policy"]["proposal_only"] = False
    with pytest.raises(ValidationError):
        JudgeConfidenceCalibrationProposalV1.model_validate(payload)


def test_invalid_confidence_band_rejected():
    with pytest.raises(ValidationError):
        ConfidenceBandCandidate(
            band_id="bad",
            min_confidence=0.8,
            max_confidence=0.7,
            action="allow",
            rows=1,
            status="CANDIDATE",
        )


def test_overlapping_active_allow_suppress_rejected():
    with pytest.raises(ValidationError):
        ConfidenceBands(
            candidates=[
                ConfidenceBandCandidate(
                    band_id="allow",
                    min_confidence=0.5,
                    max_confidence=0.7,
                    action="allow",
                    rows=10,
                    status="CANDIDATE",
                ),
                ConfidenceBandCandidate(
                    band_id="suppress",
                    min_confidence=0.6,
                    max_confidence=0.8,
                    action="suppress",
                    rows=10,
                    status="TOXIC",
                ),
            ]
        )


def test_schema_json_parses():
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        assert json.load(handle)["title"] == "Judge Confidence Calibration Proposal V1"


def test_nested_contracts_reject_unknown_fields():
    with pytest.raises(ValidationError):
        JudgeCalibrationOutcome(horizon_sec=300, extra="nope")
    with pytest.raises(ValidationError):
        JudgeCalibrationSourceRefs(verdict_id="v", extra="nope")
