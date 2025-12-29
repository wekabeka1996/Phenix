from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketAction,
    BracketPlan,
    BracketState,
    PositionView,
)


@pytest.mark.asyncio
async def test_apply_bracket_plan_skips_duplicate_sl():
    """
    Legacy test updated: Runtime no longer checks for duplicates locally.
    It relies on the Service to not emit redundant actions, or on ClientOrderID idempotency.
    In this synthetic test, we force a redundant action, so we expect a call.
    """
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(enabled=True),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(),
    )
    runtime = ExecPosRuntimeV2(
        config={}, adapter=None, price_service=None, ep_config=ep_cfg)

    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=0.5,
                             avg_entry_price=1100.0)
    runtime._positions_by_symbol[symbol] = position
    runtime.order_index.reconcile_snapshot(symbol, [
        {
            "symbol": symbol,
            "side": "SELL",
            "type": "STOP_MARKET",
            "quantity": "0.5",
            "stopPrice": "1200",
            "reduceOnly": True,
        }
    ])

    runtime.execution_service.place_order = AsyncMock()
    # Mock success to avoid loop continuation issues
    runtime.execution_service.place_order.return_value = {"success": True, "orderId": "123"}

    pos_view = PositionView(
        symbol=symbol,
        side="LONG",
        qty=Decimal("0.5"),
        avg_entry_price=Decimal("1100"),
    )
    state = BracketState(
        symbol=symbol, side="LONG", position_view=pos_view, bracket_set=None, guardian_meta=None)
    plan = BracketPlan(
        symbol=symbol,
        side="LONG",
        state=state,
        actions=[
            BracketAction(
                action="PLACE_SL", leg_type="SL", target_price=Decimal("1200"), qty=Decimal("0.5")
            )
        ],
        severity="ALERT",
        why="missing_sl",
    )

    await runtime._apply_bracket_plan(symbol, position, plan, reason="test")

    # Runtime V2 (Orchestrator) blindly executes the plan.
    # The Service is responsible for NOT emitting this action if it's redundant.
    # Since we forced the action in the plan, the runtime MUST execute it.
    runtime.execution_service.place_order.assert_called_once()
