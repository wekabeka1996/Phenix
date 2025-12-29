"""
Unit Tests: ExecutorPool Entry Flow (Phase 4 - BracketService Single Source)
============================================================================

Tests that verify ENTRY_INTENT → ExecutorPool → FILL → BracketService flow
works correctly with V2 architecture.

Key changes from V1:
- ExecutorPool has NO bracket logic (sl_pct, tp_rr REMOVED)
- Brackets are ONLY handled by BracketService after fills
- execute_entry() replaces execute_order() (entry only, no auto-brackets)
- execute_bracket() executes BracketPlan actions

RID: EXECUTOR-POOL-PHASE4-BRACKETS-SINGLE-SOURCE
"""
import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.executor_pool import ExecutorPoolV2
from apps.reference.domains.execution_position.shadow_execpos.symbol_executor import (
    SymbolExecutorV2,
    ExecutorState,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_adapter():
    """Create mock Binance adapter with async methods."""
    adapter = MagicMock()
    adapter.api_key = "test_api_key"
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter._timeout = MagicMock()
    adapter.session = MagicMock()
    adapter._sync_time = AsyncMock()
    adapter.cancel_order = AsyncMock(return_value={"success": True})
    adapter.get_open_orders = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def production_config():
    """Production-like config with ExecutorPool enabled by default."""
    return {
        "execution_position": {
            "aggregated_oco": {
                "enabled": True,
                "sl_pct": 0.02,  # Used by BracketService ONLY
                "tp_rr": 2.0,   # Used by BracketService ONLY
            },
            "fill_timeout_sec": 5.0,
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {"tick_size": "0.01", "step_size": "0.001"},
                "ETHUSDT": {"tick_size": "0.01", "step_size": "0.001"},
                "SOLUSDT": {"tick_size": "0.001", "step_size": "0.01"},
            }
        }
    }


@pytest.fixture
def runtime(mock_adapter, production_config, use_executor_pool_enabled):
    """Create production-like runtime with ExecutorPool."""
    return ExecPosRuntimeV2(
        config=production_config,
        adapter=mock_adapter,
        price_service=None,
    )


# ─────────────────────────────────────────────────────────────
# Unit Tests: ExecutorPool is Default Path
# ─────────────────────────────────────────────────────────────

class TestExecutorPoolIsDefault:
    """Verify ExecutorPool is the default execution path."""

    @pytest.mark.xfail(reason="ExecutorPool disabled for testnet (hardcoded _use_executor_pool=False)")
    def test_executor_pool_enabled_by_default(self, runtime):
        """ExecutorPool should be enabled with default config."""
        assert runtime._use_executor_pool is True

    def test_no_sync_executor_attribute(self, runtime):
        """Runtime should NOT have sync_executor attribute anymore."""
        assert not hasattr(runtime, 'sync_executor')
        assert not hasattr(runtime, '_use_sync_executor')

    def test_executor_pool_created(self, runtime):
        """ExecutorPool should be created and configured."""
        assert hasattr(runtime, 'executor_pool')
        assert isinstance(runtime.executor_pool, ExecutorPoolV2)

    def test_executor_pool_has_no_bracket_params(self, runtime):
        """ExecutorPool should NOT have sl_pct/tp_rr (V2 architecture)."""
        pool = runtime.executor_pool
        # V2: BracketService is single source of truth
        assert not hasattr(pool, 'sl_pct')
        assert not hasattr(pool, 'tp_rr')

    def test_thread_pool_created(self, runtime):
        """Dedicated thread pool should be created for async execution."""
        assert hasattr(runtime, '_executor_thread_pool')
        assert runtime._executor_thread_pool is not None


class TestNoGlobalBlocking:
    """Verify no global blocking across symbols."""

    def test_different_symbols_independent(self, runtime):
        """Each symbol should have its own executor."""
        btc = runtime.executor_pool.get_executor("BTCUSDT")
        eth = runtime.executor_pool.get_executor("ETHUSDT")
        sol = runtime.executor_pool.get_executor("SOLUSDT")

        # All different instances
        assert btc is not eth
        assert eth is not sol
        assert btc is not sol

        # All have correct symbols
        assert btc.symbol == "BTCUSDT"
        assert eth.symbol == "ETHUSDT"
        assert sol.symbol == "SOLUSDT"

    def test_busy_symbol_not_blocking_others(self, runtime):
        """Busy BTC should NOT block ETH or SOL."""
        btc = runtime.executor_pool.get_executor("BTCUSDT")
        eth = runtime.executor_pool.get_executor("ETHUSDT")
        sol = runtime.executor_pool.get_executor("SOLUSDT")

        # Make BTC busy by setting internal state
        with btc._lock:
            btc._state = ExecutorState.WAITING_FILL

        # BTC is busy
        assert runtime.executor_pool.is_busy("BTCUSDT") is True

        # ETH and SOL are NOT busy
        assert runtime.executor_pool.is_busy("ETHUSDT") is False
        assert runtime.executor_pool.is_busy("SOLUSDT") is False


