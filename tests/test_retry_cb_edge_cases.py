"""Test edge cases for retry_cb.py circuit breaker."""

import time
from vfoundation.core.retry_cb import CircuitBreaker


def test_cb_cooldown_exact_boundary():
    """Test circuit breaker behavior at exact cooldown boundary"""
    cb = CircuitBreaker(threshold=1, cool_down_s=0.5)

    # Trip the breaker
    cb.on_failure()
    assert cb.state == "OPEN"
    assert not cb.allow()

    # Wait exactly cooldown period
    time.sleep(0.5)

    # Should transition to HALF_OPEN
    assert cb.allow()  # First request allowed
    assert cb.state == "HALF_OPEN"

    # Record success to close the breaker
    cb.on_success()
    assert cb.state == "CLOSED"


def test_cb_multiple_half_open_transitions():
    """Test circuit breaker with multiple half-open transitions"""
    cb = CircuitBreaker(threshold=1, cool_down_s=0.1)

    # Trip the breaker
    cb.on_failure()
    assert cb.state == "OPEN"

    # Wait for cooldown
    time.sleep(0.15)

    # Transition to HALF_OPEN
    assert cb.allow()
    assert cb.state == "HALF_OPEN"

    # Fail again in half-open state
    cb.on_failure()
    assert cb.state == "OPEN"

    # Wait again
    time.sleep(0.15)

    # Another transition to HALF_OPEN
    assert cb.allow()
    assert cb.state == "HALF_OPEN"

    # This time succeed
    cb.on_success()
    assert cb.state == "CLOSED"


def test_cb_reset_explicit():
    """Test explicit circuit breaker reset"""
    cb = CircuitBreaker(threshold=2, cool_down_s=10.0)

    # Trip the breaker
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "OPEN"

    # Reset without waiting for cooldown
    cb.on_success()  # on_success() resets state
    assert cb.state == "CLOSED"
    assert cb.failures == 0
    assert cb.allow()
