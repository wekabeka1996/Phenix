"""
Execution Position Domain Contracts

Defines domain-specific enums, constants, and validation rules.
Uses Pydantic V2 field_validator and model_validator.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Union, Literal
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    AliasChoices,
    field_validator,
    model_validator,
)

from vfoundation.core.protocol import Message
from .infra.utils import (
    ClientOrderIntent,
    ClientOrderIdMeta,
    parse_client_order_id,
)


# === Cross-domain boundary contracts (DecisionMaking → Bridge → ExecPos → Adapter) ===


def _as_decimal(value: Any) -> Optional[Decimal]:
    """Safe Decimal converter that accepts str/float/int and returns None on blanks."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def resolve_order_defaults(
    price: Optional[Decimal],
    order_type: Optional[str],
    time_in_force: Optional[str],
) -> tuple[str, Optional[str]]:
    """
    Unified fallback policy for order_type/time_in_force along the execution path.

    Rules:
    - If order_type is missing:
        - price is None -> MARKET
        - price is set -> LIMIT
    - If order_type == LIMIT and time_in_force missing -> GTC
    """
    resolved_type = order_type
    resolved_tif = time_in_force

    if not resolved_type:
        resolved_type = "LIMIT" if price is not None else "MARKET"

    if resolved_type == "LIMIT" and resolved_tif is None:
        resolved_tif = "GTC"

    return resolved_type, resolved_tif


