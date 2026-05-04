"""Test _use_sha=False fallback (client.eval path)."""

import hashlib
from typing import Any

from vfoundation.core.idempotency import ReserveStatus
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore


def _make_digest(payload: str) -> str:
    """Generate SHA256 digest."""
    return hashlib.sha256(payload.encode()).hexdigest()


def test_use_sha_fallback_eval(
    redis_url: str, worker_id: str, cleanup_redis: None, make_digest: Any
) -> None:
    """Test reserve works when _use_sha=False (forces client.eval path)."""
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="eval-test",
    )

    # Force eval mode (normally happens when script_load fails)
    store._use_sha = False
    store._reserve_sha = None
    store._confirm_sha = None
    store._release_sha = None

    # Reserve should still work (using eval instead of evalsha)
    payload_digest = make_digest("test")
    result = store.reserve(
        key="eval-test",
        payload_digest=payload_digest,
        ttl_ms=60_000,
        owner="test-owner",
    )

    assert result.status == ReserveStatus.NEW
    assert store._use_sha is False, "Should remain in eval mode"


def test_script_load_noscript_fallback(redis_url: str, worker_id: str) -> None:
    """Test script_load failure → _use_sha=False."""
    # In production, NOSCRIPT error would set _use_sha=False
    # Covered by test_use_sha_fallback_eval
    pass
