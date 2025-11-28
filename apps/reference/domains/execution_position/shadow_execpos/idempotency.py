"""
Idempotency Logic for Shadow ExecPos
====================================

Handles deduplication of fills to ensure safe processing.
"""
from typing import Any, Dict, Optional, Tuple, Union
import time
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)

class FillIdempotency:
    """
    Determines if a fill (TRADE_EXECUTED) should be processed.

    Tracks cumulative quantity per (symbol, side, order_id) with timestamps
    for cleanup of stale entries.
    """

    DEFAULT_MAX_AGE_SEC = 3600.0

    def __init__(self, max_age_sec: float = DEFAULT_MAX_AGE_SEC):
        # Key -> (cum_qty, timestamp)
        self._seen_fills: Dict[str, Tuple[Decimal, float]] = {}
        self._max_age_sec = max_age_sec
        self._cleanup_count = 0

    def should_process_fill(
        self,
        fill_payload: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None
    ) -> bool:
        """
        Check if the fill has already been processed based on cumulative quantity.

        Args:
            fill_payload: The payload from the fill event.
            metrics: Optional metrics dictionary to update.
            symbol: The trading symbol (if not in payload).

        Returns:
            True if the fill is new and should be processed, False otherwise.
        """
        details = self._extract_fill_details(fill_payload, symbol)
        if not details:
            # If we can't identify the fill, we default to processing it (fail-open)
            # but log a warning.
            logger.warning(
                "SHADOW_EXEC_POS_IDEMPOTENCY_SKIPPED_NO_KEY",
                extra={"payload_keys": list(fill_payload.keys())[:10]},
            )
            return True

        key, cum_qty = details

        if cum_qty is None:
             logger.warning(
                "SHADOW_EXEC_POS_IDEMPOTENCY_NO_CUM_INFO",
                extra={"key": key},
            )
             return True

        now = time.time()
        entry = self._seen_fills.get(key)

        if entry is None:
            self._seen_fills[key] = (cum_qty, now)
            return True

        previous_cum, _ = entry
        if cum_qty > previous_cum:
            self._seen_fills[key] = (cum_qty, now)
            return True

        if metrics is not None:
            metrics["trade_executed_duplicate_skipped"] = (
                metrics.get("trade_executed_duplicate_skipped", 0) + 1
            )

        logger.info(
            "SHADOW_EXEC_POS_TRADE_EXECUTED_DUPLICATE_SKIPPED",
            extra={
                "key": key,
                "cum": str(cum_qty),
                "prev": str(previous_cum),
            },
        )
        return False

    def _extract_fill_details(
        self,
        payload: Dict[str, Any],
        symbol_override: Optional[str]
    ) -> Optional[Tuple[str, Optional[Decimal]]]:
        """
        Extract key components and cumulative quantity from payload.

        Returns:
            Tuple of (key, cum_qty) or None if key cannot be constructed.
        """
        symbol = symbol_override or payload.get("symbol")
        side = payload.get("side") or payload.get("position_side")
        order_id = (
            payload.get("order_id")
            or payload.get("orderId")
            or payload.get("exchangeOrderId")
            or payload.get("clientOrderId")
        )

        if not symbol or not side or not order_id:
            return None

        key = f"{str(symbol).upper()}|{str(side).upper()}|{order_id}"

        raw_cum = (
            payload.get("cum_qty")
            or payload.get("cumQty")
            or payload.get("executedQty")
            or payload.get("cum_quote")
            or payload.get("cumQuote")
        )

        cum_qty: Optional[Decimal] = None
        if raw_cum is not None:
            try:
                cum_qty = Decimal(str(raw_cum))
            except (InvalidOperation, ValueError, TypeError):
                pass

        return key, cum_qty

    def cleanup(self, max_age_sec: Optional[float] = None) -> int:
        """
        Remove entries older than max_age_sec.

        Args:
            max_age_sec: Maximum age in seconds. Uses default if not provided.

        Returns:
            Number of entries removed.
        """
        if not self._seen_fills:
            return 0

        age_threshold = max_age_sec if max_age_sec is not None else self._max_age_sec
        now = time.time()
        cutoff = now - age_threshold

        # Create list to avoid runtime error during iteration
        expired_keys = [
            key for key, (_, ts) in self._seen_fills.items()
            if ts < cutoff
        ]

        for key in expired_keys:
            self._seen_fills.pop(key, None)

        removed = len(expired_keys)
        if removed > 0:
            self._cleanup_count += removed
            logger.debug(
                "SHADOW_EXEC_POS_IDEMPOTENCY_CLEANUP",
                extra={"removed": removed, "remaining": len(self._seen_fills)},
            )

        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the idempotency store."""
        return {
            "entries": len(self._seen_fills),
            "cleanup_total": self._cleanup_count,
            "max_age_sec": self._max_age_sec,
        }
