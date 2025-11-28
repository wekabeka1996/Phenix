from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketAction,
    BracketPlan,
    BracketState,
    PositionView,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2


class FlakyAdapter:
    def __init__(self) -> None:
        self.place_order_calls = []
        self.fail_on_brackets = True
        self.create_order = self.place_order # Alias

    async def place_order(self, symbol=None, side=None, order_type=None, quantity=None, params=None, **kwargs):
        if params:
            symbol = params.symbol
            side = params.side
            order_type = params.order_type
            quantity = params.quantity
            kwargs.update({"client_order_id": params.client_order_id})

        self.place_order_calls.append(
            {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "kwargs": kwargs,
            }
        )
        if self.fail_on_brackets:
            return {
                "success": False,
                "error_kind": "ADAPTER_ERROR_TIMEOUT",
                "error": "timeout",
            }
        return {
            "success": True,
            "order_id": f"order_{len(self.place_order_calls)}",
            "client_order_id": kwargs.get("client_order_id"),
        }


def make_plan(symbol: str, qty: Decimal, sl_price: Decimal, tp_price: Decimal) -> BracketPlan:
    pos_view = PositionView(
        symbol=symbol,
        side="LONG",
        qty=Decimal(qty),
        avg_entry_price=Decimal("650"),
    )
    state = BracketState(
        symbol=symbol,
        side="LONG",
        position_view=pos_view,
        bracket_set=None,
        guardian_meta=None,
    )
    actions = [
        BracketAction(
            action_type="PLACE_SL",
            price=Decimal(sl_price),
            qty=Decimal(qty),
        ),
        BracketAction(
            action_type="PLACE_TP",
            price=Decimal(tp_price),
            qty=Decimal(qty),
        ),
    ]
    return BracketPlan(
        symbol=symbol,
        side="LONG",
        state=state,
        actions=actions,
        severity="WARN",
        why="test_plan",
    )


@pytest.mark.asyncio
async def test_no_duplicate_brackets_after_timeout_and_snapshot():
    """
    Legacy test updated: Runtime V2 is now a 'dumb orchestrator'.
    It blindly executes the plan provided.
    The duplicate check logic moved to BracketService.
    Since this test manually injects a plan with actions, the Runtime MUST execute them.
    """
    adapter = FlakyAdapter()
    runtime = ExecPosRuntimeV2(config={}, adapter=adapter, price_service=None)
    symbol = "BNBUSDT"
    position = PositionState(symbol=symbol, qty=10.0, avg_entry_price=650.0)
    runtime._positions_by_symbol[symbol] = position

    snapshot_hook = AsyncMock()
    runtime.set_snapshot_refresh_hook(snapshot_hook)

    plan = make_plan(symbol, Decimal("10"), Decimal("637.3"), Decimal("676.5"))

    await runtime._apply_bracket_plan(symbol, position, plan, reason="trade_executed")
    assert len(adapter.place_order_calls) == 1
    snapshot_hook.assert_awaited_once_with(symbol)
    assert runtime._orders_snapshot_state.get(symbol) == "UNKNOWN"

    existing_orders = [
        {
            "symbol": symbol,
            "side": "SELL",
            "type": "STOP_MARKET",
            "quantity": "9.95",
            "stopPrice": "637.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": "9.95",
            "stopPrice": "676.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]

    # Prevent recovery pass from triggering another failure during snapshot
    runtime._recovery_completed = True
    await runtime._handle_orders_snapshot({"orders": existing_orders})
    assert runtime._orders_snapshot_state.get(symbol) == "FRESH"

    adapter.fail_on_brackets = False
    # In the new architecture, the Service would NOT produce this plan if it saw the existing orders.
    # But here we force-feed the plan. The Runtime, being dumb, will try to execute it.
    await runtime._apply_bracket_plan(symbol, position, plan, reason="account_update_sync")

    # Old assertion: assert len(adapter.place_order_calls) == 1 (Runtime filtered it)
    # New assertion: assert len(adapter.place_order_calls) == 3 (1 initial + 2 new attempts)
    # The Runtime blindly follows the plan.
    assert len(adapter.place_order_calls) == 3
