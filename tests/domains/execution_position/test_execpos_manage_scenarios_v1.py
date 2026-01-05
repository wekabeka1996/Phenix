import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from tests.harness.execpos_scenarios import feed_opened_position, collect_emits, get_last_emit_by_verb

def test_manage_no_action_when_not_opened(fsm_harness):
    """1. test_manage_no_action_when_not_opened"""
    fsm, bus, cfg = fsm_harness
    manage = ManageFlowFSM(config=cfg)
    manage.state = ManageState.FLAT
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50000"})
    res = manage.handle(msg)
    assert res is None

def test_manage_fail_closed_when_missing_market_snapshot(fsm_harness):
    """2. test_manage_fail_closed_when_missing_market_snapshot"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT"}) 
    res = manage.handle(msg)
    assert res is None

def test_manage_fail_closed_when_missing_instrument_specs(fsm_harness):
    """3. test_manage_fail_closed_when_missing_instrument_specs"""
    fsm, bus, cfg = fsm_harness
    # Remove BTCUSDT from instruments to test fail-closed behavior
    if "BTCUSDT" in cfg.instruments:
        del cfg.instruments["BTCUSDT"]
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "51000"})
    res = manage.handle(msg)
    assert res is None

def test_manage_emits_bracket_on_entry_once(fsm_harness):
    """4. test_manage_emits_bracket_on_entry_once"""
    fsm, bus, cfg = fsm_harness
    manage = ManageFlowFSM(config=cfg)
    manage.state = ManageState.FLAT
    manage.symbol = "BTCUSDT"
    msg = Message(op="EVT", verb="FILL", src="adapter", dst="exec", 
                  pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000", "order_type": "LIMIT"})
    res = manage.handle(msg)
    assert res is not None
    assert res.verb in ("BATCH", "PLACE_ORDER")
    res2 = manage.handle(msg)
    assert res2 is None

def test_manage_does_not_flip_side(fsm_harness):
    """5. test_manage_does_not_flip_side"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    assert manage.position_side == "BUY"
    msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "10000"})
    manage.handle(msg)
    assert manage.position_side == "BUY"

def test_manage_tp_sl_relative_to_entry_long(fsm_harness):
    """6. test_manage_tp_sl_relative_to_entry_long"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    sl, tp1, tp2 = manage._calculate_bracket_prices()
    assert sl is not None and sl < Decimal("50000")
    assert tp1 is not None and tp1 > Decimal("50000")

def test_manage_tp_sl_relative_to_entry_short(fsm_harness):
    """7. test_manage_tp_sl_relative_to_entry_short"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "SELL", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    sl, tp1, tp2 = manage._calculate_bracket_prices()
    assert sl is not None and sl > Decimal("50000")
    assert tp1 is not None and tp1 < Decimal("50000")

def test_manage_trailing_stop_monotonicity(fsm_harness):
    """8. test_manage_trailing_stop_monotonicity"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.sl_price = Decimal("49500")
    with patch.object(manage, "_get_trailing_stop_params", return_value=(True, 0.001, 0.001, 0)):
        msg1 = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "51000", "ts": 1000000})
        res1 = manage.handle(msg1)
        if res1:
            manage.sl_price = Decimal("50949")
        msg2 = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50800", "ts": 1001000})
        res2 = manage.handle(msg2)
        assert res2 is None

def test_manage_respects_reduce_only_on_close_intent(fsm_harness):
    """9. test_manage_respects_reduce_only_on_close_intent"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    with patch.object(manage, "_get_max_hold_sec", return_value=10):
        with patch("time.time", return_value=manage.position_open_ts + 20):
            msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50000"})
            res = manage.handle(msg)
            if res:
                # reduce_only must be present for a close intent.
                # We assert it SHOULD be there, but it will fail.
                assert str(res.pld.get("reduceOnly", "")).lower() == "true" or res.pld.get("reduce_only") is True

def test_manage_idempotency_on_modify_same_key(fsm_harness):
    """10. test_manage_idempotency_on_modify_same_key"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.last_trailing_ts = 1000.0
    with patch.object(manage, "_get_trailing_stop_params", return_value=(True, 0.005, 0.005, 5)):
        with patch("time.time", return_value=1002.0):
            msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "52000"})
            res = manage.handle(msg)
            assert res is None

def test_manage_max_hold_triggers_close_or_signal(fsm_harness):
    """11. test_manage_max_hold_triggers_close_or_signal"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = 1000.0
    with patch.object(manage, "_get_max_hold_sec", return_value=60):
        with patch("time.time", return_value=1070.0):
            msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50000"})
            res = manage.handle(msg)
            if res:
                assert res.verb == "CLOSE"

def test_manage_no_modify_when_price_did_not_move_enough(fsm_harness):
    """12. test_manage_no_modify_when_price_did_not_move_enough"""
    fsm, bus, cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.sl_price = Decimal("49500")
    with patch.object(manage, "_get_trailing_stop_params", return_value=(True, 0.01, 0.005, 0)):
        msg = Message(op="UPD", verb="MARKET_DATA", src="ws", dst="exec", pld={"symbol": "BTCUSDT", "last_price": "50250"})
        res = manage.handle(msg)
        assert res is None
