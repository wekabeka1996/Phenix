"""
Canonical helpers for EVT:TRADE_INTENT_REJECTED.

This seam hardening exists for the execution-boundary reject path, where a
legacy top-level ``reason`` field previously broke schema validation and
dropped reject truth before observability/lifecycle closure.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

TRADE_INTENT_REJECTED_CANONICAL_KEYS = frozenset(
    {
        "ts_ms",
        "symbol",
        "tf_sec",
        "bar_close_ts",
        "reason_code",
        "strategy_id",
        "side",
        "rid",
        "stage",
        "why",
        "context",
        "why_chain",
        "details",
        "entry_plan",
    }
)

_ALLOWED_STAGES = {"RISK", "STRATEGY", "DECISION", "EXECUTION"}


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_text(payload: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = _stringify(payload.get(key))
        if value is not None:
            return value
    return None


def _resolve_ts_ms(payload: Mapping[str, Any], fallback_ts_ms: Optional[int]) -> int:
    for key in ("ts_ms", "timestamp", "ts", "bar_close_ts"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    if fallback_ts_ms is not None:
        return int(fallback_ts_ms)
    return int(time.time() * 1000)


def _normalize_side(value: Any) -> Optional[str]:
    text = _stringify(value)
    if text is None:
        return None
    side = text.lower()
    return side if side in {"buy", "sell"} else None


def _write_trade_intent_rejected_wal(
    *,
    payload: Mapping[str, Any],
    src: str,
    rid: Optional[str],
    logger: Optional[logging.Logger] = None,
) -> None:
    symbol = _stringify(payload.get("symbol")) or "unknown"
    reason_code = _stringify(payload.get("reason_code")) or "UNKNOWN"
    ts_ms = int(payload.get("ts_ms") or int(time.time() * 1000))
    msg = Message(
        op="EVT",
        verb="TRADE_INTENT_REJECTED",
        src=src,
        dst="any",
        rid=rid or f"rej:{symbol}:{ts_ms}",
        ts=ts_ms,
        why=truncate_why(f"trade_intent_rejected:{reason_code}"),
        pld=dict(payload),
    )
    res = wal.append(msg.model_dump())
    if res is None and logger is not None:
        logger.error("[%s] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID=%s", symbol, rid)


def normalize_trade_intent_rejected_payload(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
    fallback_symbol: Optional[str] = None,
    fallback_reason_code: Optional[str] = None,
    fallback_stage: Optional[str] = None,
    fallback_why: Optional[str] = None,
) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    raw = dict(payload or {})

    normalized["ts_ms"] = _resolve_ts_ms(raw, fallback_ts_ms)

    symbol = _first_text(raw, "symbol", "instrument") or _stringify(fallback_symbol)
    if symbol is not None:
        normalized["symbol"] = symbol

    tf_sec = raw.get("tf_sec")
    if tf_sec is not None:
        try:
            normalized["tf_sec"] = int(tf_sec)
        except (TypeError, ValueError):
            pass

    bar_close_ts = raw.get("bar_close_ts")
    if bar_close_ts is not None:
        try:
            normalized["bar_close_ts"] = int(bar_close_ts)
        except (TypeError, ValueError):
            pass

    reason_code = _first_text(raw, "reason_code") or _stringify(fallback_reason_code)
    if reason_code is not None:
        normalized["reason_code"] = reason_code

    strategy_id = _first_text(raw, "strategy_id")
    if strategy_id is not None:
        normalized["strategy_id"] = strategy_id

    side = _normalize_side(raw.get("side"))
    if side is not None:
        normalized["side"] = side

    rid = _first_text(raw, "rid") or _stringify(fallback_rid)
    if rid is not None:
        normalized["rid"] = rid

    stage = _first_text(raw, "stage")
    stage_upper = stage.upper() if stage is not None else None
    if stage_upper not in _ALLOWED_STAGES:
        fallback_stage_text = _stringify(fallback_stage)
        stage_upper = fallback_stage_text.upper() if fallback_stage_text is not None else None
    if stage_upper in _ALLOWED_STAGES:
        normalized["stage"] = stage_upper

    why = _first_text(raw, "why", "reason") or _stringify(fallback_why)
    if why is not None:
        normalized["why"] = why[:240]

    context = _first_text(raw, "context")
    if context is not None:
        normalized["context"] = context

    why_chain = raw.get("why_chain")
    if isinstance(why_chain, (list, tuple)):
        normalized["why_chain"] = [str(item) for item in why_chain if _stringify(item)]

    details = raw.get("details")
    if isinstance(details, dict):
        normalized["details"] = dict(details)

    entry_plan = raw.get("entry_plan")
    if isinstance(entry_plan, dict):
        normalized["entry_plan"] = dict(entry_plan)

    legacy_top_level_keys = sorted(
        key
        for key in raw.keys()
        if key not in TRADE_INTENT_REJECTED_CANONICAL_KEYS and key != "instrument"
    )
    if legacy_top_level_keys:
        compat_details = dict(normalized.get("details") or {})
        compat_details.setdefault("compat_dropped_top_level_keys", legacy_top_level_keys)
        normalized["details"] = compat_details

    return normalized


def emit_canonical_trade_intent_rejected_event(
    *,
    fsm: Any,
    payload: Mapping[str, Any],
    rid: Optional[str],
    src: str,
    dst: str = "*",
    why: str,
    logger: Optional[logging.Logger] = None,
    lifecycle: Any = None,
    write_wal: bool = False,
    fallback_ts_ms: Optional[int] = None,
    fallback_symbol: Optional[str] = None,
    fallback_reason_code: Optional[str] = None,
    fallback_stage: Optional[str] = "EXECUTION",
    fallback_why: Optional[str] = None,
    data_ref: Optional[list[str]] = None,
) -> Dict[str, Any]:
    normalized = normalize_trade_intent_rejected_payload(
        payload,
        fallback_rid=rid,
        fallback_ts_ms=fallback_ts_ms,
        fallback_symbol=fallback_symbol,
        fallback_reason_code=fallback_reason_code,
        fallback_stage=fallback_stage,
        fallback_why=fallback_why,
    )

    msg_rid = _stringify(normalized.get("rid")) or _stringify(rid)

    emit = getattr(fsm, "emit", None)
    if emit is None:
        raise RuntimeError(f"FSM has no emit() for TRADE_INTENT_REJECTED (fsm={type(fsm)!r})")

    try:
        emit(
            "EVT:TRADE_INTENT_REJECTED",
            normalized,
            why,
            data_ref or [],
            rid=msg_rid,
        )
    except TypeError:
        emit(
            "EVT:TRADE_INTENT_REJECTED",
            normalized,
            why,
            data_ref or [],
        )

    if write_wal:
        try:
            _write_trade_intent_rejected_wal(
                payload=normalized,
                src=src,
                rid=msg_rid,
                logger=logger,
            )
        except Exception as exc:
            if logger is not None:
                logger.warning("trade_intent_rejected WAL write failed: %s", exc)

    if lifecycle is not None and msg_rid:
        try:
            lifecycle.on_reject(
                rid=msg_rid,
                reject_reason=_stringify(normalized.get("why")) or _stringify(normalized.get("reason_code")) or why,
                reject_reason_code=_stringify(normalized.get("reason_code")) or "",
                reject_stage=_stringify(normalized.get("stage")) or "",
            )
        except Exception as exc:
            if logger is not None:
                logger.warning("trade_lifecycle.on_reject failed: %s", exc)

    return normalized


__all__ = [
    "TRADE_INTENT_REJECTED_CANONICAL_KEYS",
    "emit_canonical_trade_intent_rejected_event",
    "normalize_trade_intent_rejected_payload",
]
