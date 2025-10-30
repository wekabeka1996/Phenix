"""
Test CB full cycle (open → half-open → close) — lines 272-285.

Strategy: Verify CB state machine with controlled error injection.
"""

import time

import pytest

from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore
from vfoundation.core.idempotency.errors import CBOpenError


def test_cb_check_while_open_raises_error(
    redis_url: str,
    cleanup_redis: None,
) -> None:
    """
    Cover lines 252-254: _check_cb raises CBOpenError when OPEN.
    """
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="cb-check-test",
        cb_threshold=1,
        cb_cooldown_ms=1000,
    )

    # Force CB OPEN
    store._cb_state = "OPEN"
    store._cb_open_until_ns = time.time_ns() + 1_000_000_000  # 1 sec

    # _check_cb should raise
    with pytest.raises(CBOpenError):
        store._check_cb("test-operation")


def test_cb_counter_reset_at_200(
    redis_url: str,
    cleanup_redis: None,
) -> None:
    """
    Cover lines 283-285: Counter reset when total_count >= 200.
    """
    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="cb-reset-test",
    )

    # Set counters high
    store._cb_state = "CLOSED"
    store._cb_total_count = 200
    store._cb_error_count = 50

    # Record one more result
    store._record_cb_result(success=True)

    # Counters should reset
    assert store._cb_error_count == 0
    assert store._cb_total_count == 0
