"""BacktestEngine bootstrap portfolio emission.

Regression: DecisionMaking fail-closed with NRR-PORTFOLIO-UNKNOWN when backtest
starts without any EVT:PORTFOLIO_STATE_UPDATED.

BacktestEngine must emit a synthetic "flat" portfolio at startup so that
DecisionMaking can evaluate signals on the first bars.
"""

from datetime import datetime, date
from unittest.mock import MagicMock

import polars as pl


def test_backtest_engine_emits_initial_portfolio_bootstrap_event() -> None:
    from backtest_engine.engine import BacktestEngine

    mock_bus = MagicMock()
    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        symbol_list=["BTCUSDT"],
        timeframe="1h",
        event_bus=mock_bus,
        data_dir="/tmp/data",
        initial_balance=1234.0,
    )

    engine.feed = pl.DataFrame(
        {
            "ts": [datetime(2024, 1, 1, 0, 0, 0)],
            "symbol": ["BTCUSDT"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        }
    )

    # Run a single tick. The engine should emit the bootstrap portfolio once.
    try:
        engine.run(max_ticks=1)
    except Exception:
        # This test only cares about the early bootstrap emission.
        pass

    bootstrap_calls = []
    for call in mock_bus.emit.call_args_list:
        event_name = call.kwargs.get("event_name")
        why = call.kwargs.get("why")
        if event_name == "EVT:PORTFOLIO_STATE_UPDATED" and why == "backtest_initial_portfolio_bootstrap":
            bootstrap_calls.append(call)

    assert len(bootstrap_calls) == 1, (
        "BacktestEngine must emit exactly one initial portfolio bootstrap event "
        f"(got {len(bootstrap_calls)})"
    )

    payload = bootstrap_calls[0].kwargs.get("payload") or {}
    assert payload.get("positions") == [], "bootstrap portfolio must start flat"
    assert payload.get("equity") == "1234.0", "bootstrap equity must match initial_balance"
    assert payload.get("equity_free_usdt") == "1234.0", "free equity must match initial_balance"
    assert payload.get("positions_last_ts_ms") is not None, "must include positions_last_ts_ms"
