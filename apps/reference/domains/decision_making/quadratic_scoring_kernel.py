"""Quadratic Aurora scoring kernel and its result DTOs.

The kernel converts an upstream linear conviction input into decision and sizing
scores, then applies regime-threshold scaling, side-bias penalties, and
hysteresis-based side selection. The default Aurora geometry remains signed
quadratic on both admission and sizing paths, but compute() also supports
decoupled admission/sizing transforms used by the newer decision-geometry
contract.

Boundary notes proven in current runtime wiring:
- the kernel owns math transformation plus side selection inside the scoring
    boundary;
- it does not emit policy-blocked semantics for ordinary live denials;
- several kwargs are accepted only for shared call-site compatibility and are
    intentionally ignored here.
"""
from __future__ import annotations

import decimal
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable


@dataclass
class ScoringResult:
    """Structured output returned by QuadraticScoringKernel.compute().

    ``score`` mirrors ``decision_score`` because downstream Aurora call sites
    still read a single primary score field. ``sizing_score`` may diverge from
    ``decision_score`` when admission and sizing transforms or shield floors are
    decoupled.
    """

    # Core outputs
    score: decimal.Decimal
    side: str  # Lower-case "buy", "sell", or neutral ""
    thr_buy: decimal.Decimal
    thr_sell: decimal.Decimal
    decision_score: decimal.Decimal = decimal.Decimal("0")
    sizing_score: decimal.Decimal = decimal.Decimal("0")
    raw_score: decimal.Decimal = decimal.Decimal("0")
    admission_shield_multiplier: decimal.Decimal = decimal.Decimal("1.0")

    # Explainability payload returned to callers and logs.
    why_chain: List[str] = field(default_factory=list)
    psi_vector: Dict[str, Any] = field(default_factory=dict)

    # Regime context
    regime: Optional[str] = None
    threshold_factor: decimal.Decimal = decimal.Decimal("1.0")

    # Side bias context
    buy_bias_mult: decimal.Decimal = decimal.Decimal("1.0")
    sell_bias_mult: decimal.Decimal = decimal.Decimal("1.0")

    # Deferred state is reserved for kernel-local fail-closed/anomaly outcomes.
    deferred: bool = False
    defer_reason: Optional[str] = None

    # Shield telemetry mirrors the active attenuation branch taken by compute().
    shield_multiplier: decimal.Decimal = decimal.Decimal("1.0")
    shield_breakdown: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SideBiasState:
    """Windowed side-intent counts used to widen one side's entry threshold.

    The kernel does not build this structure itself. AuroraScoringHelpersMixin
    supplies a pre-pruned snapshot, and the kernel only converts it into buy/sell
    threshold multipliers.
    """

    buy_count: int = 0
    sell_count: int = 0
    window_sec: float = 420.0
    target_ratio: float = 0.72
    penalty_factor: float = 0.25
    min_intents: int = 18


@dataclass
class QuadraticContext:
    """Local explainability snapshot shape for quadratic scoring internals.

    The live ScoringResult contract currently exposes the same information via
    ``psi_vector`` and ``shield_breakdown`` rather than returning this DTO.
    """
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
    """Compatibility pass-through used when the caller omitted shield_fn.

    Production fail-closed enforcement against an effectively disabled shield
    stack happens outside this module during config validation and wiring.
    """
    return 1.0, []


