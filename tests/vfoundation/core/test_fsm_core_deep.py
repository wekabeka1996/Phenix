import pytest
from unittest.mock import MagicMock
from vfoundation.core.fsm_core import FSMCore

def test_fsm_core_domain_registration():
    """Test domain registration in FSMCore."""
    fsm = FSMCore()
    d1 = MagicMock()
    fsm.register_domain("d1", d1)
    assert fsm.domains["d1"] == d1
    assert fsm.get_domain("d1") == d1

def test_fsm_core_emit_with_listener():
    """Test emitting an event with a listener."""
    fsm = FSMCore()
    received = []
    def callback(msg): received.append(msg)
    
    fsm.listen("EVT:TEST", callback)
    fsm.emit("EVT:TEST", {"data": 1}, "why")
    
    assert len(received) == 1
    assert received[0].verb == "TEST"
    assert received[0].pld == {"data": 1}

def test_fsm_core_remove_listener():
    """Test removing an event listener."""
    fsm = FSMCore()
    def callback(msg): pass
    fsm.listen("EVT:X", callback)
    assert len(fsm.listeners["EVT:X"]) == 1
    fsm.remove_listener("EVT:X", callback)
    assert "EVT:X" not in fsm.listeners
