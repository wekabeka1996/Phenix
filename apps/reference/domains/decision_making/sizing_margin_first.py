from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any, Optional


def _d(v: Any) -> Decimal:
    return Decimal(str(v))


def floor_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
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
    fee_buffer: Decimal = Decimal("0.001"),  # NEW: Default 0.1% buffer
) -> tuple[Decimal, Decimal]:
    if equity <= 0:
        raise ValueError("equity must be > 0")
    if margin_pct <= 0 or margin_pct > 1:
        raise ValueError("margin_pct must be in (0, 1]")
    if leverage < 1:
        raise ValueError("leverage must be >= 1")

    # FIX: Deduct fee buffer from equity BEFORE calculating margin
    # This prevents "insufficient balance" when margin_pct=1.0
    safe_equity = equity * (Decimal("1") - fee_buffer)

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
    if qty <= 0:
        return "ZERO_QUANTITY", "qty <= 0"
    if min_qty > 0 and qty < min_qty:
        return "MIN_QTY", f"qty {qty} < min_qty {min_qty}"
    notional = qty * price
    if min_notional > 0 and notional < min_notional:
        return "MIN_NOTIONAL", f"notional {notional} < min_notional {min_notional}"
    return None, "ok"

