"""Tests for vfoundation.core.idempotency — IdempotencyStore."""
from __future__ import annotations

import time

from vfoundation.core.idempotency.idempotency import IdempotencyStore, InflightState


class TestBeginAcquire:
    def test_first_call_acquires(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        result = store.begin("key-1")
        assert result.get("acquired") is True

    def test_second_call_inflight(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("key-1")
        result = store.begin("key-1")
        assert result.get("inflight") is True

    def test_over_cap_backpressure(self) -> None:
        store = IdempotencyStore(
            default_ttl_ms=5000, max_entries=100, idem_inflight_cap=2,
        )
        store.begin("key-1")
        store.begin("key-2")
        result = store.begin("key-3")
        assert result.get("over_cap") is True


class TestComplete:
    def test_complete_then_get(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("key-1")
        store.complete("key-1", {"ok": True})
        assert store.get_if_done("key-1") == {"ok": True}

    def test_complete_causes_dedup(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("key-1")
        store.complete("key-1", "done")
        result = store.begin("key-1")
        assert result.get("dedup") is True


class TestGetIfDone:
    def test_pending_returns_none(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("key-1")
        assert store.get_if_done("key-1") is None

    def test_unknown_returns_none(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        assert store.get_if_done("nope") is None


class TestLegacyMethods:
    def test_seen_remember_get(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        assert store.seen("r1") is False
        store.remember("r1", "result-1")
        assert store.seen("r1") is True
        assert store.get("r1") == "result-1"

    def test_key_remember_get(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        assert store.key_seen("k1") is False
        store.key_remember("k1", 42)
        assert store.key_seen("k1") is True
        assert store.key_get("k1") == 42


class TestMetrics:
    def test_metrics_keys(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        m = store.get_metrics()
        for k in ("idem_acquired", "idem_inflight", "idem_dedup",
                   "cache_entries", "cache_hits_total", "cache_misses_total"):
            assert k in m, f"Missing metric: {k}"

    def test_acquire_increments_counter(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("a")
        store.begin("b")
        m = store.get_metrics()
        assert m["idem_acquired"] == 2


class TestCleanupExpired:
    def test_cleanup_does_not_crash(self) -> None:
        store = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        store.begin("x")
        store.cleanup_expired()  # should not raise


class TestInflightStateEnum:
    def test_values(self) -> None:
        assert InflightState.PENDING.value == "pending"
        assert InflightState.DONE.value == "done"
