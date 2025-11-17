from __future__ import annotations

from apps.reference.services.order_guardian import BracketSetMeta

from tools.agg_oco_snapshot import SnapshotResult, TrackedOrder, build_snapshot


def make_order(
    order_id: str,
    *,
    side: str = "LONG",
    base_id: str | None = "RID1",
    is_sl: bool = False,
    is_tp: bool = False,
) -> TrackedOrder:
    client_id = f"{base_id}{'_sl' if is_sl else '_tp' if is_tp else ''}" if base_id else None
    normalized = {
        "orderId": order_id,
        "clientOrderId": client_id,
        "symbol": "BTCUSDT",
        "side": "SELL" if side == "LONG" else "BUY",
        "positionSide": side,
        "reduceOnly": True,
        "type": "STOP_MARKET" if is_sl else "TAKE_PROFIT_MARKET" if is_tp else "LIMIT",
    }
    return TrackedOrder(
        raw=normalized,
        normalized=normalized,
        order_id=order_id,
        client_order_id=client_id,
        symbol="BTCUSDT",
        side=side,
        is_reduce_only=True,
        is_sl=is_sl,
        is_tp=is_tp,
        base_id=base_id,
        timestamp=1.0,
    )


def test_snapshot_flags_protected_when_sl_present() -> None:
    meta = BracketSetMeta(
        bracket_set_id="RID1",
        symbol="BTCUSDT",
        side="LONG",
        sl_order_id="SL1",
        tp_order_id="TP1",
        created_ts=0.0,
        version=0,
    )
    orders = [
        make_order("SL1", is_sl=True),
        make_order("TP1", is_tp=True),
    ]
    snapshot = build_snapshot(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=1.0,
        avg_entry_price=100.0,
        bracket_meta=meta,
        tracked_orders=orders,
        aggregated_enabled=True,
        extra_group_count=1,
    )
    assert snapshot.invariants["INVARIANT_PROTECTED_IF_OPEN"] is True
    assert snapshot.invariants["INVARIANT_NO_REDUCE_ONLY_IF_FLAT"] is True
    assert snapshot.invariants["HAS_ORPHANS"] is False


def test_snapshot_flags_missing_sl_when_open_position() -> None:
    meta = BracketSetMeta(
        bracket_set_id="RID1",
        symbol="BTCUSDT",
        side="LONG",
        sl_order_id=None,
        tp_order_id="TP1",
        created_ts=0.0,
        version=0,
    )
    orders = [
        make_order("TP1", is_tp=True),
    ]
    snapshot = build_snapshot(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=2.0,
        avg_entry_price=200.0,
        bracket_meta=meta,
        tracked_orders=orders,
        aggregated_enabled=True,
        extra_group_count=1,
    )
    assert snapshot.invariants["INVARIANT_PROTECTED_IF_OPEN"] is False
    assert snapshot.sl_orders == []


def test_snapshot_flags_flat_position_with_reduce_only_orders() -> None:
    orders = [
        make_order("SL1", is_sl=True),
        make_order("TP1", is_tp=True),
    ]
    snapshot = build_snapshot(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=0.0,
        avg_entry_price=None,
        bracket_meta=None,
        tracked_orders=orders,
        aggregated_enabled=True,
        extra_group_count=1,
    )
    assert snapshot.invariants["INVARIANT_NO_REDUCE_ONLY_IF_FLAT"] is False
    assert snapshot.invariants["HAS_ORPHANS"] is True


def test_snapshot_detects_multiple_bracket_groups() -> None:
    orders = [
        make_order("RID1_SL", base_id="RID1", is_sl=True),
        make_order("RID2_SL", base_id="RID2", is_sl=True),
    ]
    snapshot = build_snapshot(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=0.5,
        avg_entry_price=150.0,
        bracket_meta=None,
        tracked_orders=orders,
        aggregated_enabled=True,
        extra_group_count=2,
    )
    assert snapshot.invariants["INVARIANT_SINGLE_SET"] is False
