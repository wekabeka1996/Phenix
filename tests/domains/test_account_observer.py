"""
Tests for Account Observer domain.
"""

import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.account_observer.account_observer import AccountObserver


class TestAccountObserver:
    @pytest.fixture
    def mock_config(self):
        return {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://testnet.binancefuture.com",
                }
            },
            "account_observer": {"poll_interval": 5, "symbols": ["BTCUSDT", "ETHUSDT"]},
        }

    @pytest.fixture
    def mock_fsm(self):
        return Mock()

    @patch("apps.reference.domains.account_observer.account_observer.Client")
    def test_init_success(self, mock_client, mock_fsm, mock_config):
        """Test successful initialization."""
        observer = AccountObserver(mock_fsm, mock_config)
        assert observer.config == mock_config
        assert observer.fsm is not None

    def test_init_missing_api_key(self, mock_fsm):
        """Test initialization fails when API key is missing."""
        config = {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_secret": "secret",
                    "rest_url": "https://testnet.binancefuture.com",
                    # Missing api_key
                }
            },
        }
        with pytest.raises(ValueError):
            AccountObserver(mock_fsm, config)