class TradeIntentPayload(BaseModel):
    """
    Canonical DTO for EVT:TRADE_INTENT_PROPOSED (DecisionMaking → Bridge).

    Accepts legacy aliases (instrument/qty/idempotency_key) but normalizes to canonical
    fields for downstream mapping into CMD:OPEN.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    symbol: str = Field(validation_alias=AliasChoices("symbol", "instrument"))
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(
        validation_alias=AliasChoices("quantity", "qty"),
        description="Order quantity in base asset",
    )
    price: Optional[Decimal] = Field(default=None)
    price_ref: Optional[Decimal] = Field(default=None)
    order_type: Optional[str] = Field(default=None)
    time_in_force: Optional[str] = Field(
        default=None, serialization_alias="tif", validation_alias=AliasChoices("tif", "time_in_force")
    )

    rid: Optional[str] = None
    strategy_id: Optional[str] = None
    idempotent_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("idempotent_key", "idempotency_key")
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[Union[str, list[str]]] = None

    @field_validator("quantity", "price", "price_ref", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Optional[Decimal]:
        coerced = _as_decimal(value)
        if coerced is None:
            return None
        return coerced

    @field_validator("side", mode="before")
    @classmethod
    def _upper_side(cls, value: Any) -> str:
        return str(value).upper() if value is not None else value


class OpenCommandPayload(BaseModel):
    """
    CMD:OPEN payload (Bridge/Orchestrator → ExecPosRuntimeV2).

    Maintains backward compatibility with legacy keys (qty/tif) via aliases.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(
        validation_alias=AliasChoices("quantity", "qty"),
        serialization_alias="qty",
    )
    price: Optional[Decimal] = None
    price_ref: Optional[Decimal] = None
    order_type: str = Field(default="LIMIT")
    time_in_force: Optional[str] = Field(
        default="GTC", serialization_alias="tif", validation_alias=AliasChoices("tif", "time_in_force")
    )

    rid: Optional[str] = None
    strategy_id: Optional[str] = None
    idempotent_key: Optional[str] = None
    client_order_id: Optional[str] = None
    why: Optional[str] = None

    @field_validator("quantity", "price", "price_ref", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Optional[Decimal]:
        return _as_decimal(value)

    @field_validator("side", mode="before")
    @classmethod
    def _upper_side(cls, value: Any) -> str:
        return str(value).upper() if value is not None else value


class ExecutionRequest(BaseModel):
    """
    Canonical execution request (ExecPosRuntimeV2 → BinanceExecutionAdapter).

    Used to validate and normalize adapter inputs before forwarding.

    Note: quantity is Optional because closePosition=true orders don't need it.
    Binance will close the entire position when closePosition=true.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    symbol: str
    side: Literal["BUY", "SELL"]
    # quantity is Optional: not required for closePosition=true orders
    quantity: Optional[Decimal] = Field(default=None, validation_alias=AliasChoices("quantity", "qty"))
    order_type: str
    time_in_force: Optional[str] = Field(
        default=None, serialization_alias="tif", validation_alias=AliasChoices("tif", "time_in_force")
    )

    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = Field(default=None, validation_alias=AliasChoices("stop_price", "stopPrice"))
    reduce_only: Optional[bool] = None
    position_side: Optional[str] = None
    client_order_id: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("client_order_id", "newClientOrderId")
    )

    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "price", "stop_price", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Optional[Decimal]:
        return _as_decimal(value)

    @field_validator("side", mode="before")
    @classmethod
    def _upper_side(cls, value: Any) -> str:
        return str(value).upper() if value is not None else value


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


@dataclass
class PositionSnapshot:
    """
    Contract-first position snapshot for unified REST/WS position parsing.

    Single source of truth for extracting symbol/side/qty from exchange position data,
    handling all variations: positionSide=BOTH/LONG/SHORT, positionAmt as string/float.

    **Refs**: EP-STAB-POS-SNAPSHOT
    """
    symbol: str
    side: PositionSide | str  # Allow legacy string inputs for compatibility
    # Always positive, absolute position quantity
    qty: Optional[Decimal] = None
    avg_price: Optional[Decimal] = None
    updated_ts: Optional[float] = None
    # Legacy attribute (float) for callers expecting raw amt
    position_amt: Optional[float] = None

    def __post_init__(self) -> None:
        """Normalize side/qty so legacy callers (tests) keep working."""
        # Normalize side into PositionSide enum
        if not isinstance(self.side, PositionSide):
            normalized = canonicalize_position_side(self.side)
            if normalized is None:
                raise ValueError(f"Invalid position side: {self.side!r}")
            self.side = normalized

        # Determine qty source (qty field wins, fallback to position_amt)
        qty_source: Optional[Decimal]
        if self.qty is not None:
            qty_source = self.qty if isinstance(
                self.qty, Decimal) else Decimal(str(self.qty))
        elif self.position_amt is not None:
            qty_source = Decimal(str(self.position_amt))
        else:
            raise ValueError("PositionSnapshot requires qty or position_amt")

        qty_decimal = qty_source.copy_abs()
        self.qty = qty_decimal
        # Keep float mirror for legacy access patterns
        self.position_amt = float(qty_decimal)

    @classmethod
    def from_generic_payload(cls, payload: Dict[str, Any]) -> Optional["PositionSnapshot"]:
        """
        Extract position snapshot from a generic payload (e.g. live position state).

        Handles various keys for qty/side to unify parsing across FSMs.
        """
        if not payload:
            return None

        symbol = payload.get("symbol")
        if not symbol:
            return None

        # Try various qty keys
        qty_raw = payload.get("qty") or payload.get("position_amt") or payload.get(
            "position_amount") or payload.get("quantity")
        if qty_raw is None:
            return None

        try:
            qty_val = float(qty_raw)
            # Note: We allow 0 here if the caller needs to detect flat position,
            # but typically PositionSnapshot implies active position.
            # However, from_rest_list returns None for 0.
            # Let's match that behavior: return None if effectively zero.
            if abs(qty_val) < 1e-8:
                return None
            qty = Decimal(str(abs(qty_val)))
        except (ValueError, TypeError, InvalidOperation):
            return None

        # Try side keys
        side_raw = payload.get("side") or payload.get(
            "positionSide") or payload.get("position_side")

        # If side is explicit, use it
        if side_raw and str(side_raw).upper() in {"LONG", "SHORT", "BUY", "SELL"}:
            norm = str(side_raw).upper()
            if norm in {"LONG", "BUY"}:
                side = PositionSide.LONG
            else:
                side = PositionSide.SHORT
        else:
            # Infer from sign of qty_val
            side = PositionSide.LONG if qty_val > 0 else PositionSide.SHORT

        # Try avg_price
        avg_price = None
        price_raw = payload.get("avg_price") or payload.get(
            "entryPrice") or payload.get("avgPrice")
        if price_raw is not None:
            try:
                avg_price = Decimal(str(price_raw))
            except:
                pass

        # Try updated_ts
        updated_ts = payload.get("updated_ts") or payload.get(
            "updateTime") or payload.get("ts")
        if updated_ts is not None:
            try:
                updated_ts = float(updated_ts)
            except:
                updated_ts = None

        return cls(symbol=str(symbol).upper(), side=side, qty=qty, avg_price=avg_price, updated_ts=updated_ts)

    @classmethod
    def from_rest_list(
        cls,
        positions: list,
        symbol: str
    ) -> Optional["PositionSnapshot"]:
        """
        Extract position snapshot from REST/WS position list.

        Contract-first logic matching ManageFlowFSM's most stable implementation:
        - Filters by symbol
        - Handles positionSide: BOTH/LONG/SHORT
        - Parses positionAmt as string/float
        - Returns None if position is zero or missing

        Args:
            positions: List of position dicts from REST API or WebSocket
            symbol: Target symbol to filter (e.g., "BTCUSDT")

        Returns:
            PositionSnapshot if non-zero position found, else None

        **Refs**: EP-STAB-POS-SNAPSHOT
        """
        if not positions:
            return None

        # Convert to dicts if needed (handle Pydantic models, dataclasses)
        positions_list = [
            p.to_dict() if hasattr(p, 'to_dict') else (
                p.__dict__ if not isinstance(p, dict) else p
            )
            for p in positions
        ]

        # Filter by symbol
        sym_positions = [
            p for p in positions_list if p.get("symbol") == symbol]
        if not sym_positions:
            return None

        # Find first non-zero position (handles BOTH/LONG/SHORT)
        for pos in sym_positions:
            try:
                # Extract positionAmt (various field names)
                amt_raw = pos.get("positionAmt") or pos.get(
                    "position_amt") or pos.get("position_amount")
                if amt_raw is None:
                    continue

                amt = float(amt_raw)
                if abs(amt) < 1e-8:  # Effectively zero
                    continue

                # Determine side from positionSide field or infer from sign
                position_side_raw = pos.get(
                    "positionSide") or pos.get("position_side")

                if position_side_raw and str(position_side_raw).upper() in {"LONG", "SHORT"}:
                    # Explicit LONG/SHORT from hedge mode
                    side = PositionSide.LONG if str(
                        position_side_raw).upper() == "LONG" else PositionSide.SHORT
                else:
                    # BOTH mode or missing positionSide → infer from sign
                    side = PositionSide.LONG if amt > 0 else PositionSide.SHORT

                qty = Decimal(str(abs(amt)))

                # Extract avg_price
                avg_price = None
                price_raw = pos.get("entryPrice") or pos.get(
                    "avgPrice") or pos.get("avgEntryPrice")
                if price_raw is not None:
                    try:
                        avg_price = Decimal(str(price_raw))
                    except:
                        pass

                # Extract updated_ts
                updated_ts = None
                ts_raw = pos.get("updateTime") or pos.get(
                    "eventTime") or pos.get("ts")
                if ts_raw is not None:
                    try:
                        updated_ts = float(ts_raw)
                    except:
                        pass

                return cls(symbol=symbol, side=side, qty=qty, avg_price=avg_price, updated_ts=updated_ts)

            except (ValueError, TypeError, InvalidOperation):
                continue

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


# EP-STAB-SL-CLASS-FIX: Unified EXIT/SL classification contract
class ExitOrderKind(str, Enum):
    """
    Canonical classification of exit/close orders.

    Used by watchdog, ManageFlowFSM, and all invariant checks to consistently
    identify SL/TP/FLAT_CLOSE without duplicate heuristics.

    **Refs**: EP-STAB-SL-CLASS-FIX-A
    """
    STOP_LOSS = "stop_loss"          # SL bracket (STOP_MARKET, STOP_LIMIT, STOP, reduce-only STOP)
    # TP bracket (TAKE_PROFIT_MARKET, TAKE_PROFIT_LIMIT)
    TAKE_PROFIT = "take_profit"
    # Position close without SL/TP context (LIMIT/MARKET + reduceOnly/closePosition)
    FLAT_CLOSE = "flat_close"
    # EXIT by flag but type/pattern unclear (fallback)
    UNKNOWN_EXIT = "unknown_exit"


CLIENT_ORDER_ID_CONTRACT = """
Execution Position clientOrderId contract (v1):
- Format: epv1-<intent_token>-<seed>-<nonce> (<=36 chars, ASCII safe)
- Intent tokens: en (ENTRY), sl (STOP_LOSS), tp (TAKE_PROFIT), cl (CLOSE), ad (ADJUST)
- Seed: sanitized hash of (rid, symbol, decision_id, extra)
- Nonce: base36 timestamp fragment ensuring uniqueness
- Legacy suffixes (_sl/_tp) remain parseable via parse_client_order_id for backward compatibility.

Builder/parser live in apps.reference.domains.execution_position.utils; this module documents the schema for contract consumers.
"""


def classify_exit_order(pld: dict) -> Optional[ExitOrderKind]:
    """
    Unified classifier for EXIT order kind.

    Single source of truth for SL/TP/FLAT_CLOSE/UNKNOWN_EXIT classification,
    consumed by watchdog, ManageFlowFSM, and invariant checks.

    Considers:
    - order type (STOP_MARKET, TAKE_PROFIT_MARKET, STOP_LIMIT, LIMIT, MARKET, etc.)
    - reduceOnly / closePosition flags
    - stopPrice / activatePrice fields
    - clientOrderId contract (parse_client_order_id: epv1-<token>-<seed>-<nonce>)
    - workingType (MARK_PRICE, CONTRACT_PRICE, STOP_PRICE)

    Args:
        pld: Order payload dict (from exchange API or internal structures)

    Returns:
        ExitOrderKind if this is an exit/close order, None if this is ENTRY

    **Refs**: EP-STAB-SL-CLASS-FIX-A
    """
    order_type = str(pld.get("order_type") or pld.get("type") or "").upper()
    orig_type = str(pld.get("origType") or "").upper()
    working_type = str(pld.get("workingType") or "").upper()
    client_order_raw = pld.get("clientOrderId") or pld.get("client_order_id")
    stop_price = pld.get("stopPrice") or pld.get("activatePrice")

    reduce_only_value = pld.get("reduceOnly") or pld.get("reduce_only") or ""
    reduce_only = (
        bool(reduce_only_value is True)
        or str(reduce_only_value).strip().lower() in {"true", "1", "yes"}
    )

    close_position_value = (
        pld.get("closePosition")
        or pld.get("close_position")
        or pld.get("cp")
        or ""
    )
    close_position = (
        bool(close_position_value is True)
        or str(close_position_value).strip().lower() in {"true", "1", "yes"}
    )

    client_meta: Optional[ClientOrderIdMeta] = None
    try:
        client_meta = parse_client_order_id(client_order_raw)
    except Exception:
        client_meta = None

    if client_meta:
        if client_meta.intent == ClientOrderIntent.ENTRY:
            return None
        if client_meta.intent == ClientOrderIntent.STOP_LOSS:
            return ExitOrderKind.STOP_LOSS
        if client_meta.intent == ClientOrderIntent.TAKE_PROFIT:
            return ExitOrderKind.TAKE_PROFIT
        if client_meta.intent == ClientOrderIntent.CLOSE:
            return ExitOrderKind.FLAT_CLOSE

    # Check for explicit EXIT type indicators (STOP_*, TAKE_PROFIT_*)
    # These override the gate and always mark as EXIT
    is_explicit_stop = (
        order_type in {"STOP_MARKET", "STOP_LIMIT", "STOP"}
        or orig_type in {"STOP_MARKET", "STOP_LIMIT", "STOP"}
        or "STOP" in working_type
    )

    is_explicit_tp = (
        order_type in {"TAKE_PROFIT_MARKET",
                       "TAKE_PROFIT_LIMIT", "TAKE_PROFIT"}
        or orig_type in {"TAKE_PROFIT_MARKET", "TAKE_PROFIT_LIMIT", "TAKE_PROFIT"}
    )

    # TAKE_PROFIT classification (check BEFORE STOP_LOSS to handle priority):
    # - Any explicit TAKE_PROFIT type
    if is_explicit_tp:
        return ExitOrderKind.TAKE_PROFIT

    # STOP_LOSS classification:
    # - Any explicit STOP type
    if is_explicit_stop:
        return ExitOrderKind.STOP_LOSS

    # - reduceOnly + stopPrice present → SL (e.g., OCO bracket, LIMIT SL)
    # This logic also catches TP if stopPrice is present, but is_explicit_tp above takes priority
    if reduce_only and stop_price is not None:
        return ExitOrderKind.STOP_LOSS

    # Gate: order must have exit flags to be classified further
    # If no EXIT type and no exit flags, it's ENTRY
    if not (reduce_only or close_position):
        return None  # ENTRY order

    # FLAT_CLOSE classification:
    # - LIMIT or MARKET type with reduceOnly/closePosition
    # - No STOP/TP pattern already checked above
    if (reduce_only or close_position):
        return ExitOrderKind.FLAT_CLOSE

    return None  # Should not reach here


# Domain constraints (as Decimal for precision)
MIN_ORDER_QTY = Decimal("0.001")  # Minimum order quantity
MAX_ORDER_QTY = Decimal("1000.0")  # Maximum order quantity
MIN_PRICE = Decimal("0.01")  # Minimum price
MAX_PRICE = Decimal("1000000.0")  # Maximum price
MIN_NOTIONAL = Decimal("10.0")  # Minimum order value (qty * price)

# Quantization steps
QTY_STEP = Decimal("0.001")  # Lot size step
PRICE_STEP = Decimal("0.01")  # Price tick step

# Zero tolerance for position size (effectively zero)
POSITION_ZERO_TOLERANCE = 1e-8

# Event Constants
EVT_EXEC_POS_EXPOSURE_UPDATED = "EVT:EXEC_POS_EXPOSURE_UPDATED"



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


def is_exit_order(pld: dict) -> bool:
    """
    Contract-first classifier for EXIT vs ENTRY.

    EXIT = any condition where the order reduces or closes the position:
      - order_type in {STOP_MARKET, TAKE_PROFIT_MARKET}
      - reduceOnly == True
      - closePosition / cp == True

    **Now delegates to unified classify_exit_order for consistency.**

    This is the single source of truth for ENTRY/EXIT classification across
    ExecPosFSM, ManageFlowFSM, and all aggregated OCO paths.

    Args:
        pld: Order payload dict with keys: order_type, reduceOnly, closePosition, etc.

    Returns:
        True if this is an EXIT order (TP/SL/reduce), False if ENTRY

    **Refs**: EP-STAB-ENTRYEXIT-HELPER, EP-STAB-SL-CLASS-FIX-A
    """
    # EP-STAB-SL-CLASS-FIX: Delegate to unified classifier
    kind = classify_exit_order(pld)
    return kind is not None


def build_dec_close(
    msg: Message,
    why: str,
    payload: Dict[str, Any],
    *,
    idempotent_key: Optional[str] = None,
) -> Message:
    """Construct DEC:CLOSE with reduce_only enforced and shared metadata."""
    final_payload = payload.copy()
    final_payload.setdefault("reduce_only", True)

    return Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=why[:80],
        idempotent_key=idempotent_key or f"{msg.rid}_{why}_{int(time.time())}",
        pld=final_payload,
        data_ref=msg.data_ref.copy() if msg.data_ref else [],
    )
