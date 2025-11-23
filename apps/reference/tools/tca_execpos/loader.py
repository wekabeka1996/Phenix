"""
TCA Event Loader
================

Loads and filters WAL records for Transaction Cost Analysis.
Reuses parsers from apps.reference.tools.order_trace.
"""
import logging
from typing import List, Optional
from apps.reference.tools.order_trace.parsers import parse_wal_records
from apps.reference.tools.order_trace.types import TraceEvent

logger = logging.getLogger(__name__)

def load_tca_events(
    logs_root: str,
    from_ts: float,
    to_ts: float,
    symbol: Optional[str] = None
) -> List[TraceEvent]:
    """
    Load and filter WAL events for the specified period.
    
    Args:
        logs_root: Path to logs directory containing WAL files
        from_ts: Start timestamp (Unix seconds)
        to_ts: End timestamp (Unix seconds)
        symbol: Optional symbol filter
        
    Returns:
        List of TraceEvent objects within the time window, sorted by timestamp.
    """
    # Load all WAL records (parsers handle file globbing)
    # Note: In a production system with massive logs, we would optimize this 
    # to only read relevant files based on date. For V1, we rely on the parser.
    all_events = parse_wal_records(logs_root, symbol=symbol)
    
    # Filter by time window
    filtered_events = [
        e for e in all_events 
        if from_ts <= e.ts <= to_ts
    ]
    
    logger.info(f"Loaded {len(filtered_events)} events for TCA (from {len(all_events)} total)")
    return filtered_events
