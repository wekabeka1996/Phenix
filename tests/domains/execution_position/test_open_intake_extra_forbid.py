"""
Phase 2 — Ingress and Config Fail-Closed

Tests for DEF-E03 (extra="forbid") and DEF-E04 (Decimal parser for qty/price fields).

DEF-E03: Unknown fields in the order block must be rejected.
         Previously extra="ignore" silently dropped unknown money-impacting fields.

DEF-E04: Scientific notation qty (e.g. "1E-7") must be accepted.
         Previously regex ^[0-9]+(\.[0-9]+)?$ rejected valid Decimal values.
         NaN, Infinity, negative qty, empty string must be rejected.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.reference.domains.execution_position.flows.open.trade_intent_open_intake import (
    TradeIntentOpenIntake,
    TradeIntentOpenIntakeError,
    TradeIntentOpenOrder,
    parse_trade_intent_open_intake,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market_order_payload(**overrides):
    """Minimal valid MARKET open intent payload."""
    base = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order": {
            "qty": "0.01",
            "order_type": "MARKET",
        },
    }
    if "order" in overrides and isinstance(overrides["order"], dict):
        merged_order = {**base["order"], **overrides.pop("order")}
        overrides["order"] = merged_order
    base.update(overrides)
    return base


def _limit_order_payload(**overrides):
    """Minimal valid LIMIT open intent payload."""
    base = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "valid_for_ms": 5000,
        "order": {
            "qty": "0.01",
            "order_type": "LIMIT",
            "price": "50000.00",
            "tif": "GTC",
        },
    }
    if "order" in overrides and isinstance(overrides["order"], dict):
        merged_order = {**base["order"], **overrides.pop("order")}
        overrides["order"] = merged_order
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# DEF-E03: extra="forbid" on TradeIntentOpenOrder
# ---------------------------------------------------------------------------

class TestExtraForbidOnOrderBlock:
    """Unknown fields in the order block must be rejected (DEF-E03)."""

    def test_known_fields_pass(self):
        """Baseline: valid order with known fields succeeds."""
        result = parse_trade_intent_open_intake(_market_order_payload())
        assert result.order.qty == "0.01"

    def test_unknown_order_field_raises(self):
        """DEF-E03 regression: unknown order field must be rejected, not silently ignored."""
        payload = _market_order_payload(
            order={"unknown_money_field": "999999.99"}
        )
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(payload)

    def test_typo_in_order_key_raises(self):
        """Typo 'qty_usd' instead of 'qty' must not silently pass."""
        payload = _market_order_payload(
            order={"qty": "0.01", "qty_usd": "5000.00", "order_type": "MARKET"}
        )
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(payload)

    def test_extra_sl_hint_in_order_block_raises(self):
        """An unexpected 'sl_price' field in the order block must be rejected."""
        payload = _market_order_payload(
            order={"qty": "0.01", "order_type": "MARKET", "sl_price": "48000.00"}
        )
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(payload)

    def test_model_config_is_forbid(self):
        """TradeIntentOpenOrder model_config must explicitly have extra='forbid'."""
        config = TradeIntentOpenOrder.model_config
        assert config.get("extra") == "forbid", (
            f"TradeIntentOpenOrder.model_config has extra={config.get('extra')!r}. "
            "DEF-E03 requires extra='forbid' to prevent silent field drops."
        )

    def test_intake_model_config_is_forbid(self):
        """TradeIntentOpenIntake model_config must explicitly have extra='forbid'."""
        config = TradeIntentOpenIntake.model_config
        assert config.get("extra") == "forbid", (
            f"TradeIntentOpenIntake.model_config has extra={config.get('extra')!r}. "
            "DEF-E03 requires extra='forbid'."
        )


# ---------------------------------------------------------------------------
# DEF-E04: Decimal parser — scientific notation, NaN, Infinity, negative
# ---------------------------------------------------------------------------

class TestDecimalNumericContracts:
    """Qty and price fields must use Decimal parser, not brittle regex (DEF-E04)."""

    def test_standard_decimal_qty_passes(self):
        """Normal decimal qty like '0.01' must pass."""
        result = parse_trade_intent_open_intake(_market_order_payload(
            order={"qty": "0.01", "order_type": "MARKET"}
        ))
        assert result.order.qty == "0.01"

    def test_integer_qty_passes(self):
        """Integer qty string like '1' must pass."""
        result = parse_trade_intent_open_intake(_market_order_payload(
            order={"qty": "1", "order_type": "MARKET"}
        ))
        assert result.order.qty == "1"

    def test_scientific_notation_qty_passes(self):
        """DEF-E04: '1E-7' is a valid positive finite Decimal and must be accepted."""
        result = parse_trade_intent_open_intake(_market_order_payload(
            order={"qty": "1E-7", "order_type": "MARKET"}
        ))
        assert result.order.qty == "1E-7"

    def test_scientific_notation_uppercase_e_passes(self):
        """'1.5E+2' (scientific with uppercase E and +) must be accepted."""
        result = parse_trade_intent_open_intake(_market_order_payload(
            order={"qty": "1.5E+2", "order_type": "MARKET"}
        ))
        assert result.order.qty == "1.5E+2"

    def test_negative_qty_rejected(self):
        """Negative qty must be rejected."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "-0.01", "order_type": "MARKET"}
            ))

    def test_zero_qty_rejected(self):
        """Zero qty must be rejected (must be positive)."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "0", "order_type": "MARKET"}
            ))

    def test_empty_string_qty_rejected(self):
        """Empty string qty must be rejected."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "", "order_type": "MARKET"}
            ))

    def test_nan_qty_rejected(self):
        """'NaN' must be rejected."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "NaN", "order_type": "MARKET"}
            ))

    def test_infinity_qty_rejected(self):
        """'Infinity' must be rejected."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "Infinity", "order_type": "MARKET"}
            ))

    def test_limit_order_price_scientific_notation_passes(self):
        """Scientific notation price on LIMIT order must be accepted."""
        result = parse_trade_intent_open_intake(_limit_order_payload(
            order={"price": "5E+4", "tif": "GTC"}
        ))
        assert result.order.price == "5E+4"

    def test_stop_price_scientific_notation_passes(self):
        """Scientific notation stop_price must be accepted."""
        result = parse_trade_intent_open_intake(_market_order_payload(
            stop_price="4.5E+4"
        ))
        assert result.stop_price == "4.5E+4"

    def test_non_numeric_qty_rejected(self):
        """String 'hello' as qty must be rejected."""
        with pytest.raises((TradeIntentOpenIntakeError, ValidationError)):
            parse_trade_intent_open_intake(_market_order_payload(
                order={"qty": "hello", "order_type": "MARKET"}
            ))
