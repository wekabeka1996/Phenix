"""Regression tests for aggregated OCO side canonicalization (OCO-11.13)."""

from __future__ import annotations

import logging
import time
from decimal import Decimal

import pytest
from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.contracts import (
    PositionSide,
    canonicalize_position_side_from_qty,
)
from apps.reference.domains.execution_position.fsm import PositionSnapshot
from tests.domains.execution_position.agg_oco_test_utils import make_execpos


@pytest.fixture
def execpos_aggregated_bnb(monkeypatch: pytest.MonkeyPatch):
    return make_execpos(monkeypatch, symbol="BNBUSDT")


@pytest.fixture
def bnb_long_position_snapshot() -> PositionSnapshot:
    return PositionSnapshot(
        symbol="BNBUSDT",
        side="LONG",
        position_amt=0.25,
        avg_price=550.0,
        updated_ts=time.time(),
    )


def test_canonicalize_position_side_from_qty_contract() -> None:
    assert canonicalize_position_side_from_qty(
        Decimal("1")) is PositionSide.LONG
    assert canonicalize_position_side_from_qty(
        Decimal("-0.01")) is PositionSide.SHORT
    assert canonicalize_position_side_from_qty(
        Decimal("0")) is PositionSide.FLAT


@pytest.mark.integration
def test_agg_oco_no_unsupported_side_warning(
    execpos_aggregated_bnb,
    bnb_long_position_snapshot: PositionSnapshot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fsm = execpos_aggregated_bnb
    symbol = "BNBUSDT"
    manage_flow = fsm.manage_flow(symbol)

    cache_key = fsm._ws_cache_key(symbol, "LONG")
    fsm._ws_position_cache[cache_key] = bnb_long_position_snapshot

    caplog.set_level(logging.INFO, logger="agg_oco")

    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="watchdog",
        dst="execution_position",
        rid="agg_side",
        pld={
            "symbol": symbol,
            "qty": "0.25",
            "side": "buy",  # deliberately lowercase to mimic legacy payloads
            "price": "550",
            "orderId": "rest-fill-bnb",
            "source": "rest_watchdog",
        },
    )

    fsm.handle(msg)

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "Unsupported position side for aggregated OCO: buy" not in logs
    assert "AGG_OCO_COMPUTE_BRACKETS_START" in logs
    assert "AGG_OCO_COMPUTE_BRACKETS_DONE" in logs

    canonical_side = manage_flow._resolve_canonical_position_side()
    assert canonical_side is PositionSide.LONG
