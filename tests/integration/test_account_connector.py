"""Integration tests for AccountConnector domain.

Tests AccountConnector initialization, polling, event emission, and error handling.
"""

import pytest
import time
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.account_balance.account_connector import AccountConnector
from vfoundation.core import FSMCore


@pytest.fixture
def test_config():
    """Test configuration for AccountConnector."""
    return {
        "poll_interval_seconds": 1,  # Fast polling for tests
        "symbols": ["BTCUSDT", "ETHUSDT"],
    }


@pytest.fixture
def test_fsm_core():
    """FSM Core instance for testing."""
    return FSMCore()


def test_account_connector_initialization(test_config, test_fsm_core):
    """Test AccountConnector initializes correctly with config."""
    # Create a proper config dict with binance_api credentials for testnet
    config = {
        "account_observer": {
            "poll_interval": test_config.get("poll_interval_seconds", 1),
            "symbols": test_config.get("symbols", []),
        },
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
    }

    connector = AccountConnector(fsm=test_fsm_core, config=config)

    assert connector.update_interval == test_config["poll_interval_seconds"]
    assert connector.adapter is not None
    assert "testnet" in connector.adapter.base_url


def test_account_connector_polling_and_event_emission(test_config, test_fsm_core):
    """Test AccountConnector polls API and emits portfolio update events."""
    config = {
        "account_observer": {
            "poll_interval": 0.2,  # Fast for testing
            "symbols": test_config.get("symbols", []),
        },
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
    }

    connector = AccountConnector(fsm=test_fsm_core, config=config)

    # Mock the adapter methods
    with (
        patch.object(connector.adapter, "get_account_balance") as mock_balance,
        patch.object(connector.adapter, "get_open_positions") as mock_positions,
    ):
        # Setup mock returns
        mock_balance.return_value = [
            {"asset": "USDT", "balance": "1000.0", "crossUnPnl": "0.0"}
        ]
        mock_positions.return_value = [
            {
                "symbol": "ETHUSDT",
                "positionAmt": "1.0",
                "entryPrice": "2000",
                "unRealizedProfit": "100",
            }
        ]

        # Track emitted events
        emitted_events = []

        def event_listener(event):
            emitted_events.append(event)

        test_fsm_core.listen("EVT:BALANCE_UPDATE_RECEIVED", event_listener)
        test_fsm_core.listen("EVT:ACCOUNT_UPDATE_RECEIVED", event_listener)

        try:
            connector.start()
            # Wait for polling cycles
            time.sleep(1.0)

            # Verify methods were called
            assert mock_balance.call_count >= 1
            assert mock_positions.call_count >= 1

        finally:
            connector.stop()
            time.sleep(0.2)  # Allow cleanup


def test_account_connector_error_handling(test_config, test_fsm_core):
    """Test AccountConnector handles API errors gracefully."""
    config = {
        "account_observer": {
            "poll_interval": 0.2,
            "symbols": test_config.get("symbols", []),
        },
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
    }

    connector = AccountConnector(fsm=test_fsm_core, config=config)

    # Mock adapter to raise errors
    with (
        patch.object(connector.adapter, "get_account_balance") as mock_balance,
        patch.object(connector.adapter, "get_open_positions") as mock_positions,
    ):
        mock_balance.side_effect = Exception("API Error")
        mock_positions.side_effect = Exception("API Error")

        # Track emitted events
        emitted_events = []

        def event_listener(event):
            emitted_events.append(event)

        test_fsm_core.listen("EVT:BALANCE_UPDATE_RECEIVED", event_listener)
        test_fsm_core.listen("EVT:ACCOUNT_UPDATE_RECEIVED", event_listener)

        try:
            connector.start()
            time.sleep(1.0)

            # Verify API was called despite errors
            assert mock_balance.call_count >= 1

            # No events should be emitted on error (fail-closed)
            assert len(emitted_events) == 0

        finally:
            connector.stop()
            time.sleep(0.2)


def test_account_connector_graceful_shutdown(test_config, test_fsm_core):
    """Test AccountConnector shuts down polling thread gracefully."""
    config = {
        "account_observer": {
            "poll_interval": 0.2,
            "symbols": test_config.get("symbols", []),
        },
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
    }

    connector = AccountConnector(fsm=test_fsm_core, config=config)

    # Mock adapter methods
    with (
        patch.object(connector.adapter, "get_account_balance"),
        patch.object(connector.adapter, "get_open_positions"),
        patch.object(connector.adapter, "close_session"),
    ):
        # Start polling
        connector.start()
        time.sleep(0.5)

        # Verify thread is running
        assert connector.thread is not None
        assert connector.thread.is_alive()

        # Stop polling
        connector.stop()
        time.sleep(0.5)

        # Verify thread stopped
        assert not connector.thread.is_alive()
        assert not connector.running


def test_account_connector_config_defaults(test_fsm_core):
    """Test AccountConnector uses config defaults when values missing."""
    # Config without poll_interval set
    config = {
        "account_observer": {
            "symbols": ["BTCUSDT"]
            # No poll_interval - should use default of 30
        },
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
    }

    connector = AccountConnector(fsm=test_fsm_core, config=config)

    # Should use default poll_interval of 30
    assert connector.update_interval == 30
    assert connector.adapter is not None
