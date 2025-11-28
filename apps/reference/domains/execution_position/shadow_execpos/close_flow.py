"""
Close flow decisioning (pure logic, not wired to runtime).

Plans deterministic close actions based on position state, requested intent,
and simple rule/context inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time

from .position_model import PositionState


@dataclass(frozen=True)
class CloseDecision:
    action: str  # CLOSE_FULL | CLOSE_PARTIAL | IGNORE | NOOP
    target_qty: float = 0.0
    reason_code: str = ""
    why: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True)
class CloseContext:
    reason: str  # MANUAL | FORCE_RISK | RULE_TRIGGER | TRAIL_HIT | TIME_EXIT
    requested_qty: Optional[float] = None
    price: Optional[float] = None
    timestamp: Optional[float] = None


@dataclass(frozen=True)
class CloseConfig:
    allow_partial: bool = True
    min_close_qty: float = 0.0
    max_hold_time_sec: Optional[float] = None
    allow_time_exit: bool = True


class CloseFlowService:
    """
    Plans close decisions without side effects.

    Legacy semantics (FSM close flow snapshot):
    - Position "open" timestamp is set on first fill; elapsed time is checked against max_hold_time_sec.
    - Time-based close triggers when elapsed > max_hold_time_sec (strictly greater), emitting a full close.
    - If max_hold_time_sec == 0 or time-exit is disabled, no time-based close is produced.
    """

    def plan_close(self, position: PositionState, ctx: CloseContext, cfg: Optional[CloseConfig] = None) -> CloseDecision:
        cfg = cfg or CloseConfig()
        ts = ctx.timestamp or time.time()

        requested_qty = None
        if ctx.requested_qty is not None:
            try:
                requested_qty = float(ctx.requested_qty)
            except (TypeError, ValueError):
                requested_qty = None

        effective_qty = abs(position.qty)
        if effective_qty < 1e-12 and requested_qty:
            effective_qty = requested_qty

        if effective_qty < 1e-12:
            return CloseDecision(action="NOOP", target_qty=0.0, reason_code="ALREADY_FLAT", why="position_qty_zero", timestamp=ts)

        target_qty = effective_qty if requested_qty is None else min(effective_qty, requested_qty)

        if target_qty < cfg.min_close_qty:
            return CloseDecision(action="IGNORE", target_qty=0.0, reason_code="BELOW_MIN_QTY", why="requested_close_below_min", timestamp=ts)

        # Time-based close (legacy parity: elapsed > max_hold_time_sec, full close)
        if (
            cfg.allow_time_exit
            and (cfg.max_hold_time_sec or 0) > 0
            and position.open_time is not None
        ):
            elapsed = ts - position.open_time
            if elapsed > float(cfg.max_hold_time_sec):
                return CloseDecision(
                    action="CLOSE_FULL",
                    target_qty=abs(position.qty),
                    reason_code="TIME_CLOSE",
                    why="time_exit_threshold",
                    timestamp=ts,
                )

        reason_map = {
            "FORCE_RISK": "FORCE_CLOSE",
            "MANUAL": "MANUAL_CLOSE",
            "RULE_TRIGGER": "RULE_CLOSE",
            "TRAIL_HIT": "TRAIL_CLOSE",
            "TIME_EXIT": "TIME_CLOSE",
        }
        reason_code = reason_map.get(ctx.reason.upper(), "CLOSE")

        # Decide partial vs full
        if target_qty < abs(position.qty) and cfg.allow_partial:
            action = "CLOSE_PARTIAL"
        else:
            target_qty = abs(position.qty)
            action = "CLOSE_FULL"

        return CloseDecision(
            action=action,
            target_qty=target_qty,
            reason_code=reason_code,
            why=ctx.reason.lower(),
            timestamp=ts,
        )
