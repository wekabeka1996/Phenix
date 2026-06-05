"""Tests for vfoundation.core.cache.ttl_cache — MonotonicTTLCache."""
from __future__ import annotations

import time
import pytest

from vfoundation.core.cache.ttl_cache import (
    MonotonicTTLCache,
    CleanupStats,
    ns_from_ms,
    ms_from_ns,
)


class TestHelperConversions:
    def test_ns_from_ms(self) -> None:
        assert ns_from_ms(1) == 1_000_000
        assert ns_from_ms(1000) == 1_000_000_000

    def test_ms_from_ns(self) -> None:
        assert ms_from_ns(1_000_000) == 1
        assert ms_from_ns(999_999) == 0  # floor


class TestCacheInit:
    def test_bad_max_entries(self) -> None:
        with pytest.raises(ValueError):
            MonotonicTTLCache(max_entries=0)

    def test_bad_default_ttl(self) -> None:
        with pytest.raises(ValueError):
            MonotonicTTLCache(default_ttl_ms=-1)

    def test_good_defaults(self) -> None:
        c = MonotonicTTLCache(max_entries=100, default_ttl_ms=5000)
        assert c.capacity() == 100
        assert c.size() == 0


class TestSetGet:
    def test_roundtrip(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        c.set("k1", "v1")
        assert c.get("k1") == "v1"

    def test_miss(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        assert c.get("nope") is None

    def test_explicit_ttl(self) -> None:
        c = MonotonicTTLCache(max_entries=10)
        c.set("k1", "v1", ttl_ms=5000)
        assert c.get("k1") == "v1"

    def test_set_requires_ttl_when_no_default(self) -> None:
        c = MonotonicTTLCache(max_entries=10)
        with pytest.raises(ValueError):
            c.set("k1", "v1")

    def test_negative_ttl_raises(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        with pytest.raises(ValueError):
            c.set("k1", "v1", ttl_ms=-1)


class TestExpiration:
    def test_expired_entry_returns_none(self) -> None:
        # Use a fake clock
        now = [time.monotonic_ns()]
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=100, clock=lambda: now[0])
        c.set("k1", "v1")
        assert c.get("k1") == "v1"
        now[0] += ns_from_ms(200)  # advance past TTL
        assert c.get("k1") is None


class TestLRUEviction:
    def test_evicts_oldest(self) -> None:
        c = MonotonicTTLCache(max_entries=2, default_ttl_ms=5000)
        c.set("k1", "v1")
        c.set("k2", "v2")
        c.set("k3", "v3")  # should evict k1
        assert c.get("k1") is None
        assert c.get("k2") == "v2"
        assert c.get("k3") == "v3"

    def test_pinned_not_evicted(self) -> None:
        c = MonotonicTTLCache(max_entries=2, default_ttl_ms=5000)
        c.set("pinned", "p", pinned=True)
        c.set("k2", "v2")
        c.set("k3", "v3")  # should evict k2 (pinned is protected)
        assert c.get("pinned") == "p"
        assert c.get("k2") is None
        assert c.get("k3") == "v3"


class TestDelete:
    def test_delete_existing(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        c.set("k1", "v1")
        assert c.delete("k1") is True
        assert c.get("k1") is None

    def test_delete_nonexistent(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        assert c.delete("nope") is False


class TestPeek:
    def test_peek_without_updating_lru(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        c.set("k1", "v1")
        result = c.peek("k1")
        assert result is not None
        assert result[0] == "v1"

    def test_peek_miss(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        assert c.peek("nope") is None


class TestCleanup:
    def test_cleanup_removes_expired(self) -> None:
        now = [time.monotonic_ns()]
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=100, clock=lambda: now[0])
        c.set("k1", "v1")
        c.set("k2", "v2")
        now[0] += ns_from_ms(200)
        stats = c.cleanup_expired()
        assert isinstance(stats, CleanupStats)
        assert stats.expired == 2
        assert c.size() == 0


class TestMetrics:
    def test_metrics_keys(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        m = c.get_metrics()
        for key in ("cache_hits_total", "cache_misses_total",
                     "cache_stale_hits_total", "cache_evictions_total",
                     "cache_entries"):
            assert key in m

    def test_hit_miss_counters(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000)
        c.set("k1", "v1")
        c.get("k1")   # hit
        c.get("nope")  # miss
        m = c.get_metrics()
        assert m["cache_hits_total"] == 1
        assert m["cache_misses_total"] == 1


class TestJanitor:
    def test_start_stop_janitor(self) -> None:
        c = MonotonicTTLCache(max_entries=10, default_ttl_ms=5000,
                              janitor_interval_ms=50)
        c.start_janitor()
        time.sleep(0.15)
        c.stop_janitor(timeout_s=2.0)
        m = c.get_metrics()
        assert m["janitor_runs_total"] >= 1
