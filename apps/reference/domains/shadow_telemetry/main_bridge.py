from __future__ import annotations

import threading
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.domains.shadow_telemetry.contracts import CmdLlmIntentSubmitV1
from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpQueueClient,
    JsonlTcpServer,
    ShadowTapDeliveryFailure,
)
from apps.reference.telemetry.metrics import (
    inc_shadow_tap_delivery_failure,
    inc_shadow_tap_delivery_log_suppressed,
)


@dataclass(frozen=True)
class ShadowTapPublishOutcome:
    accepted: bool
    fatal: bool
    degraded_observability: bool
    failure_class: str | None = None
    endpoint: str = ""
    reason: str = ""


class ShadowTapDeliveryCriticalError(RuntimeError):
    """Raised when shadow tap delivery must fail closed."""


def _append_wal_event(verb: str, rid: str, payload: Dict[str, Any], why: str) -> None:
    """Best-effort WAL append for telemetry ingress lifecycle."""

    try:
        msg = Message(
            op="EVT",
            verb=verb,
            src="shadow_telemetry_ingress",
            dst="any",
            rid=str(rid),
            pld=payload,
            why=truncate_why(why),
        )
        wal.append(msg.model_dump())
    except Exception:
        # Keep bridge non-crashing in runtime path.
        pass


