"""
PHASE 5: Metrics Aggregation
Collect and aggregate metrics from all phases: clipping, rejection, idempotent cancels, -2011 absorption.
Structured JSON event logging for monitoring and compliance.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class MetricEventType(Enum):
    """Metric event types for structured logging."""
    RISK_CLIP_ORDER = "risk.clip.order"
    RISK_REJECT_ORDER = "risk.reject.order"
    ORDER_CANCEL_IDEMPOTENT = "order.cancel.idempotent"
    ORDER_CANCEL_2011_ABSORBED = "order.cancel.2011_absorbed"


@dataclass
class ClipMetricEvent:
    """Clipping metric event."""
    event_type: MetricEventType
    timestamp: datetime
    symbol: str
    original_notional: Decimal
    clipped_notional: Decimal
    clip_amount: Decimal
    clip_reason: str
    rid: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_json_line(self) -> str:
        """Convert to JSON with clip details."""
        data = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "rid": self.rid,
            "clip": {
                "original_notional": float(self.original_notional),
                "clipped_notional": float(self.clipped_notional),
                "clip_amount": float(self.clip_amount),
                "clip_reason": self.clip_reason,
            },
            "details": self.details or {},
        }
        return json.dumps(data, default=str)


@dataclass
class RejectMetricEvent:
    """Order rejection metric event."""
    event_type: MetricEventType
    timestamp: datetime
    symbol: str
    reason: str
    notional: Decimal
    side: str
    rid: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_json_line(self) -> str:
        """Convert to JSON with reject details."""
        data = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "rid": self.rid,
            "reject": {
                "reason": self.reason,
                "notional": float(self.notional),
                "side": self.side,
            },
            "details": self.details or {},
        }
        return json.dumps(data, default=str)


@dataclass
class CancelMetricEvent:
    """Cancel operation metric event."""
    event_type: MetricEventType
    timestamp: datetime
    symbol: str
    order_id: str
    cancel_success: bool
    cancel_attempt: int
    error_code: Optional[int] = None
    is_idempotent_success: bool = False
    rid: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_json_line(self) -> str:
        """Convert to JSON with cancel details."""
        data = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "rid": self.rid,
            "cancel": {
                "order_id": self.order_id,
                "success": self.cancel_success,
                "attempt": self.cancel_attempt,
                "error_code": self.error_code,
                "is_idempotent_success": self.is_idempotent_success,
            },
            "details": self.details or {},
        }
        return json.dumps(data, default=str)


@dataclass
class MetricAggregator:
    """Aggregate metrics across session."""

    # Counters
    clip_count: int = 0
    clip_notional_total: Decimal = Decimal("0")
    reject_count: int = 0
    cancel_idempotent_ok: int = 0
    cancel_2011_absorbed: int = 0

    # Time aggregates
    clip_min_amount: Optional[Decimal] = None
    clip_max_amount: Optional[Decimal] = None
    clip_avg_amount: Optional[Decimal] = None

    # Event log
    events: list = None

    def __post_init__(self):
        if self.events is None:
            self.events = []

    def record_clip(self, event: ClipMetricEvent) -> None:
        """Record clipping event."""
        self.clip_count += 1
        self.clip_notional_total += event.clip_amount

        if self.clip_min_amount is None:
            self.clip_min_amount = event.clip_amount
        else:
            self.clip_min_amount = min(self.clip_min_amount, event.clip_amount)

        if self.clip_max_amount is None:
            self.clip_max_amount = event.clip_amount
        else:
            self.clip_max_amount = max(self.clip_max_amount, event.clip_amount)

        self.events.append(event)

    def record_reject(self, event: RejectMetricEvent) -> None:
        """Record rejection event."""
        self.reject_count += 1
        self.events.append(event)

    def record_cancel_idempotent_ok(self, event: CancelMetricEvent) -> None:
        """Record successful idempotent cancel."""
        self.cancel_idempotent_ok += 1
        # Don't append here - let record_cancel_2011_absorbed handle it if needed

    def record_cancel_2011_absorbed(self, event: CancelMetricEvent) -> None:
        """Record -2011 absorbed as idempotent success."""
        self.cancel_2011_absorbed += 1
        # Append once (represents a single cancel event with -2011 absorption)
        self.events.append(event)

    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated metrics summary."""
        avg_clip = None
        if self.clip_count > 0:
            avg_clip = float(self.clip_notional_total / self.clip_count)

        return {
            "clip": {
                "count": self.clip_count,
                "notional_total": float(self.clip_notional_total),
                "min_amount": float(self.clip_min_amount) if self.clip_min_amount else None,
                "max_amount": float(self.clip_max_amount) if self.clip_max_amount else None,
                "avg_amount": avg_clip,
            },
            "reject": {
                "count": self.reject_count,
            },
            "cancel": {
                "idempotent_ok": self.cancel_idempotent_ok,
                "2011_absorbed": self.cancel_2011_absorbed,
            },
            "events_count": len(self.events),
        }

    def export_events_jsonl(self, filepath: str) -> None:
        """Export all events to JSONL file."""
        with open(filepath, "w") as f:
            for event in self.events:
                f.write(event.to_json_line() + "\n")
        logging.info(
            f"Exported {len(self.events)} metrics events to {filepath}")


