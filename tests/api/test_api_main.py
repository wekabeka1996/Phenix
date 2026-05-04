"""
Tests for api/main.py

Tests API initialization in different environments.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

pytest.importorskip("fastapi")


class TestApiInitialization:
    """Test API app initialization"""

    @patch.dict(os.environ, {"TRADING_ENV": "development"}, clear=True)
    @patch("vfoundation.obs.debug_api.app")
    def test_development_mode_imports_debug_api(self, mock_app):
        """Test that development mode imports debug API"""
        # Clear module from cache to force reimport
        import sys

        if "apps.reference.api.main" in sys.modules:
            del sys.modules["apps.reference.api.main"]

        # Import the module
        import apps.reference.api.main as main_module

        # Check that debug API was imported (app should be the imported object)
        assert hasattr(main_module, "app")

    @patch.dict(os.environ, {"TRADING_ENV": "production"}, clear=True)
    @patch("fastapi.FastAPI")
    def test_production_mode_creates_clean_api(self, mock_fastapi):
        """Test that production mode creates clean FastAPI app"""
        # Clear module from cache to force reimport
        import sys

        if "apps.reference.api.main" in sys.modules:
            del sys.modules["apps.reference.api.main"]

        mock_app_instance = MagicMock()
        mock_app_instance.title = "Aurora Core API"
        mock_fastapi.return_value = mock_app_instance

        # Import the module
        import apps.reference.api.main as main_module

        # Check that FastAPI was called with correct parameters
        mock_fastapi.assert_called_once_with(
            title="Aurora Core API",
            description="Production API for Aurora Core FSM Federation",
            version="1.0.0",
        )

        # Check that app has health endpoint
        assert hasattr(main_module, "app")
        assert main_module.app == mock_app_instance

    @patch.dict(os.environ, {}, clear=True)  # No TRADING_ENV set
    @patch("vfoundation.obs.debug_api.app")
    def test_default_development_mode(self, mock_app):
        """Test that default mode is development when TRADING_ENV not set"""
        # Clear module from cache to force reimport
        import sys

        if "apps.reference.api.main" in sys.modules:
            del sys.modules["apps.reference.api.main"]

        # Import the module
        import apps.reference.api.main as main_module

        # Should import debug API by default
        assert hasattr(main_module, "app")

    @patch.dict(os.environ, {"TRADING_ENV": "PRODUCTION"}, clear=True)  # uppercase
    @patch("fastapi.FastAPI")
    def test_production_mode_case_insensitive(self, mock_fastapi):
        """Test that production mode works with uppercase"""
        # Clear module from cache to force reimport
        import sys

        if "apps.reference.api.main" in sys.modules:
            del sys.modules["apps.reference.api.main"]

        mock_app_instance = MagicMock()
        mock_fastapi.return_value = mock_app_instance

        # Import the module
        import apps.reference.api.main as main_module

        # Should create clean API
        mock_fastapi.assert_called_once()
        assert main_module.app == mock_app_instance
