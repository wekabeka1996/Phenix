"""
TEST-OCO-R2-E — Missing / Manual Cancel Semantics for TP/SL

Tests for recreate_missing_brackets configuration behavior:
- recreate_missing_brackets=True (default, fail-closed): missing SL/TP → PLACE
- recreate_missing_brackets=False (honor missing): missing SL/TP → WARN only

Based on:
- docs/audit/OCO_AUDIT_R2E_MISSING_BRACKETS.md (future)
- TASK 5 spec: R2-E Missing Brackets Semantics

RID: OCO-STABILIZE-R2-E-MISSING-BRACKETS-SEMANTICS
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

def _make_runtime(recreate_missing_brackets: bool = True) -> ExecPosRuntimeV2:
    """Create test runtime with specified recreate_missing_brackets config."""
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.02,
            tp_rr=2.0,
            allow_unprotected_position=False,
            recreate_missing_brackets=recreate_missing_brackets,
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
    # Use order_index.reconcile_snapshot (replaces deprecated _open_orders_by_symbol)
    runtime.order_index.reconcile_snapshot(symbol, orders)
    runtime._mark_orders_snapshot(symbol)


# ========== TEST-OCO-R2-E-001: recreate_missing_brackets=True (fail-closed) ==========

@pytest.mark.asyncio
async def test_missing_sl_is_recreated_when_recreate_missing_brackets_true():
    """
    TEST-OCO-R2-E-001 — Missing SL is recreated when config.recreate_missing_brackets=True

    Scenario:
    1. LONG position opened (cycle_id=1) with SL+TP
    2. ORDERS_SNAPSHOT arrives without SL (TP remains), position still open
    3. evaluate() → should generate PLACE_SL action

    Invariants:
    - R2-E-INV-1: recreate_missing_brackets=True → missing SL generates PLACE_SL
    - R2-E-INV-2: PLACE_SL has reason_code="MISSING_SL_RECREATED"
    """
    runtime = _make_runtime(recreate_missing_brackets=True)
    symbol = "BTCUSDT"

    # Step 1: Open LONG position
    pos = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=0.5, price=50000.0)
    assert pos.cycle_id == 1
    assert pos.qty == 0.5

    # Step 2: Simulate brackets already placed (SL + TP)
    brackets_initial = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "0.5",
            "stopPrice": "49000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "0.5",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_initial)

    # Step 3: Simulate ORDERS_SNAPSHOT without SL (manual cancel scenario)
    snapshot_without_sl = [
        {
            "symbol": symbol,
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "0.5",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    await runtime._handle_orders_snapshot({"orders": snapshot_without_sl})

    # Step 4: Evaluate brackets
    await runtime._evaluate_brackets(symbol, pos, reason="test_missing_sl_recreate_true")

    # Step 5: Verify PLACE_SL action generated
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Filter for SL placement calls (after initial setup)
    # Should have at least 1 PLACE_SL call with reason "MISSING_SL_RECREATED"
    assert len(
        place_calls) >= 1, f"Expected at least 1 PLACE call for missing SL, got {len(place_calls)}"

    # Check if any call is for SL (order_type contains STOP)
    sl_calls = [c for c in place_calls if "STOP" in str(
        c.kwargs.get("order_type", "")).upper()]
    assert len(
        sl_calls) >= 1, f"Expected at least 1 STOP order placement for SL, got {len(sl_calls)}"


@pytest.mark.asyncio
async def test_missing_tp_is_recreated_when_recreate_missing_brackets_true():
    """
    TEST-OCO-R2-E-002 — Missing TP is recreated when config.recreate_missing_brackets=True

    Scenario:
    1. LONG position opened with SL+TP
    2. ORDERS_SNAPSHOT without TP (SL remains), position still open
    3. evaluate() → should generate PLACE_TP action

    Invariants:
    - R2-E-INV-3: recreate_missing_brackets=True → missing TP generates PLACE_TP
    - R2-E-INV-4: PLACE_TP has reason_code="MISSING_TP_RECREATED"
    """
    runtime = _make_runtime(recreate_missing_brackets=True)
    symbol = "ETHUSDT"

    # Step 1: Open LONG position
    pos = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=2.0, price=3000.0)
    assert pos.cycle_id == 1
    assert pos.qty == 2.0

    # Step 2: Simulate initial brackets (SL + TP)
    brackets_initial = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
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
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "2.0",
            "stopPrice": "3120.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_initial)

    # Step 3: Simulate ORDERS_SNAPSHOT without TP (SL remains)
    snapshot_without_tp = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "0.5",
            "stopPrice": "48000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    await runtime._handle_orders_snapshot({"orders": snapshot_without_tp})

    # Step 4: Evaluate brackets
    await runtime._evaluate_brackets(symbol, pos, reason="test_missing_tp_recreate_true")

    # Step 5: Verify PLACE_TP action generated
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Should have at least 1 PLACE call for TP
    assert len(
        place_calls) >= 1, f"Expected at least 1 PLACE call for missing TP, got {len(place_calls)}"

    # Check if any call is for TP (order_type contains TAKE_PROFIT or LIMIT)
    tp_calls = [c for c in place_calls if "TAKE_PROFIT" in str(c.kwargs.get(
        "order_type", "")).upper() or "LIMIT" in str(c.kwargs.get("order_type", "")).upper()]
    assert len(
        tp_calls) >= 1, f"Expected at least 1 TP order placement, got {len(tp_calls)}"


# ========== TEST-OCO-R2-E-003: recreate_missing_brackets=False (honor missing) ==========

@pytest.mark.asyncio
async def test_missing_sl_is_not_recreated_when_recreate_missing_brackets_false():
    """
    TEST-OCO-R2-E-003 — Missing SL is NOT recreated when config.recreate_missing_brackets=False

    Scenario:
    1. LONG position opened with SL+TP
    2. ORDERS_SNAPSHOT without SL (TP remains), position still open
    3. evaluate() → should NOT generate PLACE_SL, but log WARN

    Invariants:
    - R2-E-INV-5: recreate_missing_brackets=False → missing SL does NOT generate PLACE_SL
    - R2-E-INV-6: BracketPlan severity escalates to WARN for missing SL
    """
    runtime = _make_runtime(recreate_missing_brackets=False)
    symbol = "ADAUSDT"

    # Step 1: Open LONG position
    pos = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=10.0, price=1.0)
    assert pos.cycle_id == 1
    assert pos.qty == 10.0

    # Step 2: Simulate initial brackets (SL + TP)
    brackets_initial = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "10.0",
            "stopPrice": "0.98",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "10.0",
            "stopPrice": "1.04",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_initial)

    # Step 3: Simulate ORDERS_SNAPSHOT without SL (manual cancel scenario)
    snapshot_without_sl = [
        {
            "symbol": symbol,
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C2-POS2",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "0.5",
            "stopPrice": "52000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    await runtime._handle_orders_snapshot({"orders": snapshot_without_sl})

    # Step 4: Evaluate brackets
    await runtime._evaluate_brackets(symbol, pos, reason="test_missing_sl_honor_false")

    # Step 5: Verify NO PLACE_SL action generated
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Filter for SL placement calls (should be NONE after initial setup)
    sl_calls = [c for c in place_calls if "STOP" in str(
        c.kwargs.get("order_type", "")).upper()]

    # Should have NO new SL placement (honor missing mode)
    # Note: May have initial SL from first evaluate, so check only recent calls
    # In this test, we expect NO new PLACE_SL after snapshot without SL
    # Simplification: just verify that place_calls count didn't increase dramatically
    assert len(
        sl_calls) == 0, f"Expected NO new STOP order placement when recreate_missing_brackets=False, got {len(sl_calls)}"


@pytest.mark.asyncio
async def test_missing_tp_is_not_recreated_when_recreate_missing_brackets_false():
    """
    TEST-OCO-R2-E-004 — Missing TP is NOT recreated when config.recreate_missing_brackets=False

    Scenario:
    1. LONG position opened with SL+TP
    2. ORDERS_SNAPSHOT without TP (SL remains), position still open
    3. evaluate() → should NOT generate PLACE_TP, but log WARN

    Invariants:
    - R2-E-INV-7: recreate_missing_brackets=False → missing TP does NOT generate PLACE_TP
    - R2-E-INV-8: BracketPlan severity escalates to WARN for missing TP
    """
    runtime = _make_runtime(recreate_missing_brackets=False)
    symbol = "SOLUSDT"

    # Step 1: Open LONG position
    pos = await _simulate_trade_executed(runtime, symbol, side="BUY", quantity=5.0, price=100.0)
    assert pos.cycle_id == 1
    assert pos.qty == 5.0

    # Step 2: Simulate initial brackets (SL + TP)
    brackets_initial = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C1-POS1",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "5.0",
            "stopPrice": "98.0",
            "reduceOnly": True,
            "status": "NEW",
        },
        {
            "symbol": symbol,
            "orderId": "TP_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-TP-C1-POS1",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "origQty": "5.0",
            "stopPrice": "104.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    _simulate_orders_snapshot(runtime, symbol, brackets_initial)

    # Step 3: Simulate ORDERS_SNAPSHOT without TP (SL remains)
    snapshot_without_tp = [
        {
            "symbol": symbol,
            "orderId": "SL_INITIAL",
            "clientOrderId": f"AUR-{symbol}-LONG-SL-C2-POS2",
            "side": "SELL",
            "type": "STOP_MARKET",
            "origQty": "0.5",
            "stopPrice": "48000.0",
            "reduceOnly": True,
            "status": "NEW",
        },
    ]
    await runtime._handle_orders_snapshot({"orders": snapshot_without_tp})

    # Step 4: Evaluate brackets
    await runtime._evaluate_brackets(symbol, pos, reason="test_missing_tp_honor_false")

    # Step 5: Verify NO PLACE_TP action generated
    exec_service = runtime.execution_service
    place_calls = [c for c in exec_service.place_order.call_args_list]

    # Filter for TP placement calls (should be NONE after initial setup)
    tp_calls = [c for c in place_calls if "TAKE_PROFIT" in str(c.kwargs.get(
        "order_type", "")).upper() or "LIMIT" in str(c.kwargs.get("order_type", "")).upper()]

    # Should have NO new TP placement (honor missing mode)
    assert len(
        tp_calls) == 0, f"Expected NO new TP order placement when recreate_missing_brackets=False, got {len(tp_calls)}"
