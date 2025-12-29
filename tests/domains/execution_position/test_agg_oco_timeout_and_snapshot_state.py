"""
TEST-OCO-R1-020..022 — Aggregated OCO Timeout & Snapshot State Tests

Tests for snapshot state management and fail-closed behavior:
- Empty ORDERS_SNAPSHOT with open position (TEST-OCO-R1-020)
- Timeout placing SL/TP forces UNKNOWN snapshot_state (TEST-OCO-R1-021)
- Snapshot TTL + guard_loop skips evaluation on STALE (TEST-OCO-R1-022)

Based on:
- docs/audit/OCO_AUDIT_R1C_RACES.md (R1-C-RISK-5)
- docs/audit/OCO_AUDIT_R1D_TESTPLAN.md

RID: OCO-AUDIT-R1-TEST-SNAPSHOT-TIMEOUT
"""
import time
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)


# ========== Test Fixtures ==========

def _make_runtime(orders_ttl_sec: float = 30.0) -> ExecPosRuntimeV2:
    """Create test runtime with configurable snapshot TTL."""
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.02,
            tp_rr=2.0,
            allow_unprotected_position=False,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(
            orders_ttl_sec=orders_ttl_sec, position_ttl_sec=30.0),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None,
                          price_service=None, ep_config=ep_cfg)

    # Mock ExecutionService
    mock_exec_service = AsyncMock(spec=ExecutionService)
    mock_exec_service.place_order = AsyncMock(return_value={
        "success": True,
        "order_id": "ORDER_TEST_123",
        "client_order_id": "AUR-TEST-123",
    })
    mock_exec_service.cancel_order = AsyncMock(return_value={
        "success": True,
        "order_id": "ORDER_TEST_123",
    })
    rt.execution_service = mock_exec_service

    return rt


def _simulate_trade_executed(runtime: ExecPosRuntimeV2, symbol: str, side: str, quantity: float, price: float):
    """Simulate TRADE_EXECUTED event."""
    from apps.reference.domains.execution_position.shadow_execpos.position_model import apply_fill

    current_state = runtime._positions_by_symbol.get(symbol)
    if not current_state:
        current_state = PositionState(
            symbol=symbol, qty=0.0, avg_entry_price=0.0)

    new_state = apply_fill(
        state=current_state,
        side=side,
        quantity=quantity,
        price=price,
        ts=time.time(),
    )
    runtime._positions_by_symbol[symbol] = new_state
    return new_state


# ========== TEST-OCO-R1-020: Empty ORDERS_SNAPSHOT with open position ==========

@pytest.mark.asyncio
async def test_empty_orders_snapshot_with_open_position_stale_mirror():
    """
    TEST-OCO-R1-020 — Empty ORDERS_SNAPSHOT clears mirror and marks FRESH

    Invariants: R1-C-RISK-1 (resolved in R2-C)

    Given:
      - Position qty>0 in _positions_by_symbol
      - _open_orders_by_symbol[symbol] contains old SL/TP (stale mirror)

    When:
      - ORDERS_SNAPSHOT arrives with orders=[] (exchange has no orders)

    Then (R2-C behavior):
      - _open_orders_by_symbol[symbol] cleared to []
      - _orders_snapshot_state[symbol] == "FRESH" (valid empty state)
      - Subsequent evaluate sees clean state without phantom orders

    Rationale:
      - Empty ORDERS_SNAPSHOT is single source of truth
      - If exchange says "no orders", local mirror must reflect that
      - Prevents stale mirror from blocking new bracket placement
    """
    runtime = _make_runtime()
    symbol = "BTCUSDT"

    # Step 1: Setup position
    _simulate_trade_executed(runtime, symbol, side="BUY",
                             quantity=1.0, price=50000.0)

    # Step 2: Populate mirror with stale brackets (simulate previous cycle)
    # Use "time" field in the past to bypass IN_FLIGHT_GRACE_PERIOD (2s) in order_index
    old_time_ms = int((time.time() - 10) * 1000)  # 10 seconds ago
    runtime._open_orders_by_symbol[symbol] = [
        {
            "symbol": symbol,
            "orderId": "STALE_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "1.0",
            "stopPrice": "49000.0",
            "reduceOnly": True,
            "status": "NEW",
            "time": old_time_ms,  # Created in the past
        }
    ]
    runtime._mark_orders_snapshot(symbol)

    # Verify mirror not empty before test
    assert len(runtime._open_orders_by_symbol.get(symbol, [])) > 0, \
        "Precondition: mirror contains stale orders"

    # Step 3: Empty ORDERS_SNAPSHOT arrives (exchange truth: no orders)
    await runtime._handle_orders_snapshot({"orders": []})

    # Step 4: Assert mirror cleared (R2-C fix)
    current_mirror = runtime._open_orders_by_symbol.get(symbol, [])
    assert current_mirror == [], \
        "R2-C: Empty ORDERS_SNAPSHOT must clear mirror to [] (single source of truth)"

    # Step 5: Assert snapshot_state remains FRESH
    assert runtime._orders_snapshot_state.get(symbol) == "FRESH", \
        "Snapshot state should be FRESH (valid empty snapshot)"

    # Step 6: Verify evaluate can proceed with clean state
    position = runtime._positions_by_symbol[symbol]
    await runtime._evaluate_brackets(symbol, position, reason="account_update_sync")

    # BracketService now sees no orders → can place new brackets if needed
    # No phantom orders blocking evaluation