class QuadraticScoringKernel:
    """
    Non-linear scoring kernel for Aurora's active math path.

    Default geometry:
        sign(S) * |S|^2

    Actual compute() flow:
    1. resolve a linear input from ``linear_score`` or ``features['pillar_sum']``;
    2. scale and clamp it to [-1, 1];
    3. transform admission and sizing scores, optionally with different modes;
    4. apply shield attenuation and the optional admission shield floor;
    5. widen thresholds via regime factors and side-bias penalties;
    6. choose a side with 3-zone hysteresis.
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
        Compute decision and sizing scores for one symbol snapshot.

        Live inputs read by this implementation:
        - ``linear_score`` or ``features['pillar_sum']``
        - ``base_threshold`` plus ``regime_name`` / ``regime_thresholds``
        - ``side_bias_state``
        - ``shield_fn``
        - ``current_side`` and ``neutral_threshold``
        - transform controls such as ``admission_mode`` and ``sizing_mode``

        Compatibility-only kwargs accepted but not read here include:
        ``warmup_readiness``, ``price``, ``signal_weights``,
        ``feature_neutrals``, ``essential_features``,
        ``direction_strength_cfg``, ``delta_price_cap_pct``,
        ``scoring_version``, ``normalize_mode``, and ``regime_smoother``.

        Raises:
            ValueError: if a transform mode is unsupported or soft_power is
                requested without an explicit exponent. Live Aurora callers
                handle that fail-closed outside the kernel.
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

        # ``linear_score`` bypasses the feature contract and is mainly used by
        # callers that have already computed the aggregate conviction upstream.
        if linear_score is not None:
            s_linear = linear_score
            source = "arg"
        else:
            # The canonical Aurora feature contract exposes the aggregate as
            # ``pillar_sum``. Missing/invalid values defer rather than raise.
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

        # score_multiplier adjusts sensitivity before the transform, but the
        # kernel still enforces the invariant that transformed input stays in [-1, 1].
        s_scaled_raw = s_linear * score_multiplier

        s_clamped = max(-1.0, min(1.0, s_scaled_raw))

        # Admission and sizing may intentionally diverge. Decision-score logic
        # can stay more permissive or more conservative than sizing-score logic.
        admission_pre_shield = _transform_signed_score(
            s_clamped, mode=admission_mode, power=admission_power
        )
        sizing_pre_shield = _transform_signed_score(
            s_clamped, mode=sizing_mode, power=sizing_power
        )

        # The shield sees the raw linear conviction together with the sizing
        # transform. Hard vetoes force both branches to zero.
        shield_mult, shield_reasons = _shield(
            symbol, features, s_linear, sizing_pre_shield)
        shield_mult = max(0.0, min(1.0, shield_mult))

        if shield_mult == 0.0:
            admission_shield_mult = 0.0
        else:
            # admission_shield_floor can only lift a non-zero attenuation;
            # it never overrides a proven hard veto.
            admission_shield_mult = max(
                shield_mult,
                max(0.0, min(1.0, admission_shield_floor)),
            )

        decision_score_val = admission_pre_shield * admission_shield_mult
        sizing_score_val = sizing_pre_shield * shield_mult

        # ``score`` remains aliased to decision_score for compatibility with
        # older consumers that still read a single primary score field.
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

        # Threshold widening is still part of the active kernel contract even
        # though the upstream v2 linear kernel has been removed.
        factor = _resolve_regime_factor(regime_name, regime_thresholds)
        if factor is None:
            result.deferred = True
            result.defer_reason = f"MISSING_REGIME_THRESHOLD:{regime_name}"
            return result

        result.threshold_factor = factor
        signal_threshold = base_threshold * factor

        # Side-bias widens only the overloaded side once enough history exists.
        buy_bias_mult, sell_bias_mult = _compute_side_bias_mult(
            side_bias_state)
        result.buy_bias_mult = buy_bias_mult
        result.sell_bias_mult = sell_bias_mult

        thr_buy = signal_threshold * buy_bias_mult
        thr_sell = signal_threshold * sell_bias_mult
        result.thr_buy = thr_buy
        result.thr_sell = thr_sell

        # Hysteresis is evaluated on the decision score, not on sizing score.
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
    """Resolve the positive finite regime multiplier used to widen thresholds.

    Returns None when neither the named regime nor DEFAULT yields a valid
    positive Decimal. The caller converts that into a kernel defer path.
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


def _compute_side_bias_mult(
    side_bias_state: Optional[SideBiasState],
) -> tuple[decimal.Decimal, decimal.Decimal]:
    """Compute threshold multipliers from the windowed side-bias snapshot.

    No penalty is applied until ``min_intents`` has been reached. After that,
    only the overloaded side is widened, scaled by how far the observed share is
    past the configured target_ratio.
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


def _determine_side(
    score: decimal.Decimal,
    thr_buy: decimal.Decimal,
    thr_sell: decimal.Decimal,
    thr_neutral: decimal.Decimal,
    current_side: str,
) -> tuple[str, str]:
    """
    Apply 3-zone hysteresis and return a lower-case side plus explanation.

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


def _transform_signed_score(
    value: float,
    *,
    mode: str,
    power: Optional[float],
) -> float:
    """Transform a signed score magnitude under the configured geometry mode.

    Supported modes:
    - ``quadratic``: sign(x) * |x|^2
    - ``linear``: x unchanged
    - ``soft_power``: sign(x) * |x|^power

    Invalid mode/exponent combinations raise ValueError intentionally so the
    caller can fail closed instead of inventing fallback math.
    """
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
