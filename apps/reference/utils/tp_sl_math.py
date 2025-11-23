from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Literal


@dataclass(frozen=True)
class TpslParams:
    side: Literal["LONG", "SHORT"]
    avg_entry_price: Decimal
    position_qty: Decimal
    sl_pct: Decimal  # e.g. Decimal("0.01") for 1%
    tp_rr: Decimal   # reward/risk multiplier


@dataclass(frozen=True)
class TpslConstraints:
    tick_size: Decimal
    min_price: Decimal


@dataclass(frozen=True)
class TpslLevels:
    sl_price: Decimal
    tp_price: Decimal
    why: str


def _round_price(value: Decimal, tick_size: Decimal, min_price: Decimal) -> Decimal:
    """Round price down to tick_size and enforce min_price."""
    if tick_size <= 0:
        raise ValueError("tick_size must be > 0")
    quant = tick_size
    rounded = value.quantize(quant, rounding=ROUND_DOWN)
    if rounded < min_price:
        return min_price
    return rounded


def compute_tpsl_levels(params: TpslParams, constraints: TpslConstraints) -> TpslLevels:
    """Compute TP/SL levels symmetrically for LONG/SHORT."""
    if params.sl_pct <= 0:
        raise ValueError("sl_pct must be > 0")
    if params.tp_rr <= 0:
        raise ValueError("tp_rr must be > 0")
    if params.avg_entry_price <= 0:
        raise ValueError("avg_entry_price must be > 0")
    if params.position_qty < 0:
        raise ValueError("position_qty must be >= 0")

    entry = params.avg_entry_price
    sl_dist = params.sl_pct
    tp_rr = params.tp_rr

    if params.side == "LONG":
        raw_sl = entry * (Decimal("1") - sl_dist)
        raw_tp = entry * (Decimal("1") + sl_dist * tp_rr)
    elif params.side == "SHORT":
        raw_sl = entry * (Decimal("1") + sl_dist)
        raw_tp = entry * (Decimal("1") - sl_dist * tp_rr)
    else:
        raise ValueError(f"Invalid side {params.side!r}")

    sl_price = _round_price(raw_sl, constraints.tick_size, constraints.min_price)
    tp_price = _round_price(raw_tp, constraints.tick_size, constraints.min_price)

    why = f"tpsl|side={params.side}|sl_pct={params.sl_pct}|tp_rr={params.tp_rr}"
    return TpslLevels(sl_price=sl_price, tp_price=tp_price, why=why)
