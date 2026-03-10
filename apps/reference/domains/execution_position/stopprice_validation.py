"""
EP-1102 stopPrice validation helpers.

SSOT for execution_position preflight and emission guards.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

CONDITIONAL_ORDER_TYPES: frozenset[str] = frozenset(
    {
        "STOP_MARKET",
        "TAKE_PROFIT_MARKET",
        "STOP",
        "TAKE_PROFIT",
        "TRAILING_STOP_MARKET",
    }
)

_INVALID_LITERAL_VALUES: frozenset[str] = frozenset(
    {"", "none", "nan", "null", "inf", "+inf", "-inf"}
)

# Reject absurd exponent values (e.g. "1e999999") as malformed for order placement.
_MAX_ABS_ADJUSTED_EXPONENT = 100


def parse_stop_price(value: Any) -> Optional[Decimal]:
    """Parse stopPrice into a finite positive Decimal, else return None."""
    if value is None:
        return None

    if isinstance(value, Decimal):
        parsed = value
    else:
        if isinstance(value, float) and not math.isfinite(value):
            return None

        text = str(value).strip()
        if text.lower() in _INVALID_LITERAL_VALUES:
            return None

        try:
            parsed = Decimal(text)
        except (InvalidOperation, TypeError, ValueError):
            return None

    if not parsed.is_finite() or parsed <= 0:
        return None

    if abs(parsed.adjusted()) > _MAX_ABS_ADJUSTED_EXPONENT:
        return None

    return parsed


def is_valid_stop_price(value: Any) -> bool:
    """Return True iff value parses as a finite positive Decimal."""
    return parse_stop_price(value) is not None


def format_ep1102_reason(symbol: Any, order_type: Any) -> str:
    """Build fail-closed EP-1102 reason with symbol+orderType and <=80 chars."""
    symbol_s = str(symbol).strip() if symbol is not None else "?"
    order_type_s = str(order_type).strip() if order_type is not None else "?"
    if not symbol_s:
        symbol_s = "?"
    if not order_type_s:
        order_type_s = "?"
    return f"EP-1102 missing stopPrice {symbol_s} {order_type_s}"[:80]
