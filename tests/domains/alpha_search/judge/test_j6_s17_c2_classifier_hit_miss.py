from __future__ import annotations

from tools.alpha_search.j6_s17_c2_classifier_hit_miss import (
    ANALYSIS_THRESHOLDS,
    classify_hit_miss_bucket,
    classify_registry_action,
    classify_unknown_candidate,
    metrics_for_rows,
    normalize_dataset_row,
    tier_coverage_status,
)


def _make_raw_row(**overrides) -> dict[str, str]:
    row = {
        "cycle_key": "ENTRY:BTCUSDT:300:1712000000300",
        "plan_id": "sep_medium_BTCUSDT_1712000000300",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "tf_sec": "300",
        "regime": "TREND_UP",
        "surface_key": "TREND_UP:BUY:all_symbols:regime_complete",
        "matched_surface_label": "PROMISING_BUT_CONCENTRATED",
        "classifier_output": "TRACK_ONLY",
        "tier": "medium",
        "actionable": "True",
        "suppressed": "False",
        "outcome_available": "True",
        "simulation_status": "success",
        "limit_filled": "True",
        "terminal_reason": "FILLED_TP",
        "gross_pnl_pct": "0.12",
        "net_pnl_pct": "0.06",
        "fees_paid_pct": "0.06",
        "gross_pnl_bps": "12.0",
        "net_pnl_bps": "6.0",
        "total_cost_bps": "6.0",
        "tp_hit": "True",
        "sl_hit": "False",
        "timeout_hit": "False",
        "invalid_outcome_reason": "",
        "skipped_reason": "",
        "join_match_method": "cycle_key+tier",
        "join_anomalies": "[]",
        "plan_ts_ms": "1712000000300",
        "plan_ts_utc": "2024-04-01T00:00:00Z",
    }
    row.update(overrides)
    return row


def test_skipped_rows_are_excluded_from_trade_hit_miss() -> None:
    row = normalize_dataset_row(_make_raw_row(outcome_available="False", simulation_status="skipped",
                                skipped_reason="non_actionable_plan", limit_filled="False", tp_hit="False", net_pnl_pct=""))
    assert classify_hit_miss_bucket(row) == "SKIPPED"


def test_no_fill_timeout_is_not_counted_as_sl() -> None:
    row = normalize_dataset_row(_make_raw_row(limit_filled="False", terminal_reason="NOT_FILLED_TIMEOUT",
                                tp_hit="False", sl_hit="False", timeout_hit="True", net_pnl_pct=""))
    assert classify_hit_miss_bucket(row) == "NO_FILL"


def test_invalid_outcome_is_separated_from_miss() -> None:
    row = normalize_dataset_row(_make_raw_row(simulation_status="error", invalid_outcome_reason="Signal bar not found in data",
                                tp_hit="False", sl_hit="False", timeout_hit="False", net_pnl_pct=""))
    assert classify_hit_miss_bucket(row) == "INVALID"


def test_null_economics_preserved_in_metrics() -> None:
    rows = [
        normalize_dataset_row(_make_raw_row(
            plan_id="a", net_pnl_pct="", gross_pnl_pct="", fees_paid_pct="")),
        normalize_dataset_row(_make_raw_row(plan_id="b", net_pnl_pct="0.04",
                              gross_pnl_pct="0.1", fees_paid_pct="0.06", plan_ts_utc="2024-04-02T00:00:00Z")),
    ]
    metrics = metrics_for_rows(rows)
    assert metrics["filled_rows"] == 2
    assert metrics["count_with_null_economics"] == 1
    assert metrics["avg_net_pnl"] == 0.04


def test_registry_action_requires_more_forward_data_for_small_sample() -> None:
    metrics = {
        "outcome_available_rows": ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"] - 1,
        "filled_rows": ANALYSIS_THRESHOLDS["min_filled_rows_for_pnl_judgment"] - 1,
        "invalid_rows": 0,
        "sample_sufficiency_flag": False,
        "concentration_flag": False,
        "avg_net_pnl": 0.05,
        "tp_rate_among_filled": 0.4,
        "sl_rate_among_filled": 0.2,
    }
    unknown_baseline = {
        "avg_net_pnl": 0.01,
        "tp_rate_among_filled": 0.2,
        "sl_rate_among_filled": 0.3,
    }
    assert classify_registry_action(
        metrics, "UNKNOWN", unknown_baseline) == "REQUIRES_MORE_FORWARD_DATA"


def test_concentrated_positive_unknown_surface_becomes_watchlist_only() -> None:
    metrics = {
        "outcome_available_rows": 200,
        "filled_rows": 100,
        "invalid_rows": 0,
        "sample_sufficiency_flag": True,
        "concentration_flag": True,
        "avg_net_pnl": 0.08,
        "tp_rate_among_filled": 0.55,
        "sl_rate_among_filled": 0.15,
        "hit_miss_counts": {"HIT_TP": 55, "MISS_SL": 15, "NO_FILL": 5},
    }
    unknown_baseline = {
        "avg_net_pnl": 0.01,
        "tp_rate_among_filled": 0.25,
        "sl_rate_among_filled": 0.3,
    }
    assert classify_unknown_candidate(
        metrics, unknown_baseline) == "WATCHLIST_ONLY"


def test_non_actionable_tier_reports_design_status() -> None:
    metrics = {
        "actionable_rows": 0,
        "outcome_available_rows": 0,
    }
    assert tier_coverage_status(metrics) == "NON_ACTIONABLE_BY_DESIGN"
