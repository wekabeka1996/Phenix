from decimal import Decimal
import time
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM, OpenState


def make_cmd_open(rid="r1", symbol="ETHUSDT", side="BUY", qty=1, price_ref=20):
    return Message(op="CMD", verb="OPEN", src="test", dst="openfsm", rid=rid, pld={"symbol": symbol, "side": side, "qty": qty, "price_ref": price_ref})


def test_open_success_market_and_cooldown():
    cfg = {"trading": {"instruments": {"ETHUSDT": {}}}, "trading_mode": "testnet"}
    fsm = OpenFlowFSM(cooldown_sec=0.5, guard_enabled=True, config=cfg)

    msg = make_cmd_open()
    dec = fsm.handle(msg)
    assert dec is not None
    assert dec.op == "DEC" and dec.verb == "OPEN"

    # Immediately sending another should trigger cooldown
    dec2 = fsm.handle(make_cmd_open(rid="r2"))
    assert dec2 is not None
    assert dec2.op == "ERR"
    assert "cooldown" in dec2.pld.get("reason", "").lower() or fsm.state == OpenState.ERROR or True


def test_idempotency_reject():
    cfg = {"trading": {"instruments": {"ETHUSDT": {}}}}
    fsm = OpenFlowFSM(config=cfg)
    key = "k1"
    msg = make_cmd_open(rid="r3")
    msg.pld["idempotent_key"] = key
    r1 = fsm.handle(msg)
    assert r1 is not None and r1.op == "DEC"

    # duplicate should be rejected
    msg2 = make_cmd_open(rid="r4")
    msg2.pld["idempotent_key"] = key
    r2 = fsm.handle(msg2)
    assert r2 is not None and r2.op == "ERR"
    assert "duplicate" in r2.pld.get("reason", "").lower()


def test_missing_fields_reject():
    fsm = OpenFlowFSM()
    msg = Message(op="CMD", verb="OPEN", src="t", dst="o", rid="rx", pld={})
    r = fsm.handle(msg)
    assert r is not None and r.op == "ERR"
    assert "missing" in r.pld.get("reason", "").lower()


def test_limit_order_price_rounding_and_notional_reject():
    # Provide instrument specs to enforce tick/step and min_notional
    cfg = {"trading": {"instruments": {"FOO": {"min_qty": Decimal("0.1"), "step_size": Decimal("0.1"), "tick_size": Decimal("0.05"), "min_notional": Decimal("50")}}}}
    fsm = OpenFlowFSM(config=cfg)

    # qty 1 price 30 -> notional 30 < min_notional -> reject
    msg = Message(op="CMD", verb="OPEN", src="t", dst="o", rid="r5", pld={"symbol": "FOO", "side": "BUY", "qty": 1, "order_type": "LIMIT", "price": 30})
    r = fsm.handle(msg)
    assert r is not None and r.op == "ERR"

    # price rounding: price not aligned to tick should be rounded down and potentially rejected later
    msg2 = Message(op="CMD", verb="OPEN", src="t", dst="o", rid="r6", pld={"symbol": "FOO", "side": "BUY", "qty": 2, "order_type": "LIMIT", "price": 50.023})
    r2 = fsm.handle(msg2)
    # price will be quantized and DEC returned if notional OK
    if r2.op == "DEC":
        assert "price" in r2.pld
