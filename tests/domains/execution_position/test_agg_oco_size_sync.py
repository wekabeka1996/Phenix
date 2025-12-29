"""
TEST-OCO-R1-001..004 — Aggregated OCO Size Synchronization Tests

Tests for size invariants between position qty and bracket qty:
- Partial close reduces bracket qty (TEST-OCO-R1-001)
- Scale-in recomputes price and qty (TEST-OCO-R1-002)
- Reverse cancels previous side brackets (TEST-OCO-R1-003)
- Partial close via TP/SL fill respects size invariants (TEST-OCO-R1-004)

Based on:
- docs/audit/OCO_AUDIT_R1B_SIZE_SYNC.md
- docs/audit/OCO_AUDIT_R1D_TESTPLAN.md

RID: OCO-AUDIT-R1-TEST-SIZE-SYNC
"""
import time
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketService,
    BracketRulesConfig,
    PositionView,
    OrderView,
)
from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)


# ========== Test Fixtures ==========

def _make_runtime(
    sl_pct: float = 0.02,
    tp_rr: float = 2.0,
    allow_unprotected_position: bool = False
) -> ExecPosRuntimeV2:
    """
    Create test runtime with mock ExecutionService.
    """
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
            allow_unprotected_position=allow_unprotected_position,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=30.0, position_ttl_sec=30.0),
    )
    rt = ExecPosRuntimeV2(config={}, adapter=None,
                          price_service=None, ep_config=ep_cfg)

    # Mock ExecutionService to avoid real Binance calls
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


def _simulate_orders_snapshot(runtime: ExecPosRuntimeV2, symbol: str, orders: List[Dict[str, Any]]):
    """
    Simulate ORDERS_SNAPSHOT event.
    """
    runtime.order_index.reconcile_snapshot(symbol, orders)
    runtime._mark_orders_snapshot(symbol)


def _simulate_trade_executed(runtime: ExecPosRuntimeV2, symbol: str, side: str, quantity: float, price: float):
    """
    Simulate TRADE_EXECUTED event and update position.
    R2-B: Also tracks prev_position for reverse detection.
    """
    from apps.reference.domains.execution_position.shadow_execpos.position_model import apply_fill

    current_state = runtime._positions_by_symbol.get(symbol)
    if not current_state:
        current_state = PositionState(
            symbol=symbol, qty=0.0, avg_entry_price=0.0)

    # R2-B: Save prev state for reverse detection (matches runtime behavior)
    if abs(current_state.qty) > 0.0001:
        runtime._prev_positions_by_symbol[symbol] = current_state

    new_state = apply_fill(
        state=current_state,
        side=side,
        quantity=quantity,
        price=price,
        ts=time.time(),
    )
    runtime._positions_by_symbol[symbol] = new_state
    return new_state


def _get_orders_as_dicts(runtime: ExecPosRuntimeV2, symbol: str) -> List[Dict[str, Any]]:
    """Helper to get orders from OrderIndex as dicts."""
    refs = runtime.order_index.get_by_symbol(symbol)
    return [ref.to_dict() for ref in refs]


# ========== TEST-OCO-R1-001: Partial close reduces bracket qty ==========

