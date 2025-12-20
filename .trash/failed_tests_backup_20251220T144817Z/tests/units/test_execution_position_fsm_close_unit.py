import time

import pytest

from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState


class DummyMsg:
    def __init__(self, op="EVT", verb="TICK", pld=None):
        self.op = op
        self.verb = verb
        self.pld = pld or {}
        self.dst = "exec"
        self.rid = "rid"
        self.data_ref = []  # Add data_ref for compatibility


def test_fill_transitions_to_opened_state():
    f = CloseFlowFSM()
    # simulate incoming fill event which should open the FSM
    # Note: fsm_close.py expects "TRADE_EXECUTED" or "PARTIAL_FILL", not "FILL"
    msg = DummyMsg(op="EVT", verb="TRADE_EXECUTED", pld={"qty": "1"})
    dec = f.handle(msg)
    assert f.state == CloseState.OPENED
    assert f.position_active is True
    assert dec is None


def test_check_close_by_timer_triggers_emit():
    f = CloseFlowFSM(max_hold_sec=0.5)
    # Simulate an already-opened position long in the past
    f.position_active = True
    f.position_open_ts = time.time() - 2.0

    msg = DummyMsg(op="UPD", verb="TICK")
    dec = f._check_close_conditions(msg)
    assert dec is not None
    assert getattr(dec, "op", None) == "DEC"
    assert getattr(dec, "verb", None) == "CLOSE"
    assert dec.pld.get("reduce_only") is True


def test_handle_on_fill_transitions_to_opened_and_no_immediate_close():
    f = CloseFlowFSM(max_hold_sec=60.0)
    # Note: fsm_close.py expects "TRADE_EXECUTED" or "PARTIAL_FILL", not "FILL"
    msg = DummyMsg(op="EVT", verb="TRADE_EXECUTED", pld={"qty": "1"})
    dec = f.handle(msg)
    assert f.state == CloseState.OPENED
    assert f.position_active is True
    # Because hold time not exceeded, no DEC returned
    assert dec is None


def test_get_metrics_and_reset():
    f = CloseFlowFSM()
    metrics = f.get_metrics()
    assert isinstance(metrics, dict)
    f.position_active = True
    f.reset()
    assert f.state == CloseState.FLAT
    assert f.position_active is False
