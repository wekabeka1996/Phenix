import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketPlan,
    BracketState,
    PositionView,
    BracketAction,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


def _runtime(snapshot_ttl: float = 1.0) -> ExecPosRuntimeV2:
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(enabled=True),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(
            orders_ttl_sec=snapshot_ttl, position_ttl_sec=snapshot_ttl),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None,
                          price_service=None, ep_config=ep_cfg)
    return rt


@pytest.mark.asyncio
async def test_ethusdt_spam_regression_skips_when_snapshot_missing():
    runtime = _runtime(snapshot_ttl=0.5)
    symbol = "ETHUSDT"
    runtime._positions_by_symbol[symbol] = PositionState(
        symbol=symbol, qty=1.0, avg_entry_price=1800.0)

    # Force bracket service to always request PLACE_SL/TP
    def fake_build_state(positions, orders, symbol, side):
        return {(symbol, side): BracketState(symbol=symbol, side=side, position_view=positions[0], bracket_set=None, guardian_meta=None)}

    def fake_evaluate(state, cfg):
        st = next(iter(state.values()))
        return BracketPlan(
            symbol=st.symbol,
            side=st.side,
            state=st,
            actions=[
                BracketAction(action_type="PLACE_SL",
                              price=Decimal("1700"), qty=Decimal("1")),
                BracketAction(action_type="PLACE_TP",
                              price=Decimal("1900"), qty=Decimal("1")),
            ],
            severity="ALERT",
            why="missing_sl_tp",
        )

    runtime.bracket_service.build_state = fake_build_state  # type: ignore
    runtime.bracket_service.evaluate = fake_evaluate  # type: ignore
    runtime._apply_bracket_plan = AsyncMock()
    runtime.watchdog.analyze = lambda open_orders, positions: []

    # Simulate multiple POSITION_SYNC events without fresh ORDERS_SNAPSHOT
    payload = {"positions": [{"symbol": symbol, "qty": 1.0,
                              "entry_price": 1800.0, "update_time": None}]}
    for _ in range(5):
        await runtime._handle_position_sync(symbol, payload)
        await asyncio.sleep(0.1)

    # No brackets applied because snapshot is stale/missing -> no avalanche
    runtime._apply_bracket_plan.assert_not_awaited()
