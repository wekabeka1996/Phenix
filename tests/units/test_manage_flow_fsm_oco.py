"""
Tests for OCO (One-Cancels-Other) emulation in ManageFlowFSM.

The system places 3 orders:
1. MARKET entry order
2. STOP_MARKET SL bracket
3. TAKE_PROFIT_MARKET TP bracket

When one bracket (SL or TP) fills, the other MUST be cancelled.
This test suite verifies this critical logic.
"""

from vfoundation.core.protocol import Message
import time
from decimal import Decimal

import importlib.util
import os

# Load module directly to avoid ambiguous imports
spec = importlib.util.spec_from_file_location(
    "apps.reference.domains.execution_position.fsm_manage",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "apps",
        "reference",
        "domains",
        "execution_position",
        "fsm_manage.py",
    ),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ManageFlowFSM = mod.ManageFlowFSM
ManageState = mod.ManageState


def make_msg(op="EVT", verb="FILL", rid="r1", symbol="SOLUSDT", pld=None):
    """Helper to create test messages."""
    # Construct the payload - merge pld dict if provided
    if pld is None:
        pld = {}

    payload = {"symbol": symbol}
    if isinstance(pld, dict):
        payload.update(pld)

    # Return Message with the full payload
    return Message(
        op=op,
        verb=verb,
        src="test",
        dst="manage",
        rid=rid,
        pld=payload,
    )


def test_oco_emulation_disabled_by_default():
    """
    Test 1: OCO emulation is disabled by default.
    When oco_emulation=false, filling one bracket does NOT cancel the other.
    """
    fsm = ManageFlowFSM(config={"brackets": {"oco_emulation": False}})

    # Setup position with both brackets
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("50000")
    fsm.position_side = "BUY"
    fsm.sl_order_id = "sl_order_123"
    fsm.tp_order_id = "tp_order_456"
    fsm.state = ManageState.BRACKETS_PLACED

    # TP fills
    tp_fill_msg = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"orderId": "tp_order_456", "price": "50500"},
    )

    print(
        f"\n[TEST DEBUG] Before: tp_order_id={fsm.tp_order_id}, sl_order_id={fsm.sl_order_id}")
    print(f"[TEST DEBUG] Message pld: {tp_fill_msg.pld}")
    print(f"[TEST DEBUG] order_id from msg: {tp_fill_msg.pld.get('orderId')}")
    print(f"[TEST DEBUG] Calling _handle_bracket_fill...")

    result = fsm._handle_bracket_fill(tp_fill_msg)

    print(
        f"[TEST DEBUG] After: tp_order_id={fsm.tp_order_id}, sl_order_id={fsm.sl_order_id}")
    print(f"[TEST DEBUG] Result: {result}\n")

    # OCO disabled: should NOT emit cancel order
    assert result is None, "OCO disabled - should NOT cancel SL when TP fills"
    # After TP fills, tp_order_id is cleared locally
    assert fsm.tp_order_id is None, "TP order cleared after fill"
    assert fsm.sl_order_id == "sl_order_123", "SL still tracked (NOT cancelled)"


def test_oco_emulation_tp_filled_cancels_sl():
    """
    Test 2: When TP fills, SL is cancelled (OCO emulation).

    Scenario:
    - Position: 1.0 BTC LONG @ 50000
    - SL: 49750 (STOP_MARKET SELL)
    - TP: 50500 (TAKE_PROFIT_MARKET SELL)
    - TP fills @ 50500
    - Expected: SL order (ID: sl_order_123) should be CANCELLED
    """
    fsm = ManageFlowFSM(
        config={
            "brackets": {
                "oco_emulation": True,  # ENABLED
                "enable": True,
                "sl": {"fixed_bps": 50},
                "tp": {"fixed_bps": 100},
            }
        }
    )

    # Setup: Position with both brackets active
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("50000")
    fsm.position_side = "BUY"
    fsm.sl_order_id = "sl_order_123"  # SL that should be cancelled
    fsm.tp_order_id = "tp_order_456"  # TP that just filled
    fsm.sl_price = Decimal("49750")
    fsm.tp_price = Decimal("50500")
    fsm.state = ManageState.BRACKETS_PLACED

    # TP execution: price hits 50500, TP LIMIT fills
    tp_fill_msg = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        rid="r1",
        pld={"orderId": "tp_order_456", "price": "50500", "qty": "1.0"},
    )

    result = fsm._handle_bracket_fill(tp_fill_msg)

    # Should emit DEC:CANCEL_ORDER for the SL
    assert result is not None, "Should emit cancel decision when TP fills"
    assert result.op == "DEC"
    assert result.verb == "CANCEL_ORDER"
    assert result.pld["orderId"] == "sl_order_123"
    assert "OCO_TP_filled" in result.why

    # Verify tracking cleared
    assert fsm.tp_order_id is None


def test_oco_emulation_sl_filled_cancels_tp():
    """
    Test 3: When SL fills, TP is cancelled (OCO emulation).

    Scenario:
    - Position: 1.0 BTC LONG @ 50000
    - SL: 49750 (STOP_MARKET SELL)
    - TP: 50500 (TAKE_PROFIT_MARKET SELL)
    - Price drops to 49750, SL executes
    - Expected: TP order (ID: tp_order_456) should be CANCELLED
    """
    fsm = ManageFlowFSM(
        config={
            "brackets": {
                "oco_emulation": True,  # ENABLED
                "enable": True,
                "sl": {"fixed_bps": 50},
                "tp": {"fixed_bps": 100},
            }
        }
    )

    # Setup: Position with both brackets active
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("50000")
    fsm.position_side = "BUY"
    fsm.sl_order_id = "sl_order_123"  # SL that just filled
    fsm.tp_order_id = "tp_order_456"  # TP that should be cancelled
    fsm.sl_price = Decimal("49750")
    fsm.tp_price = Decimal("50500")
    fsm.state = ManageState.BRACKETS_PLACED

    # SL execution: price hits 49750, SL STOP_MARKET fills
    sl_fill_msg = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        rid="r1",
        pld={"orderId": "sl_order_123", "price": "49750", "qty": "1.0"},
    )

    result = fsm._handle_bracket_fill(sl_fill_msg)

    # Should emit DEC:CANCEL_ORDER for the TP
    assert result is not None, "Should emit cancel decision when SL fills"
    assert result.op == "DEC"
    assert result.verb == "CANCEL_ORDER"
    assert result.pld["orderId"] == "tp_order_456"
    assert "OCO_SL_filled" in result.why

    # Verify tracking cleared
    assert fsm.sl_order_id is None


