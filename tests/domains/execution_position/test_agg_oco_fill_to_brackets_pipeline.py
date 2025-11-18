"""Integration tests for aggregated OCO fill → brackets pipeline (OCO-11.13)."""

from __future__ import annotations

import logging
import time
import types
from decimal import Decimal
from typing import Any, Dict, List

import pytest
from vfoundation.core.protocol import Message

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.domains.execution_position.fsm import PositionSnapshot
from tests.domains.execution_position.agg_oco_test_utils import make_execpos


class RecordingBracketAdapter:
    """Adapter stub that records aggregated bracket placements."""

    def __init__(self) -> None:
        self.base_url = "https://testnet.binancefuture.com"
        self.calls: List[Dict[str, Any]] = []
        self._seq = 0

    def _next_order_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
        order_id = self._next_order_id("sl")
        self.calls.append(
            {
                "kind": "STOP_MARKET",
                "symbol": symbol,
                "side": side,
                "stop_price": stop_price,
                "position_side": position_side,
                "client_order_id": new_client_order_id,
            }
        )
        return {"orderId": order_id, "clientOrderId": new_client_order_id or order_id}

    async def place_take_profit_market_close_position(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:  # pragma: no cover - not used in this runtime test
        order_id = self._next_order_id("tp-mkt")
        self.calls.append({"kind": "TAKE_PROFIT_MARKET",
                          "args": args, "kwargs": kwargs})
        return {"orderId": order_id, "clientOrderId": kwargs.get("new_client_order_id", order_id)}

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
        order_id = self._next_order_id("tp")
        self.calls.append(
            {
                "kind": "LIMIT",
                "symbol": symbol,
                "side": side,
                "price": price,
                "qty": quantity,
                "position_side": position_side,
                "client_order_id": new_client_order_id,
            }
        )
        return {"orderId": order_id, "clientOrderId": new_client_order_id or order_id}


@pytest.fixture
def execpos_aggregated_sol(monkeypatch: pytest.MonkeyPatch) -> execpos_mod.ExecPosFSM:
    return make_execpos(monkeypatch, symbol="SOLUSDT")


@pytest.fixture
def sol_long_position_snapshot() -> PositionSnapshot:
    return PositionSnapshot(
        symbol="SOLUSDT",
        side="LONG",
        position_amt=1.0,
        avg_price=130.0,
        updated_ts=time.time(),
    )


@pytest.mark.integration
def test_fill_triggers_agg_oco_brackets_pipeline(
    execpos_aggregated_sol: execpos_mod.ExecPosFSM,
    sol_long_position_snapshot: PositionSnapshot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Watchdog-delivered fills must drive ManageFlow aggregated bracket placement."""

    fsm = execpos_aggregated_sol
    symbol = "SOLUSDT"
    manage_flow = fsm.manage_flow(symbol)

    original_place_fn = manage_flow._place_brackets_aggregated
    call_counter = {"count": 0}

    def _spy(self, *args, **kwargs):  # type: ignore[override]
        call_counter["count"] += 1
        return original_place_fn(*args, **kwargs)

    manage_flow._place_brackets_aggregated = types.MethodType(  # type: ignore[assignment]
        _spy, manage_flow
    )

    cache_key = fsm._ws_cache_key(symbol, "LONG")
    fsm._ws_position_cache[cache_key] = sol_long_position_snapshot

    caplog.set_level(logging.INFO, logger="agg_oco")
    caplog.set_level(logging.INFO, logger=execpos_mod.__name__)

    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="watchdog",
        dst="execution_position",
        rid="agg_pipeline",
        pld={
            "symbol": symbol,
            "qty": "1.0",
            "side": "BUY",
            "price": "130.0",
            "orderId": "rest-fill",
            "source": "rest_watchdog",
        },
    )

    decision = fsm.handle(msg)

    logs = "\n".join(record.getMessage() for record in caplog.records)
    # Entry fills only emit compute logs; AGG_OCO_HANDLE_FILL appears on later recalc flows.
    assert "AGG_OCO_COMPUTE_BRACKETS_START" in logs
    assert "AGG_OCO_COMPUTE_BRACKETS_DONE" in logs
    assert "AGG_OCO_COMPUTE_FAILED" not in logs
    assert call_counter["count"] >= 1, "ManageFlow must compute aggregated brackets"

    assert decision is not None, "ManageFlow should emit DEC:PLACE_ORDER for aggregated brackets"
    assert decision.verb == "PLACE_ORDER"
    assert decision.op == "DEC"
    assert decision.pld.get("symbol") == symbol
    assert decision.pld.get("reduceOnly") is True


@pytest.mark.asyncio
async def test_execpos_executes_manageflow_bracket_decisions_runtime(
    execpos_aggregated_sol: execpos_mod.ExecPosFSM,
    sol_long_position_snapshot: PositionSnapshot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure ExecPosFSM routes aggregated DEC:PLACE_ORDER through adapter."""

    symbol = "SOLUSDT"
    fsm = execpos_aggregated_sol
    fsm.shadow_mode = False
    adapter = RecordingBracketAdapter()
    fsm.adapter = adapter

    manage_flow = fsm.manage_flow(symbol)
    emitted: List[Message] = []
    original_emit = manage_flow._emit_place_order

    def _recording_emit(self, *args, **kwargs):  # type: ignore[override]
        msg = original_emit(*args, **kwargs)
        emitted.append(msg)
        return msg

    manage_flow._emit_place_order = types.MethodType(
        _recording_emit, manage_flow)

    cache_key = fsm._ws_cache_key(symbol, "LONG")
    fsm._ws_position_cache[cache_key] = sol_long_position_snapshot

    caplog.set_level(logging.INFO, logger="agg_oco")

    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="watchdog",
        dst="execution_position",
        rid="agg-runtime",
        pld={
            "symbol": symbol,
            "qty": "1.0",
            "side": "BUY",
            "price": "130.0",
            "orderId": "rest-fill",
            "source": "rest_watchdog",
        },
    )

    decision = fsm.handle(msg)
    assert decision is not None and decision.verb == "PLACE_ORDER"
    assert len(emitted) == 2, "ManageFlow must emit both SL and TP decisions"

    for dec in emitted:
        await fsm._execute_decision(dec)

    assert [call["kind"] for call in adapter.calls] == ["STOP_MARKET", "LIMIT"]
    assert any(record.message ==
               "AGG_OCO_BRACKETS_PLACED" for record in caplog.records)
    assert manage_flow.sl_order_id is not None
    assert manage_flow.tp_order_id is not None
