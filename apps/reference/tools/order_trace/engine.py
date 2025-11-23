"""
Correlation Engine for Order Trace
===================================

Correlates events from multiple sources into coherent trade narratives.
"""
import logging
from typing import List, Optional

from .types import TradeTrace, TraceEvent, TraceSources
from .parsers import (
    parse_decision_log,
    parse_execpos_runtime_log,
    parse_wal_records,
    parse_exposure_events,
)

logger = logging.getLogger(__name__)


def build_trace_for_trade(trade_id: str, sources: TraceSources) -> Optional[TradeTrace]:
    """
    Build trade narrative for a specific trade_id.
    
    Args:
        trade_id: Unique trade identifier
        sources: TraceSources with paths to log files
    
    Returns:
        TradeTrace object or None if no data found
    """
    all_events: List[TraceEvent] = []
    gaps = []
    
    # Parse WAL records (primary source for trade_id)
    if sources.wal_dir:
        wal_events = parse_wal_records(sources.wal_dir, trade_id=trade_id)
        all_events.extend(wal_events)
        
        # Extract symbol from WAL for filtering other sources
        symbol = None
        for event in wal_events:
            if event.payload.get("symbol"):
                symbol = event.payload["symbol"]
                break
        
        if symbol:
            # Parse DecisionLog
            if sources.decision_log_path:
                decision_events = parse_decision_log(sources.decision_log_path, symbol=symbol)
                all_events.extend(decision_events)
            else:
                gaps.append("MISSING_DECISION_LOG")
            
            # Parse runtime logs
            if sources.runtime_log_path:
                runtime_events = parse_execpos_runtime_log(sources.runtime_log_path, symbol=symbol)
                all_events.extend(runtime_events)
            else:
                gaps.append("MISSING_RUNTIME_LOG")
            
            # Parse exposure events
            if sources.exposure_log_path:
                exposure_events = parse_exposure_events(sources.exposure_log_path, symbol=symbol)
                all_events.extend(exposure_events)
    else:
        gaps.append("MISSING_WAL")
        return None
    
    if not all_events:
        logger.warning(f"No events found for trade_id={trade_id}")
        return None
    
    # Sort chronologically
    all_events.sort(key=lambda e: e.ts)
    
    # Extract trade metadata
    symbol = "UNKNOWN"
    direction = "UNKNOWN"
    entry_info = None
    exit_info = None
    entry_size = None
    final_size = None
    
    for event in all_events:
        if event.event_type == "EXEC_TRADE":
            if not symbol or symbol == "UNKNOWN":
                symbol = event.payload.get("symbol", "UNKNOWN")
            
            role = event.payload.get("role", "UNKNOWN")
            if role == "ENTRY" and not entry_info:
                entry_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": event.why,
                }
                entry_size = float(event.payload.get("qty", 0))
            elif role in ("SL", "TP", "CLOSE") and not exit_info:
                exit_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": role,
                    "pnl": event.payload.get("realized_pnl", "0"),
                }
                final_size = 0.0
        
        elif event.event_type == "EXEC_POSITION":
            direction = event.payload.get("direction", direction)
    
    return TradeTrace(
        trace_id=trade_id,
        symbol=symbol,
        direction=direction,
        entry_size=entry_size,
        final_size=final_size,
        entry_info=entry_info,
        exit_info=exit_info,
        events=all_events,
        gaps=gaps,
    )


def build_trace_for_position(position_id: str, sources: TraceSources) -> Optional[TradeTrace]:
    """
    Build trade narrative for a specific position_id.
    
    Args:
        position_id: Unique position identifier
        sources: TraceSources with paths to log files
    
    Returns:
        TradeTrace object or None if no data found
    """
    all_events: List[TraceEvent] = []
    gaps = []
    
    # Parse WAL records (primary source for position_id)
    if sources.wal_dir:
        wal_events = parse_wal_records(sources.wal_dir, position_id=position_id)
        all_events.extend(wal_events)
        
        # Extract symbol from WAL for filtering other sources
        symbol = None
        for event in wal_events:
            if event.payload.get("symbol"):
                symbol = event.payload["symbol"]
                break
        
        if symbol:
            # Parse DecisionLog
            if sources.decision_log_path:
                decision_events = parse_decision_log(sources.decision_log_path, symbol=symbol)
                all_events.extend(decision_events)
            else:
                gaps.append("MISSING_DECISION_LOG")
            
            # Parse runtime logs
            if sources.runtime_log_path:
                runtime_events = parse_execpos_runtime_log(sources.runtime_log_path, symbol=symbol)
                all_events.extend(runtime_events)
            else:
                gaps.append("MISSING_RUNTIME_LOG")
            
            # Parse exposure events
            if sources.exposure_log_path:
                exposure_events = parse_exposure_events(sources.exposure_log_path, symbol=symbol)
                all_events.extend(exposure_events)
    else:
        gaps.append("MISSING_WAL")
        return None
    
    if not all_events:
        logger.warning(f"No events found for position_id={position_id}")
        return None
    
    # Sort chronologically
    all_events.sort(key=lambda e: e.ts)
    
    # Extract position metadata (similar to trace_for_trade)
    symbol = "UNKNOWN"
    direction = "UNKNOWN"
    entry_info = None
    exit_info = None
    entry_size = None
    final_size = None
    
    for event in all_events:
        if event.event_type == "EXEC_TRADE":
            symbol = event.payload.get("symbol", symbol)
            role = event.payload.get("role", "UNKNOWN")
            
            if role == "ENTRY" and not entry_info:
                entry_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": event.why,
                }
                entry_size = float(event.payload.get("qty", 0))
            elif role in ("SL", "TP", "CLOSE"):
                exit_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": role,
                    "pnl": event.payload.get("realized_pnl", "0"),
                }
                final_size = 0.0
        
        elif event.event_type == "EXEC_POSITION":
            direction = event.payload.get("direction", direction)
            size_str = event.payload.get("position_size", "0")
            try:
                pos_size = float(size_str)
                if abs(pos_size) < 0.0001:
                    final_size = 0.0
            except ValueError:
                pass
    
    return TradeTrace(
        trace_id=position_id,
        symbol=symbol,
        direction=direction,
        entry_size=entry_size,
        final_size=final_size,
        entry_info=entry_info,
        exit_info=exit_info,
        events=all_events,
        gaps=gaps,
    )
