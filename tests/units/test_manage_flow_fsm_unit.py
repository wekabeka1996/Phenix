import time
from decimal import Decimal

import importlib.util
import os

# load module directly to avoid ambiguous imports
spec = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.fsm_manage",
    os.path.join(os.path.dirname(__file__), "..", "..", "apps", "reference", "domains", "execution_position", "fsm_manage.py"),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ManageFlowFSM = mod.ManageFlowFSM
ManageState = mod.ManageState
from vfoundation.core.protocol import Message


def test_hydrate_sets_state_and_fields():
    fsm = ManageFlowFSM()
    pos = {
        "qty": "0.1",
        "entry_price": "50000",
        "open_ts": int(time.time()),
        "side": "BUY",
        "sl_order_id": "sl-1",
        "tp_order_id": "tp-1",
        "sl_price": "49900",
        "tp_price": "50500",
        "trailing_activated": True,
    }

    fsm.hydrate(pos)

    assert fsm.state == ManageState.BRACKETS_PLACED
    assert fsm.position_qty == Decimal("0.1")
    assert fsm.position_entry_price == Decimal("50000")
    assert fsm.sl_order_id == "sl-1"
    assert fsm.tp_order_id == "tp-1"


import pytest


def test_calculate_bracket_prices_buy_and_sell():
    fsm = ManageFlowFSM()
    # set entry price and side BUY
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    fsm.config = {"brackets": {"sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}}

    sl, tp = fsm._calculate_bracket_prices()
    # For BUY, sl = entry*(1 - 50/10000) = 99.5 ; tp = entry*(1 + 100/10000) = 101.0
    assert float(sl) == pytest.approx(100 * (1 - 50 / 10000))
    assert float(tp) == pytest.approx(100 * (1 + 100 / 10000))

    # SELL side
    fsm.position_side = "SELL"
    sl2, tp2 = fsm._calculate_bracket_prices()
    # For SELL, sl = entry*(1 + 50/10000), tp = entry*(1 - 100/10000)
    assert float(sl2) == pytest.approx(100 * (1 + 50 / 10000))
    assert float(tp2) == pytest.approx(100 * (1 - 100 / 10000))


def test_emit_place_order_message_contains_expected_fields():
    fsm = ManageFlowFSM()
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "BUY"

    msg = Message(op="EVT", verb="FILL", src="test", dst="manage", rid="rid-1", pld={"symbol": "BTCUSDT"})
    dec = fsm._emit_place_order(msg, "cid123", "LIMIT", "SELL", "0.5", "101.0", "TP bracket")

    assert dec.op == "DEC"
    assert dec.verb == "PLACE_ORDER"
    assert dec.pld["symbol"] == "BTCUSDT"
    assert dec.pld["side"] == "SELL"
    assert dec.pld["qty"] == "0.5"
    assert dec.pld["price"] == "101.0"
