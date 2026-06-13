"""Process-backed baseline authority runner.

The runner intentionally uses a short-lived worker process for baseline
inference. A timed-out worker can be terminated, which is the safety property
the async bridge cannot get from a thread-pool fallback.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
DEFAULT_BASELINE_MODEL_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "checkpoints"
    / "baseline_logreg_v1.pkl"
)


def _remaining_ttl_ms(deadline_ms: int) -> int:
    now_ms = int(time.time() * 1000)
    return max(0, int(deadline_ms) - now_ms)


def _baseline_worker(
    conn: Any,
    *,
    request_payload: dict[str, Any],
    model_path: str,
    enforcement_mode: Literal["shadow", "enforce"],
    baseline_controller: Any = None,
) -> None:
    try:
        from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
            BaselineArtifactError,
            BaselineController,
            BaselinePredictionError,
        )

        req = ControlDecisionRequest.model_validate(request_payload)
        controller = baseline_controller or BaselineController(model_path=Path(model_path))
        snapshot = dict(req.causal_state_snapshot or {})
        raw_state_vector = snapshot.get("state_vector")
        if raw_state_vector is None:
            state_vector = controller.state_vector_from_snapshot(snapshot)
            snapshot["state_vector"] = state_vector.tolist()
        else:
            state_vector = np.asarray(raw_state_vector, dtype=object)
            if state_vector.ndim == 0:
                state_vector = state_vector.reshape(1)
            if state_vector.ndim > 1:
                state_vector = state_vector.reshape(-1)
            if len(state_vector) != len(controller.feature_columns):
                if set(snapshot.keys()).issubset({"state_vector"}):
                    conn.send({"ok": False, "reason_code": "MISSING_REQUIRED_STATE"})
                    return
                state_vector = controller.state_vector_from_snapshot(snapshot)

        try:
            model_action = ControlDecisionAction(controller.predict_intent(state_vector))
        except BaselinePredictionError:
            conn.send({"ok": False, "reason_code": "MISSING_REQUIRED_STATE"})
            return

        returned_action = (
            model_action
            if enforcement_mode == "enforce"
            else ControlDecisionAction.ALLOW
        )
        apply_result = f"{enforcement_mode.upper()}_MODEL_{model_action.value}"
        response = ControlDecisionResponse(
            decision_id=req.decision_id,
            action=returned_action,
            apply_result=apply_result,
            fallback_reason=None,
            ttl_ms=_remaining_ttl_ms(req.deadline_ms),
            model_action=model_action,
            enforcement_mode=enforcement_mode,
            shadow_logged=False,
        )
        conn.send(
            {
                "ok": True,
                "response": response.model_dump(mode="json"),
                "snapshot": snapshot,
                "model_action": model_action.value,
                "returned_action": returned_action.value,
            }
        )
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        conn.send(
            {
                "ok": False,
                "reason_code": "BASELINE_UNAVAILABLE",
                "error_type": type(exc).__name__,
            }
        )
    finally:
        conn.close()


@dataclass
class AuthorityRunnerTelemetry:
    timeout: int = 0
    killed_worker: int = 0
    queue_full: int = 0
    fallback_reason: dict[str, int] = field(default_factory=dict)

    def record_fallback(self, reason_code: str) -> None:
        reason = str(reason_code).strip().upper() or "UNKNOWN"
        self.fallback_reason[reason] = self.fallback_reason.get(reason, 0) + 1


@dataclass
class AuthorityProcessResult:
    response: ControlDecisionResponse | None
    reason_code: str | None = None
    shadow_snapshot: dict[str, Any] | None = None
    model_action: ControlDecisionAction | None = None
    returned_action: ControlDecisionAction | None = None
    killed_worker: bool = False


class BaselineAuthorityProcessRunner:
    """Bounded process runner for baseline authority inference."""

    def __init__(
        self,
        *,
        model_path: str | Path = DEFAULT_BASELINE_MODEL_PATH,
        enforcement_mode: Literal["shadow", "enforce"] = "shadow",
        baseline_controller: Any = None,
        max_queue_depth: int = 4,
        max_inflight_per_symbol: int = 1,
        poll_interval_sec: float = 0.002,
        mp_context: str = "spawn",
    ) -> None:
        self.model_path = str(model_path)
        self.enforcement_mode = enforcement_mode
        self.baseline_controller = baseline_controller
        self.max_queue_depth = max(1, int(max_queue_depth))
        self.max_inflight_per_symbol = max(1, int(max_inflight_per_symbol))
        self.poll_interval_sec = max(0.001, float(poll_interval_sec))
        self.telemetry = AuthorityRunnerTelemetry()
        self._ctx = mp.get_context(mp_context)
        self._running = 0
        self._running_by_symbol: dict[str, int] = {}

    async def submit(
        self,
        request: ControlDecisionRequest,
        timeout_ms: int,
    ) -> AuthorityProcessResult:
        symbol = str(request.symbol).upper()
        if self._running >= self.max_queue_depth:
            self.telemetry.queue_full += 1
            self.telemetry.record_fallback("BRIDGE_QUEUE_FULL")
            return AuthorityProcessResult(response=None, reason_code="BRIDGE_QUEUE_FULL")
        if self._running_by_symbol.get(symbol, 0) >= self.max_inflight_per_symbol:
            self.telemetry.queue_full += 1
            self.telemetry.record_fallback("BRIDGE_QUEUE_FULL")
            return AuthorityProcessResult(response=None, reason_code="BRIDGE_QUEUE_FULL")

        parent_conn, child_conn = self._ctx.Pipe(duplex=False)
        payload = request.model_dump(mode="json")
        process = self._ctx.Process(
            target=_baseline_worker,
            kwargs={
                "conn": child_conn,
                "request_payload": payload,
                "model_path": self.model_path,
                "enforcement_mode": self.enforcement_mode,
                "baseline_controller": self.baseline_controller,
            },
            daemon=True,
        )
        self._running += 1
        self._running_by_symbol[symbol] = self._running_by_symbol.get(symbol, 0) + 1
        deadline = time.monotonic() + max(float(timeout_ms), 0.0) / 1000.0
        try:
            try:
                process.start()
            except Exception:
                child_conn.close()
                self.telemetry.record_fallback("BASELINE_UNAVAILABLE")
                return AuthorityProcessResult(
                    response=None,
                    reason_code="BASELINE_UNAVAILABLE",
                )
            child_conn.close()

            while True:
                if parent_conn.poll():
                    raw = parent_conn.recv()
                    process.join(timeout=0)
                    if raw.get("ok"):
                        response = ControlDecisionResponse.model_validate(raw["response"])
                        model_action = ControlDecisionAction(raw["model_action"])
                        returned_action = ControlDecisionAction(raw["returned_action"])
                        return AuthorityProcessResult(
                            response=response,
                            shadow_snapshot=dict(raw.get("snapshot") or {}),
                            model_action=model_action,
                            returned_action=returned_action,
                        )
                    reason = str(raw.get("reason_code") or "BASELINE_UNAVAILABLE").upper()
                    self.telemetry.record_fallback(reason)
                    return AuthorityProcessResult(response=None, reason_code=reason)
                if time.monotonic() >= deadline:
                    self.telemetry.timeout += 1
                    killed = self._terminate_worker(process)
                    if killed:
                        self.telemetry.killed_worker += 1
                    self.telemetry.record_fallback("BRIDGE_TIMEOUT")
                    return AuthorityProcessResult(
                        response=None,
                        reason_code="BRIDGE_TIMEOUT",
                        killed_worker=killed,
                    )
                await asyncio.sleep(self.poll_interval_sec)
        finally:
            parent_conn.close()
            if process.is_alive():
                self._terminate_worker(process)
            if process.pid is not None:
                process.join(timeout=0.05)
            self._running -= 1
            remaining = self._running_by_symbol.get(symbol, 0) - 1
            if remaining > 0:
                self._running_by_symbol[symbol] = remaining
            else:
                self._running_by_symbol.pop(symbol, None)

    def shutdown(self, kill: bool = False) -> None:
        """API placeholder for compatibility with pooled runners."""

    @staticmethod
    def _terminate_worker(process: mp.Process) -> bool:
        if not process.is_alive():
            return False
        process.terminate()
        process.join(timeout=0.05)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=0.05)
        return True


__all__ = [
    "AuthorityProcessResult",
    "AuthorityRunnerTelemetry",
    "BaselineAuthorityProcessRunner",
]
