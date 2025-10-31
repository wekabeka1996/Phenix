"""
Tests for DecisionMaking component's equity validation.
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
def mock_config():
    """Provides a valid config for the tests."""
    return {
        "trading": {
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "decision": {
                "signal_weights": {"obi": 1.0},
                "signal_threshold": 0.1,
                "position_sizing": {"min_position_size_usd": 10},
            },
            "tca_prefs": {},
            "risk_budgets": {},
        }
    }


def test_rejects_trade_intent_if_equity_is_zero(mock_fsm, mock_config, caplog):
    """Verify trade intent is rejected if portfolio equity is zero."""
    decision_domain = DecisionMaking(fsm=mock_fsm, config=mock_config)

    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "ETHUSDT", "features": {"price": "3000", "obi": 0.5}},
    )
    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="test",
        dst="test",
        pld={"ts": int(time.time() * 1000), "symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}},
    )
    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="test",
        pld={"equity": "0"},
    )

    decision_domain.on_portfolio(portfolio_msg)
    decision_domain.on_risk(risk_msg)
    decision_domain.on_features(features_msg)

    mock_fsm.emit.assert_not_called()
    assert "equity is zero or negative" in caplog.text
