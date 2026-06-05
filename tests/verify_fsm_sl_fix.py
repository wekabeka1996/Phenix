
import sys
import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, Mock

# --- MOCKING DEPENDENCIES BEFORE IMPORT ---
# Mock vfoundation and submodules
mock_vfoundation = MagicMock()
mock_protocol = MagicMock()
mock_protocol.Message = Mock
mock_vfoundation.core.protocol = mock_protocol
sys.modules["vfoundation"] = mock_vfoundation
sys.modules["vfoundation.core"] = mock_vfoundation.core
sys.modules["vfoundation.core.protocol"] = mock_protocol

# Mock telemetry
mock_telemetry = MagicMock()
sys.modules["apps.reference.telemetry"] = mock_telemetry
sys.modules["apps.reference.telemetry.order_logger"] = mock_telemetry

# Mock config models
sys.modules["apps.reference.config_models"] = MagicMock()

# Setup path
sys.path.append(os.getcwd())

# Now import the target module
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM

class TestFSMFix(unittest.TestCase):
    def test_intent_injection_overrides_config(self):
        # Mock config with BAD default (e.g., 50bps)
        mock_config = MagicMock()
        mock_config.trading.instruments = {}
        # Simulate brackets.sl.fixed_bps path
        mock_config.trading.execution.manage.brackets.sl.fixed_bps = 50
        
        # Instantiate FSM
        fsm = ManageFlowFSM(mock_config)
        fsm.symbol = "DOGEUSDT"
        
        # Set state
        fsm.position_entry_price = Decimal("100.0")
        fsm.position_side = "BUY"
        
        # Mock instrument config return to simulate "config not found" or "default"
        fsm._get_aurora_instr_cfg = MagicMock(return_value=None)
        
        # Scenario: Strategy calculated 10% SL (Price 90.0)
        intent_sl = Decimal("90.0")
        intent_tp = Decimal("110.0")
        
        print("\n[Test] Injecting Intent Prices...")
        # CALL THE NEW METHOD
        fsm.set_intent_prices(intent_sl, intent_tp)
        
        # Verify stored properly
        self.assertEqual(fsm._intent_sl_price, intent_sl, "Intent SL not stored")
        
        # Run calculation
        print("[Test] Calculating Bracket Prices...")
        calc_sl, calc_tp1, calc_tp2 = fsm._calculate_bracket_prices()
        
        print(f"[Result] Calculated SL: {calc_sl}")
        print(f"[Result] Expected SL:   {intent_sl}")
        
        # Verify override
        self.assertEqual(calc_sl, intent_sl, "FSM failed to use injected Intent SL!")
        self.assertIsNone(fsm._intent_sl_price, "Intent SL should be consumed/cleared")
        
        print("SUCCESS: FSM respected the injected intent prices.")

if __name__ == "__main__":
    try:
        unittest.main()
    except SystemExit as e:
        if e.code != 0:
            raise
