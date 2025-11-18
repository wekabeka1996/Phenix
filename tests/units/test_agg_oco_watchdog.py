from __future__ import annotations

import time

from apps.reference.domains.execution_position.agg_oco_watchdog import (
    AggOcoViolationKind,
    WatchdogOrder,
    WatchdogPosition,
    validate_agg_oco_invariants,
)
from apps.reference.services.order_guardian import BracketSetMeta


def _make_meta(symbol: str = "BTCUSDT", side: str = "LONG", version: int = 0) -> BracketSetMeta:
    return BracketSetMeta(
        bracket_set_id=f"{symbol}-{side}-{version}",
        symbol=symbol,
        side=side,
        sl_order_id="sl-id",
        tp_order_id="tp-id",
        created_ts=time.time(),
        version=version,
    )


def _run_validator(positions, orders, metas):
    return validate_agg_oco_invariants(
        positions=positions,
        open_orders=orders,
        bracket_metas=metas,
        now_ts=time.time(),
    )


def test_watchdog_passes_when_sl_present():
    positions = [WatchdogPosition(symbol="BTCUSDT", side="LONG", quantity=1.0)]
    orders = [
        WatchdogOrder(
            symbol="BTCUSDT",
            side="LONG",
            order_id="1",
            reduce_only=True,
            close_position=False,
            is_sl=True,
        )
    ]
    metas = [_make_meta()]

    result = _run_validator(positions, orders, metas)

    assert result == []


def test_watchdog_flags_missing_sl_for_active_position():
    positions = [WatchdogPosition(symbol="BTCUSDT", side="LONG", quantity=2.0)]
    # reduceOnly order exists but not marked as SL
    orders = [
        WatchdogOrder(
            symbol="BTCUSDT",
            side="LONG",
            order_id="2",
            reduce_only=True,
            close_position=False,
            is_sl=False,
        )
    ]
    metas = [_make_meta()]

    result = _run_validator(positions, orders, metas)

    assert result
    assert any(
        v.kind == AggOcoViolationKind.NO_SL_FOR_OPEN_POSITION for v in result)


def test_watchdog_flags_orphan_sl_when_position_zero():
    positions = []
    orders = [
        WatchdogOrder(
            symbol="ETHUSDT",
            side="SHORT",
            order_id="7",
            reduce_only=True,
            close_position=True,
            is_sl=True,
        )
    ]
    metas = []

    result = _run_validator(positions, orders, metas)

    assert result
    assert any(
        v.kind == AggOcoViolationKind.ORPHAN_SL_FOR_ZERO_POSITION for v in result)


def test_watchdog_flags_multiple_meta_sets_for_same_side():
    positions = [WatchdogPosition(symbol="ARBUSDT", side="LONG", quantity=0.5)]
    orders = [
        WatchdogOrder(
            symbol="ARBUSDT",
            side="LONG",
            order_id="33",
            reduce_only=True,
            close_position=False,
            is_sl=True,
        )
    ]
    metas = [_make_meta(symbol="ARBUSDT", side="LONG", version=0), _make_meta(
        symbol="ARBUSDT", side="LONG", version=1)]

    result = _run_validator(positions, orders, metas)

    assert result
    assert any(
        v.kind == AggOcoViolationKind.MULTIPLE_META_SETS for v in result)


def test_watchdog_accepts_dict_payloads_from_adapter():
    positions = [
        {
            "symbol": "BNBUSDT",
            "positionAmt": "1.5",
            "positionSide": "LONG",
        }
    ]
    orders = [
        {
            "symbol": "BNBUSDT",
            "positionSide": "LONG",
            "orderId": "55",
            "type": "STOP_MARKET",
            "reduceOnly": True,
            "closePosition": False,
            "stopPrice": "540.0",
        }
    ]
    metas = []

    result = _run_validator(positions, orders, metas)

    assert result == []
