"""Quadratic Aurora scoring kernel and its result DTOs.

The kernel converts an upstream linear conviction input into decision and sizing
scores, then applies regime-threshold scaling, side-bias penalties, and
hysteresis-based side selection. The default Aurora geometry remains signed
quadratic on both admission and sizing paths, but compute() also supports
decoupled admission/sizing transforms used by the newer decision-geometry
contract.

Package 2 decomposition:
- Math transforms are delegated to ``aurora_math.compute_aurora_math()``.
- Policy interpretation is delegated to ``aurora_policy.apply_aurora_policy()``.
- This module is now a thin orchestration layer that composes math + policy
  and assembles the ScoringResult with full backward-compatible fields.

The private helper functions (_resolve_regime_factor, _compute_side_bias_mult,
_determine_side, _transform_signed_score) are retained as thin delegating
wrappers so any external callers or tests that import them continue to work.
"""
from __future__ import annotations

import decimal
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.reference.shared.decision_primitives.aurora_math import (
    AuroraMathInput,
    AuroraMathOutput,
    ShieldFn,
    compute_aurora_math,
    transform_signed_score as _math_transform_signed_score,
)
from apps.reference.shared.decision_primitives.aurora_policy import (
    AuroraPolicyInput,
    AuroraPolicyDecision,
    SideBiasState,
    apply_aurora_policy,
    resolve_regime_factor as _policy_resolve_regime_factor,
    compute_side_bias_multipliers as _policy_compute_side_bias_mult,
    determine_side as _policy_determine_side,
)


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


