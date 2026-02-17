
import unittest
import decimal
from unittest.mock import MagicMock, patch, ANY
import sys
import os

# Mock vfoundation
vfoundation_mock = MagicMock()
sys.modules["vfoundation"] = vfoundation_mock
sys.modules["vfoundation.core"] = MagicMock()
sys.modules["vfoundation.core.protocol"] = MagicMock()
sys.modules["vfoundation.dr"] = MagicMock()
sys.modules["vfoundation.dr.wal"] = MagicMock()
sys.modules["vfoundation.core.why_codes"] = MagicMock()

# Add project root
sys.path.append(os.getcwd())

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.config_models import ExitManagerConfig

class TestPillarToDecisionE2E(unittest.TestCase):
    def setUp(self):
        # Mock Config
        self.mock_config = MagicMock()
        instr_mock = MagicMock()
        # Explicitly disable overrides to prevent Decimal(Mock) errors
        instr_mock.signal_threshold = None
        instr_mock.neutral_threshold = None
        
        self.mock_config.instruments = {"BTCUSDT": instr_mock}
        
        # Strategies Registry (Enable the symbol!)
        self.mock_config.strategies_registry.assignments = {"BTCUSDT": ["aurora"]}
        
        # Aurora Config
        aurora = MagicMock()
        aurora.decision.scoring_version = "quadratic" # ENABLE QUADRATIC
        aurora.decision.signal_threshold = 0.1
        aurora.decision.exit = ExitManagerConfig()
        aurora.decision.safety_gates.enabled = False # Disable safety gates for simple test
        
        # Prevent Decimal(Mock) errors
        aurora.decision.signals.delta_price_cap_pct = 0.005
        aurora.decision.neutral_threshold = 0.05
        aurora.decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        
        # Side bias defaults
        aurora.decision.side_bias_window_sec = 420
        aurora.decision.side_bias_target_ratio = 0.72
        aurora.decision.side_bias_penalty_factor = 0.25
        aurora.decision.side_bias_min_intents = 18
        aurora.timeframe_sec = 60  # Essential for T2B-03 gate
        
        # Shield Config Defaults (Prevent Mock vs Float errors)
        se = aurora.decision.scoring_engine
        se.shield_enabled = True
        
        # Context Shield
        se.context_shield.enabled = True
        se.context_shield.default_multiplier = 1.0
        se.context_shield.no_regime_multiplier = 0.5
        se.context_shield.regime_multipliers = {}
        
        # Danger Zone Shield
        se.danger_zone_shield.enabled = True
        se.danger_zone_shield.vol_threshold = 0.95
        se.danger_zone_shield.spread_threshold = 50.0
        se.danger_zone_shield.motion_threshold = 3.0
        
        # Memory Shield
        se.memory_shield.enabled = True
        se.memory_shield.decay_rate = 0.95
        se.memory_shield.max_states = 100
        se.memory_shield.unknown_threshold = 10.0
        se.memory_shield.exploring_threshold = 50.0
        se.memory_shield.unknown_multiplier = 0.6
        se.memory_shield.exploring_multiplier = 0.8
        se.memory_shield.known_multiplier = 1.0
        se.memory_shield.storage_path = None
        se.memory_shield.flush_interval_sec = 60.0
        
        self.mock_config.strategies.aurora = aurora
        
        # Mock Emit
        self.emit_fn = MagicMock()
        
        # Initialize Handler with heavy mocks
        with patch("apps.reference.domains.decision_making.aurora_handler.ExecutionGate") as MockGate, \
             patch("apps.reference.domains.decision_making.aurora_handler.MemoryShield"), \
             patch("apps.reference.domains.decision_making.aurora_handler.quantize_exposure") as MockQuant: 
             
            # Configure Gate to PASS
            mock_gate_instance = MockGate.return_value
            mock_gate_instance.check_entry.return_value = (True, None)

            # Configure Quantizer to PASS (return valid position)
            MockQuant.return_value = MagicMock(qty="0.001", notional="50.0", margin_required="10.0", reject_reason=None)
            
            self.handler = AuroraHandler(
                config=self.mock_config,
                emit_fn=self.emit_fn,
                wall_time_fn=lambda: 1700000000.0
            )
            # Ensure gate is attached (init logic might skip if config wrong, but we force it)
            self.handler.execution_gate = mock_gate_instance

    def test_e2e_quadratic_flow(self):
        """Verify FE pillars -> Quadratic Kernel -> Emit Signal."""
        
        # 1. Features with PILLARS
        features = {
            "pillar_sum": 0.8,
            "pillar_operator": 0.8,
            "pillar_strategist": 0.9,
            "pillar_operator_trend": 1.0, # UP
            "price": "50000.0",
            "volatility": {"atr_14": 100.0},
            "liquidity": {"kappa": 0.9},
            "regime": "TREND_UP",
            "bar_close_ts": 1700000000
        }
        
        # 1.5 Inject Regime Heartbeat (Liveness Guard)
        self.handler.on_regime_detected({
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 1.0,
            "ts_ms": 1700000000000
        })
        
        # 2. Inject via CMD:PROCESS_STRATEGY (T2B-03)
        cmd = {
            "symbol": "BTCUSDT",
            "tf_sec": 60, # Matches config
            "bar_close_ts": 1700000000,
            "bar": {
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50000.0",
                "volume": "100.0"
            },
            "features": features,
            "warmup": {"ready": True, "full_ready": True},
            "regime": {"name": "TREND_UP"},
            "rid": "TEST_RID"
        }
        
        self.handler.on_process_strategy(cmd)
        
        # 3. Verify Emission
        if self.emit_fn.call_count == 0:
            print("DEBUG: No emit calls!")
        else:
            print(f"DEBUG: Emit calls: {self.emit_fn.call_args_list}")
            
        self.emit_fn.assert_called()
        
        # Find signal event
        calls = self.emit_fn.call_args_list
        signal_call = None
        for call in calls:
            if call[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED":
                signal_call = call
                break
                
        self.assertIsNotNone(signal_call, "Did not emit STRATEGY_SIGNAL_PRODUCED")
        
        # 4. Deep Inspection of Payload
        payload = signal_call[0][1]
        scoring = payload.get("scoring", {})
        psi = scoring.get("psi_vector", {})
        
        print(f"DEBUG: PSI Vector: {psi}")
        
        # CRITICAL CHECKS
        self.assertEqual(psi.get("scoring_engine"), "quadratic_v1")
        self.assertAlmostEqual(float(psi.get("pillar_sum", 0)), 0.8)
        
        # Quadratic Logic: 0.8^2 = 0.64 (approx)
        raw_exposure = float(psi.get("raw_exposure", 0))
        self.assertAlmostEqual(raw_exposure, 0.64, places=2)

if __name__ == "__main__":
    unittest.main()
