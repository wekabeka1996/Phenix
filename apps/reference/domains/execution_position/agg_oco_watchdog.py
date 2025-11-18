"""Aggregated OCO watchdog validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from apps.reference.services.order_guardian import BracketSetMeta


class AggOcoViolationKind(str, Enum):
    """Supported aggregated OCO invariant violation types."""

    NO_SL_FOR_OPEN_POSITION = "NO_SL_FOR_OPEN_POSITION"
    ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
    MULTIPLE_META_SETS = "MULTIPLE_META_SETS"


@dataclass(frozen=True)
class AggOcoViolation:
    """Structured violation record for aggregated OCO watchdog."""

    symbol: str
    side: str
    kind: AggOcoViolationKind
    why: str
    details: Dict[str, Any]


# Backward-compatible aliases for legacy imports
WatchdogViolationKind = AggOcoViolationKind
WatchdogViolation = AggOcoViolation


@dataclass(frozen=True)
class AggOcoValidationResult:
    """Legacy helper for callers expecting tuple results."""

    violations: Tuple[AggOcoViolation, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_kind(self) -> Dict[AggOcoViolationKind, List[AggOcoViolation]]:
        grouped: Dict[AggOcoViolationKind, List[AggOcoViolation]] = {}
        for violation in self.violations:
            grouped.setdefault(violation.kind, []).append(violation)
        return grouped


@dataclass(frozen=True)
class WatchdogPosition:
    symbol: str
    side: str
    quantity: float


@dataclass(frozen=True)
class WatchdogOrder:
    symbol: str
    side: str
    order_id: str
    reduce_only: bool
    close_position: bool
    is_sl: bool


def validate_agg_oco_invariants(
    *,
    positions: Sequence[Any],
    open_orders: Sequence[Any],
    bracket_metas: Sequence[BracketSetMeta],
    now_ts: float,
) -> List[AggOcoViolation]:
    """Validate Aggregated OCO invariants and return structured violations."""

    normalized_positions = _normalize_positions(positions)
    normalized_orders = _normalize_orders(open_orders)
    meta_map = _group_metas(bracket_metas)

    positions_map: Dict[Tuple[str, str], WatchdogPosition] = {
        (pos.symbol, pos.side): pos for pos in normalized_positions
    }
    orders_map = _group_orders(normalized_orders)

    observed_keys = set(positions_map.keys()) | set(
        orders_map.keys()) | set(meta_map.keys())
    violations: List[AggOcoViolation] = []

    for key in observed_keys:
        symbol, side = key
        position = positions_map.get(key)
        qty = position.quantity if position else 0.0
        orders_for_key = orders_map.get(key, [])
        metas_for_key = meta_map.get(key, [])
        sl_count = sum(1 for order in orders_for_key if order.is_sl)
        meta_count = len(metas_for_key)

        if qty > 0:
            if sl_count == 0:
                violations.append(
                    AggOcoViolation(
                        symbol=symbol,
                        side=side,
                        kind=AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION,
                        why="no_sl_for_open_position",
                        details={
                            "position_amt": qty,
                            "sl_count": sl_count,
                            "meta_count": meta_count,
                            "ts": now_ts,
                        },
                    )
                )
            if meta_count > 1:
                violations.append(
                    AggOcoViolation(
                        symbol=symbol,
                        side=side,
                        kind=AggOcoViolationKind.MULTIPLE_META_SETS,
                        why="multiple_meta_sets",
                        details={
                            "position_amt": qty,
                            "sl_count": sl_count,
                            "meta_count": meta_count,
                            "ts": now_ts,
                        },
                    )
                )
        else:
            if orders_for_key:
                violations.append(
                    AggOcoViolation(
                        symbol=symbol,
                        side=side,
                        kind=AggOcoViolationKind.ORPHAN_SL_FOR_ZERO_POSITION,
                        why="orphan_sl_for_zero_position",
                        details={
                            "position_amt": qty,
                            "sl_count": sl_count,
                            "meta_count": meta_count,
                            "orders": len(orders_for_key),
                            "ts": now_ts,
                        },
                    )
                )

    return violations


def validate_agg_oco_invariants_result(
    *,
    positions: Sequence[Any],
    open_orders: Sequence[Any],
    bracket_metas: Sequence[BracketSetMeta],
    now_ts: float,
) -> AggOcoValidationResult:
    """Legacy helper returning AggOcoValidationResult for existing call sites."""

    return AggOcoValidationResult(
        violations=tuple(
            validate_agg_oco_invariants(
                positions=positions,
                open_orders=open_orders,
                bracket_metas=bracket_metas,
                now_ts=now_ts,
            )
        )
    )


def _normalize_positions(raw_positions: Sequence[Any]) -> List[WatchdogPosition]:
    normalized: List[WatchdogPosition] = []
    for raw in raw_positions or []:
        mapping = _as_mapping(raw)
        if not mapping:
            continue
        symbol = _normalize_symbol(mapping.get("symbol"))
        if not symbol:
            continue
        amt = _extract_float(
            mapping,
            (
                "positionAmt",
                "position_amount",
                "position_amt",
                "qty",
                "quantity",
            ),
        )
        if amt is None:
            continue
        side = _resolve_position_side(mapping.get(
            "positionSide") or mapping.get("position_side"), amt)
        if not side:
            continue
        quantity = abs(amt)
        if quantity <= 0:
            continue
        normalized.append(WatchdogPosition(
            symbol=symbol, side=side, quantity=quantity))
    return normalized


def _normalize_orders(raw_orders: Sequence[Any]) -> List[WatchdogOrder]:
    normalized: List[WatchdogOrder] = []
    for raw in raw_orders or []:
        mapping = _as_mapping(raw)
        if not mapping:
            continue
        reduce_only = _boolish(mapping.get("reduceOnly")
                               or mapping.get("reduce_only"))
        close_position = _boolish(mapping.get(
            "closePosition") or mapping.get("close_position"))
        if not (reduce_only or close_position):
            continue
        symbol = _normalize_symbol(mapping.get("symbol"))
        if not symbol:
            continue
        side = _resolve_order_side(mapping)
        if not side:
            continue
        order_id_raw = mapping.get("orderId") or mapping.get("order_id")
        if not order_id_raw:
            continue
        order_id = str(order_id_raw)
        order = WatchdogOrder(
            symbol=symbol,
            side=side,
            order_id=order_id,
            reduce_only=reduce_only,
            close_position=close_position,
            is_sl=_is_sl_order(mapping),
        )
        normalized.append(order)
    return normalized


def _group_orders(orders: Iterable[WatchdogOrder]) -> Dict[Tuple[str, str], List[WatchdogOrder]]:
    grouped: Dict[Tuple[str, str], List[WatchdogOrder]] = {}
    for order in orders:
        grouped.setdefault((order.symbol, order.side), []).append(order)
    return grouped


def _group_metas(metas: Sequence[BracketSetMeta]) -> Dict[Tuple[str, str], List[BracketSetMeta]]:
    grouped: Dict[Tuple[str, str], List[BracketSetMeta]] = {}
    for meta in metas or []:
        symbol = _normalize_symbol(getattr(meta, "symbol", None))
        side = _normalize_symbol(getattr(meta, "side", None))
        if not symbol or not side:
            continue
        grouped.setdefault((symbol, side), []).append(meta)
    return grouped


def normalize_positions_for_watchdog(raw_positions: Sequence[Any]) -> List[WatchdogPosition]:
    """Public helper exposing normalization logic for ExecPosFSM state assembly."""

    return _normalize_positions(raw_positions)


def normalize_orders_for_watchdog(raw_orders: Sequence[Any]) -> List[WatchdogOrder]:
    """Public helper exposing normalization logic for ExecPosFSM state assembly."""

    return _normalize_orders(raw_orders)


def _normalize_symbol(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _extract_float(mapping: Dict[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        if key not in mapping:
            continue
        raw_value = mapping.get(key)
        if raw_value is None:
            continue
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue
    return None


def _resolve_position_side(side_hint: Any, quantity: float) -> Optional[str]:
    if isinstance(side_hint, str):
        candidate = side_hint.strip().upper()
        if candidate in {"LONG", "SHORT"}:
            return candidate
        if candidate == "BUY":
            return "LONG"
        if candidate == "SELL":
            return "SHORT"
    if quantity > 0:
        return "LONG"
    if quantity < 0:
        return "SHORT"
    return None


def _resolve_order_side(mapping: Dict[str, Any]) -> Optional[str]:
    side_hint = mapping.get("positionSide") or mapping.get("position_side")
    if isinstance(side_hint, str):
        candidate = side_hint.strip().upper()
        if candidate in {"LONG", "SHORT"}:
            return candidate
    side_value = mapping.get("side")
    if isinstance(side_value, str):
        candidate = side_value.strip().upper()
        if candidate in {"LONG", "SHORT"}:
            return candidate
        if candidate == "SELL":
            return "LONG"
        if candidate == "BUY":
            return "SHORT"
    return None


def _is_sl_order(mapping: Dict[str, Any]) -> bool:
    explicit_flag = mapping.get("is_sl")
    if isinstance(explicit_flag, bool):
        if explicit_flag:
            return True
    elif isinstance(explicit_flag, str):
        if explicit_flag.strip().lower() in {"1", "true", "yes", "on", "sl"}:
            return True
    order_type = str(
        mapping.get("type")
        or mapping.get("origType")
        or mapping.get("kind")
        or ""
    ).upper()
    working_type = str(mapping.get("workingType") or "").upper()
    client_order_id = str(mapping.get("clientOrderId") or "").lower()
    stop_price = mapping.get("stopPrice") or mapping.get("activatePrice")
    if "STOP" in order_type or working_type.startswith("STOP"):
        return True
    if client_order_id.endswith("_sl"):
        return True
    if stop_price is not None:
        try:
            if abs(float(stop_price)) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _boolish(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)


def _as_mapping(obj: Any) -> Optional[Dict[str, Any]]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            dumped = obj.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(obj, "to_dict"):
        try:
            dumped = obj.to_dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return dict(obj.__dict__)
        except Exception:
            return None
    return None
