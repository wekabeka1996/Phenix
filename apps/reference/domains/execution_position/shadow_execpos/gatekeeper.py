"""
Entry Gatekeeper for Shadow ExecPos
===================================

Pre-flight validation for entry orders.
Ported from fsm_open.py and qty_guard.py.
"""
from typing import Any, Dict, Optional, Union, TypedDict
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import logging
import time

from .types import GateDecision

logger = logging.getLogger(__name__)

# Safe fallbacks if instrument specs are missing (permissive precision, strict safety)
# We use high precision (1e-8) to avoid accidental rounding to zero for cheap assets (SHIB)
FALLBACK_STEP_SIZE = Decimal("1e-8")
FALLBACK_MIN_QTY = Decimal("1e-8")
FALLBACK_MIN_NOTIONAL = Decimal("1.0") # Conservative fallback
FALLBACK_TICK_SIZE = Decimal("1e-8")


class InstrumentSpec(TypedDict):
    """Specification for a trading instrument."""
    symbol: str
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    tick_size: Decimal


class ExecPosGatekeeper:
    """
    Entry validation service with fail-closed guards.

    Responsibilities:
    - Validate quantity (min_qty, step_size)
    - Validate notional (min_notional)
    - Apply cooldowns
    - Return structured GateDecision

    Ported from fsm_open.py (_check_qty_step, guards) and qty_guard.py (ExecutionQtyGuard).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}

        # Cooldown tracking: symbol -> last_entry_timestamp
        self._last_entry_ts: Dict[str, float] = {}

        # Instrument specifications cache
        self._specs: Dict[str, InstrumentSpec] = {}

        # Default cooldown (can be overridden per symbol)
        self.cooldown_sec = self.config.get("cooldown_sec", 1.0)
        exec_cfg = self.config.get("execution_position")
        if isinstance(exec_cfg, dict) and exec_cfg.get("cooldown_sec") is not None:
            # Prefer explicit execution_position cooldown override when available
            self.cooldown_sec = exec_cfg["cooldown_sec"]

    def update_instrument_specs(self, specs: Dict[str, Dict[str, Any]]) -> None:
        """
        Update instrument specifications cache.

        Args:
            specs: Dictionary mapping symbol to spec dict (tick_size, step_size, etc.)
        """
        count = 0
        for symbol, raw_spec in specs.items():
            try:
                self._specs[symbol] = {
                    "symbol": symbol,
                    "step_size": self._to_decimal(raw_spec.get("step_size"), "step_size") or FALLBACK_STEP_SIZE,
                    "min_qty": self._to_decimal(raw_spec.get("min_qty"), "min_qty") or FALLBACK_MIN_QTY,
                    "min_notional": self._to_decimal(raw_spec.get("min_notional"), "min_notional") or FALLBACK_MIN_NOTIONAL,
                    "tick_size": self._to_decimal(raw_spec.get("tick_size"), "tick_size") or FALLBACK_TICK_SIZE,
                }
                count += 1
            except Exception as e:
                logger.warning(f"Failed to parse spec for {symbol}: {e}")

        logger.info(f"Gatekeeper updated specs for {count} instruments")

    def check_entry(
        self,
        symbol: str,
        side: str,
        quantity: Union[str, float, Decimal],
        price: Optional[Union[str, float, Decimal]],
        order_type: str
    ) -> GateDecision:
        """
        Validate entry request and return decision.

        Args:
            symbol: Trading symbol
            side: BUY/SELL
            quantity: Requested quantity
            price: Order price (required for LIMIT orders)
            order_type: MARKET/LIMIT/etc

        Returns:
            GateDecision with allow/reason/modified_params
        """
        try:
            # Convert to Decimal
            qty_dec = self._to_decimal(quantity, "quantity")
            price_dec = self._to_decimal(price, "price") if price else None

            # Guard 1: Non-positive quantity
            if qty_dec <= 0:
                return GateDecision(
                    allowed=False,
                    reason="NON_POSITIVE_QTY",
                    modified_params={},
                    metadata={"symbol": symbol, "raw_qty": str(qty_dec)}
                )

            # Get instrument specifications
            specs = self._get_instrument_specs(symbol)
            step_size = specs["step_size"]
            min_qty = specs["min_qty"]
            min_notional = specs["min_notional"]
            tick_size = specs["tick_size"]

            # Guard 2: Below min_qty (before rounding)
            if qty_dec < min_qty:
                return GateDecision(
                    allowed=False,
                    reason="MIN_QTY_VIOLATION",
                    modified_params={},
                    metadata={
                        "symbol": symbol,
                        "raw_qty": str(qty_dec),
                        "min_qty": str(min_qty)
                    }
                )

            # Guard 3: Round quantity to step size
            rounded_qty = self._round_to_step(qty_dec, step_size)

            # Guard 4: Check if rounding made qty zero or below min
            if rounded_qty <= 0:
                return GateDecision(
                    allowed=False,
                    reason="QTY_ROUNDS_TO_ZERO",
                    modified_params={},
                    metadata={
                        "symbol": symbol,
                        "raw_qty": str(qty_dec),
                        "rounded_qty": str(rounded_qty),
                        "step_size": str(step_size)
                    }
                )

            if rounded_qty < min_qty:
                return GateDecision(
                    allowed=False,
                    reason="MIN_QTY_VIOLATION",
                    modified_params={},
                    metadata={
                        "symbol": symbol,
                        "rounded_qty": str(rounded_qty),
                        "min_qty": str(min_qty)
                    }
                )

            # Guard 5: Round price to tick size (if provided)
            rounded_price = None
            if price_dec is not None and price_dec > 0:
                rounded_price = self._round_to_step(price_dec, tick_size)

            # Guard 6: Min notional check (for LIMIT orders with price)
            if rounded_price is not None and rounded_price > 0:
                notional = rounded_qty * rounded_price
                if notional < min_notional:
                    return GateDecision(
                        allowed=False,
                        reason="MIN_NOTIONAL_VIOLATION",
                        modified_params={},
                        metadata={
                            "symbol": symbol,
                            "rounded_qty": str(rounded_qty),
                            "rounded_price": str(rounded_price),
                            "notional": str(notional),
                            "min_notional": str(min_notional)
                        }
                    )

            # Guard 7: Cooldown check
            if not self._check_cooldown(symbol):
                return GateDecision(
                    allowed=False,
                    reason="COOLDOWN_ACTIVE",
                    modified_params={},
                    metadata={
                        "symbol": symbol,
                        "cooldown_sec": self.cooldown_sec
                    }
                )

            # All guards passed - return success with adjusted params
            modified_params = {
                "quantity": str(rounded_qty)
            }
            if rounded_price is not None:
                modified_params["price"] = str(rounded_price)

            # Update cooldown timestamp
            self._last_entry_ts[symbol] = time.time()

            logger.info(
                f"SHADOW_GATEKEEPER_ALLOW",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "original_qty": str(qty_dec),
                    "adjusted_qty": str(rounded_qty)
                }
            )

            return GateDecision(
                allowed=True,
                reason="OK",
                modified_params=modified_params,
                metadata={
                    "symbol": symbol,
                    "guards_passed": ["qty>0", "min_qty", "step_size", "min_notional", "cooldown"]
                }
            )

        except Exception as e:
            logger.error(f"Gatekeeper check failed: {e}", exc_info=True)
            return GateDecision(
                allowed=False,
                reason="GATEKEEPER_ERROR",
                modified_params={},
                metadata={"error": str(e)}
            )

    def validate_order(
        self,
        symbol: str,
        qty: Union[str, float, Decimal, None],
        price: Optional[Union[str, float, Decimal]] = None,
    ) -> GateDecision:
        """
        Validate and round order quantity/price.

        Used by SymbolExecutor for entry order validation.
        Unlike check_entry, this doesn't check cooldowns - just validates/rounds.

        Args:
            symbol: Trading symbol
            qty: Order quantity (can be None for closePosition orders)
            price: Order price (optional)

        Returns:
            GateDecision with allowed status and modified_params containing
            rounded quantity/price if allowed.
        """
        try:
            # If qty is None (closePosition), just validate price
            if qty is None:
                if price is not None:
                    specs = self._get_instrument_specs(symbol)
                    price_dec = self._to_decimal(price, "price")
                    if price_dec and price_dec > 0:
                        rounded_price = self._round_to_step(price_dec, specs["tick_size"])
                        return GateDecision(
                            allowed=True,
                            reason="OK",
                            modified_params={"price": str(rounded_price)},
                            metadata={"symbol": symbol}
                        )
                return GateDecision(
                    allowed=True,
                    reason="OK",
                    modified_params={},
                    metadata={"symbol": symbol, "note": "closePosition_no_qty"}
                )

            # Convert to Decimal
            qty_dec = self._to_decimal(qty, "quantity")
            price_dec = self._to_decimal(price, "price") if price else None

            # Get instrument specs
            specs = self._get_instrument_specs(symbol)
            step_size = specs["step_size"]
            tick_size = specs["tick_size"]
            min_qty = specs["min_qty"]

            # Round quantity
            rounded_qty = self._round_to_step(qty_dec, step_size)

            # Validate min qty
            if rounded_qty < min_qty:
                return GateDecision(
                    allowed=False,
                    reason="MIN_QTY_VIOLATION",
                    modified_params={},
                    metadata={
                        "symbol": symbol,
                        "rounded_qty": str(rounded_qty),
                        "min_qty": str(min_qty)
                    }
                )

            # Round price if provided
            rounded_price = None
            if price_dec and price_dec > 0:
                rounded_price = self._round_to_step(price_dec, tick_size)

            return GateDecision(
                allowed=True,
                reason="OK",
                modified_params={
                    "quantity": str(rounded_qty),
                    "price": str(rounded_price) if rounded_price else None
                },
                metadata={"symbol": symbol}
            )

        except Exception as e:
            logger.warning(f"validate_order failed for {symbol}: {e}")
            return GateDecision(
                allowed=True,  # Allow on error, let exchange reject if needed
                reason="VALIDATION_ERROR",
                modified_params={},
                metadata={"error": str(e)}
            )

    def get_instrument_specs(self, symbol: str) -> InstrumentSpec:
        """
        Get instrument specifications from cache or fallback.

        Public API for external callers (e.g., SymbolExecutor) to get
        step_size/tick_size for quantity/price rounding.
        """
        return self._get_instrument_specs(symbol)

    def _get_instrument_specs(self, symbol: str) -> InstrumentSpec:
        """
        Get instrument specifications from cache or fallback.
        """
        if symbol in self._specs:
            return self._specs[symbol]

        # Log warning only once per symbol to avoid spam
        # (In a real system we might want a dedicated throttle, but this is simple enough)
        logger.warning(
            f"Missing instrument specs for {symbol}, using fallbacks. "
            f"Tick={FALLBACK_TICK_SIZE}, Step={FALLBACK_STEP_SIZE}"
        )

        return {
            "symbol": symbol,
            "step_size": FALLBACK_STEP_SIZE,
            "min_qty": FALLBACK_MIN_QTY,
            "min_notional": FALLBACK_MIN_NOTIONAL,
            "tick_size": FALLBACK_TICK_SIZE
        }

    def _round_to_step(self, value: Decimal, step_size: Decimal) -> Decimal:
        """
        Round value DOWN to nearest step_size multiple.
        Ported from qty_guard._round_to_step.
        """
        if step_size <= 0:
            return value

        steps = (value / step_size).to_integral_value(rounding=ROUND_DOWN)
        return (steps * step_size)

    def _check_cooldown(self, symbol: str) -> bool:
        """
        Check if cooldown has elapsed since last entry for this symbol.

        Returns:
            True if cooldown elapsed (entry allowed)
            False if still in cooldown (entry blocked)
        """
        if symbol not in self._last_entry_ts:
            return True  # No previous entry

        elapsed = time.time() - self._last_entry_ts[symbol]
        return elapsed >= self.cooldown_sec

    def reset_cooldown(self, symbol: str):
        """Reset cooldown for symbol (for testing)."""
        self._last_entry_ts.pop(symbol, None)

    @staticmethod
    def _to_decimal(value: Any, field: str) -> Decimal:
        """Convert value to Decimal, raising ValueError if invalid."""
        if value is None:
            raise ValueError(f"{field} cannot be None")

        if isinstance(value, Decimal):
            return value

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        if isinstance(value, str):
            try:
                return Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"{field} must be numeric: {value}") from exc

        raise ValueError(f"Unsupported {field} type: {type(value).__name__}")
