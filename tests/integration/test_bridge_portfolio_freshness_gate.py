"""
Integration tests for Aurora Bridge portfolio freshness gate.

Tests the race condition fix where TRADE_INTENT_PROPOSED events are deferred
until portfolio data is fresh, preventing fail-closed exposure blocks.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock
from vfoundation.core.protocol import Message


class MockFSM:
    """Mock FSM for testing event emission."""

    def __init__(self):
        self.emitted = []

    def emit(self, msg: Message):
        """Record emitted messages."""
        self.emitted.append(msg)

    def listen(self, event_type: str, handler):
        """Mock listen method."""
        pass


@pytest.mark.asyncio
async def test_intent_deferred_until_portfolio_fresh():
    """Test that intents are deferred when portfolio is stale and processed when fresh."""
    from apps.reference.main import AuroraBridge

    # Create mock FSM and bridge
    fsm = MockFSM()
    config = {"position_tracking": {"positions_stale_ttl_sec": 5}}
    bridge = AuroraBridge(fsm=fsm, config=config, logger=None)

    # Create a trade intent
    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_123",
        pld={
            "instrument": "BTCUSDT",
            "side": "buy",
            "order": {"qty": "0.001", "price": "50000", "price_ref": "50000"},
            "idempotent_key": "test_key_123",
        },
        why="test_intent",
    )

    # Send intent when portfolio is stale (no portfolio data yet)
    await bridge.on_trade_intent_proposed(intent)

    # Should emit INTENT_DEFERRED, not CMD:OPEN
    emitted_verbs = [msg.verb for msg in fsm.emitted]
    assert "INTENT_DEFERRED" in emitted_verbs
    assert "OPEN" not in emitted_verbs

    # Verify deferred intent details
    defer_event = next(msg for msg in fsm.emitted if msg.verb == "INTENT_DEFERRED")
    assert defer_event.pld["reason"] == "PORTFOLIO_STALE"
    assert defer_event.pld["symbol"] == "BTCUSDT"
    assert defer_event.pld["idempotent_key"] == "test_key_123"

    # Clear emitted messages
    fsm.emitted.clear()

    # Now send fresh portfolio update
    portfolio_update = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="*",
        pld={
            "positions_last_ts_ms": int(time.time() * 1000),  # Current time = fresh
            "equity_free_usdt": "10000",
            "open_positions_usd": "1000",
        },
        why="portfolio_update",
    )

    await bridge.on_portfolio_state_updated(portfolio_update)

    # Should now emit CMD:OPEN for the deferred intent
    emitted_verbs = [msg.verb for msg in fsm.emitted]
    assert "OPEN" in emitted_verbs

    # Verify CMD:OPEN details
    open_cmd = next(msg for msg in fsm.emitted if msg.verb == "OPEN")
    assert open_cmd.op == "CMD"
    assert open_cmd.pld["symbol"] == "BTCUSDT"
    assert open_cmd.pld["side"] == "buy"
    assert open_cmd.pld["qty"] == "0.001"


@pytest.mark.asyncio
async def test_intent_processed_immediately_when_portfolio_fresh():
    """Test that intents are processed immediately when portfolio is already fresh."""
    from apps.reference.main import AuroraBridge

    # Create mock FSM and bridge
    fsm = MockFSM()
    config = {"position_tracking": {"positions_stale_ttl_sec": 5}}
    bridge = AuroraBridge(fsm=fsm, config=config, logger=None)

    # First send fresh portfolio update
    portfolio_update = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="*",
        pld={
            "positions_last_ts_ms": int(time.time() * 1000),  # Current time = fresh
            "equity_free_usdt": "10000",
            "open_positions_usd": "1000",
        },
        why="portfolio_update",
    )

    await bridge.on_portfolio_state_updated(portfolio_update)

    # Clear emitted messages
    fsm.emitted.clear()

    # Now send intent - should be processed immediately
    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_456",
        pld={
            "instrument": "ETHUSDT",
            "side": "sell",
            "order": {"qty": "0.1", "price": "3000", "price_ref": "3000"},
            "idempotent_key": "test_key_456",
        },
        why="test_intent",
    )

    await bridge.on_trade_intent_proposed(intent)

    # Should emit CMD:OPEN immediately, no INTENT_DEFERRED
    emitted_verbs = [msg.verb for msg in fsm.emitted]
    assert "OPEN" in emitted_verbs
    assert "INTENT_DEFERRED" not in emitted_verbs


@pytest.mark.asyncio
async def test_deferred_intent_timeout():
    """Test that deferred intents are dropped after max retries."""
    from apps.reference.main import AuroraBridge

    # Create mock FSM and bridge with short retry settings for testing
    fsm = MockFSM()
    config = {"position_tracking": {"positions_stale_ttl_sec": 5}}
    bridge = AuroraBridge(fsm=fsm, config=config, logger=None)
    bridge._max_retries = 1  # Reduce for testing
    bridge._retry_delay_sec = 0.01  # Very short delay

    # Send intent when portfolio is stale
    intent = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid="test_rid_timeout",
        pld={
            "instrument": "BTCUSDT",
            "side": "buy",
            "order": {"qty": "0.001", "price": "50000", "price_ref": "50000"},
            "idempotent_key": "test_key_timeout",
        },
        why="test_intent",
    )

    await bridge.on_trade_intent_proposed(intent)

    # Wait for retry timeout
    await asyncio.sleep(0.1)

    # Should emit INTENT_DROPPED
    emitted_verbs = [msg.verb for msg in fsm.emitted]
    assert "INTENT_DROPPED" in emitted_verbs

    # Verify drop event details
    drop_event = next(msg for msg in fsm.emitted if msg.verb == "INTENT_DROPPED")
    assert drop_event.pld["reason"] == "STALE_PORTFOLIO_TIMEOUT"
