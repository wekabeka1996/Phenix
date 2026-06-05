"""
Smoke tests for production API mode (TRADING_ENV=production).

Ensures prod wiring works without debug endpoints.
"""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def prod_app():
    """Import app with TRADING_ENV=production set."""
    # Set env BEFORE import
    os.environ["TRADING_ENV"] = "production"

    # Force reimport if already cached
    import sys
    if "apps.reference.api.main" in sys.modules:
        del sys.modules["apps.reference.api.main"]

    from apps.reference.api.main import app
    return app


@pytest.fixture
def client(prod_app):
    return TestClient(prod_app)


def test_prod_import_success(prod_app):
    """Prod app imports without errors."""
    assert prod_app is not None
    assert prod_app.title == "Aurora Core API"


def test_health_endpoint(client):
    """Health endpoint returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "aurora-core"


def test_metrics_endpoint(client):
    """Metrics endpoint returns 200 with Prometheus format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    # Check for typical Prometheus prefixes
    assert "# HELP" in content or "# TYPE" in content or "HELP" in content


def test_prod_routes_exist(prod_app):
    """Prod app has required routes."""
    routes = [r.path for r in prod_app.routes]
    assert "/health" in routes
    assert "/metrics" in routes
    assert "/statdump" in routes
    # WebSocket route check (path exists)
    ws_routes = [r.path for r in prod_app.routes if hasattr(r, "path") and "/ws" in r.path]
    assert len(ws_routes) > 0


def test_no_debug_routes_in_prod(prod_app):
    """Prod app does not have debug routes."""
    routes = [r.path for r in prod_app.routes]
    assert "/debug/" not in " ".join(routes)
    assert "/metrics/json" not in routes