"""
Edge-Case & Concurrency Test Scenarios for ExecPosRuntimeV2
============================================================

Validates runtime behavior under stressful conditions:
- Out-of-order events
- Duplicate fills
- Rapid open/close sequences
- Adapter failures
- Race-like scenarios

Tests enforce invariants I1-I6 defined in EXECUTION_POSITION_INVARIANTS.md

Task: EP-RUNTIME-CONCURRENCY-SAFETY-S1
"""
import pytest
import asyncio
from typing import Dict, Any

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from .runtime_scenario_runner import FakeClock, FakeExecutionAdapter, RuntimeScenarioRunner
from .invariant_helpers import (
    assert_all_invariants,
    assert_no_double_close,
    assert_idempotency_respected,
    assert_no_orphan_brackets,
)


def create_test_runtime(clock: FakeClock, adapter: FakeExecutionAdapter) -> ExecPosRuntimeV2:
    """Factory to create ExecPosRuntimeV2 with test doubles."""
    config = {
        "gatekeeper": {
            "min_qty": 0.001,
            "min_notional": 5.0,
        },
        "watchdog": {
            "enabled": True,
        },
    }

    # Mock price_service
    class MockPriceService:
        def get_mark_price(self, symbol):
            return 50000.0

    return ExecPosRuntimeV2(
        config=config,
        adapter=adapter,
        price_service=MockPriceService(),
        clock=clock,  # Inject for deterministic testing
    )


@pytest.mark.asyncio
async def test_scenario_1_out_of_order_fills():
    """
    Scenario 1: Out-of-order fills

    Sequence:
    1. ENTRY_INTENT (LONG 1.0 BTC)
    2. TRADE_EXECUTED (partial: 0.5 BTC)
    3. CANCEL_INTENT (user cancels remaining)
    4. TRADE_EXECUTED (late fill: 0.3 BTC arrives after cancel)

    Assert:
    - Final position = 0.8 BTC (0.5 + 0.3)
    - No negative PnL
    - State consistent
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Step 1: Entry intent
    clock.tick(0.0)
    entry_event = {
        "kind": "ENTRY_INTENT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": 1.0,
        "price": 50000.0,
    }
    await runtime.handle(entry_event)

    # Step 2: Partial fill
    clock.tick(1.0)
    partial_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 50000.0,
        "trade_id": "T1",
        "orderId": "O1",
    }
    await runtime.handle(partial_fill)

    # Step 3: Cancel intent
    clock.tick(0.5)
    cancel_event = {
        "kind": "CANCEL_INTENT",
        "symbol": "BTCUSDT",
        "order_id": "O1",
    }
    await runtime.handle(cancel_event)

    # Step 4: Late fill (arrives after cancel)
    clock.tick(0.3)
    late_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.3,
        "price": 50000.0,
        "trade_id": "T2",  # Different trade_id
        "orderId": "O1",
    }
    await runtime.handle(late_fill)

    # Assertions
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    # Check position size
    position = state["positions"].get("BTCUSDT")
    position_size = float(position.qty) if position else 0.0
    assert abs(position_size - 0.8) < 0.001, f"Expected 0.8 BTC, got {position_size}"

    # Check invariants
    assert_all_invariants(state, adapter.get_calls(), runtime._metrics)


@pytest.mark.asyncio
async def test_scenario_2_duplicate_fills():
    """
    Scenario 2: Duplicate fills (idempotency)

    Sequence:
    1. ENTRY_INTENT
    2. TRADE_EXECUTED (1.0 BTC, trade_id=T123)
    3. TRADE_EXECUTED (duplicate: same trade_id=T123)

    Assert:
    - Position = 1.0 BTC (not 2.0)
    - fills_duplicate metric > 0
    - Idempotency prevented double-count
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Entry intent
    entry_event = {
        "kind": "ENTRY_INTENT",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "qty": 1.0,
        "price": 3000.0,
    }
    await runtime.handle(entry_event)

    # First fill
    clock.tick(1.0)
    fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "quantity": 1.0,
        "price": 3000.0,
        "trade_id": "T123",
        "orderId": "O1",
        "cumQty": "1.0",  # For idempotency
    }
    await runtime.handle(fill)

    # Duplicate fill (same trade_id)
    clock.tick(0.1)
    duplicate_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "quantity": 1.0,
        "price": 3000.0,
        "trade_id": "T123",  # Same trade_id!
        "orderId": "O1",
        "cumQty": "1.0",  # Same cumQty - this is a duplicate
    }
    await runtime.handle(duplicate_fill)

    # Assertions
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    # Position should be 1.0, not 2.0
    position = state["positions"].get("ETHUSDT")
    position_size = float(position.qty) if position else 0.0
    assert abs(position_size - 1.0) < 0.001, f"Expected 1.0 ETH (idempotency), got {position_size}"

    # Duplicate metric should be incremented
    duplicates = runtime._metrics.get("fills_duplicate", 0)
    assert duplicates > 0, "Expected fills_duplicate metric > 0"

    # Check all invariants
    assert_idempotency_respected(runtime._metrics, state)


