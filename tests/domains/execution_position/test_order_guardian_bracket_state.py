"""Unit tests for OrderGuardian aggregated bracket state (OCO-4.1)."""

from __future__ import annotations

import time
from types import SimpleNamespace

from apps.reference.services.order_guardian import (
    AggregatedOcoGuardianConfig,
    BracketSetMeta,
    OrderGuardian,
)


def _mk_guardian() -> OrderGuardian:
    """Create a minimal guardian instance for state tests."""

    return OrderGuardian(adapter=None, poll_interval_ms=0)


def _mk_guardian_with_agg() -> OrderGuardian:
    cfg = AggregatedOcoGuardianConfig(enabled=True)
    return OrderGuardian(
        adapter=None,
        poll_interval_ms=0,
        aggregated_oco_cfg=cfg,
    )


def _mk_guardian_order(
    *,
    order_id: str,
    client_id: str,
    position_side: str,
    order_type: str,
    ts: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        orderId=order_id,
        clientOrderId=client_id,
        symbol="SOLUSDT",
        positionSide=position_side,
        type=order_type,
        reduceOnly=True,
        closePosition=True,
        time=int(ts * 1000),
    )


def test_register_and_get_bracket_set():
    guardian = _mk_guardian()
    now = time.time()

    meta = guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    assert isinstance(meta, BracketSetMeta)
    assert meta.bracket_set_id == "agg-1"
    assert meta.version == 0

    active = guardian.get_active_bracket_set("SOLUSDT", "LONG")
    assert active is not None
    assert active.bracket_set_id == "agg-1"
    assert active.sl_order_id == "111"
    assert active.tp_order_id == "222"


def test_register_bracket_set_increments_version_on_update():
    guardian = _mk_guardian()
    now = time.time()

    first = guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )
    second = guardian.register_bracket_set(
        bracket_set_id="agg-2",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="333",
        tp_order_id="444",
        created_ts=now + 1,
    )

    assert first.version == 0
    assert second.version == 1

    active = guardian.get_active_bracket_set("SOLUSDT", "LONG")
    assert active is not None
    assert active.bracket_set_id == "agg-2"
    assert active.sl_order_id == "333"
    assert active.tp_order_id == "444"


def test_clear_bracket_set_for_position_removes_state():
    guardian = _mk_guardian()
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    assert guardian.get_active_bracket_set("SOLUSDT", "LONG") is not None

    guardian.clear_bracket_set_for_position(symbol="SOLUSDT", side="LONG")

    assert guardian.get_active_bracket_set("SOLUSDT", "LONG") is None


def test_list_all_bracket_sets_returns_all_positions():
    guardian = _mk_guardian()
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )
    guardian.register_bracket_set(
        bracket_set_id="agg-2",
        symbol="BTCUSDT",
        side="SHORT",
        sl_order_id="333",
        tp_order_id="444",
        created_ts=now,
    )

    all_meta = guardian.list_all_bracket_sets()
    keys = {(m.symbol, m.side) for m in all_meta}

    assert ("SOLUSDT", "LONG") in keys
    assert ("BTCUSDT", "SHORT") in keys
    assert len(all_meta) == 2


def test_rehydrate_bracket_set_registers_latest_pair():
    guardian = _mk_guardian_with_agg()
    now = time.time()

    open_orders = [
        _mk_guardian_order(
            order_id="101",
            client_id="RID-old_169000_sl",
            position_side="LONG",
            order_type="STOP_MARKET",
            ts=now - 5,
        ),
        _mk_guardian_order(
            order_id="102",
            client_id="RID-old_169000_tp",
            position_side="LONG",
            order_type="TAKE_PROFIT_MARKET",
            ts=now - 5,
        ),
        _mk_guardian_order(
            order_id="201",
            client_id="RID-new_170000_sl",
            position_side="LONG",
            order_type="STOP_MARKET",
            ts=now,
        ),
        _mk_guardian_order(
            order_id="202",
            client_id="RID-new_170000_tp",
            position_side="LONG",
            order_type="TAKE_PROFIT_MARKET",
            ts=now,
        ),
    ]

    meta = guardian.rehydrate_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.25,
        open_orders=open_orders,
        now_ts=now,
    )

    assert meta is not None
    assert meta.sl_order_id == "201"
    assert meta.tp_order_id == "202"
    assert meta.bracket_set_id.startswith("RID-new_170000")

    active = guardian.get_active_bracket_set("SOLUSDT", "LONG")
    assert active is not None
    assert active.bracket_set_id == meta.bracket_set_id


def test_register_bracket_set_normalizes_buy_sell_side():
    guardian = _mk_guardian_with_agg()
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-legacy",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    updated = guardian.register_bracket_set(
        bracket_set_id="agg-new",
        symbol="SOLUSDT",
        side="BUY",  # legacy ManageFlow used BUY/SELL — should be normalized to LONG/SHORT
        sl_order_id="333",
        tp_order_id="444",
        created_ts=now + 5,
    )

    assert updated.side == "LONG"
    active_long = guardian.get_active_bracket_set("SOLUSDT", "LONG")
    assert active_long is updated
    # Backwards-compat: querying with BUY also returns the canonical meta.
    active_buy = guardian.get_active_bracket_set("SOLUSDT", "BUY")
    assert active_buy is updated
