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


class TimeoutAdapter:
    def __init__(self) -> None:
        self.place_order_calls = []
        self.fail_on_brackets = True
        self.create_order = self.place_order # Alias for ExecutionService compatibility

    async def place_order(self, symbol=None, side=None, order_type=None, quantity=None, params=None, **kwargs):
        if params:
            symbol = params.symbol
            side = params.side
            order_type = params.order_type
            quantity = params.quantity
            # Unpack other fields if needed
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


def make_plan(symbol: str, qty: Decimal, sl_price: Decimal) -> BracketPlan:
    pos_view = PositionView(
        symbol=symbol,
        side="LONG",
        qty=Decimal(qty),
        avg_entry_price=Decimal("100"),
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
        )
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
async def test_timeout_marks_orders_state_unknown_and_requests_snapshot():
    adapter = TimeoutAdapter()
    runtime = ExecPosRuntimeV2(config={}, adapter=adapter, price_service=None)
    symbol = "BNBUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=100.0)
    runtime._positions_by_symbol[symbol] = position

    snapshot_hook = AsyncMock()
    runtime.set_snapshot_refresh_hook(snapshot_hook)

    plan = make_plan(symbol, Decimal("1"), Decimal("95"))

    await runtime._apply_bracket_plan(symbol, position, plan, reason="test_timeout")

    assert runtime._orders_snapshot_state.get(symbol) == "UNKNOWN"
    assert runtime._last_orders_snapshot_ts.get(symbol) == 0.0
    snapshot_hook.assert_awaited_once_with(symbol)

    await runtime._evaluate_brackets(symbol, position, reason="account_update_sync")
    assert len(adapter.place_order_calls) == 1
