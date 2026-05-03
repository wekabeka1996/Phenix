"""
J6-S16 — Policy Cortex Evaluator

Entry point for the policy cortex shadow annotation pipeline.
Wires together:
  1. Surface key builder
  2. Surface evidence registry lookup
  3. Policy classifier
  4. PolicyCortexAnnotation assembly

Called by the Entry Chamber / Judge verdict path as a shadow annotation step.

Does NOT:
- change execution behaviour
- emit CMD:OPEN / CMD:CLOSE
- grant advisory or production authority
- raise exceptions to the caller (all errors are logged and degraded to UNKNOWN)
"""

from __future__ import annotations

import logging
from typing import Optional

from apps.reference.domains.alpha_search.judge.policy_cortex.evidence_models import (
    PolicyCortexAnnotation,
)
from apps.reference.domains.alpha_search.judge.policy_cortex.policy_classifier import (
    build_concentration_flags,
    classify_surface,
)
from apps.reference.domains.alpha_search.judge.policy_cortex.surface_key_builder import (
    build_surface_key,
)
from apps.reference.domains.alpha_search.judge.policy_cortex.surface_registry import (
    SurfaceEvidenceRegistry,
    get_default_registry,
)

LOG = logging.getLogger(__name__)


def evaluate_policy_cortex(
    *,
    symbol: str,
    tf_sec: int,
    side: Optional[str],
    regime: Optional[str],
    tier: Optional[str] = None,
    strategy_id: Optional[str] = None,
    cycle_key: Optional[str] = None,
    registry: Optional[SurfaceEvidenceRegistry] = None,
) -> PolicyCortexAnnotation:
    """Evaluate the policy cortex for a candidate and return a shadow annotation.

    Args:
        symbol:      Trading pair symbol.
        tf_sec:      Timeframe in seconds.
        side:        Trade side ('BUY', 'SELL', 'LONG', 'SHORT') or None.
        regime:      Regime label or None.
        tier:        Confidence tier name from shadow plan, or None.
        strategy_id: Strategy identifier for provenance.
        cycle_key:   Canonical cycle key for telemetry correlation.
        registry:    Surface evidence registry (uses default if None).

    Returns:
        PolicyCortexAnnotation with shadow posture enforced.
        On any internal error: returns a degraded UNKNOWN annotation with
        reason_code 'cortex_evaluation_error:degraded_to_unknown'.
    """
    try:
        return _evaluate(
            symbol=symbol,
            tf_sec=tf_sec,
            side=side,
            regime=regime,
            tier=tier,
            strategy_id=strategy_id,
            cycle_key=cycle_key,
            registry=registry,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning(
            "PolicyCortex evaluation error for symbol=%s tf=%s regime=%s: %s — degrading to UNKNOWN",
            symbol, tf_sec, regime, exc,
        )
        return _build_error_annotation(
            symbol=symbol,
            tf_sec=tf_sec,
            side=side,
            regime=regime,
            cycle_key=cycle_key,
            tier=tier,
            strategy_id=strategy_id,
            error_msg=str(exc),
        )


def _evaluate(
    *,
    symbol: str,
    tf_sec: int,
    side: Optional[str],
    regime: Optional[str],
    tier: Optional[str],
    strategy_id: Optional[str],
    cycle_key: Optional[str],
    registry: Optional[SurfaceEvidenceRegistry],
) -> PolicyCortexAnnotation:
    reg = registry or get_default_registry()

    # 1. Build surface key
    surface_key = build_surface_key(
        regime=regime,
        side=side,
        symbol=symbol,
        tier_family=tier,
    )

    # 2. Lookup surface evidence
    record = reg.lookup(surface_key)

    # 3. Classify
    classifier_result = classify_surface(record)

    # 4. Build concentration flags
    concentration_flags = build_concentration_flags(record)

    # 5. Assemble annotation
    return PolicyCortexAnnotation(
        cycle_key=cycle_key,
        symbol=symbol,
        side=side,
        regime=regime,
        tf_sec=tf_sec,
        tier=tier,
        strategy_id=strategy_id,
        surface_key=surface_key,
        matched_surface_label=classifier_result.matched_surface_label,
        classifier_output=classifier_result.classifier_output,
        reason_codes=list(classifier_result.reason_codes),
        final_shadow_policy=classifier_result.classifier_output,
        concentration_flags=concentration_flags,
        sample_size=record.sample_size if record.label != "UNKNOWN" else None,
        avg_net_pnl=record.avg_net_pnl,
        late_avg_net_pnl=record.late_avg_net_pnl,
        ci_low=record.ci_low,
        ci_high=record.ci_high,
        evidence_registry_version=reg.evidence_version,
        source_artifact=reg.artifact_path,
        authority_mode="shadow",
        applied=False,
        advisory=False,
        production_authority=False,
        schema_version="1",
    )


def _build_error_annotation(
    *,
    symbol: str,
    tf_sec: int,
    side: Optional[str],
    regime: Optional[str],
    cycle_key: Optional[str],
    tier: Optional[str],
    strategy_id: Optional[str],
    error_msg: str,
) -> PolicyCortexAnnotation:
    """Build a degraded UNKNOWN annotation for use when evaluation fails."""
    surface_key = "unknown:error:unknown:unknown"
    return PolicyCortexAnnotation(
        cycle_key=cycle_key,
        symbol=symbol,
        side=side,
        regime=regime,
        tf_sec=tf_sec,
        tier=tier,
        strategy_id=strategy_id,
        surface_key=surface_key,
        matched_surface_label=None,
        classifier_output="UNKNOWN",
        reason_codes=[
            "cortex_evaluation_error:degraded_to_unknown",
            f"error:{error_msg[:120]}",
            "authority:shadow_only",
            "production_authority:false",
        ],
        final_shadow_policy="UNKNOWN",
        concentration_flags=[],
        sample_size=None,
        avg_net_pnl=None,
        late_avg_net_pnl=None,
        ci_low=None,
        ci_high=None,
        evidence_registry_version=None,
        source_artifact=None,
        authority_mode="shadow",
        applied=False,
        advisory=False,
        production_authority=False,
        schema_version="1",
    )
