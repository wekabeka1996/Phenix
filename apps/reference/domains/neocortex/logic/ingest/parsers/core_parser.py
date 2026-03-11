"""
Core Log Parser

Parses position events from logs/aurora_core.log

Patterns to extract:
1. Position Closed: "[SYMBOL] Position closed (neutral). Starting re-entry cooldown."
2. Portfolio Update: "ON_PORTFOLIO_DEBUG: ... equity_raw=X, realized_pnl=Y, unrealized_pnl=Z"
3. Equity Update: "totalWalletBalance=X, totalUnrealizedProfit=Y"
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import math

logger = logging.getLogger(__name__)


class CoreEventType(Enum):
    POSITION_CLOSED = "position_closed"
    TRADE_CLOSED = "trade_closed"
    PORTFOLIO_UPDATE = "portfolio_update"
    EQUITY_UPDATE = "equity_update"


@dataclass
class CoreLogEntry:
    """Parsed core log entry."""
    timestamp: float
    event_ts_ms: int
    timestamp_str: str
    event_type: CoreEventType
    symbol: Optional[str] = None
    equity: Optional[float] = None
    realized_pnl: Optional[float] = None
    realized_pnl_net: Optional[float] = None
    trade_id: Optional[str] = None
    close_ts_ms: Optional[int] = None
    entry_price: Optional[float] = None
    close_price: Optional[float] = None
    quantity: Optional[float] = None
    fees: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    reason: Optional[str] = None
    raw_line: str = ""


# Pattern: Position closed
# Format: [BTCUSDT] Position closed (neutral). Starting re-entry cooldown.
POSITION_CLOSED_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'  # Timestamp
    r' - .+? - INFO - '
    r'\[([A-Z0-9]+)\] Position closed \(([^)]+)\)'  # [SYMBOL] Position closed (reason)
)

TIMESTAMP_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})')

# Pattern: Portfolio debug with equity
# Format: ON_PORTFOLIO_DEBUG: ... equity_raw=293.27, margin_raw=23.89, ...
PORTFOLIO_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'  # Timestamp
    r' - .+? - INFO - ON_PORTFOLIO_DEBUG: .+?'
    r'equity_raw=([0-9.]+)'
)

# Pattern: Equity with realized/unrealized PnL
# Format: totalWalletBalance=345.92858879, totalUnrealizedProfit=0E-8
EQUITY_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'  # Timestamp
    r' - .+? - INFO - Emitted positions update: \d+ open positions, '
    r'totalWalletBalance=([0-9.E+-]+), totalUnrealizedProfit=([0-9.E+-]+)'
)

# Pattern: Realized PnL from portfolio keys
REALIZED_PNL_PATTERN = re.compile(
    r"'realized_pnl'|realized_pnl=([0-9.E+-]+)"
)


def _extract_field(line: str, key: str) -> Optional[str]:
    """
    Extract field value from both key=value and JSON-like snippets in log lines.
    """
    json_match = re.search(rf'"{re.escape(key)}"\s*:\s*"?(?P<val>[^",\s}}]+)"?', line)
    if json_match:
        return json_match.group("val")

    kv_match = re.search(rf'{re.escape(key)}\s*=\s*(?P<val>[^,\s]+)', line)
    if kv_match:
        return kv_match.group("val")

    return None


def parse_timestamp(ts_str: str) -> float:
    """Parse timestamp string to epoch float."""
    ts_ms = parse_timestamp_ms(ts_str)
    if ts_ms is None:
        return 0.0
    return ts_ms / 1000.0


def parse_timestamp_ms(ts_str: str) -> Optional[int]:
    """Parse timestamp string to canonical epoch milliseconds."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
        return int(round(dt.timestamp() * 1000.0))
    except ValueError:
        return None


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


