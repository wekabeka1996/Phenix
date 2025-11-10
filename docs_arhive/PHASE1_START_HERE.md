# 🚀 PHASE 1: START HERE - Contracts + Validation

**Status**: READY FOR IMPLEMENTATION
**Estimated Duration**: 1–2 hours
**Deliverable**: contracts.py + schemas (ready for Phase 2)

---

## What To Do (TL;DR)

### Step 1: Update `apps/reference/domains/execution_position/contracts.py`

**Add at top** (after existing enums):

```python
class WorkingType(str, Enum):
    """Price source for conditional order trigger validation (Binance Futures)"""
    MARK_PRICE = "MARK_PRICE"       # Recommended for TP/SL
    CONTRACT_PRICE = "CONTRACT_PRICE"


class BracketErrorCode(str, Enum):
    """API error codes specific to bracket/TP/SL orders"""
    WOULD_IMMEDIATELY_TRIGGER = "-2021"
    DUPLICATE_CLIENT_ORDER_ID = "-4116"
    QUANTITY_NOT_ALLOWED = "-4137"
    MIN_NOTIONAL_NOT_MET = "-4164"


class BracketOrderPayload(OrderPayload):
    """TP/SL order with Binance-specific fields

    Refs: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    """

    # Conditional/Bracket fields
    stop_price: Optional[Decimal] = Field(None, gt=0)
    working_type: WorkingType = WorkingType.MARK_PRICE
    price_protect: bool = False  # Enable triggerProtect check
    close_position: bool = False  # For TAKE_PROFIT_MARKET/STOP_MARKET
    reduce_only: bool = False

    # Idempotency & tracking
    orig_client_order_id: Optional[str] = Field(None, min_length=1, max_length=36)
    new_client_order_id: Optional[str] = Field(None, min_length=1, max_length=36)
    position_side: Optional[str] = Field(None, regex="^(LONG|SHORT)$")

    @model_validator(mode="after")
    def validate_bracket_rules(self):
        """Enforce Binance TP/SL rules per developers.binance.com"""
        # Rule 1: closePosition=true means NO quantity
        if self.close_position and self.qty is not None:
            raise ValueError(
                "closePosition=true cannot have quantity; use only closePosition"
            )

        # Rule 2: For closePosition=true, must use MARK_PRICE
        if self.close_position and self.working_type != WorkingType.MARK_PRICE:
            raise ValueError(
                f"closePosition=true requires MARK_PRICE, got {self.working_type}"
            )

        return self
```

**Add new class** (after OrderPayload):

```python
class TPSLValidationRules:
    """
    Enforce Binance Futures TP/SL rules.

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    - https://developers.binance.com/docs/usdm-derivatives/errors (error codes)
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

        Args:
            position_side: "LONG" or "SHORT"
            current_mark: Current mark price from API
            stop_price: Target stop/TP price
            is_take_profit: True for TP, False for SL

        Returns:
            (is_valid: bool, reason: str)

        **Binance Rules**:
            LONG + TP: stop_price > current_mark (price must go UP to trigger TP)
            LONG + SL: stop_price < current_mark (price must go DOWN to trigger SL)
            SHORT + TP: stop_price < current_mark (price must go DOWN to trigger TP)
            SHORT + SL: stop_price > current_mark (price must go UP to trigger SL)

        **Error -2021 "Order would immediately trigger"**:
            Sent if stop_price is on WRONG side (or equal to) mark price.
            Solution: This validator prevents -2021 BEFORE submission.
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
        Calculate safe offset from current price.

        Args:
            current_price: Mark price
            tick_size: Minimum price increment (e.g., 0.01 for ETHUSDT)
            offset_bps: Basis points (5 = 0.05% = 5 / 10000)

        Returns:
            offset: max(1 * tick_size, offset_bps% of price)

        **Rationale**:
            Binance docs recommend adding margin to avoid -2021 errors.
            Use the LARGER of: (1 tick) or (0.05% of price).
            Default 5 bps is conservative; can increase to 20 bps for volatile assets.

        **Refs**: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
        """
        min_offset = tick_size
        pct_offset = current_price * Decimal(offset_bps) / Decimal("10000")
        return max(min_offset, pct_offset)
```

---

