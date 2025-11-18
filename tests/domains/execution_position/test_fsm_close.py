import pytest
import time
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState

@pytest.fixture
def fsm():
    return CloseFlowFSM(max_hold_sec=10.0)

def test_initialization(fsm):
    assert fsm.state == CloseState.FLAT
    assert fsm.max_hold_sec == 10.0
    assert fsm.position_active is False

def test_transition_to_opened(fsm):
    msg = Message(
        op="EVT", verb="TRADE_EXECUTED", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT", "qty": "1.0"}
    )
    res = fsm.handle(msg)
    assert res is None # No close decision yet
    assert fsm.state == CloseState.OPENED
    assert fsm.position_active is True
    assert fsm.position_open_ts > 0

def test_manual_close(fsm):
    # Setup active position
    fsm.state = CloseState.OPENED
    fsm.position_active = True
    fsm.position_open_ts = time.time()

    msg = Message(
        op="CMD", verb="CLOSE", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT"}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    assert res.pld["reduce_only"] is True
    assert res.pld["symbol"] == "BTCUSDT"
    assert res.pld["trigger"] == "CMD:CLOSE"
    assert fsm.state == CloseState.DONE
    assert fsm.position_active is False

def test_manual_close_ignored_if_flat(fsm):
    msg = Message(
        op="CMD", verb="CLOSE", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT"}
    )
    res = fsm.handle(msg)
    assert res is None

def test_max_hold_time_exceeded(fsm):
    fsm.state = CloseState.OPENED
    fsm.position_active = True
    fsm.position_open_ts = time.time() - 15.0 # 15s elapsed > 10s max

    msg = Message(
        op="UPD", verb="TICK", src="test", dst="test", rid="1", pld={}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    # Rule 1 (max_hold_time) triggers before Rule 3 (timer_check) because it's checked first
    assert res.pld["rule"] == "max_hold_time"
    assert fsm.state == CloseState.DONE

def test_emergency_close_rejected(fsm):
    fsm.state = CloseState.OPENED
    fsm.position_active = True
    fsm.position_open_ts = time.time() # Prevent max_hold trigger

    msg = Message(
        op="EVT", verb="REJECTED", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT"}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    assert res.pld["trigger"] == "REJECTED"

def test_emergency_close_expired(fsm):
    fsm.state = CloseState.OPENED
    fsm.position_active = True
    fsm.position_open_ts = time.time() # Prevent max_hold trigger

    msg = Message(
        op="EVT", verb="EXPIRED", src="test", dst="test", rid="1",
        pld={"symbol": "BTCUSDT"}
    )
    res = fsm.handle(msg)
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    assert res.pld["trigger"] == "EXPIRED"

def test_hydrate(fsm):
    ts = time.time() - 5.0
    fsm.hydrate({"open_ts": ts})
    assert fsm.state == CloseState.OPENED
    assert fsm.position_active is True
    assert fsm.position_open_ts == ts

def test_hydrate_error(fsm):
    fsm.hydrate(None) # Should raise exception internally
    assert fsm.state == CloseState.ERROR
    metrics = fsm.get_metrics()
    assert metrics["fsm_errors_total"] > 0

def test_ignore_irrelevant_messages(fsm):
    fsm.state = CloseState.OPENED
    fsm.position_active = True
    fsm.position_open_ts = time.time() # Prevent max_hold trigger

    # Use valid OP but irrelevant verb
    msg = Message(op="EVT", verb="IRRELEVANT", src="test", dst="test", pld={})
    res = fsm.handle(msg)
    assert res is None

def test_reset(fsm):
    fsm.state = CloseState.DONE
    fsm.position_active = False
    fsm.reset()
    assert fsm.state == CloseState.FLAT
    assert fsm.position_active is False