class ShadowEventTapPublisher:
    """Main-process publisher for allowlisted events to Shadow Telemetry ingress."""

    def __init__(self, cfg: Any, logger: Optional[logging.Logger] = None) -> None:
        self.cfg = cfg
        self.logger = logger or logging.getLogger(__name__)

        ingest_cfg = cfg.ingest
        self._enabled = bool(getattr(cfg, "enabled", False))
        self.required_for_mode = bool(getattr(cfg, "required_for_mode", False))
        self._allowlist = set(str(x) for x in getattr(
            ingest_cfg, "allowlist_events", []) or [])
        self._endpoint = str(ingest_cfg.ipc_endpoint)
        self._delivery_failure_lock = threading.Lock()
        self._delivery_failure_log_state: dict[str, dict[str, float | int]] = {}
        self._delivery_failure_log_every_n = 25
        self._delivery_failure_log_interval_sec = 60.0
        self._client: JsonlTcpQueueClient | None = None
        if self._enabled:
            self._client = JsonlTcpQueueClient(
                endpoint=self._endpoint,
                queue_maxsize=int(ingest_cfg.queue_maxsize),
                overflow_policy=str(ingest_cfg.overflow_policy),
                stop_timeout_ms=int(cfg.lifecycle.stop_timeout_ms),
                logger=self.logger.getChild("event_tap"),
                name="shadow_event_tap_client",
                failure_reporter=self._handle_client_delivery_failure,
            )

    def _handle_client_delivery_failure(
        self,
        failure: ShadowTapDeliveryFailure,
    ) -> None:
        self._record_delivery_failure(
            failure,
            source="worker",
            required_for_mode=self.required_for_mode,
        )

    def _record_delivery_failure(
        self,
        failure: ShadowTapDeliveryFailure,
        *,
        source: str,
        required_for_mode: bool,
    ) -> ShadowTapPublishOutcome:
        failure_class = str(failure.failure_class or "unknown").strip() or "unknown"
        inc_shadow_tap_delivery_failure(
            component="shadow_event_tap_client",
            failure_class=failure_class,
            required_for_mode=required_for_mode,
        )

        reason_code = (
            FailureReasonCode.BRIDGE_TIMEOUT
            if failure_class == "timeout"
            else FailureReasonCode.BRIDGE_UNAVAILABLE
        )
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            reason_code,
            location="domains/shadow_telemetry/main_bridge.py:ShadowEventTapPublisher._record_delivery_failure",
            message="Shadow event tap delivery failed",
            detail={
                "source": source,
                "phase": failure.phase,
                "endpoint": failure.endpoint,
                "error_type": failure.error_type,
                "error_message": failure.error_message,
                "failure_class": failure_class,
                "required_for_mode": required_for_mode,
            },
        )

        now = time.monotonic()
        with self._delivery_failure_lock:
            state = self._delivery_failure_log_state.setdefault(
                failure_class,
                {
                    "count": 0,
                    "suppressed": 0,
                    "last_emitted_monotonic": 0.0,
                },
            )
            state["count"] = int(state["count"]) + 1
            count = int(state["count"])
            suppressed = int(state["suppressed"])
            last_emitted = float(state["last_emitted_monotonic"])
            should_emit = (
                count == 1
                or count % self._delivery_failure_log_every_n == 0
                or (now - last_emitted >= self._delivery_failure_log_interval_sec and suppressed > 0)
            )
            if should_emit:
                state["suppressed"] = 0
                state["last_emitted_monotonic"] = now
            else:
                state["suppressed"] = suppressed + 1
                inc_shadow_tap_delivery_log_suppressed(
                    component="shadow_event_tap_client",
                    failure_class=failure_class,
                )
                return ShadowTapPublishOutcome(
                    accepted=False,
                    fatal=bool(required_for_mode),
                    degraded_observability=True,
                    failure_class=failure_class,
                    endpoint=failure.endpoint,
                    reason=source,
                )

        summary_suppressed = suppressed
        message = (
            "Shadow event tap delivery degraded "
            "(endpoint=%s required_for_mode=%s failure_class=%s source=%s phase=%s error=%s: %s)"
        )
        args = (
            failure.endpoint,
            required_for_mode,
            failure_class,
            source,
            failure.phase,
            failure.error_type,
            truncate_why(str(failure.error_message), 160),
        )

        if required_for_mode:
            self.logger.critical(message, *args)
        elif summary_suppressed > 0:
            self.logger.warning(
                "%s suppressed %d additional shadow tap delivery failures "
                "(endpoint=%s failure_class=%s source=%s phase=%s)",
                self.logger.name,
                summary_suppressed,
                failure.endpoint,
                failure_class,
                source,
                failure.phase,
            )
        else:
            self.logger.warning(message, *args)

        return ShadowTapPublishOutcome(
            accepted=False,
            fatal=bool(required_for_mode),
            degraded_observability=True,
            failure_class=failure_class,
            endpoint=failure.endpoint,
            reason=source,
        )

    def start(self) -> None:
        if not self._enabled or self._client is None:
            return
        startup_failure = self._client.probe_endpoint()
        if startup_failure is not None:
            self._client.mark_delivery_failure(startup_failure)
            self._record_delivery_failure(
                startup_failure,
                source="startup",
                required_for_mode=self.required_for_mode,
            )
            if self.required_for_mode:
                raise ShadowTapDeliveryCriticalError(
                    "Shadow event tap required_for_mode=true but endpoint is unavailable "
                    f"at startup: {startup_failure.endpoint} ({startup_failure.failure_class})"
                )
        self._client.start()
        self.logger.info(
            "Shadow event tap publisher started "
            "(endpoint=%s required_for_mode=%s delivery_mode=%s queue_maxsize=%s overflow_policy=%s)",
            self._endpoint,
            self.required_for_mode,
            "fail_closed" if self.required_for_mode else "degraded_observability",
            self._client.queue_maxsize,
            self._client.overflow_policy,
        )

    def stop(self) -> None:
        if self._client is not None:
            self._client.stop()

    def preflight(self, event_name: str) -> ShadowTapPublishOutcome:
        if not self._enabled or self._client is None:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=False,
                degraded_observability=False,
                reason="disabled",
            )
        if self._allowlist and event_name not in self._allowlist:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=False,
                degraded_observability=False,
                reason="allowlist_skip",
            )

        if not self.required_for_mode:
            return ShadowTapPublishOutcome(
                accepted=True,
                fatal=False,
                degraded_observability=False,
                endpoint=self._endpoint,
                reason="non_required_mode",
            )

        prior_failure = self._client.last_delivery_failure()
        if prior_failure is not None:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=True,
                degraded_observability=True,
                failure_class=prior_failure.failure_class,
                endpoint=prior_failure.endpoint,
                reason="prior_delivery_failure",
            )

        if self._client.queue_depth() >= self._client.queue_maxsize:
            failure = ShadowTapDeliveryFailure(
                failure_class="queue_overflow",
                phase="preflight",
                error_type="queue.Full",
                error_message="shadow tap queue is full",
                endpoint=self._endpoint,
            )
            return self._record_delivery_failure(
                failure,
                source="preflight",
                required_for_mode=True,
            )

        return ShadowTapPublishOutcome(
            accepted=True,
            fatal=False,
            degraded_observability=False,
            endpoint=self._endpoint,
            reason="preflight_ok",
        )

    def publish(self, event_name: str, payload: Dict[str, Any], why: str) -> ShadowTapPublishOutcome:
        if not self._enabled or self._client is None:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=False,
                degraded_observability=False,
                reason="disabled",
            )
        if self._allowlist and event_name not in self._allowlist:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=False,
                degraded_observability=False,
                reason="allowlist_skip",
            )

        prior_failure = self._client.last_delivery_failure()
        if self.required_for_mode and prior_failure is not None:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=True,
                degraded_observability=True,
                failure_class=prior_failure.failure_class,
                endpoint=prior_failure.endpoint,
                reason="prior_delivery_failure",
            )

        frame = {
            "frame_id": f"tap-{int(time.time() * 1000)}",
            "captured_ts_ms": int(time.time() * 1000),
            "event_name": event_name,
            "payload": payload,
            "why": truncate_why(str(why), 80),
        }
        ok = self._client.enqueue(frame)
        if ok:
            return ShadowTapPublishOutcome(
                accepted=True,
                fatal=False,
                degraded_observability=False,
                endpoint=self._endpoint,
                reason="enqueued",
            )

        failure = ShadowTapDeliveryFailure(
            failure_class="queue_overflow",
            phase="enqueue",
            error_type="queue.Full",
            error_message=f"shadow tap queue overflow while publishing {event_name}",
            endpoint=self._endpoint,
        )
        return self._record_delivery_failure(
            failure,
            source="enqueue",
            required_for_mode=self.required_for_mode,
        )


