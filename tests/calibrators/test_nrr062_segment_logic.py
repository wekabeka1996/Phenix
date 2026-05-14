from __future__ import annotations

import json
from pathlib import Path

import pytest

import calibrators.policy_gates.nrr062_segment_logic as segment_logic


def _base_ledger_row() -> dict[str, object]:
    return {
        "rid": "aurora_ETHUSDT_1778520602841",
        "nrr_code": "NRR-062",
        "symbol": "ETHUSDT",
        "side": "SELL",
        "position_side": "SHORT",
        "strategy_id": "aurora",
        "regime": "LOW_VOLATILITY",
        "regime_confidence": 0.41,
        "direction_confidence": -0.0125,
        "selected_source": "signal_score",
        "selected_scale": "raw_signed_score",
        "threshold_family": "raw_signed_score",
        "structured_fields_present": True,
        "parse_quality": "STRUCTURED_METADATA_COMPLETE",
        "gross_tp_bps": 92.0,
        "required_gross_tp_bps_floor": 26.0,
        "min_rr": 1.2,
        "violations": ["direction_confidence_below_threshold"],
        "timestamp_ms": 1778520603041,
        "timestamp_utc": "2026-05-11T17:30:03.041000+00:00",
        "direction_confidence_bucket": "<0.01",
        "regime_confidence_bucket": ">=0.39",
    }


def _base_replay_row() -> dict[str, object]:
    return {
        "rid": "aurora_ETHUSDT_1778520602841",
        "symbol": "ETHUSDT",
        "side": "SELL",
        "regime": "LOW_VOLATILITY",
        "violation_pattern": "direction_confidence_below_threshold",
        "replay_status": "READY",
        "outcome_class": "COUNTERFACTUAL_TP",
        "replay_data_quality": "DETERMINISTIC_PROXY",
        "estimated_gross_pnl_quote": 10.0,
        "estimated_net_pnl_quote": 5.0,
        "estimated_fee_quote": 2.0,
        "direction_confidence_bucket": "<0.01",
        "regime_confidence_bucket": ">=0.39",
    }


def test_sell_low_vol_direction_only_raw_signal_row_is_candidate() -> None:
    classification = segment_logic.classify_row(_base_ledger_row(), _base_replay_row())

    assert classification["candidate_would_allow"] is True
    assert classification["segment_class"] == segment_logic.CANDIDATE_NAME
    assert classification["candidate_reason"] == "matches_segment_rule"
    assert classification["exclusion_reason"] is None


def test_buy_row_is_excluded() -> None:
    ledger_row = _base_ledger_row()
    replay_row = _base_replay_row()
    ledger_row["side"] = "BUY"
    ledger_row["position_side"] = "LONG"
    replay_row["side"] = "BUY"

    classification = segment_logic.classify_row(ledger_row, replay_row)

    assert classification["candidate_would_allow"] is False
    assert classification["segment_class"] == "EXCLUDED_BUY_OR_LONG"
    assert classification["exclusion_reason"] == "buy_or_long"


def test_dual_regime_and_direction_failure_is_excluded() -> None:
    ledger_row = _base_ledger_row()
    replay_row = _base_replay_row()
    ledger_row["violations"] = [
        "regime_confidence_below_threshold",
        "direction_confidence_below_threshold",
    ]
    replay_row["violation_pattern"] = "regime_confidence_below_threshold+direction_confidence_below_threshold"

    classification = segment_logic.classify_row(ledger_row, replay_row)

    assert classification["candidate_would_allow"] is False
    assert classification["segment_class"] == "EXCLUDED_DUAL_FAILURE"
    assert classification["exclusion_reason"] == "dual_regime_and_direction_failure"


def test_missing_structured_metadata_is_excluded() -> None:
    ledger_row = _base_ledger_row()
    replay_row = _base_replay_row()
    ledger_row["structured_fields_present"] = False
    ledger_row["parse_quality"] = "FREE_TEXT_ONLY"

    classification = segment_logic.classify_row(ledger_row, replay_row)

    assert classification["candidate_would_allow"] is False
    assert classification["segment_class"] == "EXCLUDED_MISSING_STRUCTURED_METADATA"
    assert classification["exclusion_reason"] == "missing_structured_low_vol_metadata"


@pytest.mark.parametrize(
    ("outcome_class", "expected_reason"),
    [
        ("COUNTERFACTUAL_INVALID_INPUT", "counterfactual_invalid_input"),
        ("COUNTERFACTUAL_NO_MARKET_PATH", "counterfactual_no_market_path"),
    ],
)
def test_invalid_or_no_market_path_replay_is_excluded(outcome_class: str, expected_reason: str) -> None:
    replay_row = _base_replay_row()
    replay_row["outcome_class"] = outcome_class

    classification = segment_logic.classify_row(_base_ledger_row(), replay_row)

    assert classification["candidate_would_allow"] is False
    assert classification["segment_class"] == "EXCLUDED_INVALID_REPLAY"
    assert classification["exclusion_reason"] == expected_reason


def test_timeout_row_is_classified_and_counted_separately() -> None:
    replay_row = _base_replay_row()
    replay_row["outcome_class"] = "COUNTERFACTUAL_TIMEOUT"
    replay_row["estimated_net_pnl_quote"] = -1.0

    classification = segment_logic.classify_row(_base_ledger_row(), replay_row)
    metrics = segment_logic.build_metrics([classification])

    assert classification["candidate_would_allow"] is True
    assert classification["candidate_reason"] == "matches_segment_rule_timeout_measured"
    assert metrics["timeout_count"] == 1
    assert metrics["tp_count"] == 0
    assert metrics["sl_count"] == 0


def test_generated_classification_is_deterministic_for_real_dataset() -> None:
    ledger_payload = json.loads(Path(segment_logic.DEFAULT_LEDGER_PATH).read_text(encoding="utf-8"))
    replay_payload = json.loads(Path(segment_logic.DEFAULT_REPLAY_RESULTS_PATH).read_text(encoding="utf-8"))

    first = segment_logic.classify_dataset(ledger_payload["rows"], replay_payload["rows"])
    second = segment_logic.classify_dataset(ledger_payload["rows"], replay_payload["rows"])

    assert first == second
    assert len(first) == 153
    assert sum(1 for row in first if row["candidate_would_allow"]) + sum(1 for row in first if not row["candidate_would_allow"]) == 153