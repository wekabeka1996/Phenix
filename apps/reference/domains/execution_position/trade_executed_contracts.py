"""
Canonical helpers for EVT:TRADE_EXECUTED.

The active runtime path co-emits TRADE_EXECUTED from websocket and watchdog
surfaces with execution-local identity fields that PositionTracking does not
own but downstream truth hardening and observability rely on.  This seam
ensures required canonical fields exist before schema validation while
retaining the active identity fields used by runtime consumers.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional


TRADE_EXECUTED_OPTIONAL_KEYS = frozenset(
    {
        "rid",
        "idempotent_key",
        "clientOrderId",
        "client_order_id",
        "exchangeOrderId",
        "orderId",
        "tradeId",
        "trade_id",
        "status",
        "order_type",
        "time_in_force",
        "qty",
        "ts_ms",
        "last_fill_qty",
        "cumulative_qty",
        "commission",
        "commissionAsset",
        "realizedPnl",
        "close_reason",
        "bracket_role",
        "tracked_bracket_order_id",
        "parent_entry_order_id",
        "terminal_correlation_source",
        "correlation_recovered",
    }
)


def _stringify_decimal(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_side(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in {"buy", "sell"} else None


def _resolve_ts(payload: Mapping[str, Any], fallback_ts_ms: Optional[int]) -> int:
    for key in ("ts", "ts_ms", "timestamp", "event_ts_ms"):
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


def _resolve_side_from_order_index(
    payload: Mapping[str, Any],
    order_index: Any,
) -> Optional[str]:
    if order_index is None:
        return None
    try:
        ref = (
            order_index.get(exchangeOrderId=str(payload.get("orderId")))
            if payload.get("orderId") is not None
            else None
        )
        if ref is None and payload.get("exchangeOrderId") is not None:
            ref = order_index.get(exchangeOrderId=str(payload.get("exchangeOrderId")))
        if ref is None and payload.get("clientOrderId") is not None:
            ref = order_index.get(clientOrderId=str(payload.get("clientOrderId")))
        if ref is None and payload.get("client_order_id") is not None:
            ref = order_index.get(clientOrderId=str(payload.get("client_order_id")))
        if ref is None and payload.get("rid") is not None:
            ref = order_index.get(rid=str(payload.get("rid")))
        if ref is None:
            return None
        return _normalize_side(getattr(ref, "side", None))
    except Exception:
        return None


def normalize_trade_executed_payload(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
    fallback_venue: str = "binance",
    order_index: Any = None,
) -> Dict[str, Any]:
    raw = dict(payload or {})
    normalized: Dict[str, Any] = {}

    symbol = _stringify_decimal(raw.get("symbol") or raw.get("instrument"))
    if symbol is not None:
        normalized["symbol"] = symbol

    side = _normalize_side(raw.get("side"))
    if side is None:
        side = _resolve_side_from_order_index(raw, order_index)
    if side is not None:
        normalized["side"] = side

    quantity = (
        _stringify_decimal(raw.get("quantity"))
        or _stringify_decimal(raw.get("qty"))
        or _stringify_decimal(raw.get("last_fill_qty"))
    )
    if quantity is not None:
        normalized["quantity"] = quantity

    price = _stringify_decimal(raw.get("price"))
    if price is not None:
        normalized["price"] = price

    ts = _resolve_ts(raw, fallback_ts_ms)
    normalized["ts"] = ts
    normalized["ts_ms"] = ts

    fees = _stringify_decimal(raw.get("fees") or raw.get("commission"))
    if fees is not None:
        normalized["fees"] = fees

    venue = (
        _stringify_decimal(raw.get("venue"))
        or _stringify_decimal(raw.get("exchange"))
        or fallback_venue
    )
    if venue is not None:
        normalized["venue"] = venue

    if raw.get("rid") is not None or fallback_rid is not None:
        normalized["rid"] = str(raw.get("rid") or fallback_rid)

    for key in TRADE_EXECUTED_OPTIONAL_KEYS:
        if key in raw and raw.get(key) is not None:
            value = raw.get(key)
            if key in {"ts_ms"}:
                try:
                    normalized[key] = int(value)
                except (TypeError, ValueError):
                    normalized[key] = ts
                continue
            if key in {
                "qty",
                "last_fill_qty",
                "cumulative_qty",
                "commission",
                "realizedPnl",
            }:
                normalized[key] = _stringify_decimal(value)
                continue
            if key in {"correlation_recovered"}:
                normalized[key] = bool(value)
                continue
            normalized[key] = value

    if "rid" not in normalized and fallback_rid is not None:
        normalized["rid"] = str(fallback_rid)

    return normalized


__all__ = [
    "TRADE_EXECUTED_OPTIONAL_KEYS",
    "normalize_trade_executed_payload",
]
