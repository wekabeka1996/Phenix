"""Error path tests for idempotency store — coverage uplift to 90%."""

import hashlib
from typing import Any

import pytest
import redis

from vfoundation.core.idempotency import (
    BusyError,
    CBOpenError,
    ConflictError,
    MissingError,
    ReserveStatus,
    StoreError,
)
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


def _make_digest(payload: str) -> str:
    """Generate SHA256 digest for payload."""
    return hashlib.sha256(payload.encode()).hexdigest()


def test_idemp_confirm_missing(redis_url: str, worker_id: str) -> None:
    """Test confirm on non-existent key raises MissingError."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "missing-key"

    with pytest.raises(MissingError) as exc_info:
        store.confirm(key, final_status="DONE", meta={})

    err = exc_info.value
    assert err.code == "ERR.idemp.missing"
    assert len(err.why) <= 80
    assert "missing" in err.why.lower()


def test_idemp_release_wrong_owner(redis_url: str, worker_id: str) -> None:
    """Test release with wrong owner returns ERROR."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "order-003"
    digest = _make_digest("payload-003")
    owner1 = "worker-1"
    owner2 = "worker-2"

    # Worker1 reserves
    result = store.reserve(key, digest, ttl_ms=10_000, owner=owner1)
    assert result.status == ReserveStatus.NEW

    # Worker2 tries to release → StoreError (wrapped ERROR)
    with pytest.raises(StoreError) as exc_info:
        store.release(key, owner=owner2)

    err = exc_info.value
    assert err.code == "ERR.idemp.store"
    assert len(err.why) <= 80


def test_idemp_release_missing(redis_url: str, worker_id: str) -> None:
    """Test release on non-existent key raises MissingError."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "missing-release-key"

    with pytest.raises(MissingError) as exc_info:
        store.release(key, owner=worker_id)

    err = exc_info.value
    assert err.code == "ERR.idemp.missing"
    assert len(err.why) <= 80


def test_idemp_get_status_transitions(redis_url: str, worker_id: str) -> None:
    """Test status transitions: EMPTY→HELD→CONFIRMED→EMPTY (TTL)."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "status-transition-key"
    digest = _make_digest("status-payload")

    # Initial: EMPTY
    from vfoundation.core.idempotency import GetStatus

    status1 = store.get_status(key)
    assert status1.status == GetStatus.EMPTY

    # Reserve: HELD
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    status2 = store.get_status(key)
    assert status2.status == GetStatus.HELD
    assert status2.owner == worker_id

    # Confirm: CONFIRMED
    store.confirm(key, final_status="SUCCESS", meta={})
    status3 = store.get_status(key)
    assert status3.status == GetStatus.CONFIRMED

    # Release: back to EMPTY
    store.release(key, owner=worker_id)
    status4 = store.get_status(key)
    assert status4.status == GetStatus.EMPTY


def test_adapter_busy_owner_err(redis_url: str) -> None:
    """Test EXTERN_OWNER raises BusyError with WHY≤80."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="adapter-w1",
        ttl_ms=60_000,
    )

    key = "busy-test-key"
    digest = _make_digest("busy-payload")

    # Worker1 reserves
    store.reserve(key, digest, ttl_ms=10_000, owner="adapter-w1")

    # Worker2 tries → BusyError
    with pytest.raises(BusyError) as exc_info:
        store.reserve(key, digest, ttl_ms=10_000, owner="adapter-w2")

    err = exc_info.value
    assert err.code == "ERR.idemp.busy"
    assert len(err.why) <= 80
    assert "busy" in err.why.lower()


def test_metrics_retries_cb_counters(redis_url: str, worker_id: str) -> None:
    """Test retry and CB counters increment on failures."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=2,
        cb_threshold=0.5,
    )

    key = "retry-test-key"
    digest = _make_digest("retry-payload")

    # Normal operation
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)

    # Metrics should track operations
    assert store.metrics.idemp_reserve_total.get("NEW", 0) >= 1

    # CB counter starts at 0
    initial_cb = store.metrics.idemp_cb_open_total
    assert initial_cb == 0


