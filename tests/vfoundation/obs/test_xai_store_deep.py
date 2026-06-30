import pytest
from vfoundation.obs.xai_store import append_why, xai_store, XAIRecord

def test_record_xai_step_coverage():
    """Test append_why to cover missing lines in xai_store.py."""
    xai_store.clear()
    rid = "test_rid_123"
    verb = "DEC:OPEN"
    why = "Signal threshold exceeded"
    pld_summary = "symbol: BTC" # It expects string for payload_summary based on type hint in code
    meta = {"strategy": "aurora"}
    
    # 1. First step
    append_why(rid, verb, why, pld_summary, meta)
    
    # 2. Verify stored
    steps = xai_store.get(rid)
    assert len(steps) == 1
    assert steps[0].rid == rid
    assert steps[0].verb == verb
    assert steps[0].why == why[:80]
    
    # 3. Second step
    append_why(rid, "EVT:ORDER_PLACED", "Order sent to broker")
    steps = xai_store.get(rid)
    assert len(steps) == 2
    assert steps[1].step == 1
    
    # 4. Empty RID check
    append_why("", "X", "Y") # Should return early
    
def test_xai_store_clear():
    """Test clearing the store."""
    xai_store.clear()
    append_why("clear_me", "V", "W")
    assert len(xai_store.get("clear_me")) == 1
    xai_store.clear()
    assert len(xai_store.get("clear_me")) == 0