class QuadraticScoringKernel:
    """
    Non-linear scoring kernel for Aurora's active path.

    Package 2: This kernel is now a thin orchestration layer that composes:
    1. aurora_math.compute_aurora_math() — pure numeric transforms
    2. aurora_policy.apply_aurora_policy() — threshold/hysteresis/side decisions

    Default geometry:
        sign(S) * |S|^2

    Actual compute() flow:
    1. resolve a linear input from ``linear_score`` or ``features['pillar_sum']``;
    2. delegate math: scale, clamp, transform, shield via aurora_math;
    3. delegate policy: regime factor, side-bias, hysteresis via aurora_policy;
    4. assemble ScoringResult with full backward-compatible fields.
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
        # ── Input resolution (orchestration) ─────────────────────────
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

        # ── MATH LAYER (delegated to aurora_math) ────────────────────
        math_input = AuroraMathInput(
            s_linear=s_linear,
            source=source,
            score_multiplier=score_multiplier,
            admission_mode=admission_mode,
            admission_power=admission_power,
            sizing_mode=sizing_mode,
            sizing_power=sizing_power,
            admission_shield_floor=admission_shield_floor,
            symbol=symbol,
            features=features,
            pillar_contribs=dict(pillar_contribs or {}),
        )
        math_out = compute_aurora_math(math_input, shield_fn=shield_fn)

        # Populate result with math outputs
        result.decision_score = decimal.Decimal(
            str(round(math_out.decision_score, 8)))
        result.sizing_score = decimal.Decimal(
            str(round(math_out.sizing_score, 8)))
        result.score = result.decision_score
        result.admission_shield_multiplier = decimal.Decimal(
            str(round(math_out.admission_shield_multiplier, 8))
        )

        # Build psi_vector from math output (trace)
        result.psi_vector = {
            "scoring_engine": "quadratic_v1",
            "source": math_out.source,
            "s_linear": math_out.s_linear,
            "multiplier": math_out.score_multiplier,
            "s_scaled_raw": math_out.s_scaled_raw,
            "s_clamped": math_out.s_clamped,
            "clamped": math_out.clamped,
            "admission_mode": math_out.admission_mode,
            "admission_power": math_out.admission_power,
            "sizing_mode": math_out.sizing_mode,
            "sizing_power": math_out.sizing_power,
            "admission_shield_floor": math_out.admission_shield_floor,
            "admission_pre_shield": math_out.admission_pre_shield,
            "sizing_pre_shield": math_out.sizing_pre_shield,
            "decision_score": math_out.decision_score,
            "sizing_score": math_out.sizing_score,
            "admission_shield_multiplier": math_out.admission_shield_multiplier,
            "final_exposure": math_out.sizing_score,
            "shield_multiplier": math_out.shield_multiplier,
            "shield_reasons": list(math_out.shield_reasons),
        }

        # Populate Phase 9 Shield Context from math output
        result.shield_multiplier = decimal.Decimal(
            str(math_out.shield_multiplier))
        result.shield_breakdown = {
            "reasons": list(math_out.shield_reasons),
            "raw_exposure": math_out.sizing_pre_shield,
            "s_linear": math_out.s_linear,
            "decision_score": math_out.decision_score,
            "sizing_score": math_out.sizing_score,
            "admission_shield_multiplier": math_out.admission_shield_multiplier,
        }

        # ── POLICY LAYER (delegated to aurora_policy) ────────────────
        policy_input = AuroraPolicyInput(
            decision_score=math_out.decision_score,
            sizing_score=math_out.sizing_score,
            base_threshold=base_threshold,
            regime_name=regime_name,
            regime_thresholds=regime_thresholds,
            side_bias_state=side_bias_state,
            neutral_threshold=neutral_threshold,
            current_side=current_side,
        )
        policy_out = apply_aurora_policy(policy_input)

        if policy_out.deferred:
            result.deferred = True
            result.defer_reason = policy_out.defer_reason
            return result

        result.threshold_factor = policy_out.threshold_factor
        result.buy_bias_mult = policy_out.buy_bias_mult
        result.sell_bias_mult = policy_out.sell_bias_mult
        result.thr_buy = policy_out.thr_buy
        result.thr_sell = policy_out.thr_sell
        result.side = policy_out.side
        result.why_chain.append(policy_out.side_why)

        # Update psi_vector with policy output (trace enrichment)
        result.psi_vector.update(
            {
                "raw_exposure": math_out.sizing_pre_shield,
                "final_score": math_out.decision_score,
                "threshold_factor": float(policy_out.threshold_factor),
                "thr_buy": float(policy_out.thr_buy),
                "thr_sell": float(policy_out.thr_sell),
                "buy_bias_mult": float(policy_out.buy_bias_mult),
                "sell_bias_mult": float(policy_out.sell_bias_mult),
                "side_why": policy_out.side_why,
            }
        )

        return result


# =============================================================================
# Backward-compatible wrapper functions
# =============================================================================
# These thin wrappers delegate to aurora_math / aurora_policy so that any
# external code importing the private helpers from this module still works.

def _resolve_regime_factor(
    regime_name: Optional[str],
    regime_thresholds: Dict[str, float],
) -> Optional[decimal.Decimal]:
    """Wrapper → aurora_policy.resolve_regime_factor."""
    return _policy_resolve_regime_factor(regime_name, regime_thresholds)


def _compute_side_bias_mult(
    side_bias_state: Optional[SideBiasState],
) -> tuple[decimal.Decimal, decimal.Decimal]:
    """Wrapper → aurora_policy.compute_side_bias_multipliers."""
    return _policy_compute_side_bias_mult(side_bias_state)


def _determine_side(
    score: decimal.Decimal,
    thr_buy: decimal.Decimal,
    thr_sell: decimal.Decimal,
    thr_neutral: decimal.Decimal,
    current_side: str,
) -> tuple[str, str]:
    """Wrapper → aurora_policy.determine_side."""
    return _policy_determine_side(score, thr_buy, thr_sell, thr_neutral, current_side)


def _transform_signed_score(
    value: float,
    *,
    mode: str,
    power: Optional[float],
) -> float:
    """Wrapper → aurora_math.transform_signed_score."""
    return _math_transform_signed_score(value, mode=mode, power=power)
