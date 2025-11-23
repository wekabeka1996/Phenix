"""
Regression test for S29: Empty ORDERS_SNAPSHOT after entry fill must unblock brackets.

When entry order FILLS and vanishes from open orders, the subsequent ORDERS_SNAPSHOT
is empty (orders=[]). Before fix, this left snapshot_state=UNKNOWN for the symbol,
blocking ALL bracket placement.

After fix: Empty snapshot marks snapshot_state=FRESH for symbols WITH positions,
allowing brackets to be evaluated and placed.
"""
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


def _runtime() -> ExecPosRuntimeV2:
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(enabled=True),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=30.0, position_ttl_sec=30.0),
    )
    return ExecPosRuntimeV2(config={}, adapter=None, price_service=None, ep_config=ep_cfg)


@pytest.mark.asyncio
async def test_empty_snapshot_after_entry_fill_unblocks_brackets():
    """
    Scenario:
    1. Position opens (entry order FILLED → removed from open orders)
    2. ORDERS_SNAPSHOT arrives with orders=[] (entry vanished)
    3. snapshot_state for symbol must transition from UNKNOWN → FRESH
    4. Brackets evaluation proceeds (not blocked by snapshot guard)
    """
    runtime = _runtime()
    symbol = "SOLUSDT"

    # Step 1: Position opened (entry filled)
    runtime._positions_by_symbol[symbol] = PositionState(
        symbol=symbol,
        qty=0.5,
        avg_entry_price=100.0,
    )

    # Verify initial state is UNKNOWN
    assert runtime._orders_snapshot_state.get(symbol, "UNKNOWN") == "UNKNOWN"

    # Step 2: Empty ORDERS_SNAPSHOT arrives (entry order vanished after fill)
    await runtime._handle_orders_snapshot({"orders": []})

    # Step 3: Verify snapshot_state transitioned to FRESH for symbol WITH position
    assert runtime._orders_snapshot_state[symbol] == "FRESH", \
        "snapshot_state must be FRESH for symbol with position even when orders=[]"

    # Step 4: Verify snapshot is marked fresh (timestamp set)
    assert symbol in runtime._last_orders_snapshot_ts, \
        "Timestamp must be set for symbol with position"


@pytest.mark.asyncio
async def test_empty_snapshot_does_not_affect_symbols_without_positions():
    """
    Scenario:
    Empty snapshot should NOT mark symbols without positions as FRESH.
    Only symbols with active positions should transition UNKNOWN → FRESH.
    """
    runtime = _runtime()
    symbol_with_pos = "BTCUSDT"
    symbol_no_pos = "ETHUSDT"

    # Only BTCUSDT has position
    runtime._positions_by_symbol[symbol_with_pos] = PositionState(
        symbol=symbol_with_pos,
        qty=1.0,
        avg_entry_price=50000.0,
    )

    # Empty snapshot
    await runtime._handle_orders_snapshot({"orders": []})

    # BTCUSDT should be FRESH (has position)
    assert runtime._orders_snapshot_state.get(symbol_with_pos) == "FRESH"

    # ETHUSDT should remain UNKNOWN (no position)
    assert runtime._orders_snapshot_state.get(
        symbol_no_pos, "UNKNOWN") == "UNKNOWN"


@pytest.mark.asyncio
async def test_empty_snapshot_stales_old_fresh_states_without_positions():
    """
    Scenario:
    If a symbol had FRESH snapshot but no longer has position,
    empty snapshot should transition it to STALE.
    """
    runtime = _runtime()
    symbol = "ADAUSDT"

    # Simulate old state: FRESH but position closed
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = 12345.0
    # No position

    # Empty snapshot arrives
    await runtime._handle_orders_snapshot({"orders": []})

    # Should transition FRESH → STALE (no position)
    assert runtime._orders_snapshot_state[symbol] == "STALE", \
        "FRESH state without position should become STALE on empty snapshot"
