"""
SL Fill Policy — SSOT for STOP_MARKET fill price computation.
==============================================================

Two models for backtest sensitivity analysis:

- CONSERVATIVE: fill at worst point of the bar after trigger
    SELL STOP -> fill = bar.low
    BUY  STOP -> fill = bar.high

- OPTIMISTIC: fill near stop_price with minimal slippage,
    bounded by bar limits (low/high).
    SELL STOP -> fill = max(bar.low,  stop_price * (1 - sl_min_bps/10000))
    BUY  STOP -> fill = min(bar.high, stop_price * (1 + sl_min_bps/10000))

NO open-based caps.  NO close as default fill.
Only low/high used as factual range of the bar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#   Enum
# ---------------------------------------------------------------------------

class SLFillModel(str, Enum):
    """Stop-loss fill model for backtest sensitivity."""
    CONSERVATIVE = "conservative"
    OPTIMISTIC = "optimistic"
    CLOSE_BASED = "close_based"  # Original behaviour: fill at bar.close (slippage applied by broker)


# ---------------------------------------------------------------------------
#   Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BarData:
    """Immutable snapshot of a single OHLCV bar."""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    ts_open_ms: int = 0


@dataclass(frozen=True)
class StopOrder:
    """Minimal info about a triggered STOP_MARKET order."""
    side: str          # "SELL" (long SL) or "BUY" (short SL)
    stop_price: float
    qty: float = 0.0
    order_id: str = ""
    symbol: str = ""


@dataclass
class SLFillResult:
    """Result of a single SL fill computation."""
    triggered: bool
    fill_price: float = 0.0
    model: str = ""


@dataclass
class SLBandRecord:
    """Per-SL band row (both models computed for same trigger)."""
    order_id: str = ""
    symbol: str = ""
    bar_ts: int = 0
    side: str = ""
    stop_price: float = 0.0
    bar_open: float = 0.0
    bar_high: float = 0.0
    bar_low: float = 0.0
    bar_close: float = 0.0
    fill_optimistic: float = 0.0
    fill_conservative: float = 0.0
    slippage_optimistic_bps: float = 0.0
    slippage_conservative_bps: float = 0.0
    delta_fill_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "bar_ts": self.bar_ts,
            "side": self.side,
            "stop_price": self.stop_price,
            "bar_open": self.bar_open,
            "bar_high": self.bar_high,
            "bar_low": self.bar_low,
            "bar_close": self.bar_close,
            "fill_optimistic": self.fill_optimistic,
            "fill_conservative": self.fill_conservative,
            "slippage_optimistic_bps": round(self.slippage_optimistic_bps, 4),
            "slippage_conservative_bps": round(self.slippage_conservative_bps, 4),
            "delta_fill_pct": round(self.delta_fill_pct, 6),
        }


# ---------------------------------------------------------------------------
#   Core pure functions
# ---------------------------------------------------------------------------

def is_stop_triggered(order: StopOrder, bar: BarData) -> bool:
    """Check if STOP_MARKET would trigger on this bar.

    SELL STOP (long SL): triggered if bar.low  <= stop_price
    BUY  STOP (short SL): triggered if bar.high >= stop_price
    """
    side = order.side.upper()
    if side == "SELL":
        return bar.low <= order.stop_price
    elif side == "BUY":
        return bar.high >= order.stop_price
    return False


def compute_stop_market_fill(
    order: StopOrder,
    bar: BarData,
    model: SLFillModel,
    sl_min_bps: float = 5.0,
) -> SLFillResult:
    """Compute fill price for a STOP_MARKET order on a given bar.

    Args:
        order: stop order descriptor (side, stop_price).
        bar:   OHLCV bar data.
        model: CONSERVATIVE, OPTIMISTIC, or CLOSE_BASED.
        sl_min_bps: minimum slippage in basis points for OPTIMISTIC model (default 5 = 0.05%).

    Returns:
        SLFillResult with triggered flag and computed fill_price.
    """
    if not is_stop_triggered(order, bar):
        return SLFillResult(triggered=False, model=model.value)

    side = order.side.upper()
    sp = order.stop_price

    if model == SLFillModel.CONSERVATIVE:
        if side == "SELL":
            fill = bar.low
        else:  # BUY
            fill = bar.high

    elif model == SLFillModel.CLOSE_BASED:
        # Original behaviour: fill at bar.close.
        # General market slippage is applied by the caller (MockBroker).
        fill = bar.close

    else:  # OPTIMISTIC
        slip_mult = sl_min_bps / 10_000.0
        if side == "SELL":
            # Best realistic fill: near stop_price minus minimal slippage,
            # but never better than bar.low (factual floor).
            fill = max(bar.low, sp * (1.0 - slip_mult))
        else:  # BUY
            fill = min(bar.high, sp * (1.0 + slip_mult))

    return SLFillResult(triggered=True, fill_price=fill, model=model.value)


def compute_slippage_bps(side: str, stop_price: float, fill_price: float) -> float:
    """Slippage in basis points from stop_price to actual fill.

    Convention: always >= 0 for adverse slippage.
    SELL STOP: slip = (stop_price - fill) / stop_price * 10000
    BUY  STOP: slip = (fill - stop_price) / stop_price * 10000
    """
    if stop_price <= 0:
        return 0.0
    side = side.upper()
    if side == "SELL":
        return (stop_price - fill_price) / stop_price * 10_000.0
    else:  # BUY
        return (fill_price - stop_price) / stop_price * 10_000.0


def build_sl_band_record(
    order: StopOrder,
    bar: BarData,
    sl_min_bps: float = 5.0,
) -> Optional[SLBandRecord]:
    """Compute both optimistic & conservative fills and return a band record.

    Returns None if stop was not triggered on this bar.
    """
    if not is_stop_triggered(order, bar):
        return None

    r_opt = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps)
    r_con = compute_stop_market_fill(order, bar, SLFillModel.CONSERVATIVE, sl_min_bps)

    slip_opt = compute_slippage_bps(order.side, order.stop_price, r_opt.fill_price)
    slip_con = compute_slippage_bps(order.side, order.stop_price, r_con.fill_price)

    # delta_fill_pct: signed difference relative to stop_price
    if order.stop_price > 0:
        delta = (r_opt.fill_price - r_con.fill_price) / order.stop_price
    else:
        delta = 0.0

    return SLBandRecord(
        order_id=order.order_id,
        symbol=order.symbol,
        bar_ts=bar.ts_open_ms,
        side=order.side.upper(),
        stop_price=order.stop_price,
        bar_open=bar.open,
        bar_high=bar.high,
        bar_low=bar.low,
        bar_close=bar.close,
        fill_optimistic=r_opt.fill_price,
        fill_conservative=r_con.fill_price,
        slippage_optimistic_bps=slip_opt,
        slippage_conservative_bps=slip_con,
        delta_fill_pct=delta,
    )


# ---------------------------------------------------------------------------
#   Aggregation helpers (for compare JSON)
# ---------------------------------------------------------------------------

def summarize_sl_band(records: list[SLBandRecord]) -> dict:
    """Aggregate SL band records into summary statistics."""
    if not records:
        return {"count_sl": 0}

    slip_opt = [r.slippage_optimistic_bps for r in records]
    slip_con = [r.slippage_conservative_bps for r in records]
    deltas = [r.delta_fill_pct for r in records]

    slip_opt_sorted = sorted(slip_opt)
    slip_con_sorted = sorted(slip_con)

    def _percentile(arr: list[float], p: float) -> float:
        if not arr:
            return 0.0
        idx = int(len(arr) * p / 100.0)
        idx = min(idx, len(arr) - 1)
        return arr[idx]

    # Top-N worst bars by conservative slippage
    worst_n = sorted(records, key=lambda r: r.slippage_conservative_bps, reverse=True)[:10]

    return {
        "count_sl": len(records),
        "mean_slip_bps_opt": round(sum(slip_opt) / len(slip_opt), 2),
        "mean_slip_bps_cons": round(sum(slip_con) / len(slip_con), 2),
        "p50_slip_bps_opt": round(_percentile(slip_opt_sorted, 50), 2),
        "p50_slip_bps_cons": round(_percentile(slip_con_sorted, 50), 2),
        "p95_slip_bps_opt": round(_percentile(slip_opt_sorted, 95), 2),
        "p95_slip_bps_cons": round(_percentile(slip_con_sorted, 95), 2),
        "max_slip_bps_opt": round(max(slip_opt), 2),
        "max_slip_bps_cons": round(max(slip_con), 2),
        "mean_delta_fill_pct": round(sum(deltas) / len(deltas), 6),
        "top_10_worst_bars": [r.to_dict() for r in worst_n],
    }
