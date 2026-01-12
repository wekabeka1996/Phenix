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

logger = logging.getLogger(__name__)


class CoreEventType(Enum):
    POSITION_CLOSED = "position_closed"
    PORTFOLIO_UPDATE = "portfolio_update"
    EQUITY_UPDATE = "equity_update"


@dataclass
class CoreLogEntry:
    """Parsed core log entry."""
    timestamp: float
    timestamp_str: str
    event_type: CoreEventType
    symbol: Optional[str] = None
    equity: Optional[float] = None
    realized_pnl: Optional[float] = None
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


def parse_timestamp(ts_str: str) -> float:
    """Parse timestamp string to epoch float."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
        return dt.timestamp()
    except ValueError:
        return 0.0


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
    
    # Try Position Closed pattern
    match = POSITION_CLOSED_PATTERN.match(line)
    if match:
        return CoreLogEntry(
            timestamp=parse_timestamp(match.group(1)),
            timestamp_str=match.group(1),
            event_type=CoreEventType.POSITION_CLOSED,
            symbol=match.group(2),
            reason=match.group(3),
            raw_line=line
        )
    
    # Try Equity pattern
    match = EQUITY_PATTERN.match(line)
    if match:
        return CoreLogEntry(
            timestamp=parse_timestamp(match.group(1)),
            timestamp_str=match.group(1),
            event_type=CoreEventType.EQUITY_UPDATE,
            equity=parse_scientific_notation(match.group(2)),
            unrealized_pnl=parse_scientific_notation(match.group(3)),
            raw_line=line
        )
    
    # Try Portfolio pattern
    match = PORTFOLIO_PATTERN.match(line)
    if match:
        return CoreLogEntry(
            timestamp=parse_timestamp(match.group(1)),
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
