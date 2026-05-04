"""
Functional tests for distributed idempotency store.

Tests 1-7: Basic functional operations (reserve/confirm/release/missing).
SLO: p95 ≤ 10ms for local Redis mock.
"""

import hashlib
from typing import Generator

import pytest

from vfoundation.core.idempotency import (
    BusyError,
    ConflictError,
    MissingError,
    ReserveStatus,
    ConfirmStatus,
    GetStatus,
    ReleaseStatus,
)
from vfoundation.core.idempotency.backends.simple_redis_store import (
    SimpleRedisIdempotencyStore,
)


# Check if fakeredis is available and compatible
REDIS_AVAILABLE = False
try:
    import redis as redis_module
    if hasattr(redis_module, 'ResponseError'):
        # Only try to import fakeredis if redis is compatible
        try:
            import fakeredis
            REDIS_AVAILABLE = True
        except ImportError:
            REDIS_AVAILABLE = False
except (ImportError, AttributeError):
    REDIS_AVAILABLE = False


# Skip all tests in this module if Redis is not available
pytestmark = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="fakeredis not available or incompatible with redis version"
)


@pytest.fixture
def redis_url() -> str:
    """Redis URL for testing (fakeredis)."""
    return "redis://localhost:6379/15"


@pytest.fixture
def worker_id() -> str:
    """Test worker ID."""
    return "test-worker-1"


@pytest.fixture
def store(
    redis_url: str, worker_id: str, monkeypatch: pytest.MonkeyPatch
) -> Generator[SimpleRedisIdempotencyStore, None, None]:
    """Create Redis idempotency store with fakeredis."""
    if not REDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")

    # Monkey-patch redis.from_url to use fakeredis
    def fake_from_url(*args: object, **kwargs: object) -> object:
        return fakeredis.FakeStrictRedis(decode_responses=True)

    monkeypatch.setattr("redis.from_url", fake_from_url)

    store = SimpleRedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        timeout_ms=100,
    )

    yield store

    # Cleanup
    store.client.flushdb()


def _make_digest(payload: str) -> str:
    """Make SHA256 digest of payload."""
    return hashlib.sha256(payload.encode()).hexdigest()


# Test 1: reserve NEW
def test_idemp_reserve_new(store: SimpleRedisIdempotencyStore, worker_id: str) -> None:
    """Test reserve creates NEW record for empty key."""
    key = "order-001"
    digest = _make_digest("order-payload-1")

    result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)

    assert result.status == ReserveStatus.NEW
    assert result.lease_ms == 10_000
    assert store.metrics.idemp_reserve_total.get("NEW") == 1

    # Verify record exists
    status = store.get_status(key)
    assert status.status == GetStatus.HELD
    assert status.owner == worker_id
    assert status.payload_digest == digest


# Test 2: reserve DUPLICATE_SAME
def test_idemp_reserve_duplicate_same(
    store: SimpleRedisIdempotencyStore, worker_id: str
) -> None:
    """Test reserve returns DUPLICATE_SAME for identical payload (idempotent no-op)."""
    key = "order-002"
    digest = _make_digest("same-payload")

    # First reserve
    result1 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result1.status == ReserveStatus.NEW

    # Second reserve with same digest → DUPLICATE_SAME (no-op)
    result2 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result2.status == ReserveStatus.DUPLICATE_SAME
    assert result2.lease_ms == 10_000
    assert store.metrics.idemp_reserve_total.get("DUPLICATE_SAME") == 1


# Test 3: reserve DUPLICATE_CONFLICT
def test_idemp_reserve_duplicate_conflict(
    store: SimpleRedisIdempotencyStore, worker_id: str
) -> None:
    """Test reserve raises ConflictError for different payload (conflict)."""
    key = "order-003"
    digest1 = _make_digest("payload-v1")
    digest2 = _make_digest("payload-v2")

    # First reserve
    result1 = store.reserve(key, digest1, ttl_ms=10_000, owner=worker_id)
    assert result1.status == ReserveStatus.NEW

    # Second reserve with different digest → ConflictError
    with pytest.raises(ConflictError) as exc_info:
        store.reserve(key, digest2, ttl_ms=10_000, owner=worker_id)

    err = exc_info.value
    assert err.code == "ERR.idemp.conflict"
    assert len(err.why) <= 80
    assert "idemp conflict" in err.why
    assert store.metrics.idemp_conflict_total == 1


# Test 4: reserve EXTERN_OWNER → BusyError
def test_idemp_extern_owner_busy(store: SimpleRedisIdempotencyStore) -> None:
    """Test reserve raises BusyError when key held by external owner."""
    key = "order-004"
    digest = _make_digest("payload")
    owner1 = "worker-1"
    owner2 = "worker-2"

    # Worker 1 reserves
    result1 = store.reserve(key, digest, ttl_ms=10_000, owner=owner1)
    assert result1.status == ReserveStatus.NEW

    # Worker 2 tries to reserve → BusyError
    with pytest.raises(BusyError) as exc_info:
        store.reserve(key, digest, ttl_ms=10_000, owner=owner2)

    err = exc_info.value
    assert err.code == "ERR.idemp.busy"
    assert len(err.why) <= 80
    assert "idemp busy" in err.why
    assert store.metrics.idemp_busy_total == 1


# Test 5: confirm OK
def test_idemp_confirm_ok(store: SimpleRedisIdempotencyStore, worker_id: str) -> None:
    """Test confirm updates record to CONFIRMED."""
    key = "order-005"
    digest = _make_digest("payload")

    # Reserve first
    result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result.status == ReserveStatus.NEW

    # Confirm
    confirm_result = store.confirm(
        key, final_status="ORDER_PLACED", meta={"eid": "12345"}
    )
    assert confirm_result.status == ConfirmStatus.CONFIRMED
    assert store.metrics.idemp_confirm_total.get("CONFIRMED") == 1

    # Verify status
    status = store.get_status(key)
    assert status.status == GetStatus.CONFIRMED
    assert status.meta == {"eid": "12345"}


# Test 6: release OK
def test_idemp_release_ok(store: SimpleRedisIdempotencyStore, worker_id: str) -> None:
    """Test release removes record (owner only)."""
    key = "order-006"
    digest = _make_digest("payload")

    # Reserve first
    result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result.status == ReserveStatus.NEW

    # Release
    release_result = store.release(key, owner=worker_id)
    assert release_result.status == ReleaseStatus.RELEASED
    assert store.metrics.idemp_release_total.get("RELEASED") == 1

    # Verify record gone
    status = store.get_status(key)
    assert status.status == GetStatus.EMPTY


# Test 7: missing confirm/release
def test_idemp_missing_confirm_release(
    store: SimpleRedisIdempotencyStore, worker_id: str
) -> None:
    """Test MISSING errors for confirm/release on non-existent keys."""
    key = "order-missing"

    # Confirm on missing key
    with pytest.raises(MissingError) as exc_info:
        store.confirm(key, final_status="DONE")

    err = exc_info.value
    assert err.code == "ERR.idemp.missing"
    assert len(err.why) <= 80
    assert "idemp missing" in err.why

    # Release on missing key
    with pytest.raises(MissingError):
        store.release(key, owner=worker_id)