class LLMIntentIngressBridge:
    """Main-process command ingress that receives LLM intents from shadow API via IPC."""

    def __init__(self, fsm: Any, config: Any, logger: Optional[logging.Logger] = None) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        shadow_cfg = getattr(
            getattr(config, "domains", None), "shadow_telemetry", None)
        self._enabled = bool(
            shadow_cfg
            and shadow_cfg.enabled
            and shadow_cfg.api.enabled
            and shadow_cfg.api.write.enabled
        )
        self._server: JsonlTcpServer | None = None
        if shadow_cfg is None:
            self._endpoint = "tcp://127.0.0.1:7102"
        else:
            self._endpoint = str(
                shadow_cfg.egress_to_main.ipc_commands_endpoint)
            self._server = JsonlTcpServer(
                endpoint=self._endpoint,
                handler=self._on_command,
                stop_timeout_ms=int(shadow_cfg.lifecycle.stop_timeout_ms),
                logger=self.logger.getChild("ingress"),
                name="llm_intent_ingress_server",
            )

    def start(self) -> None:
        if not self._enabled or self._server is None:
            return
        self._server.start()
        self.logger.info("LLM ingress bridge started on %s", self._endpoint)

    def stop(self) -> None:
        if self._server is not None:
            self._server.stop()

    def _on_command(self, payload: Dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        rid = str(payload.get("intent_id") or payload.get("rid")
                  or request_id or f"llm-{int(time.time() * 1000)}")

        try:
            cmd = CmdLlmIntentSubmitV1.model_validate(payload)
        except Exception as e:
            reject_payload = {
                "intent_id": payload.get("intent_id"),
                "request_id": request_id,
                "ts_ms": int(time.time() * 1000),
                "reason_code": "SCHEMA_INVALID",
                "reason": str(e),
                "symbol": payload.get("symbol"),
                "idempotency_key": payload.get("idempotency_key"),
            }
            self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1",
                          reject_payload, "llm_intent_schema_invalid")
            _append_wal_event("LLM_INTENT_REJECTED_V1", rid,
                              reject_payload, "llm_intent_schema_invalid")
            return

        llm_cfg = getattr(getattr(self.config, "trading",
                          None), "llm_orchestration", None)
        mode = str(getattr(llm_cfg, "mode", "baseline"))
        symbols_llm = [str(s).upper()
                       for s in (getattr(llm_cfg, "symbols_llm", []) or [])]
        allow = [str(s).upper()
                 for s in (getattr(llm_cfg, "allowlist_symbols", []) or [])]

        if mode == "baseline":
            reject_payload = {
                "intent_id": cmd.intent_id,
                "request_id": request_id,
                "ts_ms": int(time.time() * 1000),
                "reason_code": "LLM_MODE_DISABLED",
                "reason": "llm_orchestration.mode=baseline",
                "symbol": cmd.symbol,
                "idempotency_key": cmd.idempotency_key,
            }
            self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1",
                          reject_payload, "llm_mode_disabled")
            _append_wal_event("LLM_INTENT_REJECTED_V1",
                              cmd.intent_id, reject_payload, "llm_mode_disabled")
            return

        sym_u = str(cmd.symbol).upper()
        if symbols_llm and sym_u not in symbols_llm:
            reject_payload = {
                "intent_id": cmd.intent_id,
                "request_id": request_id,
                "ts_ms": int(time.time() * 1000),
                "reason_code": "SYMBOL_NOT_OWNED_BY_LLM",
                "reason": "symbol not owned by llm_microstructure",
                "symbol": cmd.symbol,
                "idempotency_key": cmd.idempotency_key,
            }
            self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1",
                          reject_payload, "llm_symbol_not_owned")
            _append_wal_event("LLM_INTENT_REJECTED_V1", cmd.intent_id,
                              reject_payload, "llm_symbol_not_owned")
            return

        if allow and sym_u not in allow:
            reject_payload = {
                "intent_id": cmd.intent_id,
                "request_id": request_id,
                "ts_ms": int(time.time() * 1000),
                "reason_code": "SYMBOL_NOT_ALLOWED",
                "reason": "symbol not in llm_orchestration.allowlist_symbols",
                "symbol": cmd.symbol,
                "idempotency_key": cmd.idempotency_key,
            }
            self.fsm.emit("EVT:LLM_INTENT_REJECTED_V1",
                          reject_payload, "llm_symbol_not_allowed")
            _append_wal_event("LLM_INTENT_REJECTED_V1", cmd.intent_id,
                              reject_payload, "llm_symbol_not_allowed")
            return

        accepted_payload = {
            "intent_id": cmd.intent_id,
            "request_id": request_id,
            "enqueue_ts_ms": int(time.time() * 1000),
            "ipc_endpoint": self._endpoint,
            "queue_depth": 0,
        }
        self.fsm.emit("EVT:LLM_INTENT_ACCEPTED_V1",
                      accepted_payload, "llm_intent_ipc_accepted")
        _append_wal_event("LLM_INTENT_ACCEPTED_V1", cmd.intent_id,
                          accepted_payload, "llm_intent_ipc_accepted")

        self.fsm.emit(
            "CMD:LLM_INTENT_SUBMIT_V1",
            payload=cmd.model_dump(),
            why="llm_intent_submit",
        )