@pytest.mark.asyncio
async def test_empty_orders_snapshot_then_evaluate_sees_no_brackets():
    """
    TEST-OCO-R1-020b — Empty ORDERS_SNAPSHOT + evaluate sees clean state

    Given:
      - Position LONG 2.0
      - Old mirror had SL/TP
      - Empty ORDERS_SNAPSHOT clears mirror

    When:
      - _evaluate_brackets called with reason="trade_executed"

    Then:
      - BracketService receives empty bracket_set (no existing orders)
      - Can place new SL/TP (not blocked by phantom orders)
      - ExecutionService.place_order called for new brackets
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Step 1: Setup position
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=3000.0)

    # Step 2: Populate mirror with old brackets (use time in past to bypass grace period)
    old_time_ms = int((time.time() - 10) * 1000)  # 10 seconds ago
    runtime._open_orders_by_symbol[symbol] = [
        {
            "symbol": symbol,
            "orderId": "OLD_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "2940.0",
            "reduceOnly": True,
            "status": "NEW",
            "time": old_time_ms,  # Created in the past
        }
    ]
    runtime._mark_orders_snapshot(symbol)

    # Step 3: Empty ORDERS_SNAPSHOT clears mirror
    await runtime._handle_orders_snapshot({"orders": []})

    assert runtime._open_orders_by_symbol.get(symbol, []) == [], \
        "Mirror cleared by empty snapshot"

    # Step 4: Mock ExecutionService to track place_order calls
    runtime.execution_service.place_order = AsyncMock(return_value={
        "success": True,
        "order_id": "NEW_SL_123",
        "client_order_id": "AUR-NEW-SL",
    })

    # Step 5: Evaluate brackets (should see empty state)
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Step 6: Verify place_order called (new brackets placed)
    assert runtime.execution_service.place_order.call_count >= 1, \
        "Evaluate should place new brackets when mirror empty (no phantom orders)"


# ========== TEST-OCO-R1-021: Timeout placing SL/TP forces UNKNOWN ==========

@pytest.mark.asyncio
async def test_timeout_placing_sl_tp_forces_unknown_snapshot_state():
    """
    TEST-OCO-R1-021 — Timeout placing SL/TP forces UNKNOWN snapshot_state

    Invariants: R1-C-RISK-5 (matches existing S2 contract)

    Given:
      - New plan PLACE_SL/PLACE_TP

    When:
      - ExecutionService.place_order returns {"success": False, "error_kind": "ADAPTER_ERROR_TIMEOUT"}

    Then:
      - _orders_snapshot_state[symbol] == "UNKNOWN"
      - _last_orders_snapshot_ts[symbol] == 0.0
      - _request_orders_snapshot(force=True) is called
      - _evaluate_brackets blocked until new ORDERS_SNAPSHOT arrives

    CURRENT STATUS: Already implemented in S2/runtime fixes.
    This test validates the contract.
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Step 1: Setup position
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=3000.0)

    # Step 2: Mock snapshot as FRESH (no existing brackets)
    runtime._open_orders_by_symbol[symbol] = []
    runtime._mark_orders_snapshot(symbol)

    # Step 3: Mock ExecutionService to return timeout on place_order
    runtime.execution_service.place_order = AsyncMock(return_value={
        "success": False,
        "error_kind": "ADAPTER_ERROR_TIMEOUT",
        "order_id": None,
    })

    # Step 4: Mock _request_orders_snapshot to track if called
    runtime._request_orders_snapshot = AsyncMock()

    # Step 5: Trigger bracket evaluation (should generate PLACE_SL/TP plan)
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Step 6: Verify timeout handling
    # After timeout, snapshot_state should be UNKNOWN
    assert runtime._orders_snapshot_state.get(symbol) == "UNKNOWN", \
        "Snapshot state should be UNKNOWN after timeout (S2 contract)"

    assert runtime._last_orders_snapshot_ts.get(symbol, -1) == 0.0, \
        "Snapshot timestamp should be reset to 0 after timeout"

    # Verify force snapshot request was triggered
    runtime._request_orders_snapshot.assert_called_once_with(
        symbol, force=True)

    # Step 7: Verify subsequent evaluate is blocked
    # Reset mock to track new calls
    runtime.execution_service.place_order.reset_mock()

    # Try another evaluate with UNKNOWN state
    await runtime._evaluate_brackets(symbol, position, reason="account_update_sync")

    # Should be blocked (no place_order calls)
    runtime.execution_service.place_order.assert_not_called()


