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
- Sole active scoring kernel (Phase 9). v1/v2 kernels deleted.
- Same ScoringResult output contract
- Pillar sum injected via features["pillar_sum"]

Shield:
- Accepts optional shield_fn that can veto/attenuate signal
- NullShield (default) passes everything through but is forbidden in production (fail-closed)
"""
from __future__ import annotations

import decimal
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable


@dataclass
class ScoringResult:
    """Result of scoring kernel computation."""

    # Core outputs
    score: decimal.Decimal
    side: str  # "buy", "sell", or ""
    thr_buy: decimal.Decimal
    thr_sell: decimal.Decimal
    decision_score: decimal.Decimal = decimal.Decimal("0")
    sizing_score: decimal.Decimal = decimal.Decimal("0")
    raw_score: decimal.Decimal = decimal.Decimal("0")
    admission_shield_multiplier: decimal.Decimal = decimal.Decimal("1.0")

    # Explainability
    why_chain: List[str] = field(default_factory=list)
    psi_vector: Dict[str, Any] = field(default_factory=dict)

    # Regime context
    regime: Optional[str] = None
    threshold_factor: decimal.Decimal = decimal.Decimal("1.0")

    # Side bias context
    buy_bias_mult: decimal.Decimal = decimal.Decimal("1.0")
    sell_bias_mult: decimal.Decimal = decimal.Decimal("1.0")

    # Deferred state
    deferred: bool = False
    defer_reason: Optional[str] = None

    # Phase 9: Shield context
    shield_multiplier: decimal.Decimal = decimal.Decimal("1.0")
    shield_breakdown: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SideBiasState:
    """Side bias window state for penalty calculation."""

    buy_count: int = 0
    sell_count: int = 0
    window_sec: float = 420.0
    target_ratio: float = 0.72
    penalty_factor: float = 0.25
    min_intents: int = 18


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

    Output contract: ScoringResult dataclass.
    """

    @staticmethod
    def compute(
        *,
        symbol: str,
        features: Dict[str, Any],
        warmup_readiness: Dict[str, bool],
        price: decimal.Decimal,
        # DEPRECATED: signal_weights, feature_neutrals, direction_strength_cfg
        # are accepted for call-site compat but NOT read by Quadratic kernel.
        # Quadratic reads pillar_sum only.
        signal_weights: Dict[str, float],
        feature_neutrals: Dict[str, float],
        essential_features: List[str],
        base_threshold: decimal.Decimal,
        regime_name: Optional[str],
        regime_thresholds: Dict[str, float],
        side_bias_state: Optional[SideBiasState],
        direction_strength_cfg: Dict[str, Any],
        delta_price_cap_pct: decimal.Decimal,
        scoring_version: str = "quadratic",
        # Hysteresis support
        neutral_threshold: Optional[decimal.Decimal] = None,
        current_side: str = "",
        normalize_mode: str = "signed_v2",
        # Phase 9 extensions
        shield_fn: Optional[ShieldFn] = None,
        pillar_contribs: Optional[Dict[str, float]] = None,
        score_multiplier: float = 1.0,
        linear_score: Optional[float] = None,
        regime_smoother: Optional[Any] = None,
        admission_mode: str = "quadratic",
        admission_power: Optional[float] = None,
        sizing_mode: str = "quadratic",
        sizing_power: Optional[float] = None,
        admission_shield_floor: float = 0.0,
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
                # FE pillars not ready yet (normal during warmup)
                result.defer_reason = "PILLAR_WARMUP"
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
        result.raw_score = decimal.Decimal(str(round(s_linear, 8)))

        # ─── Step 2: Scale & Clamp (Sensitivity) ──────────────────
        # Formula: S_scaled = clamp(S_linear * M, -1, 1)
        s_scaled_raw = s_linear * score_multiplier

        # SAFETY CAP: Enforce [-1, 1] invariant before squaring
        s_clamped = max(-1.0, min(1.0, s_scaled_raw))

        # ─── Step 3: Admission / Sizing transforms ───────────────
        admission_pre_shield = _transform_signed_score(
            s_clamped, mode=admission_mode, power=admission_power
        )
        sizing_pre_shield = _transform_signed_score(
            s_clamped, mode=sizing_mode, power=sizing_power
        )

        # ─── Step 4: Shield Cascade ──────────────────────────────
        shield_mult, shield_reasons = _shield(
            symbol, features, s_linear, sizing_pre_shield)
        shield_mult = max(0.0, min(1.0, shield_mult))

        if shield_mult == 0.0:
            admission_shield_mult = 0.0
        else:
            admission_shield_mult = max(
                shield_mult,
                max(0.0, min(1.0, admission_shield_floor)),
            )

        decision_score_val = admission_pre_shield * admission_shield_mult
        sizing_score_val = sizing_pre_shield * shield_mult

        # ─── Step 5: Output & Explainability ─────────────────────
        result.decision_score = decimal.Decimal(
            str(round(decision_score_val, 8)))
        result.sizing_score = decimal.Decimal(str(round(sizing_score_val, 8)))
        result.score = result.decision_score
        result.admission_shield_multiplier = decimal.Decimal(
            str(round(admission_shield_mult, 8))
        )

        quad_ctx = QuadraticContext(
            pillar_sum=s_linear,
            raw_exposure=sizing_pre_shield,
            shield_multiplier=shield_mult,
            final_exposure=sizing_score_val,
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
            "admission_mode": admission_mode,
            "admission_power": admission_power,
            "sizing_mode": sizing_mode,
            "sizing_power": sizing_power,
            "admission_shield_floor": admission_shield_floor,
            "admission_pre_shield": admission_pre_shield,
            "sizing_pre_shield": sizing_pre_shield,
            "decision_score": decision_score_val,
            "sizing_score": sizing_score_val,
            "admission_shield_multiplier": admission_shield_mult,
            "final_exposure": sizing_score_val,
            "shield_multiplier": shield_mult,
            "shield_reasons": list(shield_reasons),
        }

        # Populate Phase 9 Shield Context
        result.shield_multiplier = decimal.Decimal(str(shield_mult))
        result.shield_breakdown = {
            "reasons": list(shield_reasons),
            "raw_exposure": sizing_pre_shield,
            "s_linear": s_linear,
            "decision_score": decision_score_val,
            "sizing_score": sizing_score_val,
            "admission_shield_multiplier": admission_shield_mult,
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

        # Side bias penalties
        buy_bias_mult, sell_bias_mult = _compute_side_bias_mult(
            side_bias_state)
        result.buy_bias_mult = buy_bias_mult
        result.sell_bias_mult = sell_bias_mult

        thr_buy = signal_threshold * buy_bias_mult
        thr_sell = signal_threshold * sell_bias_mult
        result.thr_buy = thr_buy
        result.thr_sell = thr_sell

        # ─── Step 7: Side determination with hysteresis ──────────
        thr_neutral = neutral_threshold if neutral_threshold is not None else thr_buy
        result.side, side_why = _determine_side(
            result.decision_score, thr_buy, thr_sell, thr_neutral, current_side,
        )
        result.why_chain.append(side_why)
        result.psi_vector.update(
            {
                "raw_exposure": sizing_pre_shield,
                "final_score": decision_score_val,
                "threshold_factor": float(factor),
                "thr_buy": float(thr_buy),
                "thr_sell": float(thr_sell),
                "buy_bias_mult": float(buy_bias_mult),
                "sell_bias_mult": float(sell_bias_mult),
                "side_why": side_why,
            }
        )

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


def _transform_signed_score(
    value: float,
    *,
    mode: str,
    power: Optional[float],
) -> float:
    sign = 1.0 if value >= 0 else -1.0
    magnitude = abs(value)

    if mode == "quadratic":
        return sign * (magnitude ** 2)
    if mode == "linear":
        return value
    if mode == "soft_power":
        if power is None:
            raise ValueError("soft_power transform requires explicit power")
        return sign * (magnitude ** float(power))
    raise ValueError(f"unsupported transform mode: {mode}")
