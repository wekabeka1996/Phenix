"""
Tests for OrderGuardian cleanup_before_close with parent order ID.

Tests:
- cleanup_before_close with specific parent: cancels brackets for that entry
- cleanup_before_close without parent: cancels all brackets for symbol
- Successful cancel operations
- Failed cancel operations
- -2011 error handling (unknown order treated as success)
- No adapter scenario (shadow mode)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from apps.reference.domains.execution_position.guardian.order_guardian import OrderGuardian, InMemoryStore


class TestCleanupBeforeCloseByParent:
    """Test OrderGuardian cleanup_before_close functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.adapter = AsyncMock()
        self.store = InMemoryStore()
        self.guardian = OrderGuardian(
            adapter=self.adapter,
            store=self.store,
            poll_interval_ms=0
        )

    @pytest.mark.asyncio
    async def test_cleanup_before_close_specific_parent_with_brackets(self):
        """Test cleanup_before_close with specific parent that has brackets"""
        # Register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Register SL bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Register TP bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12347",
            client_order_id="client_tp_123",
            kind="TP"
        )

        # Mock successful cancels
        self.adapter.cancel_order.side_effect = [
            {"status": "CANCELED"},  # SL cancel
            {"status": "CANCELED"}   # TP cancel
        ]

        # Cleanup brackets for specific parent
        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify results
        assert cancelled_count == 2
        assert self.adapter.cancel_order.call_count == 2

        # Verify calls were made for correct order IDs
        calls = self.adapter.cancel_order.call_args_list
        order_ids_cancelled = [call[0][1]
                               for call in calls]  # Second arg is order_id
        assert "12346" in order_ids_cancelled  # SL
        assert "12347" in order_ids_cancelled  # TP

    @pytest.mark.asyncio
    async def test_cleanup_before_close_specific_parent_no_brackets(self):
        """Test cleanup_before_close with specific parent that has no brackets"""
        # Register entry without brackets
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Cleanup brackets for parent with no brackets
        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify no cancels attempted
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_before_close_nonexistent_parent(self):
        """Test cleanup_before_close with non-existent parent"""
        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="99999"
        )

        # Verify no cancels attempted
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_before_close_cancel_failure(self):
        """Test cleanup_before_close when cancel operations fail"""
        # Register entry with bracket
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock failed cancel
        self.adapter.cancel_order.return_value = {
            "status": "FAILED", "msg": "Cancel failed"}

        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify no successful cancels
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_before_close_2011_error_success(self):
        """Test cleanup_before_close treats -2011 (unknown order) as success"""
        # Register entry with bracket
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock -2011 error (unknown order)
        self.adapter.cancel_order.return_value = {
            "code": -2011,
            "msg": "Unknown order sent"
        }

        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify -2011 treated as success
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_before_close_unknown_order_msg_success(self):
        """Test cleanup_before_close treats 'Unknown order' message as success"""
        # Register entry with bracket
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock unknown order message
        self.adapter.cancel_order.return_value = {
            "status": "ERROR",
            "msg": "Unknown order sent"
        }

        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify unknown order message treated as success
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_before_close_no_adapter(self):
        """Test cleanup_before_close with no adapter (shadow mode)"""
        # Create guardian with no adapter
        guardian_no_adapter = OrderGuardian(
            adapter=None,
            store=self.store,
            poll_interval_ms=0
        )

        # Register entry with bracket
        guardian_no_adapter.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        guardian_no_adapter.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        cancelled_count = await guardian_no_adapter.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify no operations performed
        assert cancelled_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_before_close_exception_handling(self):
        """Test cleanup_before_close handles exceptions gracefully"""
        # Register entry with bracket
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock exception during cancel
        self.adapter.cancel_order.side_effect = Exception("Network error")

        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify exception handled, no successful cancels
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_called_once()
