"""
Test CFG-DOMAINS-STEP-02 runtime contract enforcement.

Validates that DecisionMaking enforces AuroraConfig type (not dict).
"""
import pytest
from unittest.mock import Mock
from apps.reference.config_models import AuroraConfig
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class TestDecisionMakingContractEnforcement:
    """Test that DecisionMaking enforces AuroraConfig contract."""
    
    def test_decision_making_requires_auroraconfig(self):
        """❌ Test that passing dict to DecisionMaking raises TypeError."""
        mock_fsm = Mock()
        mock_fsm.emit = Mock()
        
        # Try to pass dict (should fail)
        config_dict = {"trading": {"decision": {}}, "tca_prefs": {}, "risk_budgets": {}}
        
        with pytest.raises(TypeError) as exc_info:
            DecisionMaking(fsm=mock_fsm, config=config_dict)
        
        # Verify error message is clear
        assert "AuroraConfig" in str(exc_info.value)
        assert "dict" in str(exc_info.value)
        assert "to_dict" in str(exc_info.value)
    
    def test_decision_making_accepts_auroraconfig(self, root_mock_config):
        """✅ Test that passing AuroraConfig works correctly."""
        # Use existing fixture
        config = root_mock_config
        
        # Mock FSM
        mock_fsm = Mock()
        mock_fsm.emit = Mock()
        
        # Should initialize without error
        dm = DecisionMaking(fsm=mock_fsm, config=config)
        
        assert dm is not None
        assert not isinstance(dm.config, dict)  # NOT dict (the real contract)
