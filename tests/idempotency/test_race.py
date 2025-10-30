"""
Concurrency and race condition tests for distributed idempotency.

Tests 8-9: Multi-thread race conditions with LuaExecutor (atomic guarantees).
Validates exactly-once semantics under concurrent load.
"""

import threading
from typing import List, Tuple

import pytest

from vfoundation.core.idempotency import (
    BusyError,
    ConflictError,
)
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


# No longer needed - using conftest fixtures
# try:
#     import fakeredis
#     REDIS_AVAILABLE = True
# except ImportError:
#     REDIS_AVAILABLE = False


@pytest.fixture
def redis_url() -> str:
    return "redis://localhost:6379/15"


# Test 8: concurrent reserve race
def test_idemp_concurrency_reserve_race(
    redis_url: str,
    lua_executor: object,
    make_digest: object,
) -> None:
    """
    Test concurrent reserve from 10 threads → exactly one NEW, rest DUPLICATE_SAME/EXTERN_OWNER.

    Validates exactly-once semantics under race conditions.
    """
    key = "order-race-001"
    digest_func = make_digest  # type: ignore
    digest = digest_func("same-payload")
    num_workers = 10

    results: List[Tuple[str, str]] = []
    barrier = threading.Barrier(num_workers)

    def worker_thread(worker_id: str) -> None:
        """Worker thread for concurrent reserve test."""
        store = RedisIdempotencyStore(
            redis_url=redis_url,
            worker_id=worker_id,
            ttl_ms=60_000,
            timeout_ms=100,
        )

        # Wait for all threads
        barrier.wait()

        # Attempt reserve
        try:
            result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
            results.append((worker_id, result.status.value))
        except (BusyError, ConflictError) as e:
            results.append((worker_id, e.code))

    threads = []
    for i in range(num_workers):
        worker_id = f"worker-{i}"
        t = threading.Thread(target=worker_thread, args=(worker_id,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    # Assertions
    assert len(results) == num_workers

    # Count status distribution
    new_count = sum(1 for _, status in results if status == "NEW")
    duplicate_same_count = sum(1 for _, status in results if status == "DUPLICATE_SAME")
    busy_count = sum(1 for _, status in results if "busy" in status)

    # Exactly one NEW (exactly-once guarantee)
    assert new_count == 1, f"Expected exactly 1 NEW, got {new_count}: {results}"

    # Others should be DUPLICATE_SAME or BUSY
    assert duplicate_same_count + busy_count == num_workers - 1


# Test 9: conflict under race
def test_idemp_conflict_under_race(
    redis_url: str,
    lua_executor: object,
    make_digest: object,
) -> None:
    """
    Test concurrent reserve with DIFFERENT digests → all but one get CONFLICT/BUSY.

    Validates no double "victory" - only one payload wins.
    """
    key = "order-race-002"
    num_workers = 5
    digest_func = make_digest  # type: ignore

    results: List[Tuple[str, str, str]] = []  # (worker_id, digest, status)
    barrier = threading.Barrier(num_workers)

    def worker_with_diff_digest(worker_id: str, digest: str) -> None:
        """Worker thread with unique digest."""
        store = RedisIdempotencyStore(
            redis_url=redis_url,
            worker_id=worker_id,
            ttl_ms=60_000,
            timeout_ms=100,
        )

        barrier.wait()

        try:
            result = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
            results.append((worker_id, digest, result.status.value))
        except (BusyError, ConflictError) as e:
            results.append((worker_id, digest, e.code))

    threads = []
    for i in range(num_workers):
        worker_id = f"worker-{i}"
        digest = digest_func(f"payload-{i}")  # Unique digest per worker

        t = threading.Thread(
            target=worker_with_diff_digest,
            args=(worker_id, digest),
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    # Assertions
    assert len(results) == num_workers

    new_count = sum(1 for _, _, status in results if status == "NEW")
    conflict_count = sum(1 for _, _, status in results if "conflict" in status)
    busy_count = sum(1 for _, _, status in results if "busy" in status)

    # Exactly one NEW (no double victory)
    assert new_count == 1, f"Expected exactly 1 NEW, got {new_count}: {results}"

    # Others should be CONFLICT or BUSY
    assert conflict_count + busy_count == num_workers - 1
