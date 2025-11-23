import asyncio

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.close_flow import CloseDecision
from apps.reference.domains.execution_position.shadow_execpos.trailing import TrailingDecision, TrailingState
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


class FakeAdapter:
    def __init__(self):
        self.close_calls = []

    async def close_position(self, symbol, quantity):
        self.close_calls.append({"symbol": symbol, "quantity": quantity})
        return {"success": True, "order_id": "CLOSE-1"}

    async def place_order(self, *args, **kwargs):
        # Treat reduce_only place as close intent for logging purposes
        if kwargs.get("reduce_only"):
            self.close_calls.append({"symbol": kwargs.get("symbol"), "quantity": kwargs.get("quantity")})
        return {"success": True, "order_id": "ENTRY-1"}

    async def cancel_order(self, *args, **kwargs):
        return {"success": True}


def make_runtime():
    config = {}
    adapter = FakeAdapter()
    runtime = ExecPosRuntimeV2(config=config, adapter=adapter, price_service=None)
    return runtime, adapter


@pytest.mark.asyncio
async def test_runtime_updates_position_state_with_position_model():
    runtime, _ = make_runtime()
    event = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": {"side": "BUY", "quantity": 1, "price": 100.0, "order_id": "o1"},
    }
    await runtime.handle(event)

    # Scale-in
    event_si = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "payload": {"side": "BUY", "quantity": 1, "price": 200.0, "order_id": "o2"},
    }
    await runtime.handle(event_si)

    pos = runtime._positions_by_symbol["BTCUSDT"]
    assert isinstance(pos, PositionState)
    assert pytest.approx(pos.qty) == 2.0
    assert pytest.approx(pos.avg_entry_price) == 150.0


@pytest.mark.asyncio
async def test_runtime_close_intent_uses_close_flow_service():
    runtime, adapter = make_runtime()
    # Seed position
    runtime._positions_by_symbol["ETHUSDT"] = PositionState(symbol="ETHUSDT", qty=2.0, avg_entry_price=100)

    # Spy close_flow_service
    calls = {}

    def fake_plan_close(position, ctx, cfg):
        calls["position_qty"] = position.qty
        calls["reason"] = ctx.reason
        return CloseDecision(action="CLOSE_FULL", target_qty=2.0, reason_code="MANUAL_CLOSE", why="test", timestamp=0)

    runtime.close_flow_service.plan_close = fake_plan_close

    await runtime.handle({"kind": "CLOSE_INTENT", "symbol": "ETHUSDT", "payload": {"reason": "MANUAL"}})

    assert calls["position_qty"] == 2.0
    assert calls["reason"].upper() == "MANUAL"
    # Adapter called with full qty
    assert adapter.close_calls and adapter.close_calls[0]["quantity"] == 2.0


@pytest.mark.asyncio
async def test_runtime_trailing_eval_invoked_on_trade():
    runtime, _ = make_runtime()
    # Seed position to avoid FLAT path
    runtime._positions_by_symbol["SOLUSDT"] = PositionState(symbol="SOLUSDT", qty=1.0, avg_entry_price=10.0)

    trail_called = {}

    def fake_eval_trailing(position, price, trail_state, cfg, now=None):
        trail_called["position_qty"] = position.qty
        trail_called["price"] = price
        return TrailingDecision(
            sl_price=9.5,
            trail_state=TrailingState(status="ACTIVE", sl_price=9.5),
            reason_code="TRAIL_ACTIVE",
            why="test",
            exit=False,
            timestamp=now or 0,
        )

    runtime.trailing_service.eval_trailing = fake_eval_trailing

    event = {
        "kind": "TRADE_EXECUTED",
        "symbol": "SOLUSDT",
        "payload": {"side": "BUY", "quantity": 0.5, "price": 11.0, "order_id": "o10"},
    }
    await runtime.handle(event)

    assert trail_called["position_qty"] == 1.0 + 0.5
    assert trail_called["price"] == 11.0
    assert runtime._metrics["trailing_evaluations"] == 1
