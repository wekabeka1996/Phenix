#!/usr/bin/env python
"""Quick test of Phase 1 implementations."""

from decimal import Decimal
from apps.reference.domains.execution_position.contracts import (
    TPSLValidationRules,
    BracketOrderPayload,
    WorkingType,
    OrderType,
)


def test_validation_rules():
    """Test TPSLValidationRules correctness."""
    print("=" * 60)
    print("TESTING TPSLValidationRules")
    print("=" * 60)

    # Test 1: LONG TP (should be above mark)
    result, reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side="LONG",
        current_mark=Decimal("100"),
        stop_price=Decimal("105"),
        is_take_profit=True,
    )
    print(f"✅ Test 1 - LONG TP=105 > mark=100: {result}")
    assert result is True, f"Expected True, got {result}"

    # Test 2: LONG TP (should fail - below mark)
    result, reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side="LONG",
        current_mark=Decimal("100"),
        stop_price=Decimal("95"),
        is_take_profit=True,
    )
    print(f"✅ Test 2 - LONG TP=95 < mark=100 (should fail): {result}")
    assert result is False, f"Expected False, got {result}"

    # Test 3: LONG SL (should be below mark)
    result, reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side="LONG",
        current_mark=Decimal("100"),
        stop_price=Decimal("95"),
        is_take_profit=False,
    )
    print(f"✅ Test 3 - LONG SL=95 < mark=100: {result}")
    assert result is True, f"Expected True, got {result}"

    # Test 4: SHORT TP (should be below mark)
    result, reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side="SHORT",
        current_mark=Decimal("100"),
        stop_price=Decimal("95"),
        is_take_profit=True,
    )
    print(f"✅ Test 4 - SHORT TP=95 < mark=100: {result}")
    assert result is True, f"Expected True, got {result}"

    # Test 5: SHORT SL (should be above mark)
    result, reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side="SHORT",
        current_mark=Decimal("100"),
        stop_price=Decimal("105"),
        is_take_profit=False,
    )
    print(f"✅ Test 5 - SHORT SL=105 > mark=100: {result}")
    assert result is True, f"Expected True, got {result}"

    # Test 6: Offset calculation
    offset = TPSLValidationRules.add_safety_offset(
        current_price=Decimal("100"),
        tick_size=Decimal("0.01"),
        offset_bps=5,
    )
    expected = Decimal("0.05")  # 100 * 5 / 10000
    print(f"✅ Test 6 - Offset for $100 @ 5bps, tickSize=0.01: {offset}")
    assert offset == expected, f"Expected {expected}, got {offset}"

    print("\n✅ All TPSLValidationRules tests PASSED!")


def test_bracket_order_payload():
    """Test BracketOrderPayload validation."""
    print("\n" + "=" * 60)
    print("TESTING BracketOrderPayload")
    print("=" * 60)

    # Test 1: Valid TAKE_PROFIT_MARKET with closePosition (NO qty!)
    try:
        payload = BracketOrderPayload(
            symbol="ETHUSDT",
            side="BUY",
            # Will validate but ignored by Binance due to closePosition
            qty=Decimal("0.001"),
            order_type=OrderType.TAKE_PROFIT_MARKET,
            stop_price=Decimal("105"),
            close_position=True,
            working_type=WorkingType.MARK_PRICE,
            new_client_order_id="AUR-tp-001",
        )
        print(f"❌ Test 1 - Should have failed (qty with closePosition)")
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        print(
            f"✅ Test 1 - Correctly rejected qty with closePosition: {str(e)[:50]}...")

    # Test 2: Invalid - closePosition=True but has qty
    try:
        payload = BracketOrderPayload(
            symbol="ETHUSDT",
            side="BUY",
            qty=Decimal("1"),
            order_type=OrderType.TAKE_PROFIT_MARKET,
            stop_price=Decimal("105"),
            close_position=True,  # Should fail: can't have qty with closePosition
            working_type=WorkingType.MARK_PRICE,
            new_client_order_id="AUR-tp-002",
        )
        print(f"❌ Test 2 - Should have failed but didn't")
        raise AssertionError(
            "Expected ValueError for qty with closePosition=True")
    except ValueError as e:
        print(
            f"✅ Test 2 - Correctly rejected qty with closePosition=True: {str(e)[:50]}...")

    # Test 3: Invalid - closePosition=True but CONTRACT_PRICE
    try:
        payload = BracketOrderPayload(
            symbol="ETHUSDT",
            side="BUY",
            qty=None,
            order_type=OrderType.STOP_MARKET,
            stop_price=Decimal("95"),
            close_position=True,
            working_type=WorkingType.CONTRACT_PRICE,  # Should fail: needs MARK_PRICE
            new_client_order_id="AUR-sl-001",
        )
        print(f"❌ Test 3 - Should have failed but didn't")
        raise AssertionError(
            "Expected ValueError for CONTRACT_PRICE with closePosition=True")
    except ValueError as e:
        print(
            f"✅ Test 3 - Correctly rejected CONTRACT_PRICE with closePosition: {str(e)[:50]}...")

    print("\n✅ All BracketOrderPayload tests PASSED!")


