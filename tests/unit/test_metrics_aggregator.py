"""
PHASE 5: Metrics Aggregator Tests
Tests for structured JSON logging and metrics aggregation.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from apps.reference.domains.execution_position.metrics_aggregator import (
    StructuredMetricsLogger,
    MetricEventType,
    ClipMetricEvent,
    RejectMetricEvent,
    CancelMetricEvent,
)


class TestMetricEventTypes:
    """Test metric event type enums."""

    def test_clip_event_type(self):
        """Test RISK_CLIP_ORDER event type."""
        assert MetricEventType.RISK_CLIP_ORDER.value == "risk.clip.order"

    def test_cancel_event_type(self):
        """Test ORDER_CANCEL_IDEMPOTENT event type."""
        assert MetricEventType.ORDER_CANCEL_IDEMPOTENT.value == "order.cancel.idempotent"

    def test_2011_event_type(self):
        """Test ORDER_CANCEL_2011_ABSORBED event type."""
        assert MetricEventType.ORDER_CANCEL_2011_ABSORBED.value == "order.cancel.2011_absorbed"


class TestClipMetricEvent:
    """Test clip metric events."""

    def test_create_clip_event(self):
        """Create clip metric event."""
        event = ClipMetricEvent(
            event_type=MetricEventType.RISK_CLIP_ORDER,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            original_notional=Decimal("1000"),
            clipped_notional=Decimal("800"),
            clip_amount=Decimal("200"),
            clip_reason="margin_exhaustion",
            rid="clip_001",
        )

        assert event.symbol == "BTCUSDT"
        assert event.original_notional == Decimal("1000")
        assert event.clip_amount == Decimal("200")

    def test_clip_event_json_line(self):
        """Test clip event JSON serialization."""
        event = ClipMetricEvent(
            event_type=MetricEventType.RISK_CLIP_ORDER,
            timestamp=datetime(2025, 11, 6, 12, 0, 0),
            symbol="ETHUSDT",
            original_notional=Decimal("500"),
            clipped_notional=Decimal("400"),
            clip_amount=Decimal("100"),
            clip_reason="max_risk",
            rid="clip_eth_001",
        )

        json_line = event.to_json_line()
        assert "risk.clip.order" in json_line
        assert "ETHUSDT" in json_line
        assert "margin_exhaustion" not in json_line  # Different reason


class TestRejectMetricEvent:
    """Test rejection metric events."""

    def test_create_reject_event(self):
        """Create rejection metric event."""
        event = RejectMetricEvent(
            event_type=MetricEventType.RISK_REJECT_ORDER,
            timestamp=datetime.utcnow(),
            symbol="BNBUSDT",
            reason="nrr_hard_limit",
            notional=Decimal("5000"),
            side="BUY",
            rid="reject_001",
        )

        assert event.reason == "nrr_hard_limit"
        assert event.notional == Decimal("5000")
        assert event.side == "BUY"

    def test_reject_event_json_line(self):
        """Test reject event JSON serialization."""
        event = RejectMetricEvent(
            event_type=MetricEventType.RISK_REJECT_ORDER,
            timestamp=datetime(2025, 11, 6, 12, 0, 0),
            symbol="ADAUSDT",
            reason="margin_zero",
            notional=Decimal("100"),
            side="SELL",
            rid="reject_ada_001",
        )

        json_line = event.to_json_line()
        assert "risk.reject.order" in json_line
        assert "ADAUSDT" in json_line
        assert "margin_zero" in json_line


class TestCancelMetricEvent:
    """Test cancel metric events."""

    def test_create_cancel_event(self):
        """Create cancel metric event."""
        event = CancelMetricEvent(
            event_type=MetricEventType.ORDER_CANCEL_IDEMPOTENT,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            order_id="123456",
            cancel_success=True,
            cancel_attempt=1,
            is_idempotent_success=True,
        )

        assert event.cancel_success is True
        assert event.cancel_attempt == 1
        assert event.is_idempotent_success is True

    def test_cancel_2011_event(self):
        """Create -2011 absorbed cancel event."""
        event = CancelMetricEvent(
            event_type=MetricEventType.ORDER_CANCEL_2011_ABSORBED,
            timestamp=datetime.utcnow(),
            symbol="ETHUSDT",
            order_id="654321",
            cancel_success=True,
            cancel_attempt=2,
            error_code=-2011,
            is_idempotent_success=True,
        )

        assert event.error_code == -2011
        assert event.is_idempotent_success is True

    def test_cancel_event_json_line(self):
        """Test cancel event JSON serialization."""
        event = CancelMetricEvent(
            event_type=MetricEventType.ORDER_CANCEL_IDEMPOTENT,
            timestamp=datetime(2025, 11, 6, 12, 0, 0),
            symbol="BTCUSDT",
            order_id="999999",
            cancel_success=True,
            cancel_attempt=1,
            rid="cancel_btc_999999",
        )

        json_line = event.to_json_line()
        assert "order.cancel.idempotent" in json_line
        assert "999999" in json_line
        assert "BTCUSDT" in json_line


class TestStructuredMetricsLogger:
    """Test structured metrics logger."""

    def test_logger_init(self):
        """Initialize metrics logger."""
        logger = StructuredMetricsLogger()

        assert logger.logger is not None
        assert logger.aggregator is not None
        summary = logger.get_summary()
        assert summary["clip"]["count"] == 0
        assert summary["reject"]["count"] == 0

    def test_log_clip_event(self):
        """Log clipping event."""
        logger = StructuredMetricsLogger()

        logger.log_clip_event(
            symbol="BTCUSDT",
            original_notional=Decimal("1000"),
            clipped_notional=Decimal("800"),
            clip_reason="margin_exhaustion",
            rid="clip_001",
        )

        summary = logger.get_summary()
        assert summary["clip"]["count"] == 1
        assert summary["clip"]["notional_total"] == 200.0

    def test_log_reject_event(self):
        """Log rejection event."""
        logger = StructuredMetricsLogger()

        logger.log_reject_event(
            symbol="ETHUSDT",
            reason="nrr_hard_limit",
            notional=Decimal("5000"),
            side="BUY",
            rid="reject_001",
        )

        summary = logger.get_summary()
        assert summary["reject"]["count"] == 1

    def test_log_cancel_event_success(self):
        """Log successful cancel event."""
        logger = StructuredMetricsLogger()

        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="123456",
            success=True,
            is_idempotent_success=True,
            rid="cancel_001",
        )

        summary = logger.get_summary()
        assert summary["cancel"]["idempotent_ok"] == 1

    def test_log_cancel_event_2011(self):
        """Log -2011 absorbed cancel event."""
        logger = StructuredMetricsLogger()

        logger.log_cancel_event(
            symbol="ETHUSDT",
            order_id="654321",
            success=True,
            error_code=-2011,
            is_idempotent_success=True,
            rid="cancel_2011_001",
        )

        summary = logger.get_summary()
        assert summary["cancel"]["2011_absorbed"] == 1
        # Also counts as success
        assert summary["cancel"]["idempotent_ok"] == 1

    def test_aggregator_summary(self):
        """Test aggregator summary."""
        logger = StructuredMetricsLogger()

        # Log multiple events
        logger.log_clip_event(
            symbol="BTCUSDT",
            original_notional=Decimal("1000"),
            clipped_notional=Decimal("900"),
            clip_reason="margin_exhaustion",
        )
        logger.log_clip_event(
            symbol="ETHUSDT",
            original_notional=Decimal("500"),
            clipped_notional=Decimal("450"),
            clip_reason="max_risk",
        )
        logger.log_reject_event(
            symbol="BNBUSDT",
            reason="margin_zero",
            notional=Decimal("200"),
            side="BUY",
        )

        summary = logger.get_summary()
        assert summary["clip"]["count"] == 2
        assert summary["clip"]["notional_total"] == 150.0
        assert summary["clip"]["min_amount"] == 50.0
        assert summary["clip"]["max_amount"] == 100.0
        assert summary["reject"]["count"] == 1
        assert summary["events_count"] == 3


class TestMetricsIntegration:
    """Integration tests for metrics logging."""

    def test_full_trading_session_metrics(self):
        """Simulate full trading session with clipping, rejection, and cancels."""
        logger = StructuredMetricsLogger()

        # Phase 1: Clipping events
        logger.log_clip_event(
            symbol="BTCUSDT",
            original_notional=Decimal("1000"),
            clipped_notional=Decimal("800"),
            clip_reason="margin_exhaustion",
        )

        # Phase 2: Rejection
        logger.log_reject_event(
            symbol="ETHUSDT",
            reason="nrr_hard_limit",
            notional=Decimal("5000"),
            side="BUY",
        )

        # Phase 3: Cancel success
        logger.log_cancel_event(
            symbol="BTCUSDT",
            order_id="123456",
            success=True,
            is_idempotent_success=True,
        )

        # Phase 4: -2011 absorbed
        logger.log_cancel_event(
            symbol="ETHUSDT",
            order_id="654321",
            success=True,
            error_code=-2011,
            is_idempotent_success=True,
        )

        summary = logger.get_summary()
        assert summary["clip"]["count"] == 1
        assert summary["reject"]["count"] == 1
        assert summary["cancel"]["idempotent_ok"] == 2  # 1 normal + 1 -2011
        assert summary["cancel"]["2011_absorbed"] == 1
        # Only 4 events logged (not 5 duplicates)
        assert summary["events_count"] == 4
