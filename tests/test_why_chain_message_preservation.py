#!/usr/bin/env python3
"""
Test WHY chain preservation end-to-end.
"""

from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


def test_why_chain_preservation():
    """Test that WHY chain is preserved through Message creation."""
    # Create FSMCore
    fsm = FSMCore()

    # Test data
    why_chain = ["signal_calculation", "risk_approved", "position_sizing"]

    # Create message with data_ref
    # Payload updated to satisfy trade_intent_v1.json schema
    valid_pld = {
        "instrument": "BTCUSDT", 
        "side": "BUY", 
        "quantity_delta": "0.001",
        "strategy_id": "test_strat",
        "rid": "r1"
    }
    
    msg = Message(
        op="EVT",
        verb="MOCK_TEST_EVENT",
        src="decision_making",
        dst="execution_position",
        pld=valid_pld,
        why="trade_intent",
        data_ref=why_chain
    )

    # Verify data_ref is preserved
    assert msg.data_ref == why_chain, f"Expected {why_chain}, got {msg.data_ref}"

    # Test FSM emit with data_ref
    events_received = []

    def event_handler(event):
        events_received.append(event)

    fsm.listen("EVT:MOCK_TEST_EVENT", event_handler)

    # Emit event with data_ref
    fsm.emit(
        "EVT:MOCK_TEST_EVENT",
        payload=valid_pld,
        why="trade_intent",
        data_ref=why_chain
    )

    # Verify event received with data_ref
    assert len(events_received) == 1
    event = events_received[0]
    assert event.data_ref == why_chain, f"Expected {why_chain}, got {event.data_ref}"
