"""Pure regime-shift inception gating for the current decision tick.

This module is intentionally narrow: it evaluates the current raw/stable regime
split and returns a small result object for the caller. It does not emit
telemetry, mutate strategy state, or schedule follow-up confirmation work.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from apps.reference.config_models import RegimeShiftInceptionConfig


@dataclass
class InceptionResult:
    """Outcome of the inception gate for the current evaluation only.

    ``eligible`` tells the caller whether it may attempt an immediate inception
    action now. ``micro_fraction`` is the sizing multiplier returned by the
    selected action contract; non-entry outcomes use ``1.0``. ``why`` is a
    short reason token that callers can surface into telemetry or reason chains.
    """

    eligible: bool
    micro_fraction: float
    why: str


def check_inception_eligibility(
    raw_regime: str,
    stable_regime: str,
    allowed_regimes: List[str],
    signal_score: Decimal,
    signal_threshold_for_raw: Decimal,
    stress_state: str,
    config: Optional["RegimeShiftInceptionConfig"],
) -> InceptionResult:
    """Return whether the current regime shift qualifies for inception handling.

    This helper is stateless and evaluates only the inputs for the current
    decision pass. It does not confirm later bars or persist pending work.

    Eligibility requires all of the following:
    1. the feature is enabled;
    2. ``raw_regime`` differs from ``stable_regime``;
    3. ``raw_regime`` is in ``allowed_regimes``;
    4. ``stable_regime`` is not in ``allowed_regimes``;
    5. ``stress_state`` is not ``EXTREME``;
    6. ``abs(signal_score)`` meets the raw-regime threshold.

    Action semantics:
    - ``none`` returns a non-eligible telemetry-only result;
    - ``confirm_next_bar`` returns a non-eligible reason token only; this
      helper does not schedule or persist any follow-up confirmation;
    - ``micro_size`` returns an eligible result with the configured size
      fraction.

    Raises:
        ValueError: if ``config.action`` is outside the validated contract.
    """
    if config is None or not config.enabled:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="inception_disabled")

    if raw_regime == stable_regime:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="raw==stable")

    if raw_regime not in allowed_regimes:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="raw_not_allowed")

    if stable_regime in allowed_regimes:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="stable_already_allowed")

    if stress_state == "EXTREME":
        return InceptionResult(eligible=False, micro_fraction=1.0, why="extreme_stress")

    # The gate uses score magnitude only; a sufficiently negative score still
    # passes this threshold check and direction is handled by the caller.
    if abs(signal_score) < signal_threshold_for_raw:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="score_below_raw_threshold")

    action = config.action
    # Only ``micro_size`` makes the result eligible here. Other modes preserve a
    # machine-readable reason for the caller without authorizing an immediate entry.
    if action == "none":
        return InceptionResult(eligible=False, micro_fraction=1.0, why="action_none")
    elif action == "confirm_next_bar":
        return InceptionResult(eligible=False, micro_fraction=1.0, why="action_confirm_next_bar")
    elif action == "micro_size":
        fraction = float(config.micro_size_fraction)
        return InceptionResult(eligible=True, micro_fraction=fraction, why=f"inception:micro_{fraction}")

    # Unknown actions are treated as a contract/config error instead of silently
    # degrading into a trading decision.
    raise ValueError(f"Unknown inception action: {action!r}")