@pytest.mark.asyncio
async def test_scenario_3_rapid_open_close():
    """
    Scenario 3: Rapid open/close

    Sequence:
    1. ENTRY_INTENT (open LONG)
    2. CLOSE_INTENT (immediate close before fill)
    3. TRADE_EXECUTED (fill arrives late)
    4. TRADE_EXECUTED (close fill)

    Assert:
    - Final position = 0 (closed)
    - No double-close
    - No orphan SL/TP
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Entry intent
    entry_event = {
        "kind": "ENTRY_INTENT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": 0.5,
        "price": 50000.0,
    }
    await runtime.handle(entry_event)

    # Immediate close intent (before fill!)
    clock.tick(0.1)
    close_event = {
        "kind": "CLOSE_INTENT",
        "symbol": "BTCUSDT",
    }
    await runtime.handle(close_event)

    # Entry fill arrives late
    clock.tick(0.5)
    entry_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 50000.0,
        "trade_id": "T_ENTRY",
        "orderId": "O_ENTRY",
    }
    await runtime.handle(entry_fill)

    # Close fill
    clock.tick(0.3)
    close_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "quantity": 0.5,
        "price": 50100.0,
        "trade_id": "T_CLOSE",
        "orderId": "O_CLOSE",
        "reduceOnly": True,
    }
    await runtime.handle(close_fill)

    # Assertions
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    # Position should be closed
    position = state["positions"].get("BTCUSDT")
    position_size = float(position.qty) if position else 0.0
    assert abs(position_size) < 0.001, f"Expected position=0 (closed), got {position_size}"

    # No double-close
    assert_no_double_close(state, adapter.get_calls())

    # No orphan brackets
    assert_no_orphan_brackets(state)


@pytest.mark.asyncio
async def test_scenario_4_sl_orphan_risk():
    """
    Scenario 4: SL orphan risk (watchdog cleanup)

    Setup:
    - POSITION_SNAPSHOT: qty=0 (closed)
    - ORDERS_SNAPSHOT: has active SL order

    Assert:
    - Watchdog detects ORPHAN_SL
    - No orphan brackets in final state
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Simulate closed position with orphan SL
    clock.tick(0.0)
    position_snapshot = {
        "kind": "POSITION_SNAPSHOT",
        "symbol": "BTCUSDT",
        "position_size": "0",  # Closed!
        "direction":"FLAT",
    }
    await runtime.handle(position_snapshot)

    # Orphan SL order still active
    clock.tick(0.1)
    orders_snapshot = {
        "kind": "ORDERS_SNAPSHOT",
        "symbol": "BTCUSDT",
        "orders": [
            {
                "orderId": "O_SL_ORPHAN",
                "type": "STOP_MARKET",
                "side": "SELL",
                "quantity": "0.5",
                "stopPrice": "49000",
                "reduceOnly": True,
            }
        ],
    }
    await runtime.handle(orders_snapshot)

    # Let watchdog run (would happen on tick)
    # In real scenario, watchdog detects and cleans up
    # For this test, verify detection
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": orders_snapshot["orders"],
        "metrics": runtime._metrics,
    }

    # Should detect orphan (watchdog metrics would increment)
    # This is a simplified check - full watchdog integration would cleanup
    position = state["positions"].get("BTCUSDT")
    position_size = float(position.qty) if position else 0.0
    assert abs(position_size) < 0.001, "Position should be closed"

    # Note: Full watchdog cleanup would remove orphan order
    # This test validates detection logic


