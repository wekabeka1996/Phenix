import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

def setup_guard_with_equity(guard, equity=10000):
    """Utility to bootstrap guard with equity using CORRECT keys from exposure_guard.py:403-405"""
    state = {
        "positions_last_ts_ms": int(time.time() * 1000), 
        "equity_free_usdt": str(equity), 
        "open_positions_margin_usd": "0", 
        "positions": []
    }
    guard.on_portfolio(state)
    return state

def test_guard_deny_missing_equity(fsm_config):
    """1. deny if equity data is missing"""
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    guard._latest_portfolio_state = {}
    res = guard.can_open("BTCUSDT", Decimal("100"), {})
    assert res["allowed"] is False
    assert "EQUITY_UNKNOWN" in res["reason"]

def test_guard_deny_stale_portfolio(fsm_config):
    """2. deny if portfolio state is stale"""
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    state = {"positions_last_ts_ms": (time.time() - 1000) * 1000, "equity_free_usdt": "1000", "positions": []}
    res = guard.can_open("BTCUSDT", Decimal("100"), state)
    assert res["allowed"] is False
    assert "PORTFOLIO_STALE" in res["reason"]

def test_guard_deny_max_equity_utilization(fsm_config):
    """3. deny if max equity utilization breached"""
    eg = fsm_config.domains.execution_position.exposure_guard
    eg.max_equity_utilization_pct = "50.0"
    eg.max_portfolio_fraction = "50.0" # Large enough to not interfere
    eg.max_long_utilization_pct = "1000.0" 
    eg.max_short_utilization_pct = "1000.0"
    eg.max_directional_ratio = "100.0"
    eg.max_concentration_pct = "100.0"
    fsm_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    state = setup_guard_with_equity(guard, 1000)
    # 600 notional / 20 leverage = 30 margin. 30/1000 = 3%. Wait 50% util of 1000 is 500 margin.
    # To breach 50% util (500 margin), we need 500 * 20 = 10000 notional.
    res = guard.can_open("BTCUSDT", Decimal("11000"), state)
    assert res["allowed"] is False
    assert "EQUITY_UTILIZATION_BREACH" in res["reason"]

def test_guard_deny_max_portfolio_fraction(fsm_config):
    """4. deny if max portfolio fraction breached"""
    eg = fsm_config.domains.execution_position.exposure_guard
    eg.max_portfolio_fraction = "0.1"
    eg.max_equity_utilization_pct = "100.0" # Large enough
    fsm_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    state = setup_guard_with_equity(guard, 1000)
    # 0.1 of 1000 equity is 100 notional.
    res = guard.can_open("BTCUSDT", Decimal("200"), state)
    assert res["allowed"] is False
    assert "PORTFOLIO_FRACTION_BREACH" in res["reason"]

def test_guard_deny_max_long_utilization(fsm_config):
    """5. deny if total long exposure limit breached"""
    eg = fsm_config.domains.execution_position.exposure_guard
    eg.max_long_utilization_pct = "40.0"
    eg.max_equity_utilization_pct = "100.0" # Large enough
    eg.max_portfolio_fraction = "50.0"
    fsm_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    state = {
        "positions_last_ts_ms": int(time.time() * 1000), 
        "equity_free_usdt": "1000", 
        "open_positions_margin_usd": "300", # 30% util
        "positions": [{"symbol": "ETHUSDT", "side": "BUY", "notional_usd": "6000"}] # 6000 notional / 20 = 300 margin
    }
    guard.on_portfolio(state)
    # Need 110 more margin to reach 400 (40% of 1000). 110 * 20 = 2200 notional.
    res = guard.can_open("BTCUSDT", Decimal("3000"), state)
    assert res["allowed"] is False
    assert "LONG_UTILIZATION_BREACH" in res["reason"]

def test_guard_deny_directional_ratio_long_heavy(fsm_config):
    """7. deny if directional ratio breached"""
    eg = fsm_config.domains.execution_position.exposure_guard
    eg.max_directional_ratio = "2.0"
    fsm_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    setup_guard_with_equity(guard, 2000)
    state = {
        "positions_last_ts_ms": int(time.time() * 1000), 
        "equity_free_usdt": "2000",
        "positions": [
            {"symbol": "ETHUSDT", "side": "BUY", "notional_usd": "6000"}, # 6000 long
            {"symbol": "SOLUSDT", "side": "SELL", "notional_usd": "1000"} # 1000 short
        ]
    }
    guard.on_portfolio(state)
    # Ratio is 6000/1000 = 6.0 > 2.0.
    res = guard.can_open("BTCUSDT", Decimal("100"), state)
    assert res["allowed"] is False
    assert "DIRECTIONAL_RATIO_BREACH" in res["reason"]

def test_guard_allow_when_within_limits(fsm_config):
    """10. allow when all within limits"""
    fsm_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    state = setup_guard_with_equity(guard, 10000)
    res = guard.can_open("BTCUSDT", Decimal("100"), state)
    assert res["allowed"] is True

def test_guard_reserve_and_release(fsm_config):
    """12. test_guard_reserve_and_release"""
    fsm_config.trading.execution.exposure.leverage_defaults = {"BTCUSDT": 20}
    guard = ExposureGuard(fsm_core=MagicMock(), config=fsm_config)
    setup_guard_with_equity(guard)
    guard.reserve("order_1", Decimal("500"), symbol="BTCUSDT", side="BUY")
    assert "order_1" in guard.state.reservations
    guard.release("order_1")
    assert "order_1" not in guard.state.reservations