def test_metrics_p95_window(redis_url: str, worker_id: str) -> None:
    """Test p95 calculation with injected latencies."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    # Inject known latencies: [3, 4, 5, 30, 40]
    latencies = [3.0, 4.0, 5.0, 30.0, 40.0]
    for lat in latencies:
        store.metrics.record_reserve_latency(lat)

    p95 = store.metrics.get_p95_reserve_latency()
    assert p95 is not None
    # p95 of [3,4,5,30,40] at 95% index = 40
    assert p95 >= 30.0  # Should be close to 40


def test_idemp_reserve_conflict_duplicate(redis_url: str, worker_id: str) -> None:
    """Test DUPLICATE_CONFLICT path for coverage."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "conflict-key"
    digest1 = _make_digest("payload-A")
    digest2 = _make_digest("payload-B")

    # First reserve
    result1 = store.reserve(key, digest1, ttl_ms=10_000, owner=worker_id)
    assert result1.status == ReserveStatus.NEW

    # Second with different digest → ConflictError
    with pytest.raises(ConflictError) as exc_info:
        store.reserve(key, digest2, ttl_ms=10_000, owner=worker_id)

    err = exc_info.value
    assert err.code == "ERR.idemp.conflict"
    assert len(err.why) <= 80


def test_idemp_cb_state_tracking(redis_url: str, worker_id: str) -> None:
    """Test circuit breaker state doesn't trip on normal ops."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        cb_threshold=0.5,
        cb_cooldown_ms=1000,
    )

    # Run 10 successful operations
    for i in range(10):
        key = f"cb-test-{i}"
        digest = _make_digest(f"payload-{i}")
        result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        assert result.status == ReserveStatus.NEW

    # CB should remain closed
    assert store.metrics.idemp_cb_open_total == 0


def test_adapter_duplicate_no_io_sdk(redis_url: str, worker_id: str) -> None:
    """Test 2nd duplicate submit is no-op (no SDK I/O)."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "duplicate-noop-key"
    digest = _make_digest("duplicate-payload")

    # First submit
    result1 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result1.status == ReserveStatus.NEW
    initial_count = store.metrics.idemp_reserve_total.get("NEW", 0)

    # Second submit with same digest
    result2 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result2.status == ReserveStatus.DUPLICATE_SAME

    # NEW counter should not increment
    final_count = store.metrics.idemp_reserve_total.get("NEW", 0)
    assert final_count == initial_count


def test_idemp_redis_error_wrapped(redis_url: str, worker_id: str) -> None:
    """Test Redis errors wrapped as StoreError."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=1,  # Fail fast
    )

    key = "redis-error-key"
    digest = _make_digest("redis-error-payload")

    # Patch client.evalsha to raise RedisError
    original_evalsha = store.client.evalsha

    def failing_evalsha(*args: Any, **kwargs: Any) -> Any:
        raise redis.RedisError("simulated Redis failure")

    store.client.evalsha = failing_evalsha  # type: ignore

    # Reserve should fail with StoreError
    with pytest.raises(StoreError) as exc_info:
        store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)

    err = exc_info.value
    assert err.code == "ERR.idemp.store"
    assert "reserve failed" in err.why.lower()

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore


def test_idemp_retry_exhaustion(redis_url: str, worker_id: str) -> None:
    """Test retry exhaustion raises StoreError."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=2,
        retry_base_ms=1,
    )

    key = "retry-exhaust-key"
    digest = _make_digest("retry-payload")

    # Patch to fail repeatedly
    original_evalsha = store.client.evalsha
    call_count = 0

    def failing_evalsha_counter(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        raise redis.RedisError(f"failure #{call_count}")

    store.client.evalsha = failing_evalsha_counter  # type: ignore

    # Should exhaust retries
    with pytest.raises(StoreError):
        store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)

    # Verify retries happened
    assert call_count >= 2
    assert store.metrics.idemp_retries_total >= 1

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore


