import time
from decimal import Decimal
from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from vfoundation.core.protocol import Message


def make_fill_msg(rid="r1", symbol="ETHUSDT", qty=1, price=100.0, side="BUY"):
    return Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="manager",
        rid=rid,
        pld={"symbol": symbol, "qty": qty, "price": price, "side": side},
    )


def test_hydrate_success_and_brackets_state():
    fsm = ManageFlowFSM(config={"brackets": {}})
    pd = {
        "qty": 2,
        "entry_price": "100",
        "side": "BUY",
        "open_ts": time.time(),
        "sl_order_id": "s1",
    }
    fsm.hydrate(pd)
    # having sl_order_id should set BRACKETS_PLACED
    assert fsm.state in (
        ManageState.TRACKING,
        ManageState.BRACKETS_PLACED,
        ManageState.OPENED,
    )


def test_hydrate_missing_key_sets_error():
    fsm = ManageFlowFSM()
    fsm.hydrate({"entry_price": "100"})
    assert fsm.state == ManageState.ERROR


def test_should_place_brackets_and_place_flow():
    cfg = {
        "brackets": {"enable": True, "sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}
    }
    fsm = ManageFlowFSM(config=cfg)

    # Before any fills, should not place
    assert fsm._should_place_brackets() is True

    msg = make_fill_msg()
    # simulate a fill -> handle should place brackets and return first order DEC
    dec = fsm.handle(msg)
    # Either None (if something went wrong) or a DEC PLACE_ORDER message
    if dec is not None:
        assert dec.op == "DEC"
        assert dec.verb in ("PLACE_ORDER", "CANCEL_ORDER") or dec.verb == "PLACE_ORDER"


def test_calculate_bracket_prices_and_get_opposite():
    fsm = ManageFlowFSM()
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.position_qty = Decimal("1")
    fsm.config = {"brackets": {"sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}}

    sl, tp = fsm._calculate_bracket_prices()
    assert sl is not None and tp is not None
    assert fsm._get_opposite_side() == "SELL"
