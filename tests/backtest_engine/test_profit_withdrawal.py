from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_profit_withdrawal_triggers_and_resets_balance() -> None:
    from backtest_engine.engine import BacktestEngine

    bus = MagicMock()
    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        event_bus=bus,
        initial_balance=1000.0,
        profit_withdrawal_roi_pct=50.0,
    )

    engine.broker.balance_usdt = 1500.0
    engine._emit_portfolio_update()

    assert engine.broker.balance_usdt == 1000.0
    assert engine.capital_withdrawn_total == 500.0
    assert len(engine.capital_withdrawals) == 1
    assert engine.capital_withdrawals[0]["withdrawn_usdt"] == 500.0


def test_profit_withdrawal_requires_flat_portfolio() -> None:
    from backtest_engine.engine import BacktestEngine

    bus = MagicMock()
    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        event_bus=bus,
        initial_balance=1000.0,
        profit_withdrawal_roi_pct=50.0,
    )

    # Simulate a non-flat position
    engine.broker._positions["BTCUSDT"] = SimpleNamespace(
        symbol="BTCUSDT",
        position_amount="1",
        entry_price="100.0",
        mark_price="100.0",
        unrealized_profit="0.0",
        leverage=20,
        margin_type="CROSS",
        isolated_margin=0.0,
        position_side="BOTH",
    )
    engine.broker.balance_usdt = 1500.0
    engine._emit_portfolio_update()

    # No withdrawal should occur because portfolio isn't flat
    assert engine.broker.balance_usdt == 1500.0
    assert engine.capital_withdrawn_total == 0.0
    assert len(engine.capital_withdrawals) == 0


def test_profit_withdrawal_can_be_disabled_via_config_flag() -> None:
    from backtest_engine.engine import BacktestEngine

    bus = MagicMock()
    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        event_bus=bus,
        initial_balance=1000.0,
        profit_withdrawal_enabled=False,
        profit_withdrawal_roi_pct=50.0,
    )

    engine.broker.balance_usdt = 1500.0
    engine._emit_portfolio_update()

    assert engine.broker.balance_usdt == 1500.0
    assert engine.capital_withdrawn_total == 0.0
    assert len(engine.capital_withdrawals) == 0
