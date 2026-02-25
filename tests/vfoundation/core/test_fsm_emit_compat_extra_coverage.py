"""Extra coverage for fsm_emit_compat.py including import fallback."""
import sys
import importlib
import pytest
from unittest.mock import MagicMock, patch

# Test the module import fallback
def test_message_class_fallback(monkeypatch):
    """Test the except Exception branch when protocol.Message fails to import."""
    import vfoundation.core.fsm_emit_compat as compat_mod
    
    # Hide the real module
    monkeypatch.setitem(sys.modules, "vfoundation.core.protocol", None)
    
    # Force reload
    importlib.reload(compat_mod)
    
    # Now compat_mod.Message should be the dummy class
    msg = compat_mod.Message(op="EVT", verb="OPEN", src="A", dst="B", rid="r", pld={"x": 1}, why="t")
    assert msg.op == "EVT"
    assert msg.verb == "OPEN"
    assert msg.src == "A"
    assert msg.dst == "B"
    assert msg.rid == "r"
    assert msg.pld == {"x": 1}
    assert msg.why == "t"
    
    msg2 = compat_mod.Message(op="ASK")
    assert msg2.pld == {}
    
    # Restore
    monkeypatch.delitem(sys.modules, "vfoundation.core.protocol")
    importlib.reload(compat_mod)

def test_get_exceptions():
    from vfoundation.core.fsm_emit_compat import _get
    
    class PydV1Fail:
        def dict(self): raise RuntimeError("dict fail")
        
    class PydV2Fail:
        def model_dump(self): raise ValueError("dump fail")
        
    assert _get(PydV1Fail(), "k", "fb") == "fb"
    assert _get(PydV2Fail(), "k", "fb") == "fb"


@pytest.mark.asyncio
async def test_emit_compat_injection_and_exceptions():
    from vfoundation.core.fsm_emit_compat import emit_compat, Message
    
    class FakeFsm:
        def emit(self, *args):
            raise Exception("general error")
            
    logger = MagicMock()
    msg = Message(op="EVT", verb="TEST", src="a", dst="b", rid="r1")
    
    # We want to hit the injection logic lines 84-98 and exception handlers
    msg.pld = ["not", "a", "dict"]  # Will trigger the except block in injecting verb
    
    await emit_compat(FakeFsm(), msg, logger=logger)
    assert logger.debug.call_count >= 1
    assert logger.exception.call_count >= 1

    
@pytest.mark.asyncio
async def test_emit_compat_injection_success():
    from vfoundation.core.fsm_emit_compat import emit_compat, Message
    
    call_args = []
    class FakeFsm:
        def emit(self, *args):
            if len(args) == 4:
                call_args.append(args)
                return
            raise TypeError("only 4 arg supported")
            
    # msg with missing metadata in pld
    msg = Message(op="EVT", verb="V", src="S", dst="D", rid="R")
    await emit_compat(FakeFsm(), msg)
    
    pld = call_args[0][2]
    assert pld["verb"] == "V"
    assert pld["src"] == "S"
    assert pld["dst"] == "D"
    assert pld["rid"] == "R"

@pytest.mark.asyncio
async def test_emit_compat_4arg_async():
    from vfoundation.core.fsm_emit_compat import emit_compat, Message
    
    class FakeFsm:
        async def emit(self, *args):
            if len(args) == 4:
                return "ok"
            raise TypeError("only 4 arg")
            
    msg = Message(op="EVT", verb="V", src="S", dst="D", rid="R")
    await emit_compat(FakeFsm(), msg)

@pytest.mark.asyncio
async def test_emit_compat_3arg_async():
    from vfoundation.core.fsm_emit_compat import emit_compat, Message
    
    class FakeFsm:
        async def emit(self, *args):
            if len(args) == 3:
                return "ok"
            raise TypeError("only 3 arg")
            
    msg = Message(op="EVT", verb="V", src="S", dst="D", rid="R")
    await emit_compat(FakeFsm(), msg)