def parse_scientific_notation(value: str) -> float:
    """Parse values like '0E-8' correctly."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_core_log_line(line: str) -> Optional[CoreLogEntry]:
    """
    Parse a single core log line.
    
    Args:
        line: Raw log line
        
    Returns:
        CoreLogEntry if relevant event found, None otherwise
    """
    line = line.strip()
    if not line:
        return None

    # Try structured close payload first.
    if "POSITION_CLOSED" in line or "TRADE_CLOSED" in line:
        ts_match = TIMESTAMP_PATTERN.match(line)
        ts_str = ts_match.group(1) if ts_match else ""
        log_event_ts_ms = parse_timestamp_ms(ts_str) if ts_str else None
        event_type = (
            CoreEventType.TRADE_CLOSED
            if "TRADE_CLOSED" in line
            else CoreEventType.POSITION_CLOSED
        )
        symbol = _extract_field(line, "symbol")
        realized_pnl_raw = _extract_field(line, "realized_pnl")
        realized_pnl_net_raw = _extract_field(line, "realized_pnl_net")
        trade_id = _extract_field(line, "trade_id")
        close_ts_ms_raw = _extract_field(line, "close_ts_ms")
        entry_price_raw = _extract_field(line, "entry_price")
        close_price_raw = _extract_field(line, "close_price")
        quantity_raw = _extract_field(line, "quantity")
        fees_raw = _extract_field(line, "fees")

        # Accept as structured only when at least one structured reward field is present.
        if symbol and (
            realized_pnl_raw is not None
            or realized_pnl_net_raw is not None
            or trade_id is not None
            or close_ts_ms_raw is not None
            or close_price_raw is not None
            or fees_raw is not None
        ):
            close_ts_ms = _normalize_epoch_to_ms(close_ts_ms_raw)
            event_ts_ms = close_ts_ms or log_event_ts_ms
            if event_ts_ms is None:
                return None

            return CoreLogEntry(
                timestamp=event_ts_ms / 1000.0,
                event_ts_ms=event_ts_ms,
                timestamp_str=ts_str,
                event_type=event_type,
                symbol=symbol,
                realized_pnl=parse_scientific_notation(realized_pnl_raw)
                if realized_pnl_raw is not None
                else None,
                realized_pnl_net=parse_scientific_notation(realized_pnl_net_raw)
                if realized_pnl_net_raw is not None
                else None,
                trade_id=trade_id,
                close_ts_ms=close_ts_ms,
                entry_price=parse_scientific_notation(entry_price_raw)
                if entry_price_raw is not None
                else None,
                close_price=parse_scientific_notation(close_price_raw)
                if close_price_raw is not None
                else None,
                quantity=parse_scientific_notation(quantity_raw)
                if quantity_raw is not None
                else None,
                fees=parse_scientific_notation(fees_raw) if fees_raw is not None else None,
                raw_line=line,
            )
    
    # Try Position Closed pattern
    match = POSITION_CLOSED_PATTERN.match(line)
    if match:
        event_ts_ms = parse_timestamp_ms(match.group(1))
        if event_ts_ms is None:
            return None
        return CoreLogEntry(
            timestamp=event_ts_ms / 1000.0,
            event_ts_ms=event_ts_ms,
            timestamp_str=match.group(1),
            event_type=CoreEventType.POSITION_CLOSED,
            symbol=match.group(2),
            reason=match.group(3),
            raw_line=line
        )
    
    # Try Equity pattern
    match = EQUITY_PATTERN.match(line)
    if match:
        event_ts_ms = parse_timestamp_ms(match.group(1))
        if event_ts_ms is None:
            return None
        return CoreLogEntry(
            timestamp=event_ts_ms / 1000.0,
            event_ts_ms=event_ts_ms,
            timestamp_str=match.group(1),
            event_type=CoreEventType.EQUITY_UPDATE,
            equity=parse_scientific_notation(match.group(2)),
            unrealized_pnl=parse_scientific_notation(match.group(3)),
            raw_line=line
        )
    
    # Try Portfolio pattern
    match = PORTFOLIO_PATTERN.match(line)
    if match:
        event_ts_ms = parse_timestamp_ms(match.group(1))
        if event_ts_ms is None:
            return None
        return CoreLogEntry(
            timestamp=event_ts_ms / 1000.0,
            event_ts_ms=event_ts_ms,
            timestamp_str=match.group(1),
            event_type=CoreEventType.PORTFOLIO_UPDATE,
            equity=float(match.group(2)),
            raw_line=line
        )
    
    return None


def parse_core_log_file(file_path: str) -> List[CoreLogEntry]:
    """
    Parse an entire core log file for relevant events.
    
    Args:
        file_path: Path to log file
        
    Returns:
        List of CoreLogEntry objects
    """
    entries = []
    with open(file_path, 'r') as f:
        for line in f:
            entry = parse_core_log_line(line)
            if entry:
                entries.append(entry)
    return entries


def extract_position_closes(file_path: str) -> List[CoreLogEntry]:
    """
    Extract only position close events from core log.
    
    Args:
        file_path: Path to log file
        
    Returns:
        List of CoreLogEntry with POSITION_CLOSED events
    """
    return [
        e for e in parse_core_log_file(file_path) 
        if e.event_type == CoreEventType.POSITION_CLOSED
    ]
