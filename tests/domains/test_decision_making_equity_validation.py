"""
Tests for DecisionMaking component's equity validation.
"""
import pytest
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
            "symbols_to_track": ["ETHUSDT"],
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "decision": {
                "signal_weights": {"obi": 1.0},
                "signal_threshold": 0.1,
                "position_sizing": {"min_position_size_usd": 10}
            },
            "tca_prefs": {},
            "risk_budgets": {}
        }
    }

def test_rejects_trade_intent_if_equity_is_zero(mock_fsm, mock_config):
    """Verify trade intent is deferred if portfolio equity is zero, added to pending."""
    decision_domain = DecisionMaking(fsm=mock_fsm, config=mock_config)
    
    features_msg = Message(op="EVT", verb="FEATURES_CALCULATED", src="test", dst="test", pld={"symbol": "ETHUSDT", "features": {"price": "3000", "obi": 0.5}})
    risk_msg = Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="test", dst="test", pld={"symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}})
    portfolio_msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="test", pld={"equity": "0"})

    decision_domain.on_portfolio(portfolio_msg)
    decision_domain.on_risk(risk_msg)
    decision_domain.on_features(features_msg)

    # Should not emit trade intent yet
    mock_fsm.emit.assert_not_called()
    # Symbol should be added to pending
    assert "ETHUSDT" in decision_domain.pending_symbols


def test_processes_pending_symbols_when_portfolio_arrives_with_valid_equity(mock_fsm, mock_config):
    """Verify pending symbols are processed when portfolio arrives with valid equity."""
    decision_domain = DecisionMaking(fsm=mock_fsm, config=mock_config)
    
    # First, send features and risk without portfolio
    features_msg = Message(op="EVT", verb="FEATURES_CALCULATED", src="test", dst="test", pld={"symbol": "ETHUSDT", "features": {"price": "3000", "obi": 0.5}})
    risk_msg = Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="test", dst="test", pld={"symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}})
    
    decision_domain.on_risk(risk_msg)
    decision_domain.on_features(features_msg)
    
    # Should be added to pending since no portfolio yet
    assert "ETHUSDT" in decision_domain.pending_symbols
    mock_fsm.emit.assert_not_called()
    
    # Now send portfolio with valid equity
    portfolio_msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="test", pld={"equity": "10000"})
    decision_domain.on_portfolio(portfolio_msg)
    
    # Should process pending symbol and emit trade intent
    mock_fsm.emit.assert_called_once()
    # Should remove from pending
    assert "ETHUSDT" not in decision_domain.pending_symbols
