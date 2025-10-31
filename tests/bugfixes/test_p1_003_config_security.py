"""
Test BUG-P1-003: Verify config_loader correctly handles the new trading_mode.

This test ensures that the system correctly loads API configurations based on the
`trading_mode` and fails safely if the required configuration is missing.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
import yaml
from apps.reference.config_loader import ConfigLoader

class TestConfigSecurityAndModes:
    """Test suite for the new `trading_mode` configuration logic."""

    def test_hybrid_mode_loads_both_live_and_testnet_keys(self):
        """
        Verify that in 'hybrid' mode, the config correctly contains both
        live and testnet API sections.
        """
        with patch.dict(os.environ, {
            'LIVE_BINANCE_API_KEY': 'live_key_from_env',
            'LIVE_BINANCE_API_SECRET': 'live_secret_from_env',
            'LIVE_BINANCE_REST_URL': 'https://fapi.binance.com',
            'TESTNET_BINANCE_API_KEY': 'testnet_key_from_env',
            'TESTNET_BINANCE_API_SECRET': 'testnet_secret_from_env',
            'TESTNET_BINANCE_REST_URL': 'https://testnet.binancefuture.com',
            'TRADING_MODE': 'hybrid_live_data_testnet_exec'
        }, clear=True):
            loader = ConfigLoader()
            config = loader.load_config()
            
            assert config.trading_mode == "hybrid_live_data_testnet_exec"
            assert config.binance_api.live.api_key == "live_key_from_env"
            assert config.binance_api.testnet.api_key == "testnet_key_from_env"

    def test_live_mode_loads_live_keys(self):
        """
        Verify that in 'live' mode, the config correctly loads the live section.
        """
        with patch.dict(os.environ, {
            'LIVE_BINANCE_API_KEY': 'live_key_from_env',
            'LIVE_BINANCE_API_SECRET': 'live_secret_from_env',
            'LIVE_BINANCE_REST_URL': 'https://fapi.binance.com',
            'TRADING_MODE': 'live'
        }, clear=True):
            loader = ConfigLoader()
            config = loader.load_config()

            assert config.trading_mode == "live"
            assert config.binance_api.live.api_key == "live_key_from_env"

    def test_loader_fails_if_required_keys_are_missing(self):
        """
        Verify that the ConfigLoader raises a ValueError if a required key is missing.
        """
        with patch.dict(os.environ, {
            'TRADING_MODE': 'live'
        }, clear=True):
            loader = ConfigLoader()
            
            with pytest.raises(ValueError) as exc_info:
                loader.load_config()
            
            assert "Missing required keys" in str(exc_info.value)