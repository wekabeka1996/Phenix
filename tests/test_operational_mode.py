import unittest
from decimal import Decimal
from apps.reference.domains.decision_making.operational_mode import ModeManager
from apps.reference.config_models import OperationalMode, MemoryShieldConfig


class TestModeManager(unittest.TestCase):
    def setUp(self):
        # Base config for testing
        self.mem_config = MemoryShieldConfig(
            enabled=True,
            unknown_multiplier=0.6,
            exploring_multiplier=0.8,
            known_multiplier=1.0,
            decay_rate=0.95,
            max_states=200
        )

    def test_paranoid_mode_no_overrides(self):
        """Verify PARANOID mode returns config unchanged."""
        manager = ModeManager(OperationalMode.PARANOID)

        # Test direct overrides
        overrides = manager.get_overrides()
        self.assertEqual(overrides, {})

        # Test applied overrides
        patched_config = manager.apply_memory_shield_overrides(self.mem_config)
        self.assertEqual(patched_config.unknown_multiplier, 0.6)
        self.assertEqual(patched_config.exploring_multiplier, 0.8)

    def test_curious_mode_overrides(self):
        """Verify CURIOUS mode relaxes Memory Shield."""
        manager = ModeManager(OperationalMode.CURIOUS)

        # Test direct overrides (informational)
        overrides = manager.get_overrides()
        self.assertIn("memory_shield", overrides)
        self.assertEqual(overrides["memory_shield"]["unknown_multiplier"], 1.0)

        # Test applied overrides
        patched_config = manager.apply_memory_shield_overrides(self.mem_config)
        # Should be 1.0 (no penalty)
        self.assertEqual(patched_config.unknown_multiplier, 1.0)
        self.assertEqual(patched_config.exploring_multiplier, 1.0)
        self.assertEqual(patched_config.known_multiplier, 1.0)

        # Other fields should stay same
        self.assertEqual(patched_config.decay_rate, 0.95)

    def test_invalid_mode_rejected(self):
        """Unsupported raw mode strings should fail fast instead of no-op fallback."""
        with self.assertRaises(ValueError):
            ModeManager("invalid")
