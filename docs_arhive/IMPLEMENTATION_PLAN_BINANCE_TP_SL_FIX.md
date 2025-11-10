# 📋 IMPLEMENTATION PLAN: Binance TP/SL API Error Handling & Margin Fix

**Status**: In Progress
**Target**: Production-ready TP/SL on BOTH Testnet + Mainnet
**Priority**: CRITICAL (blocks trading)
**Deadline**: FSMP-P2-T08

---

## Executive Summary

### Problem Chain
1. **-2021 "Order would immediately trigger"**: TP/SL prices validated against `mark_price` in real-time. If price moved past target → rejected.
2. **Ghost Orders**: Failed TP/SL still reserved in `pending_exposure` → margin blocked → new trades fail.
3. **-4116 Duplicates**: Retry logic reuses `newClientOrderId` → duplicate error.
4. **Lost Margin**: No cleanup on rejection → manual intervention needed.

### Root Causes (by layer)
| Layer | Issue | Root Cause | Fix |
|-------|-------|-----------|-----|
| **API Validation** | -2021 rejection | `stopPrice` on wrong side of `mark_price` | Validate BEFORE submission; add offset |
| **Idempotency** | -4116 duplicate | Retry with same `newClientOrderId` | ULID per attempt; check before reusing |
| **Order Lifecycle** | Ghost orders | API rejected but tracked in `pending_exposure` | Listen to `ORDER_TRADE_UPDATE` + `CONDITIONAL_ORDER_TRIGGER_REJECT` |
| **Margin** | Accumulation | No cleanup on rejection | Auto-verify `totalOpenOrderInitialMargin` post-failure |
| **TP/SL Placement** | -4137 "quantity not allowed" | Passing `quantity` with `closePosition=true` | Don't send quantity; use `closePosition` alone |

---

## Phase 1: Research Findings → Code (CONTRACTS & SCHEMAS)

### 1.1 Update `contracts.py`

**New Enums & Constants**:

```python
# Order types (expand from existing)
class OrderType(str, Enum):
    # ... existing ...
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP = "STOP"

class WorkingType(str, Enum):
    """Price source for conditional order trigger validation"""
    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"

class BracketErrorCode(str, Enum):
    """API error codes specific to bracket/TP/SL orders"""
    WOULD_IMMEDIATELY_TRIGGER = "-2021"  # stopPrice on wrong side
    DUPLICATE_CLIENT_ORDER_ID = "-4116"  # newClientOrderId reused
    QUANTITY_NOT_ALLOWED = "-4137"  # Passing qty with closePosition=true
    MIN_NOTIONAL_NOT_MET = "-4164"  # Order notional too low

class TriggerType(str, Enum):
    """Trigger type for validation"""
    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"
    LIQUIDATION_PRICE = "LIQUIDATION_PRICE"
```

**Extended OrderPayload**:

```python
class BracketOrderPayload(OrderPayload):
    """TP/SL order with Binance-specific fields"""

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

    @field_validator("stop_price", mode="before")
    @classmethod
    def parse_stop_price(cls, v):
        if v is None:
            return None
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"stop_price must be valid Decimal: {e}")

    @model_validator(mode="after")
    def validate_bracket_rules(self):
        """Enforce Binance TP/SL rules"""
        # Rule 1: closePosition=true means NO quantity
        if self.close_position and self.qty is not None:
            raise ValueError(
                "closePosition=true cannot have quantity; use only closePosition"
            )

        # Rule 2: STOP_MARKET/TAKE_PROFIT_MARKET with closePosition=true must use MARK_PRICE
        if self.order_type in [OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET]:
            if self.close_position and self.working_type != WorkingType.MARK_PRICE:
                raise ValueError(
                    f"{self.order_type} with closePosition=true must use MARK_PRICE, "
                    f"got {self.working_type}"
                )

        # Rule 3: Must have stop_price for STOP/TAKE_PROFIT/STOP_MARKET/TAKE_PROFIT_MARKET
        conditional_types = [
            OrderType.STOP, OrderType.TAKE_PROFIT,
            OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET
        ]
        if self.order_type in conditional_types and self.stop_price is None:
            raise ValueError(f"{self.order_type} requires stop_price")

        return self
```

**TP/SL Validation Rules** (per Binance docs):

