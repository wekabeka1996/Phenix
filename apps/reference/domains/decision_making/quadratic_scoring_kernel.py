"""
QuadraticScoringKernel — Phase 9: The Quadratic Brain.

Converts directional conviction (Σ = pillar aggregate) into
non-linear exposure via:

    Exposure = sign(Σ) × Σ²

Properties:
- Weak conviction → near-zero exposure (hesitation penalty)
- Strong conviction → near-max exposure (conviction reward)
- Sign preserved (long vs short)
- Continuous, differentiable, no jumps

Integration:
- Drop-in replacement for AuroraScoringKernel when feature-flagged
- Same ScoringResult output contract
- Pillar sum injected via features["pillar_sum"]

Shield Stub:
- Accepts optional shield_fn that can veto/attenuate signal
- NullShield (default) passes everything through
"""
from __future__ import annotations

import decimal
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    ScoringResult,
    SideBiasState,
)


@dataclass
class QuadraticContext:
    """Explainability context for quadratic scoring."""
    pillar_sum: float = 0.0
    raw_exposure: float = 0.0           # sign(Σ)×Σ²
    shield_multiplier: float = 1.0      # from shield cascade
    final_exposure: float = 0.0         # raw_exposure × shield_multiplier
    pillar_contribs: Dict[str, float] = field(default_factory=dict)
    shield_reasons: List[str] = field(default_factory=list)


# Type for shield function: (symbol, features, pillar_sum, raw_exposure) -> (multiplier, reasons)
ShieldFn = Callable[
    [str, Dict[str, Any], float, float],
    tuple[float, List[str]],
]


def _null_shield(
    symbol: str,
    features: Dict[str, Any],
    pillar_sum: float,
    raw_exposure: float,
) -> tuple[float, List[str]]:
    """NullShield: passes everything through unchanged."""
    return 1.0, []


class QuadraticScoringKernel:
    """
    Phase 9 Quadratic Scoring Kernel.

    Formula: Exposure = sign(Σ) × Σ² × shield_multiplier

    Where:
    - Σ = weighted pillar sum ∈ [-1, +1]
    - shield_multiplier ∈ [0, 1] (attenuated by shields)

    The quadratic transform creates:
    - Near-zero exposure for weak signals (|Σ| < 0.3)
    - Aggressive scaling for strong signals (|Σ| > 0.7)
    - Natural hesitation/conviction zones

    Output contract: Same as AuroraScoringKernel.ScoringResult.
    """

    @staticmethod
    def compute(
        *,
        symbol: str,
        features: Dict[str, Any],
        warmup_readiness: Dict[str, bool],
        price: decimal.Decimal,
        signal_weights: Dict[str, float],
        feature_neutrals: Dict[str, float],
        essential_features: List[str],
        base_threshold: decimal.Decimal,
        regime_name: Optional[str],
        regime_thresholds: Dict[str, float],
        side_bias_state: Optional[SideBiasState],
        direction_strength_cfg: Dict[str, Any],
        delta_price_cap_pct: decimal.Decimal,
        scoring_version: str = "v2",
        # Hysteresis support
        neutral_threshold: Optional[decimal.Decimal] = None,
        current_side: str = "",
        # Phase 9 extensions
        shield_fn: Optional[ShieldFn] = None,
        pillar_contribs: Optional[Dict[str, float]] = None,
        score_multiplier: float = 1.0,
        linear_score: Optional[float] = None,
    ) -> ScoringResult:
        """
        Compute quadratic signal score.
        
        Args:
            linear_score: Explicit linear score input (e.g. from handler computation).
                          If provided, takes precedence over features["pillar_sum"].
        """
        _shield = shield_fn or _null_shield

        result = ScoringResult(
            score=decimal.Decimal("0"),
            side="",
            thr_buy=base_threshold,
            thr_sell=base_threshold,
            why_chain=[],
            regime=regime_name,
        )

        # ─── Step 1: Resolve Linear Input (S_linear) ────────────────
        if linear_score is not None:
             s_linear = linear_score
             source = "arg"
        else:
            # Fallback to feature contract
            pillar_sum_raw = features.get("pillar_sum")
            if pillar_sum_raw is None:
                result.deferred = True
                result.defer_reason = "PILLAR_WARMUP"  # FE pillars not ready yet (normal during warmup)
                return result
            try:
                s_linear = float(pillar_sum_raw)
                source = "feature:pillar_sum"
            except (TypeError, ValueError):
                result.deferred = True
                result.defer_reason = "LINEAR_SCORE_INVALID"
                return result

        if not math.isfinite(s_linear):
            result.deferred = True
            result.defer_reason = "LINEAR_SCORE_NAN_INF"
            return result

        # ─── Step 2: Scale & Clamp (Sensitivity) ──────────────────
        # Formula: S_scaled = clamp(S_linear * M, -1, 1)
        s_scaled_raw = s_linear * score_multiplier
        
        # SAFETY CAP: Enforce [-1, 1] invariant before squaring
        s_clamped = max(-1.0, min(1.0, s_scaled_raw))
        
        # ─── Step 3: Quadratic Transform ──────────────────────────
        # Exposure = sign(S_clamped) * (S_clamped)²
        sign = 1.0 if s_clamped >= 0 else -1.0
        # Determine magnitude from the clamped value
        final_exposure = sign * (s_clamped ** 2)

        # ─── Step 4: Shield Cascade ──────────────────────────────
        shield_mult, shield_reasons = _shield(symbol, features, s_linear, final_exposure)
        shield_mult = max(0.0, min(1.0, shield_mult))
        
        final_score_val = final_exposure * shield_mult

        # ─── Step 5: Output & Explainability ─────────────────────
        result.score = decimal.Decimal(str(round(final_score_val, 8)))

        quad_ctx = QuadraticContext(
            pillar_sum=s_linear,
            raw_exposure=final_exposure, 
            shield_multiplier=shield_mult,
            final_exposure=final_score_val,
            pillar_contribs=dict(pillar_contribs or {}),
            shield_reasons=list(shield_reasons),
        )

        result.psi_vector = {
            "scoring_engine": "quadratic_v1",
            "source": source,
            "s_linear": s_linear,
            "multiplier": score_multiplier,
            "s_scaled_raw": s_scaled_raw,
            "s_clamped": s_clamped,
            "clamped": s_scaled_raw != s_clamped,
            "final_exposure": final_score_val,
            "shield_multiplier": shield_mult,
            "shield_reasons": list(shield_reasons),
        }

        # Populate Phase 9 Shield Context
        result.shield_multiplier = decimal.Decimal(str(shield_mult))
        result.shield_breakdown = {
            "reasons": list(shield_reasons),
            "raw_exposure": final_exposure,
            "s_linear": s_linear,
        }

        # ─── Step 6: Threshold calculation ───────────────────────
        # Reuse regime × side-bias threshold logic from legacy kernel
        factor = _resolve_regime_factor(regime_name, regime_thresholds)
        if factor is None:
            result.deferred = True
            result.defer_reason = f"MISSING_REGIME_THRESHOLD:{regime_name}"
            return result

        result.threshold_factor = factor
        signal_threshold = base_threshold * factor

        # Side bias penalties (same logic as AuroraScoringKernel)
        buy_bias_mult, sell_bias_mult = _compute_side_bias_mult(side_bias_state)
        result.buy_bias_mult = buy_bias_mult
        result.sell_bias_mult = sell_bias_mult

        thr_buy = signal_threshold * buy_bias_mult
        thr_sell = signal_threshold * sell_bias_mult
        result.thr_buy = thr_buy
        result.thr_sell = thr_sell

        # ─── Step 7: Side determination with hysteresis ──────────
        thr_neutral = neutral_threshold if neutral_threshold is not None else thr_buy
        result.side, side_why = _determine_side(
            signal_score, thr_buy, thr_sell, thr_neutral, current_side,
        )
        result.why_chain.append(side_why)

        return result


