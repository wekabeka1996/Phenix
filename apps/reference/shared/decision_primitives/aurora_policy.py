"""Aurora policy layer — Package 2.

This module owns ONLY policy interpretation for the Aurora scoring path:
- regime-conditioned threshold widening
- side-bias penalty application
- hysteresis-based side selection (3-zone)
- final actionable/neutral interpretation

It does NOT:
- emit orders or mutate execution state
- own lifecycle truth
- perform numeric score transforms (that is aurora_math)
- access config trees or handler state

All public functions are pure: they take explicit inputs and return results.
State-dependent policy (hysteresis via current_side) is passed explicitly.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SideBiasState:
    """Windowed side-intent counts used to widen one side's entry threshold.

    AuroraScoringHelpersMixin supplies a pre-pruned snapshot, and the policy
    layer converts it into buy/sell threshold multipliers.

    Package 2: Canonical home for this DTO is aurora_policy.
    quadratic_scoring_kernel re-exports it for backward compatibility.
    """

    buy_count: int = 0
    sell_count: int = 0
    window_sec: float = 420.0
    target_ratio: float = 0.72
    penalty_factor: float = 0.25
    min_intents: int = 18


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AuroraPolicyInput:
    """All inputs the policy layer needs to produce a decision.

    Numeric scores come from AuroraMathOutput. Threshold/regime/bias
    parameters come from the orchestration layer that reads config.
    """
    # Numeric scores from math layer
    decision_score: float
    sizing_score: float

    # Threshold base
    base_threshold: decimal.Decimal

    # Regime context
    regime_name: Optional[str]
    regime_thresholds: Dict[str, float]

    # Side bias
    side_bias_state: Optional[SideBiasState]

    # Hysteresis
    neutral_threshold: Optional[decimal.Decimal]
    current_side: str  # "" or "buy" or "sell"


@dataclass(frozen=True, slots=True)
class AuroraPolicyDecision:
    """The result of Aurora policy interpretation.

    Contains the actionable side, thresholds applied, and rationale.
    Does NOT contain numeric scores — those stay in AuroraMathOutput.
    """
    # Side decision
    side: str  # "" (neutral), "buy", or "sell"
    side_why: str

    # Thresholds after regime + bias widening
    thr_buy: decimal.Decimal
    thr_sell: decimal.Decimal
    threshold_factor: decimal.Decimal

    # Bias multipliers applied
    buy_bias_mult: decimal.Decimal
    sell_bias_mult: decimal.Decimal

    # Was this deferred due to missing regime factor?
    deferred: bool = False
    defer_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Policy functions
# ---------------------------------------------------------------------------

def resolve_regime_factor(
    regime_name: Optional[str],
    regime_thresholds: Dict[str, float],
) -> Optional[decimal.Decimal]:
    """Resolve the positive finite regime multiplier used to widen thresholds.

    Returns None when neither the named regime nor DEFAULT yields a valid
    positive Decimal. The caller converts that into a defer/block path.
    """
    if regime_name and regime_name in regime_thresholds:
        raw = regime_thresholds[regime_name]
    elif "DEFAULT" in regime_thresholds:
        raw = regime_thresholds["DEFAULT"]
    else:
        return None

    try:
        factor = decimal.Decimal(str(raw))
        if not factor.is_finite() or factor <= 0:
            return None
        return factor
    except Exception:
        return None


def compute_side_bias_multipliers(
    side_bias_state: Optional[SideBiasState],
) -> tuple[decimal.Decimal, decimal.Decimal]:
    """Compute threshold multipliers from the windowed side-bias snapshot.

    No penalty is applied until ``min_intents`` has been reached. After that,
    only the overloaded side is widened, scaled by how far the observed share
    is past the configured target_ratio.

    Returns (buy_mult, sell_mult).
    """
    buy_mult = decimal.Decimal("1.0")
    sell_mult = decimal.Decimal("1.0")

    if not side_bias_state:
        return buy_mult, sell_mult

    total = side_bias_state.buy_count + side_bias_state.sell_count
    if total < side_bias_state.min_intents:
        return buy_mult, sell_mult

    sell_share = decimal.Decimal(
        str(side_bias_state.sell_count)) / decimal.Decimal(str(total))
    target = decimal.Decimal(str(side_bias_state.target_ratio))
    penalty_factor = decimal.Decimal(str(side_bias_state.penalty_factor))

    if sell_share > target:
        excess = sell_share - target
        max_excess = decimal.Decimal("1.0") - target
        scaling = excess / \
            max_excess if max_excess > 0 else decimal.Decimal("1.0")
        sell_mult += penalty_factor * scaling
    elif sell_share < (decimal.Decimal("1.0") - target):
        buy_share = decimal.Decimal("1.0") - sell_share
        excess = buy_share - target
        max_excess = decimal.Decimal("1.0") - target
        scaling = excess / \
            max_excess if max_excess > 0 else decimal.Decimal("1.0")
        buy_mult += penalty_factor * scaling

    return buy_mult, sell_mult


def determine_side(
    score: decimal.Decimal,
    thr_buy: decimal.Decimal,
    thr_sell: decimal.Decimal,
    thr_neutral: decimal.Decimal,
    current_side: str,
) -> tuple[str, str]:
    """Apply 3-zone hysteresis and return a lower-case side plus explanation.

    The zones are:
    - flip into the opposite side when the opposite threshold is crossed;
    - hold the current side while the score remains inside the neutral band;
    - otherwise collapse to neutral.
    """
    if current_side == "buy":
        if score <= -thr_sell:
            return "sell", f"flip:buy->sell:score={float(score):.4f}<=-thr_sell={float(thr_sell):.4f}"
        elif score >= thr_neutral:
            return "buy", f"hold:buy:score={float(score):.4f}>=thr_neutral={float(thr_neutral):.4f}"
        else:
            return "", f"exit:buy->neutral:score={float(score):.4f}<thr_neutral={float(thr_neutral):.4f}"
    elif current_side == "sell":
        if score >= thr_buy:
            return "buy", f"flip:sell->buy:score={float(score):.4f}>=thr_buy={float(thr_buy):.4f}"
        elif score <= -thr_neutral:
            return "sell", f"hold:sell:score={float(score):.4f}<=-thr_neutral={float(-thr_neutral):.4f}"
        else:
            return "", f"exit:sell->neutral:score={float(score):.4f}>-thr_neutral={float(-thr_neutral):.4f}"
    else:
        if score >= thr_buy:
            return "buy", f"enter:buy:score={float(score):.4f}>=thr_buy={float(thr_buy):.4f}"
        elif score <= -thr_sell:
            return "sell", f"enter:sell:score={float(score):.4f}<=-thr_sell={float(thr_sell):.4f}"
        else:
            return "", f"neutral:score={float(score):.4f}"


def apply_aurora_policy(inp: AuroraPolicyInput) -> AuroraPolicyDecision:
    """Execute the full Aurora policy pipeline.

    Pipeline:
    1. resolve regime factor → widen base threshold
    2. compute side-bias multipliers → apply to regime-widened threshold
    3. apply hysteresis → determine side

    Returns AuroraPolicyDecision (may be deferred if regime factor missing).
    """
    # Step 1: Regime threshold factor
    factor = resolve_regime_factor(inp.regime_name, inp.regime_thresholds)
    if factor is None:
        return AuroraPolicyDecision(
            side="",
            side_why="",
            thr_buy=inp.base_threshold,
            thr_sell=inp.base_threshold,
            threshold_factor=decimal.Decimal("1.0"),
            buy_bias_mult=decimal.Decimal("1.0"),
            sell_bias_mult=decimal.Decimal("1.0"),
            deferred=True,
            defer_reason=f"MISSING_REGIME_THRESHOLD:{inp.regime_name}",
        )

    signal_threshold = inp.base_threshold * factor

    # Step 2: Side-bias widening
    buy_bias_mult, sell_bias_mult = compute_side_bias_multipliers(
        inp.side_bias_state
    )

    thr_buy = signal_threshold * buy_bias_mult
    thr_sell = signal_threshold * sell_bias_mult

    # Step 3: Hysteresis side selection on decision_score
    thr_neutral = inp.neutral_threshold if inp.neutral_threshold is not None else thr_buy
    decision_score_dec = decimal.Decimal(str(round(inp.decision_score, 8)))

    side, side_why = determine_side(
        decision_score_dec, thr_buy, thr_sell, thr_neutral, inp.current_side,
    )

    return AuroraPolicyDecision(
        side=side,
        side_why=side_why,
        thr_buy=thr_buy,
        thr_sell=thr_sell,
        threshold_factor=factor,
        buy_bias_mult=buy_bias_mult,
        sell_bias_mult=sell_bias_mult,
    )
