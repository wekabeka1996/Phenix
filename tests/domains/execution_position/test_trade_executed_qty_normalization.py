"""
TEST-EXEC-R2-F — TRADE_EXECUTED qty Normalization

Tests for guaranteed apply_fill behavior with signed/negative quantities:
- Negative qty in TRADE_EXECUTED payload should update position (not ignored)
- Positive qty should work as baseline
- apply_fill() directly should never ignore nonzero fills due to sign

Based on:
- TASK 6 spec: R2-F qty normalization
- Observed issue: BNB trades had quantity="-0.07" that were ignored

RID: EXEC-R2-F-TRADE-EXECUTED-QTY-NORMALIZATION
"""
import time
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import AsyncMock

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState, apply_fill
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
    """Create test runtime for TRADE_EXECUTED testing."""
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.02,
            tp_rr=2.0,
            allow_unprotected_position=False,
            recreate_missing_brackets=True,
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


# ========== TEST 1: Negative qty in TRADE_EXECUTED updates position ==========

@pytest.mark.asyncio
async def test_trade_executed_negative_qty_updates_position_state():
    """
    TEST-EXEC-R2-F-001 — TRADE_EXECUTED with negative qty updates position

    Scenario:
    - FLAT position on BNBUSDT
    - TRADE_EXECUTED event with quantity="-0.07" (negative string/Decimal)
    - side="SELL"

    Expected:
    - Position qty should become -0.07 (SHORT) or equivalent
    - Fill should NOT be ignored due to qty <= 0
    - Position state updated correctly

    Invariants:
    - apply_fill() should normalize qty to abs() internally
    - Negative qty from WS/adapter should not block fill application
    """
    runtime = _make_runtime()
    symbol = "BNBUSDT"

    # Initial state: FLAT
    assert runtime._positions_by_symbol.get(symbol) is None or \
        abs(runtime._positions_by_symbol.get(symbol).qty) < 0.0001

    # Simulate TRADE_EXECUTED with NEGATIVE qty (real-world case from BNB)
    trade_payload = {
        "symbol": symbol,
        "side": "SELL",
        "quantity": "-0.07",  # ← NEGATIVE qty (observed issue)
        "qty": "-0.07",
        "price": "600.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_BNB",
        "exchangeOrderId": "EXCH_ORDER_123",
    }

    # Process trade via runtime
    await runtime._handle_trade_executed(symbol, trade_payload)

    # Verify position updated (SHORT -0.07)
    position = runtime._positions_by_symbol.get(symbol)
    assert position is not None, "Position should exist after TRADE_EXECUTED"
    assert abs(position.qty) > 0.0001, \
        f"Position qty should be non-zero after fill with negative qty, got {position.qty}"

    # Check qty magnitude (should be ~0.07 regardless of sign encoding)
    assert abs(abs(position.qty) - 0.07) < 0.001, \
        f"Position qty magnitude should be ~0.07, got {position.qty}"

    # Check side (SELL fill → SHORT position)
    assert position.side == "SHORT", \
        f"SELL fill on FLAT should create SHORT position, got {position.side}"


# ========== TEST 2: Positive qty baseline (control test) ==========

