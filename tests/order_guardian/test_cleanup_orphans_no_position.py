"""
Tests for OrderGuardian cleanup_orphans when no position exists.

Tests:
- cleanup_orphans cancels bracket orders when positionAmt == 0
- cleanup_orphans skips when position exists (unless hard=True)
- Batch limiting functionality
- -2011 error handling
- No adapter scenario
- Hard mode cancels regardless of position
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from apps.reference.services.order_guardian import OrderGuardian, InMemoryStore


class TestCleanupOrphansNoPosition:
    """Test OrderGuardian cleanup_orphans functionality when no position"""

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
    async def test_cleanup_orphans_no_position_cancels_brackets(self):
        """Test cleanup_orphans cancels bracket orders when no position"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: open bracket orders
        self.adapter.get_open_orders.return_value = [
            {
                "orderId": "12346",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "closePosition": True
            },
            {
                "orderId": "12347",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "TAKE_PROFIT_MARKET",
                "reduceOnly": True,
                "closePosition": True
            }
        ]

        # Register bracket orders in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })
        self.store.put("order:12347", {
            "symbol": "BTCUSDT",
            "type": "TAKE_PROFIT_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock successful cancels
        self.adapter.cancel_order.side_effect = [
            {"status": "CANCELED"},
            {"status": "CANCELED"}
        ]

        # Run cleanup
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify results
        assert cancelled_count == 2
        assert self.adapter.cancel_order.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_orphans_with_position_skips(self):
        """Test cleanup_orphans skips when position exists"""
        # Setup: position exists
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "1.0"}
        ]

        # Setup: open bracket orders (should not be cancelled)
        self.adapter.get_open_orders.return_value = [
            {
                "orderId": "12346",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "closePosition": True
            }
        ]

        # Register bracket order in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Run cleanup (not hard mode)
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify no cancels
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_orphans_hard_mode_cancels_anyway(self):
        """Test cleanup_orphans hard mode cancels regardless of position"""
        # Setup: position exists
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "1.0"}
        ]

        # Setup: open bracket orders
        self.adapter.get_open_orders.return_value = [
            {
                "orderId": "12346",
                "symbol": "BTCUSDT",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "closePosition": True
            }
        ]

        # Register bracket order in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock successful cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Run cleanup in hard mode
        cancelled_count = await self.guardian.cleanup_orphans(
            symbol="BTCUSDT",
            hard=True
        )

        # Verify cancel happened despite position
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_orphans_batch_limit(self):
        """Test cleanup_orphans respects batch_limit"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: multiple open bracket orders
        self.adapter.get_open_orders.return_value = [
            {"orderId": "12346", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True},
            {"orderId": "12347", "symbol": "BTCUSDT", "status": "NEW",
                "type": "TAKE_PROFIT_MARKET", "reduceOnly": True, "closePosition": True},
            {"orderId": "12348", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True},
        ]

        # Register all orders in store
        for order_id in ["12346", "12347", "12348"]:
            self.store.put(f"order:{order_id}", {
                "symbol": "BTCUSDT",
                "type": "STOP_MARKET",
                "reduce_only": True,
                "close_position": True,
                "parent_entry_id": "12345"
            })

        # Mock successful cancels
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Run cleanup with batch_limit=2
        cancelled_count = await self.guardian.cleanup_orphans(
            symbol="BTCUSDT",
            batch_limit=2
        )

        # Verify only 2 cancelled (batch limit)
        assert cancelled_count == 2
        assert self.adapter.cancel_order.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_orphans_ignores_non_bracket_orders(self):
        """Test cleanup_orphans ignores non-bracket orders"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: mix of bracket and non-bracket orders
        self.adapter.get_open_orders.return_value = [
            # Bracket order (should be cancelled)
            {"orderId": "12346", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True},
            # Non-bracket order (should be ignored)
            {"orderId": "12347", "symbol": "BTCUSDT", "status": "NEW",
                "type": "MARKET", "reduceOnly": False, "closePosition": False},
        ]

        # Register only bracket order in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })
        # Non-bracket order not in store

        # Mock successful cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Run cleanup
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify only bracket order cancelled
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once_with("BTCUSDT", "12346")

    @pytest.mark.asyncio
    async def test_cleanup_orphans_ignores_untracked_orders(self):
        """Test cleanup_orphans ignores orders not in our store"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: open orders that look like brackets but not in our store
        self.adapter.get_open_orders.return_value = [
            {"orderId": "99999", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True},
        ]

        # No orders in store

        # Run cleanup
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify no cancels (order not in our store)
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_orphans_2011_error_success(self):
        """Test cleanup_orphans treats -2011 as success"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: open bracket order
        self.adapter.get_open_orders.return_value = [
            {"orderId": "12346", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True}
        ]

        # Register order in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock -2011 error
        self.adapter.cancel_order.return_value = {
            "code": -2011,
            "msg": "Unknown order sent"
        }

        # Run cleanup
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify -2011 treated as success
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_orphans_no_adapter(self):
        """Test cleanup_orphans with no adapter (shadow mode)"""
        # Create guardian with no adapter
        guardian_no_adapter = OrderGuardian(
            adapter=None,
            store=self.store,
            poll_interval_ms=0
        )

        # Run cleanup
        cancelled_count = await guardian_no_adapter.cleanup_orphans(symbol="BTCUSDT")

        # Verify no operations
        assert cancelled_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphans_exception_handling(self):
        """Test cleanup_orphans handles exceptions gracefully"""
        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: open bracket order
        self.adapter.get_open_orders.return_value = [
            {"orderId": "12346", "symbol": "BTCUSDT", "status": "NEW",
                "type": "STOP_MARKET", "reduceOnly": True, "closePosition": True}
        ]

        # Register order in store
        self.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock exception
        self.adapter.cancel_order.side_effect = Exception("Network error")

        # Run cleanup
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        # Verify exception handled
        assert cancelled_count == 0
        self.adapter.cancel_order.assert_called_once()
