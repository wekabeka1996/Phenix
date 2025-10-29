import time
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState


def test_hydrate_sets_opened():
    fsm = CloseFlowFSM()
    fsm.hydrate({"open_ts": time.time()})
    assert fsm.state == CloseState.OPENED
    assert fsm.position_active


def test_fill_triggers_close_when_max_hold_negative():
    # If max_hold_sec is negative, elapsed > max_hold_sec immediately
    fsm = CloseFlowFSM(max_hold_sec=-1)
    msg = Message(op="EVT", verb="FILL", src="t", dst="c", rid="r1", pld={"filled_qty": 1})
    dec = fsm.handle(msg)
    # Since fill opens and immediately triggers max_hold rule -> DEC CLOSE
    assert dec is not None and dec.op == "DEC" and dec.verb == "CLOSE"


def test_rejected_triggers_emergency_close():
    fsm = CloseFlowFSM()
    # hydrate to set opened state
    fsm.hydrate({"open_ts": time.time() - 1000})
    msg = Message(op="EVT", verb="REJECTED", src="t", dst="c", rid="r2", pld={})
    dec = fsm.handle(msg)
    assert dec is not None and dec.op == "DEC" and dec.verb == "CLOSE"
    assert dec.pld.get("trigger") == "REJECTED"


def test_upd_tick_triggers_close_if_elapsed_exceeds():
    fsm = CloseFlowFSM(max_hold_sec=1)
    fsm.position_active = True
    # set position_open_ts in the past
    fsm.position_open_ts = time.time() - 3600
    fsm.state = CloseState.OPENED
    msg = Message(op="UPD", verb="TICK", src="t", dst="c", rid="r3", pld={})
    dec = fsm.handle(msg)
    assert dec is not None and dec.op == "DEC"
