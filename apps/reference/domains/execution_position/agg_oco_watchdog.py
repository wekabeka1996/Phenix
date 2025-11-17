"""Aggregated OCO watchdog validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from apps.reference.services.order_guardian import BracketSetMeta


class WatchdogViolationKind(str, Enum):
    """Supported invariant violation types."""

    NO_SL_FOR_OPEN_POSITION = "NO_SL_FOR_OPEN_POSITION"
    ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
    MULTIPLE_META_SETS = "MULTIPLE_META_SETS"
    STALE_META_FOR_ZERO_POSITION = "STALE_META_FOR_ZERO_POSITION"


@dataclass(frozen=True)
class WatchdogViolation:
    """Single watchdog violation record."""

    symbol: str
    side: str
    kind: WatchdogViolationKind
    details: str


@dataclass(frozen=True)
class AggOcoValidationResult:
    """Result of aggregated OCO invariant validation."""

    violations: Tuple[WatchdogViolation, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_kind(self) -> Dict[WatchdogViolationKind, List[WatchdogViolation]]:
        grouped: Dict[WatchdogViolationKind, List[WatchdogViolation]] = {}
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
) -> AggOcoValidationResult:
    """Validate Aggregated OCO invariants for provided state snapshots."""

    del now_ts  # Reserved for future TTL-sensitive checks

    normalized_positions = _normalize_positions(positions)
    normalized_orders = _normalize_orders(open_orders)
    meta_map = _group_metas(bracket_metas)

    positions_map: Dict[Tuple[str, str], WatchdogPosition] = {
        (pos.symbol, pos.side): pos for pos in normalized_positions
    }
    orders_map = _group_orders(normalized_orders)

    violations: List[WatchdogViolation] = []

    for key, position in positions_map.items():
        orders_for_key = orders_map.get(key, [])
        metas_for_key = meta_map.get(key, [])
        if position.quantity > 0 and not any(order.is_sl for order in orders_for_key):
            violations.append(
                WatchdogViolation(
                    symbol=position.symbol,
                    side=position.side,
                    kind=WatchdogViolationKind.NO_SL_FOR_OPEN_POSITION,
                    details=f"orders={len(orders_for_key)}",
                )
            )
        if len(metas_for_key) > 1:
            violations.append(
                WatchdogViolation(
                    symbol=position.symbol,
                    side=position.side,
                    kind=WatchdogViolationKind.MULTIPLE_META_SETS,
                    details=f"meta_count={len(metas_for_key)}",
                )
            )

    for key, orders_for_key in orders_map.items():
        if key in positions_map:
            continue
        if not orders_for_key:
            continue
        violations.append(
            WatchdogViolation(
                symbol=key[0],
                side=key[1],
                kind=WatchdogViolationKind.ORPHAN_SL_FOR_ZERO_POSITION,
                details=f"orders={len(orders_for_key)}",
            )
        )

    for key, metas in meta_map.items():
        if key in positions_map:
            continue
        if not metas:
            continue
        violations.append(
            WatchdogViolation(
                symbol=key[0],
                side=key[1],
                kind=WatchdogViolationKind.STALE_META_FOR_ZERO_POSITION,
                details=f"meta_count={len(metas)}",
            )
        )

    return AggOcoValidationResult(violations=tuple(violations))


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
