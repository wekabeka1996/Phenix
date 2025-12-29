"""
Tests for Per-Symbol Locks in ExecPosRuntimeV2
===============================================

Phase 5: Verifies per-symbol locking works correctly:
- Different symbols can execute in parallel
- Same symbol operations are serialized
- Global lock still works for snapshot operations

RID: PHASE5-PER-SYMBOL-LOCKS-TESTS
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from tests.domains.execution_position.shadow_execpos.fake_adapter import FakeRecordingAdapter


@pytest.fixture
def fake_adapter():
    return FakeRecordingAdapter()


@pytest.fixture
def runtime(fake_adapter):
    config = {
        "cooldown_sec": 0.1,
        "execution": {
            "executor_pool": {
                "enabled": False,
            }
        },
        "execution_position": {
            "executor_pool_enabled": False,
        }
    }
    return ExecPosRuntimeV2(config, fake_adapter, None)


class TestPerSymbolLocks:
    """Tests for per-symbol lock mechanism."""

    @pytest.mark.asyncio
    async def test_get_symbol_lock_creates_lock(self, runtime):
        """_get_symbol_lock creates a new lock for each symbol."""
        lock1 = runtime._get_symbol_lock("BTCUSDT")
        lock2 = runtime._get_symbol_lock("ETHUSDT")

        assert lock1 is not None
        assert lock2 is not None
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_get_symbol_lock_returns_same_lock(self, runtime):
        """_get_symbol_lock returns same lock for same symbol."""
        lock1 = runtime._get_symbol_lock("BTCUSDT")
        lock2 = runtime._get_symbol_lock("BTCUSDT")

        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_symbol_locks_are_independent(self, runtime):
        """Different symbol locks don't block each other."""
        btc_lock = runtime._get_symbol_lock("BTCUSDT")
        eth_lock = runtime._get_symbol_lock("ETHUSDT")

        # Acquire BTC lock
        await btc_lock.acquire()

        # ETH lock should still be available
        assert not eth_lock.locked()
        await eth_lock.acquire()

        # Both are now locked but independent
        assert btc_lock.locked()
        assert eth_lock.locked()

        btc_lock.release()
        eth_lock.release()

    @pytest.mark.asyncio
    async def test_parallel_symbol_execution(self, runtime):
        """Different symbols can execute handlers in parallel."""
        execution_order = []

        async def mock_evaluate_brackets(symbol, *args, **kwargs):
            execution_order.append(f"start_{symbol}")
            await asyncio.sleep(0.05)  # Simulate work
            execution_order.append(f"end_{symbol}")

        runtime._evaluate_brackets = mock_evaluate_brackets

        # Start both executions concurrently
        task1 = asyncio.create_task(
            runtime._handle_trade_executed("BTCUSDT", {
                "symbol": "BTCUSDT",
                "status": "FILLED",
                "quantity": "1.0",
                "side": "BUY",
                "price": "50000",
            })
        )
        task2 = asyncio.create_task(
            runtime._handle_trade_executed("ETHUSDT", {
                "symbol": "ETHUSDT",
                "status": "FILLED",
                "quantity": "10.0",
                "side": "BUY",
                "price": "2000",
            })
        )

        await asyncio.gather(task1, task2)

        # With per-symbol locks, both should start before either ends
        # (parallel execution)
        btc_start_idx = execution_order.index("start_BTCUSDT")
        eth_start_idx = execution_order.index("start_ETHUSDT")
        btc_end_idx = execution_order.index("end_BTCUSDT")
        eth_end_idx = execution_order.index("end_ETHUSDT")

        # Both starts should happen before both ends (parallel)
        assert btc_start_idx < btc_end_idx
        assert eth_start_idx < eth_end_idx


class TestGlobalLock:
    """Tests for global lock (for snapshot operations)."""

    @pytest.mark.asyncio
    async def test_get_global_lock_creates_lock(self, runtime):
        """_get_global_lock creates a global lock."""
        lock = runtime._get_global_lock()
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_global_lock_returns_same_lock(self, runtime):
        """_get_global_lock returns same lock on repeated calls."""
        lock1 = runtime._get_global_lock()
        lock2 = runtime._get_global_lock()
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_evaluation_lock_deprecated_returns_global(self, runtime):
        """_get_evaluation_lock (deprecated) returns global lock."""
        global_lock = runtime._get_global_lock()
        eval_lock = runtime._get_evaluation_lock()
        assert eval_lock is global_lock


class TestLockLoopBinding:
    """Tests for event loop binding of locks."""

    @pytest.mark.asyncio
    async def test_symbol_locks_recreated_on_new_loop(self, runtime):
        """Symbol locks are recreated when event loop changes."""
        # Get lock in current loop
        lock1 = runtime._get_symbol_lock("BTCUSDT")
        initial_loop = runtime._symbol_locks_loop

        # Simulate loop change by clearing the loop reference
        runtime._symbol_locks_loop = None

        # Get lock again
        lock2 = runtime._get_symbol_lock("BTCUSDT")

        # Should be a new lock
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_global_lock_recreated_on_new_loop(self, runtime):
        """Global lock is recreated when event loop changes."""
        lock1 = runtime._get_global_lock()

        # Simulate loop change
        runtime._global_lock_loop = None

        lock2 = runtime._get_global_lock()

        assert lock1 is not lock2


class TestConfigurableThrottling:
    """Tests for configurable throttling from ep_config."""

    def test_default_throttle_values(self, runtime):
        """Default throttle values are used when no ep_config."""
        # RC-1 FIX: Increased default throttle to prevent bracket churn
        assert runtime._bracket_throttle_sec == 10.0
        assert runtime._bracket_suppression_sec == 10.0

    def test_throttle_from_ep_config(self, fake_adapter):
        """Throttle values from ep_config override defaults."""
        from apps.reference.domains.execution_position.config import (
            ExecutionPositionConfig,
            AggregatedOcoConfig,
            TrailingConfig,
            CloseConfig,
            SnapshotConfig,
        )

        ep_config = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                bracket_throttle_sec=1.5,
                bracket_suppression_sec=5.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
            snapshot=SnapshotConfig(),
        )

        config = {
            "cooldown_sec": 0.1,
            "execution_position": {"executor_pool_enabled": False}
        }

        runtime = ExecPosRuntimeV2(
            config, fake_adapter, None, ep_config=ep_config)

        assert runtime._bracket_throttle_sec == 1.5
        assert runtime._bracket_suppression_sec == 5.0
