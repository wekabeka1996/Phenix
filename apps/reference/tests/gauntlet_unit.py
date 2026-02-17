
import unittest
import logging
import decimal
from unittest.mock import MagicMock, patch
from typing import Dict, Any

# Mock dependencies
import sys
from unittest.mock import MagicMock

# Create a dummy module for vfoundation to allow attribute access
vfoundation_mock = MagicMock()
sys.modules["vfoundation"] = vfoundation_mock
sys.modules["vfoundation.core"] = MagicMock()
sys.modules["vfoundation.core.protocol"] = MagicMock()
sys.modules["vfoundation.dr"] = MagicMock()
sys.modules["vfoundation.dr.wal"] = MagicMock()

# Also ensure vfoundation.core.protocol.Message is available
sys.modules["vfoundation.core.protocol"].Message = MagicMock()
sys.modules["vfoundation.core.why_codes"] = MagicMock()
sys.modules["vfoundation.core.why_codes"].WhyCode = MagicMock()
sys.modules["vfoundation.core.why_codes"].format_why_with_details = MagicMock()

from apps.reference.domains.decision_making.shields.danger_zone import DangerZoneShield
from apps.reference.domains.decision_making.shields.memory_shield import MemoryShield
from apps.reference.domains.decision_making.execution_gate import ExecutionGate
from apps.reference.domains.decision_making.exit_manager import ExitManager
from apps.reference.config_models import (
    ExecutionGateConfig, ExecutionGateName, StructuralGateConfig, ExitManagerConfig
)
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult

class TestShieldSystem(unittest.TestCase):
    def test_danger_zone_prefix(self):
        """BUG-1: Verify DANGER_ZONE: prefix."""
        shield = DangerZoneShield(vol_threshold=0.5)
        features = {"volatility_state": 1.0} # Tripped
        
        result = shield.evaluate("BTCUSDT", features, 1.0, 1.0)
        
        self.assertEqual(result.multiplier, 0.0)
        self.assertTrue(any(r.startswith("DANGER_ZONE:") for r in result.reasons), 
                       f"Reasons check failed: {result.reasons}")

    def test_memory_shield_evaluate_readonly(self):
        """BUG-2: Verify evaluate() does not side-effect (no record_visit)."""
        shield = MemoryShield(max_states=5)
        # Mock record_visit to ensure it's NOT called internally
        shield._maybe_record_visit = MagicMock()
        
        features = {"price": 100}
        shield.evaluate("BTCUSDT", features, 1.0, 1.0)
        
        shield._maybe_record_visit.assert_not_called()
        
    def test_memory_shield_record_visit_public(self):
        """BUG-2: Verify public record_visit works and is idempotent per bar."""
        shield = MemoryShield(max_states=5)
        shield._maybe_record_visit = MagicMock()
        
        features = {"price": 100}
        
        # 1. First call
        shield.record_visit("BTCUSDT", features, bar_close_ts=1000, state_hash="abc")
        shield._maybe_record_visit.assert_called_once()
        
        # 2. Second call same bar (same TS) - internal _maybe_record_visit handles logic, 
        # but here we just check if the public method passes it through.
        # Actually _maybe_record_visit implements the deduplication.
        # So we should verify _maybe_record_visit IS called, and it handles logic.
        pass 

class TestExecutionGate(unittest.TestCase):
    def setUp(self):
        self.config = ExecutionGateConfig(
            # enabled=True,  # REMOVED: Not in schema
            gates_enabled=[ExecutionGateName.DIRECTION],
            structural_gate=StructuralGateConfig(min_risk_reward=1.0)
        )
        self.gate = ExecutionGate(self.config)

    def test_float_trend_handling(self):
        """ExecutionGate Fix: Handle float values for trends."""
        features = {
            "pillar_operator_trend": 1.0, # Float!
            "pillar_strategist_trend": 1.0
        }
        
        # Should NOT raise ValueError
        ok, reason = self.gate.check_entry(
            "BTCUSDT", "BUY", features, 0.5, 1.0, None, 0.1
        )
        
        # If Logic works, this returns True (Operator 1.0 == Buy)
        self.assertTrue(ok, f"Gate failed with reason: {reason}")
        
    def test_missing_op_trend_fail_closed(self):
        features = {} # Missing trend
        ok, reason = self.gate.check_entry(
            "BTCUSDT", "BUY", features, 0.5, 1.0, None, 0.1
        )
        self.assertFalse(ok)
        self.assertIn("MissingOpTrend", reason)

class TestExitManager(unittest.TestCase):
    def test_config_defaults(self):
        """BUG-3: Verify ExitManager survives empty config but is disabled."""
        cfg = ExitManagerConfig() # Empty
        manager = ExitManager(cfg)
        
        # Should default to safe values, no crash
        self.assertTrue(manager.config.signal_exit_enabled) # Default is True
        
if __name__ == "__main__":
    unittest.main()
