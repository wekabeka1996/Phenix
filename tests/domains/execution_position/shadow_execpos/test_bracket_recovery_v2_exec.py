import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketAction, BracketPlan, BracketState


def make_plan(symbol: str, side: str, actions, severity="ALERT", why="recovery"):
    state = BracketState(
        symbol=symbol,
        side=side,
        position_view=None,
        bracket_set=None,
        guardian_meta=None,
        snapshot_ts=0,
    )
    return BracketPlan(symbol=symbol, side=side, state=state, actions=actions, severity=severity, why=why)


@pytest.mark.asyncio
async def test_recovery_orphan_cleanup_calls_apply_once():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=None)
    runtime.bracket_service = MagicMock()
    plan = make_plan("BTCUSDT", "LONG", [BracketAction(action_type="CANCEL", order_id="orph")], severity="WARN")
    runtime.bracket_service.evaluate_all_for_recovery = MagicMock(return_value=[plan])
    runtime._apply_bracket_plan = AsyncMock()
    runtime._open_orders_by_symbol = {"BTCUSDT": [{"symbol": "BTCUSDT", "orderId": "orph", "type": "STOP_MARKET", "side": "SELL", "reduceOnly": True}]}

    await runtime._run_bracket_recovery_pass()

    runtime.bracket_service.evaluate_all_for_recovery.assert_called_once()
    runtime._apply_bracket_plan.assert_awaited_once_with("BTCUSDT", PositionState(symbol="BTCUSDT"), plan, reason="brackets_recovery_orphan_cleanup")
    assert runtime._recovery_completed is True


@pytest.mark.asyncio
async def test_recovery_seed_protection_places_missing_sl():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=None)
    runtime.bracket_service = MagicMock()
    actions = [BracketAction(action_type="PLACE_SL", price=Decimal("95"), qty=Decimal("100"), reason_code="MISSING_SL")]
    plan = make_plan("ETHUSDT", "LONG", actions, severity="ALERT")
    runtime.bracket_service.evaluate_all_for_recovery = MagicMock(return_value=[plan])
    runtime._apply_bracket_plan = AsyncMock()
    runtime._positions_by_symbol = {"ETHUSDT": PositionState(symbol="ETHUSDT", qty=100.0, avg_entry_price=100.0)}
    runtime._open_orders_by_symbol = {}

    await runtime._run_bracket_recovery_pass()

    runtime._apply_bracket_plan.assert_awaited_once()
    assert runtime._apply_bracket_plan.await_args.kwargs["reason"] == "brackets_recovery_seed_protection"


@pytest.mark.asyncio
async def test_recovery_adjust_mismatch():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=None)
    runtime.bracket_service = MagicMock()
    actions = [BracketAction(action_type="ADJUST", order_id="old_tp", price=Decimal("120"), qty=Decimal("50"), reason_code="STALE_LEVELS")]
    plan = make_plan("SOLUSDT", "LONG", actions, severity="WARN")
    runtime.bracket_service.evaluate_all_for_recovery = MagicMock(return_value=[plan])
    runtime._apply_bracket_plan = AsyncMock()
    runtime._positions_by_symbol = {"SOLUSDT": PositionState(symbol="SOLUSDT", qty=50.0, avg_entry_price=100.0)}
    runtime._open_orders_by_symbol = {"SOLUSDT": [{"symbol": "SOLUSDT", "orderId": "old_tp", "type": "TAKE_PROFIT_MARKET", "side": "SELL", "reduceOnly": True}]}

    await runtime._run_bracket_recovery_pass()

    runtime._apply_bracket_plan.assert_awaited_once()
    assert runtime._apply_bracket_plan.await_args.kwargs["reason"] == "brackets_recovery_adjust_mismatch"


@pytest.mark.asyncio
async def test_recovery_error_path_does_not_raise():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None, guardian=None)
    runtime.bracket_service = MagicMock()
    plan = make_plan("BTCUSDT", "LONG", [BracketAction(action_type="CANCEL", order_id="orph")], severity="WARN")
    runtime.bracket_service.evaluate_all_for_recovery = MagicMock(return_value=[plan])
    runtime._apply_bracket_plan = AsyncMock(side_effect=Exception("fail"))

    await runtime._run_bracket_recovery_pass()

    assert runtime._recovery_completed is True
