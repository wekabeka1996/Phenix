"""
TASK50: Quantity Normalization Contract.

Single source of truth for quantity normalization before order placement.
Implements Binance LOT_SIZE / MIN_QTY / MIN_NOTIONAL validation with fail-closed semantics.

Rules (strict, no silent bump-ups):
1. rounded_qty = floor(raw_qty / step_size) * step_size (ROUND_DOWN)
2. if rounded_qty <= 0 → fail-closed (NRR-QTY-ROUNDED-TO-ZERO)
3. if rounded_qty < min_qty → fail-closed (NRR-QTY-BELOW-MIN_QTY)
4. if min_notional is set and rounded_qty * price < min_notional → fail-closed (NRR-NOTIONAL-BELOW-MIN)
5. return ok=True only when all pass

NO BUMP-UPS. If user wants minQty bump — must be explicit policy, not silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from apps.reference.domains.execution_position.exchange_filter_cache import (
    ExchangeFilterSnapshot,
)


@dataclass
class QtyNormalizeResult:
    """Result of quantity normalization."""

    ok: bool
    qty: Optional[Decimal]
    why: str  # <= 80 chars, NRR code or empty
    raw_qty: Decimal
    rounded_qty: Optional[Decimal]
    step_size: Decimal
    min_qty: Decimal
    min_notional: Optional[Decimal]
    price: Decimal
    notional: Optional[Decimal] = field(default=None)

    def to_dict(self) -> dict:
        """Convert to dict for logging."""
        return {
            "ok": self.ok,
            "qty": str(self.qty) if self.qty else None,
            "why": self.why,
            "raw_qty": str(self.raw_qty),
            "rounded_qty": str(self.rounded_qty) if self.rounded_qty else None,
            "step_size": str(self.step_size),
            "min_qty": str(self.min_qty),
            "min_notional": str(self.min_notional) if self.min_notional else None,
            "price": str(self.price),
            "notional": str(self.notional) if self.notional else None,
        }


# NRR codes for quantity normalization failures
NRR_QTY_ROUNDED_TO_ZERO = "NRR-QTY-ROUNDED-TO-ZERO"
NRR_QTY_BELOW_MIN_QTY = "NRR-QTY-BELOW-MIN_QTY"
NRR_NOTIONAL_BELOW_MIN = "NRR-NOTIONAL-BELOW-MIN"
NRR_INVALID_INPUT = "NRR-QTY-INVALID-INPUT"


def _to_decimal(value) -> Decimal:
    """Safely convert value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Cannot convert {type(value)} to Decimal")