# ========== TEST-OCO-R1-022: Snapshot TTL + guard_loop skips on STALE ==========

@pytest.mark.asyncio
async def test_snapshot_ttl_guard_loop_skips_evaluation_on_stale():
    """
    TEST-OCO-R1-022 — Snapshot TTL + guard_loop skips evaluation on STALE for account_update_sync

    Invariants: R1-C-RISK-5

    Given:
      - _orders_snapshot_state[symbol] == "FRESH"
      - But time.monotonic() advanced so TTL expired

    When:
      - _evaluate_brackets(symbol, position, reason="account_update_sync") is called

    Then:
      - snapshot_state transitioned to "STALE"
      - Evaluate skipped with BRACKETS result="snapshot_blocked"
      - This is fail-closed path for account_update (safer than operating on stale data)

    Note: For reason="trade_executed", STALE is allowed (fail-open).
    """
    runtime = _make_runtime(orders_ttl_sec=5.0)  # Short TTL for test
    symbol = "ADAUSDT"

    # Step 1: Setup position
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=10.0, price=1.0)

    # Step 2: Setup FRESH snapshot
    runtime._open_orders_by_symbol[symbol] = [
        {
            "symbol": symbol,
            "orderId": "SL_FRESH",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "10.0",
            "stopPrice": "0.98",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]

    # Mark snapshot with old timestamp (beyond TTL)
    with patch('time.monotonic', return_value=1000.0):
        runtime._mark_orders_snapshot(symbol)

    runtime._orders_snapshot_state[symbol] = "FRESH"

    # Step 3: Advance time beyond TTL
    with patch('time.monotonic', return_value=1010.0):  # 10 seconds later (TTL=5s)
        # Mock _apply_bracket_plan to track if called
        runtime._apply_bracket_plan = AsyncMock()

        # Step 4: Trigger evaluate with reason="account_update_sync"
        await runtime._evaluate_brackets(symbol, position, reason="account_update_sync")

        # Step 5: Verify evaluation was BLOCKED
        # snapshot_state should transition to STALE
        assert runtime._orders_snapshot_state.get(symbol) == "STALE", \
            "Snapshot state should transition to STALE when TTL expired"

        # _apply_bracket_plan should NOT be called (evaluation blocked)
        runtime._apply_bracket_plan.assert_not_called()


@pytest.mark.asyncio
async def test_snapshot_stale_allows_evaluation_for_trade_executed():
    """
    Additional test — STALE snapshot allows evaluate for reason="trade_executed" (fail-open).

    This is different from account_update_sync / guard_loop behavior.

    Rationale:
    - trade_executed is "hot path" — blocking it completely could leave position unprotected
    - account_update_sync is "background sync" — safer to skip than operate on stale data
    """
    runtime = _make_runtime(orders_ttl_sec=5.0)
    symbol = "SOLUSDT"

    # Step 1: Setup position
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=5.0, price=100.0)

    # Step 2: Setup STALE snapshot (TTL expired)
    runtime._open_orders_by_symbol[symbol] = []

    with patch('time.monotonic', return_value=1000.0):
        runtime._mark_orders_snapshot(symbol)

    runtime._orders_snapshot_state[symbol] = "FRESH"

    # Step 3: Advance time beyond TTL
    with patch('time.monotonic', return_value=1010.0):  # Beyond TTL
        # Mock _apply_bracket_plan
        runtime._apply_bracket_plan = AsyncMock()

        # Step 4: Trigger evaluate with reason="trade_executed"
        await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

        # Step 5: Verify evaluation PROCEEDED (fail-open for trade_executed)
        # Snapshot becomes STALE but evaluation continues

        # _apply_bracket_plan SHOULD be called (evaluation NOT blocked)
        runtime._apply_bracket_plan.assert_called_once()


