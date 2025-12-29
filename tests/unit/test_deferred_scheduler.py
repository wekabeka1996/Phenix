"""
Tests for DeferredIntentScheduler with sync/async fallback support.

BUGFIX: Ensures scheduler works in both async and sync contexts by using
threading.Timer as fallback when no event loop is running.
"""

import asyncio
import time
import threading
import pytest
from apps.reference.domains.decision_making.deferred_scheduler import DeferredIntentScheduler


class TestDeferredSchedulerSyncFallback:
    """Test DeferredIntentScheduler works in sync context (no event loop)."""

    def test_schedule_in_sync_context_uses_threading_timer(self):
        """
        BUGFIX TEST: Verify scheduler works when called from sync context.

        This test ensures the fix for the bug where scheduler would skip
        scheduling due to "no running event loop" in sync context.
        """
        scheduler = DeferredIntentScheduler()
        callback_called = threading.Event()
        callback_symbol = []

        def callback(symbol: str):
            callback_symbol.append(symbol)
            callback_called.set()

        # Schedule in sync context (no event loop) - delay 100ms
        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 100, callback)

        # Verify timer was created
        assert scheduler.get_pending_count() == 1, "Timer should be pending"

        # Wait for callback
        assert callback_called.wait(timeout=2.0), "Callback should be called"
        assert callback_symbol == ["BTCUSDT"], f"Got: {callback_symbol}"

        # Cleanup
        scheduler.shutdown()

    def test_deduplication_in_sync_context(self):
        """Test that duplicate schedules are ignored in sync context."""
        scheduler = DeferredIntentScheduler()
        call_count = [0]

        def callback(symbol: str):
            call_count[0] += 1

        now_ms = int(time.time() * 1000)

        # Schedule same symbol twice
        scheduler.schedule_once("BTCUSDT", now_ms + 100, callback)
        scheduler.schedule_once("BTCUSDT", now_ms + 200, callback)  # Should be ignored

        # Should only have one pending
        assert scheduler.get_pending_count() == 1

        # Wait for callback
        time.sleep(0.3)
        assert call_count[0] == 1, f"Expected 1 call, got {call_count[0]}"

        scheduler.shutdown()

    def test_cancel_in_sync_context(self):
        """Test cancellation works in sync context."""
        scheduler = DeferredIntentScheduler()
        callback_called = threading.Event()

        def callback(symbol: str):
            callback_called.set()

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 500, callback)

        # Cancel before it fires
        scheduler.cancel("BTCUSDT")
        assert scheduler.get_pending_count() == 0

        # Wait to ensure callback doesn't fire
        time.sleep(0.7)
        assert not callback_called.is_set(), "Callback should not be called after cancel"

        scheduler.shutdown()

    def test_multiple_symbols_independent(self):
        """Test different symbols can be scheduled independently."""
        scheduler = DeferredIntentScheduler()
        results = []
        done = threading.Event()

        def callback(symbol: str):
            results.append(symbol)
            if len(results) >= 2:
                done.set()

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 50, callback)
        scheduler.schedule_once("ETHUSDT", now_ms + 100, callback)

        assert scheduler.get_pending_count() == 2

        # Wait for both
        assert done.wait(timeout=2.0), "Both callbacks should fire"
        assert set(results) == {"BTCUSDT", "ETHUSDT"}

        scheduler.shutdown()

    def test_shutdown_cancels_all_timers(self):
        """Test shutdown cancels all pending timers."""
        scheduler = DeferredIntentScheduler()
        callback_count = [0]

        def callback(symbol: str):
            callback_count[0] += 1

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 500, callback)
        scheduler.schedule_once("ETHUSDT", now_ms + 500, callback)
        scheduler.schedule_once("SOLUSDT", now_ms + 500, callback)

        assert scheduler.get_pending_count() == 3

        # Shutdown before timers fire
        scheduler.shutdown()
        assert scheduler.get_pending_count() == 0

        # Wait to ensure no callbacks fire
        time.sleep(0.7)
        assert callback_count[0] == 0, "No callbacks should fire after shutdown"


class TestDeferredSchedulerAsyncContext:
    """Test DeferredIntentScheduler works in async context."""

    @pytest.mark.asyncio
    async def test_schedule_in_async_context_uses_loop(self):
        """Test scheduler uses asyncio in async context."""
        scheduler = DeferredIntentScheduler()
        callback_future = asyncio.get_event_loop().create_future()

        def callback(symbol: str):
            if not callback_future.done():
                callback_future.set_result(symbol)

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 50, callback)

        assert scheduler.get_pending_count() == 1

        # Wait for callback
        result = await asyncio.wait_for(callback_future, timeout=2.0)
        assert result == "BTCUSDT"

        scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_in_async_context(self):
        """Test cancellation works in async context."""
        scheduler = DeferredIntentScheduler()
        callback_called = False

        def callback(symbol: str):
            nonlocal callback_called
            callback_called = True

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 200, callback)

        # Cancel
        scheduler.cancel("BTCUSDT")

        # Wait
        await asyncio.sleep(0.3)
        assert not callback_called

        scheduler.shutdown()


class TestDeferredSchedulerEdgeCases:
    """Edge case tests for DeferredIntentScheduler."""

    def test_immediate_fire_when_past_timestamp(self):
        """Test callback fires immediately if timestamp is in the past."""
        scheduler = DeferredIntentScheduler()
        callback_event = threading.Event()

        def callback(symbol: str):
            callback_event.set()

        # Schedule with past timestamp
        past_ms = int(time.time() * 1000) - 1000
        scheduler.schedule_once("BTCUSDT", past_ms, callback)

        # Should fire immediately
        assert callback_event.wait(timeout=0.5), "Callback should fire for past timestamp"

        scheduler.shutdown()

    def test_zero_delay_works(self):
        """Test zero delay scheduling works."""
        scheduler = DeferredIntentScheduler()
        callback_event = threading.Event()

        def callback(symbol: str):
            callback_event.set()

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms, callback)  # Now = 0 delay

        assert callback_event.wait(timeout=0.5)

        scheduler.shutdown()

    def test_get_pending_count_updates_correctly(self):
        """Test pending count decrements after callback fires."""
        scheduler = DeferredIntentScheduler()

        def callback(symbol: str):
            pass

        now_ms = int(time.time() * 1000)
        scheduler.schedule_once("BTCUSDT", now_ms + 50, callback)

        assert scheduler.get_pending_count() == 1

        # Wait for it to fire
        time.sleep(0.2)

        assert scheduler.get_pending_count() == 0

        scheduler.shutdown()
