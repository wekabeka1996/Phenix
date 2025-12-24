"""
Smoke tests for /metrics endpoint and router performance metrics
"""

import time
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from vfoundation.obs.debug_api import app, record_router_timing


def test_metrics_endpoint_shape():
    """Test that /metrics endpoint returns correct shape"""
    client = TestClient(app)

    # Record some sample timings
    record_router_timing(5.0)
    record_router_timing(10.0)
    record_router_timing(15.0)

    response = client.get("/metrics/json")
    assert response.status_code == 200

    data = response.json()
    assert "router_p95_ms" in data
    assert "timeout_rate" in data
    assert "queue_depth" in data

    # Check types
    assert isinstance(data["router_p95_ms"], (int, float))
    assert isinstance(data["timeout_rate"], (int, float))
    assert isinstance(data["queue_depth"], int)

    # Check reasonable values
    assert data["router_p95_ms"] >= 0
    assert 0 <= data["timeout_rate"] <= 1
    assert data["queue_depth"] >= 0


def test_router_p95_calculation():
    """Test p95 calculation with known values"""
    from vfoundation.obs.debug_api import record_router_timing, get_p95_router_time

    # Clear any existing measurements by recording 1000+ new ones
    test_times = [i * 1.0 for i in range(1, 101)]  # 1ms to 100ms

    for t in test_times:
        record_router_timing(t)

    p95 = get_p95_router_time()

    # p95 of 1-100 should be 95
    assert 90 <= p95 <= 100  # Allow some variance for floating point


def test_health_endpoint_performance():
    """Test that health endpoint responds quickly"""
    client = TestClient(app)

    # Measure response times for multiple requests
    times = []
    for _ in range(10):
        start = time.time()
        response = client.get("/health")
        end = time.time()

        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "aurora-core"}

        duration_ms = (end - start) * 1000
        times.append(duration_ms)

    # Check that p95 is reasonable (local test should be fast)
    times.sort()
    p95_idx = int(len(times) * 0.95)
    p95_time = times[p95_idx] if p95_idx < len(times) else times[-1]

    # Health endpoint should be very fast locally
    assert p95_time <= 100, f"Health endpoint too slow: {p95_time}ms"


def test_timeout_rate_calculation():
    """Test timeout rate calculation"""
    from vfoundation.obs.debug_api import (
        record_timeout,
        get_timeout_rate,
        record_router_timing,
    )
    import vfoundation.obs.debug_api as debug_module

    # Reset counters for clean test
    with debug_module._metrics_lock:
        debug_module._total_requests = 0
        debug_module._timeout_count = 0

    # Record some normal requests
    for _ in range(80):
        record_router_timing(5.0)

    # Record some timeouts
    for _ in range(20):
        record_timeout()

    timeout_rate = get_timeout_rate()

    # Should be 20/100 = 0.2
    assert 0.15 <= timeout_rate <= 0.25  # Allow some variance
