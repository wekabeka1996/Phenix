"""
Tests for DecisionMaking component's logic branches.
"""

import pytest
import time
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.protocol import Message


@pytest.fixture
def mock_fsm():
    return MagicMock()


@pytest.fixture
def full_valid_config():
    """Provides a complete and valid trading configuration."""
    return {
        "trading": {
            "instruments": {
                "BTCUSDT": {"step_size": "0.001"},
            },
            "decision": {
                "signal_weights": {"obi": 0.5, "tfi": 0.5, "absorption": 0.1},
                "signal_threshold": 0.2,
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000,
                },
            },
            "tca_prefs": {},
            "risk_budgets": {},
        }
    }


def test_strong_long_signal_emits_trade(mock_fsm, full_valid_config):
    """Verify a strong LONG signal results in a trade intent."""
    decision_domain = DecisionMaking(fsm=mock_fsm, config=full_valid_config)

    features = {"price": "20000", "obi": 0.8, "tfi": 0.8}
    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "BTCUSDT", "features": features},
    )
    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "BTCUSDT", "risk_parameters": {"is_trading_allowed": True}},
    )
    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="test",
        pld={"equity": "50000"},
    )

    decision_domain.on_portfolio(portfolio_msg)
    decision_domain.on_risk(risk_msg)
    decision_domain.on_features(features_msg)

    mock_fsm.emit.assert_called_once()


def test_position_size_below_minimum_rejected(mock_fsm, full_valid_config, caplog):
    """Verify that trade intent is rejected if calculated position size is below minimum."""
    config_low_liq = full_valid_config.copy()
    config_low_liq["trading"]["decision"]["position_sizing"][
        "liquidity_based_cap_usd"
    ] = 5
    decision_domain = DecisionMaking(fsm=mock_fsm, config=config_low_liq)

    features = {"price": "45000", "obi": 0.8, "tfi": 0.8}
    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "BTCUSDT", "features": features},
    )
    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "BTCUSDT", "risk_parameters": {"is_trading_allowed": True}},
    )
    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="test",
        pld={"equity": "10000"},
    )

    decision_domain.on_portfolio(portfolio_msg)
    decision_domain.on_risk(risk_msg)
    decision_domain.on_features(features_msg)

    mock_fsm.emit.assert_not_called()
    assert "below minimum" in caplog.text.lower()
