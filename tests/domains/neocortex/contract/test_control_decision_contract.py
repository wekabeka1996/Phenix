from __future__ import annotations

import pytest

from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import ObservationEnvelope
from apps.reference.domains.neocortex.logic.datasets.time_provenance import CausalTimeProvenance


def _observation() -> ObservationEnvelope:
    return ObservationEnvelope(
        observation_id="decision-1",
        symbol="BTCUSDT",
        decision_basis_ts_ms=1_700_000_000_000,
        source_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
        source_event_id="rid-1",
        event_time_source=CausalTimeProvenance.AURORA_EVENT,
        event_time_is_causal=True,
        trainable=True,
        dataset_visibility="trainable",
        freshness={"snapshot_age_ms": 0},
        missingness={"market_features_missing": False},
        market_features={"signal_score": 0.8},
        regime_state={"label": "TREND_UP", "confidence": 0.9},
        risk_state={"risk_score": 0.2},
        portfolio_state={"side": "FLAT"},
        system_stress_state={"trigger_event_type": "EVT:AUTHORITY_DECISION"},
        candidate_intent_summary={"side": "BUY", "reduce_only": False},
        gate_trace_summary={"final_outcome": "PASS"},
        state_vector=(0.8,),
        context_vector=(1.0,),
    )


def test_request_requires_decision_id_idempotency_and_expiry_contract() -> None:
    request = ControlDecisionRequest(
        decision_id="decision-1",
        rid="rid-1",
        symbol="BTCUSDT",
        authority_mode=AuthorityMode.SHADOW,
        decision_basis_ts_ms=1_700_000_000_000,
        deadline_ms=10,
        expires_at_ms=1_700_000_000_010,
        observation=_observation(),
        candidate_intent_summary={"side": "BUY"},
        idempotent_key="decision-1",
    )

    assert request.request_kind.value == "new_risk_intent"
    assert request.expires_at_ms == request.decision_basis_ts_ms + request.deadline_ms


def test_request_rejects_expiry_drift() -> None:
    with pytest.raises(ValueError, match="expires_at_ms"):
        ControlDecisionRequest(
            decision_id="decision-1",
            rid="rid-1",
            symbol="BTCUSDT",
            authority_mode=AuthorityMode.SHADOW,
            decision_basis_ts_ms=1_700_000_000_000,
            deadline_ms=10,
            expires_at_ms=1_700_000_000_011,
            observation=_observation(),
            candidate_intent_summary={"side": "BUY"},
            idempotent_key="decision-1",
        )


def test_response_requires_overlay_patch_only_for_modulate() -> None:
    response = ControlDecisionResponse(
        decision_id="decision-1",
        action=ControlDecisionAction.MODULATE,
        reason_code="MODEL_MODULATE",
        reason_text="future-tick modulation recorded",
        returned_at_ms=1_700_000_000_005,
        model_ref="baseline_controller",
        policy_ref="baseline_controller",
        idempotent_key="decision-1",
        overlay_patch={"decision_making.cooldown_mult": 1.5},
    )

    assert response.action == ControlDecisionAction.MODULATE

    with pytest.raises(ValueError, match="overlay_patch"):
        ControlDecisionResponse(
            decision_id="decision-1",
            action=ControlDecisionAction.ALLOW,
            reason_code="MODEL_ALLOW",
            reason_text="allowed",
            returned_at_ms=1_700_000_000_005,
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key="decision-1",
            overlay_patch={"decision_making.cooldown_mult": 1.5},
        )


def test_response_normalizes_legacy_block_alias_to_deny() -> None:
    response = ControlDecisionResponse(
        decision_id="decision-1",
        action="BLOCK",
        reason_code="MODEL_DENY",
        reason_text="denied",
        returned_at_ms=1_700_000_000_005,
        model_ref="baseline_controller",
        policy_ref="baseline_controller",
        idempotent_key="decision-1",
    )

    assert response.action == ControlDecisionAction.DENY
