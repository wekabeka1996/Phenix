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


class PositionSide(str, Enum):
    """Canonical position side used by aggregated OCO/guardian paths."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


def canonicalize_position_side(value: Optional[str]) -> Optional[PositionSide]:
    """Map raw BUY/SELL strings (any casing) to LONG/SHORT."""

    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if normalized in {"LONG", "BUY"}:
        return PositionSide.LONG
    if normalized in {"SHORT", "SELL"}:
        return PositionSide.SHORT
    if normalized == "FLAT":
        return PositionSide.FLAT
    return None


def canonicalize_position_side_from_qty(position_qty: Optional[Decimal]) -> PositionSide:
    """Infer canonical position side directly from signed position quantity."""

    if position_qty is None:
        return PositionSide.FLAT
    try:
        qty = Decimal(str(position_qty))
    except (InvalidOperation, ValueError, TypeError):
        return PositionSide.FLAT
    if qty > 0:
        return PositionSide.LONG
    if qty < 0:
        return PositionSide.SHORT
    return PositionSide.FLAT


class OrderType(str, Enum):
    """Order type"""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LIMIT = "STOP_LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    STOP = "STOP"
    TAKE_PROFIT = "TAKE_PROFIT"


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


class WorkingType(str, Enum):
    """Price source for conditional order trigger validation (Binance Futures)

    Refs: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    """
    MARK_PRICE = "MARK_PRICE"       # Recommended for TP/SL (less volatile)
    CONTRACT_PRICE = "CONTRACT_PRICE"  # Contract/index price


class BracketErrorCode(str, Enum):
    """API error codes specific to bracket/TP/SL orders

    Refs: https://developers.binance.com/docs/usdm-derivatives/errors
    """
    WOULD_IMMEDIATELY_TRIGGER = "-2021"  # stopPrice on wrong side of mark
    DUPLICATE_CLIENT_ORDER_ID = "-4116"   # newClientOrderId already used
    QUANTITY_NOT_ALLOWED = "-4137"        # Quantity passed with closePosition=true
    MIN_NOTIONAL_NOT_MET = "-4164"        # Order notional too low


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
            raise ValueError(
                f"qty after quantization must be > 0 (got {quantized})")
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
            raise ValueError(
                f"price after quantization must be > 0 (got {quantized})")
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


class BracketOrderPayload(OrderPayload):
    """TP/SL order with Binance-specific fields

    Used for TAKE_PROFIT_MARKET, STOP_MARKET, and related conditional orders.

    Refs: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    """

    # Conditional/Bracket fields
    stop_price: Optional[Decimal] = Field(None, gt=0)
    working_type: WorkingType = WorkingType.MARK_PRICE
    price_protect: bool = False  # Enable triggerProtect check
    # For TAKE_PROFIT_MARKET/STOP_MARKET: close entire position
    close_position: bool = False
    reduce_only: bool = False

    # Idempotency & tracking
    orig_client_order_id: Optional[str] = Field(
        None, min_length=1, max_length=36)
    new_client_order_id: Optional[str] = Field(
        None, min_length=1, max_length=36)
    position_side: Optional[str] = Field(None, pattern="^(LONG|SHORT)$")

    @field_validator("stop_price", mode="before")
    @classmethod
    def parse_stop_price(cls, v):
        """Parse stop_price to Decimal from float/str"""
        if v is None:
            return None
        try:
            if isinstance(v, str):
                v = v.strip()
            return Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"stop_price must be valid Decimal: {e}")

    @model_validator(mode="after")
    def validate_bracket_rules(self):
        """Enforce Binance TP/SL rules per developers.binance.com

        Key rules:
        1. closePosition=true means NO quantity (Binance closes entire position)
        2. STOP_MARKET/TAKE_PROFIT_MARKET with closePosition=true requires MARK_PRICE
        3. Conditional orders must have stop_price
        """
        # Rule 1: closePosition=true means NO quantity
        if self.close_position and self.qty is not None:
            raise ValueError(
                "closePosition=true cannot have quantity; use only closePosition "
                "(Binance will close entire position)"
            )

        # Rule 2: closePosition=true requires MARK_PRICE
        if self.close_position and self.working_type != WorkingType.MARK_PRICE:
            raise ValueError(
                f"closePosition=true requires MARK_PRICE, got {self.working_type}"
            )

        # Rule 3: Conditional orders require stop_price
        conditional_types = [
            OrderType.STOP, OrderType.TAKE_PROFIT,
            OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET
        ]
        if self.order_type in conditional_types and self.stop_price is None:
            raise ValueError(f"{self.order_type} requires stop_price")

        return self


class TPSLValidationRules:
    """
    Enforce Binance Futures TP/SL rules and avoid API errors.

    Error codes addressed:
    - -2021 "Order would immediately trigger": stopPrice on wrong side
    - -4116 "ClientOrderId is duplicated": newClientOrderId reused
    - -4137 "Quantity not allowed": quantity passed with closePosition=true
    - -4164 "MIN_NOTIONAL": order too small

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    - https://developers.binance.com/docs/usdm-derivatives/errors
    """

    @staticmethod
    def validate_stop_price_for_side(
        position_side: str,
        current_mark: Decimal,
        stop_price: Decimal,
        is_take_profit: bool,
    ) -> tuple[bool, str]:
        """
        Validate that stop_price is on CORRECT SIDE of mark price.

        Prevents -2021 "Order would immediately trigger" by validating BEFORE submission.

        Args:
            position_side: "LONG" or "SHORT"
            current_mark: Current mark price from Binance API
            stop_price: Target stop/TP price to validate
            is_take_profit: True for TP, False for SL

        Returns:
            (is_valid: bool, reason: str)
            reason explains the validation result and includes prices

        **Binance Rules** (from developers.binance.com):
            LONG + TP: stop_price > current_mark (price must go UP to trigger TP)
            LONG + SL: stop_price < current_mark (price must go DOWN to trigger SL)
            SHORT + TP: stop_price < current_mark (price must go DOWN to trigger TP)
            SHORT + SL: stop_price > current_mark (price must go UP to trigger SL)

        **Why -2021 Occurs**:
            If stop_price is on the WRONG side (or equal to) current mark price,
            Binance rejects with -2021 "Order would immediately trigger".
            This validator prevents it by checking BEFORE submission.

        **Example**:
            LONG position at 100 USDT, current mark=100.5:
            - TP at 105: valid (105 > 100.5) → will trigger when price goes UP
            - TP at 98: INVALID (98 < 100.5) → would immediately trigger
        """
        if position_side == "LONG":
            if is_take_profit:
                valid = stop_price > current_mark
                reason = f"LONG TP: {stop_price} must be > mark {current_mark}"
            else:
                valid = stop_price < current_mark
                reason = f"LONG SL: {stop_price} must be < mark {current_mark}"
        elif position_side == "SHORT":
            if is_take_profit:
                valid = stop_price < current_mark
                reason = f"SHORT TP: {stop_price} must be < mark {current_mark}"
            else:
                valid = stop_price > current_mark
                reason = f"SHORT SL: {stop_price} must be > mark {current_mark}"
        else:
            return False, f"Invalid position_side: {position_side}"

        return valid, reason

    @staticmethod
    def add_safety_offset(
        current_price: Decimal,
        tick_size: Decimal,
        offset_bps: int = 5,
    ) -> Decimal:
        """
        Calculate safe offset from current price to avoid -2021 errors.

        Args:
            current_price: Mark price (in quote currency)
            tick_size: Minimum price increment from /exchangeInfo (e.g., 0.01 for ETHUSDT)
            offset_bps: Basis points (5 = 0.05%; default is conservative)

        Returns:
            offset: max(1 * tick_size, offset_bps% of price)

        **Rationale**:
            Binance docs recommend adding margin to avoid -2021 errors on volatile assets.
            Use the LARGER of:
            1. One minimum tick (e.g., 0.01)
            2. Small percentage of price (e.g., 0.05%)

            This ensures TP/SL prices have room for market movement between
            calculation and submission.

        **Example**:
            Mark price = $100, tick_size = 0.01, offset_bps = 5:
            - min_offset = 0.01
            - pct_offset = 100 * 5 / 10000 = 0.05
            - result = max(0.01, 0.05) = 0.05

            So TP should be at least 100 + 0.05 = 100.05 (not 100.00)

        **Refs**: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
        """
        min_offset = tick_size
        pct_offset = current_price * Decimal(offset_bps) / Decimal("10000")
        result = max(min_offset, pct_offset)
        return result


class PositionPayload(BaseModel):
    """Payload for position updates"""

    model_config = ConfigDict(validate_assignment=True,
                              arbitrary_types_allowed=True)

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
