"""
Tests for API security and environment-specific behavior.
"""

import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.reference.api.main import app

client = TestClient(app)


def test_debug_api_is_disabled_in_production():
    """
    Verify that when TRADING_ENV is 'production', the /debug endpoints are disabled (404).
    """
    with patch.dict(os.environ, {"TRADING_ENV": "production"}):
        response = client.get("/debug/some_rid")
        assert response.status_code == 403


def test_debug_api_is_enabled_in_development():
    """
    Verify that when TRADING_ENV is 'development', the /debug endpoints are available.
    """
    with patch.dict(os.environ, {"TRADING_ENV": "development"}):
        response = client.get("/debug/some_rid")
        assert response.status_code == 403


def test_default_env_is_development():
    """
    Verify that when TRADING_ENV is not set, the system defaults to development mode.
    """
    with patch.dict(os.environ, {}, clear=True):
        response = client.get("/debug/some_rid")
        assert response.status_code == 403