@pytest.mark.asyncio
async def test_trade_executed_positive_qty_updates_position_state():
    """
    TEST-EXEC-R2-F-002 — TRADE_EXECUTED with positive qty updates position (baseline)

    Scenario:
    - FLAT position on ETHUSDT
    - TRADE_EXECUTED with quantity="2.5" (positive)
    - side="BUY"

    Expected:
    - Position qty should become +2.5 (LONG)
    - Normal fill processing works as expected
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Simulate TRADE_EXECUTED with POSITIVE qty (normal case)
    trade_payload = {
        "symbol": symbol,
        "side": "BUY",
        "quantity": "2.5",  # ← POSITIVE qty (baseline)
        "qty": "2.5",
        "price": "3000.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_ETH",
        "exchangeOrderId": "EXCH_ORDER_456",
    }

    await runtime._handle_trade_executed(symbol, trade_payload)

    position = runtime._positions_by_symbol.get(symbol)
    assert position is not None
    assert abs(position.qty) > 0.0001

    # Check qty magnitude
    assert abs(position.qty - 2.5) < 0.001, \
        f"Position qty should be ~2.5, got {position.qty}"

    # Check side (BUY fill → LONG position)
    assert position.side == "LONG", \
        f"BUY fill on FLAT should create LONG position, got {position.side}"


# ========== TEST 3: apply_fill() directly with negative qty ==========

def test_apply_fill_never_ignores_nonzero_fill_due_to_sign():
    """
    TEST-EXEC-R2-F-003 — apply_fill() should normalize negative qty and apply fill

    Scenario:
    - Direct call to apply_fill() with quantity=-0.05 (negative)
    - side="SELL"

    Expected:
    - Fill should be applied (qty normalized to abs internally)
    - Position should NOT remain FLAT
    - No silent ignore due to qty <= 0 check

    This is a UNIT test for apply_fill() to ensure core logic handles signed qty.
    """
    # Start with FLAT position
    flat_state = PositionState(symbol="ADAUSDT")
    assert abs(flat_state.qty) < 0.0001

    # Apply fill with NEGATIVE quantity
    new_state = apply_fill(
        flat_state,
        side="SELL",
        quantity=-0.05,  # ← NEGATIVE qty passed directly
        price=1.0,
        ts=time.time(),
    )

    # Verify fill was NOT ignored
    assert abs(new_state.qty) > 0.0001, \
        f"apply_fill() should not ignore negative qty, but position remains FLAT: {new_state.qty}"

    # Check magnitude (should be ~0.05)
    assert abs(abs(new_state.qty) - 0.05) < 0.001, \
        f"Fill qty magnitude should be ~0.05, got {new_state.qty}"

    # Check side (SELL → SHORT)
    assert new_state.side == "SHORT", \
        f"SELL fill should create SHORT position, got {new_state.side}"


# ========== TEST 4: Multiple negative fills accumulate correctly ==========

def test_apply_fill_multiple_negative_fills_accumulate():
    """
    TEST-EXEC-R2-F-004 — Multiple negative qty fills accumulate correctly

    Scenario:
    - Start FLAT
    - Apply fill: quantity=-0.03, side="SELL"
    - Apply fill: quantity=-0.04, side="SELL"

    Expected:
    - Position qty should be -0.07 (or equivalent SHORT representation)
    - Both fills applied correctly despite negative qty
    """
    state = PositionState(symbol="SOLUSDT")

    # First fill: -0.03
    state = apply_fill(state, side="SELL", quantity=-
                       0.03, price=100.0, ts=time.time())
    assert abs(abs(state.qty) - 0.03) < 0.001, \
        f"First fill should result in ~0.03 magnitude, got {state.qty}"

    # Second fill: -0.04
    state = apply_fill(state, side="SELL", quantity=-
                       0.04, price=102.0, ts=time.time())
    assert abs(abs(state.qty) - 0.07) < 0.001, \
        f"Second fill should accumulate to ~0.07 magnitude, got {state.qty}"

    assert state.side == "SHORT"


# ========== TEST 5: Zero qty is still ignored (sanity check) ==========

def test_apply_fill_zero_qty_is_ignored():
    """
    TEST-EXEC-R2-F-005 — Zero qty fills should still be ignored (sanity check)

    Scenario:
    - FLAT position
    - Apply fill with quantity=0.0

    Expected:
    - Position remains FLAT (zero fills are noise, not real trades)
    - This confirms we don't break the zero-qty guard
    """
    state = PositionState(symbol="BTCUSDT")

    # Apply zero fill
    new_state = apply_fill(state, side="BUY", quantity=0.0,
                           price=50000.0, ts=time.time())

    # Should remain FLAT
    assert abs(new_state.qty) < 0.0001, \
        "Zero qty fill should not change position"


# ========== TEST 6: Positive and negative mix (scale-in/out with signed fills) ==========

def test_apply_fill_positive_and_negative_mix():
    """
    TEST-EXEC-R2-F-006 — Mix of positive and negative qty fills works correctly

    Scenario:
    - Start FLAT
    - BUY +1.0 (positive qty)
    - BUY -0.5 (negative qty, but side=BUY → should scale in, not close)
    - SELL +0.3 (positive qty → partial close)

    Expected:
    - Position should scale correctly based on side, not qty sign
    - Final qty reflects all fills applied with abs normalization
    """
    state = PositionState(symbol="DOTUSDT")

    # BUY +1.0 (normal)
    state = apply_fill(state, side="BUY", quantity=1.0,
                       price=10.0, ts=time.time())
    assert abs(state.qty - 1.0) < 0.001

    # BUY -0.5 (negative qty, but BUY side → scale in LONG)
    state = apply_fill(state, side="BUY", quantity=-
                       0.5, price=10.5, ts=time.time())
    # Negative qty should be normalized to abs, so BUY +0.5 → total 1.5
    assert abs(state.qty - 1.5) < 0.001, \
        f"BUY with negative qty should scale in as BUY +abs(qty), got {state.qty}"

    # SELL +0.3 (partial close)
    state = apply_fill(state, side="SELL", quantity=0.3,
                       price=11.0, ts=time.time())
    assert abs(state.qty - 1.2) < 0.001


# ========== TEST 7: Adapter payload with raw negative qty is normalized ==========

@pytest.mark.asyncio
async def test_adapter_payload_with_raw_negative_qty_normalized():
    """
    TEST-EXEC-R2-F-007 — Adapter-generated payload with raw negative qty is normalized

    Scenario:
    - Simulate adapter emitting TRADE_EXECUTED with raw_cum_qty="-0.15"
    - But quantity field is normalized to abs

    Expected:
    - Runtime should handle both quantity (abs) and raw_cum_qty (signed)
    - Position updated with abs qty, side determines direction
    """
    runtime = _make_runtime()
    symbol = "LINKUSDT"

    trade_payload = {
        "symbol": symbol,
        "side": "SELL",
        "quantity": "0.15",  # ← Normalized abs qty (from adapter)
        "qty": "0.15",
        "raw_cum_qty": "-0.15",  # ← Raw signed qty (for audit/debugging)
        "price": "15.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_LINK",
        "exchangeOrderId": "EXCH_ORDER_789",
    }

    await runtime._handle_trade_executed(symbol, trade_payload)

    position = runtime._positions_by_symbol.get(symbol)
    assert position is not None
    assert abs(abs(position.qty) - 0.15) < 0.001
    assert position.side == "SHORT"
