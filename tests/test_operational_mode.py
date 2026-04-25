from unittest.mock import MagicMock
from apps.reference.domains.strategies.runtimes.aurora.config_loader import AuroraConfigLoaderMixin
from apps.reference.config_contract import ConfigContractError
import unittest
from decimal import Decimal
from apps.reference.domains.decision_making.primitives.operational_mode import ModeManager
from apps.reference.config_models import OperationalMode, MemoryShieldConfig


class TestModeManager(unittest.TestCase):
    def setUp(self):
        # Base config for testing
        self.mem_config = MemoryShieldConfig(
            enabled=True,
            unknown_threshold=3,
            exploring_threshold=10,
            unknown_multiplier=0.6,
            exploring_multiplier=0.8,
            known_multiplier=1.0,
            decay_rate=0.95,
            max_states=200,
            storage_path=None,
            flush_interval_sec=60.0,
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


class DummyHandler(AuroraConfigLoaderMixin):
    def __init__(self, config):
        self.config = config
        self.logger = MagicMock()
        self._build_shield_cascade = MagicMock()


class TestAuroraConfigLoaderStrictMode(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.config.strategies = MagicMock()
        self.config.strategies.aurora = MagicMock()
        self.config.strategies.aurora.timeframe_sec = 60
        from types import SimpleNamespace
        self.decision = SimpleNamespace()
        self.decision.signal_threshold = "0.1"
        self.decision.side_bias_window_sec = 60
        self.decision.side_bias_target_ratio = 0.5
        self.decision.side_bias_penalty_factor = 0.5
        self.decision.side_bias_min_intents = 1
        self.decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        self.config.strategies.aurora.decision = self.decision

    def test_operational_mode_enum_accepted(self):
        """operational_mode='paranoid'/'curious' accepted through proper enum path"""
        for mode in [OperationalMode.PARANOID, OperationalMode.CURIOUS]:
            self.decision.operational_mode = mode
            handler = DummyHandler(self.config)
            handler._load_config()
            self.assertEqual(handler.mode_manager.mode, mode)

    def test_legacy_aliases_normalized_to_paranoid(self):
        """Legacy operational_mode aliases normalize at the Aurora config loader boundary."""
        for legacy_str in ["testnet", "production"]:
            self.decision.operational_mode = legacy_str
            handler = DummyHandler(self.config)
            handler._load_config()
            self.assertEqual(handler.mode_manager.mode,
                             OperationalMode.PARANOID)

    def test_missing_mock_operational_mode_defaults_to_paranoid(self):
        """Missing or mock-valued operational_mode in test doubles falls back to PARANOID."""
        handler = DummyHandler(self.config)
        handler._load_config()
        self.assertEqual(handler.mode_manager.mode, OperationalMode.PARANOID)
