"""
TEST-EXEC-R2-G — Fill Metrics & Telemetry

Tests for ExecPos fill processing metrics:
- fills_total: Total fills seen (including zero/duplicate)
- fills_abs_normalized_total: Fills where qty was normalized from negative
- fills_zero_ignored_total: Fills with zero qty (ignored)
- fills_signed_qty_seen_total: Fills with negative raw qty

Based on:
- TASK 7 spec: R2-G Fill Metrics
- Build on R2-F qty normalization (TASK 6)

RID: EXEC-R2-G-FILL-METRICS
"""
import time
from decimal import Decimal
from typing import Dict, Any
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
    """Create test runtime for metrics testing."""
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


# ========== TEST 1: Positive fill metrics ==========

@pytest.mark.asyncio
async def test_metrics_increment_on_positive_fill():
    """
    TEST-EXEC-R2-G-001 — Positive fill increments fills_total only

    Scenario:
    - FLAT position on ETHUSDT
    - TRADE_EXECUTED with quantity="2.5" (positive)
    - side="BUY"

    Expected Metrics:
    - fills_total == 1 (saw one fill)
    - fills_abs_normalized_total == 0 (no normalization needed)
    - fills_signed_qty_seen_total == 0 (qty was positive)
    - fills_zero_ignored_total == 0 (qty non-zero)

    Invariants:
    - R2-G-INV-1: fills_total increments for all fills (positive/negative/zero)
    - R2-G-INV-2: Positive qty does NOT increment signed_qty_seen or abs_normalized
    """
    runtime = _make_runtime()
    symbol = "ETHUSDT"

    # Check initial metrics (should be zero)
    initial_metrics = runtime.get_metrics()
    assert initial_metrics["fills_total"] == 0
    assert initial_metrics["fills_abs_normalized_total"] == 0
    assert initial_metrics["fills_signed_qty_seen_total"] == 0
    assert initial_metrics["fills_zero_ignored_total"] == 0

    # Simulate TRADE_EXECUTED with POSITIVE qty
    trade_payload = {
        "symbol": symbol,
        "side": "BUY",
        "quantity": "2.5",  # ← POSITIVE qty
        "qty": "2.5",
        "price": "3000.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_ETH_POSITIVE",
        "exchangeOrderId": "EXCH_ORDER_123",
    }

    await runtime._handle_trade_executed(symbol, trade_payload)

    # Check metrics after positive fill
    metrics = runtime.get_metrics()
    assert metrics["fills_total"] == 1, "fills_total should increment for positive fill"
    assert metrics["fills_abs_normalized_total"] == 0, \
        "fills_abs_normalized_total should NOT increment for positive qty"
    assert metrics["fills_signed_qty_seen_total"] == 0, \
        "fills_signed_qty_seen_total should NOT increment for positive qty"
    assert metrics["fills_zero_ignored_total"] == 0, \
        "fills_zero_ignored_total should NOT increment for non-zero qty"

    # Verify position updated correctly
    position = runtime._positions_by_symbol.get(symbol)
    assert position is not None
    assert abs(position.qty - 2.5) < 0.001


# ========== TEST 2: Negative fill metrics ==========

@pytest.mark.asyncio
async def test_metrics_increment_on_negative_fill_and_normalization():
    """
    TEST-EXEC-R2-G-002 — Negative fill increments signed_qty_seen + abs_normalized

    Scenario:
    - FLAT position on BNBUSDT
    - TRADE_EXECUTED with quantity="-0.07" (negative, real-world case)
    - side="SELL"

    Expected Metrics:
    - fills_total == 1
    - fills_signed_qty_seen_total == 1 (raw_qty < 0)
    - fills_abs_normalized_total == 1 (qty normalized from negative)
    - fills_zero_ignored_total == 0 (qty non-zero after abs)

    Invariants:
    - R2-G-INV-3: Negative raw qty increments fills_signed_qty_seen_total
    - R2-G-INV-4: Normalization (qty != raw_qty) increments fills_abs_normalized_total
    """
    runtime = _make_runtime()
    symbol = "BNBUSDT"

    # Simulate TRADE_EXECUTED with NEGATIVE qty (observed issue from R2-F)
    trade_payload = {
        "symbol": symbol,
        "side": "SELL",
        "quantity": "-0.07",  # ← NEGATIVE qty (signed from WS)
        "qty": "-0.07",
        "price": "600.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_BNB_NEGATIVE",
        "exchangeOrderId": "EXCH_ORDER_456",
    }

    await runtime._handle_trade_executed(symbol, trade_payload)

    # Check metrics after negative fill
    metrics = runtime.get_metrics()
    assert metrics["fills_total"] == 1, "fills_total should increment for negative fill"
    assert metrics["fills_signed_qty_seen_total"] == 1, \
        "fills_signed_qty_seen_total should increment when raw_qty < 0"
    assert metrics["fills_abs_normalized_total"] == 1, \
        "fills_abs_normalized_total should increment when qty normalized from negative"
    assert metrics["fills_zero_ignored_total"] == 0, \
        "fills_zero_ignored_total should NOT increment for non-zero qty"

    # Verify position updated correctly (SHORT -0.07)
    position = runtime._positions_by_symbol.get(symbol)
    assert position is not None
    assert abs(abs(position.qty) - 0.07) < 0.001
    assert position.side == "SHORT"


