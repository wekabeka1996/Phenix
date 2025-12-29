"""
Tests for duplicate entry guard in ExecPosRuntimeV2.
RID: TESTNET-POLLING-BRACKETS-FIX

Tests the following guards:
1. ENTRY_BLOCKED_HAS_POSITION - block if already have position
2. ENTRY_BLOCKED_PENDING_ORDER - block if pending LIMIT order exists
"""
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.shadow_execpos.runtime import (
    ExecPosRuntimeV2,
    PositionState,
    POSITION_ZERO_TOLERANCE,
)
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from tests.domains.execution_position.shadow_execpos.fakes import FakeExecutionAdapter


def _minimal_config():
    """Minimal config for runtime."""
    return {
        "execution_position": {
            "executor_pool_enabled": False,
            "fill_timeout_sec": 10.0,
            "aggregated_oco": {
                "enabled": True,
                "sl_pct": 0.02,
                "tp_rr": 2.0,
            },
        },
    }


class TestEntryBlockedHasPosition:
    """Test ENTRY_BLOCKED_HAS_POSITION guard."""

    @pytest.mark.asyncio
    async def test_blocks_entry_when_position_exists(self):
        """Should block entry if position already exists for symbol."""
        adapter = FakeExecutionAdapter()
        runtime = ExecPosRuntimeV2(
            config=_minimal_config(), adapter=adapter, price_service=None)

        # Setup: Add existing position
        runtime._positions_by_symbol["BTCUSDT"] = PositionState(
            symbol="BTCUSDT",
            qty=0.1,  # Non-zero position
            avg_entry_price=50000.0,
        )

        # Act
        await runtime.handle(RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={
                "side": "BUY",
                "quantity": "0.05",
                "price": "51000",
                "order_type": "LIMIT",
            },
        ))

        # Assert: No orders placed
        assert len(adapter.placed_orders) == 0

    @pytest.mark.asyncio
    async def test_allows_entry_when_no_position(self):
        """Should allow entry if no position exists."""
        adapter = FakeExecutionAdapter()
        runtime = ExecPosRuntimeV2(
            config=_minimal_config(), adapter=adapter, price_service=None)

        # Setup: No position
        runtime._positions_by_symbol.clear()

        # Act
        await runtime.handle(RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={
                "side": "BUY",
                "quantity": "0.05",
                "price": "51000",
                "order_type": "LIMIT",
            },
        ))

        # Assert: Order should be placed
        assert len(adapter.placed_orders) >= 1

    @pytest.mark.asyncio
    async def test_allows_entry_when_position_is_flat(self):
        """Should allow entry if position qty is below tolerance (flat)."""
        adapter = FakeExecutionAdapter()
        runtime = ExecPosRuntimeV2(
            config=_minimal_config(), adapter=adapter, price_service=None)

        # Setup: Flat position (qty ~ 0)
        runtime._positions_by_symbol["BTCUSDT"] = PositionState(
            symbol="BTCUSDT",
            qty=POSITION_ZERO_TOLERANCE / 10,  # Below tolerance
            avg_entry_price=50000.0,
        )

        # Act
        await runtime.handle(RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={
                "side": "BUY",
                "quantity": "0.05",
                "price": "51000",
                "order_type": "LIMIT",
            },
        ))

        # Assert: Order should be placed (flat position doesn't block)
        assert len(adapter.placed_orders) >= 1


class TestEntryBlockedPendingOrder:
    """Test ENTRY_BLOCKED_PENDING_ORDER guard."""

    @pytest.mark.asyncio
    async def test_blocks_entry_when_pending_limit_exists_same_price(self):
        """Should block entry if pending LIMIT order exists with SAME price."""
        adapter = FakeExecutionAdapter()
        runtime = ExecPosRuntimeV2(
            config=_minimal_config(), adapter=adapter, price_service=None)

        # Setup: Add pending LIMIT order to index
        runtime.order_index.upsert_from_open(
            rid="test-rid",
            idempotent_key="test-key",
            clientOrderId="test-client-123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,
            quantity=0.1,
        )
        # Set status to NEW
        ref = runtime.order_index.get(clientOrderId="test-client-123")
        if ref:
            ref.status = "NEW"

        # Act: Try to place order with SAME price
        await runtime.handle(RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={
                "side": "BUY",
                "quantity": "0.05",
                "price": "50000",  # Same price
                "order_type": "LIMIT",
            },
        ))

        # Assert: No NEW orders placed (only the pre-existing one)
        new_orders = [o for o in adapter.placed_orders if o.get(
            "status") != "PRE_EXISTING"]
        assert len(new_orders) == 0

    @pytest.mark.asyncio
    async def test_allows_entry_when_pending_limit_exists_different_price(self):
        """Should allow entry if pending LIMIT order exists with DIFFERENT price."""
        adapter = FakeExecutionAdapter()
        runtime = ExecPosRuntimeV2(
            config=_minimal_config(), adapter=adapter, price_service=None)

        # Setup: Add pending LIMIT order to index
        runtime.order_index.upsert_from_open(
            rid="test-rid",
            idempotent_key="test-key",
            clientOrderId="test-client-123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            price=50000.0,  # Existing price
            quantity=0.1,
        )
        # Set status to NEW
        ref = runtime.order_index.get(clientOrderId="test-client-123")
        if ref:
            ref.status = "NEW"

        # Act: Try to place order with DIFFERENT price
        await runtime.handle(RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={
                "side": "BUY",
                "quantity": "0.05",
                "price": "51000",  # Different price
                "order_type": "LIMIT",
            },
        ))

        # Assert: New order should be placed (different price allowed)
        new_orders = [o for o in adapter.placed_orders if o.get(
            "status") != "PRE_EXISTING"]
        assert len(new_orders) >= 1
