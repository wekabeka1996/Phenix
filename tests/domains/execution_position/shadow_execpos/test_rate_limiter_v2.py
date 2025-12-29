"""
Tests for Non-Blocking RateLimiter V2
=====================================

Phase 5: Verifies RateLimiter works correctly:
- No blocking (no time.sleep)
- Per-symbol soft limits
- Global limits
- Immediate return on rate limit

RID: PHASE5-RATE-LIMITER-TESTS
"""
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.reference.domains.execution_position.shadow_execpos.executor_pool import RateLimiter


class TestRateLimiterNonBlocking:
    """Tests that RateLimiter doesn't block on rate limit."""

    def test_try_acquire_returns_immediately(self):
        """try_acquire should return False immediately, not block."""
        limiter = RateLimiter(max_requests=1, window_seconds=1.0)

        # First acquire succeeds
        assert limiter.try_acquire() is True

        # Second acquire should return False immediately (not block)
        start = time.time()
        result = limiter.try_acquire()
        elapsed = time.time() - start

        assert result is False
        assert elapsed < 0.1, "try_acquire should not block"

    def test_acquire_deprecated_returns_immediately(self):
        """Deprecated acquire() should also not block."""
        limiter = RateLimiter(max_requests=1, window_seconds=1.0)

        # First acquire succeeds
        assert limiter.acquire(timeout=5.0) is True

        # Second acquire should return False immediately (ignore timeout)
        start = time.time()
        result = limiter.acquire(timeout=5.0)
        elapsed = time.time() - start

        assert result is False
        assert elapsed < 0.1, "acquire should not block even with timeout"

    def test_window_expires_allows_new_requests(self):
        """After window expires, new requests should be allowed."""
        limiter = RateLimiter(max_requests=1, window_seconds=0.1)

        # First acquire succeeds
        assert limiter.try_acquire() is True

        # Second fails
        assert limiter.try_acquire() is False

        # Wait for window to expire
        time.sleep(0.15)

        # Now should succeed
        assert limiter.try_acquire() is True


class TestRateLimiterPerSymbol:
    """Tests for per-symbol soft limiting."""

    def test_per_symbol_limit_independent(self):
        """Different symbols have independent limits."""
        limiter = RateLimiter(
            max_requests=10,  # High global limit
            window_seconds=1.0,
            per_symbol_limit=2,  # Low per-symbol limit
        )

        # BTCUSDT can do 2 requests
        assert limiter.try_acquire(symbol="BTCUSDT") is True
        assert limiter.try_acquire(symbol="BTCUSDT") is True
        # Third fails
        assert limiter.try_acquire(symbol="BTCUSDT") is False

        # ETHUSDT is independent
        assert limiter.try_acquire(symbol="ETHUSDT") is True
        assert limiter.try_acquire(symbol="ETHUSDT") is True
        # Third fails
        assert limiter.try_acquire(symbol="ETHUSDT") is False

    def test_global_limit_respected_with_per_symbol(self):
        """Global limit takes precedence over per-symbol."""
        limiter = RateLimiter(
            max_requests=3,  # Low global limit
            window_seconds=1.0,
            per_symbol_limit=5,  # High per-symbol limit
        )

        # First 3 requests succeed (hit global limit)
        assert limiter.try_acquire(symbol="BTCUSDT") is True
        assert limiter.try_acquire(symbol="ETHUSDT") is True
        assert limiter.try_acquire(symbol="SOLUSDT") is True

        # 4th fails even for new symbol
        assert limiter.try_acquire(symbol="XRPUSDT") is False

    def test_no_symbol_uses_global_only(self):
        """Requests without symbol only check global limit."""
        limiter = RateLimiter(
            max_requests=2,
            window_seconds=1.0,
            per_symbol_limit=1,
        )

        # Without symbol, only global limit applies
        assert limiter.try_acquire(symbol=None) is True
        assert limiter.try_acquire(symbol=None) is True
        assert limiter.try_acquire(symbol=None) is False


class TestRateLimiterWaitTime:
    """Tests for wait time estimation."""

    def test_wait_time_zero_when_available(self):
        """Wait time should be 0 when slots available."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)

        assert limiter.get_wait_time() == 0.0

    def test_wait_time_nonzero_when_limited(self):
        """Wait time should be positive when rate limited."""
        limiter = RateLimiter(max_requests=1, window_seconds=1.0)

        limiter.try_acquire()  # Use the slot
        wait_time = limiter.get_wait_time()

        assert wait_time > 0
        assert wait_time <= 1.0

    def test_wait_time_per_symbol(self):
        """Wait time respects per-symbol limits."""
        limiter = RateLimiter(
            max_requests=10,
            window_seconds=1.0,
            per_symbol_limit=1,
        )

        limiter.try_acquire(symbol="BTCUSDT")

        # Global has slots, but BTCUSDT is limited
        btc_wait = limiter.get_wait_time(symbol="BTCUSDT")
        global_wait = limiter.get_wait_time(symbol=None)

        assert btc_wait > 0
        assert global_wait == 0.0


class TestRateLimiterAvailableSlots:
    """Tests for available slots reporting."""

    def test_available_slots_initial(self):
        """Initial available slots equals max_requests."""
        limiter = RateLimiter(max_requests=8, window_seconds=1.0)

        assert limiter.get_available_slots() == 8

    def test_available_slots_decreases(self):
        """Available slots decreases after acquire."""
        limiter = RateLimiter(max_requests=8, window_seconds=1.0)

        limiter.try_acquire()
        assert limiter.get_available_slots() == 7

        limiter.try_acquire()
        limiter.try_acquire()
        assert limiter.get_available_slots() == 5

    def test_available_slots_recovers(self):
        """Available slots recovers after window expires."""
        limiter = RateLimiter(max_requests=2, window_seconds=0.1)

        limiter.try_acquire()
        limiter.try_acquire()
        assert limiter.get_available_slots() == 0

        time.sleep(0.15)
        assert limiter.get_available_slots() == 2


class TestRateLimiterThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_acquire(self):
        """Multiple threads can safely acquire."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        results = []
        lock = threading.Lock()

        def try_acquire():
            result = limiter.try_acquire()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=try_acquire) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 5 should succeed
        assert sum(results) == 5
        assert len(results) == 10

    def test_concurrent_per_symbol(self):
        """Concurrent per-symbol access is thread-safe."""
        limiter = RateLimiter(
            max_requests=100,
            window_seconds=1.0,
            per_symbol_limit=2,
        )
        results = {"BTCUSDT": [], "ETHUSDT": []}
        lock = threading.Lock()

        def try_acquire(symbol):
            result = limiter.try_acquire(symbol=symbol)
            with lock:
                results[symbol].append(result)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for _ in range(10):
                futures.append(executor.submit(try_acquire, "BTCUSDT"))
                futures.append(executor.submit(try_acquire, "ETHUSDT"))

            for f in as_completed(futures):
                f.result()

        # Each symbol should have exactly 2 successes
        assert sum(results["BTCUSDT"]) == 2
        assert sum(results["ETHUSDT"]) == 2
