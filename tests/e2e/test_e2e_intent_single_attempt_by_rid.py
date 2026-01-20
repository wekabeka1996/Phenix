from __future__ import annotations

import time
from decimal import Decimal
import pytest
from vfoundation.core.protocol import Message

pytest_plugins = ("tests.domains.execution_position.conftest",)

def test_single_attempt_by_rid(fsm_harness):
    """
    Verify that submitting the same Intent (by RID/IdempotentKey) twice results in:
    1. First attempt: Success (DEC:OPEN)
    2. Second attempt: Rejection or Deduplication (no 2nd execution)
    """
    execpos_fsm, bus, _cfg = fsm_harness
    
    # Setup state
    portfolio_state = {
        "positions_last_ts_ms": 9999999999999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    execpos_fsm._latest_portfolio_state = dict(portfolio_state)
    execpos_fsm.exposure_guard.on_portfolio(dict(portfolio_state))

    intent_payload = {
        "rid": "RID-UNIQUE-123",
        "instrument": "BTCUSDT",
        "side": "BUY",
        "order": {
            "qty": "0.01",
            "price": "1000",
            "price_ref": "1000",
        },
        "idempotent_key": "KEY-UNIQUE-123",
        "valid_for_ms": 10000,
    }

    msg = Message(
        op="EVT", verb="TRADE_INTENT_PROPOSED",
        src="dm", dst="*",
        pld=intent_payload,
        why="test_dedup"
    )

    # 1. First Attempt
    execpos_fsm._on_trade_intent_proposed(msg)
    
    # Verify Success (DEC:OPEN)
    opens = [e for e in bus.events if e[0] == "DEC:OPEN"]
    assert len(opens) == 1, "First attempt should succeed"
    
    # 2. Second Attempt (Same Message)
    # Clear bus events to isolate 2nd attempt output
    bus.events = [] 
    
    execpos_fsm._on_trade_intent_proposed(msg)
    
    # Verify Behavior
    # It should NOT be DEC:OPEN again.
    # It might be nothing (Silent Dedup) or REJECTED.
    # Current implementation of ExecPosFSM.handle checks OrderGuardian.
    # If duplicate, checks usually return None/False.
    # _on_trade_intent_proposed emits REJECT if result is None.
    
    opens_2 = [e for e in bus.events if e[0] == "DEC:OPEN"]
    rejects_2 = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    
    assert len(opens_2) == 0, "Second attempt MUST NOT trigger Open again"
    
    # Check if rejected (No Black Hole)
    # Logic in _on_trade_intent_proposed: if result is None -> emit REJECT
    # OrderGuardian returns None on dup.
    assert len(rejects_2) == 1, "Second attempt must be explicitly rejected (dedup)"
    reason = rejects_2[0][1][0]["reason"]
    assert reason in ["IDEMPOTENCY_FAIL", "internal_error_no_result"], f"Unexpected rejection reason: {reason}"


def test_reduce_only_routing_and_rejection(fsm_harness):
    """
    Verify reduce_only=True routes to CLOSE and emits REJECT if fails.
    """
    execpos_fsm, bus, _cfg = fsm_harness

    msg = Message(
        op="EVT", verb="TRADE_INTENT_PROPOSED",
        src="dm", dst="*",
        pld={
            "rid": "RID-CLOSE-FAIL",
            "instrument": "BTCUSDT",
            "reduce_only": True,
            "idempotent_key": "KEY-CLOSE-FAIL",
        },
        why="test_close"
    )
    
    # 1. Trigger
    # Since we are in Shadow Mode and no position exists, Close might succeed (DEC:CLOSE) or Fail.
    # If CloseFlow checks position existence, it might fail.
    # But CloseFlow stub usually emits DEC:CLOSE blindly?
    # Let's see.
    execpos_fsm._on_trade_intent_proposed(msg)
    
    closes = [e for e in bus.events if e[0] == "DEC:CLOSE"]
    rejects = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    
    # Assert No Black Hole
    assert len(closes) + len(rejects) > 0, "Must emit Result or Reject"
    if closes:
        assert closes[0][1][0]["reduce_only"] is True

