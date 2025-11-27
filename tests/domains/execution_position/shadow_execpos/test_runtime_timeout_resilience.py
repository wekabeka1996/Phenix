"""
Unit tests for timeout resilience in ExecPosRuntimeV2.

Validates that:
1. httpx.ReadTimeout exceptions are properly classified as ADAPTER_ERROR_TIMEOUT
2. Runtime enters stale mode on timeout and blocks new trades
3. Exponential backoff retry logic works in BinanceAdapter
4. Runtime exits stale mode after successful API resync
"""
import asyncio
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.types import RuntimeEvent
from tests.domains.execution_position.shadow_execpos.fakes import FakeExecutionAdapter


def _minimal_config() -> dict:
    return {
        "execution_position": {
            "aggregated_oco": {
                "enabled": True,
                "allow_unprotected_position": False,
                "recalc_on_partial_close": True,
                "recalc_on_scale_in": True,
                "ttl_protect_new_bracket_ms": 5000,
                "max_tp_legs": 1,
                "max_sl_legs": 1,
                "sl_pct": 0.02,
                "tp_rr": 2.0,
            },
            "trailing": {
                "enabled": False,
            },
            "close": {
                "allow_time_exit": True,
                "max_hold_time_sec": 0,
            },
        }
    }


class TimeoutFakeAdapter(FakeExecutionAdapter):
    """Fake adapter that can simulate timeout errors."""

    def __init__(self):
        super().__init__()
        self.timeout_on_get_open_orders = False
        self.timeout_on_place_order = False
        self.call_counts: Dict[str, int] = {
            "get_open_orders": 0,
            "place_order": 0,
        }

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        self.call_counts["get_open_orders"] += 1
        if self.timeout_on_get_open_orders:
            # Simulate httpx.ReadTimeout
            import httpx
            raise httpx.ReadTimeout("Simulated timeout on get_open_orders")
        return await super().get_open_orders(symbol)

    async def place_order(self, *args, **kwargs) -> Dict[str, Any]:
        self.call_counts["place_order"] += 1
        if self.timeout_on_place_order:
            import httpx
            raise httpx.ReadTimeout("Simulated timeout on place_order")
        return await super().place_order(*args, **kwargs)


# ---------------------------------------------------------------------------
# Test: Timeout classification (ADAPTER_ERROR_TIMEOUT)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_classified_as_adapter_error_timeout():
    """
    Verify that httpx.ReadTimeout is classified as ADAPTER_ERROR_TIMEOUT.
    """
    import httpx
    from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
        ExecutionService,
    )

    class MockAdapter:
        async def place_order(self, *args, **kwargs):
            raise httpx.ReadTimeout("Simulated timeout")

    service = ExecutionService(adapter=MockAdapter())  # type: ignore
    result = await service.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity="0.001",
    )

    assert result["success"] is False
    assert result["error_kind"] == "ADAPTER_ERROR_TIMEOUT"
    assert "TIMEOUT" in result["error"]


@pytest.mark.asyncio
async def test_network_error_classified_as_adapter_error_network():
    """
    Verify that httpx.ConnectError is classified as ADAPTER_ERROR_NETWORK.
    """
    import httpx
    from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
        ExecutionService,
    )

    class MockAdapter:
        async def place_order(self, *args, **kwargs):
            raise httpx.ConnectError("Simulated connect error")

    service = ExecutionService(adapter=MockAdapter())  # type: ignore
    result = await service.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity="0.001",
    )

    assert result["success"] is False
    assert result["error_kind"] == "ADAPTER_ERROR_NETWORK"
    assert "NETWORK" in result["error"]


# ---------------------------------------------------------------------------
# Test: Runtime enters stale mode on timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_enters_stale_mode_on_timeout():
    """
    When get_open_orders times out, runtime should enter stale mode for that symbol.
    """
    import httpx

    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Initially not stale
    assert runtime.is_orders_stale("BTCUSDT") is False

    # Create a snapshot hook that will call adapter and raise timeout
    async def timeout_snapshot_hook(symbol: str) -> None:
        # This simulates what the facade would do
        await adapter.get_open_orders(symbol)

    runtime.set_snapshot_refresh_hook(timeout_snapshot_hook)

    # Enable timeout
    adapter.timeout_on_get_open_orders = True

    # Request snapshot (will timeout via hook)
    await runtime._request_orders_snapshot("BTCUSDT", force=True)

    # Should now be stale
    assert runtime.is_orders_stale("BTCUSDT") is True
    assert runtime._metrics.get("stale_mode_entered", 0) >= 1


@pytest.mark.asyncio
async def test_runtime_blocks_new_trades_in_stale_mode():
    """
    When in stale mode, new ENTRY_INTENT events should be rejected.
    """
    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Force stale mode
    runtime._enter_stale_mode("BTCUSDT", "test_timeout")

    assert runtime.is_orders_stale("BTCUSDT") is True

    initial_place_count = adapter.call_counts["place_order"]

    # Try to open trade
    await runtime.handle(
        RuntimeEvent(
            kind="ENTRY_INTENT",
            symbol="BTCUSDT",
            timestamp=time.time(),
            payload={"side": "BUY", "quantity": 0.01, "order_type": "MARKET"},
        )
    )

    # Should NOT have placed any order
    assert adapter.call_counts["place_order"] == initial_place_count


