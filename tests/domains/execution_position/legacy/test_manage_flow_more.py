import time
import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.legacy.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)

pytestmark = pytest.mark.execpos_legacy


def make_fill_msg(rid="r1", qty=1, price=100.0, side="BUY"):
    return Message(
        op="EVT",
        verb="FILL",
        src="t",
        dst="mgr",
        rid=rid,
        pld={"qty": qty, "price": price, "side": side},
    )


def test_on_fill_average_down():
    fsm = ManageFlowFSM()
    # initial fill
    msg1 = make_fill_msg(rid="a1", qty=1, price=100.0, side="BUY")
    fsm._on_fill(msg1)
    assert fsm.position_qty == Decimal("1")
    # second fill to average down/up
    msg2 = make_fill_msg(rid="a2", qty=1, price=110.0, side="BUY")
    fsm._on_fill(msg2)
    assert fsm.position_qty == Decimal("2")
    assert fsm.position_entry_price is not None


def test_place_brackets_and_on_bracket_placed():
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "brackets": {"enable": True, "sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)
    fsm.position_qty = Decimal("1")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"  # Binance uses BUY/SELL, not LONG/SHORT
    fsm.position_open_ts = time.time()

    msg = make_fill_msg(rid="b1")
    dec = fsm._place_brackets(msg)
    # should return a DEC for SL (first order)
    assert dec is not None
    assert dec.op == "DEC"
    assert dec.verb == "PLACE_ORDER"

    # simulate bracket placed messages for SL and TP
    sl_msg = Message(
        op="EVT",
        verb="ORDER_UPDATED",
        src="ex",
        dst="mgr",
        rid="b1",
        pld={"clientOrderId": "b1_1_sl", "orderId": "o_sl"},
    )
    tp_msg = Message(
        op="EVT",
        verb="ORDER_UPDATED",
        src="ex",
        dst="mgr",
        rid="b1",
        pld={"clientOrderId": "b1_1_tp", "orderId": "o_tp"},
    )
    fsm._on_bracket_placed(sl_msg)
    fsm._on_bracket_placed(tp_msg)
    assert fsm.sl_order_id == "o_sl"
    assert fsm.tp_order_id == "o_tp"
    assert fsm.state == ManageState.BRACKETS_PLACED


def test_trailing_activation_and_adjust():
    cfg = {
        "trailing": {
            "enable": True,
            "activation_profit_atr_k": 1.0,
            "cooldown_sec": 0,
            "step_bps": 10,
        }
    }
    cfg_full = {
        "trading": {
            "execution": {
                "manage": {
                    "brackets": {"enable": True},
                    "trailing": cfg["trailing"]
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg_full)
    fsm.position_qty = Decimal("1")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "BUY"  # Binance uses BUY/SELL
    fsm.sl_price = Decimal("95")
    fsm.sl_order_id = "s1"
    fsm.position_open_ts = time.time() - 1000
    fsm.last_trailing_ts = 0

    # MARKET_DATA update with mark_price high enough to activate trailing
    msg = Message(
        op="UPD",
        verb="MARKET_DATA",
        src="md",
        dst="mgr",
        rid="t1",
        pld={"mark_price": 110},
    )
    # first call may activate trailing but not adjust due to cooldown; we've set cooldown=0
    result = fsm._check_trailing_stop(msg)
    # If adjustment occurs, we expect a DEC CANCEL_ORDER returned
    if result is not None:
        assert result.op == "DEC"
        assert result.verb == "CANCEL_ORDER"
    else:
        # If no result, at least trailing should be activated
        assert fsm.trailing_activated is True


def test_get_metrics_and_reset():
    fsm = ManageFlowFSM()
    fsm._metrics["fsm_adjust_decisions_total"] = 3
    m = fsm.get_metrics()
    assert isinstance(m, dict) and m["fsm_adjust_decisions_total"] == 3
    fsm.reset()
    assert fsm.state == ManageState.FLAT