def test_oco_non_bracket_order_ignored():
    """
    Test 4: Non-bracket orders do not trigger OCO logic.

    If some other order fills, OCO should not react.
    """
    fsm = ManageFlowFSM(
        config={
            "brackets": {
                "oco_emulation": True,
                "enable": True,
            }
        }
    )

    fsm.position_qty = Decimal("1.0")
    fsm.position_side = "BUY"
    fsm.sl_order_id = "sl_order_123"
    fsm.tp_order_id = "tp_order_456"

    # Some unrelated order fills
    other_fill = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"orderId": "other_order_789", "price": "50000"},
    )

    result = fsm._handle_bracket_fill(other_fill)

    # Should ignore non-bracket orders
    assert result is None
    assert fsm.sl_order_id == "sl_order_123"  # Unchanged
    assert fsm.tp_order_id == "tp_order_456"  # Unchanged


def test_oco_no_brackets_placed_yet():
    """
    Test 5: If brackets not yet placed, no OCO action.

    Edge case: message arrives before brackets placed.
    """
    fsm = ManageFlowFSM(config={"brackets": {"oco_emulation": True}})

    # No brackets placed yet
    fsm.sl_order_id = None
    fsm.tp_order_id = None

    fill_msg = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"orderId": "unknown", "price": "50000"},
    )

    result = fsm._handle_bracket_fill(fill_msg)
    assert result is None, "No OCO action if brackets not placed"


def test_oco_partial_bracket_state():
    """
    Test 6: Only SL placed, TP not yet placed.

    If only SL is tracked, filling a non-existent TP shouldn't crash.
    """
    fsm = ManageFlowFSM(config={"brackets": {"oco_emulation": True}})

    fsm.sl_order_id = "sl_order_123"
    fsm.tp_order_id = None  # TP not yet placed

    # Message claiming TP filled (even though it wasn't placed)
    msg = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"orderId": "tp_order_456", "price": "50000"},
    )

    result = fsm._handle_bracket_fill(msg)
    # Should not crash; no TP to track, so no cancel
    assert result is None


def test_oco_integration_scenario():
    """
    Test 7: Full integration - place brackets, then fill one.

    This simulates the real trading flow:
    1. Entry fills (MARKET)
    2. Brackets placed (SL + TP)
    3. Price moves to TP
    4. TP fills
    5. SL must be cancelled
    """
    cfg = {
        "execution": {"manage": {"auto": True}},
        "brackets": {
            "enable": True,
            "oco_emulation": True,
            "sl": {"fixed_bps": 50},
            "tp": {"fixed_bps": 100},
        },
    }
    fsm = ManageFlowFSM(config=cfg)

    # Step 1: Position opens (after FILL of market entry)
    entry_msg = make_msg(
        op="EVT",
        verb="FILL",
        pld={
            "qty": "1.0",
            "price": "50000",
            "side": "BUY",
        },
    )

    # Simulate position being set up from the fill
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("50000")
    fsm.position_side = "BUY"
    fsm.position_open_ts = time.time()

    # Step 2: Place brackets (would be done by handle)
    # Manually set as if brackets placed
    fsm.state = ManageState.BRACKETS_PLACED
    fsm.sl_order_id = "sl_50000_sl"
    fsm.tp_order_id = "tp_50000_tp"
    fsm.sl_price = Decimal("49750")
    fsm.tp_price = Decimal("50500")

    # Step 3: Price moves up, TP fills
    tp_fill = make_msg(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"orderId": "tp_50000_tp", "price": "50500", "qty": "1.0"},
    )

    # Step 4: Process TP fill
    cancel_decision = fsm._handle_bracket_fill(tp_fill)

    # Verify OCO worked: TP filled, SL cancelled
    assert cancel_decision is not None
    assert cancel_decision.op == "DEC"
    assert cancel_decision.verb == "CANCEL_ORDER"
    assert cancel_decision.pld["orderId"] == "sl_50000_sl"
    assert "OCO_TP_filled" in cancel_decision.why


if __name__ == "__main__":
    # Run tests
    test_oco_emulation_disabled_by_default()
    print("✓ Test 1 passed: OCO disabled by default")

    test_oco_emulation_tp_filled_cancels_sl()
    print("✓ Test 2 passed: TP filled → SL cancelled")

    test_oco_emulation_sl_filled_cancels_tp()
    print("✓ Test 3 passed: SL filled → TP cancelled")

    test_oco_non_bracket_order_ignored()
    print("✓ Test 4 passed: Non-bracket orders ignored")

    test_oco_no_brackets_placed_yet()
    print("✓ Test 5 passed: No brackets = no OCO")

    test_oco_partial_bracket_state()
    print("✓ Test 6 passed: Partial bracket state")

    test_oco_integration_scenario()
    print("✓ Test 7 passed: Integration scenario")

    print("\n✅ All OCO tests passed!")
