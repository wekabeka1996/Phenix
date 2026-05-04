"""Coverage tests for IdempotencyStore — targeting missing lines/branches."""
import pytest
import time
from vfoundation.core.idempotency.idempotency import IdempotencyStore, InflightState


class TestIdempotencyStoreBasic:
    def test_defaults_from_config(self):
        s = IdempotencyStore()
        assert s.default_ttl_ms > 0

    def test_custom_params(self):
        s = IdempotencyStore(default_ttl_ms=5000, max_entries=100)
        assert s.default_ttl_ms == 5000

    def test_legacy_seen_remember_get(self):
        s = IdempotencyStore()
        assert s.seen("rid1") is False
        s.remember("rid1", "result1")
        assert s.seen("rid1") is True
        assert s.get("rid1") == "result1"


class TestIdempotencyStoreBegin:
    def test_begin_acquire(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        status = s.begin("k1")
        assert status["acquired"] is True

    def test_begin_inflight(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        s.begin("k1")  # Acquired
        status = s.begin("k1")  # Inflight
        assert status["inflight"] is True  # Line 108-109

    def test_begin_dedup_after_complete(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        s.begin("k1")
        s.complete("k1", "result")
        status = s.begin("k1")
        assert status["dedup"] is True  # Line 99-100

    def test_begin_expired_inflight_reacquires(self):
        s = IdempotencyStore(default_ttl_ms=5000, idem_pending_ttl_ms=1)
        s.begin("k1")  # Acquired with 1ms pending TTL
        time.sleep(0.01)  # Wait for expiry
        status = s.begin("k1")
        assert status["acquired"] is True  # Line 112 expired removal

    def test_begin_over_cap(self):
        s = IdempotencyStore(default_ttl_ms=5000, idem_inflight_cap=1)
        s.begin("k1")  # Acquired — cap is now full
        status = s.begin("k2")  # Over cap
        assert status.get("over_cap") is True  # Line 118-120


class TestIdempotencyStoreComplete:
    def test_complete_and_get_if_done(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        s.begin("k1")
        s.complete("k1", "result1")
        assert s.get_if_done("k1") == "result1"

    def test_get_if_done_pending_returns_none(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        s.begin("k1")  # Still pending
        assert s.get_if_done("k1") is None  # Line 172 PENDING sentinel

    def test_get_if_done_not_found(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        assert s.get_if_done("nonexistent") is None  # Line 182


class TestIdempotencyStoreKeyMethods:
    def test_key_seen_and_remember(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        assert s.key_seen("k1") is False
        s.key_remember("k1", "v1")
        assert s.key_seen("k1") is True
        assert s.key_get("k1") == "v1"


class TestIdempotencyStoreCleanup:
    def test_cleanup_expired_inflight(self):
        s = IdempotencyStore(default_ttl_ms=5000, idem_pending_ttl_ms=1)
        s.begin("k1")  # PENDING with 1ms TTL
        time.sleep(0.01)
        s.cleanup_expired()  # Line 225-226, 229-230
        metrics = s.get_metrics()
        assert metrics["idem_inflight_evicted_total"] >= 1
        assert metrics["idem_pending_ttl_near_expiry_total"] >= 1

    def test_cleanup_expired_done(self):
        s = IdempotencyStore(default_ttl_ms=1, idem_pending_ttl_ms=1)
        s.begin("k1")
        s.complete("k1", "result")
        time.sleep(0.01)
        s.cleanup_expired()

    def test_start_stop_janitor(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        s.start_janitor()
        time.sleep(0.01)
        s.stop_janitor()

    def test_get_metrics(self):
        s = IdempotencyStore(default_ttl_ms=5000)
        m = s.get_metrics()
        assert "idem_acquired" in m
        assert "cache_entries" in m
        assert "janitor_runs_total" in m
