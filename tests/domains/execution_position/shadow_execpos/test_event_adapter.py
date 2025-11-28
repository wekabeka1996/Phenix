"""
Tests for V2RuntimeFacade mapping logic (formerly EventAdapter).
"""
import pytest
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent

@pytest.fixture
def facade():
    f = V2RuntimeFacade(config={}, adapter=MagicMock())
    f.runtime = MagicMock()
    f._submit_to_loop = MagicMock()
    return f

def create_message(op="CMD", verb="OPEN", payload=None, ts=1234567890.0):
    msg = MagicMock()
    msg.op = op
    msg.verb = verb
    msg.pld = payload or {}
    msg.ts = ts
    return msg

def test_entry_intent(facade):
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "1.5",
        "price": "50000",
        "order_type": "LIMIT",
        "client_order_id": "cid_123"
    }
    msg = create_message("CMD", "OPEN", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "ENTRY_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["side"] == "BUY"
    assert str(event.payload["quantity"]) == "1.5"
    assert str(event.payload["price"]) == "50000"
    assert event.payload["order_type"] == "LIMIT"

def test_cancel_intent(facade):
    payload = {"symbol": "BTCUSDT", "order_id": "oid_123"}
    msg = create_message("CMD", "CANCEL", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "CANCEL_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["order_id"] == "oid_123"

def test_close_intent(facade):
    payload = {"symbol": "BTCUSDT", "qty": "1.0", "reason": "manual"}
    msg = create_message("CMD", "CLOSE", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "CLOSE_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["quantity"] == "1.0"
    assert event.payload["reason"] == "manual"

def test_force_close_intent(facade):
    payload = {"symbol": "BTCUSDT", "qty": "1.0"}
    msg = create_message("CMD", "FORCE_CLOSE", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "CLOSE_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["is_force"] is True
    assert event.payload["reason"] == "force_close"

def test_trade_executed(facade):
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "last_qty": "0.5",
        "last_price": "50100",
        "order_id": "oid_123",
        "role": "MAKER",
        "trade_id": "tid_999"
    }
    msg = create_message("EVT", "TRADE_EXECUTED", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "TRADE_EXECUTED"
    assert event.symbol == "BTCUSDT"
    assert event.payload["quantity"] == "0.5"
    assert event.payload["price"] == "50100"
    assert event.payload["role"] == "MAKER"
    assert event.payload["trade_id"] == "tid_999"

def test_position_snapshot_normalization(facade):
    # Test with raw binance-style payload
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.5",
            "entryPrice": "50000",
            "positionSide": "LONG"
        },
        {
            "symbol": "ETHUSDT",
            "position_amount": "-10.0",
            "avg_price": "3000",
            "side": "SHORT"
        }
    ]
    payload = {"positions": positions}
    msg = create_message("EVT", "POSITION_SNAPSHOT", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "POSITION_SNAPSHOT"
    assert len(event.payload["positions"]) == 2

    p1 = event.payload["positions"][0]
    assert p1["symbol"] == "BTCUSDT"
    assert p1["qty"] == 1.5
    assert p1["entry_price"] == 50000.0
    assert p1["side"] == "LONG"

    p2 = event.payload["positions"][1]
    assert p2["symbol"] == "ETHUSDT"
    assert p2["qty"] == -10.0
    assert p2["entry_price"] == 3000.0
    assert p2["side"] == "SHORT"

def test_account_update_mapping(facade):
    # Test mapping of ACCOUNT_UPDATE verb
    positions = [{"symbol": "SOLUSDT", "positionAmt": "100"}]
    payload = {"positions": positions}
    msg = create_message("EVT", "ACCOUNT_UPDATE", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "POSITION_SNAPSHOT"
    assert event.payload["positions"][0]["symbol"] == "SOLUSDT"
    assert event.payload["positions"][0]["qty"] == 100.0

def test_orders_snapshot_normalization(facade):
    orders = [
        {
            "symbol": "BTCUSDT",
            "orderId": "oid_1",
            "clientOrderId": "cid_1",
            "origQty": "1.0",
            "price": "50000",
            "type": "LIMIT",
            "side": "BUY"
        }
    ]
    payload = {"symbol": "BTCUSDT", "orders": orders}
    msg = create_message("EVT", "ORDERS_SNAPSHOT", payload)
    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]

    assert event is not None
    assert event.kind == "ORDERS_SNAPSHOT"
    assert len(event.payload["orders"]) == 1

    o1 = event.payload["orders"][0]
    assert o1["order_id"] == "oid_1"
    assert o1["client_order_id"] == "cid_1"
    assert o1["quantity"] == "1.0"
    assert o1["type"] == "LIMIT"

def test_unknown_message(facade):
    msg = create_message("CMD", "UNKNOWN_VERB", {})
    facade.handle(msg)
    assert not facade.runtime.handle.called

def test_malformed_message(facade):
    # msg without op/verb attributes
    msg = MagicMock(spec=[])
    facade.handle(msg)
    assert not facade.runtime.handle.called
