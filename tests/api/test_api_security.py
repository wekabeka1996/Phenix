"""
Tests for API security and environment-specific behavior.
"""

import os
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient

def create_app_with_env(trading_env=None):
    """Create app with specific TRADING_ENV"""
    env_patch = {"TRADING_ENV": trading_env} if trading_env else {}
    with patch.dict(os.environ, env_patch, clear=bool(not trading_env)):
        # Remove module from cache to force reimport
        modules_to_remove = [k for k in sys.modules.keys() if k.startswith('apps.reference.api')]
        for mod in modules_to_remove:
            del sys.modules[mod]

        from apps.reference.api.main import app
        return TestClient(app)


def test_debug_api_is_disabled_in_production():
    """
    Verify that when TRADING_ENV is 'production', the /debug endpoints are disabled (404).
    """
    client = create_app_with_env("production")
    response = client.get("/debug/some_rid")
    assert response.status_code == 404


def test_debug_api_is_enabled_in_development():
    """
    Verify that when TRADING_ENV is 'development', the /debug endpoints are available (200).
    """
    client = create_app_with_env("development")
    response = client.get("/debug/some_rid")
    assert response.status_code == 200


def test_default_env_is_development():
    """
    Verify that when TRADING_ENV is not set, the system defaults to development mode (200).
    """
    client = create_app_with_env(None)
    response = client.get("/debug/some_rid")
    assert response.status_code == 200
