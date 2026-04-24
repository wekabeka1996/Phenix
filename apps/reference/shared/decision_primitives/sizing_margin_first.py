"""Pure margin-first sizing helpers used by decision-making paths.

The active production sizing flow goes through PositionQueries, which calls the
functions in this module in sequence:
- compute_notional_target() derives the margin-funded notional budget;
- compute_qty() translates that budget into raw and step-floored quantity;
- validate_exchange_constraints() reports venue-level sizing failures.

The helpers stay intentionally small and synchronous. They do not read config,
inspect portfolio state, or emit events.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any, Optional


def _d(v: Any) -> Decimal:
    """Convert a numeric-like input into a finite Decimal."""
    if v is None:
        raise ValueError("cannot convert None to Decimal")
    try:
        d = Decimal(str(v))
    except Exception as e:
        raise ValueError(f"cannot convert to Decimal: {v!r}") from e
    if not d.is_finite():
        raise ValueError(f"non-finite Decimal: {v!r}")
    return d


def _validated_fee_buffer(fee_buffer: Any) -> Decimal:
    """Return a finite fee buffer fraction inside the supported range.

    The sizing helpers subtract the fee buffer from available equity before
    sizing. Values outside [0, 1) would either increase buying power or drive
    a positive equity snapshot below zero, so the contract rejects them.
    """
    fee_buffer_dec = _d(fee_buffer)
    if fee_buffer_dec < 0 or fee_buffer_dec >= Decimal("1"):
        raise ValueError("fee_buffer must be in [0, 1)")
    return fee_buffer_dec


def floor_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
    """Floor quantity to the exchange step size without rounding up."""
    if step_size <= 0:
        raise ValueError("step_size must be > 0")
    if qty <= 0:
        return Decimal("0")
    return (qty / step_size).to_integral_value(rounding=decimal.ROUND_DOWN) * step_size


def compute_notional_target(
    *,
    equity: Decimal,
    margin_pct: Decimal,
    leverage: int,
    notional_cap: Optional[Decimal] = None,
    fee_buffer: Decimal = Decimal("0.001"),
) -> tuple[Decimal, Decimal]:
    """Return margin budget and resulting notional target.

    Formula:
        safe_equity = equity * (1 - fee_buffer)
        margin_usdt = safe_equity * margin_pct
        notional_target = margin_usdt * leverage

    notional_cap, when provided, truncates the final notional target but does
    not change the pre-cap margin budget.
    """
    if equity <= 0:
        raise ValueError("equity must be > 0")
    if margin_pct <= 0 or margin_pct > 1:
        raise ValueError("margin_pct must be in (0, 1]")
    if leverage < 1:
        raise ValueError("leverage must be >= 1")

    fee_buffer_dec = _validated_fee_buffer(fee_buffer)
    safe_equity = equity * (Decimal("1") - fee_buffer_dec)

    margin_usdt = safe_equity * margin_pct
    notional_target = margin_usdt * Decimal(leverage)

    if notional_cap is not None and notional_target > notional_cap:
        notional_target = notional_cap

    return margin_usdt, notional_target


def compute_qty(
    *,
    notional_target: Decimal,
    price: Decimal,
    step_size: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return raw quantity and step-floored quantity for a notional target."""
    if price <= 0:
        raise ValueError("price must be > 0")
    if notional_target <= 0:
        return Decimal("0"), Decimal("0")

    raw_qty = notional_target / price
    rounded_qty = floor_to_step(raw_qty, step_size)
    return raw_qty, rounded_qty


def validate_exchange_constraints(
    *,
    qty: Decimal,
    price: Decimal,
    min_qty: Decimal,
    min_notional: Decimal,
) -> tuple[Optional[str], str]:
    """Validate quantity against exchange minimums.

    Returns a short machine code plus human-readable explanation instead of
    raising so callers can surface blocked-order diagnostics directly.
    """
    if qty <= 0:
        return "ZERO_QUANTITY", "qty <= 0"
    if min_qty > 0 and qty < min_qty:
        return "MIN_QTY", f"qty {qty} < min_qty {min_qty}"
    notional = qty * price
    if min_notional > 0 and notional < min_notional:
        return "MIN_NOTIONAL", f"notional {notional} < min_notional {min_notional}"
    return None, "ok"


def compute_exposure_based_qty(
    *,
    equity: Decimal,
    exposure: float,
    metrics_max_notional_cap: Optional[Decimal] = None,
    leverage: int,
    price: Decimal,
    step_size: Decimal,
    fee_buffer: Decimal = Decimal("0.001"),
) -> tuple[Decimal, Decimal]:
    """Scale quantity directly from exposure conviction.

    The helper is independent from the margin_pct path above:
    - full-conviction max_notional defaults to fee-buffered equity * leverage;
    - metrics_max_notional_cap, when present, tightens that ceiling;
    - exposure magnitude selects a fraction of the resulting ceiling.
    """
    exposure_abs = abs(exposure)

    fee_buffer_dec = _validated_fee_buffer(fee_buffer)
    safe_equity = equity * (Decimal("1") - fee_buffer_dec)
    max_notional = safe_equity * Decimal(leverage)

    if metrics_max_notional_cap is not None:
        max_notional = min(max_notional, metrics_max_notional_cap)

    target_notional = max_notional * _d(exposure_abs)

    return compute_qty(
        notional_target=target_notional,
        price=price,
        step_size=step_size,
    )
