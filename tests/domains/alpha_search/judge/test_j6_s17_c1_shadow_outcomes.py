from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.alpha_search.judge.contracts import ShadowEntryPlan
from apps.reference.domains.alpha_search.judge.simulation_models import ShadowSimulationResult
from tools.alpha_search.j6_s17_c1_shadow_outcomes import (
    _skipped_record,
    _success_record,
    augment_dataset_with_outcomes,
    resolve_join_method,
)


def _make_plan(**overrides) -> ShadowEntryPlan:
    payload = {
        "plan_id": "sep_low_BTCUSDT_1712000000300",
        "source_verdict_id": "vrd_entry_BTCUSDT_1712000000300",
        "source_envelope_id": "env_entry_BTCUSDT_1712000000200",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000300,
        "authority_mode": "shadow",
        "applied": False,
        "shadow_only": True,
        "final_entry_verdict": "OPEN_LONG",
        "suppressed": False,
        "suppression_reason": None,
        "entry_side": "BUY",
        "confidence": 0.8,
        "confidence_tier": "low",
        "tier_min_confidence": 0.2,
        "actionable": True,
        "entry_price_ref": 100.0,
        "limit_offset_bps": 0,
        "limit_price": 100.0,
        "tp_price": 101.0,
        "sl_price": 99.4,
        "tp_offset_pct": 0.01,
        "sl_offset_pct": 0.006,
        "risk_reward": 1.6666666666666667,
        "entry_order_type": "HYPOTHETICAL_LIMIT",
        "plan_reason_codes": ["tier_threshold_met"],
        "strategy_id": "aurora",
        "schema_version": "1",
    }
    payload.update(overrides)
    return ShadowEntryPlan(**payload)


def test_skipped_record_preserves_identity_and_null_pnl() -> None:
    plan = _make_plan()
    record = _skipped_record(plan, "missing_ohlc_file")
    assert record["plan_id"] == plan.plan_id
    assert record["cycle_key"] == plan.cycle_key
    assert record["tier"] == plan.confidence_tier
    assert record["skipped_reason"] == "missing_ohlc_file"
    assert record["net_pnl_pct"] is None
    assert record["gross_pnl_pct"] is None


def test_success_record_preserves_plan_keys() -> None:
    plan = _make_plan()
    result = ShadowSimulationResult(
        plan_id=plan.plan_id,
        cycle_key=plan.cycle_key,
        symbol=plan.symbol,
        ts_ms=plan.ts_ms,
        entry_side=plan.entry_side,
        confidence_tier=plan.confidence_tier,
        limit_price=plan.limit_price,
        tp_price=plan.tp_price,
        sl_price=plan.sl_price,
        outcome="FILLED_TP",
        outcome_reason="TP hit in bar 1",
        fill_ts_ms=plan.ts_ms,
        fill_price=plan.limit_price,
        fill_bar_idx=0,
        exit_ts_ms=plan.ts_ms + 300000,
        exit_price=plan.tp_price,
        exit_bar_idx=1,
        duration_bars=1,
        gross_pnl_pct=1.0,
        net_pnl_pct=0.94,
        fees_paid_pct=0.06,
    )
    record = _success_record(plan, result)
    assert record["plan_id"] == plan.plan_id
    assert record["cycle_key"] == plan.cycle_key
    assert record["tf_sec"] == plan.tf_sec
    assert record["outcome_available"] is True
    assert record["tp_hit"] is True
    assert record["net_pnl_pct"] == 0.94


def test_join_falls_back_when_plan_id_not_unique() -> None:
    dataset_rows = [
        {
            "cycle_key": "ENTRY:BTCUSDT:180:1",
            "plan_id": "sep_low_BTCUSDT_1",
            "tier": "low",
            "symbol": "BTCUSDT",
            "tf_sec": "180",
        },
        {
            "cycle_key": "ENTRY:BTCUSDT:300:1",
            "plan_id": "sep_low_BTCUSDT_1",
            "tier": "low",
            "symbol": "BTCUSDT",
            "tf_sec": "300",
        },
    ]
    outcome_rows = [
        {
            "cycle_key": "ENTRY:BTCUSDT:180:1",
            "plan_id": "sep_low_BTCUSDT_1",
            "tier": "low",
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "outcome_available": True,
            "simulation_status": "success",
            "terminal_reason": "FILLED_TP",
        },
        {
            "cycle_key": "ENTRY:BTCUSDT:300:1",
            "plan_id": "sep_low_BTCUSDT_1",
            "tier": "low",
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "outcome_available": True,
            "simulation_status": "success",
            "terminal_reason": "FILLED_SL",
        },
    ]
    augmented_rows, join_summary, * \
        _ = augment_dataset_with_outcomes(dataset_rows, outcome_rows)
    assert augmented_rows[0]["join_match_method"] == "cycle_key+tier"
    assert augmented_rows[1]["join_match_method"] == "cycle_key+tier"
    assert join_summary["many_to_one_anomalies"] >= 1


def test_augment_marks_missing_outcomes_explicitly() -> None:
    dataset_rows = [
        {
            "cycle_key": "ENTRY:BTCUSDT:300:1",
            "plan_id": "sep_low_BTCUSDT_1",
            "tier": "low",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "tf_sec": "300",
            "classifier_output": "TRACK_ONLY",
            "matched_surface_label": "PROMISING_BUT_CONCENTRATED",
            "regime": "TREND_UP",
            "ts_ms": "1712000000300",
        }
    ]
    augmented_rows, join_summary, classifier_summary, label_summary, dimension_summary = augment_dataset_with_outcomes(
        dataset_rows, [])
    row = augmented_rows[0]
    assert row["outcome_available"] is False
    assert row["invalid_outcome_reason"] == "missing_outcome_key_match"
    assert row["net_pnl_pct"] is None
    assert join_summary["rows_without_outcome"] == 1
    assert classifier_summary["TRACK_ONLY"]["invalid_outcome_count"] == 1
    assert label_summary["PROMISING_BUT_CONCENTRATED"]["invalid_outcome_count"] == 1
    assert dimension_summary["symbol"]["BTCUSDT"]["invalid_reason_counts"]["missing_outcome_key_match"] == 1
