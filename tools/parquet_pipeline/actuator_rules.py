"""Actuator rules: deterministic hysteresis FSM for stress state.

Pure function — no I/O, no side effects.

Input:  stress_level per bar (float 0..1)
Output: state per bar (NORMAL | STRESS | EXTREME) + why (<=80 chars)

Implements:
  - Hysteresis thresholds (enter/exit with gap)
  - Consecutive-bar confirmation
  - Minimum duration before exit
  - Circuit breaker on excessive switching
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class StressState(str, Enum):
    NORMAL = "NORMAL"
    STRESS = "STRESS"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class ActuatorConfig:
    """Flat config extracted from SystemStressStateMappingConfig."""

    enter_stress: float
    exit_stress: float
    enter_extreme: float
    exit_extreme: float
    consecutive_bars_enter: int
    consecutive_bars_exit: int
    min_duration_bars: int
    switch_window_bars: int
    max_switches_per_window: int


@dataclass
class ActuatorResult:
    """Output of run_actuator."""

    states: List[str]
    whys: List[str]
    switches_cumulative: List[int]
    total_switches: int


def run_actuator(
    stress_levels: List[float],
    config: ActuatorConfig,
) -> ActuatorResult:
    """Run hysteresis state machine over stress_level timeseries.

    Pure, deterministic.  O(n) time, O(n) space.

    Args:
        stress_levels: Per-bar composite stress level (0..1).
        config:        Hysteresis parameters.

    Returns:
        ActuatorResult with per-bar state, why, and cumulative switch count.
    """
    n = len(stress_levels)
    if n == 0:
        return ActuatorResult(
            states=[], whys=[], switches_cumulative=[], total_switches=0
        )

    states: list[str] = [""] * n
    whys: list[str] = [""] * n
    switches_cum: list[int] = [0] * n

    current = StressState.NORMAL
    bars_in_state = 0
    consec_above = 0  # consecutive bars above "enter" threshold
    consec_below = 0  # consecutive bars below "exit" threshold
    switch_times: list[int] = []

    for i in range(n):
        sl = stress_levels[i]
        bars_in_state += 1

        # ── Circuit breaker ──────────────────────────────────────
        window_start = max(0, i - config.switch_window_bars + 1)
        recent = sum(1 for t in switch_times if t >= window_start)

        if recent >= config.max_switches_per_window:
            states[i] = current.value
            whys[i] = f"CB:halt sw={recent}/{config.max_switches_per_window}"[:80]
            switches_cum[i] = len(switch_times)
            continue

        # ── State transitions ────────────────────────────────────
        new_state = current
        why = ""

        if current == StressState.NORMAL:
            if sl >= config.enter_stress:
                consec_above += 1
                if consec_above >= config.consecutive_bars_enter:
                    new_state = StressState.STRESS
                    why = (
                        f"NORMAL->STRESS sl={sl:.3f}"
                        f">=es={config.enter_stress}"
                        f" c={consec_above}"
                    )
            else:
                consec_above = 0

        elif current == StressState.STRESS:
            # Upward: STRESS -> EXTREME
            if sl >= config.enter_extreme:
                consec_above += 1
                if consec_above >= config.consecutive_bars_enter:
                    new_state = StressState.EXTREME
                    why = (
                        f"STRESS->EXTREME sl={sl:.3f}"
                        f">=ee={config.enter_extreme}"
                        f" c={consec_above}"
                    )
            else:
                consec_above = 0

            # Downward: STRESS -> NORMAL
            if sl < config.exit_stress:
                consec_below += 1
                if (
                    consec_below >= config.consecutive_bars_exit
                    and bars_in_state >= config.min_duration_bars
                ):
                    new_state = StressState.NORMAL
                    why = (
                        f"STRESS->NORMAL sl={sl:.3f}"
                        f"<xs={config.exit_stress}"
                        f" dur={bars_in_state}"
                    )
            else:
                consec_below = 0

        elif current == StressState.EXTREME:
            # Downward: EXTREME -> STRESS
            if sl < config.exit_extreme:
                consec_below += 1
                if (
                    consec_below >= config.consecutive_bars_exit
                    and bars_in_state >= config.min_duration_bars
                ):
                    new_state = StressState.STRESS
                    why = (
                        f"EXTREME->STRESS sl={sl:.3f}"
                        f"<xe={config.exit_extreme}"
                        f" dur={bars_in_state}"
                    )
            else:
                consec_below = 0

        # ── Apply transition ─────────────────────────────────────
        if new_state != current:
            switch_times.append(i)
            current = new_state
            bars_in_state = 0
            consec_above = 0
            consec_below = 0

        if not why:
            why = f"hold:{current.value} sl={sl:.3f} bars={bars_in_state}"

        states[i] = current.value
        whys[i] = why[:80]
        switches_cum[i] = len(switch_times)

    return ActuatorResult(
        states=states,
        whys=whys,
        switches_cumulative=switches_cum,
        total_switches=len(switch_times),
    )
