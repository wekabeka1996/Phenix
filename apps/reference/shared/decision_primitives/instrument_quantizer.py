"""Pure sizing helpers for exchange-constrained decision payloads.

This module has three distinct responsibilities:
- quantize_exposure(): convert Aurora exposure into exchange-valid qty/notional;
- compute_risk_adjusted_notional(): derive a target notional from a risk budget;
- compute_structural_stop(): derive a standalone ATR-based stop distance.

The helpers are stateless and perform no I/O. The active Aurora signal-emission
path uses quantize_exposure(); the other helpers remain pure library surfaces.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional


@dataclass
class InstrumentSpec:
    """Lightweight runtime mirror of exchange precision constraints.

    The broader config layer already validates these values as positive
    decimals. This dataclass keeps only the fields the quantizer needs at
    runtime and does not re-validate them locally.
    """
    step_size: Decimal          # LOT_SIZE stepSize (e.g. 0.001)
    min_qty: Decimal            # LOT_SIZE minQty (e.g. 0.001)
    min_notional: Decimal       # MIN_NOTIONAL (e.g. 5.0 USDT)
    # PRICE_FILTER tickSize (kept for contract parity)
    tick_size: Decimal


@dataclass
class QuantizedPosition:
    """Result of quantizing exposure to exchange-valid position.

    Attributes:
        side: "buy" or "sell" or "" (neutral)
        qty: Exchange-valid quantity (floored to step_size)
        notional: Quantity × price (USDT)
        exposure_abs: |exposure| used for sizing
        margin_required: Estimated margin (notional / leverage)
        reject_reason: If set, the caller must treat the position as unusable.
            qty/notional may still carry the post-floor values for diagnostics.
        min_notional_floor_applied: True when an accepted non-zero exposure was
            raised to the smallest exchange-valid order size.
    """
    side: str
    qty: Decimal
    notional: Decimal
    exposure_abs: float
    margin_required: Decimal
    reject_reason: Optional[str] = None
    min_notional_floor_applied: bool = False


def _d(v) -> Decimal:
    """Convert a numeric-ish value to Decimal via string normalization."""
    return Decimal(str(v))


def floor_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
    """Floor quantity to step size without ever rounding up.

    Non-positive qty or step_size collapses to 0 instead of raising.
    """
    if step_size <= 0 or qty <= 0:
        return Decimal("0")
    return (qty / step_size).to_integral_value(
        rounding=decimal.ROUND_DOWN
    ) * step_size


def ceil_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
    """Ceil quantity to step size for explicit min-executable sizing floors."""
    if step_size <= 0 or qty <= 0:
        return Decimal("0")
    return (qty / step_size).to_integral_value(
        rounding=decimal.ROUND_UP
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
    min_notional_policy: Literal["reject", "floor"] = "reject",
) -> QuantizedPosition:
    """
    Convert abstract exposure into an exchange-valid position candidate.

    Args:
        exposure: Quadratic kernel output ∈ [-1, +1].
                  Sign determines side, magnitude determines size.
        price: Current instrument price.
        max_notional: Maximum notional value for full exposure (=1.0).
        leverage: Exchange leverage setting.
        spec: Instrument specifications (step_size, min_qty, etc.).
        fee_buffer: Buffer to prevent insufficient balance (default 0.1%).
        exposure_cap: Maximum |exposure| to use (from ScoringEngineConfig).
        min_notional_policy:
            - "reject": preserve strict exposure-proportional sizing;
            - "floor": for accepted non-zero exposure, lift qty to the smallest
              exchange-valid min_qty/min_notional size when the proportional
              target is too small.

    Returns:
        QuantizedPosition with exchange-valid qty, or reject_reason.

    Notes:
        - neutral exposure short-circuits to an empty-side zero position;
        - the fee buffer is applied before qty flooring;
        - exchange violations return reject_reason strings instead of raising.
    """
    # Side is derived only from the sign; all sizing below is magnitude-based.
    if exposure > 0:
        side = "buy"
    elif exposure < 0:
        side = "sell"
    else:
        return QuantizedPosition(
            side="", qty=Decimal("0"), notional=Decimal("0"),
            exposure_abs=0.0, margin_required=Decimal("0"),
        )

    # Clamp conviction to the caller-provided cap before translating into notional.
    exposure_abs = min(abs(exposure), exposure_cap)

    # max_notional is already the full-conviction ceiling from the caller.
    notional = _d(exposure_abs) * max_notional

    # Reduce target notional up front so the floored qty stays inside balance headroom.
    notional = notional * (Decimal("1") - fee_buffer)

    # Price is the hard precondition for translating notional into quantity.
    if price <= 0:
        return QuantizedPosition(
            side=side, qty=Decimal("0"), notional=Decimal("0"),
            exposure_abs=exposure_abs, margin_required=Decimal("0"),
            reject_reason="ZERO_PRICE",
        )

    raw_qty = notional / price
    qty = floor_to_step(raw_qty, spec.step_size)

    def _min_executable_qty() -> Decimal:
        required_qty = spec.min_qty
        if spec.min_notional > 0:
            required_qty = max(required_qty, spec.min_notional / price)
        return ceil_to_step(required_qty, spec.step_size)

    actual_notional = qty * price

    if min_notional_policy == "floor" and (
        qty <= 0
        or qty < spec.min_qty
        or (spec.min_notional > 0 and actual_notional < spec.min_notional)
    ):
        floored_qty = _min_executable_qty()
        floored_notional = floored_qty * price
        if floored_qty <= 0:
            return QuantizedPosition(
                side=side, qty=Decimal("0"), notional=Decimal("0"),
                exposure_abs=exposure_abs, margin_required=Decimal("0"),
                reject_reason="ZERO_QUANTITY",
            )
        if max_notional > 0 and floored_notional > max_notional:
            return QuantizedPosition(
                side=side, qty=floored_qty, notional=floored_notional,
                exposure_abs=exposure_abs,
                margin_required=floored_notional / _d(leverage) if leverage > 0 else floored_notional,
                reject_reason=f"MIN_NOTIONAL_FLOOR_EXCEEDS_CAP:{floored_notional}>{max_notional}",
            )
        qty = floored_qty
        actual_notional = floored_notional
        min_notional_floor_applied = True
    else:
        min_notional_floor_applied = False

    # leverage only affects the estimated margin requirement here; it does not
    # change the requested notional or qty.
    margin_required = actual_notional / \
        _d(leverage) if leverage > 0 else actual_notional

    # Rejects are data returns rather than exceptions so the caller can surface
    # a blocked event with the computed diagnostics.
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
        min_notional_floor_applied=min_notional_floor_applied,
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
    Derive target notional from an explicit risk budget.

    Formula:
        risk_amount = equity × risk_per_trade_pct × |exposure|
        raw_notional = risk_amount / stop_distance_pct
        notional = min(raw_notional, equity × leverage) when leverage > 1

    This ensures that a stop-loss hit loses exactly risk_per_trade_pct
    of equity (scaled by exposure conviction) before any explicit caps.

    Args:
        equity: Account equity in USDT.
        exposure_abs: |exposure| from quadratic kernel (0-1).
        risk_per_trade_pct: Max risk per trade as fraction (e.g. 0.01 = 1%).
        stop_distance_pct: Expected SL distance as fraction (e.g. 0.005 = 0.5%).
        leverage: Exchange leverage used only as a buying-power ceiling.
        notional_cap: Additional hard cap on notional.

    Returns:
        Target notional value.
    """
    if equity <= 0 or exposure_abs <= 0 or stop_distance_pct <= 0:
        return Decimal("0")

    risk_amount = equity * risk_per_trade_pct * _d(exposure_abs)
    notional = risk_amount / stop_distance_pct

    # The risk budget defines the raw target; leverage only limits how much
    # notional can be deployed from the available equity.
    if leverage > 1:
        notional = min(notional, equity * _d(leverage))

    # Caller-provided caps win last.
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
    Compute a standalone ATR-based stop-loss distance from conviction.

    Formula:
        atr_mult = base_atr_mult - confidence_scale × |pillar_confidence|
        stop_distance = max(atr × atr_mult, price × min_stop_bps/10000)

    High conviction → tighter stop (less ATR breathing room).
    Low conviction → wider stop (more tolerance).

    Args:
        price: Current price.
        atr: ATR value.
        side: "buy" or "sell". Any other value returns price unchanged.
        pillar_confidence: |pillar_sum| (0-1).
        base_atr_mult: ATR multiplier at zero confidence.
        confidence_scale: How much to tighten per unit confidence.
        min_stop_bps: Minimum stop distance in basis points.

    Returns:
        Stop-loss price (Decimal).
    """
    # Clamp confidence before it tightens the ATR multiple.
    confidence = min(1.0, max(0.0, pillar_confidence))
    atr_mult = base_atr_mult - confidence_scale * _d(confidence)
    atr_mult = max(atr_mult, Decimal("0.5"))  # Never below 0.5 ATR

    stop_distance = atr * atr_mult

    # The bps floor prevents unrealistically tight stops on tiny ATR values.
    min_distance = price * _d(min_stop_bps) / Decimal("10000")
    stop_distance = max(stop_distance, min_distance)

    if side == "buy":
        return price - stop_distance
    elif side == "sell":
        return price + stop_distance
    else:
        return price  # Neutral — no stop
