"""
Canonical helpers for EVT:TRADE_INTENT_REJECTED.

This seam hardening exists for the execution-boundary reject path, where a
legacy top-level ``reason`` field previously broke schema validation and
dropped reject truth before observability/lifecycle closure.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, Mapping, Optional

from apps.reference.shared.types import (
    TRADE_INTENT_REJECTED_CANONICAL_KEYS,
    build_trade_intent_rejected_message,
    normalize_trade_intent_rejected_payload,
    stringify_trade_intent_rejected_value,
)
from vfoundation.core.fsm_emit_compat import resolve_emit_compat_mode
from vfoundation.dr import wal


def _write_trade_intent_rejected_wal(
    *,
    payload: Mapping[str, Any],
    src: str,
    rid: Optional[str],
    logger: Optional[logging.Logger] = None,
) -> None:
    msg = build_trade_intent_rejected_message(payload, src=src, rid=rid)
    symbol = stringify_trade_intent_rejected_value(msg.pld.get("symbol")) or "unknown"
    res = wal.append(msg.model_dump())
    if res is None and logger is not None:
        logger.error("[%s] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID=%s", symbol, rid)


def _supports_positional_arg(emit: Any, index: int) -> bool:
    try:
        sig = inspect.signature(emit)
    except (TypeError, ValueError):
        return False
    positional = [
        param
        for param in sig.parameters.values()
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) > index


def _supports_named_arg(emit: Any, name: str) -> bool:
    try:
        sig = inspect.signature(emit)
    except (TypeError, ValueError):
        return False
    if name in sig.parameters:
        return True
    return any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    )


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

    wal_message = build_trade_intent_rejected_message(
        normalized,
        src=src,
        rid=rid,
    )
    msg_rid = stringify_trade_intent_rejected_value(wal_message.rid)

    emit = getattr(fsm, "emit", None)
    if emit is None:
        raise RuntimeError(f"FSM has no emit() for TRADE_INTENT_REJECTED (fsm={type(fsm)!r})")

    mode = resolve_emit_compat_mode(fsm, emit=emit, logger=logger)
    if mode == "message":
        emit_msg = build_trade_intent_rejected_message(
            normalized,
            src=src,
            rid=rid,
            dst=dst,
        )
        try:
            emit_msg.data_ref = list(data_ref or [])
        except Exception:
            pass
        emit(emit_msg)
    elif mode == "op_verb_payload_why":
        emit_payload = dict(normalized)
        if msg_rid and "rid" not in emit_payload:
            emit_payload["rid"] = msg_rid
        args: list[Any] = ["EVT", "TRADE_INTENT_REJECTED", emit_payload, why]
        if _supports_positional_arg(emit, 4):
            args.append(list(data_ref or []))
        emit(*args)
    elif mode == "op_payload_why":
        args = ["EVT:TRADE_INTENT_REJECTED", normalized, why]
        if _supports_positional_arg(emit, 3):
            args.append(list(data_ref or []))
        emit_kwargs: dict[str, Any] = {}
        if msg_rid and _supports_named_arg(emit, "rid"):
            emit_kwargs["rid"] = msg_rid
        emit(*args, **emit_kwargs)
    else:
        if logger is not None:
            logger.error(
                "TRADE_INTENT_REJECTED emit skipped: unresolved emit contract on %r",
                fsm,
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
                reject_reason=stringify_trade_intent_rejected_value(normalized.get("why")) or stringify_trade_intent_rejected_value(normalized.get("reason_code")) or why,
                reject_reason_code=stringify_trade_intent_rejected_value(normalized.get("reason_code")) or "",
                reject_stage=stringify_trade_intent_rejected_value(normalized.get("stage")) or "",
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
