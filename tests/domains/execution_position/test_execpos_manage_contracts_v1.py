import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageState, ManageFlowFSM

def test_manage_does_not_emit_adjust_when_flat(fsm_harness):
    """1. test_manage_does_not_emit_modify_when_position_not_open"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    manage.state = ManageState.FLAT
    
    # MARKET_DATA update while FLAT
    msg = Message(
        op="UPD", verb="MARKET_DATA", src="ws", dst="exec",
        pld={"symbol": "BTCUSDT", "last_price": "50000"}
    )
    result = manage.handle(msg)
    
    # In FLAT state, MARKET_DATA should skip rules (no position to manage)
    assert result is None

def test_manage_tpsl_values_respect_side_invariants(fsm_harness):
    """3. test_manage_tpsl_values_respect_side_invariants"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    
    # Setup LONG position
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_side = "BUY"
    manage.position_qty = Decimal("1.0")
    manage.position_entry_price = Decimal("50000")
    
    # Trigger bracket placement logic
    sl, tp1, tp2 = manage._calculate_bracket_prices()
    
    # LONG: SL < Entry, TP > Entry
    assert sl < manage.position_entry_price
    assert tp1 > manage.position_entry_price
    
    # Setup SHORT position
    manage.position_side = "SELL"
    sl, tp1, tp2 = manage._calculate_bracket_prices()
    
    # SHORT: SL > Entry, TP < Entry
    assert sl > manage.position_entry_price
    assert tp1 < manage.position_entry_price

def test_manage_idempotency_on_adjustment(fsm_harness):
    """4. test_manage_idempotency_on_modify (Adjustment rate limiting)"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    
    # Setup tracking
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_side = "BUY"
    manage.position_qty = Decimal("1.0")
    manage.position_entry_price = Decimal("50000")
    manage.sl_order_id = "sl_123"
    manage.sl_price = Decimal("49500")
    
    # Mock _check_trailing_stop to return an adjustment
    with patch("apps.reference.domains.execution_position.fsm_manage.time.time") as mock_time:
        mock_time.return_value = 1000.0 # t=1000
        
        # Mock _get_trailing_stop_params to return enabled
        with patch.object(manage, "_get_trailing_stop_params", return_value=(True, 0.003, 0.006, 5)):
             # First call hits adjustment (price moved up to 51000)
             msg1 = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "51000", "ts": 1000000})
             res1 = manage.handle(msg1)
             assert res1 is not None
             assert res1.verb == "CANCEL_ORDER" # Part of _adjust_trailing_stop
             
             # Update last_trailing_ts manually as if adjustment happened
             manage.last_trailing_ts = 1000.0
             manage.state = ManageState.TRACKING
             
             # Second call with t=1002 (within 5s cooldown)
             mock_time.return_value = 1002.0
             msg2 = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "51500", "ts": 1002000})
             res2 = manage.handle(msg2)
             assert res2 is None # Must be rate limited

def test_manage_handles_missing_market_data_fail_closed(fsm_harness):
    """5. test_manage_handles_missing_market_data_fail_closed"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_qty = Decimal("1.0")
    manage.position_entry_price = Decimal("50000")
    
    # Message with missing price
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT"})
    result = manage.handle(msg)
    
    # Should not emit anything if price is missing
    assert result is None

def test_manage_max_hold_time_triggers_close(fsm_harness):
    """6. test_manage_max_hold_time_triggers_close"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_open_ts = 1000.0
    manage.position_qty = Decimal("1.0")
    manage.position_entry_price = Decimal("50000") # CRITICAL FIX: missing in previous turn
    manage.position_side = "BUY"
    
    # Configure max_hold_sec directly on manage mock to be safe
    with patch.object(manage, "_get_max_hold_sec", return_value=60):
        with patch("apps.reference.domains.execution_position.fsm_manage.time.time") as mock_time:
            # Check at t=1010 (10s elapsed) -> No close
            mock_time.return_value = 1010.0
            msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "ts": 1010000})
            res1 = manage.handle(msg)
            assert res1 is None
            
            # Check at t=1070 (70s elapsed) -> Trigger close
            mock_time.return_value = 1070.0
            res2 = manage.handle(msg)
            assert res2 is not None
            assert res2.verb == "CLOSE_POSITION"
            assert res2.pld["reason"] == "MAX_HOLD_TIME_EXCEEDED"

def test_manage_emits_modify_only_when_auto_enabled(fsm_harness):
    """2. test_manage_emits_modify_only_when_limits_allow (Auto-manage gate)"""
    fsm, bus, cfg = fsm_harness
    
    # Inject manage flow manually for test
    manage = ManageFlowFSM(config=cfg)
    fsm.manage_flows["BTCUSDT"] = manage
    
    # Disable auto-manage
    manage._auto_manage_enabled = False
    manage.state = ManageState.TRACKING
    
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50000"})
    res = manage.handle(msg)
    
    # Should emit MANAGE_SKIPPED instead of rule evaluation
    assert res is not None
    assert res.verb == "MANAGE_SKIPPED"
    assert res.pld["reason"] == "auto_manage_disabled"
