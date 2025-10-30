"""
CI Smoke E2E Tests (FSMP-P1-T06)

Minimal presence checks for CI gate:
- /health returns 200
- /metrics contains expected keys
- /debug/{rid} RBAC enforcement
- /debug/{rid} drift_report presence when available
"""

from __future__ import annotations
import pytest
import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

# FSMP-REFACTOR-T03-B: Use TRADING_ENV instead of DEBUG_API
# Set to development to enable debug endpoints for smoke tests
# MUST be set BEFORE importing app
os.environ["TRADING_ENV"] = "development"

# Clear any cached app modules to ensure fresh import with correct env
if "apps.reference.api.main" in sys.modules:
    del sys.modules["apps.reference.api.main"]

# Add paths before importing
_test_root = Path(__file__).parent.parent
_vfoundation_root = _test_root / "vfoundation"
_apps_root = _test_root / "apps"
if str(_vfoundation_root) not in sys.path:
    sys.path.insert(0, str(_vfoundation_root))
if str(_apps_root) not in sys.path:
    sys.path.insert(0, str(_apps_root))

from apps.reference.api.main import app
from vfoundation.config import config


@pytest.fixture
def client():
    """Test client for FastAPI app"""
    return TestClient(app)


@pytest.fixture
def valid_admin_token():
    """Return valid admin token from config"""
    return (
        config.rbac_admin_tokens[0] if config.rbac_admin_tokens else "dev-admin-token"
    )


class TestHealthSmoke:
    """Health endpoint smoke test"""

    def test_health_ok(self, client):
        """Health endpoint returns 200"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "healthy", "up"]


class TestMetricsSmoke:
    """Metrics endpoint smoke test"""

    def test_metrics_keys_present(self, client):
        """Metrics endpoint contains expected keys"""
        # FSMP-REFACTOR-T03-B: Metrics endpoint directly available in development
        response = client.get("/metrics")
        assert response.status_code == 200

        data = response.json()

        # Check for drift metrics (from get_drift_metrics)
        assert "confusion_tp_total" in data
        assert "confusion_fp_total" in data
        assert "confusion_fn_total" in data
        assert "confusion_tn_total" in data
        assert "drift_pct_last" in data
        assert "accuracy_last" in data

        # Check for router metrics
        assert "router_p95_ms" in data
        assert "timeout_rate" in data
        assert "queue_depth" in data

        # Check for idempotency metrics (might be present if router is set)
        # These are optional, just check structure is valid
        assert isinstance(data, dict)
        assert len(data) > 5  # At least basic metrics present


class TestDebugRBACSmoke:
    """Debug endpoint RBAC smoke test"""

    def test_debug_rbac_denied_no_token(self, client):
        """Debug endpoint returns 403 without token"""
        # FSMP-REFACTOR-T03-B: Debug endpoints directly available in development
        response = client.get("/debug/RID-test-123")
        assert response.status_code == 403

    def test_debug_rbac_denied_invalid_token(self, client):
        """Debug endpoint returns 403 with invalid token"""
        # FSMP-REFACTOR-T03-B: Debug endpoints directly available in development
        response = client.get(
            "/debug/RID-test-123", headers={"Authorization": "Bearer invalid-token-xyz"}
        )
        assert response.status_code == 403

    def test_debug_rbac_allowed_with_token(self, client, valid_admin_token):
        """Debug endpoint returns 200 with valid token (even if RID not found)"""
        # FSMP-REFACTOR-T03-B: Debug endpoints directly available in development
        response = client.get(
            "/debug/RID-nonexistent",
            headers={"Authorization": f"Bearer {valid_admin_token}"},
        )
        # Should be 200 or 404, but not 403
        assert response.status_code in [200, 404]
        assert response.status_code != 403

    @pytest.mark.skip(reason="Requires fixture data in WAL with drift report")
    def test_debug_rbac_allowed_with_drift_report(self, client, valid_admin_token):
        """
        Debug endpoint returns 200 with drift_report when available.

        This test is skipped by default as it requires:
        1. Actual RID with shadow-mode execution in WAL
        2. Drift computation to be triggered
        3. Report to be stored

        To enable: populate WAL with shadow DEC/EVT and run drift computation.
        """
        response = client.get(
            "/debug/RID-with-drift",
            headers={"Authorization": f"Bearer {valid_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "drift_report" in data
        assert "confusion_matrix" in data["drift_report"]


class TestIdempotencySmoke:
    """Idempotency smoke test (reduced for CI speed)"""

    @pytest.mark.skip(reason="Requires message routing endpoint /api/v1/message")
    def test_idem_parallel_smoke(self, client, valid_admin_token):
        """
        50 parallel CMD:OPEN → 1 DEC, others inflight|dedup.

        Reduced from 100 to 50 for CI speed.
        Skipped: requires full router setup with message endpoint.
        """
        pass


class TestContractsSmoke:
    """Contract validation smoke tests"""

    @pytest.mark.skip(reason="Requires message routing endpoint /api/v1/message")
    def test_why_limit_enforced(self, client, valid_admin_token):
        """
        WHY field must be ≤80 chars, else 400.

        Skipped: requires full router setup with message endpoint.
        """
        pass
