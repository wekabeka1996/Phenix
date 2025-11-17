"""Integration smoke test for aggregated OCO DR restart (TASK OCO-6.1)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.services.order_guardian import (
    AggregatedOcoGuardianConfig,
    OrderGuardian,
)


def _mk_guardian() -> OrderGuardian:
    cfg = AggregatedOcoGuardianConfig(
        enabled=True,
        ttl_protect_new_bracket_ms=0,
        allow_unprotected_position=False,
    )
    return OrderGuardian(adapter=None, poll_interval_ms=0, aggregated_oco_cfg=cfg)


def _mk_bracket_order(
    *,
    order_id: str,
    client_id: str,
    symbol: str,
    position_side: str,
    order_type: str,
    ts: float,
):
    return SimpleNamespace(
        orderId=order_id,
        clientOrderId=client_id,
        symbol=symbol,
        positionSide=position_side,
        type=order_type,
        reduceOnly=True,
        closePosition=True,
        time=int(ts * 1000),
    )


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
def test_aggregated_oco_dr_restart_preserves_sl_cleanup_guard():
    """Ensure rehydrated bracket metadata survives follow-up cleanup after restart."""

    guardian = _mk_guardian()

    symbol = "SOLUSDT"
    side = "LONG"
    position_amt = 1.5
    bootstrap_ts = time.time()

    open_orders = [
        _mk_bracket_order(
            order_id="201",
            client_id="RID-bootstrap_170000_sl",
            symbol=symbol,
            position_side=side,
            order_type="STOP_MARKET",
            ts=bootstrap_ts,
        ),
        _mk_bracket_order(
            order_id="202",
            client_id="RID-bootstrap_170000_tp",
            symbol=symbol,
            position_side=side,
            order_type="TAKE_PROFIT_MARKET",
            ts=bootstrap_ts,
        ),
    ]

    meta = guardian.rehydrate_bracket_set_for_position(
        symbol=symbol,
        side=side,
        position_amt=position_amt,
        open_orders=open_orders,
        now_ts=bootstrap_ts,
    )

    assert meta is not None
    assert meta.sl_order_id == "201"
    assert meta.tp_order_id == "202"

    spy_cancel = MagicMock(wraps=guardian._cancel_order_safe)
    guardian._cancel_order_safe = spy_cancel

    guardian.ensure_single_bracket_set_for_position(
        symbol=symbol,
        side=side,
        position_amt=position_amt,
        open_orders=open_orders,
        now_ts=bootstrap_ts + 5,
    )

    active = guardian.get_active_bracket_set(symbol, side)
    assert active is not None
    assert active.bracket_set_id == meta.bracket_set_id

    spy_cancel.assert_not_called()
