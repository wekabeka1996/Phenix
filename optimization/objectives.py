"""
optimization/objectives.py — Objective functions for Aurora Hierarchical Optimization.

Stage 0: RegimeStabilityObjective  → stability_score (no PnL)
Stage 1: AlphaSearchObjective      → median_sharpe − penalties
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 0: Regime Stability
# ---------------------------------------------------------------------------

@dataclass
class RegimeStabilityMetrics:
    """Raw metrics collected from a regime-only simulation."""
    total_bars: int = 0
    definite_bars: int = 0        # bars with definite regime (trending/ranging/volatile)
    uncertain_bars: int = 0       # bars where regime = 'uncertain'
    regime_flips: int = 0         # number of regime transitions
    duration_hours: float = 0.0   # total simulation duration in hours

    @property
    def definite_ratio(self) -> float:
        """Fraction of bars with a definite (non-uncertain) regime."""
        return self.definite_bars / max(self.total_bars, 1)

    @property
    def uncertain_share(self) -> float:
        """Fraction of bars in 'uncertain' regime."""
        return self.uncertain_bars / max(self.total_bars, 1)

    @property
    def flicker_per_h(self) -> float:
        """Regime switches per hour — lower is more stable."""
        return self.regime_flips / max(self.duration_hours, 1e-6)


def compute_stability_score(
    metrics: RegimeStabilityMetrics,
    *,
    w_flicker: float = 2.0,
    w_uncertain: float = 1.0,
) -> float:
    """
    Stage 0 objective: regime clarity and temporal stability.

    Formula (from concept doc, with configurable weights):
        stability_score = definite_ratio − w_flicker * flicker_per_h − w_uncertain * uncertain_share

    NOTE: definite_ratio and uncertain_share are mathematically dependent
    (definite_ratio ≈ 1 − uncertain_share). w_uncertain effectively amplifies
    the definite_ratio penalty. This is a documented, deliberate design choice.

    Returns:
        stability_score (higher is better, theoretical max ≈ 1.0)
    """
    score = (
        metrics.definite_ratio
        - w_flicker * metrics.flicker_per_h
        - w_uncertain * metrics.uncertain_share
    )
    return score


# ---------------------------------------------------------------------------
# Stage 1: Alpha Search — Penalty Functions
# ---------------------------------------------------------------------------

@dataclass
class PenaltyConfig:
    """Thresholds for soft penalties in Stage 1 objective."""
    max_dd_soft_pct: float = 20.0
    max_dd_hard_pct: float = 35.0
    churn_threshold: float = 0.4
    reject_rate_threshold: float = 0.3
    starvation_min_trades: int = 10
    util_proximity_max: float = 0.95


@dataclass
class AlphaMetrics:
    """Metrics collected from a full strategy backtest for Stage 1."""
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    churn_ratio: float = 0.0       # side alternation ratio (sign changes / intents)
    reject_rate: float = 0.0       # GUARD_REJECT + NRR intents / total intents
    utilization: Optional[float] = None  # capital utilization ratio (None = unknown)
    roi_pct: float = 0.0


def P_mdd(mdd_pct: float, *, soft: float = 20.0, hard: float = 35.0) -> float:
    """
    Max Drawdown penalty — linear ramp between soft and hard thresholds.
    Returns 0 if MDD <= soft, scales to 1.0 at hard, returns HARD_REJECT above hard.
    """
    if mdd_pct <= soft:
        return 0.0
    if mdd_pct >= hard:
        return float("inf")  # Hard constraint — will cause -1e9 objective
    return (mdd_pct - soft) / (hard - soft)


def P_churn(churn_ratio: float, *, threshold: float = 0.4) -> float:
    """Churn penalty — penalizes excessive short-lived trades."""
    if churn_ratio <= threshold:
        return 0.0
    return (churn_ratio - threshold) / (1.0 - threshold)


def P_reject(reject_rate: float, *, threshold: float = 0.3) -> float:
    """Guard reject penalty — penalizes excessive GUARD_REJECT outcomes."""
    if reject_rate <= threshold:
        return 0.0
    return (reject_rate - threshold) / (1.0 - threshold)


def P_starvation(total_trades: int, *, min_trades: int = 10) -> float:
    """Starvation penalty — penalizes too few trades (strategy is idle)."""
    if total_trades >= min_trades:
        return 0.0
    if total_trades <= 0:
        return 1.0
    return 1.0 - (total_trades / min_trades)


def P_util_proximity(utilization: float, *, max_util: float = 0.95) -> float:
    """Utilization proximity penalty — penalizes near-maximum capital usage."""
    if utilization <= max_util:
        return 0.0
    return (utilization - max_util) / (1.0 - max_util)


def compute_alpha_score(
    metrics: AlphaMetrics,
    penalty_config: PenaltyConfig,
) -> float:
    """
    Stage 1 objective: risk-adjusted return minus soft penalties.

    Formula:
        alpha_score = base_sharpe − P_mdd − P_churn − P_reject − P_starvation − P_util

    If any hard constraint is violated (MDD > hard threshold), returns -1e9.

    Returns:
        alpha_score (higher is better)
    """
    # Check hard constraint first
    p_mdd = P_mdd(
        metrics.max_drawdown_pct,
        soft=penalty_config.max_dd_soft_pct,
        hard=penalty_config.max_dd_hard_pct,
    )
    if math.isinf(p_mdd):
        LOG.info(f"HARD REJECT: MDD={metrics.max_drawdown_pct:.1f}% > {penalty_config.max_dd_hard_pct}%")
        return -1e9

    p_churn = P_churn(metrics.churn_ratio, threshold=penalty_config.churn_threshold)
    p_reject = P_reject(metrics.reject_rate, threshold=penalty_config.reject_rate_threshold)
    p_starve = P_starvation(metrics.total_trades, min_trades=penalty_config.starvation_min_trades)

    # Utilization penalty: skip if metric is unavailable (None)
    p_util = 0.0
    if metrics.utilization is not None:
        p_util = P_util_proximity(metrics.utilization, max_util=penalty_config.util_proximity_max)

    total_penalty = p_mdd + p_churn + p_reject + p_starve + p_util
    alpha_score = metrics.sharpe_ratio - total_penalty

    LOG.debug(
        f"alpha_score={alpha_score:.4f} "
        f"(sharpe={metrics.sharpe_ratio:.4f}, "
        f"P_mdd={p_mdd:.3f}, P_churn={p_churn:.3f}, P_reject={p_reject:.3f}, "
        f"P_starve={p_starve:.3f}, P_util={p_util:.3f} {'(skipped)' if metrics.utilization is None else ''})"
    )
    return alpha_score
