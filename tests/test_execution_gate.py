import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.execution_gate import ExecutionGate
from apps.reference.config_models import ExecutionGateConfig, StructuralGateConfig, ExecutionGateName
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.entry_plan import EntryPlanResult

class TestExecutionGate(unittest.TestCase):
    def setUp(self):
        # Configure Gate
        gate_config = ExecutionGateConfig(
            gates_enabled=[
                ExecutionGateName.HARD_VETO,
                ExecutionGateName.DIRECTION,
                ExecutionGateName.THRESHOLD,
                ExecutionGateName.SHIELD,
                ExecutionGateName.STRUCTURAL,
            ],
            structural_gate=StructuralGateConfig(
                min_risk_reward=1.5,
                enabled=True,
            )
        )
        self.gate = ExecutionGate(gate_config)
        self.features = {
            "atr": 10.0,
            "close_ts": 1000.0,
            # Mock directional features
            "pillar_operator_trend": 1.0, # Bullish
            "pillar_strategist_trend": 1.0, # Bullish
        }
        # Mock valid EntryPlan (R: 10, R: 20 -> RR: 2.0)
        self.mock_ep = EntryPlanResult(
            entry_price="100.0",
            stop_loss_price="90.0",
            take_profit_price="120.0",
            side="BUY",
            ref_price="100.0",
            atr="10.0",
            obi=None,
            obi_multiplier=1.0,
            obi_policy_applied=False,
            atr_multiplier=1.5,
        )

    def test_hard_veto_danger_zone(self):
        """Verify Hard Veto blocks entry if DangerZone is active."""
        ok, reason = self.gate.check_entry(
            symbol="BTCUSDT",
            side="BUY",
            features=self.features,
            final_score=1.0,
            shield_multiplier=1.0,
            entry_plan=self.mock_ep,
            signal_threshold=0.5,
            oracle_level="NORMAL",
            danger_zone_active=True # Trigger veto
        )
        self.assertFalse(ok)
        self.assertIn(NormalizedRejectReasons.HARD_VETO_BLOCKED, str(reason))

    def test_threshold_rejection(self):
        """Verify Threshold Gate blocks scores below threshold."""
        ok, reason = self.gate.check_entry(
            symbol="BTCUSDT",
            side="BUY",
            features=self.features,
            final_score=0.4, # < 0.5
            shield_multiplier=1.0,
            entry_plan=self.mock_ep,
            signal_threshold=0.5,
            oracle_level="NORMAL",
            danger_zone_active=False
        )
        self.assertFalse(ok)
        self.assertIn("SCORE_TOO_WEAK", str(reason))

    def test_shield_invariant_violation(self):
        """Verify Gate blocks invalid shield multiplier > 1.0."""
        ok, reason = self.gate.check_entry(
            symbol="BTCUSDT",
            side="BUY",
            features=self.features,
            final_score=1.0,
            shield_multiplier=1.1, # Invalid
            entry_plan=self.mock_ep,
            signal_threshold=0.5,
            oracle_level="NORMAL",
            danger_zone_active=False
        )
        self.assertFalse(ok)
        self.assertIn(NormalizedRejectReasons.SHIELD_INVARIANT_VIOLATED, str(reason))

    def test_shield_veto(self):
        """Verify Gate blocks shield multiplier == 0.0."""
        ok, reason = self.gate.check_entry(
            symbol="BTCUSDT",
            side="BUY",
            features=self.features,
            final_score=1.0,
            shield_multiplier=0.0, # Zeroed
            entry_plan=self.mock_ep,
            signal_threshold=0.5,
            oracle_level="NORMAL",
            danger_zone_active=False
        )
        self.assertFalse(ok)
        self.assertIn(NormalizedRejectReasons.SHIELD_VETO_BLOCKED, str(reason))

    def test_structural_gate_rr_check(self):
        """Verify Structural Gate checks Risk/Reward ratio."""
        # Create plan with low RR (Risk 10, Reward 10 -> RR 1.0 < 1.5)
        bad_ep = EntryPlanResult(
            entry_price="100.0", stop_loss_price="90.0", take_profit_price="110.0",
            side="BUY", ref_price="100.0", atr="10.0", obi=None, obi_multiplier=1.0,
            obi_policy_applied=False, atr_multiplier=1.5
        )
        ok, reason = self.gate.check_entry(
            symbol="BTCUSDT",
            side="BUY",
            features=self.features,
            final_score=1.0,
            shield_multiplier=1.0,
            entry_plan=bad_ep,
            signal_threshold=0.5,
            oracle_level="NORMAL",
            danger_zone_active=False
        )
        self.assertFalse(ok)
        self.assertIn(NormalizedRejectReasons.STRUCTURAL_GATE_BLOCKED, str(reason))

if __name__ == '__main__':
    unittest.main()