class StructuredMetricsLogger:
    """Logger for structured metrics events."""

    def __init__(self, logger_name: str = "metrics"):
        self.logger = logging.getLogger(logger_name)
        self.aggregator = MetricAggregator()

    def log_clip_event(
        self,
        symbol: str,
        original_notional: Decimal,
        clipped_notional: Decimal,
        clip_reason: str,
        rid: Optional[str] = None,
    ) -> None:
        """Log clipping event."""
        clip_amount = original_notional - clipped_notional
        event = ClipMetricEvent(
            event_type=MetricEventType.RISK_CLIP_ORDER,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            rid=rid,
            original_notional=original_notional,
            clipped_notional=clipped_notional,
            clip_amount=clip_amount,
            clip_reason=clip_reason,
        )

        self.logger.info(event.to_json_line())
        self.aggregator.record_clip(event)

    def log_reject_event(
        self,
        symbol: str,
        reason: str,
        notional: Decimal,
        side: str,
        rid: Optional[str] = None,
    ) -> None:
        """Log rejection event."""
        event = RejectMetricEvent(
            event_type=MetricEventType.RISK_REJECT_ORDER,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            rid=rid,
            reason=reason,
            notional=notional,
            side=side,
        )

        self.logger.warning(event.to_json_line())
        self.aggregator.record_reject(event)

    def log_cancel_event(
        self,
        symbol: str,
        order_id: str,
        success: bool,
        error_code: Optional[int] = None,
        is_idempotent_success: bool = False,
        attempt: int = 1,
        rid: Optional[str] = None,
    ) -> None:
        """Log cancel event."""
        event_type = (
            MetricEventType.ORDER_CANCEL_2011_ABSORBED
            if error_code == -2011 and is_idempotent_success
            else MetricEventType.ORDER_CANCEL_IDEMPOTENT
        )

        event = CancelMetricEvent(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            rid=rid,
            order_id=order_id,
            cancel_success=success,
            error_code=error_code,
            is_idempotent_success=is_idempotent_success,
            cancel_attempt=attempt,
        )

        self.logger.info(event.to_json_line())

        # Record both: successful + -2011 absorbed (both count)
        if is_idempotent_success and error_code == -2011:
            self.aggregator.record_cancel_2011_absorbed(event)
            self.aggregator.record_cancel_idempotent_ok(
                event)  # Increment counter only
        elif success and is_idempotent_success:
            self.aggregator.record_cancel_idempotent_ok(
                event)  # Increment counter and append
            # Append the event
            self.aggregator.events.append(event)

    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated metrics summary."""
        return self.aggregator.get_summary()

    def export_metrics(self, filepath: str) -> None:
        """Export metrics to file."""
        self.aggregator.export_events_jsonl(filepath)


# Global instance
metrics_logger = StructuredMetricsLogger()
