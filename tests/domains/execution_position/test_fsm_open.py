import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM, OpenState

@pytest.fixture
def mock_config():
    return {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "10.0"
                }
            }
        },
        "idempotency_window_sec": 60
    }

@pytest.fixture
def fsm(mock_config):
    return OpenFlowFSM(config=mock_config, cooldown_sec=0.1)

def test_initialization(fsm):
    assert fsm.state == OpenState.IDLE
    assert fsm.cooldown_sec == 0.1
    assert fsm.idempotency_window_sec == 60

def test_handle_ignore_non_cmd_open(fsm):
    msg = Message(op="EVT", verb="TRADE_EXECUTED", src="test", dst="test", pld={})
    assert fsm.handle(msg) is None
    assert fsm.state == OpenState.IDLE

def test_idempotency_reject(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"idempotent_key": "key1", "symbol": "BTCUSDT", "side": "BUY", "qty": "1.0"}
    )

    # First call should succeed (or fail guards, but pass idempotency)
    # We need valid payload to pass guards if we want to test success,
    # but here we just want to test idempotency check which happens early.
    # Actually idempotency check is step 0.

    fsm.handle(msg)
    assert "key1" in fsm.idempotency_store

    # Second call with same key
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert res.pld["reason"] == "duplicate command"

def test_missing_fields_reject(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"qty": "1.0"} # Missing symbol and side
    )
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert res.pld["reason"] == "missing symbol or side"

def test_qty_below_min_reject(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.0001"} # Min is 0.001
    )
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert "qty below minimum" in res.pld["reason"]

def test_qty_rounding(fsm):
    # 0.0015 should round down to 0.001 given step 0.001
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.0015", "order_type": "MARKET", "price_ref": "20000"}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.pld["qty"] == "0.001"

def test_limit_order_missing_price(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "order_type": "LIMIT"}
    )
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert res.pld["reason"] == "LIMIT order requires price"

def test_limit_price_rounding(fsm):
    # 50000.015 should round to 50000.01 given tick 0.01
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "order_type": "LIMIT", "price": "50000.015"}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.pld["price"] == "50000.01"

def test_min_notional_limit_reject(fsm):
    # 0.001 * 1000 = 1.0 < 10.0
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", "order_type": "LIMIT", "price": "1000"}
    )
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert "notional" in res.pld["reason"]

def test_min_notional_market_reject(fsm):
    # 0.001 * 1000 = 1.0 < 10.0
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", "order_type": "MARKET", "price_ref": "1000"}
    )
    res = fsm.handle(msg)
    assert res.op == "ERR"
    assert "estimated notional" in res.pld["reason"]

def test_cooldown_reject(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "order_type": "MARKET", "price_ref": "50000"}
    )
    # First call success
    res1 = fsm.handle(msg)
    assert res1.op == "DEC"

    # Immediate second call should fail cooldown
    res2 = fsm.handle(msg)
    assert res2.op == "ERR"
    assert res2.pld["reason"] == "cooldown active"

    # Wait for cooldown
    time.sleep(0.15)

    # Third call should success (use new rid/key to avoid idempotency check if we were using keys)
    # Here we didn't provide idempotent_key so it's fine
    res3 = fsm.handle(msg)
    assert res3.op == "DEC"

def test_success_path(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0",
            "order_type": "LIMIT",
            "price": "50000.0",
            "tif": "IOC",
            "idempotent_key": "unique_key"
        }
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.verb == "OPEN"
    assert res.pld["symbol"] == "BTCUSDT"
    assert res.pld["side"] == "BUY"
    assert res.pld["qty"] == "1.0"
    assert res.pld["price"] == "50000.0"
    assert res.pld["tif"] == "IOC"
    assert res.pld["idempotent_key"] == "unique_key"
    assert fsm.state == OpenState.DONE

def test_exception_handling(fsm):
    msg = Message(
        op="CMD", verb="OPEN", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0"}
    )

    with patch.object(fsm, "_get_instrument_specs", side_effect=Exception("Boom")):
        res = fsm.handle(msg)
        assert res.op == "ERR"
        assert "FSM exception" in res.why
        assert fsm.state == OpenState.ERROR
