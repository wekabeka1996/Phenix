# tests/test_orchestrator_fsm.py
"""
Unit tests for OrchestratorFSM.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from apps.reference.orchestrator.orchestrator_fsm import OrchestratorFSM
from apps.reference.orchestrator.types import OrchestratorConfig, RIDLifecycle
from vfoundation.core.fsm_emit_compat import Message


@pytest.fixture
def config():
    """Test configuration."""
    return OrchestratorConfig(
        max_rid_ttl_seconds=3600,
        circuit_breaker_threshold=3,
        enable_signing=False  # Disable for tests
    )


@pytest.fixture
def orchestrator(config):
    """OrchestratorFSM instance."""
    orch = OrchestratorFSM(config)
    return orch


class TestOrchestratorFSM:

    @pytest.mark.asyncio
    async def test_initialization(self, orchestrator):
        """Test orchestrator initialization."""
        assert len(orchestrator._rid_states) == 0
        assert orchestrator.bus is not None

    @pytest.mark.asyncio
    async def test_trade_intent_proposed(self, orchestrator):
        """Test handling TRADE_INTENT_PROPOSED event."""
        # Create test event
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-123",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "TRADE_INTENT_PROPOSED",
                "rid": "test-rid-123",  # Add rid to payload
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": "0.001",
                "price": "50000",
                "why": ["High momentum", "Volume spike"],
                "idempotency_key": "unique-key-123"
            }
        )

        # Emit event (this will trigger the handler)
        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event.pld, "Test event", event.data_ref)

        # Give time for async processing
        await asyncio.sleep(0.1)

        # Verify state
        state = orchestrator._rid_states["test-rid-123"]
        assert state.lifecycle == RIDLifecycle.OPEN
        assert state.why_chain == ["High momentum", "Volume spike"]
        assert state.idempotency_key == "unique-key-123"

    @pytest.mark.asyncio
    async def test_order_executed(self, orchestrator):
        """Test handling ORDER_EXECUTED event."""
        # First create RID state
        event1 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-456",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "TRADE_INTENT_PROPOSED",
                "rid": "test-rid-456",
                "symbol": "ETHUSDT",
                "why": ["Test reason"]
            }
        )
        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event1.pld, "Test event", event1.data_ref)
        await asyncio.sleep(0.1)

        # Now test order executed
        event2 = Message(
            op="EVT",
            verb="ORDER_EXECUTED",
            rid="test-rid-456",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "ORDER_EXECUTED",
                "rid": "test-rid-456",
                "order_id": "12345",
                "why": ["Execution successful"]
            }
        )
        orchestrator.bus.emit("EVT:ORDER_EXECUTED",
                              event2.pld, "Test event", event2.data_ref)
        await asyncio.sleep(0.1)

        # Verify state update
        state = orchestrator._rid_states["test-rid-456"]
        assert state.lifecycle == RIDLifecycle.MONITOR
        assert "Execution successful" in state.why_chain

    @pytest.mark.asyncio
    async def test_position_closed(self, orchestrator):
        """Test handling POSITION_CLOSED event."""
        # Setup RID
        event1 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-789",
            src="test",
            dst="orchestrator",
            pld={"event_type": "TRADE_INTENT_PROPOSED",
                 "rid": "test-rid-789", "why": ["Initial"]}
        )
        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event1.pld, "Test event", event1.data_ref)
        await asyncio.sleep(0.1)

        # Close position
        event2 = Message(
            op="EVT",
            verb="POSITION_CLOSED",
            rid="test-rid-789",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "POSITION_CLOSED",
                "rid": "test-rid-789",
                "pnl": "10.5",
                "why": ["Target reached"]
            }
        )
        orchestrator.bus.emit("EVT:POSITION_CLOSED",
                              event2.pld, "Test event", event2.data_ref)
        await asyncio.sleep(0.1)

        # Verify final state
        state = orchestrator._rid_states["test-rid-789"]
        assert state.lifecycle == RIDLifecycle.CLOSED
        assert "Target reached" in state.why_chain

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, orchestrator):
        """Test circuit breaker functionality."""
        # Manually trigger errors to activate circuit breaker
        for i in range(3):
            orchestrator._record_error("trading", f"Test error {i}")

        # Check circuit breaker active
        assert orchestrator._is_circuit_breaker_active("trading")

        # Test rejection of new trade - circuit breaker should prevent processing
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-breaker",
            src="test",
            dst="orchestrator",
            pld={"event_type": "TRADE_INTENT_PROPOSED",
                 "rid": "test-rid-breaker", "why": ["Test"]}
        )

        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event.pld, "Test event", event.data_ref)
        await asyncio.sleep(0.1)

        # Should not create RID state due to circuit breaker
        assert "test-rid-breaker" not in orchestrator._rid_states

    @pytest.mark.asyncio
    async def test_idempotency(self, orchestrator):
        """Test idempotency checks."""
        # First request
        event1 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-idem-1",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "TRADE_INTENT_PROPOSED",
                "rid": "test-rid-idem-1",
                "idempotency_key": "same-key",
                "why": ["First"]
            }
        )
        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event1.pld, "Test event", event1.data_ref)
        await asyncio.sleep(0.1)

        # Duplicate request
        event2 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            rid="test-rid-idem-2",
            src="test",
            dst="orchestrator",
            pld={
                "event_type": "TRADE_INTENT_PROPOSED",
                "rid": "test-rid-idem-2",
                "idempotency_key": "same-key",
                "why": ["Second"]
            }
        )
        orchestrator.bus.emit("EVT:TRADE_INTENT_PROPOSED",
                              event2.pld, "Test event", event2.data_ref)
        await asyncio.sleep(0.1)

        # Check that only first request was processed
        assert "test-rid-idem-1" in orchestrator._rid_states
        # Second should not create new state due to duplicate key

    def test_get_rid_trace(self, orchestrator):
        """Test RID trace retrieval."""
        # Create state manually
        rid = "test-trace-rid"
        state = orchestrator._get_or_create_rid_state(rid)
        state.lifecycle = RIDLifecycle.MONITOR
        state.why_chain = ["Reason 1", "Reason 2"]

        # Get trace
        trace = orchestrator.get_rid_trace(rid)
        assert trace is not None
        assert trace["rid"] == rid
        assert trace["lifecycle"] == "MONITOR"
        assert trace["why_chain"] == ["Reason 1", "Reason 2"]

    def test_get_stats(self, orchestrator):
        """Test statistics retrieval."""
        stats = orchestrator.get_stats()
        assert "active_rids" in stats
        assert "error_counts" in stats
        assert "circuit_breaker_domains" in stats
