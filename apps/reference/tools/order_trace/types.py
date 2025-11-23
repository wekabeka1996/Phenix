"""
TradeTrace Data Types
=====================

Defines the core data structures for trade traces and correlation sources.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceEvent:
    """
    A single event in a trade trace timeline.
    
    Attributes:
        ts: Unix timestamp (seconds, float)
        source: Event source (DECISION/RUNTIME/WAL/EXPOSURE)
        event_type: Specific event type (FEATURES_RX, ENTRY_INTENT, EXEC_TRADE, etc.)
        payload: Raw event data as dict
        why: Short explanation/reason for this event
    """
    ts: float
    source: str
    event_type: str
    payload: Dict[str, Any]
    why: str = ""


@dataclass
class TradeTrace:
    """
    Complete trade narrative with chronological events.
    
    Attributes:
        trace_id: Primary identifier (trade_id, order_id, or position_id)
        symbol: Trading symbol
        direction: Position direction (LONG/SHORT/FLAT/UNKNOWN)
        entry_size: Entry position size (if known)
        final_size: Final position size (if known) 
        entry_info: Entry details (ts, price, reason) if available
        exit_info: Exit details (ts, price, reason, pnl) if available
        events: Chronologically sorted list of TraceEvent items
        gaps: List of missing data warnings
    """
    trace_id: str
    symbol: str
    direction: str = "UNKNOWN"
    entry_size: Optional[float] = None
    final_size: Optional[float] = None
    entry_info: Optional[Dict[str, Any]] = None
    exit_info: Optional[Dict[str, Any]] = None
    events: List[TraceEvent] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_size": self.entry_size,
            "final_size": self.final_size,
            "entry_info": self.entry_info,
            "exit_info": self.exit_info,
            "events": [
                {
                    "ts": e.ts,
                    "source": e.source,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "why": e.why,
                }
                for e in self.events
            ],
            "gaps": self.gaps,
        }


@dataclass
class TraceSources:
    """
    Abstraction for accessing log/WAL sources.
    
    Attributes:
        decision_log_path: Path to DecisionLog file
        runtime_log_path: Path to ExecPos V2 runtime JSONL
        wal_dir: Directory containing WAL files (<date>.jsonl)
        exposure_log_path: Optional path to exposure events log
    """
    decision_log_path: Optional[str] = None
    runtime_log_path: Optional[str] = None
    wal_dir: Optional[str] = None
    exposure_log_path: Optional[str] = None
