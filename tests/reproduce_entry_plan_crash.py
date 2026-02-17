import logging
import sys
import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal

# Add project root to path
sys.path.append(".")

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.config_models import DecisionConfig, ExecutionGateConfig, ExecutionGateName
from apps.reference.domains.decision_making.execution_gate import ExecutionGate

class TestEntryPlanCrash(unittest.TestCase):
    def setUp(self):
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        
        # Mock dependencies
        self.mock_config = MagicMock()
        self.mock_config.domains.decision_making.entry_plan = None # SIMULATE MISSING CONFIG
        self.mock_config.strategies.aurora.decision.execution = ExecutionGateConfig(
            enabled=True,
            gates_enabled=[ExecutionGateName.HARD_VETO]
        )
        
        # Instantiate Handler with mocked config
        # We need to mock a lot of internals to get to _process_decision without crashing earlier
        with patch("apps.reference.domains.decision_making.aurora_handler.AuroraHandler._start_workers"), \
             patch("apps.reference.domains.decision_making.aurora_handler.AuroraHandler._init_state_store"):
            self.handler = AuroraHandler("aurora", self.mock_config)
            
        # Mock internal components that might be missing or fail
        self.handler._symbol_states = MagicMock()
        self.handler._is_symbol_enabled = MagicMock(return_value=True)
        self.handler._get_instrument_config = MagicMock(return_value=MagicMock())
        self.handler._check_regime_liveness = MagicMock(return_value=None) # Liveness OK
        self.handler._check_liquidity_gate = MagicMock(return_value=(True, {})) # Liquidity OK
        self.handler._get_side_bias_state = MagicMock(return_value=None)
        self.handler._get_regime_thresholds = MagicMock(return_value={})
        self.handler.scoring_kernel_cls = MagicMock()
        
        # Mock scoring result
        mock_result = MagicMock()
        mock_result.side = "BUY"
        mock_result.score = 1.0
        mock_result.deferred = False
        mock_result.shield_breakdown = {}
        mock_result.shield_multiplier = 1.0
        mock_result.threshold_factor = 1.0
        mock_result.thr_buy = 0.5
        mock_result.thr_sell = 0.5
        self.handler.scoring_kernel_cls.compute.return_value = mock_result
        
        # Mock features
        self.features = {
            "price": "100.0",
            "atr": 1.0,
            "obi": 0.0
        }
        
    def test_process_decision_no_crash(self):
        """Test that _process_decision does not raise AttributeError when entry_plan is None."""
        cmd = {
            "symbol": "BTCUSDT",
            "features": self.features,
            "warmup": {"full_ready": True},
            "bar_close_ts": 1234567890
        }
        
        # This call should NOT raise AttributeError
        try:
            self.handler._process_decision("BTCUSDT", cmd)
        except AttributeError as e:
            self.fail(f"AuroraHandler crashed with AttributeError: {e}")
        except Exception as e:
            self.fail(f"AuroraHandler crashed with unexpected exception: {e}")
            
        # Optional: verify that it produced a BLOCK event for EntryPlanMissing
        # This would require mocking emit_fn and checking calls, but simply not crashing is the primary goal.

if __name__ == "__main__":
    unittest.main()
