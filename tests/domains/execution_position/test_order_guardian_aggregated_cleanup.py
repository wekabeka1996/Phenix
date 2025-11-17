"""Aggregated cleanup tests for OrderGuardian (OCO-4.2)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.services.order_guardian import (
    AggregatedOcoGuardianConfig,
    OrderGuardian,
)


def _mk_open_order(order_id: int, symbol: str, position_side: str, kind: str):
    """Helper to create a reduce-only bracket-like order payload."""

    closing_side = "SELL" if position_side.upper() == "LONG" else "BUY"
    order_type = "STOP_MARKET" if kind.upper() == "SL" else "TAKE_PROFIT_MARKET"
    return SimpleNamespace(
        order_id=str(order_id),
        order_type=order_type,
        symbol=symbol,
        side=closing_side,
        positionSide=position_side.upper(),
        kind=kind.upper(),
        reduce_only=True,
        close_position=True,
    )


def _mk_guardian_with_cfg(ttl_ms: int, allow_unprotected: bool = False) -> OrderGuardian:
    cfg = AggregatedOcoGuardianConfig(
        enabled=True,
        ttl_protect_new_bracket_ms=ttl_ms,
        allow_unprotected_position=allow_unprotected,
    )
    return OrderGuardian(adapter=None, poll_interval_ms=0, aggregated_oco_cfg=cfg)


def test_ttl_guard_does_not_cancel_fresh_bracket():
    guardian = _mk_guardian_with_cfg(ttl_ms=3000)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    open_orders = [
        _mk_open_order(111, "SOLUSDT", "LONG", "SL"),
        _mk_open_order(222, "SOLUSDT", "LONG", "TP"),
        _mk_open_order(333, "SOLUSDT", "LONG", "SL"),
    ]

    original_cancel = guardian._cancel_order_safe
    spy_cancel = MagicMock(wraps=original_cancel)
    guardian._cancel_order_safe = spy_cancel

    guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        open_orders=open_orders,
        now_ts=now,
    )

    spy_cancel.assert_not_called()


def test_cleanup_extra_brackets_keeps_active_sl_tp():
    guardian = _mk_guardian_with_cfg(ttl_ms=0)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now - 10,
    )

    open_orders = [
        _mk_open_order(111, "SOLUSDT", "LONG", "SL"),
        _mk_open_order(222, "SOLUSDT", "LONG", "TP"),
        _mk_open_order(333, "SOLUSDT", "LONG", "SL"),
    ]

    original_cancel = guardian._cancel_order_safe
    spy_cancel = MagicMock(wraps=original_cancel)
    guardian._cancel_order_safe = spy_cancel

    guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        open_orders=open_orders,
        now_ts=now,
    )

    spy_cancel.assert_called_once()
    cancelled_order = spy_cancel.call_args.args[0]
    assert getattr(cancelled_order, "order_id") == "333"


def test_fail_closed_does_not_remove_last_sl():
    guardian = _mk_guardian_with_cfg(ttl_ms=0, allow_unprotected=False)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="999",  # Active SL not tracked in metadata
        tp_order_id=None,
        created_ts=now - 10,
    )

    open_orders = [_mk_open_order(111, "SOLUSDT", "LONG", "SL")]

    original_cancel = guardian._cancel_order_safe
    spy_cancel = MagicMock(wraps=original_cancel)
    guardian._cancel_order_safe = spy_cancel

    guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        open_orders=open_orders,
        now_ts=now,
    )

    spy_cancel.assert_not_called()


def test_position_zero_clears_bracket_metadata():
    guardian = _mk_guardian_with_cfg(ttl_ms=0)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=0.0,
        open_orders=[],
        now_ts=now,
    )

    assert guardian.get_active_bracket_set("SOLUSDT", "LONG") is None


def test_zero_position_cleanup_cancels_reduce_only_orders():
    guardian = _mk_guardian_with_cfg(ttl_ms=0)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-1",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now,
    )

    open_orders = [
        _mk_open_order(111, "SOLUSDT", "LONG", "SL"),
        _mk_open_order(222, "SOLUSDT", "LONG", "TP"),
    ]

    spy_cancel = MagicMock(return_value=True)
    guardian._cancel_order_safe = spy_cancel

    cancelled = guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=0.0,
        open_orders=open_orders,
        now_ts=now,
    )

    assert cancelled == 2
    assert spy_cancel.call_count == 2
    assert guardian.get_active_bracket_set("SOLUSDT", "LONG") is None


def test_cleanup_prefers_new_meta_after_side_normalization():
    guardian = _mk_guardian_with_cfg(ttl_ms=0)
    now = time.time()

    guardian.register_bracket_set(
        bracket_set_id="agg-old",
        symbol="SOLUSDT",
        side="LONG",
        sl_order_id="111",
        tp_order_id="222",
        created_ts=now - 10,
    )

    # Register a new aggregated set using legacy BUY/SELL side naming
    guardian.register_bracket_set(
        bracket_set_id="agg-new",
        symbol="SOLUSDT",
        side="BUY",
        sl_order_id="333",
        tp_order_id="444",
        created_ts=now,
    )

    open_orders = [
        _mk_open_order(111, "SOLUSDT", "LONG", "SL"),
        _mk_open_order(222, "SOLUSDT", "LONG", "TP"),
        _mk_open_order(333, "SOLUSDT", "LONG", "SL"),
        _mk_open_order(444, "SOLUSDT", "LONG", "TP"),
    ]

    spy_cancel = MagicMock(wraps=guardian._cancel_order_safe)
    guardian._cancel_order_safe = spy_cancel

    guardian.ensure_single_bracket_set_for_position(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        open_orders=open_orders,
        now_ts=now,
    )

    cancelled_ids = {getattr(call.args[0], "order_id")
                     for call in spy_cancel.call_args_list}
    assert cancelled_ids == {"111", "222"}
    active_meta = guardian.get_active_bracket_set("SOLUSDT", "LONG")
    assert active_meta is not None
    assert active_meta.sl_order_id == "333"
    assert guardian.get_active_bracket_set("SOLUSDT", "BUY") is active_meta