def register_llm_command_mapper(fsm: Any, logger: Optional[logging.Logger] = None) -> None:
    """Register CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1 mapper."""

    lg = logger or logging.getLogger(__name__)

    def _handler(event: Message) -> None:
        try:
            pld = event.pld if isinstance(event.pld, dict) else {}
            cmd = CmdLlmIntentSubmitV1.model_validate(pld)

            ext_payload = {
                "rid": str(cmd.intent_id),
                "intent_id": str(cmd.intent_id),
                "symbol": str(cmd.symbol).upper(),
                "side": str(cmd.side).upper(),
                "qty": str(cmd.order.qty),
                "order_type": str(cmd.order.type),
                "price": str(cmd.order.limit_price),
                "tif": str(cmd.order.time_in_force),
                "stop_price": str(cmd.brackets.sl_price) if cmd.brackets and cmd.brackets.sl_price else None,
                "target_price": str(cmd.brackets.tp_price) if cmd.brackets and cmd.brackets.tp_price else None,
                "valid_for_ms": None,
                "idempotent_key": str(cmd.idempotency_key) if cmd.idempotency_key else None,
                "source": "external_llm",
                "snapshot_ref": cmd.snapshot_ref.model_dump() if cmd.snapshot_ref else None,
                "why_short": truncate_why(str(cmd.why_short), 80),
            }

            fsm.emit(
                "CMD:EXTERNAL_OPEN_REQUEST_V1",
                payload=ext_payload,
                why="llm_external_open_request",
            )
            lg.info("LLM_EXTERNAL: intent_id=%s rid=%s side=%s qty=%s price=%s -> CMD:EXTERNAL_OPEN_REQUEST_V1",
                    cmd.intent_id, cmd.intent_id, cmd.side, cmd.order.qty, cmd.order.limit_price)
        except Exception as e:
            lg.error("LLM command mapper failed: %s", e, exc_info=True)

    fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)
    lg.info("Registered LLM command mapper: CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1")
