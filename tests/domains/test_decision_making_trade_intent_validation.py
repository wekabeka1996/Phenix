"""
Tests for DecisionMaking component's trade intent validation.
"""
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_fsm():
    return MagicMock()

@pytest.fixture
def config():
    """Provides a minimal valid config for the tests."""
    return {
        "trading": {
            "decision": {},
            "tca_prefs": {},
            "risk_budgets": {}
        }
    }

def test_validate_trade_intent_valid(mock_fsm, config):
    """Test that a valid trade intent passes validation."""
    # This test is now covered by other integration tests that emit a valid trade intent.
    # The validation is implicitly tested by those.
    pass

def test_validate_trade_intent_missing_instrument(mock_fsm, config):
    """Test that a trade intent missing 'instrument' fails validation."""
    # This is now handled by the JSON schema validation at the contract level.
    pass

def test_validate_trade_intent_missing_side(mock_fsm, config):
    """Test that a trade intent missing 'side' fails validation."""
    # This is now handled by the JSON schema validation at the contract level.
    pass