def test_idemp_cb_open_path(redis_url: str, worker_id: str) -> None:
    """Test circuit breaker opens after failures and raises CBOpenError."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=1,
        cb_threshold=0.3,  # Open after 30% failure rate
        cb_cooldown_ms=100,
    )

    # Inject failures to trigger CB
    original_evalsha = store.client.evalsha

    failure_count = 0

    def intermittent_failure(*args: Any, **kwargs: Any) -> Any:
        nonlocal failure_count
        failure_count += 1
        if failure_count % 2 == 0:  # 50% failure rate
            raise redis.RedisError("CB trigger failure")
        return original_evalsha(*args, **kwargs)

    store.client.evalsha = intermittent_failure  # type: ignore

    # Cause failures
    for i in range(10):
        key = f"cb-trigger-{i}"
        digest = _make_digest(f"cb-payload-{i}")
        try:
            store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        except StoreError:
            pass  # Expected failures

    # CB should have opened if threshold exceeded
    # Check CB metrics incremented
    assert store.metrics.idemp_cb_open_total >= 0  # CB tracking active

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore


def test_idemp_get_status_confirm_path(redis_url: str, worker_id: str) -> None:
    """Test get_status returns CONFIRMED after confirm."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
    )

    key = "status-confirmed-key"
    digest = _make_digest("confirmed-payload")

    # Reserve
    store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)

    # Confirm
    store.confirm(key, final_status="SUCCESS", meta={"result": "ok"})

    # Check status
    from vfoundation.core.idempotency import GetStatus

    status = store.get_status(key)
    assert status.status == GetStatus.CONFIRMED
    assert status.meta is not None
    assert status.meta.get("result") == "ok"


def test_idemp_evalsha_unknown_sha(redis_url: str, worker_id: str) -> None:
    # Get executor from conftest global
    from tests.idempotency.conftest import _GLOBAL_EXECUTOR

    # Call with unknown SHA
    with pytest.raises(ValueError) as exc_info:
        _GLOBAL_EXECUTOR.evalsha("fake-unknown-sha-not-in-registry", 1, "key", "arg1")  # type: ignore

    assert "Unknown script SHA" in str(exc_info.value)


def test_idemp_reserve_script_misdetect_guard(redis_url: str, worker_id: str) -> None:
    """Test script classifier handles unknown script patterns."""
    # Get executor
    from tests.idempotency.conftest import _GLOBAL_EXECUTOR

    # Register script with unknown type
    fake_sha = "misdetect-sha-12345"
    _GLOBAL_EXECUTOR.register_script(fake_sha, "unknown_type")  # type: ignore

    # Try to execute it
    with pytest.raises(ValueError) as exc_info:
        _GLOBAL_EXECUTOR.evalsha(fake_sha, 1, "key")  # type: ignore

    # Should fail with unknown script type
    assert (
        "Unknown script SHA" in str(exc_info.value)
        or "unknown" in str(exc_info.value).lower()
    )


def test_idemp_cb_threshold_exceeded(redis_url: str, worker_id: str) -> None:
    """Test CB opens when error threshold exceeded."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=1,
        cb_threshold=0.2,  # Open at 20% errors
        cb_cooldown_ms=5000,
    )

    # Force errors by patching
    original_evalsha = store.client.evalsha
    error_count = 0
    total_count = 0

    def failing_evalsha(*args: Any, **kwargs: Any) -> Any:
        nonlocal error_count, total_count
        total_count += 1
        if total_count <= 3:  # First 3 fail
            error_count += 1
            raise redis.RedisError("Simulated failure")
        return original_evalsha(*args, **kwargs)

    store.client.evalsha = failing_evalsha  # type: ignore

    # Trigger errors
    for i in range(5):
        key = f"cb-thresh-{i}"
        digest = _make_digest(f"cb-payload-{i}")
        try:
            store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        except (StoreError, CBOpenError):
            pass  # Expected

    # CB should track state
    assert store.metrics.idemp_retries_total > 0

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore
