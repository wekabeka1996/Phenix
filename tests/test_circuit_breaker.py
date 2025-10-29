"""
Test suite for circuit breaker and retry policy functionality
"""
import time
from unittest.mock import patch
from vfoundation.core.retry_cb import CircuitBreaker, RetryPolicy


def test_circuit_breaker_states():
    """Test circuit breaker state transitions"""
    cb = CircuitBreaker(threshold=2, cool_down_s=0.1)  # Low threshold for testing
    
    # Initial state should be CLOSED
    assert cb.state == "CLOSED"
    assert cb.allow()
    
    # Trigger failures to open circuit
    cb.on_failure()
    assert cb.state == "CLOSED"  # Still closed after 1 failure
    assert cb.allow()
    
    cb.on_failure()
    assert cb.state == "OPEN"    # Now open after 2 failures
    assert not cb.allow()   # Should block requests
    
    # Wait for cool down
    time.sleep(0.12)  # 120ms > 100ms cool_down_s
    
    # Should transition to half-open
    assert cb.allow()    # First request allowed
    assert cb.state == "HALF_OPEN"
    
    # Success should close circuit
    cb.on_success()
    assert cb.state == "CLOSED"
    assert cb.allow()


def test_circuit_breaker_half_open_failure():
    """Test circuit breaker half-open to open transition"""
    cb = CircuitBreaker(threshold=1, cool_down_s=0.05)
    
    # Force to open state
    cb.on_failure()
    assert cb.state == "OPEN"
    
    # Wait for cool down
    time.sleep(0.06)
    
    # Should allow first request in half-open
    assert cb.allow()
    assert cb.state == "HALF_OPEN"
    
    # Failure in half-open should go back to open
    cb.on_failure()
    assert cb.state == "OPEN"
    assert not cb.allow()


def test_retry_policy_backoff():
    """Test retry policy backoff calculation"""
    policy = RetryPolicy(retries=3, base_ms=10, max_ms=100)
    
    # Test exponential backoff
    assert policy.retries == 3
    
    # Backoff should increase exponentially
    backoff_0 = policy.backoff_ms(0)
    backoff_1 = policy.backoff_ms(1)
    backoff_2 = policy.backoff_ms(2)
    
    # Should be roughly: 10, 20, 40 (plus jitter)
    assert 10 <= backoff_0 <= 30   # base + jitter
    assert 20 <= backoff_1 <= 50   # 2*base + jitter
    assert 40 <= backoff_2 <= 100  # 4*base + jitter, capped at max
    
    # Should respect max_ms
    backoff_large = policy.backoff_ms(10)
    assert backoff_large <= 100  # Should be capped at max_ms


def test_circuit_breaker_concurrent_access():
    """Test circuit breaker thread safety"""
    import threading
    
    cb = CircuitBreaker(threshold=5, cool_down_s=0.1)
    
    results = []
    
    def test_allow():
        for _ in range(10):
            results.append(cb.allow())
            time.sleep(0.001)  # Small delay
    
    # Create multiple threads
    threads = []
    for _ in range(3):
        t = threading.Thread(target=test_allow)
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Should have some results
    assert len(results) == 30  # 3 threads * 10 calls each
    # All should be True initially (CLOSED state)
    assert all(results)


def test_circuit_breaker_reset_after_success():
    """Test that circuit breaker resets failure count after success"""
    cb = CircuitBreaker(threshold=3, cool_down_s=0.1)
    
    # Add some failures (but not enough to open)
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "CLOSED"
    assert cb.failures == 2
    
    # Success should reset failure count
    cb.on_success()
    assert cb.failures == 0
    assert cb.state == "CLOSED"
    
    # Should take full threshold again to open
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "CLOSED"  # Still closed
    
    cb.on_failure()
    assert cb.state == "OPEN"    # Now open


def test_router_circuit_breaker_integration():
    """Test router integration with circuit breaker"""
    from vfoundation.core.routing import Router
    from vfoundation.core.protocol import Message
    
    router = Router()
    
    # Set low threshold for testing
    router.cb = CircuitBreaker(threshold=1, cool_down_s=0.1)
    
    # Handler that always fails
    def failing_handler(msg: Message) -> Message:
        raise Exception("Always fails")
    
    router.register("ASK", "FAIL", failing_handler)
    
    msg = Message(op="ASK", verb="FAIL", src="client", dst="handler")
    
    with patch('vfoundation.core.routing.wal_append'):
        # First call should fail and open circuit
        result1 = router.route(msg)
        assert result1.op == "ERR"
        assert result1.verb == "HANDLER_FAIL"
        
        # Second call should be blocked by circuit breaker
        result2 = router.route(msg)
        assert result2.op == "ERR"
        assert result2.verb == "CB_OPEN"


def test_router_expired_message():
    """Test router handling of expired messages"""
    from vfoundation.core.routing import Router
    from vfoundation.core.protocol import Message
    import time
    
    router = Router()
    
    def dummy_handler(msg: Message) -> Message:
        return Message(op="DEC", verb="OK", src="handler", dst=msg.src, rid=msg.rid)
    
    router.register("ASK", "TEST", dummy_handler)
    
    # Create message that's already expired
    expired_msg = Message(
        op="ASK", 
        verb="TEST", 
        src="client", 
        dst="handler",
        ts=int((time.time() - 10) * 1000),  # 10 seconds ago
        ttl_ms=1000  # 1 second TTL
    )
    
    result = router.route(expired_msg)
    assert result.op == "ERR"
    assert result.verb == "TIMEOUT"
    assert result.why == "expired"


def test_router_no_handler():
    """Test router with no registered handler"""
    from vfoundation.core.routing import Router
    from vfoundation.core.protocol import Message
    
    router = Router()
    
    msg = Message(op="ASK", verb="UNKNOWN", src="client", dst="handler")
    
    result = router.route(msg)
    assert result.op == "ERR"
    assert result.verb == "NO_ROUTE"
    assert result.why == "no route"