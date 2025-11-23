import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketAction, BracketPlan, BracketState


def make_plan(actions, severity="ALERT", why="test"):
    dummy_state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,
        bracket_set=None,
        guardian_meta=None,
        snapshot_ts=0,
    )
    return BracketPlan(symbol="BTCUSDT", side="LONG", state=dummy_state, actions=actions, severity=severity, why=why)


@pytest.mark.asyncio
async def test_apply_bracket_plan_initial_entry_places_sl_tp_and_registers_guardian():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=AsyncMock())
    runtime.execution_service = AsyncMock()
    runtime.execution_service.place_order = AsyncMock(return_value={"order_id": "o1", "client_order_id": "c1"})
    runtime.execution_service.cancel_order = AsyncMock(return_value={})

    actions = [
        BracketAction(action_type="PLACE_SL", price=Decimal("9.5"), qty=Decimal("100"), reason_code="MISSING_SL"),
        BracketAction(action_type="PLACE_TP", price=Decimal("12"), qty=Decimal("100"), reason_code="TP"),
    ]
    plan = make_plan(actions)
    position = PositionState(symbol="BTCUSDT", qty=100.0, avg_entry_price=10.0)

    await runtime._apply_bracket_plan("BTCUSDT", position, plan, reason="initial_entry")

    assert runtime.execution_service.place_order.await_count == 2
    call_kwargs = runtime.execution_service.place_order.await_args_list[0].kwargs
    assert call_kwargs["reduce_only"] is True
    assert call_kwargs["side"] == "SELL"
    assert call_kwargs["order_type"] == "STOP_MARKET"

    runtime.guardian.register_bracket_set.assert_awaited_once()
    args, kwargs = runtime.guardian.register_bracket_set.await_args
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["side"] == "LONG"
    assert len(kwargs["orders"]) == 2


@pytest.mark.asyncio
async def test_apply_bracket_plan_scale_in_cancels_and_replaces():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=AsyncMock())
    runtime.execution_service = AsyncMock()
    runtime.execution_service.place_order = AsyncMock(return_value={"order_id": "new_sl"})
    runtime.execution_service.cancel_order = AsyncMock(return_value={})

    actions = [
        BracketAction(action_type="CANCEL", order_id="old_sl"),
        BracketAction(action_type="CANCEL", order_id="old_tp"),
        BracketAction(action_type="PLACE_SL", price=Decimal("9.0"), qty=Decimal("150"), reason_code="TOO_MANY_SL"),
        BracketAction(action_type="PLACE_TP", price=Decimal("13.0"), qty=Decimal("150"), reason_code="TP"),
    ]
    plan = make_plan(actions)
    position = PositionState(symbol="BTCUSDT", qty=150.0, avg_entry_price=10.0)

    await runtime._apply_bracket_plan("BTCUSDT", position, plan, reason="scale_in")

    runtime.execution_service.cancel_order.assert_any_await(symbol="BTCUSDT", order_id="old_sl", client_order_id=None)
    runtime.execution_service.cancel_order.assert_any_await(symbol="BTCUSDT", order_id="old_tp", client_order_id=None)
    assert runtime.execution_service.place_order.await_count == 2
    runtime.guardian.register_bracket_set.assert_awaited_once()
    assert runtime.guardian.clear_bracket_set.await_count == 0


@pytest.mark.asyncio
async def test_apply_bracket_plan_cleanup_clears_guardian():
    guardian = AsyncMock()
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=guardian)
    runtime.execution_service = AsyncMock()
    runtime.execution_service.cancel_order = AsyncMock(return_value={})

    actions = [BracketAction(action_type="CANCEL", order_id="orphan")]
    plan = make_plan(actions, severity="WARN")
    position = PositionState(symbol="BTCUSDT", qty=0.0, avg_entry_price=0.0)

    await runtime._apply_bracket_plan("BTCUSDT", position, plan, reason="full_close")

    runtime.execution_service.cancel_order.assert_awaited_once()
    guardian.clear_bracket_set.assert_awaited_once_with(symbol="BTCUSDT", side="FLAT" if hasattr(position, "side") else "LONG")