@pytest.mark.asyncio
async def test_runtime_exits_stale_mode_on_successful_sync():
    """
    After successful API call, stale mode should be cleared.
    """
    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Create a snapshot hook
    async def snapshot_hook(symbol: str) -> None:
        await adapter.get_open_orders(symbol)

    runtime.set_snapshot_refresh_hook(snapshot_hook)

    # Start in stale mode
    runtime._enter_stale_mode("BTCUSDT", "test_timeout")
    assert runtime.is_orders_stale("BTCUSDT") is True

    # Now adapter works
    adapter.timeout_on_get_open_orders = False

    # Request snapshot successfully and simulate receiving the event
    await runtime._request_orders_snapshot("BTCUSDT", force=True)
    runtime._mark_orders_snapshot("BTCUSDT")

    # Should exit stale mode
    assert runtime.is_orders_stale("BTCUSDT") is False
    assert runtime._metrics.get("stale_mode_exited", 0) >= 1


# ---------------------------------------------------------------------------
# Test: Stale recovery loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stale_recovery_loop_retries():
    """
    _try_stale_recovery should attempt recovery and exit stale mode on success.
    """
    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Create a snapshot hook
    async def snapshot_hook(symbol: str) -> None:
        await adapter.get_open_orders(symbol)

    runtime.set_snapshot_refresh_hook(snapshot_hook)

    # Start in stale mode
    runtime._enter_stale_mode("BTCUSDT", "test_timeout")
    adapter.timeout_on_get_open_orders = True

    call_count_before = adapter.call_counts["get_open_orders"]

    # Run single recovery iteration (will fail)
    result = await runtime._try_stale_recovery("BTCUSDT")

    # Should have tried
    assert adapter.call_counts["get_open_orders"] > call_count_before

    # Still stale (recovery failed)
    assert runtime.is_orders_stale("BTCUSDT") is True
    assert result is False

    # Now fix adapter
    adapter.timeout_on_get_open_orders = False

    # Recovery should succeed
    result = await runtime._try_stale_recovery("BTCUSDT")

    # Simulate receiving the snapshot event
    runtime._mark_orders_snapshot("BTCUSDT")

    # Should exit stale mode
    assert runtime.is_orders_stale("BTCUSDT") is False


# ---------------------------------------------------------------------------
# Test: Runtime does not crash on timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_does_not_crash_on_repeated_timeouts():
    """
    Repeated timeouts should not crash the runtime. It should degrade gracefully.
    """
    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Create a snapshot hook
    async def snapshot_hook(symbol: str) -> None:
        await adapter.get_open_orders(symbol)

    runtime.set_snapshot_refresh_hook(snapshot_hook)

    adapter.timeout_on_get_open_orders = True

    # Multiple snapshot requests should not raise
    for _ in range(5):
        await runtime._request_orders_snapshot("BTCUSDT", force=True)
        await runtime._request_orders_snapshot("ETHUSDT", force=True)

    # Runtime should still be operational (check internal state)
    assert runtime.is_orders_stale("BTCUSDT") is True
    assert runtime.is_orders_stale("ETHUSDT") is True

    # Now fix and ensure recovery works
    adapter.timeout_on_get_open_orders = False

    await runtime._request_orders_snapshot("BTCUSDT", force=True)
    runtime._mark_orders_snapshot("BTCUSDT")
    assert runtime.is_orders_stale("BTCUSDT") is False


# ---------------------------------------------------------------------------
# Test: Metrics tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stale_mode_metrics_tracked():
    """
    Verify that stale mode metrics are properly tracked.
    """
    adapter = TimeoutFakeAdapter()
    runtime = ExecPosRuntimeV2(
        config=_minimal_config(), adapter=adapter, price_service=None)

    # Enter stale mode twice
    runtime._enter_stale_mode("BTCUSDT", "timeout1")
    runtime._enter_stale_mode("ETHUSDT", "timeout2")

    assert runtime._metrics["stale_mode_entered"] == 2

    # Exit once
    runtime._exit_stale_mode("BTCUSDT", "recovered")

    assert runtime._metrics["stale_mode_exited"] == 1

    # Check symbols in stale
    stale_symbols = runtime.get_stale_symbols()
    assert "BTCUSDT" not in stale_symbols
    assert "ETHUSDT" in stale_symbols


# ---------------------------------------------------------------------------
# Test: BinanceAdapter retry config
# ---------------------------------------------------------------------------

def test_timeout_config_testnet_defaults():
    """
    Verify TimeoutConfig.testnet_defaults() returns higher timeouts.
    """
    from apps.reference.adapters.binance_adapter import TimeoutConfig

    testnet = TimeoutConfig.testnet_defaults()
    live = TimeoutConfig.live_defaults()

    # Testnet should have higher read timeout
    assert testnet.read >= live.read
    assert testnet.read >= 20.0  # Should be at least 20s


def test_retry_config_exponential_backoff():
    """
    Verify RetryConfig produces correct exponential backoff delays.
    """
    from apps.reference.adapters.binance_adapter import RetryConfig

    config = RetryConfig(
        max_retries=4,
        initial_backoff_sec=0.5,
        backoff_multiplier=2.0,
        max_backoff_sec=10.0,
    )

    delays = config.get_backoff_delays()

    # Expected: 0.5, 1.0, 2.0, 4.0
    assert delays == [0.5, 1.0, 2.0, 4.0]
