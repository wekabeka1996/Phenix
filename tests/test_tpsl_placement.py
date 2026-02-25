"""
Unit tests for TP/SL bracket placement logic.

Tests verify that brackets are correctly placed after entry fills and
that OrderGuardian blocking logic works as expected.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.order_guardian import OrderGuardian


@pytest.fixture
def mock_adapter():
    """Create mock adapter for testing."""
    adapter = AsyncMock()
    adapter.get_open_positions = AsyncMock(return_value=[])
    adapter.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    return adapter


@pytest.fixture
def simple_store():
    """Create simple dict-based store for testing."""
    class SimpleStore:
        def __init__(self):
            self._data = {}
        def get(self, key):
            return self._data.get(key)
        def set(self, key, value):
            self._data[key] = value
        def put(self, key, value):
            self._data[key] = value
    return SimpleStore()


@pytest.fixture
def order_guardian(mock_adapter, simple_store):
    """Create OrderGuardian instance for testing."""
    return OrderGuardian(
        adapter=mock_adapter,
        clock=None,
        store=simple_store,
        poll_interval_ms=0,
        bus=None,
        config=None
    )


class TestShouldPlaceBrackets:
    """Test suite for should_place_brackets() method."""

    @pytest.mark.asyncio
    async def test_allows_brackets_when_no_entry_metadata(self, order_guardian):
        """Should allow bracket placement when no entry metadata exists."""
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_brackets_when_close_position_flag_set(self, order_guardian):
        """Should block bracket placement when entry has close_position=True."""
        # Store entry metadata with close_position flag
        order_guardian.store.set("order:entry123", {
            "symbol": "BTCUSDT",
            "close_position": True,
            "order_id": "entry123"
        })
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_allows_brackets_when_close_position_flag_false(self, order_guardian):
        """Should allow bracket placement when close_position=False."""
        # Store entry metadata without close_position flag
        order_guardian.store.set("order:entry123", {
            "symbol": "BTCUSDT",
            "close_position": False,
            "order_id": "entry123"
        })
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_allows_brackets_without_close_position_key(self, order_guardian):
        """Should allow bracket placement when close_position key doesn't exist."""
        # Store entry metadata without close_position key
        order_guardian.store.set("order:entry123", {
            "symbol": "BTCUSDT",
            "order_id": "entry123"
        })
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_allows_brackets_on_exception(self, order_guardian):
        """Should allow bracket placement if error occurs (fail-open behavior)."""
        # Make store.get() raise an exception
        order_guardian.store.get = MagicMock(side_effect=Exception("Store error"))
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_allows_brackets_without_adapter(self, simple_store):
        """Should allow bracket placement when adapter is None."""
        guardian = OrderGuardian(
            adapter=None,
            clock=None,
            store=simple_store,
            poll_interval_ms=0,
            bus=None,
            config=None
        )
        
        result = await guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is True


class TestTPSLPlacementFlow:
    """Integration tests for full TP/SL placement flow."""

    @pytest.mark.asyncio
    async def test_brackets_placed_after_entry_fill(self, order_guardian, mock_adapter):
        """
        Test that brackets are allowed after entry fill.
        
        This simulates the normal flow:
        1. Entry order is placed and filled
        2. Position exists (validated by _preflight_position_check upstream)
        3. should_place_brackets() is called
        4. Brackets should be allowed
        """
        # Simulate entry order registration
        order_guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="entry123",
            side="BUY",
            qty=0.001,
            corr_id="corr123",
            rid="rid123"
        )
        
        # Verify brackets are allowed (position check is upstream)
        result = await order_guardian.should_place_brackets("BTCUSDT", "12345")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_no_race_condition_with_rest_lag(self, order_guardian):
        """
        Test that brackets are allowed even if REST API has lag.
        
        FIX VERIFICATION: Previously, should_place_brackets() would check position
        and block if position_amt==0 due to REST lag. Now it doesn't check position,
        relying on upstream _preflight_position_check() which has retry logic.
        """
        # Simulate scenario where position hasn't propagated yet in REST API
        # (this would have blocked brackets before the fix)
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        # Should allow brackets - position check is upstream with retries
        assert result is True


class TestRegressionPrevention:
    """Tests to prevent regression of the fix."""

    @pytest.mark.asyncio
    async def test_close_position_flag_still_works(self, order_guardian):
        """Verify that close_position blocking logic still works after fix."""
        # This is the ONLY blocking condition that should remain
        order_guardian.store.set("order:entry123", {
            "close_position": True
        })
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "entry123")
        
        assert result is False, "close_position flag should still block brackets"

    @pytest.mark.asyncio 
    async def test_normal_entry_always_allowed(self, order_guardian):
        """Normal entry orders should always allow brackets."""
        # Register normal entry
        order_guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="entry123",
            side="BUY",
            qty=0.001,
            corr_id="corr123",
            rid="rid123"
        )
        
        result = await order_guardian.should_place_brackets("BTCUSDT", "12345")
        
        assert result is True
