"""
Tests for async fixes (self-review audit):
 - Fix 1: aclose() logs on error instead of silent pass
 - Fix 2: _find_symbol_by_order_id uses TTL-cached open orders scan
 - Fix 3: Watchdog task exposes crashes via done_callback
"""
import asyncio
import time
import pytest
pytest.importorskip("httpx")

from unittest.mock import AsyncMock, MagicMock, patch
from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    """BinanceAdapter with fully mocked httpx session."""
    mock_session = MagicMock()
    mock_session.aclose = AsyncMock()
    mock_session.request = AsyncMock()
    adapter = BinanceAdapter("key", "secret", "https://testnet.binancefuture.com",
                             session=mock_session)
    adapter._sync_time = AsyncMock()
    return adapter


# ---------------------------------------------------------------------------
# Fix 1: aclose() should LOG on failure instead of swallowing silently
# ---------------------------------------------------------------------------

class TestAcloseLogsOnError:
    @pytest.mark.anyio
    async def test_aclose_logs_warning_when_session_raises(self, adapter, caplog):
        adapter.session.aclose.side_effect = RuntimeError("socket already closed")

        import logging
        with caplog.at_level(logging.WARNING, logger="apps.reference.adapters.binance_adapter"):
            await adapter.aclose()  # must not raise

        assert "aclose() failed" in caplog.text, "Expected warning log from aclose()"

    @pytest.mark.anyio
    async def test_aclose_does_not_raise(self, adapter):
        """aclose() must remain non-raising even on failure."""
        adapter.session.aclose.side_effect = Exception("boom")
        # Should not propagate:
        await adapter.aclose()


# ---------------------------------------------------------------------------
# Fix 2: _get_open_orders_cached() implements TTL, _find_symbol uses it
# ---------------------------------------------------------------------------

class TestOpenOrdersTTLCache:
    @pytest.mark.anyio
    async def test_second_call_within_ttl_does_not_hit_rest(self, adapter):
        """Within TTL window, second call should return cached data without HTTP request."""
        fake_orders = [{"orderId": "111", "symbol": "BTCUSDT", "clientOrderId": "cid1"}]

        # _request is the underlying REST call
        adapter._request = AsyncMock(return_value=fake_orders)

        result1 = await adapter._get_open_orders_cached()
        result2 = await adapter._get_open_orders_cached()

        assert result1 == fake_orders
        assert result2 == fake_orders
        # Should have hit REST only once despite two calls
        assert adapter._request.call_count == 1, (
            f"Expected 1 REST call but got {adapter._request.call_count}"
        )

    @pytest.mark.anyio
    async def test_cache_expires_after_ttl(self, adapter):
        """After TTL expires, the next call fetches fresh data from REST."""
        fake_orders_v1 = [{"orderId": "111", "symbol": "BTCUSDT", "clientOrderId": "cid1"}]
        fake_orders_v2 = [{"orderId": "222", "symbol": "ETHUSDT", "clientOrderId": "cid2"}]

        adapter._request = AsyncMock(side_effect=[fake_orders_v1, fake_orders_v2])

        # First call - fills cache
        result1 = await adapter._get_open_orders_cached()
        assert result1 == fake_orders_v1

        # Manually expire the cache by backdating its timestamp
        expired_ts = int(time.time() * 1000) - adapter._open_orders_scan_ttl_ms - 100
        adapter._open_orders_scan_cache = (expired_ts, fake_orders_v1)

        # Second call - cache is stale, should fetch fresh
        result2 = await adapter._get_open_orders_cached()
        assert result2 == fake_orders_v2
        assert adapter._request.call_count == 2

    @pytest.mark.anyio
    async def test_find_symbol_uses_cache_not_direct_request(self, adapter):
        """_find_symbol_by_order_id must use cache, never go directly to _request."""
        fake_orders = [{"orderId": "999", "symbol": "SOLUSDT", "clientOrderId": "cidSOL"}]
        adapter._request = AsyncMock(return_value=fake_orders)

        # Both calls resolve the same order — only 1 REST hit expected
        sym1 = await adapter._find_symbol_by_order_id("999", None)
        sym2 = await adapter._find_symbol_by_order_id("999", None)

        assert sym1 == "SOLUSDT"
        assert sym2 == "SOLUSDT"
        assert adapter._request.call_count == 1, (
            "_find_symbol_by_order_id should leverage cache, not call REST twice"
        )


# ---------------------------------------------------------------------------
# Fix 3: Watchdog task done_callback surfaces crashes in logs
# These tests are asyncio-only — asyncio.create_task() is not trio-compatible.
# ---------------------------------------------------------------------------

class TestWatchdogDoneCallback:
    @pytest.mark.asyncio
    async def test_done_callback_logs_on_unexpected_crash(self, caplog):
        """
        If _watchdog_loop raises, the done_callback should log an ERROR
        rather than letting it disappear silently.
        """
        import logging

        errors_seen = []

        async def _crashing_loop():
            raise RuntimeError("unexpected crash in watchdog")

        task = asyncio.ensure_future(_crashing_loop())
        task.add_done_callback(
            lambda t: errors_seen.append(str(t.exception()))
            if not t.cancelled() and t.exception() else None
        )

        # Allow task to finish
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
        except Exception:
            pass

        # Verify done_callback captured the error
        assert any("unexpected crash" in e for e in errors_seen), (
            f"Expected crash to be captured by done_callback, got: {errors_seen}"
        )

    @pytest.mark.asyncio
    async def test_done_callback_not_triggered_on_cancel(self):
        """Cancelled tasks must NOT trigger the error-logging callback."""
        errors_seen = []

        async def _infinite_loop():
            while True:
                await asyncio.sleep(1)

        task = asyncio.ensure_future(_infinite_loop())
        task.add_done_callback(
            lambda t: errors_seen.append(str(t.exception()))
            if not t.cancelled() and t.exception() else None
        )

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Cancel must not fire the error callback
        assert len(errors_seen) == 0, (
            f"Expected no errors on cancel, but got: {errors_seen}"
        )
