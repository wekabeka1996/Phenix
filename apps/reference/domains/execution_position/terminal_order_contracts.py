"""
Canonical normalization helpers for terminal non-fill order events.

Additive-only contract seam hardening for:
- EVT:ORDER_REJECTED
- EVT:ORDER_STATE_CHANGED
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Dict, Mapping, Optional, Tuple

from vfoundation.core.fsm_emit_compat import Message, emit_compat

try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

IDENTITY_EXACT = "order_identity_exact"
IDENTITY_DEGRADED = "order_identity_degraded"
IDENTITY_WEAK = "order_identity_weak"

TERMINAL_NON_FILL_STATUS_MAP = {
    "CANCELED": "CANCELED",
    "CANCELLED": "CANCELED",
    "EXPIRED": "EXPIRED",
    "REJECTED": "REJECTED",
}

REJECT_ORIGIN_CLASS_UNKNOWN = "unknown"
REJECT_ORIGIN_CLASS_EXECUTION_ADAPTER = "execution_adapter"
REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL = "execution_internal"
REJECT_ORIGIN_CLASS_EXCHANGE_WEBSOCKET = "exchange_websocket"
REJECT_ORIGIN_CLASS_DECISION_ALIAS = "decision_alias"

REJECT_ORIGIN_CLASS_ALIASES = {
    "adapter": REJECT_ORIGIN_CLASS_EXECUTION_ADAPTER,
    "execution_adapter": REJECT_ORIGIN_CLASS_EXECUTION_ADAPTER,
    "ep_adapter": REJECT_ORIGIN_CLASS_EXECUTION_ADAPTER,
    "internal": REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL,
    "execution_internal": REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL,
    "ep_internal": REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL,
    "websocket": REJECT_ORIGIN_CLASS_EXCHANGE_WEBSOCKET,
    "exchange_websocket": REJECT_ORIGIN_CLASS_EXCHANGE_WEBSOCKET,
    "ws": REJECT_ORIGIN_CLASS_EXCHANGE_WEBSOCKET,
    "decision": REJECT_ORIGIN_CLASS_DECISION_ALIAS,
    "decision_alias": REJECT_ORIGIN_CLASS_DECISION_ALIAS,
}


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


def _resolve_event_ts_ms(payload: Mapping[str, Any], fallback_ts_ms: Optional[int]) -> int:
    for key in ("event_ts_ms", "ts_ms", "timestamp", "ts"):
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


def normalize_order_reject_reason(payload: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    for key in ("reject_reason_normalized", "reject_reason", "reason"):
        value = _stringify(payload.get(key))
        if value is not None:
            return value.upper(), key

    code = _stringify(payload.get("reason_code"))
    text = _stringify(payload.get("reason_text"))
    if code is not None:
        if text is not None:
            return f"{code.upper()}: {text.upper()}", "reason_code_reason_text"
        return code.upper(), "reason_code"

    return None, None


def normalize_reject_origin_class(payload: Mapping[str, Any]) -> str:
    for key in ("origin_class", "reject_origin_class", "origin", "origin_type"):
        value = _stringify(payload.get(key))
        if value is None:
            continue
        return REJECT_ORIGIN_CLASS_ALIASES.get(value.lower(), REJECT_ORIGIN_CLASS_UNKNOWN)

    reason_code = _stringify(payload.get("reason_code"))
    if reason_code is not None and reason_code.upper() == "ADAPTER_ERROR":
        return REJECT_ORIGIN_CLASS_EXECUTION_ADAPTER

    nrr_code = _stringify(payload.get("nrr_code"))
    if nrr_code is not None:
        return REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL

    details = _stringify(payload.get("details"))
    norm_result = payload.get("norm_result")
    if details is not None or norm_result is not None:
        return REJECT_ORIGIN_CLASS_EXECUTION_INTERNAL

    return REJECT_ORIGIN_CLASS_UNKNOWN


def _identity_quality(
    *,
    order_id: Optional[str],
    client_order_id: Optional[str],
    rid: Optional[str],
) -> str:
    if order_id and client_order_id:
        return IDENTITY_EXACT
    if order_id or client_order_id:
        return IDENTITY_DEGRADED
    if rid:
        return IDENTITY_WEAK
    return IDENTITY_WEAK


def _identity_key(
    *,
    event_name: str,
    symbol: Optional[str],
    order_id: Optional[str],
    client_order_id: Optional[str],
    rid: Optional[str],
    terminal_state_kind: Optional[str],
    reject_reason_normalized: Optional[str] = None,
) -> str:
    parts = [event_name.lower(), f"symbol={symbol or 'unknown'}"]
    if order_id:
        parts.append(f"order_id={order_id}")
    if client_order_id:
        parts.append(f"client_order_id={client_order_id}")
    if not order_id and not client_order_id and rid:
        parts.append(f"rid={rid}")
    if terminal_state_kind:
        parts.append(f"terminal_state={terminal_state_kind}")
    if reject_reason_normalized and not order_id and not client_order_id:
        parts.append(f"reject_reason={reject_reason_normalized}")
    return ":".join(parts)


def normalize_order_rejected_payload(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
) -> Dict[str, Any]:
    normalized = dict(payload)

    symbol = _first_text(normalized, "symbol", "instrument")
    if symbol is not None:
        normalized["symbol"] = symbol

    order_id = _first_text(normalized, "orderId", "order_id", "exchangeOrderId", "exchange_order_id")
    if order_id is not None:
        normalized.setdefault("orderId", order_id)
        normalized.setdefault("order_id", order_id)

    client_order_id = _first_text(normalized, "clientOrderId", "client_order_id", "client_id")
    if client_order_id is not None:
        normalized.setdefault("clientOrderId", client_order_id)
        normalized.setdefault("client_order_id", client_order_id)

    rid = _first_text(normalized, "rid") or _stringify(fallback_rid)
    if rid is not None:
        normalized.setdefault("rid", rid)

    side = _first_text(normalized, "side")
    if side is not None:
        normalized["side"] = side.upper()

    event_ts_ms = _resolve_event_ts_ms(normalized, fallback_ts_ms)
    normalized["event_ts_ms"] = event_ts_ms
    normalized.setdefault("ts_ms", event_ts_ms)

    reject_reason_normalized, reject_reason_source = normalize_order_reject_reason(normalized)
    if reject_reason_normalized is not None:
        normalized["reject_reason_normalized"] = reject_reason_normalized
        normalized["reject_reason_source"] = reject_reason_source
        normalized.setdefault("reject_reason", reject_reason_normalized)
        normalized.setdefault("reason", reject_reason_normalized)

    normalized["origin_class"] = normalize_reject_origin_class(normalized)

    normalized["identity_quality"] = _identity_quality(
        order_id=order_id,
        client_order_id=client_order_id,
        rid=rid,
    )
    normalized["canonical_identity_key"] = _identity_key(
        event_name="EVT:ORDER_REJECTED",
        symbol=symbol,
        order_id=order_id,
        client_order_id=client_order_id,
        rid=rid,
        terminal_state_kind="REJECTED",
        reject_reason_normalized=reject_reason_normalized,
    )
    normalized["terminal_non_fill"] = True
    normalized["terminal_state_kind"] = "REJECTED"
    normalized["compatibility_aliases_retained"] = True

    return normalized


def normalize_order_state_changed_payload(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
) -> Dict[str, Any]:
    normalized = dict(payload)

    symbol = _first_text(normalized, "symbol", "instrument")
    if symbol is not None:
        normalized["symbol"] = symbol

    status = _first_text(normalized, "status", "state")
    status_upper = status.upper() if status is not None else None
    if status_upper is not None:
        normalized["status"] = status_upper

    order_id = _first_text(normalized, "orderId", "order_id", "exchangeOrderId", "exchange_order_id")
    if order_id is not None:
        normalized.setdefault("orderId", order_id)
        normalized.setdefault("order_id", order_id)

    client_order_id = _first_text(normalized, "clientOrderId", "client_order_id", "client_id")
    if client_order_id is not None:
        normalized.setdefault("clientOrderId", client_order_id)
        normalized.setdefault("client_order_id", client_order_id)

    rid = _first_text(normalized, "rid") or _stringify(fallback_rid)
    if rid is not None:
        normalized.setdefault("rid", rid)

    side = _first_text(normalized, "side")
    if side is not None:
        normalized["side"] = side.upper()

    event_ts_ms = _resolve_event_ts_ms(normalized, fallback_ts_ms)
    normalized["event_ts_ms"] = event_ts_ms
    normalized.setdefault("ts_ms", event_ts_ms)

    terminal_state_kind = TERMINAL_NON_FILL_STATUS_MAP.get(status_upper or "")
    normalized["terminal_non_fill"] = terminal_state_kind is not None
    if terminal_state_kind is not None:
        normalized["terminal_state_kind"] = terminal_state_kind

    normalized["identity_quality"] = _identity_quality(
        order_id=order_id,
        client_order_id=client_order_id,
        rid=rid,
    )
    normalized["canonical_identity_key"] = _identity_key(
        event_name="EVT:ORDER_STATE_CHANGED",
        symbol=symbol,
        order_id=order_id,
        client_order_id=client_order_id,
        rid=rid,
        terminal_state_kind=terminal_state_kind or status_upper,
    )
    normalized["compatibility_aliases_retained"] = True

    return normalized


def normalize_terminal_order_event_payload(
    event_name: str,
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
) -> Dict[str, Any]:
    if event_name == "EVT:ORDER_REJECTED":
        return normalize_order_rejected_payload(
            payload,
            fallback_rid=fallback_rid,
            fallback_ts_ms=fallback_ts_ms,
        )
    if event_name == "EVT:ORDER_STATE_CHANGED":
        return normalize_order_state_changed_payload(
            payload,
            fallback_rid=fallback_rid,
            fallback_ts_ms=fallback_ts_ms,
        )
    return dict(payload)


def sync_trade_lifecycle_terminal_order_event(
    event_name: str,
    payload: Mapping[str, Any],
    *,
    logger: Optional[logging.Logger] = None,
) -> None:
    lifecycle = _trade_lifecycle
    if lifecycle is None:
        return

    rid = _first_text(payload, "rid")
    if not rid:
        return

    try:
        if event_name == "EVT:ORDER_REJECTED":
            lifecycle.on_reject(
                rid=rid,
                reject_reason=(
                    _stringify(payload.get("reject_reason_normalized"))
                    or _stringify(payload.get("reason"))
                    or _stringify(payload.get("reason_code"))
                    or "ORDER_REJECTED"
                ),
                reject_reason_code=_stringify(payload.get("reason_code")) or "",
                reject_stage="EXECUTION",
            )
            return

        if event_name != "EVT:ORDER_STATE_CHANGED" or payload.get("terminal_non_fill") is not True:
            return

        terminal_state_kind = (_stringify(payload.get("terminal_state_kind")) or "").upper()
        reason = (
            _stringify(payload.get("reason"))
            or _stringify(payload.get("reject_reason_normalized"))
            or terminal_state_kind
            or "ORDER_STATE_CHANGED"
        )
        if terminal_state_kind == "REJECTED":
            lifecycle.on_reject(
                rid=rid,
                reject_reason=reason,
                reject_reason_code=_stringify(payload.get("reason_code")) or "",
                reject_stage="EXECUTION",
            )
            return

        lifecycle.on_cancel(rid=rid, cancel_reason=reason)
    except Exception as exc:
        if logger is not None:
            logger.warning("trade_lifecycle terminal sync failed for %s: %s", event_name, exc)


async def emit_canonical_terminal_order_event(
    *,
    fsm: Any,
    event_name: str,
    payload: Mapping[str, Any],
    rid: Optional[str],
    src: str,
    dst: str,
    why: str,
    logger: Optional[logging.Logger] = None,
    write_wal: bool = False,
    fallback_ts_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Emit a canonical terminal-order event through the primary bus seam.

    The runtime defect package needs deterministic WAL + local shadow parity on
    selected active terminal paths. Prefer the primary `emit(Message)` seam so
    `FSMCore.emit()` can normalize, validate, and record to the local shadow
    journal in one place. Fall back to `emit_compat()` only when the bus cannot
    accept the Message API directly.
    """

    normalized = normalize_terminal_order_event_payload(
        event_name,
        payload,
        fallback_rid=rid,
        fallback_ts_ms=fallback_ts_ms,
    )
    op, verb = event_name.split(":", 1)
    msg = Message(
        op=op,
        verb=verb,
        src=src,
        dst=dst,
        rid=rid,
        pld=normalized,
        why=why,
    )

    if write_wal:
        try:
            from vfoundation.dr import wal

            wal.append(msg.model_dump())
        except Exception as exc:
            if logger is not None:
                logger.warning("Failed to write %s to WAL: %s", event_name, exc)

    emit = getattr(fsm, "emit", None)
    if emit is not None:
        try:
            result = emit(msg)
            if inspect.isawaitable(result):
                await result
            sync_trade_lifecycle_terminal_order_event(
                event_name,
                normalized,
                logger=logger,
            )
            return normalized
        except TypeError:
            pass
        except Exception as exc:
            if logger is not None:
                logger.debug(
                    "Direct emit(Message) failed for %s, falling back to emit_compat: %r",
                    event_name,
                    exc,
                )

    await emit_compat(fsm, msg, logger=logger)
    sync_trade_lifecycle_terminal_order_event(
        event_name,
        normalized,
        logger=logger,
    )
    return normalized