```python
class TPSLValidationRules:
    """
    Enforce Binance Futures TP/SL rules.

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    - stopPrice validation: https://developers.binance.com/docs/usdm-derivatives/trade/order-validator
    """

    @staticmethod
    def validate_stop_price_for_side(
        position_side: str,
        current_mark: Decimal,
        stop_price: Decimal,
        is_take_profit: bool,
    ) -> tuple[bool, str]:
        """
        Validate that stop_price is on correct side of current mark price.

        Args:
            position_side: "LONG" or "SHORT"
            current_mark: Current mark price from API
            stop_price: Target stop/TP price
            is_take_profit: True for TP, False for SL

        Returns:
            (is_valid: bool, reason: str)

        Rules:
            LONG + TP: stop_price > current_mark (price must go UP to trigger)
            LONG + SL: stop_price < current_mark (price must go DOWN to trigger)
            SHORT + TP: stop_price < current_mark (price must go DOWN to trigger)
            SHORT + SL: stop_price > current_mark (price must go UP to trigger)
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
            tick_size: Minimum price increment (from /exchangeInfo)
            offset_bps: Basis points (5 = 0.05% = 5 / 10000)

        Returns:
            offset: max(1 * tick_size, offset_bps% of price)

        Refs: Binance docs recommend adding delta to avoid -2021
        """
        min_offset = tick_size
        pct_offset = current_price * Decimal(offset_bps) / Decimal("10000")
        return max(min_offset, pct_offset)
```

### 1.2 Update JSON Schema

**File**: `schemas/bracket_order_v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.local/schemas/bracket_order_v1.json",
  "title": "Bracket Order (TP/SL)",
  "description": "Take-Profit and Stop-Loss orders per Binance Futures API",
  "type": "object",
  "properties": {
    "order_id": {
      "type": "string",
      "description": "Order ID from exchange"
    },
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
      "description": "Price source for trigger validation"
    },
    "price_protect": {
      "type": "boolean",
      "default": false,
      "description": "Enable triggerProtect validation"
    },
    "close_position": {
      "type": "boolean",
      "default": false,
      "description": "Close entire position (don't pass quantity)"
    },
    "new_client_order_id": {
      "type": "string",
      "maxLength": 36,
      "description": "Unique client order ID (ULID format recommended)"
    },
    "timestamp": {
      "type": "integer",
      "description": "Unix timestamp in milliseconds"
    },
    "status": {
      "type": "string",
      "enum": ["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"],
      "description": "Current order status"
    }
  },
  "required": ["symbol", "order_type", "stop_price", "working_type", "new_client_order_id"],
  "additionalProperties": false
}
```

**Error Response Schema**: `schemas/bracket_error_v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aurora.local/schemas/bracket_error_v1.json",
  "title": "Bracket Order API Error",
  "description": "TP/SL order rejection with diagnostic info",
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
      "enum": ["retry_with_offset", "fallback_to_limit", "abandon_bracket", "wait_and_retry"],
      "description": "Recommended recovery action"
    },
    "timestamp": {
      "type": "integer"
    }
  },
  "required": ["error_code", "symbol", "retry_count"]
}
```

---

## Phase 2: Price Validation Logic

### 2.1 Add to `fsm_manage.py`

**Method: `_calculate_bracket_prices_safe()`**

