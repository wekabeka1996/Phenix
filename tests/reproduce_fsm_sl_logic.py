
import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM

class TestFSMSLLogic(unittest.TestCase):
    def test_calculate_bracket_prices_ignores_intent(self):
        # Mock config
        mock_config = MagicMock()
        mock_config.trading.instruments = {}
        mock_config.trading.execution.manage.brackets.sl.fixed_bps = 50  # 0.5% default
        
        # Instantiate FSM
        fsm = ManageFlowFSM(None, mock_config, "DOGEUSDT")
        
        # Setup mock state
        fsm.position_entry_price = Decimal("100.0")
        fsm.position_side = "BUY"
        fsm.symbol = "DOGEUSDT"
        
        # Scenario: Intent provided a specific SL (e.g. 90.0, which is 10% away)
        # We manually set it as if the intent handler did it
        intent_sl = Decimal("90.0")
        fsm.sl_price = intent_sl 
        
        print(f"\n[Test] Intent SL set to: {fsm.sl_price}")
        
        # Run calculation
        calc_sl, calc_tp1, calc_tp2 = fsm._calculate_bracket_prices()
        
        print(f"[Test] Calculated SL: {calc_sl}")
        
        # Expected behavior for FIXED logic: matches intent (90.0)
        # Current BUG behavior: matches config default (99.5)
        
        if calc_sl == intent_sl:
            print("SUCCESS: FSM respected the Intent SL.")
        else:
            print(f"FAILURE: FSM overwrote Intent SL with {calc_sl} (likely default config).")
            # Calculate bps
            diff = (Decimal("100.0") - calc_sl) / Decimal("100.0") * 10000
            print(f"       Difference BPS: {diff}")

if __name__ == "__main__":
    unittest.main()
