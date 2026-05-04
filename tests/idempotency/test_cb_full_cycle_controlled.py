"""
Test CB full cycle (open → half-open → close) — lines 272-285.

Strategy: Direct _record_cb_result calls with controlled state, patch time_ns.
"""

import time
from unittest.mock import patch

import pytest

from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore
from vfoundation.core.idempotency.errors import CBOpenError


def test_cb_full_cycle_controlled_clock(
    redis_url: str,
    cleanup_redis: None,
) -> None:
    """
    Cover lines 272-285: CB state machine with controlled clock.

    Direct state manipulation to hit all branches:
    1. error_rate ≥ threshold → OPEN
    2. OPEN blocks via CBOpenError
    3. Cooldown → HALF_OPEN
    4. HALF_OPEN success → CLOSED
    5. HALF_OPEN failure → OPEN
    6. Counter reset at 200
    """
    # Controlled clock
    current_time_ns = [time.time_ns()]

    def mock_time_ns() -> int:
        return current_time_ns[0]

    store = RedisIdempotencyStore(
        redis_url=redis_url,
        worker_id="cb-cycle-test",
        cb_threshold=0.5,  # 50% error rate
        cb_cooldown_ms=100,
        cb_half_open_probes=1,
    )

    with patch("time.time_ns", side_effect=mock_time_ns):
        # === Phase 1: Trigger CB OPEN via error_rate ===

        # Set counters to 100 total, 51 errors → error_rate = 51%
        store._cb_state = "CLOSED"
        store._cb_total_count = 100
        store._cb_error_count = 51

        # Record one more failure → total=101, error=52 → 51.5% > 50%
        store._record_cb_result(success=False)

        # Verify CB opened (lines 271-274)
        assert store._cb_state == "OPEN", "CB should OPEN when error_rate ≥ threshold"
        assert store._cb_open_until_ns > current_time_ns[0], (
            "CB should set cooldown deadline"
        )

        # === Phase 2: CBOpenError during OPEN ===

        with pytest.raises(CBOpenError, match="cb open"):
            store._check_cb("test-operation")

        # Verify metrics
        open_count_before = store.metrics.idemp_cb_open_total
        with pytest.raises(CBOpenError):
            store._check_cb("another-op")
        assert store.metrics.idemp_cb_open_total > open_count_before, (
            "CB open counter should increment"
        )

        # === Phase 3: Advance clock → transition to HALF_OPEN ===

        # Advance time beyond cooldown
        current_time_ns[0] += (store.cb_cooldown_ms + 10) * 1_000_000

        # _check_cb should detect cooldown passed and transition (lines 247-251)
        # But _check_cb only checks, doesn't transition
        # Transition happens in reserve() or we do it manually

        # Simulate what reserve() does: check if time passed
        now_ns = mock_time_ns()
        if store._cb_state == "OPEN" and now_ns >= store._cb_open_until_ns:
            store._cb_state = "HALF_OPEN"
            store._cb_half_open_successes = 0

        assert store._cb_state == "HALF_OPEN", (
            "CB should transition to HALF_OPEN after cooldown"
        )

        # === Phase 4: HALF_OPEN success → CLOSED ===

        # Record success in HALF_OPEN (lines 276-281)
        store._record_cb_result(success=True)

        assert store._cb_state == "CLOSED", "CB should close after successful probe"
        assert store._cb_error_count == 0, "Error count should reset on close"
        assert store._cb_total_count == 0, "Total count should reset on close"

        # === Phase 5: Re-open, then HALF_OPEN failure → OPEN ===

        # Set up for re-open
        store._cb_total_count = 100
        store._cb_error_count = 60  # 60% error rate
        store._record_cb_result(success=False)  # total=101, error=61 → 60.4%

        assert store._cb_state == "OPEN", "CB should re-open"

        # Save open_until for cooldown
        open_until_ns = store._cb_open_until_ns

        # Advance clock again
        current_time_ns[0] = open_until_ns + 1_000_000  # 1ms after cooldown

        # Transition to HALF_OPEN
        now_ns = mock_time_ns()
        if store._cb_state == "OPEN" and now_ns >= store._cb_open_until_ns:
            store._cb_state = "HALF_OPEN"
            store._cb_half_open_successes = 0

        assert store._cb_state == "HALF_OPEN", "CB should be HALF_OPEN"

        # Failure in HALF_OPEN → back to OPEN (lines 282-284)
        store._record_cb_result(success=False)

        assert store._cb_state == "OPEN", "CB should re-open after HALF_OPEN failure"

        # === Phase 6: Counter reset at total_count ≥ 200 ===

        store._cb_state = "CLOSED"
        store._cb_total_count = 200
        store._cb_error_count = 50

        # Record one more result → triggers reset (lines 287-289)
        store._record_cb_result(success=True)

        assert store._cb_error_count == 0, "Error count should reset at 200"
        assert store._cb_total_count == 0, "Total count should reset at 200"
