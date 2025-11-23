"""
Trailing / breakeven / time-exit logic (pure service, not wired to runtime).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time
from decimal import Decimal

from .position_model import PositionState
from apps.reference.utils.tp_sl_math import (
    TpslParams,
    TpslConstraints,
    compute_tpsl_levels,
)


@dataclass(frozen=True)
class TrailingConfig:
    trail_distance_bps: float = 100.0  # move SL when price advances this many bps from watermark
    activate_after_bps: float = 0.0    # optional activation threshold
    breakeven_rr: float = 0.0          # move SL to entry after reward/risk multiple
    hard_time_exit_sec: Optional[float] = None


@dataclass(frozen=True)
class TrailingState:
    activated: bool = False
    breakeven_hit: bool = False
    high_watermark: float = 0.0  # for long
    low_watermark: float = 0.0   # for short
    sl_price: Optional[float] = None
    last_update_time: Optional[float] = None
    status: str = "INACTIVE"  # INACTIVE | ACTIVE | BREAKEVEN | EXIT_SIGNAL


@dataclass(frozen=True)
class TrailingDecision:
    sl_price: Optional[float]
    trail_state: TrailingState
    reason_code: str
    why: str
    exit: bool = False
    timestamp: float = 0.0


class TrailingStopService:
    """Evaluate trailing/breakeven/time-exit decisions."""

    def eval_trailing(
        self,
        position: PositionState,
        price: float,
        trail_state: TrailingState,
        cfg: TrailingConfig,
        now: Optional[float] = None,
    ) -> TrailingDecision:
        ts = now if now is not None else time.time()

        if abs(position.qty) < 1e-12:
            empty_state = TrailingState(status="INACTIVE", last_update_time=ts)
            return TrailingDecision(sl_price=None, trail_state=empty_state, reason_code="FLAT", why="position_flat", exit=False, timestamp=ts)

        is_long = position.qty > 0
        direction = 1.0 if is_long else -1.0

        # Initialize watermarks
        high = trail_state.high_watermark or (price if is_long else 0.0)
        low = trail_state.low_watermark or (price if not is_long else 0.0)
        # Baseline SL from canonical geometry (for initial seed if missing)
        if trail_state.sl_price is None and position.avg_entry_price > 0:
            try:
                base_levels = compute_tpsl_levels(
                    TpslParams(
                        side="LONG" if is_long else "SHORT",
                        avg_entry_price=Decimal(str(position.avg_entry_price)),
                        position_qty=Decimal(abs(position.qty)),
                        sl_pct=Decimal(str(cfg.trail_distance_bps / 10000.0)),
                        tp_rr=Decimal("1"),
                    ),
                    TpslConstraints(
                        tick_size=Decimal("0.00000001"),
                        min_price=Decimal("0"),
                    ),
                )
                sl_price = float(base_levels.sl_price)
            except Exception:
                sl_price = trail_state.sl_price
        else:
            sl_price = trail_state.sl_price

        if is_long:
            high = max(high, price)
        else:
            low = min(low, price)

        activated = trail_state.activated
        breakeven_hit = trail_state.breakeven_hit
        sl_price = trail_state.sl_price
        status = trail_state.status

        # Activation threshold
        if not activated and cfg.activate_after_bps > 0:
            move_bps = self._bps_move(position.avg_entry_price, price, direction)
            if move_bps >= cfg.activate_after_bps:
                activated = True
                status = "ACTIVE"
        else:
            activated = trail_state.activated or True
            if status == "INACTIVE":
                status = "ACTIVE"

        breakeven_just_hit = False
        # Breakeven
        if cfg.breakeven_rr > 0 and not breakeven_hit:
            move_bps = self._bps_move(position.avg_entry_price, price, direction)
            threshold = cfg.breakeven_rr * cfg.trail_distance_bps
            if move_bps >= threshold:
                breakeven_hit = True
                breakeven_just_hit = True
                candidate = position.avg_entry_price
                # Force SL to entry on breakeven event
                sl_price = candidate
                status = "BREAKEVEN"

        # Trail SL based on watermark
        trail_distance = cfg.trail_distance_bps / 10000.0
        if not breakeven_just_hit:
            if is_long:
                candidate_sl = high * (1 - trail_distance)
                sl_price = max(sl_price or candidate_sl, candidate_sl)
            else:
                candidate_sl = low * (1 + trail_distance)
                sl_price = min(sl_price or candidate_sl, candidate_sl)

        # Check exit via trail
        exit_signal = False
        if (is_long and price <= sl_price) or (not is_long and price >= sl_price):
            exit_signal = True
            status = "EXIT_SIGNAL"

        # Time exit
        if cfg.hard_time_exit_sec is not None and position.open_time is not None:
            if ts - position.open_time >= cfg.hard_time_exit_sec:
                exit_signal = True
                status = "EXIT_SIGNAL"
                sl_price = sl_price  # keep last computed
                reason_code = "TIME_EXIT"
                return TrailingDecision(sl_price=sl_price, trail_state=TrailingState(
                    activated=activated,
                    breakeven_hit=breakeven_hit,
                    high_watermark=high,
                    low_watermark=low,
                    sl_price=sl_price,
                    last_update_time=ts,
                    status=status,
                ), reason_code=reason_code, why="time_exit_threshold", exit=True, timestamp=ts)

        reason_code = "TRAIL_ACTIVE" if not exit_signal else "TRAIL_HIT"
        why = "trail_update" if not exit_signal else "price_hit_trailing_sl"

        return TrailingDecision(
            sl_price=sl_price,
            trail_state=TrailingState(
                activated=activated,
                breakeven_hit=breakeven_hit,
                high_watermark=high,
                low_watermark=low,
                sl_price=sl_price,
                last_update_time=ts,
                status=status,
            ),
            reason_code=reason_code,
            why=why,
            exit=exit_signal,
            timestamp=ts,
        )

    @staticmethod
    def _bps_move(entry: float, price: float, direction: float) -> float:
        if entry <= 0:
            return 0.0
        move = (price - entry) / entry * 10000.0 * direction
        return move
