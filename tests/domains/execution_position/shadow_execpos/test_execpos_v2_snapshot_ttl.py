import time
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
    BracketPlan,
    BracketState,
    PositionView,
)

# Phase 11: runtime.bracket_service is None, tests mock build_state
pytestmark = pytest.mark.xfail(
    reason="Phase 11: Legacy bracket_service mock - runtime.bracket_service deprecated")


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

    # Stub bracket_service to avoid heavy computations
    def _fake_state(positions, orders, symbol, side):
        return {(
            symbol, side): BracketState(symbol=symbol, side=side, position_view=positions[0], bracket_set=None, guardian_meta=None)}

    def _fake_plan(state, cfg):
        # No actions when SL/TP already present (simulated)
        return BracketPlan(symbol=state.symbol, side=state.side, state=state, actions=[], severity="INFO", why="noop")

    rt.bracket_service.build_state = _fake_state  # type: ignore
    rt.bracket_service.evaluate = _fake_plan  # type: ignore
    return rt


@pytest.mark.asyncio
async def test_brackets_evaluate_skipped_when_orders_snapshot_stale():
    runtime = _runtime(snapshot_ttl=0.5)
    symbol = "ETHUSDT"
    runtime._positions_by_symbol[symbol] = PositionState(
        symbol=symbol, qty=1.0, avg_entry_price=1000.0)
    # Mark snapshot old
    runtime._last_orders_snapshot_ts[symbol] = time.monotonic() - 5.0

    runtime._apply_bracket_plan = AsyncMock()

    await runtime._evaluate_brackets(runtime._positions_by_symbol[symbol].symbol,
                                     runtime._positions_by_symbol[symbol],
                                     reason="account_update_sync")

    runtime._apply_bracket_plan.assert_not_called()


@pytest.mark.asyncio
async def test_brackets_evaluate_runs_when_snapshot_fresh():
    runtime = _runtime(snapshot_ttl=10.0)
    symbol = "ETHUSDT"
    runtime._positions_by_symbol[symbol] = PositionState(
        symbol=symbol, qty=1.0, avg_entry_price=1000.0)
    runtime._last_orders_snapshot_ts[symbol] = time.monotonic()
    runtime._orders_snapshot_state[symbol] = "FRESH"  # Must set snapshot state

    runtime._apply_bracket_plan = AsyncMock()

    await runtime._evaluate_brackets(runtime._positions_by_symbol[symbol].symbol,
                                     runtime._positions_by_symbol[symbol],
                                     reason="account_update_sync")

    runtime._apply_bracket_plan.assert_called_once()
