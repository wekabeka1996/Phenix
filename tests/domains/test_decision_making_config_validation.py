"""
Tests for DecisionMaking component's configuration validation.
"""

import pytest
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.decision_making import DecisionMaking


@pytest.fixture
def mock_fsm():
    return MagicMock()


def test_halts_if_decision_config_is_missing(mock_fsm):
    """Verify that decision making halts if 'decision' config is missing."""
    config = {"trading": {}}
    with pytest.raises(ValueError, match="Configuration key missing: 'decision'"):
        DecisionMaking(fsm=mock_fsm, config=config)


def test_halts_if_tca_prefs_config_is_missing(mock_fsm):
    """Verify that decision making halts if 'tca_prefs' config is missing."""
    config = {"trading": {"decision": {}}}
    with pytest.raises(ValueError, match="Configuration key missing: 'tca_prefs'"):
        DecisionMaking(fsm=mock_fsm, config=config)


def test_halts_if_risk_budgets_config_is_missing(mock_fsm):
    """Verify that decision making halts if 'risk_budgets' config is missing."""
    config = {"trading": {"decision": {}, "tca_prefs": {}}}
    with pytest.raises(ValueError, match="Configuration key missing: 'risk_budgets'"):
        DecisionMaking(fsm=mock_fsm, config=config)
