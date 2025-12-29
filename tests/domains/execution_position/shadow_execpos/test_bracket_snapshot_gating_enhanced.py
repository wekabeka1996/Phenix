"""
Bracket Snapshot Gating Enhanced Tests (Phase 10)
==================================================

Tests for bracket evaluation gating based on ORDERS_SNAPSHOT state.
This file explicitly tests the contract for EP-CORE-SLIM-RUNTIME-STEP1.

Contract:
- Bracket evaluation is blocked when snapshot_state == "UNKNOWN" or "STALE"
- Bracket evaluation proceeds when snapshot_state == "FRESH"
- "trade_executed" reason allows "UNKNOWN" snapshot state (fail-open for immediate reaction)
- "guard_loop" and "account_update_sync" reasons require "FRESH" snapshot state (fail-closed)

Phase 10: Tests verify gating via place_order calls instead of bracket_service.evaluate,
          since runtime now uses core planner directly.
"""
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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


# =============================================================================
# Fixtures & Builders
# =============================================================================

def make_ep_config() -> ExecutionPositionConfig:
    return ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(enabled=True),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=60.0),
    )


def make_runtime() -> ExecPosRuntimeV2:
    runtime = ExecPosRuntimeV2(
        config={},
        adapter=None,
        price_service=None,
        ep_config=make_ep_config(),
        guardian=MagicMock(),
    )
    # Disable ExecutorPool to use legacy path with mocked execution_service
    runtime._use_executor_pool = False

    runtime.execution_service = MagicMock()
    runtime.execution_service.place_order = AsyncMock(
        return_value={"success": True, "order_id": "mock-oid"})
    runtime.execution_service.cancel_order = AsyncMock(
        return_value={"success": True})

    # Phase 10: bracket_service still exists on runtime but is not used for planning
    # Keep it for backwards compat but tests should verify via place_order
    runtime.bracket_service = MagicMock()
    runtime.bracket_service.build_state = MagicMock(return_value={})
    runtime.bracket_service.evaluate = MagicMock(return_value=BracketPlan(
        symbol="TEST", side="LONG", state=None, actions=[], severity="INFO", why="mock"
    ))

    return runtime

# =============================================================================
# Tests
# =============================================================================


@pytest.mark.asyncio
async def test_evaluate_brackets_blocked_when_snapshot_unknown_for_guard_loop():
    """
    Verify that guard_loop skips evaluation when snapshot_state is UNKNOWN.
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert: No bracket orders placed when gated
    runtime.execution_service.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_brackets_blocked_when_snapshot_stale_for_guard_loop():
    """
    Verify that guard_loop skips evaluation when snapshot_state is STALE.
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "STALE"

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert: No bracket orders placed when gated
    runtime.execution_service.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_brackets_blocked_when_snapshot_ttl_expired_for_guard_loop():
    """
    Verify that guard_loop skips evaluation when snapshot is FRESH but TTL expired.
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "FRESH"
    # DUPID-FIX-3: guard_loop is blocked until recovery completes
    runtime._recovery_completed = True
    # Set timestamp older than TTL (60s)
    runtime._last_orders_snapshot_ts[symbol] = time.monotonic() - 120.0

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert: No bracket orders placed when gated
    runtime.execution_service.place_order.assert_not_called()
    # Should have transitioned to STALE
    assert runtime._orders_snapshot_state[symbol] == "STALE"


@pytest.mark.asyncio
async def test_evaluate_brackets_allowed_when_snapshot_fresh_for_guard_loop():
    """
    Verify that guard_loop proceeds when snapshot is FRESH and within TTL.
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "FRESH"
    # DUPID-FIX-3: guard_loop is blocked until recovery completes
    runtime._recovery_completed = True
    runtime._last_orders_snapshot_ts[symbol] = time.monotonic()

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert: Bracket orders placed when snapshot is fresh
    # Core planner generates PLACE_SL + PLACE_TP for LONG position without brackets
    runtime.execution_service.place_order.assert_called()


@pytest.mark.asyncio
async def test_evaluate_brackets_allowed_when_snapshot_unknown_for_trade_executed():
    """
    Verify that trade_executed allows evaluation even if snapshot is UNKNOWN (fail-open).
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Assert: Bracket orders placed (trade_executed allows UNKNOWN - fail-open)
    runtime.execution_service.place_order.assert_called()


@pytest.mark.asyncio
async def test_evaluate_brackets_blocked_when_snapshot_unknown_for_account_update_sync():
    """
    Verify that account_update_sync skips evaluation when snapshot_state is UNKNOWN.
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"
    position = PositionState(symbol=symbol, qty=1.0, avg_entry_price=2000.0)

    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="account_update_sync")

    # Assert: No bracket orders placed when gated
    runtime.execution_service.place_order.assert_not_called()
