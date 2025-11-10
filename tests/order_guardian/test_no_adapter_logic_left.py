"""
Tests for OrderGuardian shadow mode (no adapter) functionality.

Tests:
- All methods return early/no-op when adapter is None
- No exceptions thrown in shadow mode
- Store operations still work in shadow mode
- Registration and queries work without adapter
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from apps.reference.services.order_guardian import OrderGuardian, InMemoryStore


class TestNoAdapterLogicLeft:
    """Test OrderGuardian shadow mode (no adapter) functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.store = InMemoryStore()
        self.guardian = OrderGuardian(
            adapter=None,  # No adapter = shadow mode
            store=self.store,
            poll_interval_ms=0
        )

    def test_registration_works_without_adapter(self):
        """Test that registration methods work without adapter"""
        # Register entry
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Register bracket
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Verify data stored
        entry_data = self.store.get("entry:12345")
        assert entry_data is not None
        assert entry_data["symbol"] == "BTCUSDT"

        brackets = self.guardian.get_brackets_for_entry("12345")
        assert "sl" in brackets

    def test_queries_work_without_adapter(self):
        """Test that query methods work without adapter"""
        # Setup some data
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Queries should work
        brackets = self.guardian.get_brackets_for_entry("12345")
        assert brackets == {}

        # get_our_open_brackets is async, so we just verify it exists
        assert hasattr(self.guardian, 'get_our_open_brackets')
        assert callable(self.guardian.get_our_open_brackets)
        import asyncio
        assert asyncio.iscoroutinefunction(self.guardian.get_our_open_brackets)

        # link_existing_from_rest should not raise
        self.guardian.link_existing_from_rest("BTCUSDT")

    @pytest.mark.asyncio
    async def test_cleanup_before_close_noop_without_adapter(self):
        """Test cleanup_before_close returns 0 without adapter"""
        cancelled_count = await self.guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        assert cancelled_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphans_noop_without_adapter(self):
        """Test cleanup_orphans returns 0 without adapter"""
        cancelled_count = await self.guardian.cleanup_orphans(symbol="BTCUSDT")

        assert cancelled_count == 0

    @pytest.mark.asyncio
    async def test_reconcile_symbol_noop_without_adapter(self):
        """Test reconcile_symbol does nothing without adapter"""
        # Should not raise exception
        await self.guardian.reconcile_symbol("BTCUSDT", rid="test_rid")

    @pytest.mark.asyncio
    async def test_start_stop_work_without_adapter(self):
        """Test lifecycle methods work without adapter"""
        # Should not raise exceptions
        await self.guardian.start()
        await self.guardian.stop()

    def test_store_operations_work_without_adapter(self):
        """Test that store operations work independently of adapter"""
        # Put some data
        self.store.put("test_key", {"test": "data"})

        # Get it back
        data = self.store.get("test_key")
        assert data == {"test": "data"}

        # Delete it
        self.store.delete("test_key")
        data = self.store.get("test_key")
        assert data is None

    def test_initialization_without_adapter(self):
        """Test OrderGuardian initializes correctly without adapter"""
        assert self.guardian.adapter is None
        assert self.guardian.store is not None
        assert self.guardian.poll_interval_ms == 5000
        assert self.guardian._poller_task is None

    def test_logging_works_without_adapter(self):
        """Test that logging operations work without adapter"""
        # Register entry (triggers logging)
        self.guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Should not raise any logging-related exceptions
        # (We can't easily test log output without mocking log handlers)

    def test_bracket_registration_without_parent_no_crash(self):
        """Test registering bracket for non-existent parent doesn't crash"""
        self.guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="nonexistent",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Should not crash, bracket metadata should still be stored
        order_meta = self.store.get("order:12346")
        assert order_meta is not None
        assert order_meta["parent_entry_id"] == "nonexistent"

    def test_multiple_operations_without_adapter(self):
        """Test sequence of operations works without adapter"""
        # Register multiple entries and brackets
        for i in range(3):
            order_id = f"1234{i}"
            client_id = f"client_{i}"

            self.guardian.register_entry(
                symbol="BTCUSDT",
                order_id=order_id,
                client_order_id=client_id,
                side="BUY",
                qty=1.0
            )

            # Add brackets for each
            self.guardian.register_bracket(
                symbol="BTCUSDT",
                parent_order_id=order_id,
                order_id=f"999{i}",
                client_order_id=f"client_sl_{i}",
                kind="SL"
            )

        # Verify all data stored
        for i in range(3):
            entry_data = self.store.get(f"entry:1234{i}")
            assert entry_data is not None

            brackets = self.guardian.get_brackets_for_entry(f"1234{i}")
            assert "sl" in brackets

    @pytest.mark.asyncio
    async def test_async_methods_no_exceptions_without_adapter(self):
        """Test all async methods complete without exceptions when no adapter"""
        # All these should complete without raising exceptions
        await self.guardian.cleanup_before_close("BTCUSDT")
        await self.guardian.cleanup_orphans("BTCUSDT")
        await self.guardian.cleanup_orphans("BTCUSDT", hard=True)
        await self.guardian.reconcile_symbol("BTCUSDT")
        await self.guardian.start()
        await self.guardian.stop()
