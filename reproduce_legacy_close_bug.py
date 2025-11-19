
import sys
import os
import logging
from decimal import Decimal
from unittest.mock import MagicMock

# Add workspace root to path
sys.path.append(r"c:\Users\user\Music\Phenix")

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.manage_config import ExecutionManageConfig, BracketsMetaConfig, AggregatedOcoConfig

# Mock config
def mock_config():
    cfg = MagicMock()
    # Legacy mode: aggregated_oco enabled = False
    cfg.brackets.aggregated_oco.enabled = False
    cfg.brackets.enable = True
    return cfg

def test_legacy_close_bug():
    print("--- Starting Reproduction Test ---")
    
    # 1. Setup FSM
    fsm = ManageFlowFSM(symbol="SOLUSDT")
    # Inject mock config
    fsm._manage_cfg_cache = mock_config()
    fsm._auto_manage_enabled = True
    
    # Mock dependencies
    fsm.order_guardian = MagicMock()
    fsm.price_service = MagicMock()
    
    # 2. Simulate Entry Fill
    print("\n[1] Simulating Entry Fill (10 SOL @ 100.0)")
    entry_msg = Message(
        op="EVT",
        verb="FILL",
        src="adapter",
        dst="execution_position",
        pld={
            "symbol": "SOLUSDT",
            "side": "BUY",
            "qty": "10.0",
            "price": "100.0",
            "orderId": "entry_1",
            "reduceOnly": False
        }
    )
    
    # Handle entry
    res = fsm.handle(entry_msg)
    print(f"State after entry: {fsm.state}")
    
    if fsm.state == ManageState.BRACKETS_PENDING:
        print("Entry handled correctly. Transitioning to TRACKING manually for simulation.")
        fsm.state = ManageState.TRACKING
        fsm.position_qty = Decimal("10.0")
        fsm.position_entry_price = Decimal("100.0")
        fsm.position_side = "BUY"
    else:
        print("FAILED: Did not transition to BRACKETS_PENDING on entry.")
        # Force it for the test
        fsm.state = ManageState.TRACKING
        fsm.position_qty = Decimal("10.0")
        fsm.position_entry_price = Decimal("100.0")
        fsm.position_side = "BUY"

    # 3. Simulate Close Fill (Market Sell 10 SOL)
    # This represents a CloseFlowFSM execution or manual close
    print("\n[2] Simulating Close Fill (Sell 10 SOL @ 101.0)")
    close_msg = Message(
        op="EVT",
        verb="FILL",
        src="adapter",
        dst="execution_position",
        pld={
            "symbol": "SOLUSDT",
            "side": "SELL",
            "qty": "10.0",
            "price": "101.0",
            "orderId": "close_1",
            "reduceOnly": True, # Close orders usually have reduceOnly
            "type": "MARKET"
        }
    )
    
    # Handle close
    fsm.handle(close_msg)
    print(f"State after close: {fsm.state}")
    print(f"Position Qty: {fsm.position_qty}")
    
    if fsm.state != ManageState.FLAT:
        print("BUG REPRODUCED: State is not FLAT after full close in legacy mode.")
    else:
        print("State is FLAT. Bug not reproduced here.")
        return

    # 4. Simulate NEW Entry Fill
    print("\n[3] Simulating NEW Entry Fill (5 SOL @ 102.0)")
    new_entry_msg = Message(
        op="EVT",
        verb="FILL",
        src="adapter",
        dst="execution_position",
        pld={
            "symbol": "SOLUSDT",
            "side": "BUY",
            "qty": "5.0",
            "price": "102.0",
            "orderId": "entry_2",
            "reduceOnly": False
        }
    )
    
    res = fsm.handle(new_entry_msg)
    print(f"State after new entry: {fsm.state}")
    
    if fsm.state == ManageState.BRACKETS_PENDING:
        print("New entry handled correctly (Brackets placed).")
    else:
        print("BUG CONFIRMED: New entry ignored because FSM was stuck in TRACKING.")

if __name__ == "__main__":
    test_legacy_close_bug()
