"""
Pure position state evolution utilities for ExecPosRuntimeV2 (not wired to runtime).

Handles:
- Opening new positions
- Scale-in averaging
- Partial close with realized PnL
- Flip (close then reopen opposite side)

All math is deterministic and side-effect free.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional
import time

# Tolerance for floating point zero comparisons
POSITION_ZERO_TOLERANCE = 1e-12


@dataclass(frozen=True)
class PositionState:
    symbol: str
    qty: float = 0.0  # signed: >0 long, <0 short
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    open_time: Optional[float] = None
    last_update_time: Optional[float] = None
    scale_in_count: int = 0
    scale_out_count: int = 0
    # R2-D: Position cycle identifier (increments on new position or reverse)
    cycle_id: int = 0

    @property
    def side(self) -> str:
        if self.qty > POSITION_ZERO_TOLERANCE:
            return "LONG"
        if self.qty < -POSITION_ZERO_TOLERANCE:
            return "SHORT"
        return "FLAT"


def _now_ts(ts: Optional[float]) -> float:
    return ts if ts is not None else time.time()


def apply_fill(state: PositionState, *, side: str, quantity: float, price: float, ts: Optional[float] = None) -> PositionState:
    """
    Apply a fill to position state and return a new PositionState.

    Args:
        state: current position state
        side: "BUY" or "SELL"
        quantity: filled quantity (can be signed or unsigned; normalized to abs internally)
        price: fill price
        ts: optional timestamp for bookkeeping

    Notes:
        - R2-F: quantity is normalized to abs() to handle signed WS/adapter payloads
        - Sign/direction is determined by side parameter (BUY/SELL)
        - Zero fills are ignored (qty == 0 after abs normalization)
    """
    # R2-F: Normalize quantity to absolute value (handle signed payloads)
    quantity = abs(quantity)

    if quantity < POSITION_ZERO_TOLERANCE:
        return replace(state, last_update_time=_now_ts(ts))

    signed_fill = quantity if side.upper() == "BUY" else -quantity
    ts_val = _now_ts(ts)

    # Fresh open
    if abs(state.qty) < POSITION_ZERO_TOLERANCE:
        return PositionState(
            symbol=state.symbol,
            qty=signed_fill,
            avg_entry_price=price,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=0.0,
            open_time=ts_val,
            last_update_time=ts_val,
            scale_in_count=0,
            scale_out_count=0,
            cycle_id=state.cycle_id + 1,
        )

    # Same direction (scale-in)
    if state.qty * signed_fill > 0:
        new_qty = state.qty + signed_fill
        total_cost = state.avg_entry_price * abs(state.qty) + price * quantity
        new_avg = total_cost / abs(new_qty)
        return PositionState(
            symbol=state.symbol,
            qty=new_qty,
            avg_entry_price=new_avg,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=0.0,
            open_time=state.open_time or ts_val,
            last_update_time=ts_val,
            scale_in_count=state.scale_in_count + 1,
            scale_out_count=state.scale_out_count,
            cycle_id=state.cycle_id,
        )

    # Opposite direction: closing or flipping
    closing_qty = min(abs(state.qty), quantity)
    # pnl: long closes gain when sell price > entry; short closes gain when buy price < entry
    direction = 1.0 if state.qty > 0 else -1.0
    pnl = closing_qty * (price - state.avg_entry_price) * direction
    new_realized = state.realized_pnl + pnl
    new_qty = state.qty + signed_fill  # may flip sign

    # Fully flat after close
    if abs(new_qty) < POSITION_ZERO_TOLERANCE:
        return PositionState(
            symbol=state.symbol,
            qty=0.0,
            avg_entry_price=0.0,
            realized_pnl=new_realized,
            unrealized_pnl=0.0,
            open_time=None,
            last_update_time=ts_val,
            scale_in_count=state.scale_in_count,
            scale_out_count=state.scale_out_count + 1,
            cycle_id=state.cycle_id,
        )

    # Flip: remaining open on opposite side at flip price
    if state.qty * new_qty < 0:
        # remaining open qty uses the flip price as new entry
        return PositionState(
            symbol=state.symbol,
            qty=new_qty,
            avg_entry_price=price,
            realized_pnl=new_realized,
            unrealized_pnl=0.0,
            open_time=ts_val,
            last_update_time=ts_val,
            scale_in_count=0,
            scale_out_count=state.scale_out_count + 1,
            cycle_id=state.cycle_id + 1,
        )

    # Partial close (same direction remains)
    return PositionState(
        symbol=state.symbol,
        qty=new_qty,
        avg_entry_price=state.avg_entry_price,
        realized_pnl=new_realized,
        unrealized_pnl=0.0,
        open_time=state.open_time,
        last_update_time=ts_val,
        scale_in_count=state.scale_in_count,
        scale_out_count=state.scale_out_count + 1,
        cycle_id=state.cycle_id,
    )
