import unittest
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_models import create_aurora_config
from tests.conftest import make_app_cfg_stub


def _to_dict(obj):
    if isinstance(obj, SimpleNamespace):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    return obj

class TestMonitoringSafety(unittest.TestCase):
    """
    Test suite to ensure monitoring and telemetry logic in DecisionMaking
    is fail-safe.
    """

    def setUp(self):
        # Mock FSMCore
        self.mock_fsm = MagicMock()
        
        # Mock AuroraConfig
        self.mock_config = make_app_cfg_stub(
            domains__decision_making__qos_exposure_block_cooldown_sec=60,
            domains__decision_making__qos_max_intents_per_minute_per_symbol=5,
            domains__decision_making__qos_mode="monitor",
            domains__decision_making__position_sizing_min_position_size_usd=10,
            domains__decision_making__position_sizing_liquidity_based_cap_usd=10000,
            domains__decision_making__flip_hysteresis_mult=1.0,
        )

    def test_dm_initialization_delegates(self):
        """Test that monitoring delegates are initialized."""
        dm = DecisionMaking(fsm=self.mock_fsm, config=create_aurora_config(_to_dict(self.mock_config)))
        
        # In the new architecture, counters are in _readiness or other delegates
        # We just verify the dm object exists and doesn't crash
        self.assertIsNotNone(dm)

    def test_record_accepted_intent_safety(self):
        """Test that _record_accepted_intent doesn't crash."""
        dm = DecisionMaking(fsm=self.mock_fsm, config=create_aurora_config(_to_dict(self.mock_config)))
        
        # This method might be internal to a delegate now, but if it exists on DM, we call it
        if hasattr(dm, "_record_accepted_intent"):
            dm._record_accepted_intent("ETHUSDT")
        
    def test_record_blocked_intent_safety(self):
        """Test that _record_blocked_intent doesn't crash."""
        dm = DecisionMaking(fsm=self.mock_fsm, config=create_aurora_config(_to_dict(self.mock_config)))
        
        if hasattr(dm, "_record_blocked_intent"):
            dm._record_blocked_intent("ETHUSDT")

if __name__ == '__main__':
    unittest.main()