# ========== Additional test: UNKNOWN state blocks all reasons ==========

@pytest.mark.asyncio
async def test_unknown_snapshot_state_blocks_all_evaluate_reasons():
    """
    Verify that snapshot_state=UNKNOWN blocks evaluation for ALL reasons.

    This is the strictest fail-closed behavior:
    - UNKNOWN = "we don't know what's on exchange"
    - Better to block than make incorrect decisions

    Applies to:
    - trade_executed
    - account_update_sync
    - guard_loop
    """
    runtime = _make_runtime()
    symbol = "BTCUSDT"

    # Setup position
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=1.0, price=50000.0)

    # Set snapshot state to UNKNOWN
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"
    runtime._last_orders_snapshot_ts[symbol] = 0.0

    # Mock _apply_bracket_plan
    runtime._apply_bracket_plan = AsyncMock()

    # Test all reasons
    for reason in ["trade_executed", "account_update_sync", "guard_loop"]:
        runtime._apply_bracket_plan.reset_mock()

        await runtime._evaluate_brackets(symbol, position, reason=reason)

        # UNKNOWN should block all reasons
        runtime._apply_bracket_plan.assert_not_called(), \
            f"Evaluation should be blocked for reason={reason} when snapshot_state=UNKNOWN"


# ========== Test: Snapshot refresh after timeout recovery ==========

@pytest.mark.asyncio
async def test_snapshot_refresh_after_timeout_allows_retry():
    """
    Verify that after timeout → UNKNOWN → fresh ORDERS_SNAPSHOT:
    - snapshot_state returns to FRESH
    - Bracket evaluation can proceed

    This tests the recovery path from timeout.
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Step 1: Setup position + timeout scenario
    position = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=3000.0)

    runtime._orders_snapshot_state[symbol] = "UNKNOWN"
    runtime._last_orders_snapshot_ts[symbol] = 0.0

    # Mock _apply_bracket_plan
    runtime._apply_bracket_plan = AsyncMock()

    # Step 2: Verify evaluation blocked
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")
    runtime._apply_bracket_plan.assert_not_called()

    # Step 3: Fresh ORDERS_SNAPSHOT arrives (recovery)
    await runtime._handle_orders_snapshot({
        "orders": [
            {
                "symbol": symbol,
                "orderId": "RECOVERED_SL",
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "2.0",
                "stopPrice": "2940.0",
                "reduceOnly": True,
                "status": "NEW",
            }
        ]
    })

    # Step 4: Verify snapshot_state recovered
    assert runtime._orders_snapshot_state.get(symbol) == "FRESH", \
        "Snapshot state should be FRESH after receiving orders"

    # Step 5: Retry evaluation
    runtime._apply_bracket_plan.reset_mock()
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Should now proceed (FRESH state)
    runtime._apply_bracket_plan.assert_called_once()
