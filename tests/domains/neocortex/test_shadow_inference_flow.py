from __future__ import annotations

import asyncio
import time
from pathlib import Path

import joblib
import numpy as np

from apps.reference.domains.decision_making.authority_bridge import NeocortexAuthorityBridge
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import BaselineController


class _FixedToxicModel:
    classes_ = np.array([0, 1])

    def __init__(self, toxic_probability: float) -> None:
        self.toxic_probability = toxic_probability

    def predict_proba(self, _frame):
        return np.array([[1.0 - self.toxic_probability, self.toxic_probability]])


def _write_baseline_artifact(path: Path, *, toxic_probability: float) -> None:
    joblib.dump(
        {
            "artifact_version": "test_baseline_logreg_v1",
            "model": _FixedToxicModel(toxic_probability),
            "feature_columns": ["f_danger_score"],
            "threshold": 0.835,
        },
        path,
    )


def _make_request() -> ControlDecisionRequest:
    now_ms = int(time.time() * 1000)
    return ControlDecisionRequest(
        decision_id="decision-shadow-001",
        rid="rid-shadow-001",
        symbol="BTCUSDT",
        proposed_action="OPEN_LONG",
        deadline_ms=now_ms + 1_000,
        decision_basis_ts=now_ms,
        causal_state_snapshot={"state_vector": [1.0]},
    )


def test_baseline_controller_predicts_block_for_dangerous_state_vector(tmp_path: Path) -> None:
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path, toxic_probability=0.90)

    controller = BaselineController(model_path=model_path)

    assert controller.predict_intent(np.array([1.0])) == "BLOCK"


def test_shadow_authority_logs_model_block_but_returns_allow(tmp_path: Path) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path, toxic_probability=0.90)
    controller = BaselineController(model_path=model_path)
    shadow_events: list[tuple[str, dict, str]] = []

    bridge = NeocortexAuthorityBridge(
        baseline_controller=controller,
        enforcement_mode="shadow",
        shadow_emit_fn=lambda event_name, payload, why: shadow_events.append(
            (event_name, payload, why)),
    )

    response = asyncio.run(bridge.request_authority(
        _make_request(), timeout_ms=1_000))

    assert response.action == ControlDecisionAction.ALLOW
    assert response.model_action == ControlDecisionAction.BLOCK
    assert response.enforcement_mode == "shadow"
    assert response.shadow_logged is True
    assert shadow_events

    event_name, payload, why = shadow_events[0]
    assert event_name == "SHADOW:NEOCORTEX_DECISION_LOGGED"
    assert why == "neocortex_baseline_shadow_decision"
    assert payload["action"] == "BLOCK"
    assert payload["data_quality_flags"]["returned_action"] == "ALLOW"
    assert payload["data_quality_flags"]["shadow_mode_forced_allow"] is True


def test_shadow_emit_failure_degrades_observability_without_crashing(tmp_path: Path) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path, toxic_probability=0.90)
    controller = BaselineController(model_path=model_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("emit failed")

    bridge = NeocortexAuthorityBridge(
        baseline_controller=controller,
        enforcement_mode="shadow",
        shadow_emit_fn=_boom,
    )

    response = asyncio.run(bridge.request_authority(
        _make_request(), timeout_ms=1_000))

    assert response.action == ControlDecisionAction.ALLOW
    assert response.shadow_logged is False
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code="HANDLER_FAILURE",
    ) == 1
