"""Tests for vfoundation.core.idempotency.backends.simple_redis_store — using fakeredis."""

from __future__ import annotations

import pytest

fakeredis = pytest.importorskip("fakeredis")

import fakeredis as _fakeredis

from vfoundation.core.idempotency.backends.simple_redis_store import (
    SimpleRedisIdempotencyStore,
)
from vfoundation.core.idempotency.errors import (
    BusyError,
    ConflictError,
    MissingError,
    StoreError,
)
from vfoundation.core.idempotency.store import (
    ConfirmStatus,
    GetStatus,
    ReleaseStatus,
    ReserveStatus,
)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> SimpleRedisIdempotencyStore:
    """Create a SimpleRedisIdempotencyStore backed by fakeredis."""
    import redis as _redis_mod

    # Patch redis.from_url to return fakeredis instance
    fake_server = _fakeredis.FakeServer()
    fake_client = _fakeredis.FakeRedis(server=fake_server, decode_responses=True)

    def _from_url(*args, **kwargs):
        return fake_client

    monkeypatch.setattr(_redis_mod, "from_url", _from_url)

    return SimpleRedisIdempotencyStore(
        redis_url="redis://fake:6379/0",
        worker_id="test-worker",
        ttl_ms=60_000,
        timeout_ms=100,
    )


# ── reserve ───────────────────────────────────────────────────────────────


class TestReserve:
    def test_new_key_returns_new(self, store: SimpleRedisIdempotencyStore) -> None:
        r = store.reserve("k1", "digest1", 60000, "test-worker")
        assert r.status == ReserveStatus.NEW
        assert r.lease_ms == 60000

    def test_same_digest_returns_duplicate_same(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "digest1", 60000, "test-worker")
        r = store.reserve("k1", "digest1", 60000, "test-worker")
        assert r.status == ReserveStatus.DUPLICATE_SAME

    def test_different_digest_raises_conflict(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "digest1", 60000, "test-worker")
        with pytest.raises(ConflictError):
            store.reserve("k1", "digest-DIFFERENT", 60000, "test-worker")

    def test_different_owner_raises_busy(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "digest1", 60000, "test-worker")
        with pytest.raises(BusyError):
            store.reserve("k1", "digest1", 60000, "other-worker")

    def test_metrics_tracked(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        assert store.metrics.idemp_reserve_total.get("NEW", 0) == 1
        assert len(store.metrics.reserve_latencies) >= 1


# ── confirm ───────────────────────────────────────────────────────────────


class TestConfirm:
    def test_confirm_existing_key(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        r = store.confirm("k1", "ORDER_PLACED", meta={"exchange_id": "e1"})
        assert r.status == ConfirmStatus.CONFIRMED

    def test_confirm_missing_raises(self, store: SimpleRedisIdempotencyStore) -> None:
        with pytest.raises(MissingError):
            store.confirm("nonexistent", "ORDER_PLACED")

    def test_confirm_metrics(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        store.confirm("k1", "ORDER_PLACED")
        assert store.metrics.idemp_confirm_total.get("CONFIRMED", 0) == 1


# ── get_status ────────────────────────────────────────────────────────────


class TestGetStatus:
    def test_empty_key(self, store: SimpleRedisIdempotencyStore) -> None:
        r = store.get_status("nonexistent")
        assert r.status == GetStatus.EMPTY

    def test_held_key(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        r = store.get_status("k1")
        assert r.status == GetStatus.HELD
        assert r.owner == "test-worker"
        assert r.payload_digest == "d1"

    def test_confirmed_key(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        store.confirm("k1", "ORDER_PLACED", meta={"qty": 1})
        r = store.get_status("k1")
        assert r.status == GetStatus.CONFIRMED
        assert r.meta == {"qty": 1}


# ── release ───────────────────────────────────────────────────────────────


class TestRelease:
    def test_release_owned_key(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        r = store.release("k1", "test-worker")
        assert r.status == ReleaseStatus.RELEASED
        # After release, key should be empty
        assert store.get_status("k1").status == GetStatus.EMPTY

    def test_release_missing_raises(self, store: SimpleRedisIdempotencyStore) -> None:
        with pytest.raises(MissingError):
            store.release("nonexistent", "test-worker")

    def test_release_wrong_owner_raises(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        with pytest.raises(StoreError):
            store.release("k1", "other-worker")

    def test_release_metrics(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        store.release("k1", "test-worker")
        assert store.metrics.idemp_release_total.get("RELEASED", 0) == 1


# ── Full lifecycle ────────────────────────────────────────────────────────


class TestFullLifecycle:
    def test_reserve_confirm_get(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("order-123", "sha256abc", 60000, "test-worker")
        store.confirm("order-123", "FILLED", meta={"filled_qty": 0.5})
        status = store.get_status("order-123")
        assert status.status == GetStatus.CONFIRMED
        assert status.meta["filled_qty"] == 0.5

    def test_reserve_release_reserve_again(self, store: SimpleRedisIdempotencyStore) -> None:
        store.reserve("k1", "d1", 60000, "test-worker")
        store.release("k1", "test-worker")
        # Should be able to reserve again after release
        r = store.reserve("k1", "d2", 60000, "test-worker")
        assert r.status == ReserveStatus.NEW
