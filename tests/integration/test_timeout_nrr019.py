"""Test order timeout NRR-019 integration."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog, OrderTimeoutType
from vfoundation.core.why_codes import WhyCode


class TestOrderTimeoutNRR019:
    """Test order timeout returns NRR-019."""

    @pytest.fixture
    def fsm_config(self):
        """Create FSM configuration."""
        return {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "order_timeout_seconds": 30,  # Example timeout
            "max_retries": 3,
            "execution": {
                "watchdog": {
                    "ack_ttl_ms": 8000,
                    "fill_ttl_ms": 30000,
                }
            }
        }

    def test_nrr_019_code_exists(self):
        """Test that NRR-019 code is defined."""
        assert hasattr(WhyCode, 'NRR_019_ORDER_TIMEOUT_EXPIRED')
        code = WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED
        assert code.value == "NRR-019"

    def test_watchdog_initialization(self, fsm_config):
        """Test that watchdog is properly initialized."""
        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        assert hasattr(fsm, 'watchdog')
        assert isinstance(fsm.watchdog, OrderTimeoutWatchdog)
        assert fsm.watchdog.ack_ttl_ms == 8000
        assert fsm.watchdog.fill_ttl_ms == 30000

    def test_watchdog_tracking_and_ack(self, fsm_config):
        """Test order tracking and ACK notification."""
        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        # Track an order
        fsm.watchdog.track_order_placed(
            order_id="test_order_123",
            client_order_id="client_123",
            symbol="BTCUSDT",
            corr_id="corr_123",
            rid="rid_123"
        )

        # Check it's being tracked
        assert "test_order_123" in fsm.watchdog.pending_orders
        assert len(fsm.watchdog.pending_orders) == 1

        # Send ACK
        fsm.watchdog.on_order_ack("test_order_123")

        # Check it's moved to acked orders
        assert "test_order_123" not in fsm.watchdog.pending_orders
        assert "test_order_123" in fsm.watchdog.acked_orders
        assert len(fsm.watchdog.acked_orders) == 1

    def test_watchdog_fill_notification(self, fsm_config):
        """Test order fill notification removes from tracking."""
        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        # Track and ACK an order
        fsm.watchdog.track_order_placed(
            order_id="test_order_456",
            client_order_id="client_456",
            symbol="BTCUSDT"
        )
        fsm.watchdog.on_order_ack("test_order_456")

        # Send fill
        fsm.watchdog.on_order_fill("test_order_456")

        # Check it's removed from tracking
        assert "test_order_456" not in fsm.watchdog.pending_orders
        assert "test_order_456" not in fsm.watchdog.acked_orders

    @pytest.mark.asyncio
    async def test_watchdog_timeout_detection(self, fsm_config, caplog):
        """Test that watchdog detects timeouts and calls callback."""
        import logging

        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        # Mock timeout callback
        timeout_called = []

        async def mock_timeout_callback(deadline):
            timeout_called.append(deadline)

        fsm.watchdog.on_timeout_callback = mock_timeout_callback

        # Track an order with very short timeout
        fsm.watchdog.ack_ttl_ms = 100  # 100ms timeout
        fsm.watchdog.track_order_placed(
            order_id="timeout_order_789",
            client_order_id="client_789",
            symbol="BTCUSDT",
            corr_id="corr_789",
            rid="rid_789"
        )

        # Wait for timeout
        await asyncio.sleep(0.2)

        # Manually trigger timeout check (since we can't wait for the loop)
        await fsm.watchdog._check_timeouts()

        # Check timeout was detected
        assert len(timeout_called) == 1
        deadline = timeout_called[0]
        assert deadline.order_id == "timeout_order_789"
        assert deadline.timeout_type == OrderTimeoutType.ACK_TIMEOUT

        # Check order was removed from tracking
        assert "timeout_order_789" not in fsm.watchdog.pending_orders

    def test_watchdog_metrics(self, fsm_config):
        """Test watchdog metrics reporting."""
        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        # Track some orders
        fsm.watchdog.track_order_placed("order1", "client1", "BTCUSDT")
        fsm.watchdog.track_order_placed("order2", "client2", "BTCUSDT")
        fsm.watchdog.on_order_ack("order1")

        metrics = fsm.watchdog.get_metrics()

        assert metrics["pending_orders_count"] == 1  # order2 still pending
        assert metrics["acked_orders_count"] == 1     # order1 acked
        assert metrics["total_timeouts"] == 0
        assert metrics["ack_ttl_ms"] == 8000
        assert metrics["fill_ttl_ms"] == 30000

    def test_watchdog_cancel_tracking(self, fsm_config):
        """Test that cancelled orders are removed from tracking."""
        fsm = ExecPosFSM(fsm_config, None, shadow_mode=True)

        # Track orders
        fsm.watchdog.track_order_placed("order1", "client1", "BTCUSDT")
        fsm.watchdog.track_order_placed("order2", "client2", "BTCUSDT")
        fsm.watchdog.on_order_ack("order1")

        # Cancel orders
        fsm.watchdog.on_order_cancel("order1")  # Acked order
        fsm.watchdog.on_order_cancel("order2")  # Pending order

        # Check both removed
        assert "order1" not in fsm.watchdog.acked_orders
        assert "order2" not in fsm.watchdog.pending_orders

    def test_order_status_expired_exists(self):
        """Test that EXPIRED order status exists for timeout handling."""
        from apps.reference.domains.execution_position.contracts import OrderStatus

        assert hasattr(OrderStatus, 'EXPIRED')
        assert OrderStatus.EXPIRED == "EXPIRED"