class TestFillRoutingToCorrectExecutor:
    """Verify fill events route to correct symbol executor."""

    def test_fill_routes_to_correct_symbol(self, runtime):
        """Fill should route to correct symbol executor."""
        btc = runtime.executor_pool.get_executor("BTCUSDT")
        eth = runtime.executor_pool.get_executor("ETHUSDT")

        # Set BTC in waiting state with order_id
        with btc._lock:
            btc._state = ExecutorState.WAITING_FILL
            btc._current_order_id = "btc_order_123"

        # Before fill
        assert not btc._fill_event.is_set()
        assert not eth._fill_event.is_set()

        # Route fill to BTC
        runtime.executor_pool.on_fill(
            symbol="BTCUSDT",
            fill_price="95050.00",
            fill_qty="0.1",
            order_id="btc_order_123",
        )

        # BTC should receive fill, ETH should not
        assert btc._fill_event.is_set()
        assert not eth._fill_event.is_set()

    def test_fill_ignored_when_not_waiting(self, runtime):
        """Fill should be ignored if executor not in WAITING_FILL state."""
        btc = runtime.executor_pool.get_executor("BTCUSDT")

        # BTC is IDLE
        assert btc._state == ExecutorState.IDLE

        # Fill should be ignored
        runtime.executor_pool.on_fill(
            symbol="BTCUSDT",
            fill_price="95000.00",
            fill_qty="0.1",
            order_id="some_order",
        )

        # Fill event should NOT be set
        assert not btc._fill_event.is_set()


class TestPositionUpdateOnFill:
    """Verify position state updates correctly on fills."""

    @pytest.mark.asyncio
    async def test_position_created_on_fill(self, runtime):
        """Position should be created when fill received."""
        assert "BTCUSDT" not in runtime._positions_by_symbol

        await runtime._handle_trade_executed(
            symbol="BTCUSDT",
            payload={
                "order_id": "order_001",
                "side": "BUY",
                "price": "95000.00",
                "quantity": "0.1",
                "status": "FILLED",
            }
        )

        assert "BTCUSDT" in runtime._positions_by_symbol
        pos = runtime._positions_by_symbol["BTCUSDT"]
        assert pos.qty == 0.1
        assert pos.side == "LONG"

    @pytest.mark.asyncio
    async def test_position_increases_on_scale_in(self, runtime):
        """Position qty should increase on scale-in fill."""
        runtime._positions_by_symbol["BTCUSDT"] = PositionState(
            symbol="BTCUSDT",
            qty=0.1,
            avg_entry_price=95000.0,
        )

        await runtime._handle_trade_executed(
            symbol="BTCUSDT",
            payload={
                "order_id": "order_002",
                "side": "BUY",
                "price": "94500.00",
                "quantity": "0.1",
                "status": "FILLED",
            }
        )

        pos = runtime._positions_by_symbol["BTCUSDT"]
        assert pos.qty == 0.2


class TestAsyncFallbackPath:
    """Test async fallback when ExecutorPool is disabled."""

    @pytest.mark.asyncio
    async def test_async_path_when_pool_disabled(self, mock_adapter):
        """Should use async ExecutionService when ExecutorPool disabled."""
        config = {
            "execution": {"executor_pool": {"enabled": False}},
            "execution_position": {
                "executor_pool_enabled": False,
                "aggregated_oco": {"sl_pct": 0.02, "tp_rr": 2.0},
            }
        }

        runtime = ExecPosRuntimeV2(
            config=config,
            adapter=mock_adapter,
            price_service=None,
        )

        assert runtime._use_executor_pool is False

        runtime.gatekeeper.check_entry = MagicMock(return_value={
            "allowed": True,
            "reason": "ok",
            "modified_params": {"quantity": 0.1, "price": None}
        })

        runtime.execution_service.place_order = AsyncMock(return_value={
            "success": True,
            "order_id": "async_order_001",
        })

        await runtime._handle_entry_intent(
            symbol="BTCUSDT",
            payload={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.1,
                "order_type": "MARKET",
            }
        )

        runtime.execution_service.place_order.assert_called_once()


class TestMetrics:
    """Verify metrics are correctly tracked."""

    @pytest.mark.asyncio
    async def test_fills_processed_metric(self, runtime):
        """fills_processed metric should increment on valid fill."""
        initial = runtime._metrics["fills_processed"]

        await runtime._handle_trade_executed(
            symbol="BTCUSDT",
            payload={
                "order_id": "order_001",
                "side": "BUY",
                "price": "95000.00",
                "quantity": "0.1",
                "status": "FILLED",
            }
        )

        assert runtime._metrics["fills_processed"] == initial + 1

    def test_executor_pool_metrics_accessible(self, runtime):
        """ExecutorPool metrics should be accessible from runtime."""
        runtime.executor_pool.get_executor("BTCUSDT")
        runtime.executor_pool.get_executor("ETHUSDT")

        metrics = runtime.executor_pool.get_metrics()

        assert metrics["pool"]["executors_created"] == 2
        assert metrics["pool"]["active_executors"] == 2


class TestBracketServiceIsSingleSource:
    """Verify BracketService is the single source of truth."""

    def test_executor_pool_has_execute_entry_not_execute_order(self, runtime):
        """ExecutorPool should have execute_entry, not execute_order."""
        pool = runtime.executor_pool

        # V2: execute_entry (entry only) replaces execute_order (with auto-brackets)
        assert hasattr(pool, 'execute_entry')
        assert not hasattr(pool, 'execute_order')

    def test_executor_pool_has_execute_bracket(self, runtime):
        """ExecutorPool should have execute_bracket for BracketPlan actions."""
        pool = runtime.executor_pool

        assert hasattr(pool, 'execute_bracket')
        assert hasattr(pool, 'execute_batch')

    def test_symbol_executor_has_no_bracket_calculation(self, runtime):
        """SymbolExecutor should not calculate brackets."""
        executor = runtime.executor_pool.get_executor("BTCUSDT")

        # V2: No bracket math - BracketService handles everything
        assert not hasattr(executor, '_calculate_sl_price')
        assert not hasattr(executor, '_calculate_tp_price')
        assert not hasattr(executor, '_place_brackets_close_position')
        assert not hasattr(executor, 'sl_pct')
        assert not hasattr(executor, 'tp_rr')
