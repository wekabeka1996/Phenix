"""Additive numeric contract helpers for Phase 8A.

Phase 8A keeps the current numeric SSOT in ``execution_position.contracts``.
This module mirrors that contract surface without changing any hot-path imports.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any

from apps.reference.domains.execution_position.contracts import (
    MAX_ORDER_QTY,
    MAX_PRICE,
    MIN_NOTIONAL,
    MIN_ORDER_QTY,
    MIN_PRICE,
    PRICE_STEP,
    QTY_STEP,
)


def parse_decimal(value: Any, *, field_name: str = "value") -> Decimal:
    """Parse a numeric-like value into ``Decimal`` with stable error text."""
    if value is None:
        raise ValueError(f"{field_name} cannot be None")
    try:
        if isinstance(value, str):
            value = value.strip()
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be valid number: {exc}") from exc


def quantize_qty(value: Any) -> Decimal:
    """Round quantity down to the current EP lot-size step."""
    return parse_decimal(value, field_name="qty").quantize(
        QTY_STEP,
        rounding=ROUND_DOWN,
    )


def quantize_price(value: Any) -> Decimal:
    """Round price down to the current EP price tick step."""
    return parse_decimal(value, field_name="price").quantize(
        PRICE_STEP,
        rounding=ROUND_DOWN,
    )


def validate_qty(value: Any) -> Decimal:
    """Validate quantity bounds using the current EP numeric contract."""
    qty = quantize_qty(value)
    if qty < MIN_ORDER_QTY:
        raise ValueError(f"qty must be >= {MIN_ORDER_QTY}")
    if qty > MAX_ORDER_QTY:
        raise ValueError(f"qty must be <= {MAX_ORDER_QTY}")
    if qty <= 0:
        raise ValueError(f"qty after quantization must be > 0 (got {qty})")
    return qty


def validate_price(value: Any) -> Decimal:
    """Validate price bounds using the current EP numeric contract."""
    price = quantize_price(value)
    if price < MIN_PRICE:
        raise ValueError(f"price must be >= {MIN_PRICE}")
    if price > MAX_PRICE:
        raise ValueError(f"price must be <= {MAX_PRICE}")
    if price <= 0:
        raise ValueError(f"price after quantization must be > 0 (got {price})")
    return price


__all__ = [
    "MAX_ORDER_QTY",
    "MAX_PRICE",
    "MIN_NOTIONAL",
    "MIN_ORDER_QTY",
    "MIN_PRICE",
    "PRICE_STEP",
    "QTY_STEP",
    "parse_decimal",
    "quantize_price",
    "quantize_qty",
    "validate_price",
    "validate_qty",
]
