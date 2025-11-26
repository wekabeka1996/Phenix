from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _extract_ts(order: Dict[str, Any]) -> float:
    for key in ("updateTime", "time", "ts", "timestamp", "created_ts", "update_ts"):
        raw = order.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _order_id_key(order_id: str) -> float:
    try:
        return float(order_id)
    except (TypeError, ValueError):
        return 0.0


def _is_sl(order: Dict[str, Any]) -> bool:
    order_type = str(order.get("type") or order.get("order_type") or "").upper()
    client_id = str(order.get("clientOrderId") or order.get("client_order_id") or "").upper()
    if "STOP" in order_type:
        return True
    return "-SL-" in client_id or client_id.endswith("_SL") or client_id.endswith("-SL")


def _is_tp(order: Dict[str, Any]) -> bool:
    order_type = str(order.get("type") or order.get("order_type") or "").upper()
    client_id = str(order.get("clientOrderId") or order.get("client_order_id") or "").upper()
    if "TAKE_PROFIT" in order_type or "PROFIT" in order_type:
        return True
    return "-TP-" in client_id or client_id.endswith("_TP") or client_id.endswith("-TP")


@dataclass
class NormalizedOrder:
    order_id: str
    client_order_id: str
    qty: Decimal
    side: str
    order_type: str
    is_sl: bool
    is_tp: bool
    update_ts: float
    raw: Dict[str, Any]


@dataclass
class AggOcoReplayState:
    symbol: str
    side: str
    position_qty: Decimal = Decimal("0")
    sl_order: Optional[NormalizedOrder] = None
    tp_order: Optional[NormalizedOrder] = None
    orphans: List[NormalizedOrder] = field(default_factory=list)


class AggOcoReplayEnforcer:
    """
    Lightweight invariant enforcer for replay streams.

    Ensures:
    - at most one SL and one TP per (symbol, side);
    - combined SL/TP qty never exceeds current position size;
    - stale/duplicate orders are pushed to orphans.
    """

    def __init__(self) -> None:
        self._states: Dict[Tuple[str, str], AggOcoReplayState] = {}

    def apply_frame(self, frame: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Normalize a replay frame, enforce invariants, and return a repaired copy.
        """
        symbol = str(frame.get("symbol", "")).upper()
        side = str(frame.get("side", "")).upper()
        key = (symbol, side)
        state = self._states.get(key) or AggOcoReplayState(symbol=symbol, side=side)

        position_qty = _to_decimal(frame.get("position_qty", 0))
        norm_orders = self._normalize_orders(frame.get("orders", []), symbol=symbol, side=side)

        sl_orders = [o for o in norm_orders if o.is_sl]
        tp_orders = [o for o in norm_orders if o.is_tp]

        sl_primary, sl_orphans = self._pick_primary(sl_orders)
        tp_primary, tp_orphans = self._pick_primary(tp_orders)

        violations: List[str] = []
        if len(sl_orders) > 1:
            violations.append(f"dedup_sl:{len(sl_orders)}")
        if len(tp_orders) > 1:
            violations.append(f"dedup_tp:{len(tp_orders)}")

        ordered_priority = [
            o for o in sorted(
                [o for o in (sl_primary, tp_primary) if o],
                key=lambda ord: (ord.update_ts, _order_id_key(ord.order_id)),
                reverse=True,
            )
        ]

        clean_orders: List[Dict[str, Any]] = []
        orphans: List[NormalizedOrder] = sl_orphans + tp_orphans

        if position_qty <= 0:
            if sl_primary:
                orphans.append(sl_primary)
            if tp_primary:
                orphans.append(tp_primary)
        else:
            remaining = position_qty
            for order in ordered_priority:
                allowed = min(order.qty, remaining)
                if allowed <= 0:
                    orphans.append(order)
                    continue
                if allowed < order.qty:
                    violations.append(f"clamp_qty:{order.order_id}:{order.qty}->{allowed}")
                repaired = dict(order.raw)
                repaired["qty"] = float(allowed)
                clean_orders.append(repaired)
                remaining -= allowed

        state.position_qty = position_qty
        state.sl_order = sl_primary if position_qty > 0 else None
        state.tp_order = tp_primary if position_qty > 0 else None
        state.orphans = orphans
        self._states[key] = state

        repaired_frame = dict(frame)
        repaired_frame["orders"] = clean_orders
        if orphans:
            repaired_frame["orphan_orders"] = [o.raw for o in orphans]

        return repaired_frame, violations

    def _normalize_orders(self, orders: List[Dict[str, Any]], symbol: str, side: str) -> List[NormalizedOrder]:
        normalized: List[NormalizedOrder] = []
        for raw in orders:
            try:
                oid = raw.get("orderId") or raw.get("order_id") or raw.get("clientOrderId")
                if not oid:
                    continue
                client_oid = str(raw.get("clientOrderId") or raw.get("client_order_id") or oid)
                order_type = str(raw.get("type") or raw.get("order_type") or "").upper()
                qty = _to_decimal(raw.get("qty") or raw.get("quantity") or raw.get("origQty") or 0)
                order_side = str(raw.get("side") or "").upper() or ("SELL" if side == "LONG" else "BUY")
                normalized.append(
                    NormalizedOrder(
                        order_id=str(oid),
                        client_order_id=client_oid,
                        qty=qty,
                        side=order_side,
                        order_type=order_type,
                        is_sl=_is_sl(raw),
                        is_tp=_is_tp(raw),
                        update_ts=_extract_ts(raw),
                        raw=dict(raw),
                    )
                )
            except Exception:
                continue
        return normalized

    def _pick_primary(self, orders: List[NormalizedOrder]) -> Tuple[Optional[NormalizedOrder], List[NormalizedOrder]]:
        if not orders:
            return None, []
        ordered = sorted(
            orders,
            key=lambda ord: (ord.update_ts, _order_id_key(ord.order_id)),
            reverse=True,
        )
        primary = ordered[0]
        return primary, ordered[1:]