### Step 2: Create `schemas/bracket_order_v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.local/schemas/bracket_order_v1.json",
  "title": "Bracket Order (TP/SL)",
  "description": "Take-Profit and Stop-Loss orders per Binance Futures API (https://developers.binance.com/docs/usdm-derivatives/trade/new-order)",
  "type": "object",
  "properties": {
    "symbol": {
      "type": "string",
      "pattern": "^[A-Z0-9]+$",
      "description": "Trading pair (e.g., ETHUSDT)"
    },
    "side": {
      "type": "string",
      "enum": ["BUY", "SELL"],
      "description": "Order side"
    },
    "order_type": {
      "type": "string",
      "enum": ["STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT"],
      "description": "Conditional order type"
    },
    "stop_price": {
      "type": "number",
      "exclusiveMinimum": 0,
      "description": "Price that triggers the order"
    },
    "working_type": {
      "type": "string",
      "enum": ["MARK_PRICE", "CONTRACT_PRICE"],
      "default": "MARK_PRICE",
      "description": "Price source for trigger validation (MARK_PRICE recommended)"
    },
    "price_protect": {
      "type": "boolean",
      "default": false,
      "description": "Enable triggerProtect validation per exchangeInfo"
    },
    "close_position": {
      "type": "boolean",
      "default": false,
      "description": "Close entire position (don't pass quantity)"
    },
    "new_client_order_id": {
      "type": "string",
      "maxLength": 36,
      "description": "Unique client order ID (ULID format recommended, never reuse)"
    },
    "timestamp": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    }
  },
  "required": ["symbol", "order_type", "stop_price", "working_type", "new_client_order_id"],
  "additionalProperties": false
}
```

---

### Step 3: Create `schemas/bracket_error_v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.local/schemas/bracket_error_v1.json",
  "title": "Bracket Order API Error",
  "description": "TP/SL order rejection with diagnostic info (https://developers.binance.com/docs/usdm-derivatives/errors)",
  "type": "object",
  "properties": {
    "error_code": {
      "type": "string",
      "enum": ["-2021", "-4116", "-4137", "-4164"],
      "description": "Binance error code"
    },
    "error_message": {
      "type": "string",
      "description": "Binance error message"
    },
    "symbol": {
      "type": "string"
    },
    "order_type": {
      "type": "string"
    },
    "new_client_order_id": {
      "type": "string"
    },
    "attempted_stop_price": {
      "type": "number"
    },
    "current_mark_price": {
      "type": "number",
      "description": "Mark price at time of rejection"
    },
    "position_side": {
      "type": "string",
      "enum": ["LONG", "SHORT"]
    },
    "retry_count": {
      "type": "integer",
      "minimum": 0
    },
    "next_action": {
      "type": "string",
      "enum": ["retry_with_offset", "retry_with_new_id", "fallback_to_limit", "abandon"],
      "description": "Recommended recovery action"
    },
    "timestamp": {
      "type": "integer"
    }
  },
  "required": ["error_code", "symbol", "retry_count"],
  "additionalProperties": false
}
```

---

## Validation Checklist

- [ ] `contracts.py` compiles without syntax errors
- [ ] New enums visible: `WorkingType`, `BracketErrorCode`
- [ ] `BracketOrderPayload` validates `close_position=true` rules
- [ ] `TPSLValidationRules.validate_stop_price_for_side()` returns correct (bool, reason)
- [ ] `TPSLValidationRules.add_safety_offset()` returns Decimal
- [ ] `schemas/bracket_order_v1.json` validates via `jsonschema`
- [ ] `schemas/bracket_error_v1.json` validates via `jsonschema`
- [ ] All docstrings reference Binance official docs

---

## Quick Test (Python)

```python
from decimal import Decimal
from apps.reference.domains.execution_position.contracts import (
    TPSLValidationRules, BracketOrderPayload, WorkingType
)

# Test 1: Validation rules
result, reason = TPSLValidationRules.validate_stop_price_for_side(
    position_side="LONG",
    current_mark=Decimal("100"),
    stop_price=Decimal("105"),
    is_take_profit=True,
)
print(f"LONG TP=105 > mark=100: {result}")  # Should be True

# Test 2: Offset calculation
offset = TPSLValidationRules.add_safety_offset(
    current_price=Decimal("100"),
    tick_size=Decimal("0.01"),
    offset_bps=5,
)
print(f"Offset for $100 @ 5bps: {offset}")  # Should be 0.05 (0.05% = $0.05)

# Test 3: BracketOrderPayload validation
try:
    payload = BracketOrderPayload(
        symbol="ETHUSDT",
        side="BUY",
        qty=Decimal("1"),
        order_type="TAKE_PROFIT_MARKET",
        stop_price=Decimal("105"),
        close_position=True,
        working_type=WorkingType.MARK_PRICE,
    )
    print(f"✅ Payload created: {payload.symbol}")
except ValueError as e:
    print(f"❌ Validation error: {e}")

print("\n✅ Phase 1 ready for Phase 2!")
```

---

## Next Steps (Phase 2)

Once Phase 1 is merged:
1. Add `_calculate_bracket_prices_safe()` to `fsm_manage.py`
2. Add error handling to `binance_execution_adapter.py`
3. Add margin verification to `exposure_guard.py`

---

## References

- [Binance New Order API](https://developers.binance.com/docs/usdm-derivatives/trade/new-order)
- [Binance Error Codes](https://developers.binance.com/docs/usdm-derivatives/errors)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core.html)

---

**Ready?** Copy the code above into `contracts.py` and create the two schema files.
**Issues?** Check syntax with `python -m py_compile contracts.py`