# =============================================================================
# Helper functions (extracted for testability)
# =============================================================================

def _resolve_regime_factor(
    regime_name: Optional[str],
    regime_thresholds: Dict[str, float],
) -> Optional[decimal.Decimal]:
    """Resolve regime threshold factor (same logic as legacy kernel)."""
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


def _compute_side_bias_mult(
    side_bias_state: Optional[SideBiasState],
) -> tuple[decimal.Decimal, decimal.Decimal]:
    """Compute buy/sell bias multipliers from side bias state."""
    buy_mult = decimal.Decimal("1.0")
    sell_mult = decimal.Decimal("1.0")

    if not side_bias_state:
        return buy_mult, sell_mult

    total = side_bias_state.buy_count + side_bias_state.sell_count
    if total < side_bias_state.min_intents:
        return buy_mult, sell_mult

    sell_share = decimal.Decimal(str(side_bias_state.sell_count)) / decimal.Decimal(str(total))
    target = decimal.Decimal(str(side_bias_state.target_ratio))
    penalty_factor = decimal.Decimal(str(side_bias_state.penalty_factor))

    if sell_share > target:
        excess = sell_share - target
        max_excess = decimal.Decimal("1.0") - target
        scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
        sell_mult += penalty_factor * scaling
    elif sell_share < (decimal.Decimal("1.0") - target):
        buy_share = decimal.Decimal("1.0") - sell_share
        excess = buy_share - target
        max_excess = decimal.Decimal("1.0") - target
        scaling = excess / max_excess if max_excess > 0 else decimal.Decimal("1.0")
        buy_mult += penalty_factor * scaling

    return buy_mult, sell_mult


def _determine_side(
    score: decimal.Decimal,
    thr_buy: decimal.Decimal,
    thr_sell: decimal.Decimal,
    thr_neutral: decimal.Decimal,
    current_side: str,
) -> tuple[str, str]:
    """
    3-zone hysteresis side determination.

    Returns (side, why_string).
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