def test_fsm_bracket_validation_integration():
    """Test FSM integration with bracket validation (simple mock FSM test)."""
    print("\n" + "=" * 60)
    print("TESTING FSM BRACKET VALIDATION INTEGRATION")
    print("=" * 60)

    # This is a simple mock test to verify that FSM would call validators
    # In a real test, we'd have an actual ManageFlowFSM instance

    # Test scenario: LONG position, validate SL/TP before placement
    position_side = "LONG"
    entry_price = Decimal("100")
    mark_price = Decimal("100")

    # FSM would calculate: SL = 95 (50 bps below), TP = 110 (100 bps above)
    sl_price = Decimal("95")
    tp_price = Decimal("110")

    # FSM would validate both before _emit_place_order
    is_sl_valid, sl_reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=sl_price,
        is_take_profit=False,
    )
    print(f"✅ SL validation for LONG @ {sl_price}: {is_sl_valid}")
    assert is_sl_valid, f"SL validation failed: {sl_reason}"

    is_tp_valid, tp_reason = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=tp_price,
        is_take_profit=True,
    )
    print(f"✅ TP validation for LONG @ {tp_price}: {is_tp_valid}")
    assert is_tp_valid, f"TP validation failed: {tp_reason}"

    # FSM would then apply safety offset (offset_bps=5)
    tick_size = Decimal("0.01")
    offset_bps = 5

    sl_offset = TPSLValidationRules.add_safety_offset(
        sl_price, tick_size, offset_bps)
    tp_offset = TPSLValidationRules.add_safety_offset(
        tp_price, tick_size, offset_bps)

    # For LONG: SL moves down (safer), TP moves up (safer)
    sl_price_safe = sl_price - sl_offset
    tp_price_safe = tp_price + tp_offset

    print(
        f"✅ SL offset applied: {sl_price} → {sl_price_safe} (offset={sl_offset})")
    print(
        f"✅ TP offset applied: {tp_price} → {tp_price_safe} (offset={tp_offset})")

    # Validate offset prices are still valid
    is_sl_safe_valid, _ = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=sl_price_safe,
        is_take_profit=False,
    )
    print(f"✅ SL offset price still valid: {is_sl_safe_valid}")
    assert is_sl_safe_valid, "SL offset price validation failed"

    is_tp_safe_valid, _ = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=tp_price_safe,
        is_take_profit=True,
    )
    print(f"✅ TP offset price still valid: {is_tp_safe_valid}")
    assert is_tp_safe_valid, "TP offset price validation failed"

    # Test SHORT scenario
    print("\n--- Testing SHORT position ---")
    position_side = "SHORT"
    sl_price = Decimal("105")  # Above entry for SHORT
    tp_price = Decimal("90")   # Below entry for SHORT

    is_sl_valid, _ = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=sl_price,
        is_take_profit=False,
    )
    print(f"✅ SL validation for SHORT @ {sl_price}: {is_sl_valid}")
    assert is_sl_valid, "SHORT SL validation failed"

    is_tp_valid, _ = TPSLValidationRules.validate_stop_price_for_side(
        position_side=position_side,
        current_mark=mark_price,
        stop_price=tp_price,
        is_take_profit=True,
    )
    print(f"✅ TP validation for SHORT @ {tp_price}: {is_tp_valid}")
    assert is_tp_valid, "SHORT TP validation failed"

    print("\n✅ All FSM bracket validation integration tests PASSED!")


if __name__ == "__main__":
    test_validation_rules()
    test_bracket_order_payload()
    test_fsm_bracket_validation_integration()
    print("\n" + "=" * 60)
    print("✅✅✅ PHASE 1 VALIDATION COMPLETE! ✅✅✅")
    print("=" * 60)
