"""
Hot-path coverage gap tests for authority_bridge.py branch closure.

Targets uncovered lines: 32-33, 57, 90/94-95, 106, 135, 153, 155, 165-169.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import joblib
import numpy as np
import pytest

from apps.reference.domains.decision_making.authority_bridge import (
    AuthorityBridgeFallbackError,
    BaselineControllerUnavailableError,
    NeocortexAuthorityBridge,
)
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FixedModel:
    classes_ = np.array([0, 1])

    def __init__(self, toxic_prob: float = 0.9) -> None:
        self.toxic_prob = toxic_prob

    def predict_proba(self, _frame):
        return np.array([[1.0 - self.toxic_prob, self.toxic_prob]])


def _write_artifact(path: Path, *, toxic_prob: float = 0.9, threshold: float = 0.5) -> None:
    joblib.dump(
        {
            "artifact_version": "test_v1",
            "model": _FixedModel(toxic_prob),
            "feature_columns": ["f_symbol", "f_snapshot_contract", "f_trigger_event_type"],
            "threshold": threshold,
        },
        path,
    )


def _req(
    *,
    decision_id: str = "req-1",
    symbol: str = "BTCUSDT",
    deadline_ms: int = 1_700_000_000_050,
    causal_state_snapshot: dict | None = None,
) -> ControlDecisionRequest:
    return ControlDecisionRequest(
        decision_id=decision_id,
        rid="rid-1",
        symbol=symbol,
        proposed_action="OPEN_LONG",
        deadline_ms=deadline_ms,
        decision_basis_ts=1_700_000_000_000,
        causal_state_snapshot=causal_state_snapshot or {},
    )


@pytest.fixture(autouse=True)
def _reset_failure_outcomes_fixture():
    reset_failure_outcomes()
    yield
    reset_failure_outcomes()


# ---------------------------------------------------------------------------
# AuthorityBridgeFallbackError (lines 32-33)
# ---------------------------------------------------------------------------

class TestAuthorityBridgeFallbackError:
    def test_reason_code_is_uppercased(self):
        err = AuthorityBridgeFallbackError("handler_failure")
        assert err.reason_code == "HANDLER_FAILURE"
        assert str(err) == "HANDLER_FAILURE"

    def test_empty_reason_code_becomes_unknown(self):
        err = AuthorityBridgeFallbackError("  ")
        assert err.reason_code == "UNKNOWN"


# ---------------------------------------------------------------------------
# BaselineControllerUnavailableError
# ---------------------------------------------------------------------------

class TestBaselineControllerUnavailableError:
    def test_is_runtime_error(self):
        err = BaselineControllerUnavailableError("msg")
        assert isinstance(err, RuntimeError)


# ---------------------------------------------------------------------------
# NeocortexAuthorityBridge enforcement_mode validation (line 57)
# ---------------------------------------------------------------------------

class TestEnforcementModeValidation:
    def test_invalid_enforcement_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="enforcement_mode"):
            # type: ignore[arg-type]
            NeocortexAuthorityBridge(enforcement_mode="live")

    def test_shadow_mode_is_accepted(self):
        bridge = NeocortexAuthorityBridge(enforcement_mode="shadow")
        assert bridge._enforcement_mode == "shadow"

    def test_enforce_mode_is_accepted(self, tmp_path):
        path = tmp_path / "m.pkl"
        _write_artifact(path)
        bridge = NeocortexAuthorityBridge(
            model_path=path,
            enforcement_mode="enforce",
        )
        assert bridge._enforcement_mode == "enforce"


# ---------------------------------------------------------------------------
# decision_id mismatch → fallback (lines 90, 94-95)
# ---------------------------------------------------------------------------

class TestDecisionIdMismatch:
    def test_mismatched_decision_id_falls_back(self):
        async def _wrong_id(req: ControlDecisionRequest) -> ControlDecisionResponse:
            return ControlDecisionResponse(
                decision_id="WRONG_ID",
                action=ControlDecisionAction.ALLOW,
                apply_result=None,
                fallback_reason=None,
                ttl_ms=10,
            )

        bridge = NeocortexAuthorityBridge(authority_fn=_wrong_id)
        response = asyncio.run(
            bridge.request_authority(
                _req(decision_id="req-correct"), timeout_ms=100)
        )
        assert response.action == ControlDecisionAction.FALLBACK
        assert response.fallback_reason == "HANDLER_FAILURE"


# ---------------------------------------------------------------------------
# authority_fn raises → HANDLER_FAILURE (line 106)
# ---------------------------------------------------------------------------

class TestAuthorityFnException:
    def test_authority_fn_os_error_falls_back(self):
        async def _os_err(_req):
            raise OSError("network down")

        bridge = NeocortexAuthorityBridge(authority_fn=_os_err)
        response = asyncio.run(
            bridge.request_authority(_req(), timeout_ms=100)
        )
        assert response.action == ControlDecisionAction.FALLBACK
        assert response.fallback_reason == "HANDLER_FAILURE"
        assert get_failure_outcome_total(
            taxonomy=FailureOutcomeTaxonomy.FALLBACK,
            reason_code="HANDLER_FAILURE",
        ) == 1

    def test_authority_fn_value_error_falls_back(self):
        async def _val_err(_req):
            raise ValueError("bad value")

        bridge = NeocortexAuthorityBridge(authority_fn=_val_err)
        response = asyncio.run(
            bridge.request_authority(_req(), timeout_ms=100)
        )
        assert response.action == ControlDecisionAction.FALLBACK


# ---------------------------------------------------------------------------
# Baseline controller unavailable at startup path (line 135)
# ---------------------------------------------------------------------------

class TestBaselineUnavailableAtStartup:
    def test_startup_error_stored_and_fallback_on_request(self, tmp_path):
        bridge = NeocortexAuthorityBridge(model_path=tmp_path / "missing.pkl")

        response = asyncio.run(
            bridge.request_authority(_req(), timeout_ms=500)
        )
        assert response.action == ControlDecisionAction.FALLBACK
        assert response.fallback_reason == "BRIDGE_TIMEOUT"
        assert get_failure_outcome_total(
            taxonomy=FailureOutcomeTaxonomy.FALLBACK,
            reason_code="BRIDGE_TIMEOUT",
        ) == 1


# ---------------------------------------------------------------------------
# BaselinePredictionError → MISSING_REQUIRED_STATE (line 153)
# ---------------------------------------------------------------------------

class TestBaselinePredictionError:
    def test_vector_length_mismatch_maps_to_missing_required_state(self, tmp_path):
        path = tmp_path / "m.pkl"
        _write_artifact(path)
        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path)
        )
        # length 1, controller expects 3
        req = _req(causal_state_snapshot={"state_vector": [1.0]})

        with pytest.raises(AuthorityBridgeFallbackError, match="MISSING_REQUIRED_STATE"):
            bridge._predict_baseline_response(req)


# ---------------------------------------------------------------------------
# BaselineArtifactError → BaselineControllerUnavailableError (line 155)
# ---------------------------------------------------------------------------

class TestBaselineArtifactErrorDuringPredict:
    def test_artifact_error_during_prediction_falls_back(self, tmp_path):
        path = tmp_path / "m.pkl"
        _write_artifact(path)
        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path)
        )
        # Patch controller to raise BaselineArtifactError mid-predict
        bridge._baseline_controller.predict_intent = MagicMock(
            side_effect=BaselineArtifactError("corrupt at predict")
        )
        with pytest.raises(BaselineControllerUnavailableError):
            bridge._predict_baseline_response(_req())


# ---------------------------------------------------------------------------
# enforce mode returns model_action directly (lines 163-169)
# ---------------------------------------------------------------------------

class TestEnforceMode:
    def test_enforce_mode_block_model_returns_block_action(self, tmp_path):
        path = tmp_path / "m.pkl"
        # model will predict BLOCK
        _write_artifact(path, toxic_prob=0.95, threshold=0.5)
        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path), enforcement_mode="enforce")

        response = bridge._predict_baseline_response(_req())
        assert response.action == ControlDecisionAction.BLOCK
        assert response.model_action == ControlDecisionAction.BLOCK
        assert response.enforcement_mode == "enforce"
        assert "ENFORCE_MODEL_BLOCK" in (response.apply_result or "")

    def test_enforce_mode_allow_model_returns_allow_action(self, tmp_path):
        path = tmp_path / "m.pkl"
        # model will predict ALLOW
        _write_artifact(path, toxic_prob=0.1, threshold=0.5)
        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path), enforcement_mode="enforce")

        response = bridge._predict_baseline_response(_req())
        assert response.action == ControlDecisionAction.ALLOW
        assert response.model_action == ControlDecisionAction.ALLOW
        assert "ENFORCE_MODEL_ALLOW" in (response.apply_result or "")

    def test_shadow_mode_block_model_returns_allow_action(self, tmp_path):
        """Shadow mode: model says BLOCK → runtime returns ALLOW (shadow-only)."""
        path = tmp_path / "m.pkl"
        _write_artifact(path, toxic_prob=0.95, threshold=0.5)
        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path), enforcement_mode="shadow")

        response = bridge._predict_baseline_response(_req())
        assert response.action == ControlDecisionAction.ALLOW
        assert response.model_action == ControlDecisionAction.BLOCK
        assert response.shadow_logged is False  # no emit fn attached
        assert "SHADOW_MODEL_BLOCK" in (response.apply_result or "")


# ---------------------------------------------------------------------------
# shadow emit degraded path (lines 229-242)
# ---------------------------------------------------------------------------

class TestShadowEmitDegraded:
    def test_shadow_emit_exception_is_caught_and_recorded(self, tmp_path):
        path = tmp_path / "m.pkl"
        _write_artifact(path, toxic_prob=0.95, threshold=0.5)

        def _boom(event_name, payload, why):
            raise OSError("emit unavailable")

        bridge = NeocortexAuthorityBridge(
            baseline_controller=BaselineController(path),
            enforcement_mode="shadow",
            shadow_emit_fn=_boom,
        )
        response = bridge._predict_baseline_response(_req())
        # Should still return ALLOW (shadow) but shadow_logged=False
        assert response.action == ControlDecisionAction.ALLOW
        assert response.shadow_logged is False
        assert get_failure_outcome_total(
            taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            reason_code="HANDLER_FAILURE",
        ) == 1


# ---------------------------------------------------------------------------
# _remaining_ttl_ms edge case (already in bridge but ensures branch hit)
# ---------------------------------------------------------------------------

class TestRemainingTtlMs:
    def test_ttl_never_goes_negative(self, tmp_path):
        path = tmp_path / "m.pkl"
        _write_artifact(path)
        bridge = NeocortexAuthorityBridge(model_path=path)
        # deadline in the past
        ttl = bridge._remaining_ttl_ms(1)
        assert ttl == 0
