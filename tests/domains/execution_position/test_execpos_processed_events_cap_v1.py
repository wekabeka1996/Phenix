import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message

@pytest.mark.slow
def test_execpos_processed_events_unbounded_leak_risk(fsm_harness):
    """
    Step 4.3: Memory leak regression test.
    Checks for unbounded growth of _processed_events set.
    """
    fsm, bus, cfg = fsm_harness
    
    # Set a small cap for the test to ensure it passes quickly
    if hasattr(fsm, "_processed_events") and hasattr(fsm._processed_events, "max_size"):
        fsm._processed_events.max_size = 5000
    
    N = 10000 
    
    for i in range(N):
        msg = Message(
            op="EVT", verb="ORDER_ACK", 
            src="adapter", dst="exec",
            pld={"orderId": f"leak_{i}", "symbol": "BTCUSDT"}
        )
        fsm._on_order_ack(msg)
        
    # Check size
    size = len(fsm._processed_events)
    
    # If the size is exactly N, and there is no cap in code, this confirms leak risk.
    # The test purposefully reports if growth is unbounded.
    
    # Assuming code currently has NO cap (from view_file audit)
    if size >= N:
        # Intentionally highlight the risk if no cap detected
        # In a real "fix check" test, we'd assert size < N if a cap existed.
        pytest.fail(f"MEMORY LEAK RISK: _processed_events grew to {size} without capping. Unbounded growth detected.")
    else:
        # If it's capped, it should be smaller than N
        assert size < N
