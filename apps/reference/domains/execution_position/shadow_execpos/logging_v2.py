"""
V2 Runtime Structured Logging
==============================

Provides structured JSONL logging for ExecPosRuntimeV2 events.
All logging is fail-closed: errors in logging never crash trading logic.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Log file path
LOG_FILE = Path("logs") / "execpos_v2_runtime.jsonl"


def _ensure_log_dir() -> None:
    """Ensure logs directory exists."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create logs directory: {e}")


def _write_jsonl(record: Dict[str, Any]) -> None:
    """
    Write a JSON record to the log file.
    Fail-closed: on any error, log warning and continue.
    """
    try:
        _ensure_log_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, default=str)
            f.write("\n")
    except Exception as e:
        logger.warning(f"V2 logging failed: {e}", exc_info=False)


def log_runtime_event(
    event_kind: str,
    symbol: str,
    action: str,
    result: str,
    why: str,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a runtime event in structured JSONL format.
    
    Args:
        event_kind: Type of event (ENTRY_INTENT, TRADE_EXECUTED, etc.)
        symbol: Trading symbol
        action: Action taken (allowed, rejected, executed, cancelled, etc.)
        result: Result of action (success, error, blocked, etc.)
        why: Short explanation/reason
        extra: Optional additional fields (qty, price, side, order_id, etc.)
    
    Example output:
        {
          "ts": "2025-11-20T17:30:00.123Z",
          "runtime": "ExecPosRuntimeV2",
          "symbol": "BTCUSDT",
          "event_kind": "ENTRY_INTENT",
          "action": "allowed",
          "result": "success",
          "why": "gatekeeper_passed",
          "qty": "0.001",
          "side": "buy"
        }
    """
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "runtime": "ExecPosRuntimeV2",
        "symbol": symbol,
        "event_kind": event_kind,
        "action": action,
        "result": result,
        "why": why,
    }
    
    if extra:
        # Merge extra fields, converting values to strings for JSON safety
        for k, v in extra.items():
            if v is not None:
                record[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v
    
    _write_jsonl(record)


def log_watchdog_action(
    symbol: str,
    side: str,
    violation_kind: str,
    action: str,
    result: str,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a watchdog violation detection or healing action.
    
    Args:
        symbol: Trading symbol
        side: Position side (LONG/SHORT)
        violation_kind: Type of violation (NO_SL, ORPHAN_SL,TOO_MANY_SL)
        action: Action taken (detected, healed, cancelled_order, placed_order)
        result: Result (success, failed, skipped)
        extra: Optional additional fields
    
    Example output:
        {
          "ts": "2025-11-20T17:30:01.456Z",
          "runtime": "ExecPosRuntimeV2",
          "symbol": "BTCUSDT",
          "event_kind": "WATCHDOG_ACTION",
          "watchdog_violation_kind": "ORPHAN_SL",
          "action": "cancelled_order",
          "result": "success",
          "why": "auto_heal_orphan_sl",
          "order_id": "1234567"
        }
    """
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "runtime": "ExecPosRuntimeV2",
        "symbol": symbol,
        "event_kind": "WATCHDOG_ACTION",
        "side": side,
        "watchdog_violation_kind": violation_kind,
        "action": action,
        "result": result,
        "why": f"watchdog_{violation_kind.lower()}",
    }
    
    if extra:
        for k, v in extra.items():
            if v is not None:
                record[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v
    
    _write_jsonl(record)


def log_bracket_eval_snapshot(
    symbol: str,
    side: str,
    position_qty: float,
    position_cycle_id: int,
    snapshot_state: str,
    open_brackets: list,
    bracket_plan: list
) -> None:
    """
    Log a BRACKET_EVAL_SNAPSHOT event for replay analysis.
    
    This function writes structured snapshots of bracket evaluations
    to enable offline replay and invariant testing.
    
    Args:
        symbol: Trading symbol
        side: Position side (LONG/SHORT/FLAT)
        position_qty: Position quantity
        position_cycle_id: Cycle ID for position lifecycle tracking
        snapshot_state: Orders snapshot state (UNKNOWN/STALE/FRESH)
        open_brackets: List of open bracket orders (dicts with orderId, side, type, qty, price, clientOrderId)
        bracket_plan: List of planned actions (dicts with action_type, qty, price, why)
    
    Example output:
        {
          "ts": "2025-11-26T00:15:00.123Z",
          "runtime": "ExecPosRuntimeV2",
          "event_kind": "BRACKET_EVAL_SNAPSHOT",
          "symbol": "BTCUSDT",
          "side": "LONG",
          "position_qty": 1.0,
          "position_cycle_id": 42,
          "orders_snapshot_state": "FRESH",
          "snapshot": "{...json...}"
        }
    """
    try:
        # Build the snapshot payload
        snapshot = {
            "symbol": symbol,
            "side": side,
            "position_qty": position_qty,
            "position_cycle_id": position_cycle_id,
            "orders_snapshot_state": snapshot_state,
            "open_brackets": open_brackets,
            "bracket_plan": bracket_plan
        }
        
        # Serialize to JSON string for the 'snapshot' field
        snapshot_json = json.dumps(snapshot, default=str)
        
        # Create log record
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "runtime": "ExecPosRuntimeV2",
            "event_kind": "BRACKET_EVAL_SNAPSHOT",
            "symbol": symbol,
            "side": side,
            "position_qty": position_qty,
            "snapshot": snapshot_json
        }
        
        _write_jsonl(record)
        
    except Exception as e:
        # Fail-closed: never crash on logging errors
        logger.warning(f"Failed to log BRACKET_EVAL_SNAPSHOT: {e}", exc_info=False)
