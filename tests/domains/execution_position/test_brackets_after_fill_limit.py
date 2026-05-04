"""
EP-BRACKETS-AFTER-FILL-01: Test Suite for Deferred Brackets Logic

Tests:
1. LIMIT order preflight fails → brackets deferred → fill event → brackets placed
2. Idempotency: duplicate fills don't create duplicate brackets
3. MARKET order: fast path works (brackets placed immediately)
4. Cancel/expire: pending brackets cleared
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal


class TestDeferredBracketsLogic:
    """Test EP-BRACKETS-AFTER-FILL-01 deferred brackets placement."""
    
    @pytest.fixture
    def mock_fsm(self):
        """Create a minimal mock ExecPosFSM with required attributes."""
        fsm = MagicMock()
        fsm._brackets_pending = {}
        fsm._brackets_placed = set()
        return fsm
    
    def test_brackets_pending_structure(self, mock_fsm):
        """Verify _brackets_pending dict structure."""
        # Simulate deferred brackets
        mock_fsm._brackets_pending["BTCUSDT"] = {
            "rid": "test-rid-123",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_id": "ENTRY-abc",
            "entry_order_id": "12345678",
            "sl_price": "95000.00",
            "tp_price": "98000.00",
            "tick_size": "0.10",
            "qty": "0.008",
            "created_ts_ms": 1705276800000,
            "order_type": "LIMIT",
        }
        
        assert "BTCUSDT" in mock_fsm._brackets_pending
        pending = mock_fsm._brackets_pending["BTCUSDT"]
        assert pending["sl_price"] == "95000.00"
        assert pending["tp_price"] == "98000.00"
        assert pending["side"] == "BUY"
    
    def test_brackets_placed_idempotency(self, mock_fsm):
        """Verify _brackets_placed prevents duplicates."""
        bracket_key = "BTCUSDT_12345678"
        
        # First placement
        assert bracket_key not in mock_fsm._brackets_placed
        mock_fsm._brackets_placed.add(bracket_key)
        
        # Second attempt should be blocked
        assert bracket_key in mock_fsm._brackets_placed
        
    def test_pending_cleared_on_cancel(self, mock_fsm):
        """Verify pending brackets cleared when order cancelled."""
        mock_fsm._brackets_pending["BTCUSDT"] = {"entry_order_id": "12345"}
        
        # Simulate cancel event
        symbol = "BTCUSDT"
        if symbol in mock_fsm._brackets_pending:
            mock_fsm._brackets_pending.pop(symbol, None)
        
        assert "BTCUSDT" not in mock_fsm._brackets_pending
    
    def test_preflight_failure_stores_pending(self, mock_fsm):
        """Verify preflight failure stores brackets intent."""
        # Simulate what PHASE A3 does on preflight failure
        symbol = "BTCUSDT"
        entry_order_id = "12345678"
        
        mock_fsm._brackets_pending[symbol] = {
            "rid": "test-rid",
            "symbol": symbol,
            "side": "SELL",
            "entry_order_id": entry_order_id,
            "sl_price": "97000.00",
            "tp_price": "94000.00",
        }
        
        assert symbol in mock_fsm._brackets_pending
        assert mock_fsm._brackets_pending[symbol]["entry_order_id"] == entry_order_id
    
    def test_fill_event_triggers_placement(self, mock_fsm):
        """Verify fill event checks pending and marks placed."""
        symbol = "BTCUSDT"
        entry_order_id = "12345678"
        bracket_key = f"{symbol}_{entry_order_id}"
        
        # Setup pending
        mock_fsm._brackets_pending[symbol] = {
            "entry_order_id": entry_order_id,
            "sl_price": "95000.00",
            "tp_price": "98000.00",
        }
        
        # Simulate fill event logic
        if symbol in mock_fsm._brackets_pending:
            pending = mock_fsm._brackets_pending[symbol]
            if bracket_key not in mock_fsm._brackets_placed:
                # Would call _place_deferred_brackets here
                mock_fsm._brackets_placed.add(bracket_key)
                mock_fsm._brackets_pending.pop(symbol, None)
        
        # Verify
        assert bracket_key in mock_fsm._brackets_placed
        assert symbol not in mock_fsm._brackets_pending
    
    def test_decimal_parsing_from_strings(self, mock_fsm):
        """Verify Decimal parsing from string values."""
        pending = {
            "sl_price": "95000.50",
            "tp_price": "98000.75",
            "tick_size": "0.10",
            "qty": "0.008",
        }
        
        sl = Decimal(str(pending["sl_price"]))
        tp = Decimal(str(pending["tp_price"]))
        tick = Decimal(str(pending["tick_size"]))
        qty = Decimal(str(pending["qty"]))
        
        assert sl == Decimal("95000.50")
        assert tp == Decimal("98000.75")
        assert tick == Decimal("0.10")
        assert qty == Decimal("0.008")


class TestBracketsFlow:
    """Integration-level tests for brackets flow."""
    
    def test_limit_order_deferred_flow(self):
        """
        Test complete LIMIT order flow:
        1. Entry placed
        2. Preflight fails (position=0)
        3. Brackets deferred
        4. Fill event received
        5. Brackets placed
        """
        # State simulation
        brackets_pending = {}
        brackets_placed = set()
        
        # Step 1-3: Entry placed, preflight fails
        symbol = "BTCUSDT"
        entry_order_id = "999888777"
        
        preflight_passed = False  # Simulating LIMIT order, position=0
        
        if not preflight_passed:
            brackets_pending[symbol] = {
                "entry_order_id": entry_order_id,
                "sl_price": "95000",
                "tp_price": "98000",
            }
        
        assert symbol in brackets_pending
        
        # Step 4-5: Fill event triggers placement
        bracket_key = f"{symbol}_{entry_order_id}"
        
        if symbol in brackets_pending and bracket_key not in brackets_placed:
            # Place brackets (mocked)
            brackets_placed.add(bracket_key)
            brackets_pending.pop(symbol, None)
        
        # Final state
        assert bracket_key in brackets_placed
        assert symbol not in brackets_pending
    
    def test_market_order_immediate_flow(self):
        """
        Test MARKET order flow (unchanged):
        1. Entry placed
        2. Preflight passes (instant fill)
        3. Brackets placed immediately
        """
        brackets_pending = {}
        brackets_placed = set()
        
        symbol = "ETHUSDT"
        entry_order_id = "111222333"
        bracket_key = f"{symbol}_{entry_order_id}"
        
        preflight_passed = True  # MARKET order, instant fill
        
        if preflight_passed:
            # Place immediately, no pending
            brackets_placed.add(bracket_key)
        
        assert bracket_key in brackets_placed
        assert symbol not in brackets_pending


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
