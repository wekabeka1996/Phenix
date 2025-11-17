"""
Integration tests for REST polling fill detection.

FIX-TRADEEXEC-5: Add tests for TRADE_EXECUTED path and concurrency.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog
from vfoundation.core.protocol import Message
import time


class TestRestPollingIntegration:
    """Test REST polling fill detection and TRADE_EXECUTED emission."""

    @pytest.fixture
    def config(self):
        """Mock config object - use dict for easier access."""
        return {
            "trading": {
                "execution": {
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000
                    },
                    "manage": {
                        "orphan_monitor": {
                            "enabled": True,
                            "run_on_startup": True,
                            "periodic_interval_sec": 300,
                            "min_order_age_sec": 0,
                            "batch_cancel_limit": 50,
                            "rate_limit_per_min": 120
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def fsm_mock(self):
        """Mock FSM core with event emission."""
        fsm = Mock()
        fsm.listen = Mock()
        fsm.emit = AsyncMock()
        return fsm

    @pytest.fixture
    def exec_pos_fsm(self, config, fsm_mock):
        """Create ExecPosFSM instance with mocks."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter') as mock_adapter:
            mock_adapter_instance = Mock()
            mock_adapter.return_value = mock_adapter_instance

            fsm = ExecPosFSM(config=config, fsm=fsm_mock)
            # Mock exposure guard
            fsm.exposure_guard = Mock()
            fsm.exposure_guard.on_fill = Mock()
            fsm.order_guardian = Mock()
            fsm.order_guardian.on_fill = Mock()
            fsm.order_guardian.reconcile_symbol = AsyncMock()

            # Set up async loop
            loop = asyncio.new_event_loop()
            fsm._async_loop = loop
            fsm._submit_async = Mock()

            # Mock adapter for REST polling
            mock_order_response = {
                "status": "FILLED",
                "executedQty": "0.001",
                "price": "50000.0",
                "side": "BUY",
                "clientOrderId": "rest_fill_order_123"
            }
            mock_adapter_instance.get_order = AsyncMock(
                return_value=mock_order_response)

            # Set up watchdog emit_fn to call fsm.emit after watchdog is created
            fsm.watchdog.emit_fn = fsm.fsm.emit
            # Set up get_order_fn to use adapter
            fsm.watchdog.get_order_fn = mock_adapter_instance.get_order

            return fsm

    @pytest.mark.asyncio
    async def test_rest_polling_fill_detection(self, exec_pos_fsm):
        """Test that REST polling detects fills and emits TRADE_EXECUTED."""
        # Simulate order that needs polling
        order_id = "poll_order_123"
        symbol = "BTCUSDT"

        # Add order to watchdog polling metadata and acked_orders
        exec_pos_fsm.watchdog._poll_meta[order_id] = {
            'symbol': symbol,
            'attempts': 0,
            'backoff_ms': 1000,
            'next_poll_at': 0  # Poll immediately
        }
        # Add to acked_orders to make it tracked
        from apps.reference.domains.execution_position.watchdog import OrderDeadline, OrderTimeoutType
        deadline = OrderDeadline(
            order_id=order_id,
            client_order_id="client_" + order_id,
            symbol=symbol,
            deadline_ms=int(time.time() * 1000) + 30000,
            timeout_type=OrderTimeoutType.FILL_TIMEOUT,
            corr_id=None,
            rid=None
        )
        exec_pos_fsm.watchdog.acked_orders[order_id] = deadline

        # Run polling
        await exec_pos_fsm.watchdog._poll_order_statuses()

        # Verify TRADE_EXECUTED was emitted
        exec_pos_fsm.fsm.emit.assert_called()
        call_args = exec_pos_fsm.fsm.emit.call_args
        assert call_args[0][0] == "EVT:TRADE_EXECUTED"
        emitted_payload = call_args[0][1]

        # Verify payload contents
        assert emitted_payload["symbol"] == symbol
        assert emitted_payload["quantity"] == "0.001"
        assert emitted_payload["price"] == "50000.0"
        assert emitted_payload["clientOrderId"] == "rest_fill_order_123"

    @pytest.mark.asyncio
    async def test_rest_polling_metrics_increment(self, exec_pos_fsm):
        """Test that REST polling increments metrics correctly."""
        initial_polls = exec_pos_fsm.watchdog._rest_polls_total
        initial_fills = exec_pos_fsm.watchdog._rest_detected_fills_total

        # Simulate polling
        order_id = "metrics_order_123"
        exec_pos_fsm.watchdog._poll_meta[order_id] = {
            'symbol': 'BTCUSDT',
            'attempts': 0,
            'backoff_ms': 1000,
            'next_poll_at': 0
        }
        # Add to acked_orders to make it tracked
        from apps.reference.domains.execution_position.watchdog import OrderDeadline, OrderTimeoutType
        deadline = OrderDeadline(
            order_id=order_id,
            client_order_id="client_" + order_id,
            symbol='BTCUSDT',
            deadline_ms=int(time.time() * 1000) + 30000,
            timeout_type=OrderTimeoutType.FILL_TIMEOUT,
            corr_id=None,
            rid=None
        )
        exec_pos_fsm.watchdog.acked_orders[order_id] = deadline

        await exec_pos_fsm.watchdog._poll_order_statuses()

        # Verify metrics incremented
        assert exec_pos_fsm.watchdog._rest_polls_total > initial_polls
        assert exec_pos_fsm.watchdog._rest_detected_fills_total > initial_fills

    @pytest.mark.asyncio
    async def test_rps_throttling(self, exec_pos_fsm):
        """Test RPS throttling prevents excessive REST calls."""
        # Set low RPS limit for testing
        exec_pos_fsm.watchdog._rps_limit = 2

        # Make multiple rapid calls
        results = []
        for i in range(5):
            results.append(exec_pos_fsm.watchdog._check_rps_limit())

        # First 2 should be True, rest False
        assert results[:2] == [True, True]
        assert all(not r for r in results[2:])

        # Verify throttle hits incremented
        assert exec_pos_fsm.watchdog._rps_throttle_hits >= 3
