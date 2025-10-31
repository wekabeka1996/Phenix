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
            'BINANCE_FUTURES_API_KEY_LIVE': 'live_key_from_env',
            'BINANCE_FUTURES_API_SECRET_LIVE': 'live_secret_from_env',
            'BINANCE_FUTURES_REST_URL_LIVE': 'https://fapi.binance.com',
            'BINANCE_TESTNET_API_KEY': 'testnet_key_from_env',
            'BINANCE_TESTNET_API_SECRET': 'testnet_secret_from_env',
            'BINANCE_TESTNET_REST_URL': 'https://testnet.binancefuture.com',
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
            'BINANCE_FUTURES_API_KEY_LIVE': 'live_key_from_env',
            'BINANCE_FUTURES_API_SECRET_LIVE': 'live_secret_from_env',
            'BINANCE_FUTURES_REST_URL_LIVE': 'https://fapi.binance.com',
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
        }, clear=True), \
             patch('dotenv.load_dotenv') as mock_load_dotenv, \
             patch('os.getenv') as mock_getenv:
            mock_load_dotenv.return_value = None  # Prevent loading .env file
            # Mock os.getenv to return None for API keys
            def getenv_side_effect(key, default=None):
                if key in ['BINANCE_FUTURES_API_KEY_LIVE', 'BINANCE_FUTURES_API_SECRET_LIVE', 
                          'BINANCE_FUTURES_REST_URL_LIVE', 'BINANCE_TESTNET_API_KEY', 
                          'BINANCE_TESTNET_API_SECRET', 'BINANCE_TESTNET_REST_URL']:
                    return None
                elif key == 'TRADING_MODE':
                    return 'live'
                else:
                    return default
            mock_getenv.side_effect = getenv_side_effect
            
            loader = ConfigLoader()
            
            with pytest.raises(ValueError) as exc_info:
                loader.load_config()
            
            assert "Missing required keys" in str(exc_info.value)