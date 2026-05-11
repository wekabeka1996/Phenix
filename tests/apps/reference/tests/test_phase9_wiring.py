
from apps.reference.config_models import (
    AuroraConfig, DecisionConfig, ExitManagerConfig
)
from apps.reference.shared.decision_primitives.shields.memory_shield import MemoryShield
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler, ScoringResult
import decimal
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock vfoundation to prevent import hang
sys.modules["vfoundation"] = MagicMock()
sys.modules["vfoundation.core"] = MagicMock()
sys.modules["vfoundation.core.protocol"] = MagicMock()
sys.modules["vfoundation.dr"] = MagicMock()
sys.modules["vfoundation.dr.wal"] = MagicMock()
sys.modules["vfoundation.obs"] = MagicMock()
sys.modules["vfoundation.obs.domain_bridge"] = MagicMock()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__)))))


class TestPhase9Wiring(unittest.TestCase):
    def setUp(self):
        # Mock Config
        self.mock_config = MagicMock()

        # Mock Instruments Config (execution.target_leverage is the SSOT — LEV-REPOINT-QUANTIZER-2026-05-09)
        btcusdt_mock = MagicMock(
            step_size="0.001",
            min_qty="0.001",
            min_notional="5.0",
            tick_size="0.01",
        )
        btcusdt_mock.execution.target_leverage = 10
        self.mock_config.instruments = {
            "BTCUSDT": btcusdt_mock,
        }

        # Mock Strategy Config
        aurora_cfg = MagicMock()
        decision_cfg = MagicMock()
        decision_cfg.exit = ExitManagerConfig()  # Valid Exit Config
        decision_cfg.scoring_version = "quadratic"

        # Phase 9: Memory Shield Config
        mem_cfg = MagicMock()
        mem_cfg.enabled = True
        mem_cfg.decay_rate = 0.95
        mem_cfg.max_states = 10
        mem_cfg.storage_path = "/tmp/memory_shield_test.json"

        # Scoring Engine Config
        scoring_eng = MagicMock()
        scoring_eng.shield_enabled = True
        scoring_eng.memory_shield = mem_cfg

        decision_cfg.scoring_engine = scoring_eng
        aurora_cfg.decision = decision_cfg

        self.mock_config.strategies.aurora = aurora_cfg

        # Mock Emit Function
        self.emit_fn = MagicMock()

        # Instantiate Handler (with patched methods to avoid heavy init)
        with patch("apps.reference.domains.strategies.runtimes.aurora.handler.UnifiedFeatureExtractor"), \
                patch("apps.reference.domains.strategies.runtimes.aurora.handler.ExecutionGate"), \
                patch("apps.reference.domains.strategies.runtimes.aurora.handler.DomainConfigResolver"):
            self.handler = AuroraHandler(
                config=self.mock_config,
                emit_fn=self.emit_fn,
                wall_time_fn=lambda: 1700000000.0
            )

    def test_emit_signal_quantization_wiring(self):
        """Verify BUG-5: Quantizer is wired and injects payload."""
        # Setup Result
        result = ScoringResult(
            score=0.8,  # High conviction
            thr_buy=0.5,
            thr_sell=-0.5,
            regime="TREND_UP",
            psi_vector={"trend": 0.8},
            side="BUY",
            why_chain=["QuadraticScoring"],
            shield_multiplier=1.0,
            details={"memory_state_hash": "test_hash_123"}
        )

        features = {
            "price": "50000.0",
            "volatility": {"atr_14": 100.0},
            "liquidity": {"kappa": 0.9}
        }

        # Mock Instrument Config helper
        with patch.object(self.handler, "_get_instrument_config") as mock_get_instr:
            instr_cfg = MagicMock()
            # max_notional_value still read from aurora.assets.leverage (separate surface, not this seam)
            instr_cfg.leverage.max_notional_value = decimal.Decimal("1000000")
            mock_get_instr.return_value = instr_cfg

            # Act
            self.handler._emit_signal(
                symbol="BTCUSDT",
                result=result,
                features=features,
                source_event={}
            )

        # Assert Emit Called
        self.emit_fn.assert_called_once()
        args, _ = self.emit_fn.call_args
        event_name, payload = args

        self.assertEqual(event_name, "EVT:STRATEGY_SIGNAL_PRODUCED")

        # Assert Quantization in Payload (BUG-5 Fix)
        self.assertIn("quantization", payload)
        q = payload["quantization"]
        print(f"Quantization Payload: {q}")

        # Expected:
        # Score 0.8 -> Exposure 0.8
        # Max Notional 1,000,000 -> Notional 800,000 (approx)
        # Price 50,000 -> Qty 16 (approx)
        # Leverage 10 from instruments SSOT (execution.target_leverage) -> Margin 80,000

        qty = decimal.Decimal(q["qty"])
        self.assertTrue(qty > 0)
        # 800k * 0.999 (fee buffer) / 50000 = 15.984
        self.assertEqual(q["qty"], "15.984")

    def test_memory_shield_recording(self):
        """Verify BUG-2: MemoryShield.record_visit is called idempotently."""
        # Mock Memory Shield
        self.handler._memory_shield = MagicMock(spec=MemoryShield)

        result = ScoringResult(
            score=0.8,
            thr_buy=0.5,
            thr_sell=-0.5,
            regime="TREND_UP",
            psi_vector={},
            side="BUY",
            why_chain=[],
            details={"memory_state_hash": "hash_xyz_789"}
        )

        features = {"price": "50000.0"}

        # Act
        with patch.object(self.handler, "_get_instrument_config"):
            self.handler._emit_signal("BTCUSDT", result, features, {})

        # Assert Record Visit Called
        self.handler._memory_shield.record_visit.assert_called_once()
        call_args = self.handler._memory_shield.record_visit.call_args
        self.assertEqual(call_args.kwargs["state_hash"], "hash_xyz_789")
        self.assertEqual(call_args.kwargs["now_ts"], 1700000000)


if __name__ == "__main__":
    unittest.main()
