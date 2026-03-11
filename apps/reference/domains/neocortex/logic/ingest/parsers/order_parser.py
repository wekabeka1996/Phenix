"""
Order Log Parser

Parses order events from logs/order_log_v1.jsonl

Format: One JSON object per line containing order lifecycle events.

Event Types:
    - ORDER_INTENT: Trade intent proposed
    - ORDER_PLACED: Order sent to exchange
    - ORDER_REJECTED: Order rejected (with NRR code)
    - ORDER_FILLED: Order filled (execution)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
import math

logger = logging.getLogger(__name__)


class OrderEventType(Enum):
    INTENT = "ORDER_INTENT"
    PLACED = "ORDER_PLACED"
    REJECTED = "ORDER_REJECTED"
    FILLED = "ORDER_FILLED"
    CANCELLED = "ORDER_CANCELLED"  # Added for backtest regime changes
    TIMEOUT = "ORDER_TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class OrderLogEntry:
    """Parsed order log entry."""
    timestamp: float
    event_ts_ms: int
    event_type: OrderEventType
    symbol: str
    side: str  # BUY or SELL
    quantity: Optional[float] = None
    price: Optional[float] = None
    lifecycle_id: Optional[str] = None
    trade_id: Optional[str] = None
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    legacy_rid: Optional[str] = None
    nrr_code: Optional[str] = None  # Normalized Reject Reason
    why: Optional[str] = None  # Human-readable reason
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_entry(self) -> bool:
        """True if this is an entry (open position) order."""
        return self.metadata.get("order_type") == "MARKET_ENTRY"
    
    @property  
    def is_exit(self) -> bool:
        """True if this is an exit (close position) order."""
        return self.metadata.get("reduce_only", False)


def _normalize_epoch_to_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric) or numeric <= 0.0:
        return None

    if numeric >= 1e11:
        return int(round(numeric))
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))
    return None


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_order_log_line(line: str) -> Optional[OrderLogEntry]:
    """
    Parse a single order log line (JSONL format).
    
    Args:
        line: Raw JSON line
        
    Returns:
        OrderLogEntry if successful, None otherwise
    """
    line = line.strip()
    if not line:
        return None
        
    try:
        data = json.loads(line)
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        adapter_response = data.get("adapter_response", {})
        if not isinstance(adapter_response, dict):
            adapter_response = {}

        event_ts_ms = None
        for key in ("event_ts_ms", "timestamp_ms", "timestamp", "ts"):
            if key in data:
                event_ts_ms = _normalize_epoch_to_ms(data.get(key))
                if event_ts_ms is not None:
                    break

        if event_ts_ms is None:
            logger.warning(
                "Rejecting order log row without valid timestamp: event_type=%s symbol=%s",
                data.get("event_type", "UNKNOWN"),
                data.get("symbol", "UNKNOWN"),
            )
            return None
        
        event_type_str = data.get("event_type", "UNKNOWN")
        try:
            event_type = OrderEventType(event_type_str)
        except ValueError:
            event_type = OrderEventType.UNKNOWN

        return OrderLogEntry(
            timestamp=event_ts_ms / 1000.0,
            event_ts_ms=event_ts_ms,
            event_type=event_type,
            symbol=data.get("symbol", "UNKNOWN"),
            side=data.get("side", "UNKNOWN"),
            quantity=data.get("quantity"),
            price=data.get("price"),
            lifecycle_id=_optional_str(data.get("lifecycle_id")),
            trade_id=(
                _optional_str(data.get("trade_id"))
                or _optional_str(metadata.get("fill_trade_id"))
            ),
            order_id=(
                _optional_str(data.get("order_id"))
                or _optional_str(adapter_response.get("orderId"))
            ),
            client_order_id=(
                _optional_str(data.get("client_order_id"))
                or _optional_str(adapter_response.get("clientOrderId"))
            ),
            legacy_rid=_optional_str(data.get("rid")),
            nrr_code=data.get("nrr_code"),
            why=data.get("why"),
            metadata=metadata,
            raw=data
        )
        
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse order log: {e}")
        return None


def parse_order_log_file(file_path: str) -> List[OrderLogEntry]:
    """
    Parse an entire order log file.
    
    Args:
        file_path: Path to log file
        
    Returns:
        List of OrderLogEntry objects
    """
    entries = []
    with open(file_path, 'r') as f:
        for line in f:
            entry = parse_order_log_line(line)
            if entry:
                entries.append(entry)
    return entries
