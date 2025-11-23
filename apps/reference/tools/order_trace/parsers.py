"""
Log Parsers for Order Trace
============================

Parsers for DecisionLog, ExecPos V2 runtime logs, WAL records, and exposure events.
All parsers normalize events into TraceEvent format.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import TraceEvent

logger = logging.getLogger(__name__)


def _parse_iso_timestamp(ts_str: str) -> float:
    """Parse ISO 8601 timestamp to Unix seconds."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


def parse_decision_log(log_path: str, symbol: Optional[str] = None, rid: Optional[str] = None) -> List[TraceEvent]:
    """
    Parse DecisionLog file into TraceEvents.
    
    Args:
        log_path: Path to domain_decision_making.log
        symbol: Filter by symbol (optional)
        rid: Filter by request ID (optional)
    
    Returns:
        List of TraceEvent items sorted by timestamp
    """
    events = []
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # DecisionLog format: "timestamp | LEVEL | JSON"
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                
                try:
                    payload = json.loads(parts[2].strip())
                except json.JSONDecodeError:
                    continue
                
                # Filter by symbol/rid
                if symbol and payload.get("symbol") != symbol:
                    continue
                if rid and payload.get("rid") != rid:
                    continue
                
                # Convert ms timestamp to seconds
                ts = payload.get("ts", 0) / 1000.0
                event_type = payload.get("event", "UNKNOWN")
                why = ", ".join(payload.get("why", [])) if isinstance(payload.get("why"), list) else str(payload.get("why", ""))
                
                events.append(TraceEvent(
                    ts=ts,
                    source="DECISION",
                    event_type=event_type,
                    payload=payload,
                    why=why
                ))
    
    except FileNotFoundError:
        logger.warning(f"DecisionLog not found: {log_path}")
    except Exception as e:
        logger.error(f"Error parsing DecisionLog: {e}")
    
    return sorted(events, key=lambda e: e.ts)


def parse_execpos_runtime_log(log_path: str, symbol: Optional[str] = None) -> List[TraceEvent]:
    """
    Parse ExecPos V2 runtime JSONL log into TraceEvents.
    
    Args:
        log_path: Path to execpos_v2_runtime.jsonl
        symbol: Filter by symbol (optional)
    
    Returns:
        List of TraceEvent items sorted by timestamp
    """
    events = []
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Filter by symbol
                if symbol and payload.get("symbol") != symbol:
                    continue
                
                ts = _parse_iso_timestamp(payload.get("ts", ""))
                event_type = payload.get("event_kind", "UNKNOWN")
                why = payload.get("why", "")
                
                events.append(TraceEvent(
                    ts=ts,
                    source="RUNTIME",
                    event_type=event_type,
                    payload=payload,
                    why=why
                ))
    
    except FileNotFoundError:
        logger.warning(f"Runtime log not found: {log_path}")
    except Exception as e:
        logger.error(f"Error parsing runtime log: {e}")
    
    return sorted(events, key=lambda e: e.ts)


def parse_wal_records(wal_dir: str, symbol: Optional[str] = None, trade_id: Optional[str] = None, 
                     order_id: Optional[str] = None, position_id: Optional[str] = None) -> List[TraceEvent]:
    """
    Parse WAL files (EXEC_TRADE/ORDER/POSITION) into TraceEvents.
    
    Args:
        wal_dir: Directory containing WAL files (<date>.jsonl)
        symbol: Filter by symbol (optional)
        trade_id: Filter by trade_id (optional)
        order_id: Filter by order_id (optional)
        position_id: Filter by position_id (optional)
    
    Returns:
        List of TraceEvent items sorted by timestamp
    """
    events = []
    
    try:
        wal_path = Path(wal_dir)
        if not wal_path.exists():
            logger.warning(f"WAL directory not found: {wal_dir}")
            return events
        
        # Read all .jsonl files in WAL directory
        for wal_file in sorted(wal_path.glob("*.jsonl")):
            try:
                with open(wal_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        
                        # Only process ExecPos WAL records
                        if payload.get("domain") != "execution_position" or payload.get("runtime") != "v2":
                            continue
                        
                        event_type = payload.get("event_type")
                        if event_type not in ("EXEC_TRADE", "EXEC_ORDER", "EXEC_POSITION"):
                            continue
                        
                        # Filter by criteria
                        if symbol and payload.get("symbol") != symbol:
                            continue
                        if trade_id and payload.get("trade_id") != trade_id:
                            continue
                        if order_id and payload.get("order_id") != order_id:
                            continue
                        if position_id and payload.get("position_id") != position_id:
                            continue
                        
                        ts = float(payload.get("ts", 0))
                        
                        # Extract "why" from event context
                        why = ""
                        if event_type == "EXEC_TRADE":
                            role = payload.get("role", "UNKNOWN")
                            why = f"role={role}"
                        elif event_type == "EXEC_ORDER":
                            status = payload.get("status", "UNKNOWN")
                            why = f"status={status}"
                        elif event_type == "EXEC_POSITION":
                            direction = payload.get("direction", "UNKNOWN")
                            why = f"direction={direction}"
                        
                        events.append(TraceEvent(
                            ts=ts,
                            source="WAL",
                            event_type=event_type,
                            payload=payload,
                            why=why
                        ))
            
            except Exception as e:
                logger.error(f"Error parsing WAL file {wal_file}: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error reading WAL directory: {e}")
    
    return sorted(events, key=lambda e: e.ts)


def parse_exposure_events(log_path: Optional[str], symbol: Optional[str] = None) -> List[TraceEvent]:
    """
    Parse exposure events log into TraceEvents.
    
    Args:
        log_path: Path to exposure events log (if separate from WAL)
        symbol: Filter by symbol (optional)
    
    Returns:
        List of TraceEvent items sorted by timestamp
    
    Note: Currently exposure is tracked via EXEC_POSITION WAL records.
          This is a placeholder for future event-based exposure tracking.
    """
    events = []
    
    if not log_path:
        return events
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Check for exposure update events
                if payload.get("kind") !=  "EVT:EXEC_POS_EXPOSURE_UPDATED":
                    continue
                
                event_payload = payload.get("payload", {})
                
                # Filter by symbol
                if symbol and event_payload.get("symbol") != symbol:
                    continue
                
                ts = float(event_payload.get("update_time", 0))
                direction = event_payload.get("direction", "UNKNOWN")
                
                events.append(TraceEvent(
                    ts=ts,
                    source="EXPOSURE",
                    event_type="EXPOSURE_UPDATE",
                    payload=event_payload,
                    why=f"direction={direction}"
                ))
    
    except FileNotFoundError:
        logger.warning(f"Exposure log not found: {log_path}")
    except Exception as e:
        logger.error(f"Error parsing exposure log: {e}")
    
    return sorted(events, key=lambda e: e.ts)
