"""Pytest configuration for domains tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Add apps to path for domain tests
apps_root = Path(__file__).parent.parent.parent / "apps"
if str(apps_root) not in sys.path:
    sys.path.insert(0, str(apps_root))

# Path setup is handled by root conftest.py


@pytest.fixture
def mock_fsm():
    """Mock FSM core for testing."""
    return MagicMock()


@pytest.fixture
def mock_config():
    """Mock config for testing."""
    config = MagicMock()
    config.__getitem__ = MagicMock(
        side_effect=lambda key: {
            "account_balance": {"poll_interval_seconds": 30},
            "trading_env": "test",
            "binance_ro_api_key": "test_key",
            "binance_ro_api_secret": "test_secret",
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://testnet.binance.vision",
                }
            },
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000,
                },
            },
            "risk": {
                "max_daily_drawdown_limit": 0.05,
                "score_weights": {
                    "delta_price": 0.05,
                    "obi": 0.35,
                    "tfi": 0.35,
                    "absorption_inverse": 0.25,
                },
                "trading_allowed_thresholds": {"max_risk_score": 0.8},
            },
            "domain_configuration": {
                "market_data": {"trading_mode": "live"},
                "feature_engineering": {"trading_mode": "live"},
                "decision_making": {"trading_mode": "live"},
                "risk_management": {"trading_mode": "live"},
                "execution_position": {"trading_mode": "live"},
                "audit_trail": {"trading_mode": "live"},
            },
        }.get(key, "test")
    )
    config.get = MagicMock(
        side_effect=lambda key, default=None: {
            "account_balance": {"poll_interval_seconds": 30},
            "trading_mode": "testnet",
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
            },
        }.get(key, default)
    )
    # Set attributes as strings
    config.binance_ro_api_key = "test_key"
    config.binance_ro_api_secret = "test_secret"
    config.trading_env = "test"
    config.trading_mode = "testnet"
    config.account_balance = {"poll_interval_seconds": 30}
    config.decision = {"signal_weights": {"obi": 0.6}}
    config.domain_configuration = {
        "market_data": {"trading_mode": "live"},
        "feature_engineering": {"trading_mode": "live"},
    }
    return config


# NOTE: adapter_live fixture removed — binance_execution_adapter.py was deleted.
# Use adapter_init.AdapterInitMixin for adapter wiring tests.