# ========== TEST 3: Zero fill metrics ==========

@pytest.mark.asyncio
async def test_zero_qty_fill_increments_zero_ignored_metric():
    """
    TEST-EXEC-R2-G-003 — Zero qty fill increments fills_zero_ignored_total

    Scenario:
    - FLAT position on ADAUSDT
    - TRADE_EXECUTED with quantity="0.0" (zero, noise event)

    Expected Metrics:
    - fills_total == 1 (saw fill event)
    - fills_zero_ignored_total == 1 (fill ignored due to zero qty)
    - fills_abs_normalized_total == 0 (no normalization for zero)
    - fills_signed_qty_seen_total == 0 (zero is not negative)
    - Position remains FLAT (fill ignored)

    Invariants:
    - R2-G-INV-5: Zero fills increment fills_total + fills_zero_ignored_total
    - R2-G-INV-6: Zero fills do NOT change position state
    """
    runtime = _make_runtime()
    symbol = "ADAUSDT"

    # Simulate TRADE_EXECUTED with ZERO qty
    trade_payload = {
        "symbol": symbol,
        "side": "BUY",
        "quantity": "0.0",  # ← ZERO qty
        "qty": "0.0",
        "price": "1.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "TEST_ORDER_ADA_ZERO",
        "exchangeOrderId": "EXCH_ORDER_789",
    }

    await runtime._handle_trade_executed(symbol, trade_payload)

    # Check metrics after zero fill
    metrics = runtime.get_metrics()
    assert metrics["fills_total"] == 1, "fills_total should increment even for zero qty"
    assert metrics["fills_zero_ignored_total"] == 1, \
        "fills_zero_ignored_total should increment when qty == 0"
    assert metrics["fills_abs_normalized_total"] == 0, \
        "fills_abs_normalized_total should NOT increment for zero qty"
    assert metrics["fills_signed_qty_seen_total"] == 0, \
        "fills_signed_qty_seen_total should NOT increment for zero qty (not negative)"

    # Verify position remains FLAT (zero fill ignored)
    position = runtime._positions_by_symbol.get(symbol)
    assert position is None or abs(position.qty) < 0.0001, \
        "Position should remain FLAT after zero fill"


# ========== TEST 4: Multiple fills accumulate metrics ==========

@pytest.mark.asyncio
async def test_multiple_fills_accumulate_metrics_correctly():
    """
    TEST-EXEC-R2-G-004 — Multiple fills accumulate metrics correctly

    Scenario:
    - 3 fills on SOLUSDT:
      1. BUY +1.0 (positive)
      2. SELL -0.5 (negative)
      3. BUY +0.0 (zero)

    Expected Metrics:
    - fills_total == 3
    - fills_signed_qty_seen_total == 1 (only fill #2 negative)
    - fills_abs_normalized_total == 1 (only fill #2 normalized)
    - fills_zero_ignored_total == 1 (only fill #3 zero)
    """
    runtime = _make_runtime()
    symbol = "SOLUSDT"

    # Fill 1: BUY +1.0 (positive)
    await runtime._handle_trade_executed(symbol, {
        "symbol": symbol,
        "side": "BUY",
        "quantity": "1.0",
        "qty": "1.0",
        "price": "100.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "ORDER_1",
        "exchangeOrderId": "EXCH_1",
    })

    # Fill 2: SELL -0.5 (negative)
    await runtime._handle_trade_executed(symbol, {
        "symbol": symbol,
        "side": "SELL",
        "quantity": "-0.5",
        "qty": "-0.5",
        "price": "102.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "ORDER_2",
        "exchangeOrderId": "EXCH_2",
    })

    # Fill 3: BUY +0.0 (zero)
    await runtime._handle_trade_executed(symbol, {
        "symbol": symbol,
        "side": "BUY",
        "quantity": "0.0",
        "qty": "0.0",
        "price": "101.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "ORDER_3",
        "exchangeOrderId": "EXCH_3",
    })

    # Check accumulated metrics
    metrics = runtime.get_metrics()
    assert metrics["fills_total"] == 3, "fills_total should be 3 (all fills counted)"
    assert metrics["fills_signed_qty_seen_total"] == 1, \
        "fills_signed_qty_seen_total should be 1 (only fill #2 negative)"
    assert metrics["fills_abs_normalized_total"] == 1, \
        "fills_abs_normalized_total should be 1 (only fill #2 normalized)"
    assert metrics["fills_zero_ignored_total"] == 1, \
        "fills_zero_ignored_total should be 1 (only fill #3 zero)"


