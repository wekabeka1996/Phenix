"""Tests for vfoundation.core.retry_cb — Phase 1.5."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_cb_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure config defaults don't break import."""
    from vfoundation.config import config
    monkeypatch.setattr(config, "cb_threshold", 3)
    monkeypatch.setattr(config, "cb_cooldown_sec", 1.0)


# ─── RetryPolicy ────────────────────────────────────────────────────

class TestRetryPolicy:
    def test_first_attempt_is_base(self) -> None:
        from vfoundation.core.retry_cb import RetryPolicy
        rp = RetryPolicy(retries=3, base_ms=20, max_ms=2000)
        val = rp.backoff_ms(0)
        # 2^0 * 20 + jitter(0..10) = 20..30
        assert 20 <= val <= 30

    def test_exponential_growth(self) -> None:
        from vfoundation.core.retry_cb import RetryPolicy
        rp = RetryPolicy(retries=5, base_ms=100, max_ms=50000)
        # attempt 3: 2^3 * 100 = 800 + jitter(0..10)
        val = rp.backoff_ms(3)
        assert 800 <= val <= 810

    def test_capped_at_max(self) -> None:
        from vfoundation.core.retry_cb import RetryPolicy
        rp = RetryPolicy(retries=5, base_ms=100, max_ms=500)
        val = rp.backoff_ms(10)  # 2^10 * 100 = 102400 → capped to 500
        assert val == 500

    def test_jitter_adds_randomness(self) -> None:
        from vfoundation.core.retry_cb import RetryPolicy
        rp = RetryPolicy(retries=3, base_ms=20, max_ms=2000)
        vals = {rp.backoff_ms(1) for _ in range(20)}
        # With jitter 0..10, we expect more than 1 unique value
        assert len(vals) > 1


# ─── CircuitBreaker ─────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        from vfoundation.core.retry_cb import CircuitBreaker
        cb = CircuitBreaker(threshold=3, cool_down_s=1.0)
        assert cb.state == "CLOSED"
        assert cb.allow() is True

    def test_opens_after_threshold_failures(self) -> None:
        from vfoundation.core.retry_cb import CircuitBreaker
        cb = CircuitBreaker(threshold=3, cool_down_s=10.0)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == "CLOSED"
        cb.on_failure()
        assert cb.state == "OPEN"
        assert cb.allow() is False

    def test_transitions_to_half_open_after_cooldown(self) -> None:
        from vfoundation.core.retry_cb import CircuitBreaker
        cb = CircuitBreaker(threshold=2, cool_down_s=0.5)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == "OPEN"

        future = time.time() + 0.6
        with patch("vfoundation.core.retry_cb.time") as mock_time:
            mock_time.time.return_value = future
            assert cb.allow() is True
        assert cb.state == "HALF_OPEN"

    def test_success_resets_to_closed(self) -> None:
        from vfoundation.core.retry_cb import CircuitBreaker
        cb = CircuitBreaker(threshold=2, cool_down_s=0.5)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == "OPEN"
        cb.on_success()
        assert cb.state == "CLOSED"
        assert cb.failures == 0
        assert cb.allow() is True

    def test_half_open_allows_probe(self) -> None:
        from vfoundation.core.retry_cb import CircuitBreaker
        cb = CircuitBreaker(threshold=1, cool_down_s=0.0)
        cb.on_failure()
        assert cb.state == "OPEN"
        # cool_down_s=0 → immediately transitions to HALF_OPEN
        assert cb.allow() is True
        assert cb.state == "HALF_OPEN"