```python
def _calculate_bracket_prices_safe(
    self,
    entry_price: Decimal,
    position_side: str,
    mark_price: Decimal,
    tick_size: Decimal,
    risk_reward_ratio: float = 2.0,
    offset_bps: int = 5,
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[str]]:
    """
    Calculate TP/SL prices with safety validations per Binance rules.

    Args:
        entry_price: Entry fill price
        position_side: "LONG" or "SHORT"
        mark_price: Current mark price (from Binance API)
        tick_size: Minimum price increment
        risk_reward_ratio: TP distance / SL distance
        offset_bps: Basis points from mark (e.g., 5 = 0.05%)

    Returns:
        (sl_price, tp_price, error_msg)
        error_msg: None if success, string with reason if validation failed

    Binance Rules (from developers.binance.com):
    1. stopPrice must be on CORRECT SIDE of current mark_price
    2. stopPrice must be > MIN_OFFSET from mark (to avoid -2021)
    3. MARK_PRICE working type recommended for volatile assets
    4. priceProtect=true adds extra validation

    Refs: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
    """
    try:
        # Calculate base offset
        safety_offset = TPSLValidationRules.add_safety_offset(
            mark_price, tick_size, offset_bps
        )

        # Calculate SL and TP based on position side
        if position_side == "LONG":
            # LONG: SL below mark, TP above mark
            # SL: mark_price - offset
            sl_raw = mark_price - safety_offset
            # TP: mark_price + (offset * risk_reward_ratio)
            tp_raw = mark_price + (safety_offset * Decimal(str(risk_reward_ratio)))
        elif position_side == "SHORT":
            # SHORT: SL above mark, TP below mark
            # SL: mark_price + offset
            sl_raw = mark_price + safety_offset
            # TP: mark_price - (offset * risk_reward_ratio)
            tp_raw = mark_price - (safety_offset * Decimal(str(risk_reward_ratio)))
        else:
            return None, None, f"Invalid position_side: {position_side}"

        # Quantize to tick size
        sl_price = (sl_raw / tick_size).quantize(Decimal("1"), ROUND_DOWN) * tick_size
        tp_price = (tp_raw / tick_size).quantize(Decimal("1"), ROUND_DOWN) * tick_size

        # Validate rules
        valid_sl, msg_sl = TPSLValidationRules.validate_stop_price_for_side(
            position_side, mark_price, sl_price, is_take_profit=False
        )
        valid_tp, msg_tp = TPSLValidationRules.validate_stop_price_for_side(
            position_side, mark_price, tp_price, is_take_profit=True
        )

        if not valid_sl:
            return None, None, f"SL validation failed: {msg_sl}"
        if not valid_tp:
            return None, None, f"TP validation failed: {msg_tp}"

        logger.info(
            f"[ManageFlowFSM] ✅ Bracket prices calculated: "
            f"entry={entry_price}, mark={mark_price}, "
            f"SL={sl_price}, TP={tp_price}, side={position_side}"
        )
        return sl_price, tp_price, None

    except Exception as e:
        return None, None, f"Exception calculating brackets: {e}"
```

---

## Phase 3: Error Handling (Adapter Layer)

### 3.1 Add to `binance_execution_adapter.py`

**New Method: `_handle_bracket_order_error()`**

