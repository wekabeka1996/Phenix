"""Tests for execution_position domain contracts"""
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
    TimeInForce,
    validate_order_command,
)


def test_order_payload_valid():
    """Test valid order payload"""
    order = OrderPayload(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=1.0,
        order_type=OrderType.LIMIT,
        price=50000.0,
        tif=TimeInForce.GTC
    )
    
    assert order.symbol == "BTCUSDT"
    assert order.side == Side.BUY
    assert order.qty == Decimal("1.0")  # Now returns Decimal
    assert order.price == Decimal("50000.0")  # Now returns Decimal


def test_order_payload_qty_too_small():
    """Test that qty < MIN_ORDER_QTY is rejected"""
    with pytest.raises(ValueError, match="qty must be >="):
        OrderPayload(
            symbol="ETHUSDT",
            side=Side.SELL,
            qty=0.0001,  # Too small
            order_type=OrderType.LIMIT,
            price=3000.0
        )


def test_order_payload_qty_too_large():
    """Test that qty > MAX_ORDER_QTY is rejected"""
    with pytest.raises(ValueError, match="qty must be <="):
        OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=10000.0,  # Too large
            order_type=OrderType.LIMIT,
            price=50000.0
        )


def test_order_payload_price_negative():
    """Test that negative price is rejected"""
    with pytest.raises(ValueError):
        OrderPayload(
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=1.0,
            order_type=OrderType.LIMIT,
            price=-100.0  # Negative
        )


def test_order_payload_market_order():
    """Test market order (no price)"""
    order = OrderPayload(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=0.5,
        order_type=OrderType.MARKET
    )
    
    assert order.price is None
    assert order.order_type == OrderType.MARKET


def test_position_payload():
    """Test position payload"""
    position = PositionPayload(
        symbol="ETHUSDT",
        side=Side.BUY,  # Fixed: use BUY instead of LONG
        qty=10.0,
        avg_price=3000.0,
        unrealized_pnl=500.0,
        realized_pnl=100.0
    )
    
    assert position.symbol == "ETHUSDT"
    assert position.qty == Decimal("10.0")  # Now returns Decimal
    assert position.unrealized_pnl == Decimal("500.0")  # Now returns Decimal


def test_validate_order_command_valid():
    """Test validate_order_command with valid data"""
    pld = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": 1.0,
        "order_type": "LIMIT",
        "price": 50000.0
    }
    
    assert validate_order_command(pld) is True


def test_validate_order_command_invalid():
    """Test validate_order_command with invalid data"""
    pld = {
        "symbol": "BTC",  # Too short
        "side": "BUY",
        "qty": -1.0,  # Negative
        "order_type": "LIMIT"
    }
    
    assert validate_order_command(pld) is False


def test_side_enum():
    """Test Side enum values"""
    assert Side.BUY.value == "BUY"
    assert Side.SELL.value == "SELL"


def test_order_type_enum():
    """Test OrderType enum values"""
    assert OrderType.MARKET.value == "MARKET"
    assert OrderType.LIMIT.value == "LIMIT"
    assert OrderType.STOP_LIMIT.value == "STOP_LIMIT"


def test_time_in_force_enum():
    """Test TimeInForce enum values"""
    assert TimeInForce.GTC.value == "GTC"
    assert TimeInForce.IOC.value == "IOC"
    assert TimeInForce.FOK.value == "FOK"
