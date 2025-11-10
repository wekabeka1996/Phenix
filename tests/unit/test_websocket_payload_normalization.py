"""
Unit tests for WebSocket payload normalization in BinanceExecutionAdapter.

Tests ensure that Binance ORDER_TRADE_UPDATE events are properly normalized
to flat structure with orderId/status on top level for FSM consumption.
"""

import pytest
import time
from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)


def test_normalize_order_event_with_real_binance_payload():
    """
    Test normalization with real Binance ORDER_TRADE_UPDATE structure.

    Validates that nested {"o": {"i": orderId, ...}} is flattened to
    {"orderId": ..., ...} for ManageFlowFSM OCO emulation.
    """
    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Real Binance ORDER_TRADE_UPDATE payload (from official docs)
    raw_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1568879465651,  # Event time
        "T": 1568879465650,  # Transaction time
        "o": {
            "s": "BTCUSDT",       # Symbol
            "c": "ENTRY-abc123",  # Client order ID
            "S": "BUY",           # Side
            "o": "MARKET",        # Order type
            "f": "GTC",           # Time in force
            "q": "0.001",         # Original quantity
            "p": "0",             # Price
            "ap": "9000.0",       # Average price
            "sp": "0",            # Stop price
            "x": "TRADE",         # Execution type
            "X": "FILLED",        # Order status
            "i": 6375394853,      # Order ID (integer)
            "l": "0.001",         # Last filled quantity
            "z": "0.001",         # Cumulative filled quantity
            "L": "9000.0",        # Last filled price
            "n": "0",             # Commission
            "N": "USDT",          # Commission asset
            "T": 1568879465650,   # Order trade time
            "t": 1234567890,      # Trade ID
            "b": "100000",        # Bids notional
            "a": "0",             # Ask notional
            "m": False,           # Is maker side
            "R": False,           # Reduce only
            "wt": "CONTRACT_PRICE",
            "ot": "MARKET",
            "ps": "BOTH",
            "cp": False,          # Close position
        }
    }

    normalized = adapter._normalize_order_event(raw_event)

    # Assert flat structure with key fields on top level
    assert normalized["orderId"] == "6375394853"  # Integer -> string
    assert normalized["clientOrderId"] == "ENTRY-abc123"
    assert normalized["symbol"] == "BTCUSDT"
    assert normalized["status"] == "FILLED"
    assert normalized["side"] == "buy"  # Lowercase
    assert normalized["type"] == "market"  # Lowercase
    assert normalized["executedQty"] == "0.001"
    assert normalized["reduceOnly"] is False
    assert normalized["closePosition"] is False
    assert normalized["timestamp"] == 1568879465650

    # Verify raw event is preserved for debugging
    assert "_raw_binance_event" in normalized
    assert normalized["_raw_binance_event"] == raw_event


def test_normalize_order_event_with_sl_bracket():
    """
    Test normalization with STOP_MARKET bracket order.

    Ensures SL brackets have orderId properly extracted.
    """
    adapter = BinanceExecutionAdapter(shadow_mode=True)

    raw_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1568879466000,
        "T": 1568879465999,
        "o": {
            "s": "ETHUSDT",
            "c": "SL-xyz789",
            "S": "SELL",
            "o": "STOP_MARKET",
            "X": "NEW",
            "i": 7654321098,  # SL order ID
            "q": "0.1",
            "z": "0",
            "R": True,  # reduceOnly=true for brackets
            "cp": True,  # closePosition=true for brackets
        }
    }

    normalized = adapter._normalize_order_event(raw_event)

    assert normalized["orderId"] == "7654321098"
    assert normalized["clientOrderId"] == "SL-xyz789"
    assert normalized["status"] == "NEW"
    assert normalized["reduceOnly"] is True
    assert normalized["closePosition"] is True


