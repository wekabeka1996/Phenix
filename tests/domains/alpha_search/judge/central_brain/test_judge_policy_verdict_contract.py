from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    AgreementStateScores,
    HardUnknownConditions,
    JudgeMetaScoringConfig,
    StalePolicy,
    VerdictThresholds,
)
from apps.reference.domains.alpha_search.judge.central_brain.verdict import (
    ConfidenceBand,
    JudgePolicyVerdictV2,
    PolicyContext,
    ScoreComponents,
    VerdictRationale,
    VerdictSourceRefs,
)


def valid_config() -> JudgeMetaScoringConfig:
    return JudgeMetaScoringConfig(
        agreement_weight=0.35,
        confidence_weight=0.35,
        regime_weight=0.15,
        historical_surface_weight=0.10,
        missingness_penalty_weight=0.02,
        freshness_penalty_weight=1.0,
        disagreement_penalty_weight=0.20,
        no_expert_penalty=0.40,
        unknown_cap=0.25,
        min_confidence=0.0,
        max_confidence=1.0,
        verdict_thresholds=VerdictThresholds(
            open_long_min_confidence=0.60,
            open_short_min_confidence=0.60,
            suppress_max_confidence=0.20,
            unknown_max_evidence_score=0.05,
        ),
        stale_policy=StalePolicy(
            stale_regime_penalty=0.10,
            stale_market_penalty=0.10,
            missing_execution_readiness_penalty=0.05,
            missing_risk_context_penalty=0.05,
            missing_portfolio_context_penalty=0.05,
        ),
        hard_unknown_conditions=HardUnknownConditions(
            no_strategy_experts=True,
            missing_regime_context=False,
            missing_market_context=False,
        ),
        agreement_state_scores=AgreementStateScores(
            agree=1.0,
            single_expert=0.45,
            unknown=0.0,
            disagree=0.0,
            no_experts=0.0,
        ),
    )


def minimal_verdict() -> JudgePolicyVerdictV2:
    return JudgePolicyVerdictV2(
        verdict_id="verdict-1",
        envelope_id="env-1",
        created_ts_ms=1000,
        symbol="BTCUSDT",
        question_type="entry",
        verdict="UNKNOWN",
        confidence=0.10,
        confidence_band=ConfidenceBand(min=0.0, max=0.20, label="suppress_candidate"),
        rationale=VerdictRationale(
            summary="shadow verdict",
            disagreement_state="NO_EXPERTS",
        ),
        score_components=ScoreComponents(
            agreement_component=0.0,
            expert_confidence_component=0.0,
            regime_component=0.0,
            historical_surface_component=0.0,
            missingness_penalty=0.0,
            freshness_penalty=0.0,
            disagreement_penalty=0.0,
            final_score_before_clamp=0.10,
            final_confidence=0.10,
        ),
        policy_context=PolicyContext(runtime_mode=None),
        source_refs=VerdictSourceRefs(
            envelope_id="env-1",
            decision_id="decision-1",
            rid="rid-1",
            cycle_key="cycle-1",
        ),
    )


def test_valid_minimal_verdict_validates():
    verdict = minimal_verdict()
    assert verdict.authority_status == "shadow_only"
    assert verdict.applied is False
    assert verdict.confidence_source == "judge_meta_scorer_v1"


def test_extra_fields_are_rejected():
    payload = minimal_verdict().model_dump()
    payload["command"] = "OPEN"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_authority_status_cannot_differ_from_shadow_only():
    payload = minimal_verdict().model_dump()
    payload["authority_status"] = "live"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_applied_true_rejected():
    payload = minimal_verdict().model_dump()
    payload["applied"] = True
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_bridge_mode_cannot_differ_from_none():
    payload = minimal_verdict().model_dump()
    payload["policy_context"]["bridge_mode"] = "live_gated"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_confidence_source_fixed_to_meta_scorer():
    payload = minimal_verdict().model_dump()
    payload["confidence_source"] = "strategy_confidence"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


@pytest.mark.parametrize("field", ["cmd", "order_id", "canonical_intent", "place_order"])
def test_command_order_and_intent_fields_rejected(field: str):
    payload = minimal_verdict().model_dump()
    payload[field] = "forbidden"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_verdict_enum_validates():
    for verdict in ("OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"):
        payload = minimal_verdict().model_dump()
        payload["verdict"] = verdict
        assert JudgePolicyVerdictV2.model_validate(payload).verdict == verdict
    payload = minimal_verdict().model_dump()
    payload["verdict"] = "HOLD"
    with pytest.raises(ValidationError):
        JudgePolicyVerdictV2.model_validate(payload)


def test_score_components_rationale_and_source_refs_required():
    for field in ("score_components", "rationale", "source_refs"):
        payload = minimal_verdict().model_dump()
        payload.pop(field)
        with pytest.raises(ValidationError):
            JudgePolicyVerdictV2.model_validate(payload)


def test_source_refs_preserve_identity_fields():
    refs = minimal_verdict().source_refs
    assert refs.envelope_id == "env-1"
    assert refs.decision_id == "decision-1"
    assert refs.rid == "rid-1"
    assert refs.cycle_key == "cycle-1"


def test_valid_meta_scoring_config_validates():
    assert valid_config().schema_version == "1.0.0"


def test_negative_weights_rejected():
    payload = valid_config().model_dump()
    payload["agreement_weight"] = -0.1
    with pytest.raises(ValidationError):
        JudgeMetaScoringConfig.model_validate(payload)


def test_out_of_range_confidence_rejected():
    payload = valid_config().model_dump()
    payload["max_confidence"] = 1.1
    with pytest.raises(ValidationError):
        JudgeMetaScoringConfig.model_validate(payload)


def test_all_zero_positive_weights_rejected():
    payload = valid_config().model_dump()
    payload["agreement_weight"] = 0.0
    payload["confidence_weight"] = 0.0
    payload["regime_weight"] = 0.0
    payload["historical_surface_weight"] = 0.0
    with pytest.raises(ValidationError):
        JudgeMetaScoringConfig.model_validate(payload)


def test_invalid_thresholds_rejected():
    payload = valid_config().model_dump()
    payload["verdict_thresholds"]["open_long_min_confidence"] = -0.1
    with pytest.raises(ValidationError):
        JudgeMetaScoringConfig.model_validate(payload)


def test_unknown_config_fields_rejected():
    payload = valid_config().model_dump()
    payload["hidden_magic"] = 0.5
    with pytest.raises(ValidationError):
        JudgeMetaScoringConfig.model_validate(payload)