@pytest.mark.asyncio
async def test_oco_partial_close_brackets_do_not_exceed_position_qty():
    """
    TEST-OCO-R1-001 — Partial close reduces bracket qty

    Invariants: R1-B-INV-1, R1-B-INV-3, R1-C-RISK-3

    Given:
      - LONG position qty=2.0, avg_entry_price=100.0
      - Active SL/TP: SELL reduceOnly, quantity=2.0
      - FRESH ORDERS_SNAPSHOT

    When:
      - Partial close fill TRADE_EXECUTED SELL quantity=0.5 @ 102.0
      - Triggers _evaluate_brackets(reason="trade_executed")

    Then (EXPECTED — currently FAILS):
      - BracketPlan ensures sum(bracket_qty) ≤ abs(position_qty_after)
      - No remaining SL/TP that exceed position size

    CURRENT BEHAVIOR (bug):
      - Position qty reduces to 1.5
      - BUT: existing SL/TP remain at qty=2.0 each
      - sum(bracket_qty) = 4.0 > position_qty = 1.5 ❌
    """
    runtime = _make_runtime(sl_pct=0.02, tp_rr=2.0)
    symbol = "SOLUSDT"

    # Step 1: Setup initial LONG position
    _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=100.0)

    # Step 2: Simulate existing SL/TP on exchange
    existing_orders = [
        {
            "symbol": symbol,
            "orderId": "SL_123",
            "clientOrderId": "AUR-BRK-SL-123",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "98.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_456",
            "clientOrderId": "AUR-BRK-TP-456",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "104.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, existing_orders)

    # Step 3: Partial close — SELL 0.5
    new_state = _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=0.5, price=102.0)

    assert abs(new_state.qty) == 1.5, "Position qty should be 1.5"

    # Step 4: Trigger bracket evaluation
    await runtime._evaluate_brackets(symbol, new_state, reason="trade_executed")

    # Step 5: Check invariants (EXPECTED TO FAIL currently)
    # After evaluation, sum of bracket qty should NOT exceed position qty
    current_orders = _get_orders_as_dicts(runtime, symbol)

    sl_orders = [o for o in current_orders if o.get("type") in (
        "STOP_MARKET", "STOP") and o.get("reduceOnly")]
    tp_orders = [o for o in current_orders if o.get("type") in (
        "TAKE_PROFIT_MARKET", "TAKE_PROFIT") and o.get("reduceOnly")]

    total_sl_qty = sum(float(o.get("origQty", 0) or o.get("quantity", 0)) for o in sl_orders)
    total_tp_qty = sum(float(o.get("origQty", 0) or o.get("quantity", 0)) for o in tp_orders)

    # THIS WILL FAIL with current implementation:
    # Expected: total_sl_qty <= 1.5 and total_tp_qty <= 1.5
    # Actual: total_sl_qty = 2.0, total_tp_qty = 2.0 (no recalc happened)

    assert total_sl_qty <= abs(new_state.qty), \
        f"SL qty {total_sl_qty} exceeds position qty {abs(new_state.qty)} (R1-B-INV-1 violated)"

    assert total_tp_qty <= abs(new_state.qty), \
        f"TP qty {total_tp_qty} exceeds position qty {abs(new_state.qty)} (R1-B-INV-1 violated)"


# ========== TEST-OCO-R1-002: Scale-in recomputes price and qty ==========

@pytest.mark.asyncio
async def test_oco_scale_in_triggers_recalc_or_detects_invariant_break():
    """
    TEST-OCO-R1-002 — Scale-in recomputes price and qty

    Invariants: R1-B-INV-1, R1-B-INV-5

    Given:
      - Initial fill LONG 1.0 @ 100.0 → SL/TP on 1.0
      - _open_orders_by_symbol contains these SL/TP

    When:
      - Second fill LONG 1.0 @ 110.0 (scale-in) via TRADE_EXECUTED

    Then (EXPECTED):
      - PositionState.qty == 2.0, avg_entry_price == 105.0
      - BracketService via stale_levels generates plan:
        - CANCEL old SL/TP
        - PLACE_SL/TP on qty=2.0 with new levels

    CURRENT BEHAVIOR:
      - Scale-in should trigger stale_levels (price changed)
      - This test verifies that qty is also updated to 2.0
    """
    runtime = _make_runtime(sl_pct=0.02, tp_rr=2.0)
    symbol = "BTCUSDT"

    # Step 1: Initial LONG entry 1.0 @ 100.0
    state1 = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=1.0, price=100.0)

    # Simulate initial SL/TP placed at qty=1.0
    initial_orders = [
        {
            "symbol": symbol,
            "orderId": "SL_OLD",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "1.0",
            "stopPrice": "98.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_OLD",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "1.0",
            "stopPrice": "104.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, initial_orders)

    # Step 2: Scale-in LONG 1.0 @ 110.0
    state2 = _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=1.0, price=110.0)

    assert abs(state2.qty) == 2.0, "Position qty should be 2.0 after scale-in"
    assert abs(state2.avg_entry_price -
               105.0) < 0.01, "Avg entry price should be ~105.0"

    # Step 3: Trigger bracket evaluation
    await runtime._evaluate_brackets(symbol, state2, reason="trade_executed")

    # Step 4: Check that ExecutionService was called to place new brackets
    # (stale_levels should trigger CANCEL + PLACE)
    exec_service = runtime.execution_service

    # Verify CANCEL was called for old brackets
    cancel_calls = [c for c in exec_service.cancel_order.call_args_list]
    assert len(cancel_calls) >= 2, "Should CANCEL old SL and TP"

    # Verify PLACE was called with qty=2.0
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # At least 2 PLACE calls (SL + TP)
    assert len(place_calls) >= 2, "Should PLACE new SL and TP"

    # Check that new brackets have qty=2.0
    for call in place_calls:
        kwargs = call[1] if len(call) > 1 else call.kwargs
        if kwargs.get("close_position") or kwargs.get("closePosition"):
            qty = 2.0
        else:
            qty = float(kwargs.get("quantity") or 0)
        assert qty == 2.0, f"New bracket qty should be 2.0, got {qty}"


# ========== TEST-OCO-R1-003: Reverse cancels previous side brackets ==========

@pytest.mark.asyncio
async def test_reverse_long_to_short_leaves_no_long_brackets():
    """
    TEST-OCO-R1-003 — Reverse cancels previous side brackets and protects new side

    Invariants: R1-B-INV-4, R1-C-RISK-4

    Given:
      - LONG qty=2.0 with SL/TP SELL reduceOnly
      - Orders reflected in _open_orders_by_symbol

    When:
      - Reverse fill: SELL quantity=4.0 @ 95.0 → SHORT qty=2.0

    Then (EXPECTED — currently PARTIAL):
      - Plan includes:
        - CANCEL all SL/TP for LONG (old side)
        - PLACE_SL/TP for SHORT (new side)
      - After applying plan:
        - No active LONG-brackets on exchange or in mirror

    CURRENT BEHAVIOR (gap):
      - Runtime places new SHORT SL/TP (BUY reduceOnly) ✓
      - BUT: does NOT explicitly CANCEL old LONG SL/TP ❌
      - Cleanup relies on DR-pass or external Guardian
    """
    runtime = _make_runtime(sl_pct=0.02, tp_rr=2.0)
    symbol = "ETHUSDT"

    # Step 1: Setup LONG position
    _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=100.0)

    # Simulate LONG SL/TP (SELL reduceOnly)
    long_brackets = [
        {
            "symbol": symbol,
            "orderId": "LONG_SL",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",
            "stopPrice": "98.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "LONG_TP",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "104.0",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, long_brackets)

    # Step 2: Reverse fill — SELL 4.0 @ 95.0
    new_state = _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=4.0, price=95.0)

    assert new_state.qty == -2.0, "Position should flip to SHORT qty=-2.0"
    assert new_state.side == "SHORT", "Position side should be SHORT"

    # R2-B: Trigger reverse cleanup (matches runtime._handle_trade_executed flow)
    await runtime._handle_reverse_cleanup(symbol, new_state)

    # Step 3: Trigger bracket evaluation for new SHORT position
    await runtime._evaluate_brackets(symbol, new_state, reason="trade_executed")


    # Step 4: Check that new SHORT brackets were placed
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Should place SL/TP for SHORT (BUY reduceOnly or closePosition)
    short_brackets_placed = [
        c for c in place_calls
        if c[1].get("side") == "BUY" and (c[1].get("reduce_only") is True or c[1].get("close_position") is True)
    ]
    assert len(short_brackets_placed) >= 2, "Should place SL/TP for SHORT position"

    # Step 5: Check cleanup of old LONG brackets (EXPECTED TO FAIL)
    cancel_calls = [c for c in exec_service.cancel_order.call_args_list]

    # CURRENT BEHAVIOR: cancel_calls is likely EMPTY or does not include old LONG brackets
    # Because _evaluate_brackets with side=SHORT does not see SELL reduceOnly as compatible legs

    old_long_orders_cancelled = [
        c for c in cancel_calls
        if c[1].get("order_id") in ("LONG_SL", "LONG_TP")
    ]

    # THIS ASSERTION WILL FAIL:
    assert len(old_long_orders_cancelled) >= 2, \
        "Old LONG SL/TP should be CANCELLED during reverse (R1-B-INV-4 / R1-C-RISK-4 violated)"


# ========== TEST-OCO-R1-004: Partial close via TP/SL fill ==========

@pytest.mark.asyncio
async def test_partial_close_via_brackets_respects_size_invariants():
    """
    TEST-OCO-R1-004 — Partial close via TP/SL fill (reduceOnly)

    Invariants: R1-B-INV-1/3, R1-C-RISK-3

    Given:
      - LONG qty=2.0, SL/TP each on 2.0
      - Partial fill TP on 1.0 (reduceOnly) → position qty=1.0

    When:
      - Recovers state via POSITION_SYNC + ORDERS_SNAPSHOT (one SL/TP on 1.0, one already FILLED)
      - Triggers evaluate / guard_loop

    Then (EXPECTED):
      - BracketService does not generate overshoot (no PLACE_* with qty > 1.0)
      - Orphan orders (if any) are marked and CANCELLED

    CURRENT BEHAVIOR (gap):
      - If TP partially fills, remaining TP + full SL may still total > position_qty
      - No explicit qty-check in evaluate()
    """
    runtime = _make_runtime(sl_pct=0.02, tp_rr=2.0)
    symbol = "ADAUSDT"

    # Step 1: Setup LONG position 2.0
    _simulate_trade_executed(
        runtime, symbol, side="BUY", quantity=2.0, price=1.0)

    # Step 2: Simulate partial TP fill (1.0 filled, position now 1.0)
    state_after_tp = _simulate_trade_executed(
        runtime, symbol, side="SELL", quantity=1.0, price=1.04)

    assert abs(
        state_after_tp.qty) == 1.0, "Position should be 1.0 after partial TP fill"

    # Step 3: Simulate ORDERS_SNAPSHOT with remaining orders
    # One TP is FILLED (not in snapshot), one SL remains with qty=2.0 (bug scenario)
    remaining_orders = [
        {
            "symbol": symbol,
            "orderId": "SL_REMAINING",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "2.0",  # ❌ Still 2.0, but position is only 1.0
            "stopPrice": "0.98",
            "reduceOnly": True,
            "status": "NEW",
        }
    ]
    _simulate_orders_snapshot(runtime, symbol, remaining_orders)

    # Step 4: Trigger bracket evaluation
    await runtime._evaluate_brackets(symbol, state_after_tp, reason="guard_loop")

    # Step 5: Check invariants
    current_orders = _get_orders_as_dicts(runtime, symbol)

    sl_orders = [o for o in current_orders if o.get("type") in (
        "STOP_MARKET", "STOP") and o.get("reduceOnly")]
    total_sl_qty = sum(float(o.get("origQty", 0) or o.get("quantity", 0)) for o in sl_orders)

    # EXPECTED: total_sl_qty <= 1.0
    # CURRENT: May still be 2.0 (no recalc triggered)
    assert total_sl_qty <= abs(state_after_tp.qty), \
        f"SL qty {total_sl_qty} exceeds position qty {abs(state_after_tp.qty)} after partial TP fill (R1-B-INV-3 violated)"


# ========== Additional helper test for size invariant validation ==========

@pytest.mark.skip(reason="BracketService.__init__ requires aggregator+guardian; integration tests already document gap")
@pytest.mark.asyncio
async def test_bracket_service_detects_qty_overshoot():
    """
    Helper test — BracketService should detect when bracket qty > position qty.

    This is a unit test for BracketService.evaluate() invariant checking.
    Currently this check does NOT exist in the code.
    """
    from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketService, BracketState, BracketSet, BracketLeg

    bracket_service = BracketService()
    cfg = BracketRulesConfig(
        sl_pct=0.02,
        tp_rr=2.0,
        max_sl_legs=1,
        max_tp_legs=1,
        allow_unprotected_position=False,
    )

    # Scenario: position qty=1.0, but SL leg has qty=2.0
    position_view = PositionView(
        symbol="TESTUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
    )

    bracket_set = BracketSet(
        position_qty=Decimal("1.0"),
        legs=[
            BracketLeg(
                order_id="SL_OVERSHOOT",
                client_order_id="TEST-SL",
                leg_type="SL",
                side="SELL",
                qty=Decimal("2.0"),  # ❌ Exceeds position qty
                price=Decimal("98.0"),
                status="NEW",
            )
        ]
    )

    state = BracketState(
        symbol="TESTUSDT",
        side="LONG",
        position_view=position_view,
        bracket_set=bracket_set,
        guardian_meta=None,
    )

    # Call evaluate
    plan = bracket_service.evaluate(state, cfg)

    # EXPECTED (future implementation): plan should detect overshoot
    # CURRENT: evaluate() does NOT check sum(leg.qty) vs position_qty
    # This test documents the gap

    # For now, we just assert that plan exists (no crash)
    assert plan is not None

    # In future, we would expect:
    # assert plan.severity in ("WARN", "ALERT")
    # assert "qty_overshoot" in plan.why or "qty_mismatch" in plan.why
    # assert any(action.action_type == "CANCEL" for action in plan.actions)
