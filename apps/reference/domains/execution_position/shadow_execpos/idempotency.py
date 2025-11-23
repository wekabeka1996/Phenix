"""
Idempotency Logic for Shadow ExecPos
====================================

Handles deduplication of events and fills to ensure safe processing.
"""
from typing import Any, Dict, Optional
import time
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class FillIdempotency:
    """
    Determines if a fill (TRADE_EXECUTED) should be processed.
    
    Tracks cumulative quantity per (symbol, side, order_id).
    """
    
    def __init__(self):
        self._seen_fills: Dict[str, Decimal] = {}

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
        symbol = symbol or fill_payload.get("symbol")
        side = fill_payload.get("side") or fill_payload.get("position_side")
        order_id = (
            fill_payload.get("order_id")
            or fill_payload.get("orderId")
            or fill_payload.get("exchangeOrderId")
            or fill_payload.get("clientOrderId")
        )

        if not symbol or not side or not order_id:
            logger.warning(
                "SHADOW_EXEC_POS_IDEMPOTENCY_SKIPPED_NO_KEY",
                extra={"payload_keys": list(fill_payload.keys())[:10]},
            )
            return True

        key = f"{str(symbol).upper()}|{str(side).upper()}|{order_id}"

        raw_cum = (
            fill_payload.get("cum_qty")
            or fill_payload.get("cumQty")
            or fill_payload.get("executedQty")
            or fill_payload.get("cum_quote")
            or fill_payload.get("cumQuote")
        )
        
        cum: Optional[Decimal] = None
        try:
            cum = Decimal(str(raw_cum)) if raw_cum is not None else None
        except Exception:
            cum = None

        if cum is None:
            logger.warning(
                "SHADOW_EXEC_POS_IDEMPOTENCY_NO_CUM_INFO",
                extra={"symbol": symbol, "side": side, "order_id": order_id},
            )
            return True

        previous = self._seen_fills.get(key)
        if previous is None:
            self._seen_fills[key] = cum
            return True

        if cum > previous:
            self._seen_fills[key] = cum
            return True

        if metrics is not None:
            metrics["trade_executed_duplicate_skipped"] = (
                metrics.get("trade_executed_duplicate_skipped", 0) + 1
            )
            
        logger.info(
            "SHADOW_EXEC_POS_TRADE_EXECUTED_DUPLICATE_SKIPPED",
            extra={
                "symbol": symbol,
                "side": side,
                "order_id": order_id,
                "cum": str(cum),
                "prev": str(previous),
            },
        )
        return False

class EventIdempotency:
    """
    Generic event deduplication using TTL.
    """

    def __init__(self, ttl_seconds: float = 3600.0):
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, float] = {}

    def mark_processed(self, key: str) -> None:
        """Mark a key as processed with the current timestamp."""
        self._store[key] = time.time()

    def is_processed(self, key: str) -> bool:
        """Check if a key has been processed within the TTL window."""
        timestamp = self._store.get(key)
        if timestamp is None:
            return False
            
        if time.time() - timestamp > self._ttl_seconds:
            return False
            
        return True

    def cleanup(self) -> int:
        """Remove expired keys from the store."""
        if not self._store:
            return 0
            
        now = time.time()
        expired_keys = [
            key for key, ts in self._store.items()
            if now - ts > self._ttl_seconds
        ]
        
        for key in expired_keys:
            self._store.pop(key, None)
            
        return len(expired_keys)
