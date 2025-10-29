"""
Tests for idempotency with TTL cache functionality
"""
import time
from unittest.mock import patch
from vfoundation.core.idempotency import IdempotencyStore
from vfoundation.core.routing import Router
from vfoundation.core.protocol import Message


def test_idempotency_ttl_basic():
    """Test basic TTL-based idempotency functionality"""
    store = IdempotencyStore(default_ttl_ms=1000)  # 1 second TTL
    
    # Test key not seen initially
    assert not store.key_seen("test-key")
    assert store.key_get("test-key") is None
    
    # Remember a result
    test_result = {"status": "success", "data": "test"}
    store.key_remember("test-key", test_result)
    
    # Should now be seen
    assert store.key_seen("test-key")
    retrieved = store.key_get("test-key")
    assert retrieved == test_result


def test_idempotency_ttl_expiration():
    """Test that keys expire after TTL"""
    store = IdempotencyStore(default_ttl_ms=100)  # 100ms TTL
    
    # Remember a result
    test_result = {"status": "success"}
    store.key_remember("test-key", test_result)
    
    # Should be available immediately
    assert store.key_seen("test-key")
    
    # Wait for expiration
    time.sleep(0.15)  # 150ms > 100ms TTL
    
    # Should now be expired
    assert not store.key_seen("test-key")
    assert store.key_get("test-key") is None


def test_idempotency_custom_ttl():
    """Test custom TTL values"""
    store = IdempotencyStore(default_ttl_ms=1000)
    
    # Use custom short TTL
    test_result = {"status": "success"}
    store.key_remember("test-key", test_result, ttl_ms=50)
    
    # Should be available immediately
    assert store.key_seen("test-key")
    
    # Wait for custom TTL to expire
    time.sleep(0.1)  # 100ms > 50ms custom TTL
    
    # Should be expired
    assert not store.key_seen("test-key")


def test_router_idempotency_integration():
    """Test router integration with idempotent_key"""
    router = Router()
    
    # Mock handler that returns success
    def mock_handler(msg: Message) -> Message:
        return Message(
            op="DEC",
            verb="SUCCESS", 
            src="handler",
            dst=msg.src,
            rid=msg.rid,
            why="processed"
        )
    
    router.register("ASK", "PROCESS", mock_handler)
    
    # Create message with idempotent_key
    msg1 = Message(
        op="ASK",
        verb="PROCESS",
        src="client",
        dst="handler",
        idempotent_key="unique-operation-123",
        why="test request"
    )
    
    # Mock WAL append to avoid file system
    with patch('vfoundation.core.routing.wal_append'):
        # First request should process normally
        result1 = router.route(msg1)
        assert result1.op == "DEC"
        assert result1.verb == "SUCCESS"
        assert result1.why == "processed"
    
    # Second request with same idempotent_key should return cached result
    msg2 = Message(
        op="ASK",
        verb="PROCESS",
        src="client",
        dst="handler", 
        idempotent_key="unique-operation-123",  # Same key
        why="duplicate request"
    )
    
    with patch('vfoundation.core.routing.wal_append'):
        result2 = router.route(msg2)
        # Should get cached result with dedup marker
        assert result2.op == "DEC"
        assert result2.verb == "SUCCESS"
        # Should have dedup marker in payload
        assert result2.pld.get("dedup")


def test_router_idempotency_no_wal_on_dedup():
    """Test that duplicate requests don't write to WAL"""
    router = Router()
    
    def mock_handler(msg: Message) -> Message:
        return Message(op="DEC", verb="OK", src="handler", dst=msg.src, rid=msg.rid)
    
    router.register("ASK", "TEST", mock_handler)
    
    msg = Message(
        op="ASK",
        verb="TEST",
        src="client", 
        dst="handler",
        idempotent_key="no-wal-test"
    )
    
    # Mock WAL append to count calls
    with patch('vfoundation.core.routing.wal_append') as mock_wal:
        # First request - should write to WAL
        router.route(msg)
        assert mock_wal.call_count == 1
        
        # Second request - should NOT write to WAL
        router.route(msg) 
        assert mock_wal.call_count == 1  # Still only 1 call


