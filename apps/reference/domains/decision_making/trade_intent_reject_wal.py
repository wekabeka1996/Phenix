"""Decision-making WAL helper for TRADE_INTENT_REJECTED artifacts.

This module is the narrow decision_making-side writer for reject truth. It
builds an event-shaped payload and appends it directly to WAL for audit and
forensics, but it does not emit EVT:TRADE_INTENT_REJECTED on the live FSM bus.

The helper preserves most caller-supplied values as-is. When WAL output is
redirected away from disk via environment mode, it keeps only a bounded private
in-process copy instead of appending to WAL.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Literal, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

if TYPE_CHECKING:
    from apps.reference.core.time.clock import Clock

# Schema-allowed reject stages for the event payload written by this helper.
RejectStage = Literal["RISK", "STRATEGY", "DECISION", "EXECUTION"]

logger = logging.getLogger(__name__)
# Private bounded buffer used when WAL writes are redirected away from disk.
_MEMORY_REJECT_LOG: list[dict[str, Any]] = []
_MEMORY_REJECT_CAP = 200_000


def write_trade_intent_rejected(
    *,
    symbol: str,
    reason_code: str,
    stage: RejectStage,
    why: str,
    src: str,
    strategy_id: Optional[str] = None,
    side: Optional[str] = None,
    context: Optional[str] = None,
    why_chain: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
    tf_sec: Optional[int] = None,
    bar_close_ts: Optional[int] = None,
    entry_plan: Optional[dict[str, Any]] = None,
    ts_ms: Optional[int] = None,
    rid: Optional[str] = None,
    clock: Optional["Clock"] = None,
) -> None:
    """
        Persist one TRADE_INTENT_REJECTED payload for decision-making rejects.

        Contract:
        - builds a sparse payload and includes only optional fields that were
            actually supplied;
        - appends an event-shaped Message to WAL, but does not publish to the FSM
            bus;
        - keeps caller-provided reason_code/stage/why mostly unchanged, so callers
            remain responsible for schema-safe values;
        - if TRADE_INTENT_REJECT_WAL_MODE is memory/off/disabled, skips the WAL
            append and stores only the private in-process copy.
    """
    if ts_ms is not None:
        ts_ms_final = int(ts_ms)
    else:
        # Prefer the injected clock for deterministic tests/replay paths.
        if clock:
            ts_ms_final = int(clock.now_ms())
        else:
            from apps.reference.core.time.clock import LiveClock
            ts_ms_final = int(LiveClock().now_ms())

    payload: dict[str, Any] = {
        "ts_ms": ts_ms_final,
        "symbol": str(symbol),
        "reason_code": str(reason_code),
        "stage": stage,
        "why": str(why),
    }
    if strategy_id is not None:
        payload["strategy_id"] = str(strategy_id)
    if side is not None:
        # The schema allows only buy/sell. Unknown values are omitted instead of
        # being normalized heuristically into a side.
        side_norm = str(side).lower()
        if side_norm in ("buy", "sell"):
            payload["side"] = side_norm
    if rid is not None:
        payload["rid"] = str(rid)
    if context is not None:
        payload["context"] = str(context)
    if why_chain is not None:
        payload["why_chain"] = [str(x) for x in why_chain if str(x)]
    if details is not None:
        payload["details"] = details
    if tf_sec is not None:
        payload["tf_sec"] = int(tf_sec)
    if bar_close_ts is not None:
        payload["bar_close_ts"] = int(bar_close_ts)
    if entry_plan is not None:
        payload["entry_plan"] = entry_plan

    wal_mode = str(
        os.getenv("TRADE_INTENT_REJECT_WAL_MODE", "wal")).strip().lower()
    if wal_mode in ("memory", "off", "disabled"):
        # Keep only a bounded in-process copy when disk WAL writes are disabled
        # or redirected away from the normal append path.
        _MEMORY_REJECT_LOG.append(payload)
        if len(_MEMORY_REJECT_LOG) > _MEMORY_REJECT_CAP:
            del _MEMORY_REJECT_LOG[: len(
                _MEMORY_REJECT_LOG) - _MEMORY_REJECT_CAP]
        return

    # Append an event-shaped record to WAL for forensics without touching the
    # live event bus. Higher-level emitters handle FSM publication separately.
    msg = Message(
        op="EVT",
        verb="TRADE_INTENT_REJECTED",
        src=str(src),
        dst="any",
        rid=str(rid) if rid is not None else f"rej:{symbol}:{ts_ms_final}",
        ts=ts_ms_final,
        why=truncate_why(f"trade_intent_rejected:{reason_code}"),
        pld=payload,
    )
    res = wal.append(msg.model_dump())
    # wal.append() reports lock-timeout style write failure via None. True
    # exceptions still propagate to the caller, which decides whether reject
    # telemetry must be best-effort or fail the current path.
    if res is None:
        logger.error(
            f"[{symbol}] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID={rid}"
        )
