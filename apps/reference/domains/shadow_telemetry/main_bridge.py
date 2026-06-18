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
from apps.reference.domains.shadow_telemetry.contracts import (
    CmdLlmBracketAmendV1,
    CmdLlmIntentSubmitV1,
    CmdLlmPositionCloseV1,
)
from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpQueueClient,
    JsonlTcpServer,
    ShadowTapDeliveryFailure,
)
from apps.reference.telemetry.metrics import (
    inc_shadow_tap_delivery_failure,
    inc_shadow_tap_delivery_log_suppressed,
)
from apps.reference.domains.decision_making.intent.truth_artifacts import (
    write_strategy_decision_blocked,
)
from apps.reference.domains.strategies.authority import FINANCIAL_MODES, resolve_strategy_mode


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

    def _runtime_allowlist(self) -> tuple[str, list[str], list[str]]:
        llm_cfg = getattr(getattr(self.config, "trading", None), "llm_orchestration", None)
        mode = str(getattr(llm_cfg, "mode", "baseline"))
        symbols_llm = [str(s).upper() for s in (getattr(llm_cfg, "symbols_llm", []) or [])]
        allow = [str(s).upper() for s in (getattr(llm_cfg, "allowlist_symbols", []) or [])]
        return mode, symbols_llm, allow

    def _emit_bridge_reject(
        self,
        *,
        event_name: str,
        rid: str,
        payload: Dict[str, Any],
        why: str,
    ) -> None:
        self.fsm.emit(event_name, payload, why)
        _append_wal_event(event_name.split(":", 1)[1], rid, payload, why)

    def _reject_runtime_symbol(
        self,
        *,
        event_name: str,
        rid: str,
        action_key: str,
        action_value: str,
        request_id: str,
        symbol: str,
        lifecycle_id: str | None,
        idempotency_key: str,
        mode: str,
        symbols_llm: list[str],
        allow: list[str],
    ) -> bool:
        if mode == "baseline":
            self._emit_bridge_reject(
                event_name=event_name,
                rid=rid,
                payload={
                    action_key: action_value,
                    "request_id": request_id,
                    "ts_ms": int(time.time() * 1000),
                    "reason_code": "LLM_MODE_DISABLED",
                    "reason": "llm_orchestration.mode=baseline",
                    "symbol": symbol,
                    "lifecycle_id": lifecycle_id,
                    "idempotency_key": idempotency_key,
                },
                why=f"{event_name.lower()}_mode_disabled",
            )
            return True

        sym_u = str(symbol).upper()
        if symbols_llm and sym_u not in symbols_llm:
            self._emit_bridge_reject(
                event_name=event_name,
                rid=rid,
                payload={
                    action_key: action_value,
                    "request_id": request_id,
                    "ts_ms": int(time.time() * 1000),
                    "reason_code": "SYMBOL_NOT_OWNED_BY_LLM",
                    "reason": "symbol not owned by llm_microstructure",
                    "symbol": symbol,
                    "lifecycle_id": lifecycle_id,
                    "idempotency_key": idempotency_key,
                },
                why=f"{event_name.lower()}_symbol_not_owned",
            )
            return True

        if allow and sym_u not in allow:
            self._emit_bridge_reject(
                event_name=event_name,
                rid=rid,
                payload={
                    action_key: action_value,
                    "request_id": request_id,
                    "ts_ms": int(time.time() * 1000),
                    "reason_code": "SYMBOL_NOT_ALLOWED",
                    "reason": "symbol not in llm_orchestration.allowlist_symbols",
                    "symbol": symbol,
                    "lifecycle_id": lifecycle_id,
                    "idempotency_key": idempotency_key,
                },
                why=f"{event_name.lower()}_symbol_not_allowed",
            )
            return True
        return False

    def _on_command(self, payload: Dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        request_kind = str(payload.get("request_kind") or "")
        is_eze_open = request_kind == "eze_open"
        is_eze_close = request_kind == "eze_close_position"
        is_eze_amend = request_kind == "eze_amend_brackets"
        rid = str(
            payload.get("intent_id")
            or payload.get("action_id")
            or payload.get("rid")
            or request_id
            or f"llm-{int(time.time() * 1000)}"
        )
        mode, symbols_llm, allow = self._runtime_allowlist()

        if request_kind in {"close_position", "eze_close_position"}:
            normalized_payload = dict(payload)
            normalized_payload["request_kind"] = "close_position"
            try:
                cmd_close = CmdLlmPositionCloseV1.model_validate(normalized_payload)
            except Exception as e:
                self._emit_bridge_reject(
                    event_name="EVT:LLM_CLOSE_REJECTED_V1",
                    rid=rid,
                    payload={
                        "action_id": payload.get("action_id"),
                        "request_id": request_id,
                        "ts_ms": int(time.time() * 1000),
                        "reason_code": "SCHEMA_INVALID",
                        "reason": str(e),
                        "symbol": payload.get("symbol"),
                        "lifecycle_id": payload.get("lifecycle_id"),
                        "idempotency_key": payload.get("idempotency_key"),
                    },
                    why="llm_close_schema_invalid",
                )
                return

            if not is_eze_close and self._reject_runtime_symbol(
                event_name="EVT:LLM_CLOSE_REJECTED_V1",
                rid=cmd_close.action_id,
                action_key="action_id",
                action_value=cmd_close.action_id,
                request_id=request_id,
                symbol=cmd_close.symbol,
                lifecycle_id=cmd_close.lifecycle_id,
                idempotency_key=cmd_close.idempotency_key,
                mode=mode,
                symbols_llm=symbols_llm,
                allow=allow,
            ):
                return

            accepted_payload = {
                "action_id": cmd_close.action_id,
                "request_id": request_id,
                "enqueue_ts_ms": int(time.time() * 1000),
                "ipc_endpoint": self._endpoint,
                "queue_depth": 0,
                "lifecycle_id": cmd_close.lifecycle_id,
                "ingress_mode": "eze_direct" if is_eze_close else "guarded",
            }
            self.fsm.emit("EVT:LLM_CLOSE_ACCEPTED_V1",
                          accepted_payload, "eze_close_ipc_accepted" if is_eze_close else "llm_close_ipc_accepted")
            _append_wal_event("LLM_CLOSE_ACCEPTED_V1", cmd_close.action_id,
                              accepted_payload, "eze_close_ipc_accepted" if is_eze_close else "llm_close_ipc_accepted")
            self.fsm.emit(
                "CMD:LLM_POSITION_CLOSE_V1",
                payload=cmd_close.model_dump(),
                why="eze_position_close" if is_eze_close else "llm_position_close",
            )
            return

        if request_kind in {"amend_brackets", "eze_amend_brackets"}:
            normalized_payload = dict(payload)
            normalized_payload["request_kind"] = "amend_brackets"
            try:
                cmd_amend = CmdLlmBracketAmendV1.model_validate(normalized_payload)
            except Exception as e:
                self._emit_bridge_reject(
                    event_name="EVT:LLM_BRACKET_AMEND_REJECTED_V1",
                    rid=rid,
                    payload={
                        "action_id": payload.get("action_id"),
                        "request_id": request_id,
                        "ts_ms": int(time.time() * 1000),
                        "reason_code": "SCHEMA_INVALID",
                        "reason": str(e),
                        "symbol": payload.get("symbol"),
                        "lifecycle_id": payload.get("lifecycle_id"),
                        "idempotency_key": payload.get("idempotency_key"),
                    },
                    why="llm_bracket_amend_schema_invalid",
                )
                return

            if not is_eze_amend and self._reject_runtime_symbol(
                event_name="EVT:LLM_BRACKET_AMEND_REJECTED_V1",
                rid=cmd_amend.action_id,
                action_key="action_id",
                action_value=cmd_amend.action_id,
                request_id=request_id,
                symbol=cmd_amend.symbol,
                lifecycle_id=cmd_amend.lifecycle_id,
                idempotency_key=cmd_amend.idempotency_key,
                mode=mode,
                symbols_llm=symbols_llm,
                allow=allow,
            ):
                return

            accepted_payload = {
                "action_id": cmd_amend.action_id,
                "request_id": request_id,
                "enqueue_ts_ms": int(time.time() * 1000),
                "ipc_endpoint": self._endpoint,
                "queue_depth": 0,
                "lifecycle_id": cmd_amend.lifecycle_id,
                "ingress_mode": "eze_direct" if is_eze_amend else "guarded",
            }
            self.fsm.emit("EVT:LLM_BRACKET_AMEND_ACCEPTED_V1",
                          accepted_payload, "eze_bracket_amend_ipc_accepted" if is_eze_amend else "llm_bracket_amend_ipc_accepted")
            _append_wal_event("LLM_BRACKET_AMEND_ACCEPTED_V1", cmd_amend.action_id,
                              accepted_payload, "eze_bracket_amend_ipc_accepted" if is_eze_amend else "llm_bracket_amend_ipc_accepted")
            self.fsm.emit(
                "CMD:LLM_BRACKET_AMEND_V1",
                payload=cmd_amend.model_dump(),
                why="eze_bracket_amend" if is_eze_amend else "llm_bracket_amend",
            )
            return

        normalized_open_payload = dict(payload)
        normalized_open_payload.pop("request_kind", None)
        try:
            cmd = CmdLlmIntentSubmitV1.model_validate(normalized_open_payload)
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

        llm_strategy_cfg = getattr(
            getattr(self.config, "strategies", None), "llm_microstructure", None)
        authority_mode = resolve_strategy_mode(llm_strategy_cfg)
        if authority_mode not in FINANCIAL_MODES:
            now_ms = int(time.time() * 1000)
            blocked_payload = write_strategy_decision_blocked(
                strategy_id="llm_microstructure",
                symbol=cmd.symbol,
                side=cmd.side,
                regime="UNCERTAIN",
                reason_code="AUTHORITY_MODE_SHADOW" if authority_mode == "shadow" else "AUTHORITY_MODE_DISABLED",
                reason="LLM strategy has no authority to open new risk",
                context="llm_intent_ingress:authority_mode",
                src="shadow_telemetry_ingress",
                ts_ms=now_ms,
                rid=cmd.intent_id,
                details={"mode": authority_mode, "terminal_outcome": "shadowed"},
                tf_sec=int(getattr(llm_strategy_cfg, "timeframe_sec", 60)),
            )
            self.fsm.emit(
                "EVT:STRATEGY_DECISION_BLOCKED",
                blocked_payload,
                "llm_strategy_authority_blocked",
            )
            self._emit_bridge_reject(
                event_name="EVT:LLM_INTENT_REJECTED_V1",
                rid=cmd.intent_id,
                payload={
                    "intent_id": cmd.intent_id,
                    "request_id": request_id,
                    "ts_ms": now_ms,
                    "reason_code": blocked_payload["reason_code"],
                    "reason": blocked_payload["reason"],
                    "symbol": cmd.symbol,
                    "idempotency_key": cmd.idempotency_key,
                },
                why="llm_strategy_authority_blocked",
            )
            return

        if not is_eze_open and self._reject_runtime_symbol(
            event_name="EVT:LLM_INTENT_REJECTED_V1",
            rid=cmd.intent_id,
            action_key="intent_id",
            action_value=cmd.intent_id,
            request_id=request_id,
            symbol=cmd.symbol,
            lifecycle_id=None,
            idempotency_key=cmd.idempotency_key,
            mode=mode,
            symbols_llm=symbols_llm,
            allow=allow,
        ):
            return

        accepted_payload = {
            "intent_id": cmd.intent_id,
            "request_id": request_id,
            "enqueue_ts_ms": int(time.time() * 1000),
            "ipc_endpoint": self._endpoint,
            "queue_depth": 0,
            "ingress_mode": "eze_direct" if is_eze_open else "guarded",
        }
        self.fsm.emit("EVT:LLM_INTENT_ACCEPTED_V1",
                      accepted_payload, "eze_intent_ipc_accepted" if is_eze_open else "llm_intent_ipc_accepted")
        _append_wal_event("LLM_INTENT_ACCEPTED_V1", cmd.intent_id,
                          accepted_payload, "eze_intent_ipc_accepted" if is_eze_open else "llm_intent_ipc_accepted")
        self.fsm.emit(
            "CMD:LLM_INTENT_SUBMIT_V1",
            payload=cmd.model_dump(),
            why="eze_intent_submit" if is_eze_open else "llm_intent_submit",
        )


def register_llm_command_mapper(fsm: Any, logger: Optional[logging.Logger] = None) -> None:
    """Register LLM ingress mappers into execution_position intake commands."""

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
        except Exception as e:
            lg.error("LLM command mapper failed: %s", e, exc_info=True)

    def _close_handler(event: Message) -> None:
        try:
            pld = event.pld if isinstance(event.pld, dict) else {}
            cmd = CmdLlmPositionCloseV1.model_validate(pld)
            ext_payload = {
                "rid": str(cmd.action_id),
                "action_id": str(cmd.action_id),
                "lifecycle_id": str(cmd.lifecycle_id),
                "symbol": str(cmd.symbol).upper(),
                "qty": str(cmd.qty) if cmd.qty is not None else None,
                "reason": str(cmd.reason),
                "idempotent_key": str(cmd.idempotency_key),
                "source": "external_llm",
            }
            fsm.emit(
                "CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1",
                payload=ext_payload,
                why="llm_external_close_request",
            )
        except Exception as e:
            lg.error("LLM close mapper failed: %s", e, exc_info=True)

    def _amend_handler(event: Message) -> None:
        try:
            pld = event.pld if isinstance(event.pld, dict) else {}
            cmd = CmdLlmBracketAmendV1.model_validate(pld)
            ext_payload = {
                "rid": str(cmd.action_id),
                "action_id": str(cmd.action_id),
                "lifecycle_id": str(cmd.lifecycle_id),
                "symbol": str(cmd.symbol).upper(),
                "side": str(cmd.side).upper(),
                "tp_price": str(cmd.brackets.tp_price),
                "sl_price": str(cmd.brackets.sl_price),
                "entry_price": str(cmd.entry_price) if cmd.entry_price is not None else None,
                "reason": str(cmd.reason),
                "idempotent_key": str(cmd.idempotency_key),
                "source": "external_llm",
            }
            fsm.emit(
                "CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1",
                payload=ext_payload,
                why="llm_external_bracket_amend_request",
            )
        except Exception as e:
            lg.error("LLM bracket amend mapper failed: %s", e, exc_info=True)

    fsm.listen("CMD:LLM_INTENT_SUBMIT_V1", _handler)
    fsm.listen("CMD:LLM_POSITION_CLOSE_V1", _close_handler)
    fsm.listen("CMD:LLM_BRACKET_AMEND_V1", _amend_handler)
    lg.info("Registered LLM command mappers for open, close, and bracket amend ingress")
