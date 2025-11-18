"""Unit tests for ExecPosFSM DEC:PLACE_ORDER execution."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from vfoundation.core.protocol import Message

import apps.reference.domains.execution_position.fsm as execpos_mod


class RecordingAdapter:
    """Minimal adapter stub that records bracket placement calls."""

    def __init__(self) -> None:
        self.base_url = "https://testnet.binancefuture.com"
        self.calls: List[Dict[str, Any]] = []

    async def place_stop_market_close_position(
        self,
        symbol: str,
        side: str,
        stop_price: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
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
        return {
            "orderId": "sl-1",
            "clientOrderId": new_client_order_id or "cid-sl",
        }

    async def place_limit_reduce_only(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        position_side: str | None = None,
        new_client_order_id: str | None = None,
    ) -> Dict[str, Any]:
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
        return {
            "orderId": "tp-1",
            "clientOrderId": new_client_order_id or "cid-tp",
        }

    async def place_take_profit_market_close_position(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:  # pragma: no cover - not used in current tests
        self.calls.append({"kind": "TAKE_PROFIT_MARKET",
                          "args": args, "kwargs": kwargs})
        return {"orderId": "tp-2", "clientOrderId": kwargs.get("new_client_order_id", "cid-tp-mkt")}


@pytest.fixture
def execpos_with_adapter(monkeypatch: pytest.MonkeyPatch) -> execpos_mod.ExecPosFSM:
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_guardian_start", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_fsm_cleanup_loop", lambda self: None)
    fsm = execpos_mod.ExecPosFSM(config={}, fsm=None)
    fsm.adapter = RecordingAdapter()
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(execpos_mod.asyncio, "get_running_loop", lambda: loop)
    return fsm


@pytest.mark.asyncio
async def test_place_order_stop_invokes_adapter(execpos_with_adapter: execpos_mod.ExecPosFSM) -> None:
    msg = Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="manage",
        dst="execution_position",
        rid="agg-stop",
        pld={
            "symbol": "BTCUSDT",
            "order_type": "STOP_MARKET",
            "side": "SELL",
            "qty": "0.001",
            "stopPrice": "9000",
            "reduceOnly": True,
            "newClientOrderId": "rid_sl",
        },
    )

    await execpos_with_adapter._execute_decision(msg)

    assert execpos_with_adapter.adapter.calls == [
        {
            "kind": "STOP_MARKET",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "stop_price": "9000",
            "position_side": None,
            "client_order_id": "rid_sl",
        }
    ]


@pytest.mark.asyncio
async def test_place_order_invalid_type_fail_closed(
    execpos_with_adapter: execpos_mod.ExecPosFSM, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING", logger=execpos_mod.__name__)
    msg = Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="manage",
        dst="execution_position",
        rid="agg-unknown",
        pld={
            "symbol": "BTCUSDT",
            "order_type": "UNKNOWN",
            "side": "SELL",
            "qty": "0.001",
            "reduceOnly": True,
            "newClientOrderId": "rid_x",
        },
    )

    await execpos_with_adapter._execute_decision(msg)

    assert execpos_with_adapter.adapter.calls == []
    reasons = [record.reason for record in caplog.records if record.message ==
               "DECISION_EXECUTION_FAILED"]
    assert "agg_place_order_invalid_type" in reasons
