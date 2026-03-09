from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from apps.reference.config_models import RegimeShiftInceptionConfig


@dataclass
class InceptionResult:
    eligible: bool
    micro_fraction: float  # 1.0 if not inception, < 1.0 if micro
    why: str  # <= 80 chars


def check_inception_eligibility(
    raw_regime: str,
    stable_regime: str,
    allowed_regimes: List[str],
    signal_score: Decimal,
    signal_threshold_for_raw: Decimal,
    stress_state: str,
    config: Optional["RegimeShiftInceptionConfig"],
) -> InceptionResult:
    """
    Zero-delay eligibility filter. ALL must be true:
    1. raw_regime != stable_regime
    2. raw_regime ∈ allowed_regimes
    3. stable_regime ∉ allowed_regimes (RESCUE-ONLY guard)
    4. signal_score >= threshold for raw_regime
    5. stress_state != "EXTREME"
    If config is None or config.enabled is False → InceptionResult(eligible=False, micro_fraction=1.0)
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

    if abs(signal_score) < signal_threshold_for_raw:
        return InceptionResult(eligible=False, micro_fraction=1.0, why="score_below_raw_threshold")

    action = config.action
    if action == "none":
        # telemetry only, not eligible for trading
        return InceptionResult(eligible=False, micro_fraction=1.0, why="action_none")
    elif action == "confirm_next_bar":
        return InceptionResult(eligible=False, micro_fraction=1.0, why="action_confirm_next_bar")
    elif action == "micro_size":
        fraction = float(config.micro_size_fraction)
        return InceptionResult(eligible=True, micro_fraction=fraction, why=f"inception:micro_{fraction}")

    raise ValueError(f"Unknown inception action: {action!r}")
