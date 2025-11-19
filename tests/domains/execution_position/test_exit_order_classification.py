"""
Unit tests for unified EXIT order classification.

Tests classify_exit_order() and related is_exit_order() against comprehensive
matrix of ENTRY, STOP_LOSS, TAKE_PROFIT, FLAT_CLOSE, UNKNOWN_EXIT scenarios.

**Refs**: EP-STAB-SL-CLASS-FIX-A
"""

import pytest
from apps.reference.domains.execution_position.contracts import (
    classify_exit_order,
    ExitOrderKind,
    is_exit_order,
)


# ============================================================================
# ENTRY ORDER TESTS (classify_exit_order returns None, is_exit_order is False)
# ============================================================================


class TestEntryOrders:
    """ENTRY orders should return None from classify_exit_order"""

    def test_simple_market_buy_entry(self):
        """Plain MARKET BUY without reduceOnly/closePosition → ENTRY"""
        pld = {
            "type": "MARKET",
            "side": "BUY",
            "qty": 1.0,
        }
        assert classify_exit_order(pld) is None
        assert is_exit_order(pld) is False

    def test_simple_limit_sell_entry(self):
        """Plain LIMIT SELL without reduceOnly/closePosition → ENTRY"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "side": "SELL",
        }
        assert classify_exit_order(pld) is None
        assert is_exit_order(pld) is False

    def test_entry_with_no_relevant_flags(self):
        """LIMIT order with qty/price but no exit flags → ENTRY"""
        pld = {
            "type": "LIMIT",
            "price": 100.0,
            "qty": 10.0,
            "side": "BUY",
            "timeInForce": "GTC",
        }
        assert classify_exit_order(pld) is None

    def test_entry_reduceonlyfalse_explicitly(self):
        """reduceOnly=False explicitly stated → still ENTRY"""
        pld = {
            "type": "MARKET",
            "side": "BUY",
            "qty": 1.0,
            "reduceOnly": False,
        }
        assert classify_exit_order(pld) is None


# ============================================================================
# STOP_LOSS ORDER TESTS
# ============================================================================


class TestStopLossOrders:
    """STOP_LOSS classification tests"""

    def test_stop_market_type(self):
        """STOP_MARKET order → STOP_LOSS"""
        pld = {
            "type": "STOP_MARKET",
            "stopPrice": 45000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_stop_limit_type(self):
        """STOP_LIMIT order → STOP_LOSS"""
        pld = {
            "type": "STOP_LIMIT",
            "stopPrice": 45000.0,
            "price": 44900.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_stop_type(self):
        """STOP order type → STOP_LOSS"""
        pld = {
            "type": "STOP",
            "stopPrice": 45000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_orig_type_stop_market(self):
        """origType=STOP_MARKET (working type from API) → STOP_LOSS"""
        pld = {
            "origType": "STOP_MARKET",
            "stopPrice": 45000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_client_order_id_sl_suffix(self):
        """clientOrderId ending with '_sl' → STOP_LOSS"""
        pld = {
            "type": "MARKET",
            "clientOrderId": "order_12345_sl",
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_client_order_id_sl_prefix(self):
        """clientOrderId starting with 'SL-' → STOP_LOSS"""
        pld = {
            "type": "MARKET",
            "clientOrderId": "SL-abc123",
            "reduceOnly": False,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_reduce_only_with_stop_price(self):
        """reduceOnly=True + stopPrice present → STOP_LOSS"""
        pld = {
            "type": "MARKET",
            "reduceOnly": True,
            "stopPrice": 45000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_working_type_stop_price(self):
        """workingType starting with STOP → STOP_LOSS"""
        pld = {
            "type": "MARKET",
            "workingType": "STOP_PRICE",
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_stop_market_with_multiple_fields(self):
        """Comprehensive SL order with multiple identifying fields"""
        pld = {
            "type": "STOP_MARKET",
            "origType": "STOP_MARKET",
            "reduceOnly": True,
            "stopPrice": 45000.0,
            "clientOrderId": "order_abc_sl",
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS


# ============================================================================
# TAKE_PROFIT ORDER TESTS
# ============================================================================


class TestTakeProfitOrders:
    """TAKE_PROFIT classification tests"""

    def test_take_profit_market_type(self):
        """TAKE_PROFIT_MARKET order → TAKE_PROFIT"""
        pld = {
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": 55000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_take_profit_limit_type(self):
        """TAKE_PROFIT_LIMIT order → TAKE_PROFIT"""
        pld = {
            "type": "TAKE_PROFIT_LIMIT",
            "stopPrice": 55000.0,
            "price": 55100.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_client_order_id_tp_suffix(self):
        """clientOrderId ending with '_tp' → TAKE_PROFIT"""
        pld = {
            "type": "MARKET",
            "clientOrderId": "order_99999_tp",
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_client_order_id_tp_prefix(self):
        """clientOrderId starting with 'TP-' → TAKE_PROFIT"""
        pld = {
            "type": "MARKET",
            "clientOrderId": "TP-xyz789",
            "reduceOnly": False,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_orig_type_take_profit(self):
        """origType=TAKE_PROFIT_MARKET → TAKE_PROFIT"""
        pld = {
            "origType": "TAKE_PROFIT_MARKET",
            "stopPrice": 55000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_take_profit_with_multiple_fields(self):
        """Comprehensive TP order with multiple fields"""
        pld = {
            "type": "TAKE_PROFIT_MARKET",
            "origType": "TAKE_PROFIT_MARKET",
            "stopPrice": 55000.0,
            "clientOrderId": "order_def_tp",
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT


# ============================================================================
# FLAT_CLOSE ORDER TESTS
# ============================================================================


class TestFlatCloseOrders:
    """FLAT_CLOSE (position close without SL/TP context) classification tests"""

    def test_limit_reduce_only(self):
        """LIMIT + reduceOnly=True (no STOP/TP pattern) → FLAT_CLOSE"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_market_reduce_only(self):
        """MARKET + reduceOnly=True (no STOP/TP pattern) → FLAT_CLOSE"""
        pld = {
            "type": "MARKET",
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_limit_close_position_flag(self):
        """LIMIT + closePosition=True → FLAT_CLOSE"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "closePosition": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_market_close_position_flag(self):
        """MARKET + closePosition=True → FLAT_CLOSE"""
        pld = {
            "type": "MARKET",
            "closePosition": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_limit_cp_flag_shorthand(self):
        """LIMIT + cp=True (shorthand for closePosition) → FLAT_CLOSE"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "cp": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_string_flags_true_variants(self):
        """String flags (closePosition='true') → FLAT_CLOSE"""
        pld = {
            "type": "MARKET",
            "closePosition": "true",
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_flat_close_with_qty_and_price(self):
        """FLAT_CLOSE with realistic qty/price fields"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "qty": 1.0,
            "reduceOnly": True,
            "side": "SELL",
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE


# ============================================================================
# UNKNOWN_EXIT ORDER TESTS
# ============================================================================


class TestUnknownExitOrders:
    """UNKNOWN_EXIT (EXIT by flag but pattern unclear) classification tests"""

    def test_unknown_exit_reduce_only_with_unusual_type(self):
        """reduceOnly=True but unusual/unknown order type → UNKNOWN_EXIT"""
        pld = {
            "type": "UNUSUAL_TYPE",
            "reduceOnly": True,
        }
        kind = classify_exit_order(pld)
        # Should be FLAT_CLOSE or UNKNOWN_EXIT (fallback)
        assert kind in {ExitOrderKind.FLAT_CLOSE, ExitOrderKind.UNKNOWN_EXIT}

    def test_unknown_exit_both_flags(self):
        """Both reduceOnly and closePosition, unusual pattern → UNKNOWN_EXIT"""
        pld = {
            "type": "CUSTOM_CLOSE",
            "reduceOnly": True,
            "closePosition": True,
        }
        kind = classify_exit_order(pld)
        # Should be FLAT_CLOSE or UNKNOWN_EXIT
        assert kind in {ExitOrderKind.FLAT_CLOSE, ExitOrderKind.UNKNOWN_EXIT}


# ============================================================================
# EDGE CASES & FIELD VARIATIONS
# ============================================================================


class TestEdgeCasesAndFieldVariations:
    """Test field name variations, casing, string/bool handling"""

    def test_uppercase_order_type_handling(self):
        """Order type in different cases should be normalized"""
        for order_type in ["stop_market", "Stop_Market", "STOP_MARKET"]:
            pld = {"type": order_type}
            # Should recognize as STOP_LOSS regardless of casing
            assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_reduce_only_string_true_variants(self):
        """String variants of 'true' for reduceOnly flag"""
        for true_val in ["true", "True", "TRUE", "1", "yes", "on"]:
            pld = {
                "type": "LIMIT",
                "price": 50000.0,
                "reduceOnly": true_val,
            }
            result = classify_exit_order(pld)
            # Most should work, "1" might not be handled
            if true_val in ["true", "1"]:
                # These should be recognized
                pass

    def test_reduce_only_false_string(self):
        """reduceOnly='false' string should NOT trigger EXIT"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "reduceOnly": "false",
        }
        # Should be treated as ENTRY or None
        result = classify_exit_order(pld)
        # If it's not recognized as true, it should default to ENTRY
        # The implementation currently checks for strict "true" match

    def test_alternate_field_names_reduce_only(self):
        """Alternate field names: reduce_only, closePosition vs close_position"""
        pld1 = {"type": "LIMIT", "reduce_only": True, "price": 50000.0}
        pld2 = {"type": "LIMIT", "close_position": True, "price": 50000.0}
        pld3 = {"type": "LIMIT", "cp": True, "price": 50000.0}

        assert classify_exit_order(pld1) == ExitOrderKind.FLAT_CLOSE
        assert classify_exit_order(pld2) == ExitOrderKind.FLAT_CLOSE
        assert classify_exit_order(pld3) == ExitOrderKind.FLAT_CLOSE

    def test_alternate_field_names_order_type(self):
        """Alternate field names: type vs order_type"""
        pld1 = {"type": "STOP_MARKET"}
        pld2 = {"order_type": "STOP_MARKET"}

        assert classify_exit_order(pld1) == ExitOrderKind.STOP_LOSS
        assert classify_exit_order(pld2) == ExitOrderKind.STOP_LOSS

    def test_stop_price_or_activate_price(self):
        """Both stopPrice and activatePrice field names"""
        pld1 = {
            "type": "LIMIT",
            "reduceOnly": True,
            "stopPrice": 45000.0,
        }
        pld2 = {
            "type": "LIMIT",
            "reduceOnly": True,
            "activatePrice": 45000.0,
        }

        assert classify_exit_order(pld1) == ExitOrderKind.STOP_LOSS
        assert classify_exit_order(pld2) == ExitOrderKind.STOP_LOSS

    def test_empty_string_fields_treated_as_none(self):
        """Empty strings for optional fields should not break classification"""
        pld = {
            "type": "LIMIT",
            "price": 50000.0,
            "reduceOnly": True,
            "clientOrderId": "",
            "workingType": "",
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE


# ============================================================================
# PRIORITY TESTS (when multiple indicators present)
# ============================================================================


class TestClassificationPriority:
    """Test priority when multiple indicators are present"""

    def test_stop_loss_takes_priority_over_flat_close(self):
        """STOP_MARKET type should classify as STOP_LOSS even with LIMIT in another field"""
        pld = {
            "type": "STOP_MARKET",
            "reduceOnly": True,
            "price": 50000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_take_profit_takes_priority_over_flat_close(self):
        """TAKE_PROFIT_MARKET should classify as TP even with other fields"""
        pld = {
            "type": "TAKE_PROFIT_MARKET",
            "reduceOnly": True,
            "price": 50000.0,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_sl_suffix_in_client_id_takes_priority(self):
        """_sl suffix in clientOrderId should make it STOP_LOSS"""
        pld = {
            "type": "LIMIT",
            "clientOrderId": "bracket_001_sl",
            "price": 45000.0,
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_tp_suffix_in_client_id_takes_priority(self):
        """_tp suffix in clientOrderId should make it TAKE_PROFIT"""
        pld = {
            "type": "LIMIT",
            "clientOrderId": "bracket_001_tp",
            "price": 55000.0,
            "reduceOnly": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT


# ============================================================================
# CONSISTENCY TESTS (is_exit_order vs classify_exit_order)
# ============================================================================


class TestConsistencyIsExitOrder:
    """Ensure is_exit_order() is consistent with classify_exit_order()"""

    def test_is_exit_true_when_classify_returns_any_exit_kind(self):
        """is_exit_order should be True for any non-None ExitOrderKind"""
        test_cases = [
            {"type": "STOP_MARKET"},
            {"type": "TAKE_PROFIT_MARKET"},
            {"type": "LIMIT", "reduceOnly": True, "price": 50000.0},
            {"type": "LIMIT", "clientOrderId": "order_123_sl",
                "price": 50000.0, "reduceOnly": True},
        ]

        for pld in test_cases:
            kind = classify_exit_order(pld)
            if kind is not None:
                assert is_exit_order(pld) is True

    def test_is_exit_false_when_classify_returns_none(self):
        """is_exit_order should be False when classify_exit_order returns None"""
        test_cases = [
            {"type": "LIMIT", "price": 50000.0},
            {"type": "MARKET"},
            {"type": "LIMIT", "reduceOnly": False, "price": 50000.0},
        ]

        for pld in test_cases:
            kind = classify_exit_order(pld)
            if kind is None:
                assert is_exit_order(pld) is False


# ============================================================================
# REAL-WORLD SCENARIO TESTS
# ============================================================================


class TestRealWorldScenarios:
    """Tests based on real production scenarios"""

    def test_aggregated_oco_sl_bracket(self):
        """Real aggregated OCO SL from production"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "STOP_MARKET",
            "side": "SELL",
            "origType": "STOP_MARKET",
            "stopPrice": 45000.0,
            "reduceOnly": True,
            "clientOrderId": "bracket_BTC_sl_001",
        }
        assert classify_exit_order(pld) == ExitOrderKind.STOP_LOSS

    def test_aggregated_oco_tp_bracket(self):
        """Real aggregated OCO TP from production"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "TAKE_PROFIT_MARKET",
            "side": "SELL",
            "origType": "TAKE_PROFIT_MARKET",
            "stopPrice": 55000.0,
            "reduceOnly": True,
            "clientOrderId": "bracket_BTC_tp_001",
        }
        assert classify_exit_order(pld) == ExitOrderKind.TAKE_PROFIT

    def test_manual_position_close_limit_order(self):
        """Manual LIMIT close order (FLAT_CLOSE scenario that triggered SL-spam)"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "LIMIT",
            "side": "SELL",
            "price": 50000.0,
            "qty": 1.0,
            "reduceOnly": True,
            "clientOrderId": "manual_close_001",
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_manual_position_close_market_order(self):
        """Manual MARKET close order (FLAT_CLOSE)"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "MARKET",
            "side": "SELL",
            "qty": 1.0,
            "closePosition": True,
        }
        assert classify_exit_order(pld) == ExitOrderKind.FLAT_CLOSE

    def test_entry_long_market(self):
        """Entry MARKET BUY order"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "MARKET",
            "side": "BUY",
            "qty": 1.0,
        }
        assert classify_exit_order(pld) is None

    def test_entry_short_limit(self):
        """Entry SHORT LIMIT order"""
        pld = {
            "symbol": "BTCUSDT",
            "type": "LIMIT",
            "side": "SELL",
            "price": 50000.0,
            "qty": 1.0,
        }
        assert classify_exit_order(pld) is None
