"""Unit tests for aggregated OCO invariant validator (OCO-11.4)."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Dict, List

from apps.reference.domains.execution_position.agg_oco_watchdog import (
    AggOcoViolationKind,
    validate_agg_oco_invariants,
)
from apps.reference.services.order_guardian import BracketSetMeta


def _position(symbol: str, side: str, qty: Decimal) -> Dict[str, object]:
    return {
        "symbol": symbol,
        "positionSide": side,
        "positionAmt": str(qty),
    }


def _reduce_only_order(symbol: str, side: str) -> Dict[str, object]:
    return {
        "symbol": symbol,
        "positionSide": side,
        "orderId": f"{symbol}-{side}-sl",
        "type": "STOP_MARKET",
        "reduceOnly": True,
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "stopPrice": "123.45",
    }


def _meta(symbol: str, side: str, suffix: str = "0") -> BracketSetMeta:
    try:
        version = int(suffix)
    except ValueError:
        version = 0
    return BracketSetMeta(
        bracket_set_id=f"{symbol}-{side}-{suffix}",
        symbol=symbol,
        side=side,
        sl_order_id=f"sl-{suffix}",
        tp_order_id=f"tp-{suffix}",
        created_ts=time.time(),
        version=version,
    )


def _run_validator(positions: List[Dict[str, object]], orders: List[Dict[str, object]], metas: List[BracketSetMeta]):
    return validate_agg_oco_invariants(
        positions=positions,
        open_orders=orders,
        bracket_metas=metas,
        now_ts=time.time(),
    )


def test_invariants_ok_for_open_position_with_single_sl_and_meta() -> None:
    positions = [_position("BTCUSDT", "LONG", Decimal("1"))]
    orders = [_reduce_only_order("BTCUSDT", "LONG")]
    metas = [_meta("BTCUSDT", "LONG", "a")]

    result = _run_validator(positions, orders, metas)

    assert result == []


def test_no_sl_for_open_position_detected_as_violation() -> None:
    positions = [_position("BTCUSDT", "LONG", Decimal("1.5"))]
    orders: List[Dict[str, object]] = []
    metas = [_meta("BTCUSDT", "LONG", "v1")]

    result = _run_validator(positions, orders, metas)

    assert any(
        v.kind == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION for v in result)
    assert all(v.symbol == "BTCUSDT" for v in result)


def test_orphan_sl_for_zero_position_detected_as_violation() -> None:
    positions = [_position("ETHUSDT", "LONG", Decimal("0"))]
    orders = [_reduce_only_order("ETHUSDT", "LONG")]
    metas: List[BracketSetMeta] = []

    result = _run_validator(positions, orders, metas)

    assert any(
        v.kind == AggOcoViolationKind.ORPHAN_SL_FOR_ZERO_POSITION for v in result)
    assert all(v.side == "LONG" for v in result)


def test_multiple_meta_sets_detected_as_violation() -> None:
    positions = [_position("SOLUSDT", "LONG", Decimal("0.4"))]
    orders = [_reduce_only_order("SOLUSDT", "LONG")]
    metas = [
        _meta("SOLUSDT", "LONG", "0"),
        _meta("SOLUSDT", "LONG", "1"),
    ]

    result = _run_validator(positions, orders, metas)

    assert any(v.kind == AggOcoViolationKind.MULTIPLE_META_SETS for v in result)
    assert not any(
        v.kind == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION for v in result)
