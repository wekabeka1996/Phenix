"""Additional tests for idempotency edge cases"""

import time
from vfoundation.core.cache.ttl_cache import now_ns, ns_from_ms
from vfoundation.core.idempotency import InflightState
from vfoundation.core.idempotency import IdempotencyStore


def test_get_if_done_from_cache():
    """Test get_if_done retrieves from cache"""
    store = IdempotencyStore(default_ttl_ms=1000)

    # Use public API to add to cache via complete()
    key = "test-key"
    result = {"data": "cached"}

    # Simulate begin + complete
    store.begin(key)
    store.complete(key, result)

    # Should retrieve from cache
    retrieved = store.get_if_done(key)
    assert retrieved == result


def test_get_if_done_expired_cache():
    """Test get_if_done returns None for expired cache"""
    store = IdempotencyStore(default_ttl_ms=20)  # Very short TTL

    # Add entry and wait for expiration
    key = "expired-key"
    result = {"data": "old"}

    store.begin(key)
    store.complete(key, result)

    # Wait for definite expiration
    time.sleep(0.05)  # 50ms > 20ms TTL

    # Trigger cleanup to force expiration
    store.cleanup_expired()

    # Should return None (expired)
    retrieved = store.get_if_done(key)
    assert retrieved is None


def test_get_if_done_from_inflight_done():
    """Test get_if_done retrieves from inflight DONE state"""
    store = IdempotencyStore(default_ttl_ms=1000)

    # Manually add to inflight as DONE using monotonic time
    key = "inflight-done"
    result = {"data": "completed"}
    expire_ns = now_ns() + ns_from_ms(1000)

    store._inflight[key] = (InflightState.DONE, result, expire_ns)

    # Should retrieve from inflight
    retrieved = store.get_if_done(key)
    assert retrieved == result


def test_get_if_done_from_inflight_pending():
    """Test get_if_done returns None for inflight PENDING state"""
    store = IdempotencyStore(default_ttl_ms=1000)

    # Manually add to inflight as PENDING using monotonic time
    key = "inflight-pending"
    expire_ns = now_ns() + ns_from_ms(1000)

    store._inflight[key] = (InflightState.PENDING, None, expire_ns)

    # Should return None (still processing)
    retrieved = store.get_if_done(key)
    assert retrieved is None


def test_key_get_expired():
    """Test key_get removes expired entries"""
    store = IdempotencyStore(default_ttl_ms=50)

    # Add entry and wait for expiration
    key = "expired"
    result = {"old": "data"}

    store.begin(key)
    store.complete(key, result)

    # Wait for expiration
    time.sleep(0.1)  # 100ms > 50ms TTL

    # Should return None (expired and removed)
    retrieved = store.key_get(key)
    assert retrieved is None


def test_key_seen_expired():
    """Test key_seen returns False and cleans up expired entries"""
    store = IdempotencyStore(default_ttl_ms=50)

    # Add entry and wait for expiration
    key = "expired"

    store.begin(key)
    store.complete(key, {"data": "old"})

    # Wait for expiration
    time.sleep(0.1)

    # Should return False (expired)
    seen = store.key_seen(key)
    assert seen is False


def test_cleanup_expired_cache():
    """Test cleanup_expired removes expired cache entries"""
    store = IdempotencyStore(default_ttl_ms=100)

    # Add multiple entries
    store.begin("valid1")
    store.complete("valid1", {"data": 1})

    store.begin("expired1")
    store.complete("expired1", {"data": 2})

    # Wait for one to expire
    time.sleep(0.15)  # 150ms > 100ms TTL

    store.begin("valid2")
    store.complete("valid2", {"data": 3})

    # Trigger cleanup
    store.cleanup_expired()

    # valid2 should exist (fresh), expired1 should be gone
    assert store.key_seen("valid2") is True
    assert store.key_seen("expired1") is False


def test_cleanup_expired_inflight():
    """Test cleanup_expired removes expired inflight entries"""
    store = IdempotencyStore(default_ttl_ms=100, idem_pending_ttl_ms=100)

    # Add entries with different states
    expire_ns_future = now_ns() + ns_from_ms(10000)  # Far future
    expire_ns_past = now_ns() - ns_from_ms(100)  # Already expired

    store._inflight["valid1"] = (InflightState.PENDING, None, expire_ns_future)
    store._inflight["expired1"] = (InflightState.DONE, {"data": 1}, expire_ns_past)
    store._inflight["valid2"] = (InflightState.DONE, {"data": 2}, expire_ns_future)
    store._inflight["expired2"] = (InflightState.PENDING, None, expire_ns_past)

    store.cleanup_expired()

    # Only valid entries should remain
    assert "valid1" in store._inflight
    assert "valid2" in store._inflight
    assert "expired1" not in store._inflight
    assert "expired2" not in store._inflight


def test_begin_with_expired_inflight():
    """Test begin() cleans up expired inflight entries"""
    store = IdempotencyStore(default_ttl_ms=100, idem_pending_ttl_ms=100)

    key = "test-key"
    expired_ns = now_ns() - ns_from_ms(100)

    # Add expired PENDING entry
    store._inflight[key] = (InflightState.PENDING, None, expired_ns)

    # begin() should remove expired and acquire
    status = store.begin(key)

    assert status.get("acquired") is True
    assert key in store._inflight
    # Old expired entry should be replaced with new PENDING
    state, _, expire = store._inflight[key]
    assert state == InflightState.PENDING
    assert expire > now_ns()  # New expiry in future
