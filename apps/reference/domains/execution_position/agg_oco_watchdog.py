"""Aggregated OCO watchdog validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from apps.reference.services.order_guardian import BracketSetMeta
# EP-STAB-SL-CLASS-FIX: Import unified classifier
from apps.reference.domains.execution_position.contracts import (
    classify_exit_order,
    ExitOrderKind,
)


class AggOcoViolationKind(str, Enum):
    """Supported aggregated OCO invariant violation types."""

    NO_SL_FOR_OPEN_POSITION = "NO_SL_FOR_OPEN_POSITION"
    ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
    MULTIPLE_META_SETS = "MULTIPLE_META_SETS"
    TOO_MANY_SL_FOR_OPEN_POSITION = "TOO_MANY_SL_FOR_OPEN_POSITION"


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
    is_sl: bool  # Deprecated: use exit_kind instead
    # EP-STAB-SL-CLASS-FIX-B: Unified exit classification
    exit_kind: Optional[ExitOrderKind] = None

    @property
    def is_flat_close(self) -> bool:
        """True if this is a position close without SL/TP context."""
        return self.exit_kind == ExitOrderKind.FLAT_CLOSE

    @property
    def is_take_profit(self) -> bool:
        """True if this is a TP bracket."""
        return self.exit_kind == ExitOrderKind.TAKE_PROFIT


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
        # EP-STAB-SL-CLASS-FIX-B: Use unified classifier, count STOP_LOSS only
        sl_count = sum(
            1 for order in orders_for_key if order.exit_kind == ExitOrderKind.STOP_LOSS)
        tp_count = sum(
            1 for order in orders_for_key if order.exit_kind == ExitOrderKind.TAKE_PROFIT)
        flat_close_count = sum(
            1 for order in orders_for_key if order.exit_kind == ExitOrderKind.FLAT_CLOSE)
        meta_count = len(metas_for_key)

        if qty > 0:
            # EP-STAB-SL-CLASS-FIX-B: NO_SL_FOR_OPEN_POSITION should NOT trigger if FLAT_CLOSE is active
            # (position is being explicitly closed without SL/TP bracket context)
            has_flat_close_exit = flat_close_count > 0

            if sl_count == 0 and not has_flat_close_exit:
                violations.append(
                    AggOcoViolation(
                        symbol=symbol,
                        side=side,
                        kind=AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION,
                        why="no_sl_for_open_position",
                        details={
                            "position_amt": qty,
                            "sl_count": sl_count,
                            "tp_count": tp_count,
                            "flat_close_count": flat_close_count,
                            "meta_count": meta_count,
                            "ts": now_ts,
                        },
                    )
                )
            if sl_count > 1:
                violations.append(
                    AggOcoViolation(
                        symbol=symbol,
                        side=side,
                        kind=AggOcoViolationKind.TOO_MANY_SL_FOR_OPEN_POSITION,
                        why="too_many_sl_for_open_position",
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
    """
    Normalize positions using PositionSnapshot for unified parsing.

    Handles both raw REST payloads and pre-normalized WatchdogPosition objects
    (useful for tests and internal calls).

    **Refs**: EP-STAB-POS-SNAPSHOT
    """
    from apps.reference.domains.execution_position.contracts import PositionSnapshot

    normalized: List[WatchdogPosition] = []
    rest_payloads = []

    # Separate pre-normalized WatchdogPosition objects from raw payloads
    for raw in raw_positions or []:
        if isinstance(raw, WatchdogPosition):
            # Already normalized, pass through
            normalized.append(raw)
        else:
            # Raw payload, collect for PositionSnapshot processing
            rest_payloads.append(raw)

    # Process raw payloads via PositionSnapshot
    if rest_payloads:
        # Extract unique symbols
        symbols = set()
        for raw in rest_payloads:
            mapping = _as_mapping(raw)
            if mapping and mapping.get("symbol"):
                symbols.add(str(mapping.get("symbol")))

        # Use PositionSnapshot for each symbol
        for symbol in symbols:
            try:
                snapshot = PositionSnapshot.from_rest_list(
                    list(rest_payloads), symbol)
                if snapshot:
                    normalized.append(WatchdogPosition(
                        symbol=snapshot.symbol,
                        side=snapshot.side.value,  # LONG or SHORT
                        quantity=float(snapshot.qty)
                    ))
            except Exception:
                continue

    return normalized


def _normalize_orders(raw_orders: Sequence[Any]) -> List[WatchdogOrder]:
    """
    EP-STAB-ADAPT-ORD-META-WIRE: Normalize open orders for watchdog invariant checks.

    Uses unified classify_exit_order() to identify EXIT orders (STOP_LOSS, TAKE_PROFIT, FLAT_CLOSE).
    Only tracks exit orders; ENTRY orders (classify_exit_order returns None) are skipped.

    If raw_order is already a WatchdogOrder (pre-normalized), passes through if exit_kind is set.
    If raw_order is a dict/mapping, classifies via classify_exit_order.
    """
    normalized: List[WatchdogOrder] = []
    for raw in raw_orders or []:
        # Handle pre-normalized WatchdogOrder objects (from tests or internal calls)
        if isinstance(raw, WatchdogOrder):
            # Already a WatchdogOrder: include if exit_kind is set or if it has legacy is_sl flag
            if raw.exit_kind is not None or raw.is_sl:
                normalized.append(raw)
            continue

        mapping = _as_mapping(raw)
        if not mapping:
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

        # EP-STAB-ADAPT-ORD-META-WIRE: Use unified classifier as filter
        # Only include orders that are classified as EXIT (non-None exit_kind)
        exit_kind = classify_exit_order(mapping)
        if exit_kind is None:
            continue  # Skip ENTRY orders; watchdog only tracks exit/close orders

        reduce_only = _boolish(mapping.get("reduceOnly")
                               or mapping.get("reduce_only"))
        close_position = _boolish(mapping.get(
            "closePosition") or mapping.get("close_position"))

        order = WatchdogOrder(
            symbol=symbol,
            side=side,
            order_id=order_id,
            reduce_only=reduce_only,
            close_position=close_position,
            is_sl=_is_sl_order(mapping),  # For backward compatibility
            exit_kind=exit_kind,
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
    # EP-STAB-SL-CLASS-FIX: Delegate to unified classifier
    return classify_exit_order(mapping) == ExitOrderKind.STOP_LOSS


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
