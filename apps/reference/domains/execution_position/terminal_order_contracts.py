"""
Canonical normalization helpers for terminal non-fill order events.

Additive-only contract seam hardening for:
- EVT:ORDER_REJECTED
- EVT:ORDER_STATE_CHANGED
"""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional, Tuple

IDENTITY_EXACT = "order_identity_exact"
IDENTITY_DEGRADED = "order_identity_degraded"
IDENTITY_WEAK = "order_identity_weak"

TERMINAL_NON_FILL_STATUS_MAP = {
    "CANCELED": "CANCELED",
    "CANCELLED": "CANCELED",
    "EXPIRED": "EXPIRED",
    "REJECTED": "REJECTED",
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
