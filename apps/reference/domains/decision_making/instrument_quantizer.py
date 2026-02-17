"""
InstrumentQuantizer — Phase 9: Exposure → Position Size.

Converts the abstract exposure level from the quadratic kernel
into exchange-compliant position sizes.

Flow:
    exposure ∈ [-1, +1] → notional → qty (floored to step_size)

Key formulas:
    notional = |exposure| × max_notional
    qty = floor(notional / price, step_size)

The quantizer respects:
- Exchange min_qty / min_notional constraints
- Step size rounding (always floor, never round up)
- Maximum notional cap
- Fee buffer to prevent insufficient balance

Pure functions, no state, no I/O.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union


@dataclass
class InstrumentSpec:
    """Exchange instrument specification.

    These values come from exchange info (symbol filters).
    """
    step_size: Decimal          # LOT_SIZE stepSize (e.g. 0.001)
    min_qty: Decimal            # LOT_SIZE minQty (e.g. 0.001)
    min_notional: Decimal       # MIN_NOTIONAL (e.g. 5.0 USDT)
    tick_size: Decimal           # PRICE_FILTER tickSize (e.g. 0.01)


@dataclass
class QuantizedPosition:
    """Result of quantizing exposure to exchange-valid position.

    Attributes:
        side: "buy" or "sell" or "" (neutral)
        qty: Exchange-valid quantity (floored to step_size)
        notional: Quantity × price (USDT)
        exposure_abs: |exposure| used for sizing
        margin_required: Estimated margin (notional / leverage)
        reject_reason: If set, position is invalid (min_qty, min_notional)
    """
    side: str
    qty: Decimal
    notional: Decimal
    exposure_abs: float
    margin_required: Decimal
    reject_reason: Optional[str] = None


def _d(v) -> Decimal:
    """Safe Decimal conversion."""
    return Decimal(str(v))


def floor_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
    """Floor quantity to step size (never round up)."""
    if step_size <= 0 or qty <= 0:
        return Decimal("0")
    return (qty / step_size).to_integral_value(
        rounding=decimal.ROUND_DOWN
    ) * step_size


def quantize_exposure(
    *,
    exposure: float,
    price: Decimal,
    max_notional: Decimal,
    leverage: int,
    spec: InstrumentSpec,
    fee_buffer: Decimal = Decimal("0.001"),
    exposure_cap: float = 1.0,
) -> QuantizedPosition:
    """
    Convert abstract exposure to exchange-valid position.

    Args:
        exposure: Quadratic kernel output ∈ [-1, +1].
                  Sign determines side, magnitude determines size.
        price: Current instrument price.
        max_notional: Maximum notional value for full exposure (=1.0).
        leverage: Exchange leverage setting.
        spec: Instrument specifications (step_size, min_qty, etc.).
        fee_buffer: Buffer to prevent insufficient balance (default 0.1%).
        exposure_cap: Maximum |exposure| to use (from ScoringEngineConfig).

    Returns:
        QuantizedPosition with exchange-valid qty, or reject_reason.
    """
    # Determine side
    if exposure > 0:
        side = "buy"
    elif exposure < 0:
        side = "sell"
    else:
        return QuantizedPosition(
            side="", qty=Decimal("0"), notional=Decimal("0"),
            exposure_abs=0.0, margin_required=Decimal("0"),
        )

    # Clamp |exposure| to [0, cap]
    exposure_abs = min(abs(exposure), exposure_cap)

    # Compute notional: |exposure| × max_notional
    notional = _d(exposure_abs) * max_notional

    # Apply fee buffer
    notional = notional * (Decimal("1") - fee_buffer)

    # Compute quantity
    if price <= 0:
        return QuantizedPosition(
            side=side, qty=Decimal("0"), notional=Decimal("0"),
            exposure_abs=exposure_abs, margin_required=Decimal("0"),
            reject_reason="ZERO_PRICE",
        )

    raw_qty = notional / price
    qty = floor_to_step(raw_qty, spec.step_size)

    actual_notional = qty * price
    margin_required = actual_notional / _d(leverage) if leverage > 0 else actual_notional

    # Validate exchange constraints
    if qty <= 0:
        return QuantizedPosition(
            side=side, qty=Decimal("0"), notional=Decimal("0"),
            exposure_abs=exposure_abs, margin_required=Decimal("0"),
            reject_reason="ZERO_QUANTITY",
        )
    if qty < spec.min_qty:
        return QuantizedPosition(
            side=side, qty=qty, notional=actual_notional,
            exposure_abs=exposure_abs, margin_required=margin_required,
            reject_reason=f"MIN_QTY:{qty}<{spec.min_qty}",
        )
    if actual_notional < spec.min_notional:
        return QuantizedPosition(
            side=side, qty=qty, notional=actual_notional,
            exposure_abs=exposure_abs, margin_required=margin_required,
            reject_reason=f"MIN_NOTIONAL:{actual_notional}<{spec.min_notional}",
        )

    return QuantizedPosition(
        side=side,
        qty=qty,
        notional=actual_notional,
        exposure_abs=exposure_abs,
        margin_required=margin_required,
    )


def compute_risk_adjusted_notional(
    *,
    equity: Decimal,
    exposure_abs: float,
    risk_per_trade_pct: Decimal,
    stop_distance_pct: Decimal,
    leverage: int,
    notional_cap: Optional[Decimal] = None,
) -> Decimal:
    """
    Risk-based sizing: position size derived from risk budget.

    Formula:
        risk_amount = equity × risk_per_trade_pct × |exposure|
        notional = risk_amount / stop_distance_pct × leverage

    This ensures that a stop-loss hit loses exactly risk_per_trade_pct
    of equity (scaled by exposure conviction).

    Args:
        equity: Account equity in USDT.
        exposure_abs: |exposure| from quadratic kernel (0-1).
        risk_per_trade_pct: Max risk per trade as fraction (e.g. 0.01 = 1%).
        stop_distance_pct: Expected SL distance as fraction (e.g. 0.005 = 0.5%).
        leverage: Exchange leverage.
        notional_cap: Hard cap on notional.

    Returns:
        Target notional value.
    """
    if equity <= 0 or exposure_abs <= 0 or stop_distance_pct <= 0:
        return Decimal("0")

    risk_amount = equity * risk_per_trade_pct * _d(exposure_abs)
    notional = risk_amount / stop_distance_pct

    # Apply leverage
    if leverage > 1:
        notional = min(notional, equity * _d(leverage))

    # Apply cap
    if notional_cap is not None and notional > notional_cap:
        notional = notional_cap

    return notional


def compute_structural_stop(
    *,
    price: Decimal,
    atr: Decimal,
    side: str,
    pillar_confidence: float,
    base_atr_mult: Decimal = Decimal("1.5"),
    confidence_scale: Decimal = Decimal("0.5"),
    min_stop_bps: int = 15,
) -> Decimal:
    """
    Structural stop-loss scaled by pillar conviction.

    Formula:
        atr_mult = base_atr_mult - confidence_scale × |pillar_confidence|
        stop_distance = max(atr × atr_mult, price × min_stop_bps/10000)

    High conviction → tighter stop (less ATR breathing room).
    Low conviction → wider stop (more tolerance).

    Args:
        price: Current price.
        atr: ATR value.
        side: "buy" or "sell".
        pillar_confidence: |pillar_sum| (0-1).
        base_atr_mult: ATR multiplier at zero confidence.
        confidence_scale: How much to tighten per unit confidence.
        min_stop_bps: Minimum stop distance in basis points.

    Returns:
        Stop-loss price (Decimal).
    """
    # Scale ATR multiplier by conviction
    confidence = min(1.0, max(0.0, pillar_confidence))
    atr_mult = base_atr_mult - confidence_scale * _d(confidence)
    atr_mult = max(atr_mult, Decimal("0.5"))  # Never below 0.5 ATR

    stop_distance = atr * atr_mult

    # Enforce minimum stop distance
    min_distance = price * _d(min_stop_bps) / Decimal("10000")
    stop_distance = max(stop_distance, min_distance)

    if side == "buy":
        return price - stop_distance
    elif side == "sell":
        return price + stop_distance
    else:
        return price  # Neutral — no stop
