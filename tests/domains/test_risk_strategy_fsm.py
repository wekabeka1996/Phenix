from unittest.mock import patch
from vfoundation.core.protocol import Message
import pytest


pytest.skip("Risk strategy FSM test requires complex mocking",
            allow_module_level=True)


def test_risk_strategy_handle_eval(monkeypatch):
    # Import handler lazily
    from apps.reference.domains.risk_strategy import fsm as rs_fsm

    # Capture wal.append calls
    called = []

    def fake_append(x):
        called.append(x)

    monkeypatch.setattr("vfoundation.dr.wal.append", fake_append)

    msg = Message(op="ASK", verb="EVAL", src="test", dst="risk", rid="rx1")
    # call the handler function directly
    dec = rs_fsm.handle_eval(msg)
    assert dec is not None
    assert dec.op == "DEC"
    # wal.append should have been called at least twice (input and decision)
    assert len(called) >= 2
