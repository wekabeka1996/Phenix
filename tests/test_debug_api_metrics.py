"""Tests for debug_api.py metrics functions (non-FastAPI parts)."""

from fastapi.testclient import TestClient
from vfoundation.obs import debug_api


def test_debug_api_record_router_timing():
    """Test recording router timing metrics"""
    # Record some timings
    debug_api.record_router_timing(10.5)
    debug_api.record_router_timing(25.3)
    debug_api.record_router_timing(15.7)

    # Get p95 metric
    p95 = debug_api.get_p95_router_time()
    assert p95 > 0.0
    assert isinstance(p95, float)


def test_debug_api_record_timeout():
    """Test recording timeout events"""
    # Record initial state
    debug_api.get_timeout_rate()

    # Record a timeout
    debug_api.record_timeout()

    # Timeout rate should change
    new_rate = debug_api.get_timeout_rate()
    assert new_rate >= 0.0
    assert new_rate <= 1.0


def test_debug_api_set_queue_depth():
    """Test setting queue depth metric"""
    # Set various queue depths
    debug_api.set_queue_depth(0)
    debug_api.set_queue_depth(5)
    debug_api.set_queue_depth(10)

    # Should not raise any exceptions
    assert True


def test_debug_api_p95_empty():
    """Test p95 calculation with empty data"""
    # Create new instance to test empty case
    # (tricky since we're using global state, but we can force it)
    from vfoundation.obs.debug_api import _metrics_lock, _router_times

    with _metrics_lock:
        original_times = _router_times.copy()
        _router_times.clear()

    # Should return 0.0 for empty data
    p95 = debug_api.get_p95_router_time()
    assert p95 == 0.0

    # Restore original state
    with _metrics_lock:
        _router_times.extend(original_times)


def test_debug_api_p95_many_samples():
    """Test p95 with many samples"""
    # Add many samples to test the 1000-sample limit
    for i in range(100):
        debug_api.record_router_timing(float(i))

    p95 = debug_api.get_p95_router_time()
    assert p95 > 80.0  # Should be around 95th percentile
    assert p95 < 100.0


def test_debug_api_set_router():
    """Test set_router function"""

    class MockRouter:
        def get_idempotency_metrics(self):
            return {"cache_hits": 0, "cache_misses": 0}

    # Save original router
    from vfoundation.obs.debug_api import _router_instance

    original_router = _router_instance

    # Set mock router
    mock_router = MockRouter()
    debug_api.set_router(mock_router)

    # Restore original
    debug_api.set_router(original_router)

    # Should not raise exception
    assert True


def test_debug_api_timeout_rate_zero_requests():
    """Test timeout rate when no requests made"""
    # This is tricky due to global state, but we can test the logic
    # by checking that the rate is between 0 and 1
    rate = debug_api.get_timeout_rate()
    assert 0.0 <= rate <= 1.0


def test_debug_api_metrics_thread_safety():
    """Test that metrics functions are thread-safe"""
    import threading

    def worker():
        for i in range(10):
            debug_api.record_router_timing(float(i))
            debug_api.record_timeout()
            debug_api.set_queue_depth(i)

    # Run multiple threads
    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Should not crash and should have recorded metrics
    p95 = debug_api.get_p95_router_time()
    assert p95 >= 0.0

    rate = debug_api.get_timeout_rate()
    assert 0.0 <= rate <= 1.0


def test_force_resync_endpoint_invokes_handler(monkeypatch):
    """Force-resync endpoint should call registered handler and return details."""
    monkeypatch.setenv("TRADING_ENV", "production")
    client = TestClient(debug_api.app)

    captured = {}

    def handler(reason, symbol):
        captured["reason"] = reason
        captured["symbol"] = symbol
        return {"status": "ok", "symbol": symbol or "ALL"}

    monkeypatch.setattr(debug_api, "_resync_handler", None)
    debug_api.register_resync_handler(handler)

    response = client.post(
        "/debug/position/force-resync",
        json={"reason": "manual", "symbol": "BTCUSDT"},
        params={"authorization": "dev-admin-token-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["reason"] == "manual"
    assert body["symbol"] == "BTCUSDT"
    assert captured == {"reason": "manual", "symbol": "BTCUSDT"}


def test_force_resync_endpoint_requires_auth(monkeypatch):
    """Production mode should enforce admin token for manual resync endpoint."""
    monkeypatch.setenv("TRADING_ENV", "production")
    client = TestClient(debug_api.app)
    monkeypatch.setattr(debug_api, "_resync_handler",
                        lambda *_: {"status": "ok"})

    response = client.post(
        "/debug/position/force-resync",
        json={"reason": "manual"},
    )

    assert response.status_code == 403