def normalize_qty(
    *,
    raw_qty: Decimal | float | str,
    price: Decimal | float | str,
    step_size: Decimal | float | str,
    min_qty: Decimal | float | str,
    min_notional: Optional[Decimal | float | str] = None,
) -> QtyNormalizeResult:
    """
    Normalize quantity according to Binance LOT_SIZE / MIN_QTY / MIN_NOTIONAL filters.

    Implements fail-closed semantics: returns ok=False with NRR code on any violation.
    NO SILENT BUMP-UPS.

    Args:
        raw_qty: Raw quantity from sizing calculation
        price: Current price for notional calculation
        step_size: LOT_SIZE stepSize from exchange
        min_qty: LOT_SIZE minQty from exchange
        min_notional: MIN_NOTIONAL notional from exchange (optional)

    Returns:
        QtyNormalizeResult with ok=True if valid, ok=False with why code if not.

    Examples:
        >>> result = normalize_qty(raw_qty=1.029, price=100, step_size=0.01, min_qty=0.01)
        >>> result.ok, result.qty  # True, Decimal('1.02')

        >>> result = normalize_qty(raw_qty=0.27, price=150, step_size=1, min_qty=1)
        >>> result.ok, result.why  # False, 'NRR-QTY-BELOW-MIN_QTY'
    """
    # Convert inputs to Decimal
    try:
        raw_qty_d = _to_decimal(raw_qty)
        price_d = _to_decimal(price)
        step_size_d = _to_decimal(step_size)
        min_qty_d = _to_decimal(min_qty)
        min_notional_d = _to_decimal(min_notional) if min_notional is not None else None
    except (ValueError, TypeError) as e:
        return QtyNormalizeResult(
            ok=False,
            qty=None,
            why=NRR_INVALID_INPUT,
            raw_qty=Decimal("0"),
            rounded_qty=None,
            step_size=Decimal("0"),
            min_qty=Decimal("0"),
            min_notional=None,
            price=Decimal("0"),
            notional=None,
        )

    # Validate step_size > 0
    if step_size_d <= 0:
        return QtyNormalizeResult(
            ok=False,
            qty=None,
            why=NRR_INVALID_INPUT,
            raw_qty=raw_qty_d,
            rounded_qty=None,
            step_size=step_size_d,
            min_qty=min_qty_d,
            min_notional=min_notional_d,
            price=price_d,
            notional=None,
        )

    # Rule 1: rounded_qty = floor(raw_qty / step_size) * step_size
    # Using Decimal quantize with ROUND_DOWN
    steps = (raw_qty_d / step_size_d).quantize(Decimal("1"), rounding=ROUND_DOWN)
    rounded_qty = steps * step_size_d

    # Rule 2: if rounded_qty <= 0 → fail-closed
    if rounded_qty <= 0:
        return QtyNormalizeResult(
            ok=False,
            qty=None,
            why=NRR_QTY_ROUNDED_TO_ZERO,
            raw_qty=raw_qty_d,
            rounded_qty=rounded_qty,
            step_size=step_size_d,
            min_qty=min_qty_d,
            min_notional=min_notional_d,
            price=price_d,
            notional=None,
        )

    # Rule 3: if rounded_qty < min_qty → fail-closed
    if rounded_qty < min_qty_d:
        return QtyNormalizeResult(
            ok=False,
            qty=None,
            why=NRR_QTY_BELOW_MIN_QTY,
            raw_qty=raw_qty_d,
            rounded_qty=rounded_qty,
            step_size=step_size_d,
            min_qty=min_qty_d,
            min_notional=min_notional_d,
            price=price_d,
            notional=rounded_qty * price_d,
        )

    # Calculate notional
    notional = rounded_qty * price_d

    # Rule 4: if min_notional is set and notional < min_notional → fail-closed
    if min_notional_d is not None and notional < min_notional_d:
        return QtyNormalizeResult(
            ok=False,
            qty=None,
            why=NRR_NOTIONAL_BELOW_MIN,
            raw_qty=raw_qty_d,
            rounded_qty=rounded_qty,
            step_size=step_size_d,
            min_qty=min_qty_d,
            min_notional=min_notional_d,
            price=price_d,
            notional=notional,
        )

    # Rule 5: All checks passed
    return QtyNormalizeResult(
        ok=True,
        qty=rounded_qty,
        why="",
        raw_qty=raw_qty_d,
        rounded_qty=rounded_qty,
        step_size=step_size_d,
        min_qty=min_qty_d,
        min_notional=min_notional_d,
        price=price_d,
        notional=notional,
    )


def normalize_qty_with_filter(
    *,
    raw_qty: Decimal | float | str,
    price: Decimal | float | str,
    exchange_filter: ExchangeFilterSnapshot,
) -> QtyNormalizeResult:
    """Normalize quantity from the current exchange filter snapshot."""
    return normalize_qty(
        raw_qty=raw_qty,
        price=price,
        step_size=exchange_filter.step_size,
        min_qty=exchange_filter.min_qty,
        min_notional=exchange_filter.min_notional,
    )


def verify_ack_qty(
    sent_qty: Decimal | float | str,
    ack_qty: Decimal | float | str,
    step_size: Decimal | float | str,
) -> tuple[bool, str]:
    """
    Verify that exchange ACK quantity matches sent quantity within step_size tolerance.

    Args:
        sent_qty: Quantity that was sent to exchange
        ack_qty: Quantity returned in exchange ACK (origQty)
        step_size: LOT_SIZE stepSize for tolerance calculation

    Returns:
        (True, "") if match, (False, reason) if mismatch
    """
    try:
        sent_d = _to_decimal(sent_qty)
        ack_d = _to_decimal(ack_qty)
        step_d = _to_decimal(step_size)
    except (ValueError, TypeError):
        return False, "QTY_ACK_PARSE_ERROR"

    # Allow tolerance of 1 step (for floating point edge cases)
    tolerance = step_d
    diff = abs(sent_d - ack_d)

    if diff > tolerance:
        return False, f"QTY_ACK_MISMATCH:sent={sent_d},ack={ack_d},diff={diff}"

    return True, ""
