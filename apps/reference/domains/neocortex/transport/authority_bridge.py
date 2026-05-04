"""Phase 5 synchronous authority bridge entrypoint."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Mapping

from apps.reference.domains.neocortex.config_models import NeocortexConfig
from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionApplyResult,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
    DEFAULT_BASELINE_MODEL_PATH,
)
from apps.reference.telemetry.metrics import inc_neocortex_authority_fallback


def _fallback_policy(reason_code: str) -> str:
    normalized = str(reason_code).strip().upper()
    if normalized in {
        FailureReasonCode.BASELINE_UNAVAILABLE.value,
        FailureReasonCode.MISSING_REQUIRED_STATE.value,
    }:
        return "baseline_controller"
    if normalized == FailureReasonCode.HANDLER_FAILURE.value:
        return "authority_handler"
    if normalized in {
        FailureReasonCode.BRIDGE_UNAVAILABLE.value,
        FailureReasonCode.CONFIG_MISSING.value,
        FailureReasonCode.CONFIG_INVALID.value,
    }:
        return "authority_guard"
    return "unknown"


class NeocortexAuthorityBridge:
    """Synchronous, bounded authority bridge for Phase 5."""

    def __init__(
        self,
        *,
        config: NeocortexConfig | None,
        authority_fn: Callable[[ControlDecisionRequest],
                               ControlDecisionResponse | Mapping[str, object]] | None = None,
        baseline_controller: BaselineController | None = None,
        model_path: str | Path = DEFAULT_BASELINE_MODEL_PATH,
        shadow_emit_fn: Callable[[
            str, dict[str, object], str], None] | None = None,
        config_error: Exception | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._config_error = config_error
        self._authority_fn = authority_fn
        self._shadow_emit = shadow_emit_fn
        self._logger = logger or logging.getLogger(__name__)
        self._baseline_controller = baseline_controller
        self._baseline_startup_error: Exception | None = None
        self._inflight_symbols: set[str] = set()
        self._inflight_lock = threading.Lock()
        self._model_path = Path(model_path)

        if self._authority_fn is None and self._baseline_controller is None:
            try:
                self._baseline_controller = BaselineController(
                    model_path=model_path)
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                self._baseline_startup_error = error
                self._logger.warning(
                    "Neocortex baseline controller unavailable at startup path=%s",
                    model_path,
                    exc_info=error,
                )

    @property
    def short_circuit_reason(self) -> str | None:
        if self._config_error is not None:
            return "CONFIG_INVALID"
        if self._config is None:
            return "CONFIG_MISSING"
        if not bool(self._config.trust_enabled):
            return "TRUST_DISABLED"
        return None

    @property
    def authority_mode(self) -> AuthorityMode:
        if self._config is None:
            return AuthorityMode.SHADOW
        return AuthorityMode(str(self._config.authority.mode))

    @property
    def journal_only_capture_enabled(self) -> bool:
        if self._config is None:
            return False
        capture_cfg = getattr(self._config, "evidence_capture", None)
        if capture_cfg is None:
            return False
        return (
            str(getattr(capture_cfg, "mode", "disabled")).strip().lower() == "journal_only"
            and bool(getattr(capture_cfg, "collect_observation", False))
            and bool(getattr(capture_cfg, "collect_authority_request", False))
        )

    @property
    def journal_only_response_journal_enabled(self) -> bool:
        if self._config is None:
            return False
        capture_cfg = getattr(self._config, "evidence_capture", None)
        if capture_cfg is None:
            return False
        return bool(getattr(capture_cfg, "collect_authority_response", False))

    @property
    def journal_only_emit_shadow_decision_logged(self) -> bool:
        if self._config is None:
            return False
        capture_cfg = getattr(self._config, "evidence_capture", None)
        if capture_cfg is None:
            return False
        return bool(getattr(capture_cfg, "emit_shadow_decision_logged", False))

    @property
    def deadline_ms(self) -> int:
        if self._config is None:
            return 1
        return int(self._config.authority.deadline_ms)

    @property
    def data_dir(self) -> Path | None:
        if self._config is None:
            return None
        return Path(self._config.system.data_dir)

    def decide(self, request: ControlDecisionRequest) -> ControlDecisionResponse:
        returned_at_ms = self._now_ms()
        if self._config_error is not None or self._config is None:
            return self._fallback_response(
                request,
                returned_at_ms=returned_at_ms,
                reason_code=self.short_circuit_reason or "CONFIG_INVALID",
                reason_text="Neocortex authority config unavailable",
            )
        if not self._try_acquire_symbol(request.symbol):
            return self._fallback_response(
                request,
                returned_at_ms=returned_at_ms,
                reason_code="BRIDGE_UNAVAILABLE",
                reason_text="max_inflight_per_symbol reached",
            )

        try:
            raw_response: ControlDecisionResponse | Mapping[str, object]
            if self._authority_fn is not None:
                raw_response = self._authority_fn(request)
            else:
                raw_response = self._predict_baseline_response(request)
            response = self._coerce_response(raw_response)
            if response.decision_id != request.decision_id:
                raise ValueError("decision_id mismatch")
            if response.idempotent_key != request.idempotent_key:
                raise ValueError("idempotent_key mismatch")
            self._emit_shadow_response(
                request,
                response,
                request_ts_ms=returned_at_ms,
            )
            return response
        except BaselineArtifactError:
            return self._fallback_response(
                request,
                returned_at_ms=self._now_ms(),
                reason_code="BASELINE_UNAVAILABLE",
                reason_text="Baseline controller unavailable",
            )
        except BaselinePredictionError:
            return self._fallback_response(
                request,
                returned_at_ms=self._now_ms(),
                reason_code="MISSING_REQUIRED_STATE",
                reason_text="Baseline prediction missing required state",
            )
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            return self._fallback_response(
                request,
                returned_at_ms=self._now_ms(),
                reason_code="HANDLER_FAILURE",
                reason_text=f"authority bridge error: {type(error).__name__}",
            )
        finally:
            self._release_symbol(request.symbol)

    def journal_only_capture(
        self,
        request: ControlDecisionRequest,
    ) -> ControlDecisionResponse:
        returned_at_ms = self._now_ms()
        response = ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.ALLOW,
            reason_code="JOURNAL_ONLY_CAPTURE",
            reason_text="Journal-only capture recorded without authority application",
            returned_at_ms=returned_at_ms,
            model_ref="journal_only_capture",
            policy_ref="journal_only_capture",
            idempotent_key=request.idempotent_key,
            apply_result=ControlDecisionApplyResult.SHADOW_RECORDED,
        )
        if self.journal_only_emit_shadow_decision_logged:
            self._emit_shadow_response(
                request,
                response,
                request_ts_ms=returned_at_ms,
                capture_mode="journal_only",
                authority_applied=False,
                no_effect=True,
                shadow_logged=True,
            )
        return response

    def _predict_baseline_response(
        self,
        request: ControlDecisionRequest,
    ) -> ControlDecisionResponse:
        if self._baseline_controller is None:
            raise BaselineArtifactError(
                "baseline controller unavailable") from self._baseline_startup_error

        state_vector = self._baseline_controller.state_vector_from_snapshot(
            request.observation.model_dump()
        )
        predicted = str(self._baseline_controller.predict_intent(
            state_vector)).strip().upper()
        action = (
            ControlDecisionAction.DENY
            if predicted == "BLOCK"
            else ControlDecisionAction.ALLOW
        )
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=action,
            reason_code="MODEL_DENY" if action == ControlDecisionAction.DENY else "MODEL_ALLOW",
            reason_text=(
                "Baseline controller denied candidate risk intent"
                if action == ControlDecisionAction.DENY
                else "Baseline controller allowed candidate risk intent"
            ),
            returned_at_ms=self._now_ms(),
            model_ref=str(self._model_path),
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
        )

    def _coerce_response(
        self,
        response: ControlDecisionResponse | Mapping[str, object],
    ) -> ControlDecisionResponse:
        if isinstance(response, ControlDecisionResponse):
            return response
        return ControlDecisionResponse.model_validate(response)

    def _fallback_response(
        self,
        request: ControlDecisionRequest,
        *,
        returned_at_ms: int,
        reason_code: str,
        reason_text: str,
    ) -> ControlDecisionResponse:
        mapped_reason = {
            "BASELINE_UNAVAILABLE": FailureReasonCode.BASELINE_UNAVAILABLE,
            "HANDLER_FAILURE": FailureReasonCode.HANDLER_FAILURE,
            "BRIDGE_UNAVAILABLE": FailureReasonCode.BRIDGE_UNAVAILABLE,
            "CONFIG_MISSING": FailureReasonCode.CONFIG_MISSING,
            "CONFIG_INVALID": FailureReasonCode.CONFIG_INVALID,
            "MISSING_REQUIRED_STATE": FailureReasonCode.MISSING_REQUIRED_STATE,
        }.get(reason_code)
        if mapped_reason is not None:
            record_failure_outcome(
                FailureOutcomeTaxonomy.FALLBACK,
                mapped_reason,
                source="neocortex.transport.authority_bridge.decide",
                location="transport.authority_bridge.decide",
                detail=request.symbol,
                message=reason_text,
            )
        inc_neocortex_authority_fallback(
            policy=_fallback_policy(reason_code),
            reason_code=reason_code,
        )
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.FALLBACK,
            reason_code=reason_code,
            reason_text=reason_text,
            returned_at_ms=returned_at_ms,
            model_ref="baseline_yaml",
            policy_ref="baseline_yaml",
            idempotent_key=request.idempotent_key,
        )

    def _emit_shadow_response(
        self,
        request: ControlDecisionRequest,
        response: ControlDecisionResponse,
        *,
        request_ts_ms: int,
        capture_mode: str | None = None,
        authority_applied: bool | None = None,
        no_effect: bool | None = None,
        shadow_logged: bool | None = None,
    ) -> None:
        if self._shadow_emit is None:
            return
        payload = {
            "decision_id": request.decision_id,
            "rid": request.rid,
            "symbol": request.symbol,
            "decision_ts_ms": int(response.returned_at_ms),
            "request_ts_ms": int(request_ts_ms),
            "response_ts_ms": int(response.returned_at_ms),
            "decision_basis_ts": int(request.decision_basis_ts_ms),
            "authority_mode": request.authority_mode.value,
            "apply_result": response.apply_result,
            "action": response.action.value,
            "causal_state_snapshot": request.observation.model_dump(),
            "fallback_reason": (
                response.reason_code
                if response.action == ControlDecisionAction.FALLBACK
                else None
            ),
            "data_quality_flags": {
                "authority_mode": request.authority_mode.value,
                "reason_code": response.reason_code,
            },
        }
        if capture_mode is not None:
            payload["capture_mode"] = capture_mode
            payload["data_quality_flags"]["capture_mode"] = capture_mode
        if authority_applied is not None:
            payload["authority_applied"] = bool(authority_applied)
            payload["data_quality_flags"]["authority_applied"] = bool(
                authority_applied)
        if no_effect is not None:
            payload["no_effect"] = bool(no_effect)
            payload["data_quality_flags"]["no_effect"] = bool(no_effect)
        if shadow_logged is not None:
            payload["shadow_logged"] = bool(shadow_logged)
            payload["data_quality_flags"]["shadow_logged"] = bool(
                shadow_logged)
        try:
            self._shadow_emit(
                "SHADOW:NEOCORTEX_DECISION_LOGGED",
                payload,
                "neocortex_authority_bridge",
            )
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.HANDLER_FAILURE,
                source="neocortex.transport.authority_bridge._emit_shadow_response",
                location="transport.authority_bridge.shadow_emit",
                detail=type(error).__name__,
                message="Shadow authority emit degraded",
            )
            self._logger.warning(
                "Neocortex authority shadow emit degraded decision_id=%s",
                request.decision_id,
                exc_info=error,
            )

    def _try_acquire_symbol(self, symbol: str) -> bool:
        with self._inflight_lock:
            if symbol in self._inflight_symbols:
                return False
            self._inflight_symbols.add(symbol)
            return True

    def _release_symbol(self, symbol: str) -> None:
        with self._inflight_lock:
            self._inflight_symbols.discard(symbol)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
