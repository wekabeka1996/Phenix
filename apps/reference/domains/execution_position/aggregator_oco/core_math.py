"""
Aggregator OCO — Core Math Module (Phase 6)

RID: EXEC-AGGREGATOR-OCO-PHASE6-CORE-MATH-EXTRACTION

Pure mathematical functions for computing desired SL/TP levels.
This module has NO dependencies on runtime, adapter, or bracket_service.

The formulas here are extracted from and verified against:
- `shadow_execpos/bracket_service.py::_compute_desired_levels`
- `vfoundation/.../bracket_aggregator.py::compute_aggregated_brackets`
- `apps/reference/utils/tp_sl_math.py::compute_tpsl_levels`

Formulas:
    LONG:
        SL = entry_price × (1 - sl_pct)
        TP = entry_price × (1 + sl_pct × tp_rr)

    SHORT:
        SL = entry_price × (1 + sl_pct)
        TP = entry_price × (1 - sl_pct × tp_rr)

Invariants:
    - LONG: SL < entry_price < TP
    - SHORT: TP < entry_price < SL
    - All prices are Decimal for precision
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Literal, Optional

# Type alias for position side
Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class DesiredLevels:
    """
    Pure result of SL/TP level calculation.

    This is the output of core math with no bracket_service dependencies.

    Attributes:
        side: Position side ("LONG" or "SHORT").
        entry_price: Average entry price used for calculation.
        sl_price: Computed stop-loss price.
        tp_price: Computed take-profit price.
        sl_pct: SL percentage used (for tracing).
        tp_rr: TP risk:reward ratio used (for tracing).
        why: Short explanation (≤80 chars).
    """
    side: Side
    entry_price: Decimal
    sl_price: Decimal
    tp_price: Decimal
    sl_pct: Decimal
    tp_rr: Decimal
    why: str = "core_math_v1"


@dataclass(frozen=True)
class PriceConstraints:
    """
    Price constraints for rounding.

    Attributes:
        tick_size: Minimum price increment (e.g., 0.01 for BTCUSDT).
        min_price: Minimum allowed price (usually = tick_size).
    """
    tick_size: Decimal = Decimal("0.00000001")  # Default: high precision
    min_price: Decimal = Decimal("0.00000001")


def _round_price(
    value: Decimal,
    tick_size: Decimal,
    min_price: Decimal,
) -> Decimal:
    """
    Round price down to tick_size and enforce min_price.

    Args:
        value: Raw calculated price.
        tick_size: Minimum price increment.
        min_price: Minimum allowed price.

    Returns:
        Rounded price, at least min_price.
    """
    if tick_size <= 0:
        # No rounding if tick_size not specified
        return value

    rounded = value.quantize(tick_size, rounding=ROUND_DOWN)
    if rounded < min_price:
        return min_price
    return rounded


def compute_desired_levels(
    side: Side,
    entry_price: Decimal,
    sl_pct: Decimal,
    tp_rr: Decimal,
    *,
    constraints: Optional[PriceConstraints] = None,
) -> DesiredLevels:
    """
    Compute desired SL/TP levels using pure math.

    This is the core formula extracted from bracket_service._compute_desired_levels.
    It performs NO I/O, NO aggregator calls — just math.

    Args:
        side: Position side ("LONG" or "SHORT").
        entry_price: Average entry price.
        sl_pct: Stop-loss percentage (e.g., 0.02 for 2%).
        tp_rr: Take-profit risk:reward ratio (e.g., 2.0 for 1:2).
        constraints: Optional price constraints for rounding.

    Returns:
        DesiredLevels with computed SL and TP prices.

    Raises:
        ValueError: If inputs are invalid.

    Example:
        >>> from decimal import Decimal
        >>> levels = compute_desired_levels(
        ...     side="LONG",
        ...     entry_price=Decimal("100"),
        ...     sl_pct=Decimal("0.02"),
        ...     tp_rr=Decimal("2.0"),
        ... )
        >>> levels.sl_price
        Decimal('98')
        >>> levels.tp_price
        Decimal('104')
    """
    # ═══════════════════════════════════════════════════════════════════════════
    # INPUT VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    if side not in ("LONG", "SHORT"):
        raise ValueError(f"Invalid side: {side!r}, must be 'LONG' or 'SHORT'")

    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")

    if sl_pct <= 0:
        raise ValueError(f"sl_pct must be > 0, got {sl_pct}")

    if tp_rr <= 0:
        raise ValueError(f"tp_rr must be > 0, got {tp_rr}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CORE FORMULA (matches legacy _compute_desired_levels fallback)
    # ═══════════════════════════════════════════════════════════════════════════

    if side == "LONG":
        # LONG: SL below entry, TP above entry
        raw_sl = entry_price * (Decimal("1") - sl_pct)
        raw_tp = entry_price * (Decimal("1") + sl_pct * tp_rr)
    else:  # SHORT
        # SHORT: SL above entry, TP below entry
        raw_sl = entry_price * (Decimal("1") + sl_pct)
        raw_tp = entry_price * (Decimal("1") - sl_pct * tp_rr)

    # ═══════════════════════════════════════════════════════════════════════════
    # PRICE ROUNDING (optional)
    # ═══════════════════════════════════════════════════════════════════════════

    if constraints:
        sl_price = _round_price(
            raw_sl, constraints.tick_size, constraints.min_price)
        tp_price = _round_price(
            raw_tp, constraints.tick_size, constraints.min_price)
    else:
        sl_price = raw_sl
        tp_price = raw_tp

    # ═══════════════════════════════════════════════════════════════════════════
    # BUILD RESULT
    # ═══════════════════════════════════════════════════════════════════════════

    why = f"core_math|{side}|sl_pct={sl_pct}|tp_rr={tp_rr}"
    if len(why) > 80:
        why = why[:80]

    return DesiredLevels(
        side=side,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
        why=why,
    )


def compute_desired_levels_from_position(
    position_side: Side,
    position_entry_price: Decimal,
    sl_pct: Decimal,
    tp_rr: Decimal,
    *,
    tick_size: Optional[Decimal] = None,
) -> DesiredLevels:
    """
    Convenience wrapper matching bracket_service calling convention.

    This function provides a simpler interface for callers that have
    position data in separate variables rather than a PositionSnapshot.

    Args:
        position_side: "LONG" or "SHORT".
        position_entry_price: Average entry price.
        sl_pct: Stop-loss percentage.
        tp_rr: Take-profit risk:reward ratio.
        tick_size: Optional tick size for rounding.

    Returns:
        DesiredLevels with computed prices.
    """
    constraints = None
    if tick_size and tick_size > 0:
        constraints = PriceConstraints(
            tick_size=tick_size,
            min_price=tick_size,
        )

    return compute_desired_levels(
        side=position_side,
        entry_price=position_entry_price,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
        constraints=constraints,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# INVARIANT HELPERS (for testing)
# ═══════════════════════════════════════════════════════════════════════════════

def verify_level_invariants(levels: DesiredLevels) -> bool:
    """
    Verify that computed levels satisfy core invariants.

    INV-4: LONG → SL < entry < TP
    INV-5: SHORT → TP < entry < SL

    Args:
        levels: Computed desired levels.

    Returns:
        True if invariants hold, False otherwise.
    """
    if levels.side == "LONG":
        return levels.sl_price < levels.entry_price < levels.tp_price
    else:  # SHORT
        return levels.tp_price < levels.entry_price < levels.sl_price


def prices_match_with_tolerance(
    price1: Decimal,
    price2: Decimal,
    tolerance_pct: Decimal = Decimal("0.001"),  # 0.1% default tolerance
) -> bool:
    """
    Check if two prices match within a percentage tolerance.

    Used for stale levels detection - allows for small rounding/calculation differences.

    Args:
        price1: First price to compare.
        price2: Second price to compare.
        tolerance_pct: Maximum percentage difference allowed (e.g., 0.001 = 0.1%).

    Returns:
        True if prices match within tolerance, False otherwise.
    """
    if price1 == price2:
        return True

    # Calculate percentage difference
    diff = abs(price1 - price2)
    avg_price = (price1 + price2) / 2
    pct_diff = diff / avg_price

    return pct_diff <= tolerance_pct
