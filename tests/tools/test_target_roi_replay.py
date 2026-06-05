from __future__ import annotations

from pathlib import Path

from tools.order_log_scenario_backtest.exit_policies import (
    compute_target_roi_geometry,
    materialize_trade_result,
    target_roi_exit,
)
from tools.order_log_scenario_backtest.models import CanonicalEntry, CandleSeries, ScenarioRuntime


def _runtime(candles_by_symbol: dict[str, CandleSeries] | None = None) -> ScenarioRuntime:
    return ScenarioRuntime(
        workspace_root=Path("."),
        runtime_root=Path("."),
        report_root=Path("."),
        config={"fees": {"open_fee_bps": 10.0, "close_fee_bps": 10.0}},
        candles_by_symbol=candles_by_symbol or {},
        strict=True,
    )


def test_compute_target_roi_geometry_uses_historical_fee_and_sell_fallback() -> None:
    runtime = _runtime()

    buy_entry = CanonicalEntry(
        entry_id="buy-1",
        lifecycle_id="buy-1",
        rid="buy-1",
        trade_id="",
        symbol="ETHUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_ts_ms=1,
        entry_time_iso="",
        entry_price=100.0,
        qty=1.0,
        leverage=10.0,
        timestamp_quality="direct_order_log",
        reconstruction_confidence="high",
        regime_at_entry="TREND_UP",
        regime_confidence_at_entry=0.5,
        regime_source="direct",
        historical_stop_price=98.0,
        historical_round_trip_fee_bps=6.0,
    )
    buy_geometry = compute_target_roi_geometry(buy_entry, runtime, 8.0)
    assert round(float(buy_geometry["tp_price"]), 6) == 100.86
    assert round(float(buy_geometry["context"]
                 ["original_sl_net_roi_pct"]), 6) == -20.6
    assert round(float(buy_geometry["context"]
                 ["rr_vs_original_sl"]), 6) == 0.43

    sell_entry = CanonicalEntry(
        entry_id="sell-1",
        lifecycle_id="sell-1",
        rid="sell-1",
        trade_id="",
        symbol="BTCUSDT",
        side="SELL",
        strategy_id="aurora",
        entry_ts_ms=1,
        entry_time_iso="",
        entry_price=100.0,
        qty=1.0,
        leverage=5.0,
        timestamp_quality="direct_order_log",
        reconstruction_confidence="high",
        regime_at_entry="TREND_DOWN",
        regime_confidence_at_entry=0.5,
        regime_source="direct",
        historical_stop_price=102.0,
    )
    sell_geometry = compute_target_roi_geometry(sell_entry, runtime, 7.0)
    assert round(float(sell_geometry["tp_price"]), 6) == 98.4
    assert round(float(sell_geometry["context"]
                 ["original_sl_net_roi_pct"]), 6) == -11.0


def test_target_roi_exit_uses_historical_sl_and_sl_first_intrabar() -> None:
    entry = CanonicalEntry(
        entry_id="buy-1",
        lifecycle_id="buy-1",
        rid="buy-1",
        trade_id="",
        symbol="ETHUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_ts_ms=10_000,
        entry_time_iso="",
        entry_price=100.0,
        qty=1.0,
        leverage=10.0,
        timestamp_quality="direct_order_log",
        reconstruction_confidence="high",
        regime_at_entry="TREND_UP",
        regime_confidence_at_entry=0.5,
        regime_source="direct",
        historical_stop_price=99.5,
        historical_round_trip_fee_bps=0.0,
    )
    candles = CandleSeries(
        symbol="ETHUSDT",
        rows=[
            {"timestamp": 59_999, "open": 100.0,
                "high": 100.8, "low": 99.4, "close": 100.1},
        ],
        timestamps=[59_999],
    )
    runtime = _runtime({"ETHUSDT": candles})

    exit_event, extras = target_roi_exit(
        entry, runtime, 5.0, horizon_mode="fixed_24h_window")
    assert exit_event.reason == "historical_sl_first_ambiguous_intrabar"
    assert exit_event.price == 99.5
    assert extras["target_hit"] == "false"

    row = materialize_trade_result(
        "target_roi_replay", entry, runtime, exit_event, extras)
    assert row["status"] == "loss"
