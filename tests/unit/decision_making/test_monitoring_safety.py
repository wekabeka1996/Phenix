
import unittest
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from tests.conftest import make_app_cfg_stub

class TestMonitoringSafety(unittest.TestCase):
    """
    Test suite to ensure monitoring and telemetry logic in DecisionMaking
    is fail-safe and does not block trading operations.
    Addresses Incident: ETH Silent Drop (2026-01-05).
    """

    def setUp(self):
        # Mock FSMCore
        self.mock_fsm = MagicMock()
        
        # Mock AuroraConfig (strict object)
        self.mock_config = make_app_cfg_stub(
            domains__decision_making__qos_exposure_block_cooldown_sec=60,
            domains__decision_making__qos_max_intents_per_minute_per_symbol=5,
            domains__decision_making__qos_mode="monitor",
            domains__decision_making__position_sizing_min_position_size_usd=10,
            domains__decision_making__position_sizing_liquidity_based_cap_usd=10000,
            domains__decision_making__flip_hysteresis_mult=1.0,
        )

    def test_dm_initialization_counters(self):
        """Test that monitoring counters are initialized in __init__."""
        try:
            dm = DecisionMaking(fsm=self.mock_fsm, config=self.mock_config)
        except Exception as e:
            self.fail(f"DecisionMaking failed to initialize: {e}")

        self.assertTrue(hasattr(dm, "intents_seen_total"), "Missing intents_seen_total")
        self.assertTrue(hasattr(dm, "intents_blocked_total"), "Missing intents_blocked_total")
        self.assertTrue(hasattr(dm, "last_alert_check_time"), "Missing last_alert_check_time")
        
        # Verify initial values
        self.assertEqual(dm.intents_seen_total, 0)
        self.assertEqual(dm.intents_blocked_total, 0)

    def test_record_accepted_intent_safety(self):
        """Test that _record_accepted_intent increments counters and doesn't crash."""
        dm = DecisionMaking(fsm=self.mock_fsm, config=self.mock_config)
        
        # Call the method
        dm._record_accepted_intent("ETHUSDT")
        
        # Verify side effects
        self.assertEqual(dm.intents_seen_total, 1)
        self.assertEqual(dm.intents_blocked_total, 0)

    def test_record_blocked_intent_safety(self):
        """Test that _record_blocked_intent increments counters and doesn't crash."""
        dm = DecisionMaking(fsm=self.mock_fsm, config=self.mock_config)
        
        # Call the method
        dm._record_blocked_intent("ETHUSDT")
        
        # Verify side effects
        self.assertEqual(dm.intents_seen_total, 1)
        self.assertEqual(dm.intents_blocked_total, 1)

if __name__ == '__main__':
    unittest.main()
