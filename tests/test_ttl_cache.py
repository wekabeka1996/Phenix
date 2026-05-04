"""
Tests for MonotonicTTLCache
"""

import time
import threading
import pytest
from vfoundation.core.cache.ttl_cache import MonotonicTTLCache


class TestMonotonicTTLCache:
    def test_basic_set_get(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.size() == 1

    def test_get_nonexistent(self):
        cache = MonotonicTTLCache(max_entries=10)
        assert cache.get("missing") is None

    def test_ttl_expiration(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=50)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(0.08)  # Wait longer for reliable expiration (80ms > 50ms TTL)
        assert cache.get("key1") is None
        assert cache.size() == 0

    def test_custom_ttl(self):
        cache = MonotonicTTLCache(max_entries=10)
        cache.set("key1", "value1", ttl_ms=50)
        assert cache.get("key1") == "value1"
        time.sleep(0.08)  # Wait longer for reliable expiration
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = MonotonicTTLCache(max_entries=2, default_ttl_ms=1000)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.size() == 2

    def test_lru_ordering(self):
        cache = MonotonicTTLCache(max_entries=3, default_ttl_ms=1000)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.get("key1")  # Move key1 to end
        cache.set("key4", "value4")  # Should evict key2
        assert cache.get("key2") is None
        assert cache.get("key1") == "value1"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_peek_no_lru_change(self):
        cache = MonotonicTTLCache(max_entries=3, default_ttl_ms=1000)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.peek("key1")  # Should not change LRU
        cache.set("key4", "value4")  # Should evict key1
        assert cache.get("key1") is None

    def test_delete(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=1000)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("missing") is False

    def test_cleanup_expired(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=50)
        cache.set("key1", "value1")
        time.sleep(0.08)  # Wait longer for reliable expiration (80ms > 50ms TTL)
        cache.set("key2", "value2", ttl_ms=1000)  # Won't expire
        stats = cache.cleanup_expired()
        assert stats.expired == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_cleanup_budget(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=50)
        for i in range(5):
            cache.set(f"key{i}", f"value{i}")
        time.sleep(0.08)  # Wait longer for reliable expiration
        stats = cache.cleanup_expired(budget=3)
        assert stats.scanned == 3
        assert stats.expired <= 3

    def test_metrics(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=1000)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("missing")  # Miss
        metrics = cache.get_metrics()
        assert metrics["cache_hits_total"] == 1
        assert metrics["cache_misses_total"] == 1
        assert metrics["cache_entries"] == 1

    def test_stale_hit_metric(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=50)
        cache.set("key1", "value1")
        time.sleep(0.1)  # Wait longer for expiration
        cache.get("key1")  # Stale hit
        metrics = cache.get_metrics()
        assert metrics["cache_stale_hits_total"] == 1

    def test_eviction_metric(self):
        cache = MonotonicTTLCache(max_entries=1, default_ttl_ms=1000)
        cache.set("key1", "value1")
        cache.set("key2", "value2")  # Evicts key1
        metrics = cache.get_metrics()
        assert metrics["cache_evictions_total"] == 1

    def test_janitor_basic(self):
        cache = MonotonicTTLCache(
            max_entries=10, default_ttl_ms=100, janitor_interval_ms=50
        )
        cache.set("key1", "value1")
        cache.start_janitor()
        time.sleep(0.2)  # Let janitor run
        cache.stop_janitor()
        metrics = cache.get_metrics()
        assert metrics["janitor_runs_total"] > 0

    def test_janitor_cleanup(self):
        cache = MonotonicTTLCache(
            max_entries=10, default_ttl_ms=50, janitor_interval_ms=100
        )
        cache.set("key1", "value1")
        cache.start_janitor()
        time.sleep(0.2)  # Wait for expiration and cleanup
        cache.stop_janitor()
        assert cache.get("key1") is None
        metrics = cache.get_metrics()
        assert metrics["janitor_expired_total"] >= 1

    def test_concurrent_access(self):
        cache = MonotonicTTLCache(max_entries=100, default_ttl_ms=1000)

        def worker():
            for i in range(100):
                cache.set(f"key{i}", f"value{i}")
                cache.get(f"key{i}")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash, basic sanity check
        assert cache.size() <= 100

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            MonotonicTTLCache(max_entries=0)
        with pytest.raises(ValueError):
            MonotonicTTLCache(default_ttl_ms=-1)
        with pytest.raises(ValueError):
            MonotonicTTLCache(janitor_interval_ms=0)

    def test_pinned_entries_not_evicted(self):
        cache = MonotonicTTLCache(max_entries=2, default_ttl_ms=1000)
        cache.set("key1", "value1", pinned=True)
        cache.set("key2", "value2", pinned=True)
        cache.set("key3", "value3")  # Should not evict pinned entries
        # Cache should have 3 entries (over capacity) because pinned entries can't be evicted
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.size() == 3

    def test_pinned_expired_can_be_cleaned(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=50)
        cache.set("key1", "value1", pinned=True)
        time.sleep(0.08)  # Wait longer for reliable expiration (80ms > 50ms TTL)
        stats = cache.cleanup_expired()
        assert stats.expired == 1
        assert cache.get("key1") is None

    def test_janitor_threads_active_metric(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=1000)
        assert cache.get_metrics()["janitor_threads_active"] == 0
        cache.start_janitor()
        assert cache.get_metrics()["janitor_threads_active"] == 1
        cache.stop_janitor()
        assert cache.get_metrics()["janitor_threads_active"] == 0

    def test_janitor_idempotent(self):
        cache = MonotonicTTLCache(max_entries=10, default_ttl_ms=1000)
        cache.start_janitor()
        cache.start_janitor()  # Should not create second thread
        assert cache.get_metrics()["janitor_threads_active"] == 1
        cache.stop_janitor()
