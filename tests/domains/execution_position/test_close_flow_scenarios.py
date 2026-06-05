
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.flows.close.fsm_close import CloseFlowFSM, CloseState
from apps.reference.core.time import get_clock

class TestCloseFlowScenarios:
    
    def test_transition_flat_to_opened_on_trade_executed(self):
        close_flow = CloseFlowFSM()
        
        # Initial state
        assert close_flow.state == CloseState.FLAT
        assert close_flow.position_active is False
        
        # Simulate TRADE_EXECUTED
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="execution_position",
            rid="rid-1",
            pld={"symbol": "BTCUSDT", "qty": "0.1", "price": "50000", "order_id": "oid-1"},
            why="test-entry"
        )
        
        # Should transition to OPENED
        res = close_flow.handle(msg)
        
        assert close_flow.state == CloseState.OPENED
        assert close_flow.position_active is True
        assert close_flow.position_open_ts > 0
        assert res is None # No immediate close condition

    def test_transition_flat_to_opened_on_partial_fill(self):
        close_flow = CloseFlowFSM()
        
        msg = Message(
            op="EVT",
            verb="PARTIAL_FILL",
            src="adapter",
            dst="execution_position",
            rid="rid-2",
            pld={"symbol": "BTCUSDT", "qty": "0.05", "price": "50000", "order_id": "oid-2"},
            why="test-entry"
        )
        
        close_flow.handle(msg)
        assert close_flow.state == CloseState.OPENED
        assert close_flow.position_active is True

    def test_ignore_zero_qty_fill(self):
        close_flow = CloseFlowFSM()
        
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="adapter",
            dst="execution_position",
            rid="rid-3",
            pld={"symbol": "BTCUSDT", "qty": "0.0", "price": "50000"},
            why="test-entry"
        )
        
        close_flow.handle(msg)
        assert close_flow.state == CloseState.FLAT
        assert close_flow.position_active is False

    def test_cmd_close_emits_dec_close(self):
        close_flow = CloseFlowFSM()
        # Pre-seed state (though CMD:CLOSE works even from FLAT)
        close_flow.state = CloseState.OPENED
        close_flow.position_active = True
        
        msg = Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            rid="rid-close",
            pld={"symbol": "BTCUSDT", "reason": "signal_flip"},
            why="regime_change"
        )
        
        dec = close_flow.handle(msg)
        
        assert dec is not None
        assert dec.op == "DEC"
        assert dec.verb == "CLOSE"
        assert dec.pld["reduce_only"] is True
        assert dec.pld["reason"] == "signal_flip"
        assert dec.pld["symbol"] == "BTCUSDT"
        
        assert close_flow.state == CloseState.DONE
        assert close_flow.position_active is False
        
        metrics = close_flow.get_metrics()
        assert metrics["fsm_close_decisions_total"] == 1

    def test_hydration_success(self):
        close_flow = CloseFlowFSM()
        
        pos_data = {
            "symbol": "BTCUSDT",
            "open_ts": 1234567890.0,
            "side": "LONG"
        }
        
        close_flow.hydrate(pos_data)
        
        assert close_flow.state == CloseState.OPENED
        assert close_flow.position_active is True
        assert close_flow.position_open_ts == 1234567890.0

    def test_hydration_error_safe(self):
        close_flow = CloseFlowFSM()
        
        # Pass invalid data that might cause error (though simple dict access is robust, 
        # let's assume valid dict but check if it handles it gracefully)
        # Actually hydrate only accesses open_ts and sets state.
        # Let's mock get_clock to raise exception to trigger except block
        
        with patch("apps.reference.domains.execution_position.flows.close.fsm_close.get_clock", side_effect=Exception("Time error")):
            # omit open_ts to force get_clock() call
            close_flow.hydrate({"symbol": "BTCUSDT"})
            
        assert close_flow.state == CloseState.ERROR
        metrics = close_flow.get_metrics()
        assert metrics["fsm_errors_total"] == 1

    def test_autonomous_close_disabled(self):
        # Verify that autonomous rules (stubbed) do not trigger close
        close_flow = CloseFlowFSM()
        close_flow.state = CloseState.OPENED
        
        msg_tick = Message(
            op="UPD",
            verb="TICK",
            src="market_data",
            dst="execution_position",
            rid="tick-1",
            pld={"price": "100"},
            why="timer"
        )
        
        res = close_flow.handle(msg_tick)
        assert res is None # Should return None per "soldier" pattern

    def test_reset(self):
        close_flow = CloseFlowFSM()
        close_flow.state = CloseState.DONE
        close_flow.position_active = True # Manually set to bad state to verify reset
        
        close_flow.reset()
        
        assert close_flow.state == CloseState.FLAT
        assert close_flow.position_active is False
        assert close_flow.position_open_ts == 0.0