def test_idempotency_cleanup():
    """Test cleanup of expired entries"""
    store = IdempotencyStore(default_ttl_ms=50)
    
    # Add several entries
    for i in range(5):
        store.key_remember(f"key-{i}", f"value-{i}")
    
    # Verify all are present
    for i in range(5):
        assert store.key_seen(f"key-{i}")
    
    # Wait for expiration
    time.sleep(0.1)
    
    # Manual cleanup
    store.cleanup_expired()
    
    # All should be gone
    for i in range(5):
        assert not store.key_seen(f"key-{i}")


def test_legacy_rid_idempotency_still_works():
    """Test that legacy RID-based idempotency still functions"""
    store = IdempotencyStore()
    
    # Test legacy methods
    assert not store.seen("rid-123")
    
    result = {"legacy": "result"}
    store.remember("rid-123", result)
    
    assert store.seen("rid-123")
    assert store.get("rid-123") == result


def test_inflight_cleanup():
    """Test cleanup of expired inflight entries"""
    store = IdempotencyStore(default_ttl_ms=1000, idem_pending_ttl_ms=50)
    
    # Start a request
    result = store.begin("test-key")
    assert result == {"acquired": True}
    
    # Should be in inflight
    assert len(store._inflight) == 1
    
    # Wait for pending TTL to expire
    time.sleep(0.1)
    
    # Cleanup should remove expired inflight
    store.cleanup_expired()
    
    # Should be empty now
    assert len(store._inflight) == 0
    
    # Metrics should show evicted
    metrics = store.get_metrics()
    assert metrics["idem_inflight_evicted_total"] >= 1


def test_pending_ttl_longer_than_result_ttl():
    """Test that pending TTL is longer than result TTL"""
    store = IdempotencyStore(default_ttl_ms=100, max_entries=2, idem_pending_ttl_ms=200)
    
    # Start request
    result = store.begin("test-key")
    assert result == {"acquired": True}
    
    # Check that PENDING is pinned in cache
    assert store._cache.get("test-key") == "__PENDING__"
    
    # Complete with result
    store.complete("test-key", "result")
    
    # Result should be cached and pinned
    assert store.get_if_done("test-key") == "result"
    
    # Wait for result TTL to expire but not pending TTL
    time.sleep(0.15)  # 150ms > 100ms result TTL, < 200ms pending TTL
    
    # Result should still be available (from cache, pinned)
    assert store.get_if_done("test-key") == "result"


def test_admission_control_over_cap():
    """Test admission control when inflight cap is exceeded"""
    store = IdempotencyStore(idem_inflight_cap=2)
    
    # Fill up to cap
    result1 = store.begin("key1")
    assert result1 == {"acquired": True}
    
    result2 = store.begin("key2")
    assert result2 == {"acquired": True}
    
    # Next request should be rejected
    result3 = store.begin("key3")
    assert result3 == {"over_cap": True}
    
    # Check metrics
    metrics = store.get_metrics()
    assert metrics["idem_inflight_over_cap_total"] == 1
    assert metrics["idem_inflight_cardinality"] == 2


def test_pending_pinning_under_lru_pressure():
    """Test that PENDING entries are pinned and not evicted by LRU"""
    store = IdempotencyStore(max_entries=4, default_ttl_ms=1000)
    
    # Start PENDING request (should be pinned)
    result = store.begin("pending-key")
    assert result == {"acquired": True}
    
    # Fill cache to capacity with other entries
    store.key_remember("key1", "value1")
    store.key_remember("key2", "value2")
    store.key_remember("key3", "value3")
    
    # Cache should have 4 entries (3 regular + 1 pinned PENDING)
    assert store._cache.size() == 4
    
    # Add one more to trigger LRU eviction
    store.key_remember("key4", "value4")
    
    # PENDING should still be there (pinned), but one regular evicted
    assert store._cache.get("pending-key") == "__PENDING__"
    assert store._cache.size() == 4  # 3 regular + 1 pinned
    
    # Complete the PENDING
    store.complete("pending-key", "completed")
    
    # Now result should be cached and pinned
    assert store.get_if_done("pending-key") == "completed"