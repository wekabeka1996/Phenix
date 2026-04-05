"""
Pending Brackets WAL Persistence (PHASE4-LIMIT-BRACKETS-PERSISTENCE)

Persists _pending_brackets state to WAL for LIMIT entry orders.
Allows rehydration on restart to prevent naked positions.

Records:
- PENDING_BRACKETS_STORED: When LIMIT entry placed, brackets deferred
- PENDING_BRACKETS_CLEARED: When brackets placed or entry cancelled
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal
from apps.reference.core.time.clock import get_clock

LOG = logging.getLogger(__name__)

# Verb constants
VERB_STORED = "PENDING_BRACKETS_STORED"
VERB_CLEARED = "PENDING_BRACKETS_CLEARED"


def write_pending_brackets_stored(
    *,
    entry_order_id: str,
    symbol: str,
    side: str,
    sl: float,
    tp: float,
    qty: float,
    rid: str,
    idem_key: str,
    tick_size: float,
    corr_id: Optional[str] = None,
    oco_group_id: Optional[str] = None,
    entry_client_order_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    strategy_source: Optional[str] = None,
    owner_status: Optional[str] = None,
    owner_detail: Optional[str] = None,
    assigned_strategies: Optional[list[str]] = None,
    placement_path: Optional[str] = None,
) -> None:
    """
    Write PENDING_BRACKETS_STORED to WAL when LIMIT entry defers TP/SL.

    This record allows rehydration on restart.
    """
    ts_ms = get_clock().now_ms()

    payload: Dict[str, Any] = {
        "ts_ms": ts_ms,
        "entry_order_id": str(entry_order_id),
        "symbol": str(symbol),
        "side": str(side),
        "sl": float(sl) if sl is not None else None,
        "tp": float(tp) if tp is not None else None,
        "qty": float(qty),
        "rid": str(rid),
        "idem_key": str(idem_key),
        "tick_size": float(tick_size),
    }

    if corr_id is not None:
        payload["corr_id"] = str(corr_id)
    if oco_group_id is not None:
        payload["oco_group_id"] = str(oco_group_id)
    if entry_client_order_id is not None:
        payload["entry_client_order_id"] = str(entry_client_order_id)
    if strategy_id is not None:
        payload["strategy_id"] = str(strategy_id)
    if strategy_source is not None:
        payload["strategy_source"] = str(strategy_source)
    if owner_status is not None:
        payload["owner_status"] = str(owner_status)
    if owner_detail is not None:
        payload["owner_detail"] = str(owner_detail)
    if assigned_strategies is not None:
        payload["assigned_strategies"] = [
            str(item) for item in assigned_strategies if str(item or "").strip()
        ]
    if placement_path is not None:
        payload["placement_path"] = str(placement_path)

    msg = Message(
        op="EVT",
        verb=VERB_STORED,
        src="execution_position",
        dst="wal",
        rid=str(rid),
        ts=ts_ms,
        why=truncate_why(f"limit_entry_deferred_brackets:{symbol}"),
        pld=payload,
    )

    wal.append(msg.model_dump())
    LOG.debug(f"[WAL] {VERB_STORED}: {entry_order_id} for {symbol}")


def write_pending_brackets_cleared(
    *,
    entry_order_id: str,
    symbol: str,
    reason: str,
    rid: Optional[str] = None,
) -> None:
    """
    Write PENDING_BRACKETS_CLEARED to WAL when brackets are placed or entry cancelled.

    Reasons:
    - "filled": LIMIT entry filled, brackets placed
    - "cancelled": Entry order cancelled (regime change, TTL, user)
    - "expired": Entry order expired
    """
    ts_ms = get_clock().now_ms()

    payload: Dict[str, Any] = {
        "ts_ms": ts_ms,
        "entry_order_id": str(entry_order_id),
        "symbol": str(symbol),
        "reason": str(reason),
    }

    msg = Message(
        op="EVT",
        verb=VERB_CLEARED,
        src="execution_position",
        dst="wal",
        rid=str(rid) if rid else f"clear:{entry_order_id}:{ts_ms}",
        ts=ts_ms,
        why=truncate_why(f"brackets_cleared:{reason}"),
        pld=payload,
    )

    wal.append(msg.model_dump())
    LOG.debug(f"[WAL] {VERB_CLEARED}: {entry_order_id} reason={reason}")


def read_pending_brackets_from_wal() -> Dict[str, Dict[str, Any]]:
    """
    Read pending brackets from WAL for rehydration on startup.

    Reconstructs state by replaying STORED/CLEARED events.
    Only returns brackets that were STORED but not yet CLEARED.

    Returns:
        Dict[entry_order_id, bracket_data]
    """
    import glob
    from vfoundation.config import config

    pending: Dict[str, Dict[str, Any]] = {}
    wal_dir = config.wal_dir

    # Scan all WAL files (today and recent days)
    wal_pattern = str(wal_dir / "*.jsonl")
    # Oldest first for correct replay
    wal_files = sorted(glob.glob(wal_pattern))

    for wal_file in wal_files:
        try:
            with open(wal_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        verb = record.get("verb", "")
                        pld = record.get("pld", {})

                        if verb == VERB_STORED:
                            entry_order_id = pld.get("entry_order_id")
                            if entry_order_id:
                                pending[entry_order_id] = {
                                    "symbol": pld.get("symbol"),
                                    "side": pld.get("side"),
                                    "sl": pld.get("sl"),
                                    "tp": pld.get("tp"),
                                    "qty": pld.get("qty"),
                                    "rid": pld.get("rid"),
                                    "idem_key": pld.get("idem_key"),
                                    "tick_size": pld.get("tick_size"),
                                    "corr_id": pld.get("corr_id"),
                                    "oco_group_id": pld.get("oco_group_id"),
                                    "entry_client_order_id": pld.get("entry_client_order_id"),
                                    "strategy_id": pld.get("strategy_id"),
                                    "strategy_source": pld.get("strategy_source"),
                                    "owner_status": pld.get("owner_status"),
                                    "owner_detail": pld.get("owner_detail"),
                                    "assigned_strategies": pld.get("assigned_strategies"),
                                    "placement_path": pld.get("placement_path") or "deferred_pending",
                                    "created_at": pld.get("ts_ms", 0) / 1000.0,
                                }

                        elif verb == VERB_CLEARED:
                            entry_order_id = pld.get("entry_order_id")
                            if entry_order_id and entry_order_id in pending:
                                del pending[entry_order_id]

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            LOG.warning(f"Error reading WAL file {wal_file}: {e}")
            continue

    LOG.info(f"[WAL] Rehydrated {len(pending)} pending brackets from WAL")
    return pending


def gc_old_bracket_records(max_age_days: int = 7) -> int:
    """
    Garbage collect old bracket WAL records (optional maintenance).

    Note: WAL files are date-based, so old files can simply be deleted.
    This function is for in-file cleanup if needed.

    Returns:
        Number of records considered for cleanup
    """
    # WAL files are rotated daily, so GC is handled by file deletion
    # This is a placeholder for future in-file compaction if needed
    return 0