def test_normalize_order_event_with_tp_bracket():
    """
    Test normalization with TAKE_PROFIT_MARKET bracket order.

    Ensures TP brackets have orderId properly extracted.
    """
    adapter = BinanceExecutionAdapter(shadow_mode=True)

    raw_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1568879467000,
        "T": 1568879466999,
        "o": {
            "s": "SOLUSDT",
            "c": "TP-def456",
            "S": "SELL",
            "o": "TAKE_PROFIT_MARKET",
            "X": "FILLED",
            "i": 9876543210,  # TP order ID
            "q": "1.5",
            "z": "1.5",
            "ap": "25.5",
            "R": True,
            "cp": True,
        }
    }

    normalized = adapter._normalize_order_event(raw_event)

    assert normalized["orderId"] == "9876543210"
    assert normalized["clientOrderId"] == "TP-def456"
    assert normalized["status"] == "FILLED"
    assert normalized["executedQty"] == "1.5"
    assert normalized["avgPrice"] == "25.5"


def test_normalize_order_event_with_already_flat_structure():
    """
    Test normalization when event is already flat (backward compatibility).

    Ensures function doesn't break if payload format changes.
    """
    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Already normalized payload (no nested "o")
    flat_event = {
        "orderId": "1234567890",
        "clientOrderId": "ENTRY-test",
        "symbol": "BTCUSDT",
        "status": "FILLED",
        "side": "buy",
        "type": "market",
    }

    normalized = adapter._normalize_order_event(flat_event)

    # Should return as-is
    assert normalized == flat_event


def test_normalize_order_event_with_empty_payload():
    """
    Test normalization with empty/malformed payload.

    Ensures graceful handling of missing fields.
    """
    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Empty nested structure
    raw_event = {
        "e": "ORDER_TRADE_UPDATE",
        "o": {}
    }

    normalized = adapter._normalize_order_event(raw_event)

    # Should have default empty strings
    assert normalized["orderId"] == ""
    assert normalized["clientOrderId"] == ""
    assert normalized["symbol"] == ""
    assert normalized["status"] == ""


def test_integration_handle_order_trade_update_includes_orderId_in_payload():
    """
    Integration test: Verify _handle_order_trade_update emits payload with orderId.

    This ensures ManageFlowFSM._handle_bracket_fill() can match orderId.
    """
    # Mock FSM core
    class MockFSMCore:
        def __init__(self):
            self.emitted_events = []
            self.order_index = None

        def emit(self, verb, payload, why):
            self.emitted_events.append(
                {"verb": verb, "payload": payload, "why": why})

    fsm_core = MockFSMCore()
    adapter = BinanceExecutionAdapter(shadow_mode=True, fsm_core=fsm_core)

    # Mock order_index
    class MockOrderRef:
        def __init__(self):
            self.rid = "test-rid-123"
            self.idempotent_key = "test-idem-key"
            self.created_ts = time.time()

    class MockOrderIndex:
        def get(self, clientOrderId=None, exchangeOrderId=None):
            return MockOrderRef()

        def mark_terminal(self, order_ref):
            pass

    fsm_core.order_index = MockOrderIndex()

    # Simulate WebSocket ORDER_TRADE_UPDATE
    raw_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1568879465651,
        "T": 1568879465650,
        "o": {
            "s": "BTCUSDT",
            "c": "ENTRY-test",
            "S": "BUY",
            "o": "MARKET",
            "X": "FILLED",
            "i": 1234567890,
            "q": "0.01",
            "z": "0.01",
            "p": "0",
            "ap": "50000.0",
            "R": False,
            "cp": False,
        }
    }

    # Process event
    adapter._handle_order_trade_update(raw_event)

    # Verify payload includes orderId on top level
    assert len(fsm_core.emitted_events) == 1
    event = fsm_core.emitted_events[0]
    # Adapter emits EVT:TRADE_EXECUTED for FILLED orders (not ORDER_STATE_CHANGED)
    assert event["verb"] in ("EVT:TRADE_EXECUTED", "EVT:ORDER_STATE_CHANGED")
    assert "orderId" in event["payload"]
    assert event["payload"]["orderId"] == "1234567890"
    assert event["payload"]["status"] == "FILLED"
    assert event["payload"]["exchangeOrderId"] == "1234567890"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
