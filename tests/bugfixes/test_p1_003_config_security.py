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

# Mock YAML content for different scenarios
MOCK_YAML_FULL = """
trading_mode: "hybrid_live_data_testnet_exec"
binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
"""

MOCK_YAML_TRADING = "some_trading_key: value"

MOCK_YAML_LIVE_ONLY = """
trading_mode: "live"
binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
"""

MOCK_YAML_MISSING_KEYS = """
trading_mode: "hybrid_live_data_testnet_exec"
binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
"""

def yaml_mocker(system_content, trading_content):
    """Helper to mock the return values of _load_yaml."""
    def side_effect(filename):
        if filename == "system.yaml":
            return yaml.safe_load(system_content)
        if filename == "trading.yaml":
            return yaml.safe_load(trading_content)
        return {}
    return MagicMock(side_effect=side_effect)

class TestConfigSecurityAndModes:
    """Test suite for the new `trading_mode` configuration logic."""

    @patch('apps.reference.config_loader.ConfigLoader._load_yaml')
    def test_hybrid_mode_loads_both_live_and_testnet_keys(self, mock_load_yaml):
        """
        Verify that in 'hybrid' mode, the config correctly contains both
        live and testnet API sections.
        """
        mock_load_yaml.side_effect = yaml_mocker(MOCK_YAML_FULL, MOCK_YAML_TRADING).side_effect
        with patch.dict(os.environ, {
            'BINANCE_LIVE_API_KEY': 'live_key_from_env',
            'BINANCE_LIVE_API_SECRET': 'live_secret_from_env',
            'BINANCE_TESTNET_API_KEY': 'testnet_key_from_env',
            'BINANCE_TESTNET_API_SECRET': 'testnet_secret_from_env'
        }, clear=True):
            loader = ConfigLoader()
            config = loader.load_config()
            
            assert config.trading_mode == "hybrid_live_data_testnet_exec"
            assert config.binance_api.live.api_key == "live_key_from_env"
            assert config.binance_api.testnet.api_key == "testnet_key_from_env"

    @patch('apps.reference.config_loader.ConfigLoader._load_yaml')
    def test_live_mode_loads_live_keys(self, mock_load_yaml):
        """
        Verify that in 'live' mode, the config correctly loads the live section.
        """
        mock_load_yaml.side_effect = yaml_mocker(MOCK_YAML_LIVE_ONLY, MOCK_YAML_TRADING).side_effect
        with patch.dict(os.environ, {
            'BINANCE_LIVE_API_KEY': 'live_key_from_env',
            'BINANCE_LIVE_API_SECRET': 'live_secret_from_env'
        }, clear=True):
            loader = ConfigLoader()
            config = loader.load_config()

            assert config.trading_mode == "live"
            assert config.binance_api.live.api_key == "live_key_from_env"
            assert "testnet" not in config.binance_api.to_dict()

    @patch('apps.reference.config_loader.ConfigLoader._load_yaml')
    def test_env_vars_override_yaml_keys(self, mock_load_yaml):
        """
        Verify that environment variables correctly override keys defined in the YAML.
        """
        mock_load_yaml.side_effect = yaml_mocker(MOCK_YAML_FULL, MOCK_YAML_TRADING).side_effect
        with patch.dict(os.environ, {
            'BINANCE_LIVE_API_KEY': 'live_key_from_env',
            'BINANCE_LIVE_API_SECRET': 'live_secret_from_yaml_default',
            'BINANCE_TESTNET_API_KEY': 'testnet_key_from_yaml_default',
            'BINANCE_TESTNET_API_SECRET': 'testnet_secret_from_env'
        }, clear=True):
            loader = ConfigLoader()
            config = loader.load_config()

            assert config.binance_api.live.api_key == "live_key_from_env"
            assert config.binance_api.live.api_secret == "live_secret_from_yaml_default"
            assert config.binance_api.testnet.api_secret == "testnet_secret_from_env"

    @patch('apps.reference.config_loader.ConfigLoader._load_yaml')
    def test_loader_fails_if_required_keys_are_missing(self, mock_load_yaml):
        """
        Verify that the ConfigLoader raises a ValueError if a required key is missing.
        """
        mock_load_yaml.side_effect = yaml_mocker(MOCK_YAML_MISSING_KEYS, MOCK_YAML_TRADING).side_effect
        with patch.dict(os.environ, {}, clear=True):
            loader = ConfigLoader()
            
            with pytest.raises(ValueError) as exc_info:
                loader.load_config()
            
            assert "Missing required keys" in str(exc_info.value)

