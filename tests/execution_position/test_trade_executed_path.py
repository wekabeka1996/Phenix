"""
Tests for TRADE_EXECUTED event path in ExecPosFSM.

FIX-TRADEEXEC-5: Add tests for TRADE_EXECUTED path and concurrency.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard


class TestTradeExecutedPath:
    """Test _on_trade_executed method and idempotency."""

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
            fsm.order_guardian.on_fill = Mock()
            fsm.order_guardian.reconcile_symbol = AsyncMock()

            # Mock async loop
            fsm._async_loop = asyncio.new_event_loop()
            fsm._submit_async = Mock()

            return fsm

    def test_on_trade_executed_basic(self, exec_pos_fsm):
        """Test basic _on_trade_executed functionality."""
        # Create test event
        payload = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "50000.0",
            "quantity": "0.001",
            "clientOrderId": "test_order_123",
            "rid": "test_rid_123"
        }
        event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld=payload,
            rid="test_rid_123"
        )

        # Call the method
        exec_pos_fsm._on_trade_executed(event)

        # Verify exposure guard was called
        exec_pos_fsm.exposure_guard.on_fill.assert_called_once()
        call_args, call_kwargs = exec_pos_fsm.exposure_guard.on_fill.call_args
        assert call_args[0] == "test_order_123"  # idempotent_key
        assert isinstance(call_args[1], Decimal)  # notional_usd
        assert call_args[1] == Decimal("50.0")  # 50000 * 0.001
        assert call_kwargs["symbol"] == "BTCUSDT"  # symbol
        assert call_kwargs["side"] == "buy"  # side

        # Verify order guardian was called
        exec_pos_fsm.order_guardian.on_fill.assert_called_once_with(
            symbol="BTCUSDT",
            parent_order_id="test_order_123",
            filled_qty=0.001
        )

    def test_on_trade_executed_idempotent_key_fallback(self, exec_pos_fsm):
        """Test fallback to rid when clientOrderId is missing."""
        payload = {
            "symbol": "ETHUSDT",
            "side": "sell",
            "price": "3000.0",
            "quantity": "0.01",
            "rid": "fallback_rid"
        }
        event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld=payload,
            rid="fallback_rid"
        )

        exec_pos_fsm._on_trade_executed(event)

        # Verify exposure guard called with rid as key
        exec_pos_fsm.exposure_guard.on_fill.assert_called_once()
        call_args = exec_pos_fsm.exposure_guard.on_fill.call_args
        assert call_args[0][0] == "fallback_rid"

    def test_on_trade_executed_idempotency(self, exec_pos_fsm):
        """Test that duplicate events are ignored."""
        payload = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "50000.0",
            "quantity": "0.001",
            "clientOrderId": "dup_order",
            "rid": "dup_rid"
        }
        event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld=payload,
            rid="dup_rid"
        )

        # First call
        exec_pos_fsm._on_trade_executed(event)
        # Second call (duplicate)
        exec_pos_fsm._on_trade_executed(event)

        # Verify exposure guard called only once
        assert exec_pos_fsm.exposure_guard.on_fill.call_count == 1

    def test_on_trade_executed_missing_required_fields(self, exec_pos_fsm):
        """Test handling of events with missing required fields."""
        # Missing symbol
        payload = {
            "side": "buy",
            "price": "50000.0",
            "quantity": "0.001"
        }
        event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld=payload
        )

        with patch.object(exec_pos_fsm.logger, 'warning') as mock_log:
            exec_pos_fsm._on_trade_executed(event)
            mock_log.assert_called_with(
                "EVT:TRADE_EXECUTED missing required fields: symbol=None, quantity=0.001"
            )

        # Verify no calls to exposure guard
        exec_pos_fsm.exposure_guard.on_fill.assert_not_called()

    def test_on_trade_executed_invalid_price_quantity(self, exec_pos_fsm):
        """Test handling of invalid price/quantity that can't be converted to Decimal."""
        payload = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "invalid_price",
            "quantity": "0.001",
            "clientOrderId": "test_order"
        }
        event = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="test",
            dst="execution_position",
            pld=payload
        )

        exec_pos_fsm._on_trade_executed(event)

        # Verify exposure guard called with None notional (due to invalid price)
        exec_pos_fsm.exposure_guard.on_fill.assert_called_once()
        call_args = exec_pos_fsm.exposure_guard.on_fill.call_args
        assert call_args[0][1] is None  # notional_usd should be None
