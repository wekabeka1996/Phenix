import sys
import os
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def test_production_health_endpoint_returns_healthy():
    # Use patch.dict style to ensure no other env vars leak
    from unittest.mock import patch

    with patch.dict(os.environ, {"TRADING_ENV": "production"}, clear=True):
        # Remove module from cache to force re-import under new env
        if "apps.reference.api.main" in sys.modules:
            del sys.modules["apps.reference.api.main"]

        import apps.reference.api.main as main_module

        client = TestClient(main_module.app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy", "service": "aurora-core"}