```python
def _handle_bracket_order_error(
    self,
    error_code: str,
    error_msg: str,
    payload: Dict[str, Any],
) -> tuple[str, Dict[str, Any]]:
    """
    Handle TP/SL-specific error codes with recovery strategy.

    Args:
        error_code: API error code (e.g., "-2021", "-4116")
        error_msg: API error message
        payload: Original order payload

    Returns:
        (next_action, recovery_info)
        next_action: "retry_with_offset" | "retry_with_new_id" | "fallback_to_limit" | "abandon"
        recovery_info: Dict with params for next attempt

    Refs: https://developers.binance.com/docs/usdm-derivatives/errors (error codes)
    """

    logger.error(
        f"[BinanceAdapter] 🔴 Bracket error {error_code}: {error_msg} | "
        f"symbol={payload.get('symbol')}, type={payload.get('order_type')}"
    )

    if error_code == "-2021":
        # "Order would immediately trigger"
        # Root cause: stopPrice on wrong side of mark_price or too close
        # Solution: Recalculate with larger offset

        logger.warning(
            f"[BinanceAdapter] -2021: stopPrice={payload.get('stop_price')} "
            f"is on wrong side or too close to mark. Recalculating..."
        )

        # Increase offset for retry
        current_offset_bps = payload.get("_offset_bps", 5)
        new_offset_bps = min(current_offset_bps + 5, 20)  # Up to 20 bps max

        recovery_info = {
            "offset_bps": new_offset_bps,
            "retry_delay_ms": 120,  # Start with 120ms
            "retry_count": payload.get("_retry_count", 0) + 1,
            "max_retries": 2,
        }

        if recovery_info["retry_count"] > recovery_info["max_retries"]:
            logger.error(
                f"[BinanceAdapter] -2021 persisted after {recovery_info['max_retries']} retries. "
                f"Falling back to LIMIT orders."
            )
            return "fallback_to_limit", recovery_info

        return "retry_with_offset", recovery_info

    elif error_code == "-4116":
        # "ClientOrderId is duplicated"
        # Root cause: newClientOrderId already used in open orders
        # Solution: Generate new ULID

        logger.warning(
            f"[BinanceAdapter] -4116: Duplicate newClientOrderId. "
            f"Generating new ULID..."
        )

        from vfoundation.core.idempotency import generate_ulid  # or use uuid4 + prefix

        recovery_info = {
            "new_client_order_id": f"AUR-{generate_ulid()}",
            "retry_delay_ms": 100,
            "retry_count": payload.get("_retry_count", 0) + 1,
            "max_retries": 3,
            "check_before_retry": True,  # Check GET /order first
        }

        if recovery_info["retry_count"] > recovery_info["max_retries"]:
            logger.error(
                f"[BinanceAdapter] -4116 persisted after {recovery_info['max_retries']} retries. "
                f"Abandoning TP/SL placement."
            )
            return "abandon", recovery_info

        return "retry_with_new_id", recovery_info

    elif error_code == "-4137":
        # "Quantity not allowed for closePosition=true"
        # Root cause: Passing quantity when closePosition=true
        # Solution: Remove quantity, use closePosition alone

        logger.warning(
            f"[BinanceAdapter] -4137: quantity passed with closePosition=true. "
            f"Retrying without quantity."
        )

        recovery_info = {
            "remove_quantity": True,
            "retry_delay_ms": 50,
        }

        return "retry_with_new_id", recovery_info  # Try again without qty

    elif error_code == "-4164":
        # "MIN_NOTIONAL not met"
        # Root cause: Order too small
        # Solution: Increase quantity or abandon

        logger.warning(
            f"[BinanceAdapter] -4164: Order notional too small. "
            f"Current: {payload.get('qty')} * {payload.get('price')}"
        )

        recovery_info = {
            "reason": "order_too_small",
            "action": "abandon",  # Can't increase without changing position size
        }

        return "abandon", recovery_info

    else:
        # Unknown error
        logger.error(f"[BinanceAdapter] ❓ Unknown bracket error {error_code}")
        return "abandon", {"reason": f"unknown_error_{error_code}"}


async def place_order_with_bracket_retry(
    self,
    msg: Message,
    max_retries: int = 3,
) -> Message:
    """
    Place TP/SL order with exponential backoff and error recovery.

    Args:
        msg: Order message with payload
        max_retries: Max retry attempts

    Returns:
        Response message (success or error)

    Flow:
        1. POST /fapi/v1/order
        2. On -2021: Recalculate, retry (up to 2x)
        3. On -4116: New ULID, check first, retry (up to 3x)
        4. On persistent failure: Fallback to LIMIT or abandon
    """

    payload = msg.pld.copy()
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Fetch fresh mark price
            mark_price = await self.get_mark_price(payload["symbol"])

            # Validate TP/SL prices
            if "stop_price" in payload and mark_price:
                valid, reason = TPSLValidationRules.validate_stop_price_for_side(
                    position_side=payload.get("position_side"),
                    current_mark=Decimal(str(mark_price)),
                    stop_price=Decimal(str(payload["stop_price"])),
                    is_take_profit=(payload["order_type"] == "TAKE_PROFIT_MARKET"),
                )

                if not valid:
                    logger.warning(f"[BinanceAdapter] Pre-flight validation failed: {reason}")
                    # Recalculate if offset-based issue
                    if "-2021-like" in reason:
                        payload["_offset_bps"] = payload.get("_offset_bps", 5) + 5
                        # Recalculate stop_price with new offset
                        # (call ManageFlowFSM._calculate_bracket_prices_safe)

            # Attempt POST /fapi/v1/order
            response = await self._post_order_with_auth(payload)

            if response.status_code == 200:
                logger.info(f"[BinanceAdapter] ✅ TP/SL order placed: {response.json()}")
                return Message(
                    op="EVT",
                    verb="ORDER_PLACED",
                    src="execution_position",
                    pld=response.json(),
                )

            elif response.status_code == 400:
                # Parse error
                error_data = response.json()
                error_code = str(error_data.get("code", ""))
                error_msg = error_data.get("msg", "")

                # Determine recovery action
                next_action, recovery_info = self._handle_bracket_order_error(
                    error_code, error_msg, payload
                )

                if next_action == "abandon":
                    logger.error(
                        f"[BinanceAdapter] ❌ Bracket order abandoned: {error_code} {error_msg}"
                    )
                    return Message(
                        op="EVT",
                        verb="BRACKET_ORDER_FAILED",
                        src="execution_position",
                        pld={"error_code": error_code, "error_msg": error_msg},
                    )

                elif next_action == "retry_with_offset":
                    # Wait and retry with new offset
                    await asyncio.sleep(recovery_info["retry_delay_ms"] / 1000.0)
                    payload["_offset_bps"] = recovery_info["offset_bps"]
                    payload["_retry_count"] = recovery_info["retry_count"]
                    retry_count += 1
                    continue

                elif next_action == "retry_with_new_id":
                    # Check old order first (idempotency)
                    if recovery_info.get("check_before_retry"):
                        old_result = await self._check_order_by_client_id(
                            payload.get("new_client_order_id")
                        )
                        if old_result:
                            logger.info(
                                f"[BinanceAdapter] Old order found on retry, returning it"
                            )
                            return Message(
                                op="EVT",
                                verb="ORDER_PLACED",
                                src="execution_position",
                                pld=old_result,
                            )

                    # New client ID
                    await asyncio.sleep(recovery_info["retry_delay_ms"] / 1000.0)
                    payload["new_client_order_id"] = recovery_info["new_client_order_id"]
                    payload["_retry_count"] = recovery_info["retry_count"]
                    if recovery_info.get("remove_quantity"):
                        del payload["qty"]
                    retry_count += 1
                    continue

                elif next_action == "fallback_to_limit":
                    # Convert to LIMIT order
                    logger.info(f"[BinanceAdapter] Falling back to LIMIT order")
                    payload["order_type"] = "LIMIT" if payload["order_type"] == "TAKE_PROFIT_MARKET" else "STOP"
                    payload["price"] = payload.get("stop_price")
                    payload["time_in_force"] = "GTC"
                    # Retry
                    await asyncio.sleep(200 / 1000.0)
                    retry_count += 1
                    continue

        except Exception as e:
            logger.exception(f"[BinanceAdapter] Exception in bracket retry: {e}")
            retry_count += 1
            await asyncio.sleep(250 / 1000.0)

    # Max retries exhausted
    logger.error(
        f"[BinanceAdapter] ❌ TP/SL order failed after {max_retries} retries"
    )
    return Message(
        op="EVT",
        verb="BRACKET_ORDER_FAILED",
        src="execution_position",
        pld={"reason": "max_retries_exceeded"},
    )
```

