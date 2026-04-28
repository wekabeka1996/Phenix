"""Latency-bounded synchronous authority bridge for Neocortex."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

import numpy as np

from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
    DEFAULT_BASELINE_MODEL_PATH,
)


class AuthorityBridgeFallbackError(RuntimeError):
    def __init__(self, reason_code: str):
        self.reason_code = str(reason_code).strip().upper() or "UNKNOWN"
        super().__init__(self.reason_code)


class BaselineControllerUnavailableError(RuntimeError):
    """The baseline controller could not be constructed or invoked."""


class NeocortexAuthorityBridge:
    """Fail-closed bridge from the fast FSM to the slow AI authority path."""

    def __init__(
        self,
        authority_fn: Optional[
            Callable[[ControlDecisionRequest],
                     Awaitable[ControlDecisionResponse]]
        ] = None,
        *,
        baseline_controller: BaselineController | None = None,
        model_path: str | Path = DEFAULT_BASELINE_MODEL_PATH,
        enforcement_mode: Literal["shadow", "enforce"] = "shadow",
        shadow_emit_fn: Optional[Callable[[str, dict, str], None]] = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if enforcement_mode not in {"shadow", "enforce"}:
            raise ValueError(
                "neocortex_enforcement_mode must be 'shadow' or 'enforce'")
        self._authority_fn = authority_fn
        self._enforcement_mode = enforcement_mode
        self._shadow_emit = shadow_emit_fn
        self.logger = logger or logging.getLogger(__name__)
        self._baseline_controller = baseline_controller
        self._baseline_startup_error: Exception | None = None
        if self._authority_fn is None and self._baseline_controller is None:
            try:
                self._baseline_controller = BaselineController(
                    model_path=model_path)
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                self._baseline_startup_error = error
                self.logger.warning(
                    "Neocortex baseline controller unavailable at startup path=%s",
                    model_path,
                    exc_info=error,
                )

    async def request_authority(
        self,
        req: ControlDecisionRequest,
        timeout_ms: int,
    ) -> ControlDecisionResponse:
        timeout_seconds = max(float(timeout_ms), 0.0) / 1000.0
        try:
            authority_call = self._request_authority_inner(req)
            response = await asyncio.wait_for(
                authority_call,
                timeout=timeout_seconds,
            )
            if response.decision_id != req.decision_id:
                raise AuthorityBridgeFallbackError("HANDLER_FAILURE")
            return response
        except asyncio.TimeoutError:
            return self._fallback_response(req, reason_code="BRIDGE_TIMEOUT")
        except AuthorityBridgeFallbackError as error:
            return self._fallback_response(req, reason_code=error.reason_code)

    async def _request_authority_inner(
        self,
        req: ControlDecisionRequest,
    ) -> ControlDecisionResponse:
        if self._authority_fn is None:
            return await self._request_baseline(req)
        try:
            return await self._authority_fn(req)
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            raise AuthorityBridgeFallbackError("HANDLER_FAILURE") from error

    def _fallback_response(
        self,
        req: ControlDecisionRequest,
        *,
        reason_code: str,
    ) -> ControlDecisionResponse:
        record_failure_outcome(
            FailureOutcomeTaxonomy.FALLBACK,
            reason_code,
            location="decision_making.authority_bridge.request_authority",
            detail=req.symbol,
        )
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.FALLBACK,
            apply_result=None,
            fallback_reason=reason_code,
            ttl_ms=self._remaining_ttl_ms(req.deadline_ms),
        )

    async def _request_baseline(
        self,
        req: ControlDecisionRequest,
    ) -> ControlDecisionResponse:
        try:
            return await asyncio.to_thread(self._predict_baseline_response, req)
        except (BaselineControllerUnavailableError, BaselineArtifactError, BaselinePredictionError) as error:
            raise AuthorityBridgeFallbackError(
                "BASELINE_UNAVAILABLE") from error

    def _predict_baseline_response(self, req: ControlDecisionRequest) -> ControlDecisionResponse:
        if self._baseline_controller is None:
            raise BaselineControllerUnavailableError(
                "BASELINE_CONTROLLER_UNAVAILABLE"
            ) from self._baseline_startup_error

        snapshot = dict(req.causal_state_snapshot or {})
        raw_state_vector = snapshot.get("state_vector")
        if raw_state_vector is None:
            state_vector = self._baseline_controller.state_vector_from_snapshot(
                snapshot)
            snapshot["state_vector"] = state_vector.tolist()
        else:
            state_vector = np.asarray(raw_state_vector, dtype=object)
            if state_vector.ndim == 0:
                state_vector = state_vector.reshape(1)
            if state_vector.ndim > 1:
                state_vector = state_vector.reshape(-1)
            if len(state_vector) != len(self._baseline_controller.feature_columns):
                if set(snapshot.keys()).issubset({"state_vector"}):
                    raise AuthorityBridgeFallbackError(
                        "MISSING_REQUIRED_STATE")
                state_vector = self._baseline_controller.state_vector_from_snapshot(
                    snapshot
                )

        try:
            model_action = ControlDecisionAction(
                self._baseline_controller.predict_intent(state_vector)
            )
        except BaselinePredictionError as error:
            raise AuthorityBridgeFallbackError(
                "MISSING_REQUIRED_STATE") from error
        except (BaselineArtifactError, ValueError, TypeError) as error:
            raise BaselineControllerUnavailableError(
                "BASELINE_PREDICTION_FAILED") from error
        returned_action = (
            model_action
            if self._enforcement_mode == "enforce"
            else ControlDecisionAction.ALLOW
        )
        apply_result = f"{self._enforcement_mode.upper()}_MODEL_{model_action.value}"

        shadow_logged = self._emit_shadow_model_decision(
            req=req,
            snapshot=snapshot,
            model_action=model_action,
            returned_action=returned_action,
        )
        self.logger.info(
            "Neocortex baseline decision mode=%s decision_id=%s rid=%s symbol=%s model_action=%s returned_action=%s",
            self._enforcement_mode,
            req.decision_id,
            req.rid,
            req.symbol,
            model_action.value,
            returned_action.value,
        )
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=returned_action,
            apply_result=apply_result,
            fallback_reason=None,
            ttl_ms=self._remaining_ttl_ms(req.deadline_ms),
            model_action=model_action,
            enforcement_mode=self._enforcement_mode,
            shadow_logged=shadow_logged,
        )

    def _emit_shadow_model_decision(
        self,
        *,
        req: ControlDecisionRequest,
        snapshot: dict,
        model_action: ControlDecisionAction,
        returned_action: ControlDecisionAction,
    ) -> bool:
        if self._shadow_emit is None:
            return False

        payload = {
            "decision_id": req.decision_id,
            "rid": req.rid,
            "symbol": req.symbol,
            "decision_ts_ms": int(time.time() * 1000),
            "decision_basis_ts": int(req.decision_basis_ts),
            "action": model_action.value,
            "causal_state_snapshot": snapshot,
            "fallback_reason": None,
            "data_quality_flags": {
                "neocortex_enforcement_mode": self._enforcement_mode,
                "model_action": model_action.value,
                "returned_action": returned_action.value,
                "shadow_mode_forced_allow": self._enforcement_mode == "shadow" and model_action == ControlDecisionAction.BLOCK,
            },
        }
        try:
            self._shadow_emit(
                "SHADOW:NEOCORTEX_DECISION_LOGGED",
                payload,
                "neocortex_baseline_shadow_decision",
            )
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                "HANDLER_FAILURE",
                location="decision_making.authority_bridge._emit_shadow_model_decision",
                detail=type(error).__name__,
            )
            self.logger.warning(
                "Neocortex shadow emit degraded decision_id=%s symbol=%s",
                req.decision_id,
                req.symbol,
                exc_info=error,
            )
            return False
        return True

    def _remaining_ttl_ms(self, deadline_ms: int) -> int:
        now_ms = int(time.time() * 1000)
        return max(0, int(deadline_ms) - now_ms)
