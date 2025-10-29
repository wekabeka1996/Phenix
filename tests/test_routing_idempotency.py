from __future__ import annotations
from unittest.mock import patch
from vfoundation.core.routing import Router
from vfoundation.core.protocol import Message

def test_idempotent_route():
    r = Router()
    def handler(m: Message) -> Message:
        return Message(op="DEC", verb="EVAL", src="risk", dst="exec", rid=m.rid, why="ok")
    r.register("ASK","EVAL", handler)
    rid = "rid-1"
    msg = Message(op="ASK", verb="EVAL", src="risk", dst="exec", rid=rid)
    
    # Mock WAL append to avoid file system operations
    with patch('vfoundation.core.routing.wal_append'):
        a = r.route(msg)
        b = r.route(msg)
    assert a.model_dump() == b.model_dump()

def test_idempotent_key_route():
    """Test new idempotent_key based routing"""
    r = Router()
    def handler(m: Message) -> Message:
        return Message(op="DEC", verb="RESULT", src="processor", dst=m.src, rid=m.rid, why="processed")
    r.register("ASK", "PROCESS", handler)
    
    idem_key = "test-idem-key-123"
    
    # First message with idempotent_key
    msg1 = Message(
        op="ASK", 
        verb="PROCESS", 
        src="client", 
        dst="processor",
        rid="rid-1", 
        idempotent_key=idem_key
    )
    
    # Second message with same idempotent_key but different RID
    msg2 = Message(
        op="ASK",
        verb="PROCESS", 
        src="client",
        dst="processor",
        rid="rid-2",  # Different RID
        idempotent_key=idem_key  # Same idempotent_key
    )
    
    # Mock WAL append
    with patch('vfoundation.core.routing.wal_append'):
        result1 = r.route(msg1)
        result2 = r.route(msg2)
    
    # Results should be equivalent (from cache)
    assert result1.op == result2.op
    assert result1.verb == result2.verb
    assert result1.why == result2.why
    
    # Check for dedup marker in cached result
    if hasattr(result2, 'pld') and result2.pld:
        assert result2.pld.get("dedup")


def test_why_validation():
    """Test that router validates why field length"""
    r = Router()
    def handler(m: Message) -> Message:
        return Message(op="DEC", verb="OK", src="handler", dst=m.src, rid=m.rid)
    r.register("ASK", "TEST", handler)
    
    # Create message with why field too long, bypassing Pydantic validation
    long_why = "x" * 81
    
    # Create valid message first, then modify why field directly
    msg = Message(op="ASK", verb="TEST", src="client", dst="handler")
    msg.why = long_why  # Bypass validation
    
    with patch('vfoundation.core.routing.wal_append'):
        result = r.route(msg)
    
    assert result.op == "ERR"
    assert result.verb == "WHY_TOO_LONG"
