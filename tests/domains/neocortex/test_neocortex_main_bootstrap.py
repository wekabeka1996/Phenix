from __future__ import annotations

import asyncio
from pathlib import Path

import joblib
import numpy as np
import pytest

from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import BaselineController
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
)
from apps.reference.domains.neocortex.main import (
    FatalStartupError,
    SHADOW_DECISION_EVENT,
    NeocortexShadowRuntime,
    append_shadow_decision_to_wal,
    build_shadow_baseline_runtime,
)


class _FixedToxicModel:
    classes_ = np.array([0, 1])

    def __init__(self, toxic_probability: float) -> None:
        self.toxic_probability = toxic_probability

    def predict_proba(self, _frame):
        return np.array([[1.0 - self.toxic_probability, self.toxic_probability]])


def _write_baseline_artifact(path: Path, *, toxic_probability: float = 0.90) -> None:
    joblib.dump(
        {
            "artifact_version": "test_baseline_logreg_v1",
            "model": _FixedToxicModel(toxic_probability),
            "feature_columns": [
                "f_symbol",
                "f_snapshot_contract",
                "f_trigger_event_type",
            ],
            "threshold": 0.835,
        },
        path,
    )


def _feature_payload(runtime: NeocortexShadowRuntime) -> dict:
    features = {
        feature_name: float(index + 1)
        for index, feature_name in enumerate(runtime.config.ingest.feature_list)
    }
    features["price"] = 100.0
    features["obi"] = 0.25
    features["delta_price"] = 1.0
    return {
        "frame_id": "tap-bootstrap-001",
        "captured_ts_ms": 1_700_000_000_050,
        "event_name": "EVT:FEATURES_CALCULATED",
        "payload": {
            "decision_id": "decision-bootstrap-001",
            "rid": "rid-bootstrap-001",
            "symbol": "BTCUSDT",
            "event_ts_ms": 1_700_000_000_000,
            "mid_price": 100.0,
            "features": features,
            "side": "BUY",
            "proposed_action": "OPEN_LONG",
            "strategy_id": "bootstrap_test",
            "quantity": 0.01,
        },
        "why": "bootstrap_test_event_flow",
    }


def test_config_load_and_stage03_runtime_initialization(tmp_path: Path) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path)
    shadow_events: list[tuple[str, dict, str]] = []

    runtime, runtime_config = build_shadow_baseline_runtime(
        model_path=model_path,
        shadow_emit_fn=lambda event_name, payload, why: shadow_events.append(
            (event_name, payload, why)
        ),
    )

    assert isinstance(runtime, NeocortexShadowRuntime)
    assert isinstance(runtime.aggregator, NeocortexStateAggregator)
    assert isinstance(runtime.baseline_controller, BaselineController)
    assert runtime.enforcement_mode == "shadow"
    assert runtime_config.enforcement_mode == "shadow"
    assert runtime_config.event_tap_endpoint == "tcp://127.0.0.1:7101"


def test_event_flow_mock_logs_shadow_decision_without_hard_block(tmp_path: Path) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path, toxic_probability=0.90)
    shadow_events: list[tuple[str, dict, str]] = []
    runtime, _runtime_config = build_shadow_baseline_runtime(
        model_path=model_path,
        shadow_emit_fn=lambda event_name, payload, why: shadow_events.append(
            (event_name, payload, why)
        ),
    )

    response = asyncio.run(
        runtime.handle_event_frame(_feature_payload(runtime)))

    assert response is not None
    assert response.action == ControlDecisionAction.ALLOW
    assert response.model_action == ControlDecisionAction.BLOCK
    assert response.enforcement_mode == "shadow"
    assert response.shadow_logged is True
    assert runtime.events_seen == 1
    assert runtime.snapshots_emitted == 1
    assert runtime.decisions_logged == 1

    assert len(shadow_events) == 1
    event_name, payload, why = shadow_events[0]
    assert event_name == SHADOW_DECISION_EVENT
    assert why == "neocortex_baseline_shadow_decision"
    assert payload["action"] == "BLOCK"
    assert payload["data_quality_flags"]["model_action"] == "BLOCK"
    assert payload["data_quality_flags"]["returned_action"] == "ALLOW"
    assert payload["data_quality_flags"]["shadow_mode_forced_allow"] is True
    assert payload["causal_state_snapshot"]["neocortex_state"]["state_vector_dim"] == (
        len(runtime.config.ingest.feature_list) + 11
    )


@pytest.mark.parametrize("artifact_kind", ["missing", "corrupt"])
def test_bootstrap_fails_closed_when_baseline_pkl_unavailable(
    tmp_path: Path, artifact_kind: str
) -> None:
    reset_failure_outcomes()
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    if artifact_kind == "corrupt":
        model_path.write_text("not a joblib artifact", encoding="utf-8")

    with pytest.raises(FatalStartupError):
        build_shadow_baseline_runtime(model_path=model_path)

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FATAL_STARTUP,
        reason_code="MODEL_ARTIFACT_MISMATCH",
    ) == 1


def test_shadow_wal_append_failure_degrades_observability(monkeypatch) -> None:
    reset_failure_outcomes()

    def _boom(_payload):
        raise OSError("wal unavailable")

    monkeypatch.setattr(
        "apps.reference.domains.neocortex.main.wal.append", _boom)

    append_shadow_decision_to_wal(
        SHADOW_DECISION_EVENT,
        {"decision_id": "decision-1", "rid": "rid-1"},
        "test_wal_failure",
    )

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code="HANDLER_FAILURE",
    ) == 1
