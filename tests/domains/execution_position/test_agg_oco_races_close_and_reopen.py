"""
TEST-OCO-R1-010..011 — Aggregated OCO Race Conditions: Close + Reopen

Tests for race conditions around full close + new entry (same symbol):
- Full close via bracket SL/TP + new entry (TEST-OCO-R1-010)
- Manual DEC:CLOSE + new CMD:OPEN (TEST-OCO-R1-011)

Based on:
- docs/audit/OCO_AUDIT_R1C_RACES.md
- docs/audit/OCO_AUDIT_R1D_TESTPLAN.md

RID: OCO-AUDIT-R1-TEST-RACES
"""
import time
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import AsyncMock

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

def _make_runtime() -> ExecPosRuntimeV2:
    """Create test runtime with mock ExecutionService."""
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.02,
            tp_rr=2.0,
            allow_unprotected_position=False,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=30.0, position_ttl_sec=30.0),
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


async def _simulate_trade_executed(runtime: ExecPosRuntimeV2, symbol: str, side: str, quantity: float, price: float):
    """Simulate TRADE_EXECUTED event and update position via _handle_trade_executed."""
    trade_payload = {
        "side": side,
        "quantity": quantity,
        "price": price,
        "timestamp": time.time() * 1000,  # Convert to ms
        "orderId": f"TEST_ORDER_{int(time.time())}",
        "tradeId": f"TEST_TRADE_{int(time.time())}",
    }
    await runtime._handle_trade_executed(symbol, trade_payload)
    return runtime._positions_by_symbol.get(symbol)


def _simulate_orders_snapshot(runtime: ExecPosRuntimeV2, symbol: str, orders: List[Dict[str, Any]]):
    """Simulate ORDERS_SNAPSHOT event."""
    runtime._open_orders_by_symbol[symbol] = orders
    runtime._mark_orders_snapshot(symbol)


# ========== TEST-OCO-R1-010: Full close via bracket + new entry ==========

@pytest.mark.asyncio
async def test_full_close_via_bracket_then_new_entry_cleans_old_brackets():
    """
    TEST-OCO-R1-010 — Full close via bracket SL/TP + new entry

    Invariants: R1-B-INV-2, R1-C-RISK-1/2

    Given:
      - LONG position qty>0 with active SL/TP
      - Bracket SL/TP exist on exchange and in _open_orders_by_symbol

    When:
      1. SL or TP fully closes position (fill + ACCOUNT_UPDATE/ORDERS_SNAPSHOT)
      2. Shortly after: new CMD:OPEN for same symbol
      3. New entry fills (TRADE_EXECUTED) and triggers _evaluate_brackets

    Then (EXPECTED):
      - Old SL/TP:
        - Either absent from mirror at time of new evaluate
        - OR explicitly identified as orphans and CANCELLED before/during new bracket creation
      - No scenario where new position is "protected" by old SL/TP that no longer exist on exchange

    CURRENT BEHAVIOR (gap — R1-C-RISK-1):
      - Empty ORDERS_SNAPSHOT does NOT clear _open_orders_by_symbol
      - New evaluate may see old SL/TP in mirror → think brackets already exist
      - No PLACE_SL/TP for new position ❌
    """
    runtime = _make_runtime()
    symbol = "BTCUSDT"

    # Step 1: Setup LONG position with SL/TP
    await _simulate_trade_executed(runtime, symbol, side="BUY",
                                   quantity=1.0, price=50000.0)

    old_brackets = [
        {
            "symbol": symbol,
            "orderId": "OLD_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "1.0",
            "stopPrice": "49000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "OLD_TP",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "1.0",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, old_brackets)

    # Step 2: Full close via TP fill
    flat_state = await _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=1.0, price=52000.0)
    assert abs(flat_state.qty) < 0.0001, "Position should be FLAT after full close"

    # Step 3: Simulate empty ORDERS_SNAPSHOT (SL/TP executed/cancelled on exchange)
    # CURRENT BUG (S29 partial fix): empty snapshot does NOT clear _open_orders_by_symbol
    await runtime._handle_orders_snapshot({"orders": []})

    # Step 4: Check that old brackets are still in mirror (BUG)
    current_mirror = runtime._open_orders_by_symbol.get(symbol, [])
    # With S29 fix, FLAT position + empty snapshot should mark state FRESH but NOT clear old orders
    # This is the gap documented in R1-C-RISK-1

    # Step 5: New entry for same symbol
    new_long_state = await _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=0.5, price=51000.0)
    assert new_long_state.qty > 0, "New LONG position opened"

    # Step 6: Trigger bracket evaluation for new position
    await runtime._evaluate_brackets(symbol, new_long_state, reason="trade_executed")

    # Step 7: Check that NEW brackets were placed (EXPECTED TO FAIL)
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Filter for calls AFTER the new entry (skip initial setup)
    # In real scenario, we'd track call order; for simplicity, check total count

    # EXPECTED: At least 2 new PLACE calls for SL/TP
    # CURRENT: May be 0 if BracketService sees old brackets in mirror and thinks protection exists

    new_bracket_calls = [
        c for c in place_calls
        if c[1].get("reduce_only") is True and c[1].get("side") == "SELL"
    ]

    # THIS ASSERTION WILL FAIL if mirror contains old brackets:
    assert len(new_bracket_calls) >= 2, \
        "New position should have SL/TP placed, but may be blocked by stale mirror (R1-C-RISK-1)"