---

## Phase 4: Ghost Order Cleanup

### 4.1 Update `exposure_guard.py`

**Method: `verify_margin_after_error()`**

```python
async def verify_margin_after_error(
    self,
    symbol: str,
) -> Dict[str, Any]:
    """
    After a TP/SL API error, verify that margin was NOT reserved for failed order.

    Returns:
        {
            "total_open_order_initial_margin": Decimal,
            "expected_margin": Decimal,
            "ghost_orders": [list of unexpected orders],
            "action_taken": "none" | "cancel_all" | "manual_review",
        }

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/account/balance
    - Account V3: totalOpenOrderInitialMargin field
    """

    try:
        # Get account info from API
        account_info = await self.exchange_api.get_account()
        actual_margin = Decimal(str(account_info.get("totalOpenOrderInitialMargin", 0)))

        # Get open orders from cache
        expected_margin = self.pending_exposure + self.postfill_reservations

        logger.info(
            f"[ExposureGuard] 📊 Margin verification after error:\n"
            f"  actual (from API): {actual_margin}\n"
            f"  expected (cached): {expected_margin}\n"
            f"  diff: {actual_margin - expected_margin}"
        )

        if actual_margin < expected_margin:
            # Margin was NOT reserved for failed order (good!)
            logger.info(f"[ExposureGuard] ✅ No ghost margin reserved")
            return {
                "total_open_order_initial_margin": actual_margin,
                "expected_margin": expected_margin,
                "ghost_orders": [],
                "action_taken": "none",
            }

        elif actual_margin > expected_margin + Decimal("5"):  # 5 USDT tolerance
            # More margin reserved than expected (ghost orders!)
            logger.warning(
                f"[ExposureGuard] ⚠️ Extra margin detected: {actual_margin - expected_margin}"
            )

            # List open orders to find ghosts
            open_orders = await self.exchange_api.get_open_orders(symbol)
            tracked_order_ids = set(o.get("client_order_id") for o in self.pending_exposure_orders)
            ghost_orders = [
                o for o in open_orders
                if o.get("client_order_id") not in tracked_order_ids
            ]

            if ghost_orders:
                logger.error(
                    f"[ExposureGuard] 👻 Found {len(ghost_orders)} ghost orders:"
                )
                for g in ghost_orders:
                    logger.error(
                        f"  - {g.get('symbol')} {g.get('side')} {g.get('type')} "
                        f"@ {g.get('stopPrice')} (ID: {g.get('client_order_id')})"
                    )

                # Cancel all ghosts
                for g in ghost_orders:
                    await self.exchange_api.cancel_order(
                        symbol=g["symbol"],
                        order_id=g.get("order_id"),
                        orig_client_order_id=g.get("client_order_id"),
                    )

                logger.info(f"[ExposureGuard] Canceled {len(ghost_orders)} ghost orders")

            return {
                "total_open_order_initial_margin": actual_margin,
                "expected_margin": expected_margin,
                "ghost_orders": ghost_orders,
                "action_taken": "cancel_all",
            }

        else:
            logger.info(f"[ExposureGuard] ✅ Margin in sync")
            return {
                "total_open_order_initial_margin": actual_margin,
                "expected_margin": expected_margin,
                "ghost_orders": [],
                "action_taken": "none",
            }

    except Exception as e:
        logger.exception(f"[ExposureGuard] Exception verifying margin: {e}")
        return {
            "total_open_order_initial_margin": None,
            "expected_margin": expected_margin,
            "ghost_orders": [],
            "action_taken": "manual_review",
        }
```