# ========== TEST 5: get_metrics() returns all fill metrics ==========

def test_get_metrics_includes_all_fill_metrics():
    """
    TEST-EXEC-R2-G-005 — get_metrics() includes all R2-G fill metrics

    Scenario:
    - Create fresh runtime
    - Call get_metrics()

    Expected:
    - Metrics dict contains all 4 R2-G fill metrics with initial value 0

    Invariants:
    - R2-G-INV-7: get_metrics() exposes fills_total/abs_normalized/zero_ignored/signed_qty_seen
    """
    runtime = _make_runtime()
    metrics = runtime.get_metrics()

    # Verify all R2-G metrics present with initial value 0
    assert "fills_total" in metrics, "fills_total should be in metrics dict"
    assert "fills_abs_normalized_total" in metrics, \
        "fills_abs_normalized_total should be in metrics dict"
    assert "fills_zero_ignored_total" in metrics, \
        "fills_zero_ignored_total should be in metrics dict"
    assert "fills_signed_qty_seen_total" in metrics, \
        "fills_signed_qty_seen_total should be in metrics dict"

    # Check initial values
    assert metrics["fills_total"] == 0
    assert metrics["fills_abs_normalized_total"] == 0
    assert metrics["fills_zero_ignored_total"] == 0
    assert metrics["fills_signed_qty_seen_total"] == 0


# ========== TEST 6: Metrics survive multiple symbols ==========

@pytest.mark.asyncio
async def test_metrics_aggregate_across_symbols():
    """
    TEST-EXEC-R2-G-006 — Metrics aggregate across multiple symbols

    Scenario:
    - Fill on BTCUSDT: positive qty
    - Fill on ETHUSDT: negative qty
    - Fill on BNBUSDT: zero qty

    Expected:
    - fills_total == 3 (all symbols counted together)
    - fills_signed_qty_seen_total == 1 (ETHUSDT negative)
    - fills_abs_normalized_total == 1 (ETHUSDT normalized)
    - fills_zero_ignored_total == 1 (BNBUSDT zero)

    Invariants:
    - R2-G-INV-8: Metrics are runtime-level (not per-symbol)
    """
    runtime = _make_runtime()

    # BTCUSDT: positive
    await runtime._handle_trade_executed("BTCUSDT", {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.1",
        "qty": "0.1",
        "price": "50000.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "BTC_ORDER",
        "exchangeOrderId": "BTC_EXCH",
    })

    # ETHUSDT: negative
    await runtime._handle_trade_executed("ETHUSDT", {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "quantity": "-2.0",
        "qty": "-2.0",
        "price": "3000.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "ETH_ORDER",
        "exchangeOrderId": "ETH_EXCH",
    })

    # BNBUSDT: zero
    await runtime._handle_trade_executed("BNBUSDT", {
        "symbol": "BNBUSDT",
        "side": "BUY",
        "quantity": "0.0",
        "qty": "0.0",
        "price": "600.0",
        "timestamp": int(time.time() * 1000),
        "venue": "binance_ws_testnet",
        "clientOrderId": "BNB_ORDER",
        "exchangeOrderId": "BNB_EXCH",
    })

    # Check aggregated metrics
    metrics = runtime.get_metrics()
    assert metrics["fills_total"] == 3
    assert metrics["fills_signed_qty_seen_total"] == 1  # ETHUSDT
    assert metrics["fills_abs_normalized_total"] == 1  # ETHUSDT
    assert metrics["fills_zero_ignored_total"] == 1  # BNBUSDT
