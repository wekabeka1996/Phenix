"""
V2 Runtime Structured Logging
==============================

Provides structured JSONL logging for ExecPosRuntimeV2 events.
All logging is fail-closed: errors in logging never crash trading logic.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Log file path - configurable via environment variable
_LOG_DIR = Path(os.environ.get("EXECPOS_LOG_DIR", "logs"))
LOG_FILE = _LOG_DIR / "execpos_v2_runtime.jsonl"

# Runtime identifier
_RUNTIME_ID = "ExecPosRuntimeV2"


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


def _build_base_record(event_kind: str, symbol: str) -> Dict[str, Any]:
    """
    Build base record with common fields.

    Args:
        event_kind: Type of event
        symbol: Trading symbol

    Returns:
        Dict with ts, runtime, event_kind, symbol
    """
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "runtime": _RUNTIME_ID,
        "event_kind": event_kind,
        "symbol": symbol,
    }


def _merge_extra(record: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> None:
    """
    Merge extra fields into record, converting non-primitives to strings.

    Args:
        record: Target record dict (modified in-place)
        extra: Optional additional fields
    """
    if not extra:
        return
    for k, v in extra.items():
        if v is not None:
            record[k] = v if isinstance(v, (str, int, float, bool)) else str(v)


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
          "ts": "2025-11-20T17:30:00.123+00:00",
          "runtime": "ExecPosRuntimeV2",
          "event_kind": "ENTRY_INTENT",
          "symbol": "BTCUSDT",
          "action": "allowed",
          "result": "success",
          "why": "gatekeeper_passed",
          "qty": "0.001",
          "side": "buy"
        }
    """
    record = _build_base_record(event_kind, symbol)
    record.update({
        "action": action,
        "result": result,
        "why": why,
    })
    _merge_extra(record, extra)
    _write_jsonl(record)


def log_bracket_eval_snapshot(
    symbol: str,
    side: str,
    position_qty: float,
    position_cycle_id: int,
    snapshot_state: str,
    open_brackets: List[Dict[str, Any]],
    bracket_plan: List[Dict[str, Any]]
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
          "ts": "2025-11-26T00:15:00.123+00:00",
          "runtime": "ExecPosRuntimeV2",
          "event_kind": "BRACKET_EVAL_SNAPSHOT",
          "symbol": "BTCUSDT",
          "side": "LONG",
          "position_qty": 1.0,
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
            "bracket_plan": bracket_plan,
        }

        record = _build_base_record("BRACKET_EVAL_SNAPSHOT", symbol)
        record.update({
            "side": side,
            "position_qty": position_qty,
            "snapshot": json.dumps(snapshot, default=str),
        })

        _write_jsonl(record)

    except Exception as e:
        # Fail-closed: never crash on logging errors
        logger.warning(f"Failed to log BRACKET_EVAL_SNAPSHOT: {e}", exc_info=False)
