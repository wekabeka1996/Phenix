import pytest
from vfoundation.core.protocol import Message
import time
from decimal import Decimal

import importlib.util
import os

# load module directly to avoid ambiguous imports
spec = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.legacy.fsm_manage",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "apps",
        "reference",
        "domains",
        "execution_position",
        "fsm_manage.py",
    ),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ManageFlowFSM = mod.ManageFlowFSM
ManageState = mod.ManageState
ResolvedBrackets = mod.ResolvedBrackets


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


def test_calculate_bracket_prices_buy_and_sell():
    fsm = ManageFlowFSM()
    # set entry price and side BUY
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"
    brackets_cfg = {
        "sl": {"fixed_bps": 50},
        "tp": {"fixed_bps": 100},
    }
    fsm.config = {
        "trading": {
            "execution": {
                "manage": {
                    "brackets": brackets_cfg,
                }
            }
        }
    }

    resolved = ResolvedBrackets(
        sl_bps=Decimal("50"),
        tp_bps=Decimal("100"),
        offset_bps=5,
        sl_source="test",
        tp_source="test",
    )

    sl, tp = fsm._calculate_bracket_prices(
        resolved,
        tick_size=Decimal("0.1"),
        offset_bps=Decimal("5"),
    )
    assert sl is not None and tp is not None
    assert sl < fsm.position_entry_price
    assert tp > fsm.position_entry_price

    # SELL side
    fsm.position_side = "SELL"
    sl2, tp2 = fsm._calculate_bracket_prices(
        resolved,
        tick_size=Decimal("0.1"),
        offset_bps=Decimal("5"),
    )
    assert sl2 is not None and tp2 is not None
    assert sl2 > fsm.position_entry_price
    assert tp2 < fsm.position_entry_price


def test_emit_place_order_message_contains_expected_fields():
    fsm = ManageFlowFSM()
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "BUY"

    msg = Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="manage",
        rid="rid-1",
        pld={"symbol": "BTCUSDT"},
    )
    dec = fsm._emit_place_order(
        msg, "cid123", "LIMIT", "SELL", "0.5", "101.0", "TP bracket"
    )

    assert dec.op == "DEC"
    assert dec.verb == "PLACE_ORDER"
    assert dec.pld["symbol"] == "BTCUSDT"
    assert dec.pld["side"] == "SELL"
    assert dec.pld["qty"] == "0.5"
    assert dec.pld["price"] == "101.0"
    assert dec.pld["positionSide"] == "LONG"
    assert dec.pld["position_side"] == "LONG"


def test_emit_place_order_sets_stop_price_for_take_profit_market():
    fsm = ManageFlowFSM()
    fsm.position_qty = Decimal("0.25")
    fsm.position_side = "BUY"

    msg = Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="manage",
        rid="rid-2",
        pld={"symbol": "ETHUSDT"},
    )

    dec = fsm._emit_place_order(
        msg,
        "cid-tp",
        "TAKE_PROFIT_MARKET",
        "SELL",
        "0.25",
        "3050.0",
        "TP agg",
    )

    assert dec.pld["stopPrice"] == "3050.0"
    assert dec.pld["price"] is None
    assert dec.pld["positionSide"] == "LONG"
    assert dec.pld["position_side"] == "LONG"

