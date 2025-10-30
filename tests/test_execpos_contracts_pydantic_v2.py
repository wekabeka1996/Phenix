"""
Pydantic V2 validator tests for execution_position contracts

Tests field_validator, model_validator, Decimal quantization, and cross-field validation.
"""

import pytest
import sys
from pathlib import Path
from decimal import Decimal

# Add vfoundation to path
sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))

from apps.reference.domains.execution_position.contracts import (
    OrderPayload,
    PositionPayload,
    Side,
    OrderType,
    MIN_ORDER_QTY,
    MAX_ORDER_QTY,
    MAX_PRICE,
    MIN_NOTIONAL,
)


class TestQtyFieldValidator:
    """Test qty field_validator (parse + quantize)"""

    def test_qty_from_float(self):
        """Test qty parsing from float"""
        order = OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty=1.5, price=50000.0)
        assert order.qty == Decimal("1.5")
        assert isinstance(order.qty, Decimal)

    def test_qty_from_string(self):
        """Test qty parsing from string"""
        order = OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty="2.5", price=50000.0)
        assert order.qty == Decimal("2.5")

    def test_qty_quantization(self):
        """Test qty quantization to QTY_STEP"""
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty="1.5555",  # Should round to 1.555
            price=50000.0,
        )
        # ROUND_DOWN: 1.5555 -> 1.555
        assert order.qty == Decimal("1.555")

    def test_qty_below_min(self):
        """Test qty < MIN_ORDER_QTY raises ValueError"""
        with pytest.raises(ValueError, match="qty must be >="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=0.0001,  # Too small
                price=50000.0,
            )

    def test_qty_above_max(self):
        """Test qty > MAX_ORDER_QTY raises ValueError"""
        with pytest.raises(ValueError, match="qty must be <="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=10000.0,  # Too large
                price=50000.0,
            )

    def test_qty_invalid_string(self):
        """Test invalid qty string raises ValueError"""
        with pytest.raises(ValueError, match="qty must be valid number"):
            OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty="invalid", price=50000.0)

    def test_qty_none(self):
        """Test qty=None raises ValueError"""
        with pytest.raises(ValueError, match="qty cannot be None"):
            OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty=None, price=50000.0)