---

## Phase 5: User Data Stream (Event Bus)

### 5.1 Update `aurora_log_adapter.py`

**Listen for NEW error events**:

```python
async def on_order_update(self, msg: Dict[str, Any]):
    """
    Handle ORDER_TRADE_UPDATE from Binance User Data Stream.

    Logs order lifecycle + automatically cleans up failed conditional orders.

    Events:
    - NEW: Order created (normal)
    - PARTIALLY_FILLED: Partial fill (track)
    - FILLED: Full fill (track)
    - CANCELED: User canceled (cleanup)
    - REJECTED: Exchange rejected (check for -2021/-4116)
    - TRADE_REJECTED: Trade rejected (rare, similar to REJECTED)

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/user-data-streams/user-data-stream-details
    - ORDER_TRADE_UPDATE event format
    """

    try:
        order = msg.get("o", {})
        order_type = order.get("o")  # NEW, CANCELED, FILLED, etc.
        symbol = order.get("s")
        order_id = order.get("i")
        client_order_id = order.get("c")
        status = order.get("X")  # NEW, PARTIALLY_FILLED, FILLED, CANCELED
        reason = order.get("x")  # TRADE (for FILLED), usually for status field

        logger.info(
            f"[AuroraLogAdapter] 📨 ORDER_TRADE_UPDATE: "
            f"{symbol} {status} id={order_id} c_id={client_order_id}"
        )

        # Specific handling for REJECTED (if received as event)
        if status == "REJECTED":
            reason_code = order.get("sr")  # Reject reason code
            logger.error(
                f"[AuroraLogAdapter] ❌ ORDER REJECTED: "
                f"symbol={symbol}, c_id={client_order_id}, code={reason_code}"
            )

            # Emit BRACKET_ORDER_FAILED event to FSM
            await self.emit_message(
                Message(
                    op="EVT",
                    verb="BRACKET_ORDER_FAILED",
                    src="aurora_log_adapter",
                    pld={
                        "symbol": symbol,
                        "client_order_id": client_order_id,
                        "reject_reason": reason_code,
                        "order_id": order_id,
                    },
                )
            )

        # Track for margin verification
        if status in ["FILLED", "CANCELED"]:
            # Remove from pending
            self.remove_pending_order(client_order_id)
        elif status == "NEW":
            # Track as pending
            self.add_pending_order(
                client_order_id=client_order_id,
                symbol=symbol,
                order_id=order_id,
            )

    except Exception as e:
        logger.exception(f"[AuroraLogAdapter] Exception in order update: {e}")


async def on_conditional_order_trigger_reject(self, msg: Dict[str, Any]):
    """
    Handle CONDITIONAL_ORDER_TRIGGER_REJECT from User Data Stream.

    This event is sent when a conditional order (e.g., STOP_MARKET) is rejected
    by the exchange AFTER the trigger condition is met (but before execution).

    Most common causes:
    - -2021: stopPrice on wrong side of current price
    - -4137: Quantity not allowed with closePosition=true
    - -1000: Internal exchange error

    Refs:
    - https://developers.binance.com/docs/usdm-derivatives/user-data-streams/user-data-stream-details
    - CONDITIONAL_ORDER_TRIGGER_REJECT event
    """

    try:
        event = msg.get("o", {})
        symbol = event.get("s")
        client_order_id = event.get("c")
        order_id = event.get("i")
        reject_reason = event.get("rj")  # Reject reason code
        trigger_type = event.get("tt")  # Trigger type (e.g., "MARK_PRICE")

        logger.error(
            f"[AuroraLogAdapter] 🚫 CONDITIONAL_ORDER_TRIGGER_REJECT: "
            f"{symbol} c_id={client_order_id} reason={reject_reason} trigger={trigger_type}"
        )

        # Remove from pending (order won't execute)
        self.remove_pending_order(client_order_id)

        # Emit to FSM for margin cleanup
        await self.emit_message(
            Message(
                op="EVT",
                verb="BRACKET_ORDER_TRIGGER_REJECT",
                src="aurora_log_adapter",
                pld={
                    "symbol": symbol,
                    "client_order_id": client_order_id,
                    "order_id": order_id,
                    "reject_reason": reject_reason,
                    "trigger_type": trigger_type,
                },
            )
        )

        # Schedule margin verification
        asyncio.create_task(
            self.verify_margin_after_error(symbol)
        )

    except Exception as e:
        logger.exception(
            f"[AuroraLogAdapter] Exception in conditional trigger reject: {e}"
        )
```

