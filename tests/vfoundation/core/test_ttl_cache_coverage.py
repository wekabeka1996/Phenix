"""Coverage tests for MonotonicTTLCache — targeting missing lines/branches."""
import pytest
import time
import threading
from vfoundation.core.cache.ttl_cache import (
    MonotonicTTLCache, CleanupStats, ns_from_ms, ms_from_ns, now_ns, now_ms
)


class TestHelperFunctions:
    def test_ns_from_ms(self):
        assert ns_from_ms(1) == 1_000_000
        assert ns_from_ms(0) == 0

    def test_ms_from_ns(self):
        assert ms_from_ns(1_000_000) == 1
        assert ms_from_ns(500_000) == 0

    def test_now_ns(self):
        assert now_ns() > 0

    def test_now_ms(self):
        assert now_ms() > 0


class TestCleanupStats:
    def test_repr(self):
        cs = CleanupStats(expired=3, scanned=10, remaining=7)
        assert "3" in repr(cs)


class TestCacheInit:
    def test_max_entries_zero_raises(self):
        with pytest.raises(ValueError):
            MonotonicTTLCache(max_entries=0)  # Line 90

    def test_default_ttl_negative_raises(self):
        with pytest.raises(ValueError):
            MonotonicTTLCache(default_ttl_ms=-1)  # Line 92

    def test_janitor_interval_zero_raises(self):
        with pytest.raises(ValueError):
            MonotonicTTLCache(janitor_interval_ms=0)  # Line 94

    def test_scan_budget_zero_raises(self):
        with pytest.raises(ValueError):
            MonotonicTTLCache(scan_budget=0)  # Line 96


class TestCacheSetGet:
    def test_set_without_ttl_and_no_default_raises(self):
        c = MonotonicTTLCache()
        with pytest.raises(ValueError):
            c.set("key", "val")  # Line 153

    def test_set_negative_ttl_raises(self):
        c = MonotonicTTLCache()
        with pytest.raises(ValueError):
            c.set("key", "val", ttl_ms=-1)

    def test_set_with_default_ttl(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        c.set("key", "val")
        assert c.get("key") == "val"

    def test_get_expired_returns_none(self):
        # Use custom clock for deterministic expiry
        fake_time = [0]
        def clock():
            return fake_time[0]

        c = MonotonicTTLCache(clock=clock)
        c.set("key", "val", ttl_ms=100)

        # Advance past expiry
        fake_time[0] = ns_from_ms(200)
        assert c.get("key") is None  # Line 213-219 (stale hit)

    def test_get_miss(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        assert c.get("nonexistent") is None  # Line 207

    def test_lru_eviction(self):
        c = MonotonicTTLCache(max_entries=2, default_ttl_ms=10000)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)  # Evicts "a" (LRU)
        assert c.get("a") is None
        assert c.get("b") == 2
        assert c.get("c") == 3
        assert c.get_metrics()["cache_evictions_total"] == 1

    def test_lru_eviction_all_pinned(self):
        c = MonotonicTTLCache(max_entries=2, default_ttl_ms=10000)
        c.set("a", 1, pinned=True)
        c.set("b", 2, pinned=True)
        # All pinned — cannot evict, should log warning but not crash (Line 175-180)
        c.set("c", 3)  # Tries to evict, fails, adds anyway
        assert c.size() == 3

    def test_set_updates_existing(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        c.set("key", "v1")
        c.set("key", "v2")
        assert c.get("key") == "v2"


class TestCachePeekDelete:
    def test_peek(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        c.set("key", "val")
        entry = c.peek("key")
        assert entry is not None
        assert entry[0] == "val"

    def test_peek_miss(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        assert c.peek("x") is None

    def test_delete_existing(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        c.set("key", "val")
        assert c.delete("key") is True
        assert c.size() == 0

    def test_delete_nonexistent(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        assert c.delete("x") is False


class TestCacheCleanup:
    def test_cleanup_expired_entries(self):
        fake_time = [0]
        def clock():
            return fake_time[0]

        c = MonotonicTTLCache(clock=clock, default_ttl_ms=100)
        c.set("a", 1)
        c.set("b", 2)

        # Advance past expiry
        fake_time[0] = ns_from_ms(200)
        stats = c.cleanup_expired()
        assert stats.expired == 2
        assert c.size() == 0

    def test_cleanup_with_budget(self):
        fake_time = [0]
        def clock():
            return fake_time[0]

        c = MonotonicTTLCache(clock=clock, default_ttl_ms=100)
        for i in range(5):
            c.set(f"k{i}", i)
        
        fake_time[0] = ns_from_ms(200)
        stats = c.cleanup_expired(budget=2)
        assert stats.scanned == 2  # Budget limits scan


class TestCacheJanitor:
    def test_start_stop_janitor(self):
        c = MonotonicTTLCache(default_ttl_ms=1000, janitor_interval_ms=50)
        c.start_janitor()
        assert c._janitor_running is True
        
        # Start again — should be idempotent (Line 325-326)
        c.start_janitor()
        
        time.sleep(0.1)  # Let janitor run once
        c.stop_janitor()
        assert c._janitor_running is False
        metrics = c.get_metrics()
        assert metrics["janitor_runs_total"] >= 1

    def test_stop_janitor_not_started(self):
        c = MonotonicTTLCache(default_ttl_ms=1000)
        c.stop_janitor()  # No crash (Line 343-344)

    def test_capacity_and_size(self):
        c = MonotonicTTLCache(max_entries=100, default_ttl_ms=1000)
        assert c.capacity() == 100
        assert c.size() == 0
