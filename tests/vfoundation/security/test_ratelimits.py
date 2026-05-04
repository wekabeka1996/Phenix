"""Tests for vfoundation.security.ratelimits — Phase 1.3."""
from __future__ import annotations

import time
from unittest.mock import patch

from vfoundation.security.ratelimits import RateLimiter


def test_allows_up_to_limit() -> None:
    rl = RateLimiter(per_s=3)
    for _ in range(3):
        assert rl.allow("k") is True


def test_denies_over_limit() -> None:
    rl = RateLimiter(per_s=2)
    assert rl.allow("k") is True
    assert rl.allow("k") is True
    assert rl.allow("k") is False


def test_separate_keys_independent() -> None:
    rl = RateLimiter(per_s=1)
    assert rl.allow("a") is True
    assert rl.allow("b") is True
    assert rl.allow("a") is False
    assert rl.allow("b") is False


def test_window_expires() -> None:
    rl = RateLimiter(per_s=1)
    assert rl.allow("k") is True
    assert rl.allow("k") is False
    # Simulate 1.1 seconds later
    future = time.time() + 1.1
    with patch("vfoundation.security.ratelimits.time") as mock_time:
        mock_time.time.return_value = future
        assert rl.allow("k") is True
