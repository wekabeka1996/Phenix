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

logger = logging.getLogger(__name__)


class OrderEventType(Enum):
    INTENT = "ORDER_INTENT"
    PLACED = "ORDER_PLACED"
    REJECTED = "ORDER_REJECTED"
    FILLED = "ORDER_FILLED"
    CANCELLED = "ORDER_CANCELLED"  # Added for backtest regime changes
    UNKNOWN = "UNKNOWN"


@dataclass
class OrderLogEntry:
    """Parsed order log entry."""
    timestamp: float
    event_type: OrderEventType
    symbol: str
    side: str  # BUY or SELL
    quantity: Optional[float] = None
    price: Optional[float] = None
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
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
        
        event_type_str = data.get("event_type", "UNKNOWN")
        try:
            event_type = OrderEventType(event_type_str)
        except ValueError:
            event_type = OrderEventType.UNKNOWN
            
        return OrderLogEntry(
            timestamp=data.get("timestamp", 0.0),
            event_type=event_type,
            symbol=data.get("symbol", "UNKNOWN"),
            side=data.get("side", "UNKNOWN"),
            quantity=data.get("quantity"),
            price=data.get("price"),
            order_id=str(data.get("order_id", "")) if data.get("order_id") else None,
            client_order_id=data.get("client_order_id"),
            nrr_code=data.get("nrr_code"),
            why=data.get("why"),
            metadata=data.get("metadata", {}),
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