class TestPriceFieldValidator:
    """Test price field_validator (parse + quantize)"""

    def test_price_from_float(self):
        """Test price parsing from float"""
        order = OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty=1.0, price=50000.55)
        assert order.price == Decimal("50000.55")
        assert isinstance(order.price, Decimal)

    def test_price_from_string(self):
        """Test price parsing from string"""
        order = OrderPayload(
            symbol="ETHUSDT", side=Side.SELL, qty=10.0, price="3000.99"
        )
        assert order.price == Decimal("3000.99")

    def test_price_quantization(self):
        """Test price quantization to PRICE_STEP"""
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=1.0,
            price="50000.999",  # Should round to 50000.99
        )
        # ROUND_DOWN: 50000.999 -> 50000.99
        assert order.price == Decimal("50000.99")

    def test_price_below_min(self):
        """Test price < MIN_PRICE raises ValueError"""
        with pytest.raises(ValueError, match="price must be >="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=1.0,
                price=0.001,  # Too small
            )

    def test_price_above_max(self):
        """Test price > MAX_PRICE raises ValueError"""
        with pytest.raises(ValueError, match="price must be <="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=1.0,
                price=10000000.0,  # Too large
            )

    def test_price_none_for_market_order(self):
        """Test price=None is allowed for MARKET orders"""
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=1.0,
            order_type=OrderType.MARKET,
            price=None,
        )
        assert order.price is None

    def test_price_invalid_string(self):
        """Test invalid price string raises ValidationError (finite_number)"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="finite_number"):
            OrderPayload(symbol="BTCUSDT", side=Side.BUY, qty=1.0, price="NaN")


class TestModelValidator:
    """Test model_validator for cross-field validation"""

    def test_limit_order_requires_price(self):
        """Test LIMIT order without price raises ValueError"""
        with pytest.raises(ValueError, match="LIMIT orders require price"):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=1.0,
                order_type=OrderType.LIMIT,
                price=None,
            )

    def test_notional_below_minimum(self):
        """Test order notional < MIN_NOTIONAL raises ValueError"""
        with pytest.raises(ValueError, match="order notional value must be >="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=0.001,  # qty * price = 0.001 * 100 = 0.1 < MIN_NOTIONAL (10.0)
                price=100.0,
            )

    def test_notional_exactly_minimum(self):
        """Test order notional = MIN_NOTIONAL passes"""
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=0.1,  # 0.1 * 100 = 10.0 = MIN_NOTIONAL
            price=100.0,
        )
        assert order.qty * order.price == MIN_NOTIONAL

    def test_notional_above_minimum(self):
        """Test order notional > MIN_NOTIONAL passes"""
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=1.0,
            price=50000.0,  # notional = 50000.0 > MIN_NOTIONAL
        )
        assert order.qty * order.price > MIN_NOTIONAL


class TestPositionPayload:
    """Test PositionPayload with Decimal fields"""

    def test_position_with_decimals(self):
        """Test position creation with Decimal values"""
        position = PositionPayload(
            symbol="ETHUSDT",
            side=Side.BUY,
            qty=Decimal("10.5"),
            avg_price=Decimal("3000.50"),
            unrealized_pnl=Decimal("500.25"),
            realized_pnl=Decimal("100.10"),
        )

        assert position.qty == Decimal("10.5")
        assert position.avg_price == Decimal("3000.50")
        assert position.unrealized_pnl == Decimal("500.25")
        assert position.realized_pnl == Decimal("100.10")

    def test_position_default_pnl(self):
        """Test position with default PNL values"""
        position = PositionPayload(
            symbol="BTCUSDT",
            side=Side.SELL,
            qty=Decimal("1.0"),
            avg_price=Decimal("50000.0"),
        )

        assert position.unrealized_pnl == Decimal("0.0")
        assert position.realized_pnl == Decimal("0.0")


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_minimum_valid_order(self):
        """Test minimum valid order (MIN_ORDER_QTY * MIN_PRICE >= MIN_NOTIONAL)"""
        # Need qty * price >= 10.0
        # MIN_ORDER_QTY = 0.001, so need price >= 10000.0
        order = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=MIN_ORDER_QTY,
            price=Decimal("10000.0"),  # 0.001 * 10000 = 10.0 = MIN_NOTIONAL
        )
        assert order.qty == MIN_ORDER_QTY
        assert order.price == Decimal("10000.0")

    def test_maximum_valid_order(self):
        """Test maximum valid order"""
        order = OrderPayload(
            symbol="BTCUSDT", side=Side.BUY, qty=MAX_ORDER_QTY, price=MAX_PRICE
        )
        assert order.qty == MAX_ORDER_QTY
        assert order.price == MAX_PRICE

    def test_whitespace_handling(self):
        """Test that whitespace is stripped from string inputs"""
        order = OrderPayload(
            symbol="BTCUSDT", side=Side.BUY, qty="  1.5  ", price="  50000.0  "
        )
        assert order.qty == Decimal("1.5")
        assert order.price == Decimal("50000.0")

    def test_zero_qty_after_quantization_fails(self):
        """Test that qty below MIN_ORDER_QTY raises ValueError"""
        # Qty below MIN_ORDER_QTY (0.001) will be rejected before quantization
        with pytest.raises(ValueError, match="qty must be >="):
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.0001"),  # Below MIN_ORDER_QTY
                price=50000.0,
            )


class TestValidateOrderCommand:
    """Test validate_order_command helper function"""

    def test_validate_valid_command(self):
        """Test validation of valid order command dict"""
        from apps.reference.domains.execution_position.contracts import (
            validate_order_command,
        )

        pld = {"symbol": "BTCUSDT", "side": "BUY", "qty": 1.0, "price": 50000.0}

        assert validate_order_command(pld) is True

    def test_validate_invalid_command(self):
        """Test validation of invalid order command dict"""
        from apps.reference.domains.execution_position.contracts import (
            validate_order_command,
        )

        pld = {
            "symbol": "BT",  # Too short
            "side": "BUY",
            "qty": -1.0,  # Negative
            "price": 50000.0,
        }

        assert validate_order_command(pld) is False
