import pytest
import os
import logging
from unittest.mock import MagicMock, patch
from typing import Literal

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.bootstrap.preflight import check_hybrid_coherence
from vfoundation.core import FSMCore

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture
def mock_fsm():
    """Fixture for a mock FSM core."""
    return MagicMock(spec=FSMCore)

@pytest.fixture
def mock_binance_client():
    """Fixture for a mock Binance Client."""
    with patch('apps.reference.domains.account_observer.account_observer.Client') as MockClient:
        yield MockClient

@pytest.fixture
def config_loader_with_mock_env(tmp_path):
    """Fixture for ConfigLoader with a temporary .env file."""
    def _loader(env_vars: dict, trading_yaml_content: str):
        env_path = tmp_path / ".env"
        with open(env_path, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        # Create config/aurora directory
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create system.yaml (minimal)
        system_yaml_path = config_dir / "system.yaml"
        with open(system_yaml_path, "w") as f:
            f.write("trading_mode: \"hybrid_live_data_testnet_exec\"\n") # Default for hybrid

        # Create trading.yaml
        trading_yaml_path = config_dir / "trading.yaml"
        with open(trading_yaml_path, "w") as f:
            f.write(trading_yaml_content)

        # Patch os.getenv to use our mock env vars
        with patch.dict(os.environ, env_vars, clear=True):
            loader = ConfigLoader(config_dir=config_dir)
            return loader.load_config()
    return _loader

# Scenario a) no new keys → follow-execution (execution=testnet) → risk_portfolio_source == "testnet"
def test_risk_portfolio_source_default_follow_execution(config_loader_with_mock_env, mock_fsm, mock_binance_client):
    env_vars = {
        "BINANCE_TESTNET_API_KEY": "test_key",
        "BINANCE_TESTNET_API_SECRET": "test_secret",
        "BINANCE_FUTURES_BASE_URL_LIVE": "https://api.binance.com",
        "BINANCE_FUTURES_API_KEY_LIVE": "live_key",
        "BINANCE_FUTURES_API_SECRET_LIVE": "live_secret",
    }
    trading_yaml_content = """
trading:
  domain_configuration:
    execution_position:
      trading_mode: "testnet"
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    api_secret: "${BINANCE_FUTURES_API_SECRET_LIVE}"
    rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
    ws_url: "wss://fstream.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
"""
    config = config_loader_with_mock_env(env_vars, trading_yaml_content)

    assert config.get("_resolved", {}).get("risk_portfolio_source") == "testnet"
    
    # Verify AccountObserver is initialized with testnet
    observer = AccountObserver(mock_fsm, config.to_dict())
    assert observer.testnet is True
    mock_binance_client.assert_called_once_with("test_key", "test_secret", testnet=True)

# Scenario b) explicit "live" при execution=testnet → WARN + принудительный "testnet" (fail-closed)
def test_risk_portfolio_source_explicit_live_fail_closed(config_loader_with_mock_env, mock_fsm, mock_binance_client, caplog):
    env_vars = {
        "BINANCE_TESTNET_API_KEY": "test_key",
        "BINANCE_TESTNET_API_SECRET": "test_secret",
        "BINANCE_FUTURES_BASE_URL_LIVE": "https://api.binance.com",
        "BINANCE_FUTURES_API_KEY_LIVE": "live_key",
        "BINANCE_FUTURES_API_SECRET_LIVE": "live_secret",
    }
    trading_yaml_content = """
trading:
  domain_configuration:
    execution_position:
      trading_mode: "testnet"
  risk_management:
    data_sources:
      portfolio_state: "live"
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    api_secret: "${BINANCE_FUTURES_API_SECRET_LIVE}"
    rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
    ws_url: "wss://fstream.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
"""
    with caplog.at_level(logging.WARNING):
        config = config_loader_with_mock_env(env_vars, trading_yaml_content)
    
    assert config.get("_resolved", {}).get("risk_portfolio_source") == "testnet"
    assert "Risk portfolio source 'live' overridden to 'testnet' under hybrid/testnet execution mode (fail-closed)." in caplog.text

    # Verify AccountObserver is initialized with testnet
    observer = AccountObserver(mock_fsm, config.to_dict())
    assert observer.testnet is True
    mock_binance_client.assert_called_once_with("test_key", "test_secret", testnet=True)

# Scenario c) preflight incoherence → decision DEFER с why="hybrid_incoherent"
def test_preflight_incoherence_defer(config_loader_with_mock_env, caplog):
    env_vars = {
        "BINANCE_TESTNET_API_KEY": "test_key",
        "BINANCE_TESTNET_API_SECRET": "test_secret",
        "BINANCE_FUTURES_BASE_URL_LIVE": "https://api.binance.com",
        "BINANCE_FUTURES_API_KEY_LIVE": "live_key",
        "BINANCE_FUTURES_API_SECRET_LIVE": "live_secret",
    }
    # Incoherent config: market_data is testnet, but should be live
    trading_yaml_content = """
trading:
  domain_configuration:
    market_data:
      trading_mode: "testnet" # This should be "live" for coherence
    execution_position:
      trading_mode: "testnet"
  risk_management:
    data_sources:
      portfolio_state: "testnet"
binance_api:
  live:
    api_key: "${BINANCE_FUTURES_API_KEY_LIVE}"
    api_secret: "${BINANCE_FUTURES_API_SECRET_LIVE}"
    rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
    ws_url: "wss://fstream.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"
    ws_url: "wss://stream.testnet.binancefuture.com"
"""
    with caplog.at_level(logging.WARNING):
        config = config_loader_with_mock_env(env_vars, trading_yaml_content)
        is_coherent, reasons = check_hybrid_coherence(config.to_dict())
    
    assert is_coherent is False
    assert "Market data trading_mode is 'testnet', expected 'live'." in reasons
    assert "HYBRID_INCOHERENT: Hybrid mode pre-flight check failed." in caplog.text

    # Verify that the main application would log a critical error
    # This part would typically be in main.py, but we're testing the preflight function directly
    # The main.py integration already logs CRITICAL if not coherent.