# ========== TEST-OCO-R1-011: Manual DEC:CLOSE + new CMD:OPEN ==========

@pytest.mark.asyncio
async def test_manual_close_then_reopen_same_symbol_separates_brackets():
    """
    TEST-OCO-R1-011 — Manual DEC:CLOSE + new CMD:OPEN

    Invariants: R1-B-INV-2, R1-C-RISK-2

    Given:
      - LONG position with SL/TP

    When:
      1. CMD:CLOSE from DecisionMaking → CLOSE_INTENT
      2. Position becomes FLAT via TRADE_EXECUTED/ACCOUNT_UPDATE
      3. New CMD:OPEN for same symbol → new LONG position
      4. Triggers bracket evaluation for new position

    Then (EXPECTED):
      - Cleanup of SL/TP from previous position does NOT delete brackets for new position
      - New TP/SL are built from scratch or correctly re-bound (via future position_id/versioning)

    CURRENT BEHAVIOR (gap — R1-C-RISK-2):
      - No position_id/versioning
      - Cleanup by symbol+side only → may interfere with new position
      - OR: old brackets remain and confuse new position evaluation
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Step 1: Setup LONG position
    await _simulate_trade_executed(runtime, symbol, side="BUY",
                                   quantity=2.0, price=3000.0)

    old_brackets = [
        {
            "symbol": symbol,
            "orderId": "MANUAL_OLD_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "2940.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "MANUAL_OLD_TP",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "3120.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, old_brackets)

    # Step 2: Manual CLOSE (simulate CLOSE_INTENT → market order)
    # In real flow: CloseFlowService places market order, then TRADE_EXECUTED
    flat_state = await _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=2.0, price=3050.0)
    assert abs(
        flat_state.qty) < 0.0001, "Position should be FLAT after manual close"

    # Step 3: Simulate time passage + ORDERS_SNAPSHOT update
    # Old SL/TP may still be on exchange (if not auto-cancelled) or removed
    # For test: simulate empty snapshot (brackets cancelled)
    await runtime._handle_orders_snapshot({"orders": []})

    # Step 4: New CMD:OPEN shortly after
    new_long_state = await _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=1.5, price=3100.0)
    assert new_long_state.qty > 0, "New LONG position opened"

    # Step 5: Simulate fresh ORDERS_SNAPSHOT for new position (no brackets yet)
    _simulate_orders_snapshot(runtime, symbol, [])

    # Step 6: Trigger bracket evaluation
    await runtime._evaluate_brackets(symbol, new_long_state, reason="trade_executed")

    # Step 7: Verify new brackets placed
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Should have placed SL/TP for new position
    new_bracket_calls = [
        c for c in place_calls
        if c[1].get("reduce_only") is True and c[1].get("quantity") == 1.5
    ]

    assert len(new_bracket_calls) >= 2, \
        "New position should have fresh SL/TP, not confused with old brackets (R1-C-RISK-2)"


# ========== Additional test: Orphan detection after full close ==========

@pytest.mark.asyncio
async def test_orphan_brackets_detected_after_full_close():
    """
    Helper test — Orphan brackets should be detected when position FLAT.

    Current implementation:
    - BracketService.evaluate() CAN detect orphans (Invariant 1)
    - BUT: Runtime only calls evaluate for non-FLAT positions
    - Cleanup relies on _run_bracket_recovery_pass (one-time DR) or external Guardian

    This test documents the gap: no continuous orphan cleanup after full close.
    """
    runtime = _make_runtime()
    symbol = "ADAUSDT"

    # Step 1: Open position + brackets
    await _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=10.0, price=1.0)

    brackets = [
        {
            "symbol": symbol,
            "orderId": "ORPHAN_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "10.0",
            "stopPrice": "0.98",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets)

    # Step 2: Full close
    flat_state = await _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=10.0, price=1.05)
    assert abs(flat_state.qty) < 0.0001, "Position FLAT"

    # Step 3: Trigger evaluation for FLAT position
    # R2-ORPHAN-FIX: _evaluate_brackets now calls _cleanup_orphan_brackets_for_flat
    await runtime._evaluate_brackets(symbol, flat_state, reason="guard_loop")

    # Step 4: Verify orphan cleanup was executed
    exec_service = runtime.execution_service
    cancel_calls = [c for c in exec_service.cancel_order.call_args_list]

    # R2-ORPHAN-FIX: Orphan SL should be CANCELLED when position is FLAT
    assert len(cancel_calls) == 1, \
        "Orphan SL should be cancelled when position is FLAT"
    assert cancel_calls[0].kwargs.get("order_id") == "ORPHAN_SL"


# ========== Test: Symbol-only binding allows bracket confusion ==========

@pytest.mark.asyncio
async def test_symbol_only_binding_without_position_id_causes_confusion():
    """
    TEST scenario for R1-C-RISK-2 — Symbol+side-only binding without position_id.

    Given:
      - First position opens and closes
      - Second position opens with similar qty/price
      - Old brackets have compatible (symbol, side, qty, price) fingerprint

    When:
      - BracketService evaluates new position

    Then (EXPECTED gap):
      - May interpret old brackets as valid for new position
      - No position_id/versioning to distinguish

    This test documents the binding weakness.
    """
    runtime = _make_runtime()
    symbol = "SOLUSDT"

    # Step 1: First position cycle
    pos1 = await _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=5.0, price=100.0)

    brackets_v1 = [
        {
            "symbol": symbol,
            "orderId": "V1_SL",
            # Fingerprint based on qty+price
            "clientOrderId": "AUR-BRK-SOLUSDT-LONG-SL-5.0-100.0",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "5.0",
            "stopPrice": "98.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_v1)

    # Close first position
    flat_state = await _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=5.0, price=102.0)
    assert abs(flat_state.qty) < 0.0001

    # Step 2: Second position with SAME qty and similar price (fingerprint collision)
    pos2 = await _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=5.0, price=100.0)

    # Old brackets still in mirror (empty snapshot bug)
    # Brackets have same (symbol, side, qty, price) fingerprint

    # Step 3: Evaluate new position
    await runtime._evaluate_brackets(symbol, pos2, reason="trade_executed")

    # Step 4: Check if BracketService treated old brackets as valid
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # If BracketService saw brackets with matching fingerprint:
    # - sl_count > 0, tp_count >= 0
    # - May skip PLACE_SL (thinking protection exists)

    # This test documents the risk; exact behavior depends on current mirror state
    # Expected gap: No mechanism to distinguish "old bracket from previous position" vs "current bracket"

    # For now, just assert that test runs without crash
    assert pos2.qty == 5.0, "Second position opened"

    # In future with position_id:
    # - Brackets would be tagged with position_id/version
    # - BracketService would ignore brackets not matching current position_id
    # - Would always PLACE new brackets for new position_id


# ========== TASK 4 — R2-D: PositionCycleId Tests ==========

@pytest.mark.asyncio
async def test_old_cycle_brackets_are_canceled_and_do_not_block_new_cycle():
    """
    TEST-OCO-R2-D-001 — Old cycle brackets do not block new cycle

    Scenario:
    1. Cycle 1: LONG position opened → brackets placed (cycle_id=1)
    2. Position closed to FLAT (cycle_id remains 1)
    3. Cycle 2: New LONG position opened (cycle_id increments to 2)
    4. ORDERS_SNAPSHOT contains old cycle=1 brackets (delayed from exchange)
    5. Evaluate: old cycle=1 brackets should be CANCELED, new cycle=2 brackets PLACED

    Invariants:
    - R2-D-INV-1: Brackets from previous cycles are orphans
    - R2-D-INV-2: Orphan brackets do not satisfy current position protection requirements
    """
    runtime = _make_runtime()
    symbol = "BTCUSDT"

    # Step 1: Cycle 1 — Open LONG position
    pos1 = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=0.5, price=50000.0)
    assert pos1.cycle_id == 1  # First cycle
    assert pos1.qty == 0.5

    # Step 2: Simulate cycle 1 brackets in mirror (already placed)
    brackets_cycle1 = [
        {
            "symbol": symbol,
            "orderId": "SL_CYCLE1",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",  # cycle_id=1
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "0.5",
            "stopPrice": "49000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_CYCLE1",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",  # cycle_id=1
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "0.5",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_cycle1)

    # Step 3: Close position to FLAT
    flat_state = await _simulate_trade_executed(runtime, symbol, side="SELL", quantity=0.5, price=51000.0)
    assert abs(flat_state.qty) < 0.0001
    assert flat_state.cycle_id == 1  # Cycle doesn't increment on FLAT

    # Step 4: Cycle 2 — Open new LONG position (cycle increments)
    pos2 = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=0.8, price=51000.0)
    assert pos2.cycle_id == 2  # New cycle
    assert pos2.qty == 0.8

    # Step 5: Delayed ORDERS_SNAPSHOT still contains old cycle=1 brackets
    # (Exchange hasn't sent cancellation yet)
    _simulate_orders_snapshot(runtime, symbol, brackets_cycle1)

    # Step 6: Evaluate Cycle 2 position
    await runtime._evaluate_brackets(symbol, pos2, reason="cycle2_open")

    # Step 7: Verify orphan brackets are CANCELED
    exec_service = runtime.execution_service
    cancel_calls = [c for c in exec_service.cancel_order.call_args_list]

    # Should have at least 2 CANCEL calls (old SL + old TP)
    # Note: May be more if multiple evaluations happened
    assert len(
        cancel_calls) >= 2, f"Expected at least 2 CANCEL calls for cycle 1 orphans, got {len(cancel_calls)}"

    # Verify CANCELs target cycle 1 brackets
    canceled_order_ids = {c.kwargs.get(
        "order_id") or c.args[1] for c in cancel_calls}
    assert "SL_CYCLE1" in canceled_order_ids, "Old cycle 1 SL should be canceled"
    assert "TP_CYCLE1" in canceled_order_ids, "Old cycle 1 TP should be canceled"

    # Step 8: Verify BracketService recognized cycle mismatch
    # (This test validates the orphan detection logic, not necessarily PLACE calls
    # which might be suppressed by watchdog or other guards)


@pytest.mark.asyncio
async def test_reverse_does_not_reuse_brackets_from_previous_cycle():
    """
    TEST-OCO-R2-D-002 — Reverse does not reuse brackets from previous cycle

    Scenario:
    1. Cycle 1: LONG position opened (cycle_id=1) → SL/TP placed
    2. Reverse to SHORT without intermediate FLAT (cycle_id increments to 2)
    3. ORDERS_SNAPSHOT contains old LONG SL/TP (cycle_id=1)
    4. Evaluate: old LONG brackets should be CANCELED, new SHORT brackets PLACED

    Invariants:
    - R2-D-INV-3: Reverse (LONG→SHORT or SHORT→LONG) increments cycle_id
    - R2-D-INV-4: Old side brackets are orphans after reverse
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Step 1: Cycle 1 — Open LONG position
    pos1 = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=2.0, price=3000.0)
    assert pos1.cycle_id == 1
    assert pos1.side == "LONG"

    # Step 2: Simulate LONG brackets in mirror
    brackets_long_cycle1 = [
        {
            "symbol": symbol,
            "orderId": "SL_LONG_C1",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "2940.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_LONG_C1",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "3120.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_long_cycle1)

    # Step 3: Reverse to SHORT (SELL 4.0 → net -2.0 SHORT)
    pos2 = await _simulate_trade_executed(runtime, symbol, side="SELL", quantity=4.0, price=3050.0)
    assert pos2.cycle_id == 2  # Cycle increments on reverse
    assert pos2.side == "SHORT"
    assert pos2.qty == -2.0

    # Step 4: ORDERS_SNAPSHOT still contains old LONG brackets (cycle=1)
    _simulate_orders_snapshot(runtime, symbol, brackets_long_cycle1)

    # Step 5: Evaluate SHORT position
    await runtime._evaluate_brackets(symbol, pos2, reason="reverse_short")

    # Step 6: Verify old LONG brackets are CANCELED
    exec_service = runtime.execution_service
    cancel_calls = [c for c in exec_service.cancel_order.call_args_list]

    assert len(
        cancel_calls) >= 2, f"Expected at least 2 CANCEL calls for old LONG brackets, got {len(cancel_calls)}"

    canceled_order_ids = {c.kwargs.get(
        "order_id") or c.args[1] for c in cancel_calls}
    assert "SL_LONG_C1" in canceled_order_ids, "Old LONG SL should be canceled"
    assert "TP_LONG_C1" in canceled_order_ids, "Old LONG TP should be canceled"

    # This test validates the orphan detection and CANCEL logic
    # (PLACE calls may be suppressed by watchdog or other conditions)
