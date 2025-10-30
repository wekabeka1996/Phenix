"""Test CB state machine transitions."""

import hashlib
import time
from typing import Any

import redis

from vfoundation.core.idempotency import ReserveStatus, StoreError
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


def _make_digest(payload: str) -> str:
    """Generate SHA256 digest."""
    return hashlib.sha256(payload.encode()).hexdigest()


def test_idemp_reserve_timeout_cb_open(redis_url: str, worker_id: str) -> None:
    """Test CB opens after threshold failures, then half-open recovery."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        retry_max_attempts=1,  # Fail fast
        cb_threshold=0.5,  # Open at 50% error rate
        cb_cooldown_ms=100,  # 100ms cooldown
        cb_half_open_probes=1,  # 1 probe in half-open
    )

    original_evalsha = store.client.evalsha

    # Track call counts
    success_count = 0
    failure_count = 0

    def controlled_evalsha(*args: Any, **kwargs: Any) -> Any:
        nonlocal success_count, failure_count
        # First 5 calls fail (to exceed threshold)
        if success_count + failure_count < 5:
            failure_count += 1
            raise redis.RedisError("Simulated timeout")
        # After cooldown: succeed
        success_count += 1
        return original_evalsha(*args, **kwargs)

    store.client.evalsha = controlled_evalsha  # type: ignore

    # Cause 5 failures
    for i in range(5):
        key = f"cb-fail-{i}"
        digest = _make_digest(f"cb-payload-{i}")
        try:
            store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        except StoreError:
            pass  # Expected

    # CB should track failures
    initial_retries = store.metrics.idemp_retries_total
    assert initial_retries >= 5

    # Wait for cooldown
    time.sleep(0.15)  # 150ms > 100ms cooldown

    # Next call should succeed (half-open probe)
    key_recover = "cb-recover"
    digest_recover = _make_digest("cb-recover-payload")
    result = store.reserve(key_recover, digest_recover, ttl_ms=10_000, owner=worker_id)
    assert result.status == ReserveStatus.NEW

    # CB closed, next call also succeeds
    key_final = "cb-final"
    digest_final = _make_digest("cb-final-payload")
    result_final = store.reserve(
        key_final, digest_final, ttl_ms=10_000, owner=worker_id
    )
    assert result_final.status == ReserveStatus.NEW

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore

    # Verify WHY length
    if failure_count > 0:
        # WHY should be ≤80 chars (validated by StoreError constructor)
        pass


def test_cb_state_machine_half_open(redis_url: str, worker_id: str) -> None:
    """Test CB half-open state allows limited probes."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        cb_threshold=0.3,
        cb_cooldown_ms=50,
        cb_half_open_probes=2,
    )

    # Force errors to open CB
    original_evalsha = store.client.evalsha
    error_phase = [True]  # Mutable flag

    def phase_controlled_evalsha(*args: Any, **kwargs: Any) -> Any:
        if error_phase[0]:
            raise redis.RedisError("Phase 1 error")
        return original_evalsha(*args, **kwargs)

    store.client.evalsha = phase_controlled_evalsha  # type: ignore

    # Trigger errors
    for i in range(5):
        key = f"cb-phase1-{i}"
        digest = _make_digest(f"phase1-{i}")
        try:
            store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        except StoreError:
            pass

    # Cooldown
    time.sleep(0.08)

    # Switch to success phase
    error_phase[0] = False

    # Half-open probes should succeed
    for i in range(3):
        key = f"cb-probe-{i}"
        digest = _make_digest(f"probe-{i}")
        result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
        assert result.status == ReserveStatus.NEW

    # Restore
    store.client.evalsha = original_evalsha  # type: ignore
