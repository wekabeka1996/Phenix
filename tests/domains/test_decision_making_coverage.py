"""
Unit tests for DecisionMaking component to cover critical logic branches.
"""
import decimal
import pytest
from unittest.mock import MagicMock, patch

# Ensure the app path is available for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from apps.reference.domains.decision_making.decision_making import DecisionMaking

@pytest.fixture
def mock_fsm():
    """Creates a mock FSM core."""
    return MagicMock()

@pytest.fixture
def mock_config():
    """Creates a mock configuration dictionary."""
    return {
        "trading": {
            "decision": {
                "signal_weights": {
                    "feature1": 0.6,
                    "feature2": 0.4
                },
                "signal_threshold": "0.5",
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000
                }
            },
            "instruments": {
                "BTCUSDT": {
                    "step_size": "0.001"
                }
            },
            "tca_prefs": {},
            "risk_budgets": {}
        }
    }

@pytest.fixture
def decision_making_instance(mock_fsm, mock_config):
    """Creates an instance of DecisionMaking with mocked dependencies."""
    return DecisionMaking(fsm=mock_fsm, config=mock_config)

def get_default_context():
    """Returns a default valid context for decision making."""
    return {
        "features": {
            "features": {
                "feature1": 1.0,
                "feature2": 0.8,
                "price": "50000"
            }
        },
        "risk_params": {
            "risk_parameters": {
                "is_trading_allowed": True
            }
        },
        "portfolio": {
            "equity": "5000"
        },
        "regime": {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP"
        }
    }

@patch('apps.reference.domains.decision_making.decision_making.logging.getLogger')
def test_rejects_decision_if_equity_is_zero(mock_get_logger, decision_making_instance):
    """
    Verify that no trade intent is proposed if portfolio equity is zero.
    """
    # Arrange: Set up the mock logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    decision_making_instance.logger = mock_logger

    context = get_default_context()
    context["portfolio"]["equity"] = "0"
    
    # Act
    decision_making_instance._make_decision_for_symbol("BTCUSDT", context, "test_rid")
    
    # Assert
    decision_making_instance.fsm.emit.assert_not_called()
    mock_logger.warning.assert_called_with(
        "Trade intent for BTCUSDT rejected: equity is zero or negative."
    )

@patch('apps.reference.domains.decision_making.decision_making.logging.getLogger')
def test_rejects_decision_if_trading_not_allowed(mock_get_logger, decision_making_instance):
    """
    Verify that no trade intent is proposed if risk manager forbids trading.
    """
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    decision_making_instance.logger = mock_logger

    context = get_default_context()
    context["risk_params"]["risk_parameters"]["is_trading_allowed"] = False
    
    decision_making_instance._make_decision_for_symbol("BTCUSDT", context, "test_rid")
    
    decision_making_instance.fsm.emit.assert_not_called()
    mock_logger.info.assert_called_with(
        "Trade intent for BTCUSDT rejected: Trading not allowed by risk manager."
    )

@patch('apps.reference.domains.decision_making.decision_making.logging.getLogger')
def test_rejects_decision_on_neutral_signal(mock_get_logger, decision_making_instance):
    """
    Verify that no trade intent is proposed if the signal score is below the threshold.
    """
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    decision_making_instance.logger = mock_logger

    context = get_default_context()
    context["features"]["features"]["feature1"] = 0.1  # Lower the feature value
    context["features"]["features"]["feature2"] = 0.1
    
    decision_making_instance._make_decision_for_symbol("BTCUSDT", context, "test_rid")
    
    decision_making_instance.fsm.emit.assert_not_called()
    # Check that the log message contains the expected rejection reason
    mock_logger.info.assert_any_call(
        'REJECT: Neutral signal 0.1000 (Threshold: 0.5)'
    )

@patch('apps.reference.domains.decision_making.decision_making.logging.getLogger')
def test_rejects_decision_on_counter_trend_signal(mock_get_logger, decision_making_instance):
    """
    Verify that a 'sell' signal is rejected during a 'TREND_UP' regime.
    """
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    decision_making_instance.logger = mock_logger

    context = get_default_context()
    # Create a strong sell signal
    context["features"]["features"]["feature1"] = -1.0
    context["features"]["features"]["feature2"] = -1.0
    
    decision_making_instance._make_decision_for_symbol("BTCUSDT", context, "test_rid")
    
    decision_making_instance.fsm.emit.assert_not_called()
    mock_logger.info.assert_called_with(
        "REJECT: Counter-trend sell blocked by regime TREND_UP"
    )

@patch('apps.reference.domains.decision_making.decision_making.uuid.uuid4', return_value='mock_uuid')
@patch('apps.reference.domains.decision_making.decision_making.logging.getLogger')
def test_proposes_intent_on_valid_buy_signal(mock_get_logger, mock_uuid, decision_making_instance):
    """
    Verify that a valid 'buy' signal results in a proposed trade intent.
    """
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger
    decision_making_instance.logger = mock_logger

    context = get_default_context()
    
    decision_making_instance._make_decision_for_symbol("BTCUSDT", context, "test_rid")
    
    # Assert that a trade intent event was emitted once
    decision_making_instance.fsm.emit.assert_called_once()
    
    # Get the actual call arguments
    call_args, call_kwargs = decision_making_instance.fsm.emit.call_args
    
    # Assert event name and why
    assert call_args[0] == "EVT:TRADE_INTENT_PROPOSED"
    assert call_kwargs['why'] == "trade_intent"
    
    # Assert payload contents robustly
    payload = call_kwargs['payload']
    assert payload['symbol'] == 'BTCUSDT'
    assert payload['side'] == 'buy'
    assert decimal.Decimal(payload['order']['qty']) == decimal.Decimal('0.010')
    assert decimal.Decimal(payload['size']['notional_cap_usd']) == decimal.Decimal('500.0')
    assert payload['idempotent_key'] == 'mock_uuid'
    assert 'pos_size_usd=500.00 (simple 10% equity cap)' in payload['why']
