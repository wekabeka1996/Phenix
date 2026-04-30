from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

from apps.reference.domains.shadow_telemetry.contracts import CmdLlmIntentSubmitV1
from apps.reference.domains.shadow_telemetry.ipc import JsonlTcpQueueClient, JsonlTcpServer


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
        self._allowlist = set(str(x) for x in getattr(
            ingest_cfg, "allowlist_events", []) or [])
        self._required = bool(getattr(cfg, "required_for_mode", False))
        self._client: JsonlTcpQueueClient | None = None
        if self._enabled:
            self._client = JsonlTcpQueueClient(
                endpoint=str(ingest_cfg.ipc_endpoint),
                queue_maxsize=int(ingest_cfg.queue_maxsize),
                overflow_policy=str(ingest_cfg.overflow_policy),
                stop_timeout_ms=int(cfg.lifecycle.stop_timeout_ms),
                logger=self.logger.getChild("event_tap"),
                name="shadow_event_tap_client",
            )

    def start(self) -> None:
        if not self._enabled or self._client is None:
            return
        self._client.start()
        self.logger.info("Shadow event tap publisher started")

    def stop(self) -> None:
        if self._client is not None:
            self._client.stop()

    def publish(self, event_name: str, payload: Dict[str, Any], why: str) -> None:
        if not self._enabled or self._client is None:
            return
        if self._allowlist and event_name not in self._allowlist:
            return

        frame = {
            "frame_id": f"tap-{int(time.time() * 1000)}",
            "captured_ts_ms": int(time.time() * 1000),
            "event_name": event_name,
            "payload": payload,
            "why": truncate_why(str(why), 80),
        }
        ok = self._client.enqueue(frame)
        if not ok and self._required:
            self.logger.critical(
                "Shadow tap queue overflow with required_for_mode=true; event=%s", event_name
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