---

## Phase 6-8: Testing, Documentation, Deployment

### 6.1 Test Structure (TDD)

**File**: `test_bracket_orders_api_errors.py`

```python
"""
Test suite for Binance TP/SL API error handling.

Covers:
- -2021 "Order would immediately trigger" (retry with offset)
- -4116 "ClientOrderId is duplicated" (ULID retry)
- -4137 "Quantity not allowed" (remove qty)
- -4164 "MIN_NOTIONAL" (abandon)
- Ghost order cleanup
- Testnet vs Mainnet consistency
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.contracts import (
    BracketOrderPayload, WorkingType, TPSLValidationRules
)

class Test_2021_WouldImmediatelyTrigger:
    """Error -2021: stopPrice on wrong side or too close to mark."""

    @pytest.mark.asyncio
    async def test_long_tp_above_mark_valid(self):
        """LONG TP must be above current mark price."""
        result, reason = TPSLValidationRules.validate_stop_price_for_side(
            position_side="LONG",
            current_mark=Decimal("100"),
            stop_price=Decimal("105"),
            is_take_profit=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_long_tp_below_mark_invalid(self):
        """LONG TP below mark should fail (would immediately trigger)."""
        result, reason = TPSLValidationRules.validate_stop_price_for_side(
            position_side="LONG",
            current_mark=Decimal("100"),
            stop_price=Decimal("95"),
            is_take_profit=True,
        )
        assert result is False
        assert "must be >" in reason

    @pytest.mark.asyncio
    async def test_short_tp_below_mark_valid(self):
        """SHORT TP must be below current mark price."""
        result, reason = TPSLValidationRules.validate_stop_price_for_side(
            position_side="SHORT",
            current_mark=Decimal("100"),
            stop_price=Decimal("95"),
            is_take_profit=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_offset_calculation(self):
        """Offset should be max(tickSize, offset_bps%)."""
        mark = Decimal("100")
        tick_size = Decimal("0.01")
        offset_bps = 5  # 0.05%

        offset = TPSLValidationRules.add_safety_offset(mark, tick_size, offset_bps)

        expected_pct = Decimal("100") * Decimal("5") / Decimal("10000")
        expected = max(tick_size, expected_pct)

        assert offset == expected

    @pytest.mark.asyncio
    async def test_calculate_brackets_long_position(self):
        """Calculate brackets for LONG position."""
        fsm = ManageFlowFSM()
        entry_price = Decimal("100")
        mark_price = Decimal("100.5")
        tick_size = Decimal("0.01")

        sl, tp, err = fsm._calculate_bracket_prices_safe(
            entry_price=entry_price,
            position_side="LONG",
            mark_price=mark_price,
            tick_size=tick_size,
            risk_reward_ratio=2.0,
            offset_bps=5,
        )

        assert err is None
        assert sl < mark_price  # SL below mark
        assert tp > mark_price  # TP above mark
        assert (tp - mark_price) > (mark_price - sl)  # 2:1 reward:risk

# ... more tests for -4116, -4137, -4164, ghost orders, etc.
```