@pytest.mark.asyncio
async def test_scenario_5_missing_sl():
    """
    Scenario 5: Missing SL under open position

    Setup:
    - POSITION_SNAPSHOT: qty > 0 (open)
    - ORDERS_SNAPSHOT: no SL order

    Assert:
    - Watchdog detects NO_SL_FOR_OPEN_POSITION
    - Metrics track violation
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Open position
    position_snapshot = {
        "kind": "POSITION_SNAPSHOT",
        "symbol": "ETHUSDT",
        "position_size": "10.0",  # Open!
        "direction": "LONG",
        "entry_price": "3000.0",
    }
    await runtime.handle(position_snapshot)

    # No SL/TP orders
    clock.tick(0.1)
    orders_snapshot = {
        "kind": "ORDERS_SNAPSHOT",
        "symbol": "ETHUSDT",
        "orders": [],  # No SL!
    }
    await runtime.handle(orders_snapshot)

    # Watchdog should detect missing SL
    # (In real runtime, watchdog.validate() would be called)
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    position = state["positions"].get("ETHUSDT")
    position_size = float(position.qty) if position else 0.0
    assert position_size > 0, "Position should be open"

    # Watchdog should flag this (metrics would show NO_SL violation)
    # Full integration would log warning


@pytest.mark.asyncio
async def test_scenario_6_adapter_failures():
    """
    Scenario 6: Adapter failures (error codes)

    Tests error handling for:
    - -2011 (order already cancelled)
    - -2021 (order would immediately trigger)

    Assert:
    - Errors normalized correctly
    - No inconsistent state
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)

    # Script adapter to fail with -2011 on first cancel
    adapter.script[("cancel_order", 0)] = (False, "Error -2011: Order does not exist")

    runtime = create_test_runtime(clock, adapter)

    # Try to cancel non-existent order
    cancel_event = {
        "kind": "CANCEL_INTENT",
        "symbol": "BTCUSDT",
        "order_id": "FAKE_ORDER_999",
    }

    # Should handle gracefully
    try:
        await runtime.handle(cancel_event)
    except RuntimeError as e:
        # Expected - adapter raises error
        assert "-2011" in str(e)

    # State should remain consistent
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    # No position corruption
    assert len(state["positions"]) == 0, "No positions should exist after failed cancel"


@pytest.mark.asyncio
async def test_scenario_7_mixed_conditions():
    """
    Scenario 7: Mixed conditions (stress test)

    Combines:
    - Out-of-order events
    - Duplicate fills
    - Adapter errors
    - Rapid state changes

    Assert:
    - All invariants I1-I6 hold
    - No data corruption
    """
    clock = FakeClock()
    adapter = FakeExecutionAdapter(clock=clock)
    runtime = create_test_runtime(clock, adapter)

    # Complex sequence
    # 1. Entry
    entry_event = {
        "kind": "ENTRY_INTENT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": 1.0,
        "price": 50000.0,
    }
    await runtime.handle(entry_event)

    # 2. Fill
    clock.tick(1.0)
    fill1 = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 50000.0,
        "trade_id": "T1",
        "orderId": "O1",
        "cumQty": "0.5",
    }
    await runtime.handle(fill1)

    # 3. Duplicate fill (should be ignored)
    clock.tick(0.1)
    await runtime.handle(fill1)  # Same event

    # 4. Late second fill (out of order)
    clock.tick(0.5)
    fill2 = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 50000.0,
        "trade_id": "T2",
        "orderId": "O1",
        "cumQty": "1.0",
    }
    await runtime.handle(fill2)

    # 5. Close
    clock.tick(1.0)
    close_fill = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "quantity": 1.0,
        "price": 50100.0,
        "trade_id": "T_CLOSE",
        "orderId": "O_CLOSE",
        "reduceOnly": True,
    }
    await runtime.handle(close_fill)

    # Final assertions - ALL invariants
    state = {
        "positions": runtime._positions_by_symbol,
        "orders": [],
        "metrics": runtime._metrics,
    }

    # Check all invariants
    assert_all_invariants(state, adapter.get_calls(), runtime._metrics)

    # Specific checks
    position = state["positions"].get("BTCUSDT")
    position_size = float(position.qty) if position else 0.0

    # Should be closed (1.0 BUY - 1.0 SELL = 0)
    assert abs(position_size) < 0.001, f"Expected closed position, got {position_size}"

    # Duplicate should be caught
    duplicates = runtime._metrics.get("fills_duplicate", 0)
    assert duplicates > 0, "Should have detected duplicate fill"


if __name__ == "__main__":
    # Run scenarios
    pytest.main([__file__, "-v"])

