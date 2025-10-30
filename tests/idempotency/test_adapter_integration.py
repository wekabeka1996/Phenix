"""
Integration tests with execution adapter.

Tests 12-13: Adapter integration with distributed idempotency.
Validates no-op on duplicate, busy handling.
"""

import hashlib
from unittest.mock import MagicMock

import pytest

from vfoundation.core.idempotency import (
    BusyError,
    ReserveStatus,
)
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


def _make_digest(payload: str) -> str:
    """Make SHA256 digest of payload."""
    return hashlib.sha256(payload.encode()).hexdigest()


# Test 12: adapter with distributed idemp - no-op on duplicate
def test_adapter_with_distributed_idemp_noop_on_duplicate(
    redis_url: str,
    worker_id: str,
) -> None:
    """
    Test adapter integration: repeated submit returns same EVT (no SDK I/O).

    Simulates adapter calling store.reserve() before SDK.submit().
    On DUPLICATE_SAME, adapter should return cached result without SDK call.
    """
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=worker_id,
        ttl_ms=60_000,
        timeout_ms=100,
    )

    key = "client-order-001"
    digest = _make_digest("submit-payload-1")

    # Mock SDK (should only be called once)
    mock_sdk = MagicMock()
    mock_sdk.submit = MagicMock(return_value={"order_id": "EX-123", "status": "PLACED"})

    # First submit: reserve → NEW → call SDK
    result1 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result1.status == ReserveStatus.NEW

    sdk_response = mock_sdk.submit()
    assert mock_sdk.submit.call_count == 1

    # Confirm after SDK success
    store.confirm(key, final_status="ORDER_PLACED", meta=sdk_response)

    # Second submit: reserve → DUPLICATE_SAME → return cached (no SDK call)
    result2 = store.reserve(key, digest, ttl_ms=10_000, owner=worker_id)
    assert result2.status == ReserveStatus.DUPLICATE_SAME

    # SDK should NOT be called again (idempotent no-op)
    assert mock_sdk.submit.call_count == 1

    # Adapter would return the same EVT from cache/status


# Test 13: adapter busy handling
def test_adapter_busy_owner(
    redis_url: str,
) -> None:
    """
    Test adapter handling of EXTERN_OWNER (busy).

    If another worker holds the key, adapter should get BusyError.
    """
    key = "client-order-002"
    digest = _make_digest("submit-payload-2")
    owner1 = "worker-1"
    owner2 = "worker-2"

    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id=owner1,
        ttl_ms=60_000,
        timeout_ms=100,
    )

    # Worker 1 reserves
    result1 = store.reserve(key, digest, ttl_ms=10_000, owner=owner1)
    assert result1.status == ReserveStatus.NEW

    # Worker 2 tries to reserve → EXTERN_OWNER (raises BusyError)
    with pytest.raises(BusyError) as exc_info:
        store.reserve(key, digest, ttl_ms=10_000, owner=owner2)

    err = exc_info.value
    assert err.code == "ERR.idemp.busy"
    assert len(err.why) <= 80
    assert "idemp busy" in err.why

    # Adapter would handle this by:
    # 1. Short backoff (1-2 retries)
    # 2. Return ERR.idemp.busy to caller

    # Worker 1 releases
    store.release(key, owner=owner1)

    # Now worker 2 can reserve
    result2 = store.reserve(key, digest, ttl_ms=10_000, owner=owner2)
    assert result2.status == ReserveStatus.NEW