### 7.1 Documentation

**File**: `docs/BRACKET_ORDERS_RUNBOOK.md`

```markdown
# 🔧 TP/SL Bracket Orders Runbook

## Quick Reference

| Error | Meaning | Action | Retry |
|-------|---------|--------|-------|
| **-2021** | Price on wrong side | Recalculate + offset ↑ | 2x (120–250 ms) |
| **-4116** | Duplicate client ID | New ULID + check first | 3x (100 ms) |
| **-4137** | Quantity with closePos | Remove qty, retry | 1x |
| **-4164** | Order too small | Abandon (can't increase pos) | No |

## Monitoring

Watch these metrics:
- `bracket_order_error_rate`: Target < 5%
- `retry_success_rate`: Target > 90%
- `ghost_order_cleanup_time`: Target < 5 sec
- `margin_utilization_jitter`: Target < 2%

## Alerts

Trigger if:
- 3+ consecutive -2021 errors → Increase offset config
- totalOpenOrderInitialMargin > 105% of expected → Manual review
- Bracket retry exhaustion rate > 10% → Fallback to LIMIT mode

## References

- Binance API Error Codes: https://developers.binance.com/docs/usdm-derivatives/errors
- TP/SL Order Rules: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
- Account Margin: https://developers.binance.com/docs/usdm-derivatives/account/balance
```

---

## Commit Strategy (Conventional Commits)

```
fix(execution_position): add TP/SL API error handling (-2021/-4116) [FSMP-P2-T08]
- Add TPSLValidationRules in contracts.py
- Implement retry logic in binance_execution_adapter.py
- Add MARK_PRICE validation before submission
- Update exposure_guard.py for ghost order cleanup

Refs: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
```

---

## Success Criteria

✅ **Acceptance**:
- [ ] TP/SL success rate > 95% on Testnet
- [ ] Zero ghost orders after 5s cleanup
- [ ] Margin never blocked for > 1s post-error
- [ ] No manual intervention needed for -2021/-4116
- [ ] Testnet behavior = Mainnet behavior (offline-testable)
- [ ] 90% code coverage on bracket logic
- [ ] Runbook + monitoring dashboards active

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1–2 | 1–2h | Contracts + validation rules |
| 3 | 1–2h | Error handling + retry |
| 4–5 | 1–2h | Cleanup + event bus |
| 6 | 1–2h | Schemas |
| 7 | 2–3h | Tests + fixtures |
| 8 | 1–2h | Docs + runbook |
| **Total** | **8–13h** | Production-ready |

---

## Current Status

📊 **Phase**: 1 (Research findings → Code integration)
🔍 **Focus**: Adding contracts + TPSLValidationRules
📅 **Due**: FSMP-P2-T08 (this sprint)
👤 **Owner**: @copilot (automated)

---

## References (Binance Official)

1. **New Order (Futures)**: https://developers.binance.com/docs/usdm-derivatives/trade/new-order
2. **Error Codes**: https://developers.binance.com/docs/usdm-derivatives/errors
3. **Account Info V3**: https://developers.binance.com/docs/usdm-derivatives/account/balance
4. **User Data Streams**: https://developers.binance.com/docs/usdm-derivatives/user-data-streams/user-data-stream-details
5. **ExchangeInfo (triggerProtect)**: https://developers.binance.com/docs/usdm-derivatives/market-data/exchange-information

---

**Last Updated**: 2025-11-07
**Prepared By**: GitHub Copilot
**Status**: ✅ Ready for Phase 1 Implementation
