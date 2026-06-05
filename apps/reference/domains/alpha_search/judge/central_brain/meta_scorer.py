from __future__ import annotations

import hashlib
from copy import deepcopy

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    JudgeEvidenceEnvelopeV2,
    JudgeMetaScoringConfig,
)
from apps.reference.domains.alpha_search.judge.central_brain.verdict import (
    ConfidenceBand,
    JudgePolicyVerdictV2,
    PolicyContext,
    ScoreComponents,
    VerdictRationale,
    VerdictSourceRefs,
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _directional_state(envelope: JudgeEvidenceEnvelopeV2) -> str | None:
    state = envelope.disagreement_map.agreement_state
    if state == "AGREE_LONG":
        return "BUY"
    if state == "AGREE_SHORT":
        return "SELL"
    if state == "SINGLE_EXPERT":
        for side in envelope.disagreement_map.side_opinions.values():
            if side in {"BUY", "SELL"}:
                return side
    if state == "DISAGREE":
        buy_count = sum(
            1 for side in envelope.disagreement_map.side_opinions.values() if side == "BUY"
        )
        sell_count = sum(
            1 for side in envelope.disagreement_map.side_opinions.values() if side == "SELL"
        )
        if buy_count > sell_count:
            return "BUY"
        if sell_count > buy_count:
            return "SELL"
    return None


def compute_agreement_component(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    state = envelope.disagreement_map.agreement_state
    if state in {"AGREE_LONG", "AGREE_SHORT"}:
        score = config.agreement_state_scores.agree
    elif state == "SINGLE_EXPERT":
        score = config.agreement_state_scores.single_expert
    elif state == "DISAGREE":
        score = config.agreement_state_scores.disagree
    elif state == "NO_EXPERTS":
        score = config.agreement_state_scores.no_experts
    else:
        score = config.agreement_state_scores.unknown
    return config.agreement_weight * score


def compute_expert_confidence_component(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    values = [
        value
        for value in envelope.disagreement_map.confidence_by_expert.values()
        if value is not None
    ]
    if not values:
        return 0.0
    return config.confidence_weight * (sum(values) / len(values))


def compute_regime_component(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    if not envelope.regime_context.present or envelope.regime_context.envelope is None:
        return 0.0
    regime = envelope.regime_context.envelope
    if regime.timing.freshness_state in {"STALE", "MISSING"}:
        return 0.0
    if regime.regime.confidence is None:
        return 0.0
    return config.regime_weight * regime.regime.confidence


def compute_historical_surface_component(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    surface = envelope.historical_surface_evidence
    if not surface.present:
        return 0.0
    if surface.sample_count is None or surface.sample_count <= 0:
        return 0.0
    if surface.expectancy_net is None or surface.expectancy_net <= 0:
        return 0.0
    return config.historical_surface_weight


def compute_missingness_penalty(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    penalty = 0.0
    missing_blocks = [
        name
        for name, state in envelope.freshness_missingness_map.per_block.items()
        if state == "MISSING"
    ]
    penalty += config.missingness_penalty_weight * len(missing_blocks)
    if not envelope.risk_context.present:
        penalty += config.stale_policy.missing_risk_context_penalty
    if not envelope.portfolio_context.present:
        penalty += config.stale_policy.missing_portfolio_context_penalty
    if not envelope.execution_readiness.present:
        penalty += config.stale_policy.missing_execution_readiness_penalty
    if envelope.disagreement_map.agreement_state == "NO_EXPERTS":
        penalty += config.no_expert_penalty
    return penalty


def compute_freshness_penalty(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    penalty = 0.0
    if envelope.market_context.data_freshness_state in {"STALE", "MISSING"}:
        penalty += config.stale_policy.stale_market_penalty
    if envelope.regime_context.present and envelope.regime_context.envelope is not None:
        if envelope.regime_context.envelope.timing.freshness_state in {"STALE", "MISSING"}:
            penalty += config.stale_policy.stale_regime_penalty
    return penalty * config.freshness_penalty_weight


def compute_disagreement_penalty(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> float:
    if envelope.disagreement_map.agreement_state == "DISAGREE":
        return config.disagreement_penalty_weight
    return 0.0


def _blocking_reasons(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
    final_score_before_clamp: float,
) -> list[str]:
    reasons: list[str] = []
    if (
        config.hard_unknown_conditions.no_strategy_experts
        and envelope.disagreement_map.agreement_state == "NO_EXPERTS"
    ):
        reasons.append("hard_unknown:no_strategy_experts")
    if (
        config.hard_unknown_conditions.missing_regime_context
        and not envelope.regime_context.present
    ):
        reasons.append("hard_unknown:missing_regime_context")
    if (
        config.hard_unknown_conditions.missing_market_context
        and envelope.freshness_missingness_map.per_block.get("market_context") == "MISSING"
    ):
        reasons.append("hard_unknown:missing_market_context")
    if final_score_before_clamp <= config.verdict_thresholds.unknown_max_evidence_score:
        reasons.append("evidence_score_below_unknown_threshold")
    return reasons


def classify_verdict(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
    confidence: float,
    blocking_reasons: list[str],
) -> str:
    if any(reason.startswith("hard_unknown:") for reason in blocking_reasons):
        return "UNKNOWN"
    state = envelope.disagreement_map.agreement_state
    if state == "AGREE_LONG" and confidence >= config.verdict_thresholds.open_long_min_confidence:
        return "OPEN_LONG"
    if state == "AGREE_SHORT" and confidence >= config.verdict_thresholds.open_short_min_confidence:
        return "OPEN_SHORT"
    poor_evidence = bool(blocking_reasons) or state in {"NO_EXPERTS", "UNKNOWN"}
    if poor_evidence and confidence <= config.verdict_thresholds.suppress_max_confidence:
        return "SUPPRESS"
    if state in {"DISAGREE", "SINGLE_EXPERT", "UNKNOWN"}:
        return "NO_ENTRY"
    return "UNKNOWN"


def classify_confidence_band(
    confidence: float,
    config: JudgeMetaScoringConfig,
) -> ConfidenceBand:
    open_min = min(
        config.verdict_thresholds.open_long_min_confidence,
        config.verdict_thresholds.open_short_min_confidence,
    )
    if confidence >= open_min:
        return ConfidenceBand(
            min=open_min,
            max=config.max_confidence,
            label="open_candidate",
        )
    if confidence <= config.verdict_thresholds.suppress_max_confidence:
        return ConfidenceBand(
            min=config.min_confidence,
            max=config.verdict_thresholds.suppress_max_confidence,
            label="suppress_candidate",
        )
    if confidence <= config.verdict_thresholds.unknown_max_evidence_score:
        return ConfidenceBand(
            min=config.min_confidence,
            max=config.verdict_thresholds.unknown_max_evidence_score,
            label="unknown_candidate",
        )
    return ConfidenceBand(
        min=config.verdict_thresholds.suppress_max_confidence,
        max=open_min,
        label="middle_band",
    )


def _supporting_and_dissenting_experts(
    envelope: JudgeEvidenceEnvelopeV2,
) -> tuple[list[str], list[str]]:
    target_side = _directional_state(envelope)
    if target_side is None:
        return [], [
            expert
            for expert, side in envelope.disagreement_map.side_opinions.items()
            if side in {"BUY", "SELL"}
        ]
    supporting: list[str] = []
    dissenting: list[str] = []
    for expert, side in envelope.disagreement_map.side_opinions.items():
        if side == target_side:
            supporting.append(expert)
        elif side in {"BUY", "SELL"}:
            dissenting.append(expert)
    return supporting, dissenting


def _missing_evidence(envelope: JudgeEvidenceEnvelopeV2) -> list[str]:
    return sorted(
        field
        for field, state in envelope.freshness_missingness_map.per_field.items()
        if state
    )


def _freshness_warnings(envelope: JudgeEvidenceEnvelopeV2) -> list[str]:
    warnings: list[str] = []
    if envelope.market_context.data_freshness_state in {"STALE", "MISSING"}:
        warnings.append(f"market_context:{envelope.market_context.data_freshness_state}")
    if envelope.regime_context.present and envelope.regime_context.envelope is not None:
        state = envelope.regime_context.envelope.timing.freshness_state
        if state in {"STALE", "MISSING"}:
            warnings.append(f"regime_context:{state}")
    return warnings


def build_rationale(
    envelope: JudgeEvidenceEnvelopeV2,
    verdict: str,
    blocking_reasons: list[str],
) -> VerdictRationale:
    supporting, dissenting = _supporting_and_dissenting_experts(envelope)
    state = envelope.disagreement_map.agreement_state
    return VerdictRationale(
        summary=f"{verdict} from {state} with evidence-only shadow authority",
        supporting_experts=supporting,
        dissenting_experts=dissenting,
        blocking_reasons=blocking_reasons,
        missing_evidence=_missing_evidence(envelope),
        freshness_warnings=_freshness_warnings(envelope),
        disagreement_state=state,
    )


def _verdict_id(envelope: JudgeEvidenceEnvelopeV2) -> str:
    raw = f"{envelope.envelope_id}|{envelope.created_ts_ms}|{envelope.question_type}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"judge_policy_v2_{digest}"


def score_judge_envelope(
    envelope: JudgeEvidenceEnvelopeV2,
    config: JudgeMetaScoringConfig,
) -> JudgePolicyVerdictV2:
    envelope_snapshot = envelope.model_dump()
    agreement_component = compute_agreement_component(envelope, config)
    expert_confidence_component = compute_expert_confidence_component(envelope, config)
    regime_component = compute_regime_component(envelope, config)
    historical_surface_component = compute_historical_surface_component(
        envelope,
        config,
    )
    missingness_penalty = compute_missingness_penalty(envelope, config)
    freshness_penalty = compute_freshness_penalty(envelope, config)
    disagreement_penalty = compute_disagreement_penalty(envelope, config)
    final_score_before_clamp = (
        agreement_component
        + expert_confidence_component
        + regime_component
        + historical_surface_component
        - missingness_penalty
        - freshness_penalty
        - disagreement_penalty
    )
    clamped_confidence = _clamp(
        final_score_before_clamp,
        config.min_confidence,
        config.max_confidence,
    )
    blocking_reasons = _blocking_reasons(envelope, config, final_score_before_clamp)
    verdict = classify_verdict(envelope, config, clamped_confidence, blocking_reasons)
    final_confidence = (
        min(clamped_confidence, config.unknown_cap)
        if verdict == "UNKNOWN"
        else clamped_confidence
    )
    components = ScoreComponents(
        agreement_component=agreement_component,
        expert_confidence_component=expert_confidence_component,
        regime_component=regime_component,
        historical_surface_component=historical_surface_component,
        missingness_penalty=missingness_penalty,
        freshness_penalty=freshness_penalty,
        disagreement_penalty=disagreement_penalty,
        final_score_before_clamp=final_score_before_clamp,
        final_confidence=final_confidence,
    )
    result = JudgePolicyVerdictV2(
        verdict_id=_verdict_id(envelope),
        envelope_id=envelope.envelope_id,
        created_ts_ms=envelope.created_ts_ms,
        symbol=envelope.symbol,
        question_type=envelope.question_type,
        verdict=verdict,  # type: ignore[arg-type]
        confidence=final_confidence,
        confidence_band=classify_confidence_band(final_confidence, config),
        rationale=build_rationale(envelope, verdict, blocking_reasons),
        score_components=components,
        policy_context=PolicyContext(
            runtime_mode=envelope.runtime_mode,
            bridge_mode="none",
            source_envelope_version=envelope.schema_version,
        ),
        source_refs=VerdictSourceRefs(
            envelope_id=envelope.envelope_id,
            decision_id=envelope.decision_id,
            rid=envelope.rid,
            cycle_key=envelope.cycle_key,
        ),
    )
    if envelope.model_dump() != envelope_snapshot:
        raise RuntimeError("score_judge_envelope mutated input envelope")
    return result
