"""
Tests for execution_position/contracts.py

Covers Pydantic models and validation logic.
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError

from apps.reference.domains.execution_position.contracts import (
    Side,
    OrderType,
    TimeInForce,
    OrderStatus,
    OrderPayload,
    PositionPayload,
    validate_order_command,
    MIN_ORDER_QTY,
    MAX_ORDER_QTY,
    MIN_PRICE,
    MAX_PRICE,
    MIN_NOTIONAL,
)


class TestEnums:
    """Test enum definitions"""

    def test_side_enum(self):
        assert Side.BUY == "BUY"
        assert Side.SELL == "SELL"

    def test_order_type_enum(self):
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.STOP_LIMIT == "STOP_LIMIT"

    def test_time_in_force_enum(self):
        assert TimeInForce.GTC == "GTC"
        assert TimeInForce.IOC == "IOC"
        assert TimeInForce.FOK == "FOK"

    def test_order_status_enum(self):
        assert OrderStatus.PENDING == "PENDING"
        assert OrderStatus.PLACED == "PLACED"
        assert OrderStatus.PARTIAL == "PARTIAL"
        assert OrderStatus.FILLED == "FILLED"
        assert OrderStatus.CANCELLED == "CANCELLED"
        assert OrderStatus.REJECTED == "REJECTED"
        assert OrderStatus.EXPIRED == "EXPIRED"


class TestOrderPayloadValidation:
    """Test OrderPayload model validation"""

    def test_valid_limit_order(self):
        """Test valid LIMIT order creation"""
        payload = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("50000.00"),
            tif=TimeInForce.GTC,
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.side == Side.BUY
        assert payload.qty == Decimal("0.001")
        assert payload.price == Decimal("50000.00")

    def test_valid_market_order(self):
        """Test valid MARKET order creation"""
        payload = OrderPayload(
            symbol="ETHUSDT",
            side=Side.SELL,
            qty=Decimal("1.0"),
            order_type=OrderType.MARKET,
        )
        assert payload.symbol == "ETHUSDT"
        assert payload.side == Side.SELL
        assert payload.qty == Decimal("1.0")
        assert payload.price is None

    def test_qty_validation_min(self):
        """Test minimum quantity validation"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.0001"),  # Below MIN_ORDER_QTY
                order_type=OrderType.MARKET,
            )
        assert "qty must be >=" in str(exc_info.value)

    def test_qty_validation_max(self):
        """Test maximum quantity validation"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("2000.0"),  # Above MAX_ORDER_QTY
                order_type=OrderType.MARKET,
            )
        assert "qty must be <=" in str(exc_info.value)

    def test_price_validation_min(self):
        """Test minimum price validation"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                price=Decimal("0.001"),  # Below MIN_PRICE
            )
        assert "price must be >=" in str(exc_info.value)

    def test_price_validation_max(self):
        """Test maximum price validation"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                price=Decimal("2000000.0"),  # Above MAX_PRICE
            )
        assert "price must be <=" in str(exc_info.value)

    def test_limit_order_requires_price(self):
        """Test that LIMIT orders require price"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                # Missing price
            )
        assert "LIMIT orders require price" in str(exc_info.value)

    def test_minimum_notional_validation(self):
        """Test minimum notional value validation"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                price=Decimal("5.00"),  # 0.001 * 5.00 = 0.005 < MIN_NOTIONAL (10.0)
            )
        assert "order notional value must be >=" in str(exc_info.value)

    def test_qty_quantization(self):
        """Test quantity quantization to step"""
        payload = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal("0.0015"),  # Should quantize to 0.001
            order_type=OrderType.MARKET,
        )
        assert payload.qty == Decimal("0.001")

    def test_price_quantization(self):
        """Test price quantization to step"""
        payload = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("50000.123"),  # Should quantize to 50000.12
        )
        assert payload.price == Decimal("50000.12")

    def test_qty_parsing_from_string(self):
        """Test quantity parsing from string"""
        payload = OrderPayload(
            symbol="BTCUSDT", side=Side.BUY, qty="0.001", order_type=OrderType.MARKET
        )
        assert payload.qty == Decimal("0.001")

    def test_price_parsing_from_string(self):
        """Test price parsing from string"""
        payload = OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price="50000.00",
        )
        assert payload.price == Decimal("50000.00")

    def test_invalid_qty_string(self):
        """Test invalid quantity string"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty="invalid",
                order_type=OrderType.MARKET,
            )
        assert "qty must be valid number" in str(exc_info.value)

    def test_invalid_price_string(self):
        """Test invalid price string"""
        with pytest.raises(ValidationError) as exc_info:
            OrderPayload(
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                price="invalid",
            )
        assert "price must be valid number" in str(exc_info.value)


class TestPositionPayloadValidation:
    """Test PositionPayload model validation"""

    def test_valid_position_payload(self):
        """Test valid position payload creation"""
        payload = PositionPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal("0.001"),
            avg_price=Decimal("50000.00"),
            unrealized_pnl=Decimal("10.0"),
            realized_pnl=Decimal("5.0"),
        )
        assert payload.symbol == "BTCUSDT"
        assert payload.side == Side.BUY
        assert payload.qty == Decimal("0.001")
        assert payload.avg_price == Decimal("50000.00")
        assert payload.unrealized_pnl == Decimal("10.0")
        assert payload.realized_pnl == Decimal("5.0")


class TestValidateOrderCommand:
    """Test validate_order_command function"""

    def test_valid_command(self):
        """Test validation of valid order command"""
        cmd = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.001",
            "order_type": "LIMIT",
            "price": "50000.00",
        }
        assert validate_order_command(cmd) is True

    def test_invalid_command_missing_symbol(self):
        """Test validation of invalid command (missing symbol)"""
        cmd = {
            "side": "BUY",
            "qty": "0.001",
            "order_type": "LIMIT",
            "price": "50000.00",
        }
        assert validate_order_command(cmd) is False

    def test_invalid_command_invalid_qty(self):
        """Test validation of invalid command (invalid qty)"""
        cmd = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "invalid",
            "order_type": "LIMIT",
            "price": "50000.00",
        }
        assert validate_order_command(cmd) is False

    def test_invalid_command_below_min_notional(self):
        """Test validation of invalid command (below min notional)"""
        cmd = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.001",
            "order_type": "LIMIT",
            "price": "5.00",
        }
        assert validate_order_command(cmd) is False
