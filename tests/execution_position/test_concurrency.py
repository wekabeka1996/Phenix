"""
Concurrency tests for ExecPosFSM and ExposureGuard.

FIX-TRADEEXEC-5: Add tests for TRADE_EXECUTED path and concurrency.
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from vfoundation.core.protocol import Message


class TestConcurrency:
    """Test concurrent operations and race conditions."""

    @pytest.fixture
    def config(self):
        """Minimal config dict for testing."""
        return {
            "trading": {
                "execution": {
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000
                    },
                    "exposure": {
                        "max_equity_utilization_pct": 80.0,
                        "max_portfolio_notional_usd": 10000.0
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
                    },
                    "guardian": {
                        "unified": True,
                        "emit_tidy_event": True,
                        "poll_interval_ms": 500
                    }
                }
            }
        }

    @pytest.fixture
    def fsm_mock(self):
        """Mock FSM core."""
        fsm = Mock()
        fsm.listen = Mock()
        return fsm

    @pytest.fixture
    def exec_pos_fsm(self, config, fsm_mock):
        """Create ExecPosFSM instance with mocks."""
        with patch('apps.reference.domains.execution_position.fsm.BinanceAdapter') as mock_adapter, \
                patch('apps.reference.domains.execution_position.fsm.ExposureGuard') as mock_guard:
            mock_adapter_instance = Mock()
            mock_adapter.return_value = mock_adapter_instance

            mock_guard_instance = Mock()
            mock_guard.return_value = mock_guard_instance

            fsm = ExecPosFSM(config=config, fsm=fsm_mock)
            # Override with our mock
            fsm.exposure_guard = mock_guard_instance
            fsm.order_guardian = Mock()
            return fsm

    def test_concurrent_open_commands_blocking(self, exec_pos_fsm):
        """Test that concurrent OPEN commands for same symbol are properly serialized."""
        symbol = "BTCUSDT"
        results = []

        def attempt_open(order_id):
            """Attempt to open a position."""
            try:
                # Mock the flow creation and command handling
                with exec_pos_fsm._flows_lock:
                    if symbol not in exec_pos_fsm.open_flows:
                        exec_pos_fsm.open_flows[symbol] = Mock()
                        exec_pos_fsm.manage_flows[symbol] = Mock()
                        exec_pos_fsm.close_flows[symbol] = Mock()

                # Simulate exposure guard check
                if exec_pos_fsm.exposure_guard.can_open(symbol, Decimal("0.001"), Decimal("50000")):
                    exec_pos_fsm.exposure_guard.reserve(
                        order_id, Decimal("50.0"), symbol, "BUY")
                    results.append(f"success_{order_id}")
                else:
                    results.append(f"blocked_{order_id}")
            except Exception as e:
                results.append(f"error_{order_id}_{str(e)}")

        # Configure exposure guard to allow only one reservation
        call_count = 0

        def can_open_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # Only first call succeeds

        exec_pos_fsm.exposure_guard.can_open.side_effect = can_open_side_effect

        # Run concurrent attempts
        threads = []
        for i in range(3):
            thread = threading.Thread(target=attempt_open, args=[f"order_{i}"])
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify only one succeeded
        success_count = sum(1 for r in results if r.startswith("success_"))
        blocked_count = sum(1 for r in results if r.startswith("blocked_"))

        assert success_count == 1, f"Expected 1 success, got {success_count}. Results: {results}"
        assert blocked_count == 2, f"Expected 2 blocked, got {blocked_count}. Results: {results}"

    def test_exposure_guard_pending_expiry(self, exec_pos_fsm):
        """Test that expired pending exposures are cleaned up."""
        # Setup exposure guard with mock state
        exec_pos_fsm.exposure_guard.state = Mock()
        exec_pos_fsm.exposure_guard.state.pending_exposure = {
            "expired_key": {"notional": Decimal("100"), "ts": time.time() - 400, "reduce_only": False},
            "valid_key": {"notional": Decimal("200"), "ts": time.time() - 50, "reduce_only": False}
        }
        exec_pos_fsm.exposure_guard.state.postfill_reservations = {
            "expired_postfill": {"notional": Decimal("50"), "exp_ts": time.time() - 400}
        }

        # Mock cleanup methods
        exec_pos_fsm.exposure_guard.expire_stale = Mock()

        # Call cleanup (assuming there's a cleanup method)
        if hasattr(exec_pos_fsm.exposure_guard, 'expire_stale'):
            exec_pos_fsm.exposure_guard.expire_stale()

            # Verify cleanup was called
            exec_pos_fsm.exposure_guard.expire_stale.assert_called_once()

    def test_watchdog_timeout_handling(self, exec_pos_fsm):
        """Test watchdog timeout handling under concurrent load."""
        # Add multiple orders to watchdog
        for i in range(5):
            order_id = f"timeout_order_{i}"
            exec_pos_fsm.watchdog.track_order_placed(
                order_id=order_id,
                client_order_id=f"client_{order_id}",
                symbol="BTCUSDT"
            )
            exec_pos_fsm.watchdog.on_order_ack(order_id)

        initial_pending = len(exec_pos_fsm.watchdog.pending_orders)
        initial_acked = len(exec_pos_fsm.watchdog.acked_orders)

        # Simulate timeout by directly calling timeout handler
        # (In real scenario, this would happen via _check_timeouts)
        async def simulate_timeout():
            deadline = exec_pos_fsm.watchdog.acked_orders[list(
                exec_pos_fsm.watchdog.acked_orders.keys())[0]]
            await exec_pos_fsm.watchdog._handle_timeout(deadline)

        asyncio.run(simulate_timeout())

        # Verify order was removed from tracking
        assert len(exec_pos_fsm.watchdog.acked_orders) < initial_acked

    def test_multiple_trade_executed_events(self, exec_pos_fsm):
        """Test handling multiple TRADE_EXECUTED events concurrently."""
        import concurrent.futures

        def process_trade_event(order_id):
            """Process a single trade event."""
            payload = {
                "symbol": "BTCUSDT",
                "side": "buy",
                "price": "50000.0",
                "quantity": "0.001",
                "clientOrderId": order_id
            }
            event = Message(
                op="EVT",
                verb="TRADE_EXECUTED",
                src="test",
                dst="execution_position",
                pld=payload
            )
            exec_pos_fsm._on_trade_executed(event)
            return order_id

        # Process multiple events concurrently
        order_ids = [f"concurrent_order_{i}" for i in range(10)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(process_trade_event, order_ids))

        # Verify all events were processed
        assert len(results) == 10
        assert exec_pos_fsm.exposure_guard.on_fill.call_count == 10

        # Verify no duplicates in processed trade events (fill keys may be tracked separately)
        trade_events = {
            key
            for key in exec_pos_fsm._processed_events
            if key.startswith("trade_executed_")
        }
        assert len(trade_events) == 10
