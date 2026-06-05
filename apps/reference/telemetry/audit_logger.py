"""
JSONL Audit Logger for Aurora events.

Provides structured JSONL logging for order lifecycle and other audit events.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional


class AuroraEventLogger:
    """
    JSONL logger for Aurora audit events.

    Writes structured JSON events to logs/aurora_events.jsonl with rotation support.
    """

    def __init__(
        self, log_dir: str = "logs", filename: str = "aurora_events.jsonl", max_size_mb: int = 100
    ):
        self.log_dir = Path(log_dir)
        self.filename = filename
        self.max_size_mb = max_size_mb
        self.current_file: Optional[Path] = None
        self.file_handle: Optional[object] = None

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

    def _get_current_file(self) -> Path:
        """Get current log file path, rotating if necessary."""
        if self.current_file and self.current_file.exists():
            size_mb = self.current_file.stat().st_size / (1024 * 1024)
            if size_mb >= self.max_size_mb:
                # Rotate file
                timestamp = int(os.path.getmtime(self.current_file))
                rotated_name = f"{self.filename}.{timestamp}"
                rotated_path = self.log_dir / rotated_name
                self.current_file.rename(rotated_path)
                self.current_file = None
                if self.file_handle:
                    self.file_handle.close()
                    self.file_handle = None

        if not self.current_file:
            self.current_file = self.log_dir / self.filename

        return self.current_file

    def _get_file_handle(self):
        """Get file handle for writing, opening if necessary."""
        if not self.file_handle:
            file_path = self._get_current_file()
            self.file_handle = open(file_path, "a", encoding="utf-8")
        return self.file_handle

    def log_event(self, event_type: str, **kwargs) -> None:
        """
        Log an audit event to JSONL file.

        Args:
            event_type: Type of event (e.g., "ORDER_STATE_CHANGED")
            **kwargs: Event data fields
        """
        try:
            event_data = {
                # fallback to process time
                "ts_ms": kwargs.get("ts_ms", int(time.time() * 1000)),
                "event": event_type,
                **kwargs,
            }

            # Remove None values for cleaner JSON
            event_data = {k: v for k, v in event_data.items() if v is not None}

            json_line = json.dumps(
                event_data, ensure_ascii=False, separators=(",", ":"))

            handle = self._get_file_handle()
            handle.write(json_line + "\n")
            handle.flush()  # Ensure immediate write

        except Exception as e:
            self.logger.error(f"Failed to log audit event {event_type}: {e}")

    def log_order_state_changed(
        self,
        rid: str,
        idempotent_key: Optional[str],
        clientOrderId: Optional[str],
        exchangeOrderId: Optional[str],
        symbol: str,
        status: str,
        qty: Optional[str] = None,
        filled_qty: Optional[str] = None,
        avg_fill_price: Optional[str] = None,
        why: str = "order_update",
        ts_ms: Optional[int] = None,
    ) -> None:
        """
        Log ORDER_STATE_CHANGED event.

        Args:
            rid: Request ID
            idempotent_key: Idempotency key
            clientOrderId: Client order ID
            exchangeOrderId: Exchange order ID
            symbol: Trading symbol
            status: Order status (NEW, PARTIALLY_FILLED, FILLED, etc.)
            qty: Order quantity
            filled_qty: Filled quantity
            avg_fill_price: Average fill price
            why: Reason for the event
            ts_ms: Timestamp in milliseconds
        """
        self.log_event(
            "ORDER_STATE_CHANGED",
            rid=rid,
            idempotent_key=idempotent_key,
            clientOrderId=clientOrderId,
            exchangeOrderId=exchangeOrderId,
            symbol=symbol,
            status=status,
            qty=qty,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            why=why,
            ts_ms=ts_ms,
        )

    def log_order_error(
        self,
        rid: str,
        idempotent_key: Optional[str],
        clientOrderId: Optional[str],
        exchangeOrderId: Optional[str],
        symbol: Optional[str],
        reason: str,
        reason_raw: Optional[str] = None,
        why: str = "order_error",
        ts_ms: Optional[int] = None,
    ) -> None:
        """
        Log order error event (e.g., ERR:OPEN).

        Args:
            rid: Request ID
            idempotent_key: Idempotency key
            clientOrderId: Client order ID
            exchangeOrderId: Exchange order ID
            symbol: Trading symbol
            reason: Normalized error reason (NRR code)
            reason_raw: Raw error message
            why: Reason for the event
            ts_ms: Timestamp in milliseconds
        """
        self.log_event(
            "ORDER_ERROR",
            rid=rid,
            idempotent_key=idempotent_key,
            clientOrderId=clientOrderId,
            exchangeOrderId=exchangeOrderId,
            symbol=symbol,
            reason=reason,
            reason_raw=reason_raw,
            why=why,
            ts_ms=ts_ms,
        )

    def close(self) -> None:
        """Close the log file handle."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None


# Global instance for application-wide use
audit_logger = AuroraEventLogger()
