from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Literal
from apps.reference.utils.tp_sl_math import (
    TpslParams,
    TpslConstraints,
    compute_tpsl_levels,
)


PositionSide = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class AggregatedOcoRiskConfig:
    sl_pct: Decimal
    tp_rr: Decimal


@dataclass(frozen=True)
class InstrumentPriceConstraints:
    tick_size: Decimal
    min_price: Decimal


@dataclass(frozen=True)
class AggregatedBracketLevels:
    tp_price: Decimal
    sl_price: Decimal
    why: str


class AggregatedOcoError(ValueError):
    """Raised for invalid aggregated OCO inputs."""


def compute_aggregated_brackets(
    position_amt: Decimal,
    avg_entry_price: Decimal,
    side: PositionSide,
    risk_cfg: AggregatedOcoRiskConfig,
    constraints: InstrumentPriceConstraints,
    why: str = "agg_oco_v1_from_pct_rr",
) -> AggregatedBracketLevels:
    """
    Compute aggregated TP/SL levels for a position.
    """
    _validate_inputs(position_amt, avg_entry_price, side, risk_cfg, constraints)

    try:
        levels = compute_tpsl_levels(
            TpslParams(
                side=side,
                avg_entry_price=avg_entry_price,
                position_qty=position_amt,
                sl_pct=risk_cfg.sl_pct,
                tp_rr=risk_cfg.tp_rr,
            ),
            TpslConstraints(
                tick_size=constraints.tick_size,
                min_price=constraints.min_price,
            ),
        )
    except ValueError as exc:
        raise AggregatedOcoError(str(exc))

    safe_why = why if len(why) <= 80 else why[:80]

    return AggregatedBracketLevels(
        tp_price=levels.tp_price,
        sl_price=levels.sl_price,
        why=safe_why if safe_why else levels.why,
    )


def _validate_inputs(
    position_amt: Decimal,
    avg_entry_price: Decimal,
    side: PositionSide,
    risk_cfg: AggregatedOcoRiskConfig,
    constraints: InstrumentPriceConstraints,
) -> None:
    if position_amt <= 0:
        raise AggregatedOcoError("position_amt must be > 0")

    if avg_entry_price <= 0:
        raise AggregatedOcoError("avg_entry_price must be > 0")

    if risk_cfg.sl_pct <= 0:
        raise AggregatedOcoError("risk_cfg.sl_pct must be > 0")

    if risk_cfg.tp_rr <= 0:
        raise AggregatedOcoError("risk_cfg.tp_rr must be > 0")

    if constraints.tick_size <= 0:
        raise AggregatedOcoError("constraints.tick_size must be > 0")

    if constraints.min_price <= 0:
        raise AggregatedOcoError("constraints.min_price must be > 0")

    if side not in ("LONG", "SHORT"):
        raise AggregatedOcoError(f"Unsupported side: {side!r}")


def _apply_price_constraints(
    raw_price: Decimal,
    constraints: InstrumentPriceConstraints,
) -> Decimal:
    rounded = raw_price.quantize(constraints.tick_size, rounding=ROUND_DOWN)
    if rounded < constraints.min_price:
        rounded = constraints.min_price
    return rounded
