from __future__ import annotations

import logging
import time
from typing import Any, Literal, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

RejectStage = Literal["RISK", "STRATEGY", "DECISION", "EXECUTION"]

logger = logging.getLogger(__name__)


def write_trade_intent_rejected(
    *,
    symbol: str,
    reason_code: str,
    stage: RejectStage,
    why: str,
    src: str,
    normalize_mode_effective: Optional[str] = None,
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
) -> None:
    """
    OBS-04-INT: Persist a single SSOT reject record to WAL.

    Note: this writes only to WAL (not console logs). Emitting an EVT via FSM is optional
    and should be done by the caller if needed.
    """
    ts_ms_final = int(ts_ms) if ts_ms is not None else int(time.time() * 1000)

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
    if normalize_mode_effective is not None:
        payload["normalize_mode_effective"] = str(normalize_mode_effective)

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
    if res is None:
        logger.error(
            f"[{symbol}] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID={rid}"
        )
