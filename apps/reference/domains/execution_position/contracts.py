"""
Execution Position Domain Contracts

Defines domain-specific enums, constants, and validation rules.
Uses Pydantic V2 field_validator and model_validator.
"""

from enum import Enum
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class Side(str, Enum):
    """Order side"""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type"""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Time-in-force"""

    GTC = "GTC"  # Good-Till-Cancel
    IOC = "IOC"  # Immediate-Or-Cancel
    FOK = "FOK"  # Fill-Or-Kill


class OrderStatus(str, Enum):
    """Order execution status"""

    PENDING = "PENDING"
    PLACED = "PLACED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# Domain constraints (as Decimal for precision)
MIN_ORDER_QTY = Decimal("0.001")  # Minimum order quantity
MAX_ORDER_QTY = Decimal("1000.0")  # Maximum order quantity
MIN_PRICE = Decimal("0.01")  # Minimum price
MAX_PRICE = Decimal("1000000.0")  # Maximum price
MIN_NOTIONAL = Decimal("10.0")  # Minimum order value (qty * price)

# Quantization steps
QTY_STEP = Decimal("0.001")  # Lot size step
PRICE_STEP = Decimal("0.01")  # Price tick step


class OrderPayload(BaseModel):
    """Payload for order commands/events with Pydantic V2 validators"""

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    symbol: str = Field(..., min_length=3, max_length=20)
    side: Side
    qty: Decimal = Field(..., gt=0)
    order_type: OrderType = OrderType.LIMIT
    price: Optional[Decimal] = Field(None, gt=0)
    tif: TimeInForce = TimeInForce.GTC

    @field_validator("qty", mode="before")
    @classmethod
    def parse_qty(cls, v):
        """Parse qty to Decimal from float/str"""
        if v is None:
            raise ValueError("qty cannot be None")
        try:
            if isinstance(v, str):
                v = v.strip()
            return Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"qty must be valid number: {e}")

    @field_validator("qty", mode="after")
    @classmethod
    def validate_and_quantize_qty(cls, v: Decimal) -> Decimal:
        """Validate qty bounds and quantize to step"""
        if v < MIN_ORDER_QTY:
            raise ValueError(f"qty must be >= {MIN_ORDER_QTY}")
        if v > MAX_ORDER_QTY:
            raise ValueError(f"qty must be <= {MAX_ORDER_QTY}")

        # Quantize to lot size step (round to nearest)
        quantized = v.quantize(QTY_STEP, rounding=ROUND_DOWN)
        if quantized <= 0:
            raise ValueError(f"qty after quantization must be > 0 (got {quantized})")
        return quantized

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, v):
        """Parse price to Decimal from float/str"""
        if v is None:
            return None
        try:
            if isinstance(v, str):
                v = v.strip()
            return Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"price must be valid number: {e}")

    @field_validator("price", mode="after")
    @classmethod
    def validate_and_quantize_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price bounds and quantize to step"""
        if v is None:
            return None

        if v < MIN_PRICE:
            raise ValueError(f"price must be >= {MIN_PRICE}")
        if v > MAX_PRICE:
            raise ValueError(f"price must be <= {MAX_PRICE}")

        # Quantize to price step (round to nearest)
        quantized = v.quantize(PRICE_STEP, rounding=ROUND_DOWN)
        if quantized <= 0:
            raise ValueError(f"price after quantization must be > 0 (got {quantized})")
        return quantized

    @model_validator(mode="after")
    def validate_cross_field_invariants(self):
        """Cross-field validation: notional value, price requirement for LIMIT orders"""
        # LIMIT orders require price
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require price")

        # Check minimum notional (qty * price >= MIN_NOTIONAL)
        if self.price is not None:
            notional = self.qty * self.price
            if notional < MIN_NOTIONAL:
                raise ValueError(
                    f"order notional value must be >= {MIN_NOTIONAL} "
                    f"(got {notional} = {self.qty} * {self.price})"
                )

        return self


class PositionPayload(BaseModel):
    """Payload for position updates"""

    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    symbol: str
    side: Side
    qty: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0.0")
    realized_pnl: Decimal = Decimal("0.0")


def validate_order_command(pld: Dict[str, Any]) -> bool:
    """Validate order command payload"""
    try:
        OrderPayload(**pld)
        return True
    except Exception:
        return False
