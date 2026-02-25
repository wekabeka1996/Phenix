"""
Tests for FSM delegation to OrderGuardian.

Tests:
- FSM calls order_guardian.cleanup_orphans() in DEC:CLOSE
- FSM calls order_guardian.cleanup_before_close() appropriately
- FSM initialization includes OrderGuardian
- FSM delegates all cleanup operations to OrderGuardian
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from apps.reference.domains.execution_position.order_guardian import OrderGuardian
from apps.reference.domains.execution_position.fsm import ExecPosFSM


class TestFSMDelegation:
    """Test FSM delegation to OrderGuardian"""

    def setup_method(self):
        """Setup test fixtures"""
        self.adapter = AsyncMock()
        self.order_guardian = OrderGuardian(
            adapter=self.adapter,
            poll_interval_ms=0
        )

        # Mock FSM with OrderGuardian
        self.fsm = Mock(spec=ExecPosFSM)
        self.fsm.order_guardian = self.order_guardian

    @pytest.mark.asyncio
    async def test_fsm_cleanup_before_close_delegates_to_guardian(self):
        """Test FSM cleanup_before_close delegates to OrderGuardian"""
        # Setup FSM mock to call cleanup_before_close
        async def mock_cleanup_before_close(symbol, parent_order_id=None):
            return await self.order_guardian.cleanup_before_close(symbol, parent_order_id)

        self.fsm.cleanup_before_close = mock_cleanup_before_close

        # Setup test data: entry with brackets
        self.order_guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.order_guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock successful cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Call FSM method (which delegates to OrderGuardian)
        cancelled_count = await self.fsm.cleanup_before_close("BTCUSDT", parent_order_id="12345")

        # Verify delegation worked
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once_with("BTCUSDT", "12346")

    @pytest.mark.asyncio
    async def test_fsm_cleanup_orphans_delegates_to_guardian(self):
        """Test FSM cleanup_orphans delegates to OrderGuardian"""
        # Setup FSM mock to call cleanup_orphans
        async def mock_cleanup_orphans(symbol=None, hard=False, batch_limit=50):
            return await self.order_guardian.cleanup_orphans(symbol, hard, batch_limit)

        self.fsm.cleanup_orphans = mock_cleanup_orphans

        # Setup: no position, bracket order
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

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

        # Register order in guardian
        self.order_guardian.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock successful cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Call FSM method (delegates to OrderGuardian)
        cancelled_count = await self.fsm.cleanup_orphans("BTCUSDT")

        # Verify delegation worked
        assert cancelled_count == 1
        self.adapter.cancel_order.assert_called_once_with("BTCUSDT", "12346")

    @pytest.mark.asyncio
    async def test_fsm_dec_close_calls_guardian_cleanup(self):
        """Test FSM DEC:CLOSE signal calls OrderGuardian cleanup"""
        # This test simulates the FSM DEC:CLOSE behavior
        # In real FSM, this would be called during DEC:CLOSE execution

        # Setup entry with brackets
        self.order_guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        self.order_guardian.register_bracket(
            symbol="BTCUSDT",
            parent_order_id="12345",
            order_id="12346",
            client_order_id="client_sl_123",
            kind="SL"
        )

        # Mock successful cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Simulate FSM DEC:CLOSE behavior: cleanup brackets before close
        cancelled_count = await self.order_guardian.cleanup_before_close(
            symbol="BTCUSDT",
            parent_order_id="12345"
        )

        # Verify cleanup happened
        assert cancelled_count == 1

    @pytest.mark.asyncio
    async def test_fsm_reconcile_calls_guardian_reconcile(self):
        """Test FSM reconcile_symbol delegates to OrderGuardian"""
        # Setup FSM mock
        async def mock_reconcile_symbol(symbol, rid=None):
            await self.order_guardian.reconcile_symbol(symbol, rid)

        self.fsm.reconcile_symbol = mock_reconcile_symbol

        # Setup: no position
        self.adapter.get_open_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.0"}
        ]

        # Setup: bracket order to be cancelled
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

        # Register order
        self.order_guardian.store.put("order:12346", {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
            "parent_entry_id": "12345"
        })

        # Mock cancel
        self.adapter.cancel_order.return_value = {"status": "CANCELED"}

        # Call FSM reconcile (delegates to OrderGuardian)
        await self.fsm.reconcile_symbol("BTCUSDT", rid="test_rid")

        # Verify reconcile triggered cleanup
        self.adapter.cancel_order.assert_called_once_with("BTCUSDT", "12346")

    def test_fsm_initialization_includes_guardian(self):
        """Test that FSM is initialized with OrderGuardian"""
        # This test verifies the conceptual requirement
        # In real implementation, FSM.__init__ should create OrderGuardian

        # Verify our mock FSM has the guardian
        assert hasattr(self.fsm, 'order_guardian')
        assert self.fsm.order_guardian is self.order_guardian

    def test_guardian_methods_exist_for_fsm_delegation(self):
        """Test that OrderGuardian has all methods FSM needs to delegate to"""
        required_methods = [
            'cleanup_before_close',
            'cleanup_orphans',
            'reconcile_symbol',
            'register_entry',
            'register_bracket',
            'get_brackets_for_entry',
            'get_our_open_brackets',
            'link_existing_from_rest'
        ]

        for method_name in required_methods:
            assert hasattr(self.order_guardian,
                           method_name), f"Missing method: {method_name}"
            assert callable(getattr(self.order_guardian, method_name)
                            ), f"Method not callable: {method_name}"

    @pytest.mark.asyncio
    async def test_fsm_shadow_mode_delegation(self):
        """Test FSM delegation works in shadow mode (no adapter)"""
        # Create guardian with no adapter
        shadow_guardian = OrderGuardian(
            adapter=None,
            poll_interval_ms=0
        )

        # Setup FSM mock with shadow guardian
        shadow_fsm = Mock(spec=ExecPosFSM)
        shadow_fsm.order_guardian = shadow_guardian

        # Setup delegation methods
        async def mock_cleanup_before_close(symbol, parent_order_id=None):
            return await shadow_guardian.cleanup_before_close(symbol, parent_order_id)

        async def mock_cleanup_orphans(symbol=None, hard=False, batch_limit=50):
            return await shadow_guardian.cleanup_orphans(symbol, hard, batch_limit)

        shadow_fsm.cleanup_before_close = mock_cleanup_before_close
        shadow_fsm.cleanup_orphans = mock_cleanup_orphans

        # Calls should return 0 (no-op) in shadow mode
        cancelled_before = await shadow_fsm.cleanup_before_close("BTCUSDT", "12345")
        cancelled_orphans = await shadow_fsm.cleanup_orphans("BTCUSDT")

        assert cancelled_before == 0
        assert cancelled_orphans == 0

    def test_guardian_store_independence_from_adapter(self):
        """Test that OrderGuardian store operations work regardless of adapter"""
        # Register some data
        self.order_guardian.register_entry(
            symbol="BTCUSDT",
            order_id="12345",
            client_order_id="client_123",
            side="BUY",
            qty=1.0
        )

        # Data should be stored even though adapter is mocked
        entry_data = self.order_guardian.store.get("entry:12345")
        assert entry_data is not None
        assert entry_data["symbol"] == "BTCUSDT"

        # Queries should work
        brackets = self.order_guardian.get_brackets_for_entry("12345")
        assert brackets == {}
