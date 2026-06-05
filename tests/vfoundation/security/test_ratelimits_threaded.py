"""Tests for thread-safe ratelimiter — Phase 17.3."""
import threading

from vfoundation.security.ratelimits import RateLimiter


class TestRateLimiterThreadSafe:
    """Phase 17.3: Thread-safety tests for RateLimiter."""

    def test_lock_exists(self):
        """RateLimiter has a threading.Lock attribute."""
        rl = RateLimiter(per_s=5)
        assert hasattr(rl, "_lock")
        assert isinstance(rl._lock, type(threading.Lock()))

    def test_concurrent_threads(self):
        """Multiple threads calling allow() concurrently should not crash."""
        rl = RateLimiter(per_s=100)
        results: list[bool] = []
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(50):
                    results.append(rl.allow("test_key"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 500
