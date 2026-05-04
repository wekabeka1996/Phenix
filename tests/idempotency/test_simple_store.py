"""Tests for simple_redis_store — coverage uplift."""

import hashlib

import pytest

from vfoundation.core.idempotency import (
    MissingError,
    ReserveStatus,
)
from vfoundation.core.idempotency.backends.simple_redis_store import (
    SimpleRedisIdempotencyStore,
)


def _make_digest(payload: str) -> str:
    """Generate SHA256 digest."""
    return hashlib.sha256(payload.encode()).hexdigest()


def test_simple_store_reserve_new(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore reserve NEW."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "simple-new-key"
    digest = _make_digest("simple-payload")

    result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result.status == ReserveStatus.NEW


def test_simple_store_confirm(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore confirm."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "simple-confirm-key"
    digest = _make_digest("simple-confirm-payload")

    # Reserve then confirm
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    result = store.confirm(key, final_status="SUCCESS", meta={})

    from vfoundation.core.idempotency import ConfirmStatus

    assert result.status == ConfirmStatus.CONFIRMED


def test_simple_store_release(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore release."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "simple-release-key"
    digest = _make_digest("simple-release-payload")

    # Reserve then release
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    result = store.release(key, owner=worker_id)

    from vfoundation.core.idempotency import ReleaseStatus

    assert result.status == ReleaseStatus.RELEASED


def test_simple_store_get_status(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore get_status."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "simple-status-key"
    digest = _make_digest("simple-status-payload")

    # Empty initially
    from vfoundation.core.idempotency import GetStatus

    status1 = store.get_status(key)
    assert status1.status == GetStatus.EMPTY

    # After reserve: HELD
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    status2 = store.get_status(key)
    assert status2.status == GetStatus.HELD


def test_simple_store_confirm_missing(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore confirm on missing key."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    with pytest.raises(MissingError):
        store.confirm("missing-simple-key", final_status="DONE", meta={})


def test_simple_store_release_missing(redis_url: str, worker_id: str) -> None:
    """Test SimpleRedisIdempotencyStore release on missing key."""
    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    with pytest.raises(MissingError):
        store.release("missing-simple-release-key", owner=worker_id)
