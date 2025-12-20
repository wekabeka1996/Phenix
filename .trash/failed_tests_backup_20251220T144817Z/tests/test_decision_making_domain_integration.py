import pytest
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.decision_making import DecisionMaking

class TestDecisionMakingIntegration:
    def test_decision_making_uses_domains_config(self, mock_fsm, root_mock_config):
        """Verify DecisionMaking initializes with values from domains config."""
        # Initialize component
        dm = DecisionMaking(mock_fsm, root_mock_config)
        
        # Verify values match domains.yaml
        # Position sizing
        assert dm.min_pos_size_usd == 10
        assert dm.liq_cap_usd == 10000
        
        # QoS
        assert dm.qos_exposure_block_cooldown_sec == 10
        assert dm.qos_symbol_cooldown_sec == 3
        assert dm.qos_max_intents_per_minute_per_symbol == 6
        
        # Features TTL
        assert dm.features_ttl_sec == 5
        
        # Bar gating
        assert dm._bar_ms == 900000
        
        # Behavior FSM
        assert dm._behavior_thresholds["high_vol_multiplier"] == 2.0
        assert dm._behavior_thresholds["low_vol_multiplier"] == 0.5
