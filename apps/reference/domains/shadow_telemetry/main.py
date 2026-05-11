from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import logging
import os
import socket
import threading
import time
import uuid
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    record_failure_outcome,
)
from apps.reference.domains.shadow_telemetry.contracts import (
    CmdLlmBracketAmendV1,
    CmdLlmIntentSubmitV1,
    CmdLlmPositionCloseV1,
    IntentAcceptedResponseV1,
    LLMBracketAmendRequestV1,
    LLMCloseRequestV1,
    LLMIntentRequestV1,
    PositionActionAcceptedResponseV1,
    canonical_payload_hash,
    compute_bracket_amend_idempotency_key,
    compute_close_idempotency_key,
    compute_idempotency_key,
)
from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpQueueClient,
    JsonlTcpServer,
    parse_tcp_endpoint,
)
from apps.reference.domains.shadow_telemetry.snapshot_store import SnapshotStore
from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

LOG = logging.getLogger("shadow_telemetry.main")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _token_subject(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"bearer:{digest}"


def _load_bearer_tokens() -> set[str]:
    tokens: set[str] = set()
    single = os.getenv("SHADOW_TELEMETRY_BEARER_TOKEN", "").strip()
    if single:
        tokens.add(single)
    single_alt = os.getenv("AURORA_SHADOW_TELEMETRY_BEARER_TOKEN", "").strip()
    if single_alt:
        tokens.add(single_alt)

    many = os.getenv("SHADOW_TELEMETRY_BEARER_TOKENS", "").strip()
    if many:
        for part in many.split(","):
            part_s = part.strip()
            if part_s:
                tokens.add(part_s)
    return tokens


def _append_wal_event(verb: str, rid: str, payload: Dict[str, Any], why: str) -> None:
    try:
        msg = Message(
            op="EVT",
            verb=str(verb),
            src="shadow_telemetry_api",
            dst="any",
            rid=str(rid),
            pld=payload,
            why=truncate_why(str(why), 80) or "shadow_telemetry",
        )
        wal.append(msg.model_dump())
    except Exception:
        # Observability must never crash telemetry process.
        pass


def _emit_audit_event(app: FastAPI, event_name: str, payload: Dict[str, Any], why: str) -> None:
    event_full = str(event_name)
    if not event_full.startswith("EVT:"):
        event_full = f"EVT:{event_full}"
    verb = event_full.split(":", 1)[1]
    rid = str(payload.get("intent_id") or payload.get(
        "request_id") or f"req-{_now_ms()}")
    _append_wal_event(verb=verb, rid=rid, payload=payload, why=why)

    store: SnapshotStore = app.state.snapshot_store
    frame = {
        "frame_id": f"api-{_now_ms()}-{uuid.uuid4().hex[:8]}",
        "captured_ts_ms": _now_ms(),
        "event_name": event_full,
        "payload": payload,
        "why": truncate_why(str(why), 80) or "shadow_telemetry",
    }
    try:
        store.ingest_event(frame)
    except Exception:
        pass


def _reject_with_event(
    app: FastAPI,
    request_id: str,
    *,
    http_status: int,
    reason_code: str,
    reason: str,
    intent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> None:
    payload = {
        "intent_id": intent_id,
        "request_id": request_id,
        "ts_ms": _now_ms(),
        "reason_code": str(reason_code),
        "reason": truncate_why(str(reason), 80) or "reject",
        "symbol": symbol,
        "idempotency_key": idempotency_key,
    }
    _emit_audit_event(app, "EVT:LLM_INTENT_REJECTED_V1",
                      payload, f"reject:{reason_code}")
    raise HTTPException(
        status_code=http_status,
        detail={
            "request_id": request_id,
            "reason_code": str(reason_code),
            "reason": truncate_why(str(reason), 80) or "reject",
        },
    )


def _authorize_or_reject(
    app: FastAPI,
    request_id: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    auth_mode = str(getattr(app.state, "auth_mode", "bearer") or "bearer").strip().lower()
    source_host = request.client.host if request.client is not None else ""

    def _is_loopback_host(host: str) -> bool:
        host_s = str(host or "").strip().lower()
        if host_s in {"127.0.0.1", "::1", "localhost"}:
            return True
        try:
            return ipaddress.ip_address(host_s).is_loopback
        except ValueError:
            return False

    allow_loopback_noauth = auth_mode == "loopback_optional_bearer" and _is_loopback_host(source_host)

    if credentials is None:
        if allow_loopback_noauth:
            return "loopback:noauth"
        _reject_with_event(
            app,
            request_id,
            http_status=status.HTTP_401_UNAUTHORIZED,
            reason_code="AUTH_MISSING",
            reason="Missing bearer token",
        )
    if str(credentials.scheme).lower() != "bearer":
        _reject_with_event(
            app,
            request_id,
            http_status=status.HTTP_401_UNAUTHORIZED,
            reason_code="AUTH_SCHEME_INVALID",
            reason="Authorization scheme must be Bearer",
        )
    token = str(credentials.credentials or "").strip()
    if not token:
        _reject_with_event(
            app,
            request_id,
            http_status=status.HTTP_401_UNAUTHORIZED,
            reason_code="AUTH_TOKEN_EMPTY",
            reason="Bearer token is empty",
        )
    tokens: set[str] = app.state.auth_tokens
    if not tokens:
        _reject_with_event(
            app,
            request_id,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            reason_code="AUTH_NOT_CONFIGURED",
            reason="No bearer tokens configured on server",
        )

    for known in tokens:
        if hmac.compare_digest(token, known):
            return _token_subject(known)

    _reject_with_event(
        app,
        request_id,
        http_status=status.HTTP_403_FORBIDDEN,
        reason_code="AUTH_FORBIDDEN",
        reason="Bearer token is not authorized",
    )
    return "unreachable"


def _cleanup_runtime_state(app: FastAPI, now_ms: int) -> None:
    ttl_ms = int(app.state.idempotency_ttl_sec * 1000)
    open_ttl_ms = max(ttl_ms, int(
        app.state.intent_policy_cooldown_sec * 1000), 60_000)

    with app.state.state_lock:
        stale_idem = [
            key
            for key, rec in app.state.idempotency_records.items()
            if int(rec["ts_ms"]) + ttl_ms < now_ms
        ]
        for key in stale_idem:
            app.state.idempotency_records.pop(key, None)

        for sym, dq in list(app.state.active_intents.items()):
            while dq and (int(dq[0][0]) + open_ttl_ms) < now_ms:
                dq.popleft()
            if not dq:
                app.state.active_intents.pop(sym, None)


def _probe_ipc_endpoint(endpoint: str, timeout_sec: float = 0.25) -> bool:
    try:
        host, port = parse_tcp_endpoint(endpoint)
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def _effective_symbol_allowlist(app: FastAPI) -> set[str]:
    write_allow = set(str(s).upper() for s in (
        app.state.write_symbol_allowlist or []) if str(s).strip())
    llm_owned = set(str(s).upper()
                    for s in (app.state.symbols_llm or []) if str(s).strip())
    trading_allow = set(str(s).upper() for s in (
        app.state.trading_symbol_allowlist or []) if str(s).strip())

    effective = write_allow or trading_allow or llm_owned
    if write_allow and trading_allow:
        effective = write_allow & trading_allow
    if llm_owned:
        effective = effective & llm_owned if effective else llm_owned
    return effective


def _extract_reference_price(snapshot: Optional[Dict[str, Any]]) -> Optional[Decimal]:
    if not isinstance(snapshot, dict):
        return None

    try:
        features = snapshot.get("features")
        if isinstance(features, dict) and features.get("price") is not None:
            px = Decimal(str(features.get("price")))
            if px.is_finite() and px > 0:
                return px
    except (InvalidOperation, TypeError, ValueError):
        pass

    try:
        bar = snapshot.get("bar")
        if isinstance(bar, dict) and bar.get("close") is not None:
            px = Decimal(str(bar.get("close")))
            if px.is_finite() and px > 0:
                return px
    except (InvalidOperation, TypeError, ValueError):
        pass

    return None


def create_shadow_telemetry_app(config: Any) -> FastAPI:
    shadow_cfg = config.domains.shadow_telemetry
    write_cfg = shadow_cfg.api.write
    llm_cfg = config.trading.llm_orchestration
    intent_policy = llm_cfg.intent_policy

    app = FastAPI(
        title="Shadow Telemetry API",
        description="Read-path snapshots + write-path External LLM Intent Ingress",
        version="1.0.0",
    )

    bearer = HTTPBearer(auto_error=False)
    write_endpoint = str(write_cfg.intents_endpoint or "/intents/llm/v1")

    app.state.shadow_cfg = shadow_cfg
    app.state.write_endpoint = write_endpoint
    app.state.state_lock = threading.Lock()
    app.state.idempotency_records = {}  # key -> {payload_hash, response, ts_ms}
    app.state.intent_status = {}  # intent_id -> status payload
    app.state.position_action_status = {}  # action_id -> status payload
    app.state.rate_buckets = defaultdict(deque)  # subject -> deque[float(sec)]
    app.state.last_accept_ts_ms = {}  # symbol -> ts_ms
    # symbol -> deque[(ts_ms, intent_id)]
    app.state.active_intents = defaultdict(deque)
    app.state.idempotency_ttl_sec = int(write_cfg.idempotency_ttl_sec)
    app.state.intent_policy_max_open = int(intent_policy.max_open_intents)
    app.state.intent_policy_cooldown_sec = int(intent_policy.cooldown_sec)
    app.state.intent_policy_allow_limit_only = bool(
        intent_policy.allow_limit_only)
    app.state.intent_policy_require_tp_sl = bool(intent_policy.require_tp_sl)
    app.state.intent_policy_max_notional_usd = getattr(
        intent_policy, "max_notional_usd", None)
    app.state.intent_policy_max_qty = getattr(intent_policy, "max_qty", None)
    app.state.intent_policy_max_price_deviation_bps = getattr(
        intent_policy, "max_price_deviation_bps", None)
    app.state.intent_policy_allowed_tif = [str(x).upper() for x in (
        getattr(intent_policy, "allowed_tif", []) or [])]
    app.state.symbols_llm = [str(s).upper() for s in (
        getattr(llm_cfg, "symbols_llm", []) or [])]
    app.state.require_telemetry = bool(
        getattr(llm_cfg, "require_telemetry", False))
    app.state.write_symbol_allowlist = [
        str(s).upper() for s in (write_cfg.symbol_allowlist or [])]
    app.state.trading_symbol_allowlist = [
        str(s).upper() for s in (llm_cfg.allowlist_symbols or [])]
    app.state.rate_limit_per_min = int(write_cfg.rate_limit_per_min)
    app.state.require_snapshot_ref = bool(write_cfg.require_snapshot_ref)
    app.state.max_body_kb = int(write_cfg.max_body_kb)
    app.state.auth_mode = str(shadow_cfg.api.auth_mode or "bearer")
    app.state.auth_tokens = _load_bearer_tokens()

    @app.on_event("startup")
    async def _startup() -> None:
        store = SnapshotStore(
            output_dir=str(shadow_cfg.snapshot.output_dir),
            trigger_event=str(shadow_cfg.snapshot.trigger_event),
            bar_snapshots_enabled=bool(
                shadow_cfg.snapshot.tf_policy.bar_snapshots_enabled),
            tick_snapshots_mode=str(
                shadow_cfg.snapshot.tf_policy.tick_snapshots_mode),
            tick_sample_every_n=int(
                shadow_cfg.snapshot.tf_policy.tick_sample_every_n),
            min_tf_sec_for_full=int(
                shadow_cfg.snapshot.tf_policy.min_tf_sec_for_full),
            logger=LOG.getChild("snapshot_store"),
        )
        app.state.snapshot_store = store

        app.state.ingress_server = JsonlTcpServer(
            endpoint=str(shadow_cfg.ingest.ipc_endpoint),
            handler=store.ingest_event,
            stop_timeout_ms=int(shadow_cfg.lifecycle.stop_timeout_ms),
            logger=LOG.getChild("ingress"),
            name="shadow_telemetry_ingress_server",
        )
        app.state.ingress_server.start()

        app.state.command_client = JsonlTcpQueueClient(
            endpoint=str(shadow_cfg.egress_to_main.ipc_commands_endpoint),
            queue_maxsize=int(shadow_cfg.egress_to_main.queue_maxsize),
            overflow_policy=str(shadow_cfg.egress_to_main.overflow_policy),
            stop_timeout_ms=int(shadow_cfg.lifecycle.stop_timeout_ms),
            logger=LOG.getChild("egress"),
            name="shadow_telemetry_command_client",
        )
        app.state.command_client.start()

        if bool(write_cfg.enabled) and app.state.auth_mode == "bearer" and not app.state.auth_tokens:
            raise RuntimeError(
                "shadow_telemetry.api.write.enabled=true, but no bearer tokens configured "
                "(set SHADOW_TELEMETRY_BEARER_TOKEN or SHADOW_TELEMETRY_BEARER_TOKENS)"
            )

        LOG.info(
            "ShadowTelemetry startup complete: ingest=%s egress=%s write_endpoint=%s",
            shadow_cfg.ingest.ipc_endpoint,
            shadow_cfg.egress_to_main.ipc_commands_endpoint,
            write_endpoint,
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        try:
            app.state.ingress_server.stop()
        except Exception as exc:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.UNCLEAN_SHUTDOWN,
                location="domains/shadow_telemetry/main.py:_shutdown",
                message="Shadow telemetry ingress server stop failed",
                detail=type(exc).__name__,
            )
            LOG.warning(
                "Shadow telemetry ingress server stop failed", exc_info=True)
        try:
            app.state.command_client.stop()
        except Exception as exc:
            record_failure_outcome(
                FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
                FailureReasonCode.UNCLEAN_SHUTDOWN,
                location="domains/shadow_telemetry/main.py:_shutdown",
                message="Shadow telemetry command client stop failed",
                detail=type(exc).__name__,
            )
            LOG.warning(
                "Shadow telemetry command client stop failed", exc_info=True)
        LOG.info("ShadowTelemetry shutdown complete")

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.method.upper() == "POST" and request.url.path == app.state.write_endpoint:
            request_id = str(request.headers.get(
                "x-request-id") or f"req-{_now_ms()}")
            body = exc.body if isinstance(exc.body, dict) else {}
            intent_id = body.get("intent_id") if isinstance(
                body, dict) else None
            symbol = body.get("symbol") if isinstance(body, dict) else None
            idem = body.get("idempotency_key") if isinstance(
                body, dict) else None
            _emit_audit_event(
                app,
                "EVT:LLM_INTENT_REJECTED_V1",
                {
                    "intent_id": intent_id,
                    "request_id": request_id,
                    "ts_ms": _now_ms(),
                    "reason_code": "SCHEMA_INVALID",
                    "reason": "payload validation failed",
                    "symbol": symbol,
                    "idempotency_key": idem,
                },
                "reject:schema_invalid",
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "request_id": request_id,
                    "reason_code": "SCHEMA_INVALID",
                    "reason": "payload validation failed",
                },
            )

        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        queue_depth = int(app.state.command_client.queue_depth())
        return {
            "status": "healthy",
            "service": "shadow_telemetry",
            "ts_ms": _now_ms(),
            "ingest_endpoint": str(shadow_cfg.ingest.ipc_endpoint),
            "commands_endpoint": str(shadow_cfg.egress_to_main.ipc_commands_endpoint),
            # Canonical key expected by Stage A runbook.
            "queue_depth": queue_depth,
            # Backward-compatible alias.
            "commands_queue_depth": queue_depth,
        }

    @app.get("/snapshots/latest")
    async def snapshots_latest(
        symbol: Optional[str] = Query(default=None),
        tf_sec: Optional[int] = Query(default=None, ge=0),
    ) -> Dict[str, Any]:
        store: SnapshotStore = app.state.snapshot_store
        row = store.latest(symbol=symbol, tf_sec=tf_sec)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
        return row

    @app.get("/snapshots/tail")
    async def snapshots_tail(
        symbol: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        cursor: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        # Cursor is reserved for additive pagination evolution (MVP returns bounded tail).
        _ = cursor
        store: SnapshotStore = app.state.snapshot_store
        items = store.tail(symbol=symbol, limit=limit)
        return {
            "items": items,
            "next_cursor": None,
        }

    async def post_llm_intent(
        intent: LLMIntentRequestV1,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> JSONResponse:
        if not bool(write_cfg.enabled):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"reason_code": "WRITE_DISABLED",
                        "reason": "write-path disabled by config"},
            )

        request_id = str(request.headers.get(
            "x-request-id") or f"req-{uuid.uuid4()}")
        auth_subject = _authorize_or_reject(app, request_id, request, credentials)
        now_ms = _now_ms()

        content_len_raw = request.headers.get("content-length")
        if content_len_raw:
            try:
                content_len = int(content_len_raw)
            except Exception:
                content_len = 0
            if content_len > int(app.state.max_body_kb) * 1024:
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    reason_code="PAYLOAD_TOO_LARGE",
                    reason=f"request body exceeds max_body_kb={app.state.max_body_kb}",
                    intent_id=intent.intent_id,
                    symbol=intent.symbol,
                    idempotency_key=intent.idempotency_key,
                )

        _cleanup_runtime_state(app, now_ms)

        idempotency_hdr = str(request.headers.get(
            "idempotency-key") or "").strip()
        idempotency_key = str(
            intent.idempotency_key or idempotency_hdr or compute_idempotency_key(intent))
        normalized_intent = intent.model_copy(
            update={"idempotency_key": idempotency_key})
        payload_hash = canonical_payload_hash(
            normalized_intent.model_dump(
                mode="json", exclude={"idempotency_key"})
        )

        with app.state.state_lock:
            rec = app.state.idempotency_records.get(idempotency_key)
            if rec is not None:
                if rec["payload_hash"] == payload_hash:
                    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=dict(rec["response"]))
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_409_CONFLICT,
                    reason_code="IDEMPOTENCY_CONFLICT",
                    reason="same idempotency_key used with different payload",
                    intent_id=normalized_intent.intent_id,
                    symbol=normalized_intent.symbol,
                    idempotency_key=idempotency_key,
                )

        symbol = str(normalized_intent.symbol).upper()
        llm_symbols = set(str(s).upper() for s in (
            app.state.symbols_llm or []) if str(s).strip())
        if llm_symbols and symbol not in llm_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="SYMBOL_NOT_OWNED_BY_LLM",
                reason="symbol is not owned by llm_microstructure",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        allowed_symbols = _effective_symbol_allowlist(app)
        if allowed_symbols and symbol not in allowed_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="SYMBOL_NOT_ALLOWED",
                reason="symbol not in allowlist",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        allowed_tif = set(str(x).upper()
                          for x in (app.state.intent_policy_allowed_tif or []))
        requested_tif = str(normalized_intent.order.time_in_force).upper()
        if allowed_tif and requested_tif not in allowed_tif:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="LIMIT_ONLY_POLICY",
                reason=f"time_in_force={requested_tif} is forbidden by policy",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        if bool(app.state.require_snapshot_ref) and normalized_intent.snapshot_ref is None:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="SNAPSHOT_REF_REQUIRED",
                reason="snapshot_ref is required by policy",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        if bool(app.state.intent_policy_allow_limit_only) and str(normalized_intent.order.type).upper() != "LIMIT":
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="LIMIT_ONLY_POLICY",
                reason="only LIMIT orders are allowed",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        if bool(app.state.intent_policy_require_tp_sl):
            if normalized_intent.brackets.tp_price is None or normalized_intent.brackets.sl_price is None:
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    reason_code="TP_SL_REQUIRED",
                    reason="both tp_price and sl_price are required",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

        latest_snapshot = app.state.snapshot_store.latest(
            symbol=symbol, tf_sec=None)
        if app.state.require_telemetry and latest_snapshot is None:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="TELEMETRY_UNAVAILABLE",
                reason="no telemetry snapshot available for symbol",
                intent_id=normalized_intent.intent_id,
                symbol=symbol,
                idempotency_key=idempotency_key,
            )

        limit_price = Decimal(str(normalized_intent.order.limit_price))
        reference_price = _extract_reference_price(latest_snapshot)
        max_dev_bps = app.state.intent_policy_max_price_deviation_bps
        if max_dev_bps is not None:
            if reference_price is None:
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    reason_code="TELEMETRY_UNAVAILABLE",
                    reason="reference price unavailable for price band guard",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )
            deviation_bps = abs(limit_price - reference_price) / \
                reference_price * Decimal("10000")
            if deviation_bps > Decimal(str(max_dev_bps)):
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    reason_code="PRICE_OUT_OF_BAND",
                    reason=f"limit price deviation {deviation_bps:.4f} bps exceeds max {max_dev_bps}",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

        requested_qty = Decimal(str(normalized_intent.order.qty))
        max_qty = app.state.intent_policy_max_qty
        max_notional_usd = app.state.intent_policy_max_notional_usd
        cap_qty: Optional[Decimal] = None
        if max_qty is not None:
            cap_qty = Decimal(str(max_qty))
        if max_notional_usd is not None and limit_price > 0:
            cap_from_notional = Decimal(str(max_notional_usd)) / limit_price
            cap_qty = cap_from_notional if cap_qty is None else min(
                cap_qty, cap_from_notional)

        effective_qty = requested_qty
        if cap_qty is not None and requested_qty > cap_qty:
            if cap_qty <= 0:
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    reason_code="QTY_CAP_EXCEEDED",
                    reason="effective qty cap is non-positive",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )
            # Critical overshoot guard: reject if request is >3x effective cap.
            overshoot = requested_qty / \
                cap_qty if cap_qty > 0 else Decimal("999")
            if overshoot > Decimal("3"):
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_400_BAD_REQUEST,
                    reason_code="QTY_CAP_EXCEEDED",
                    reason=f"requested qty exceeds cap by {overshoot:.2f}x",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )
            effective_qty = cap_qty

        with app.state.state_lock:
            # Per-auth_subject rate limit.
            now_sec = time.time()
            subject_bucket: Deque[float] = app.state.rate_buckets[auth_subject]
            while subject_bucket and (now_sec - subject_bucket[0]) > 60.0:
                subject_bucket.popleft()
            if len(subject_bucket) >= int(app.state.rate_limit_per_min):
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                    reason_code="RATE_LIMIT_EXCEEDED",
                    reason=f"rate_limit_per_min={app.state.rate_limit_per_min}",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )
            subject_bucket.append(now_sec)

            # Symbol cooldown.
            last_ts = app.state.last_accept_ts_ms.get(symbol)
            cooldown_ms = int(app.state.intent_policy_cooldown_sec) * 1000
            if last_ts is not None and cooldown_ms > 0 and (now_ms - int(last_ts)) < cooldown_ms:
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                    reason_code="SYMBOL_COOLDOWN_ACTIVE",
                    reason=f"cooldown_sec={app.state.intent_policy_cooldown_sec}",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

            # Approximate max open intents per symbol (local bounded horizon).
            active_for_symbol: Deque[Tuple[int, str]
                                     ] = app.state.active_intents[symbol]
            if len(active_for_symbol) >= int(app.state.intent_policy_max_open):
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                    reason_code="MAX_OPEN_INTENTS_EXCEEDED",
                    reason=f"max_open_intents={app.state.intent_policy_max_open}",
                    intent_id=normalized_intent.intent_id,
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

        cmd_payload = normalized_intent.model_dump(mode="json")
        if effective_qty != requested_qty:
            cmd_payload.setdefault("policy_hints", {})
            cmd_payload["policy_hints"]["risk_tag"] = "QTY_CLAMPED"
            cmd_payload["order"]["qty"] = str(effective_qty.normalize())

        cmd = CmdLlmIntentSubmitV1.model_validate(
            {
                **cmd_payload,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            }
        )

        source_ip = request.client.host if request.client is not None else None
        received_payload = {
            "intent_id": cmd.intent_id,
            "request_id": request_id,
            "auth_subject": auth_subject,
            "source_ip": source_ip,
            "ts_ms": now_ms,
            "symbol": cmd.symbol,
            "side": cmd.side,
            "idempotency_key": cmd.idempotency_key,
            "why_short": truncate_why(str(cmd.why_short), 80),
        }
        _emit_audit_event(app, "EVT:LLM_INTENT_RECEIVED_V1",
                          received_payload, "llm_intent_received")

        app.state.snapshot_store.record_external_intent(
            {
                "symbol": cmd.symbol,
                "intent_id": cmd.intent_id,
                "idempotency_key": cmd.idempotency_key,
                "snapshot_ref": cmd.snapshot_ref.model_dump(mode="json") if cmd.snapshot_ref else None,
                "llm_decision": {
                    "side": cmd.side,
                    "limit_price": cmd.order.limit_price,
                    "qty": cmd.order.qty,
                    "tp_price": cmd.brackets.tp_price,
                    "sl_price": cmd.brackets.sl_price,
                },
                "why_short": truncate_why(str(cmd.why_short), 80),
                "model_meta": cmd.model_meta.model_dump(mode="json") if cmd.model_meta else None,
            }
        )

        ipc_endpoint = str(
            app.state.shadow_cfg.egress_to_main.ipc_commands_endpoint)
        if not _probe_ipc_endpoint(ipc_endpoint):
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_UNAVAILABLE",
                reason=f"main ingress endpoint is unavailable: {ipc_endpoint}",
                intent_id=cmd.intent_id,
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )

        ok = bool(app.state.command_client.enqueue(
            cmd.model_dump(mode="json")))
        if not ok:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_QUEUE_FULL",
                reason="failed to enqueue command to main ingress",
                intent_id=cmd.intent_id,
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )

        response_obj = IntentAcceptedResponseV1(
            intent_id=cmd.intent_id,
            request_id=request_id,
            state="queued",
        )
        response_payload = response_obj.model_dump(mode="json")

        with app.state.state_lock:
            app.state.idempotency_records[idempotency_key] = {
                "payload_hash": payload_hash,
                "response": response_payload,
                "ts_ms": now_ms,
            }
            app.state.last_accept_ts_ms[symbol] = now_ms
            app.state.active_intents[symbol].append(
                (now_ms, str(cmd.intent_id)))
            app.state.intent_status[str(cmd.intent_id)] = {
                "intent_id": str(cmd.intent_id),
                "request_id": request_id,
                "state": "queued",
                "symbol": symbol,
                "ts_ms": now_ms,
                "idempotency_key": idempotency_key,
            }

        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response_payload)

    app.add_api_route(
        path=write_endpoint,
        endpoint=post_llm_intent,
        methods=["POST"],
        response_model=IntentAcceptedResponseV1,
        status_code=status.HTTP_202_ACCEPTED,
        openapi_extra={
            "x-openai-isConsequential": bool(write_cfg.consequential)},
        responses={
            202: {"description": "Accepted (queued for async processing)"},
            400: {"description": "Schema or policy violation"},
            401: {"description": "Unauthorized"},
            403: {"description": "Forbidden"},
            409: {"description": "Idempotency conflict"},
            429: {"description": "Rate limit / policy throttle"},
            503: {"description": "IPC unavailable or fail-closed"},
        },
        tags=["shadow-telemetry"],
    )

    async def post_position_close(
        lifecycle_id: str,
        payload: LLMCloseRequestV1,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> JSONResponse:
        request_id = str(request.headers.get("x-request-id") or f"req-{uuid.uuid4()}")
        now_ms = _now_ms()
        _cleanup_runtime_state(app, now_ms)
        auth_subject = _authorize_or_reject(app, request_id, request, credentials)

        if str(lifecycle_id).strip() != str(payload.lifecycle_id).strip():
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="LIFECYCLE_ID_MISMATCH",
                reason="path lifecycle_id must match payload lifecycle_id",
                symbol=payload.symbol,
            )

        symbol = str(payload.symbol).upper()
        llm_symbols = set(str(s).upper() for s in (app.state.symbols_llm or []) if str(s).strip())
        if llm_symbols and symbol not in llm_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_403_FORBIDDEN,
                reason_code="SYMBOL_NOT_OWNED_BY_LLM",
                reason="symbol not owned by llm_microstructure",
                symbol=symbol,
                idempotency_key=payload.idempotency_key,
            )

        allowed_symbols = _effective_symbol_allowlist(app)
        if allowed_symbols and symbol not in allowed_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_403_FORBIDDEN,
                reason_code="SYMBOL_NOT_ALLOWED",
                reason="symbol not in allowlist",
                symbol=symbol,
                idempotency_key=payload.idempotency_key,
            )

        idempotency_key = payload.idempotency_key or compute_close_idempotency_key(payload)
        payload_hash = canonical_payload_hash(payload.model_dump(mode="json"))
        with app.state.state_lock:
            rec = app.state.idempotency_records.get(idempotency_key)
            if rec is not None:
                if rec["payload_hash"] == payload_hash:
                    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=dict(rec["response"]))
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_409_CONFLICT,
                    reason_code="IDEMPOTENCY_CONFLICT",
                    reason="same idempotency_key used with different payload",
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

        cmd = CmdLlmPositionCloseV1.model_validate(
            {
                **payload.model_dump(mode="json"),
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            }
        )
        _emit_audit_event(
            app,
            "EVT:LLM_CLOSE_RECEIVED_V1",
            {
                "action_id": cmd.action_id,
                "request_id": request_id,
                "auth_subject": auth_subject,
                "source_ip": request.client.host if request.client is not None else None,
                "ts_ms": now_ms,
                "symbol": cmd.symbol,
                "lifecycle_id": cmd.lifecycle_id,
                "reason": truncate_why(str(cmd.reason), 80),
            },
            "llm_close_received",
        )

        ipc_endpoint = str(app.state.shadow_cfg.egress_to_main.ipc_commands_endpoint)
        if not _probe_ipc_endpoint(ipc_endpoint):
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_UNAVAILABLE",
                reason=f"main ingress endpoint is unavailable: {ipc_endpoint}",
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )
        ok = bool(app.state.command_client.enqueue(cmd.model_dump(mode="json")))
        if not ok:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_QUEUE_FULL",
                reason="failed to enqueue close command to main ingress",
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )

        response_obj = PositionActionAcceptedResponseV1(
            action_id=cmd.action_id,
            request_id=request_id,
            lifecycle_id=cmd.lifecycle_id,
            action="close_position",
            state="queued",
        )
        response_payload = response_obj.model_dump(mode="json")
        with app.state.state_lock:
            app.state.idempotency_records[idempotency_key] = {
                "payload_hash": payload_hash,
                "response": response_payload,
                "ts_ms": now_ms,
            }
            app.state.position_action_status[str(cmd.action_id)] = response_payload
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response_payload)

    async def patch_position_brackets(
        lifecycle_id: str,
        payload: LLMBracketAmendRequestV1,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> JSONResponse:
        request_id = str(request.headers.get("x-request-id") or f"req-{uuid.uuid4()}")
        now_ms = _now_ms()
        _cleanup_runtime_state(app, now_ms)
        auth_subject = _authorize_or_reject(app, request_id, request, credentials)

        if str(lifecycle_id).strip() != str(payload.lifecycle_id).strip():
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_400_BAD_REQUEST,
                reason_code="LIFECYCLE_ID_MISMATCH",
                reason="path lifecycle_id must match payload lifecycle_id",
                symbol=payload.symbol,
            )

        symbol = str(payload.symbol).upper()
        llm_symbols = set(str(s).upper() for s in (app.state.symbols_llm or []) if str(s).strip())
        if llm_symbols and symbol not in llm_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_403_FORBIDDEN,
                reason_code="SYMBOL_NOT_OWNED_BY_LLM",
                reason="symbol not owned by llm_microstructure",
                symbol=symbol,
                idempotency_key=payload.idempotency_key,
            )

        allowed_symbols = _effective_symbol_allowlist(app)
        if allowed_symbols and symbol not in allowed_symbols:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_403_FORBIDDEN,
                reason_code="SYMBOL_NOT_ALLOWED",
                reason="symbol not in allowlist",
                symbol=symbol,
                idempotency_key=payload.idempotency_key,
            )

        idempotency_key = payload.idempotency_key or compute_bracket_amend_idempotency_key(payload)
        payload_hash = canonical_payload_hash(payload.model_dump(mode="json"))
        with app.state.state_lock:
            rec = app.state.idempotency_records.get(idempotency_key)
            if rec is not None:
                if rec["payload_hash"] == payload_hash:
                    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=dict(rec["response"]))
                _reject_with_event(
                    app,
                    request_id,
                    http_status=status.HTTP_409_CONFLICT,
                    reason_code="IDEMPOTENCY_CONFLICT",
                    reason="same idempotency_key used with different payload",
                    symbol=symbol,
                    idempotency_key=idempotency_key,
                )

        cmd = CmdLlmBracketAmendV1.model_validate(
            {
                **payload.model_dump(mode="json"),
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            }
        )
        _emit_audit_event(
            app,
            "EVT:LLM_BRACKET_AMEND_RECEIVED_V1",
            {
                "action_id": cmd.action_id,
                "request_id": request_id,
                "auth_subject": auth_subject,
                "source_ip": request.client.host if request.client is not None else None,
                "ts_ms": now_ms,
                "symbol": cmd.symbol,
                "lifecycle_id": cmd.lifecycle_id,
                "tp_price": cmd.brackets.tp_price,
                "sl_price": cmd.brackets.sl_price,
            },
            "llm_bracket_amend_received",
        )

        ipc_endpoint = str(app.state.shadow_cfg.egress_to_main.ipc_commands_endpoint)
        if not _probe_ipc_endpoint(ipc_endpoint):
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_UNAVAILABLE",
                reason=f"main ingress endpoint is unavailable: {ipc_endpoint}",
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )
        ok = bool(app.state.command_client.enqueue(cmd.model_dump(mode="json")))
        if not ok:
            _reject_with_event(
                app,
                request_id,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                reason_code="IPC_QUEUE_FULL",
                reason="failed to enqueue bracket amend command to main ingress",
                symbol=cmd.symbol,
                idempotency_key=cmd.idempotency_key,
            )

        response_obj = PositionActionAcceptedResponseV1(
            action_id=cmd.action_id,
            request_id=request_id,
            lifecycle_id=cmd.lifecycle_id,
            action="amend_brackets",
            state="queued",
        )
        response_payload = response_obj.model_dump(mode="json")
        with app.state.state_lock:
            app.state.idempotency_records[idempotency_key] = {
                "payload_hash": payload_hash,
                "response": response_payload,
                "ts_ms": now_ms,
            }
            app.state.position_action_status[str(cmd.action_id)] = response_payload
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response_payload)

    app.add_api_route(
        path="/positions/{lifecycle_id}/close",
        endpoint=post_position_close,
        methods=["POST"],
        response_model=PositionActionAcceptedResponseV1,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["shadow-telemetry"],
    )
    app.add_api_route(
        path="/positions/{lifecycle_id}/brackets",
        endpoint=patch_position_brackets,
        methods=["PATCH"],
        response_model=PositionActionAcceptedResponseV1,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["shadow-telemetry"],
    )

    def _custom_openapi() -> Dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        # Contract policy: expose 400 for schema violations (not FastAPI 422).
        post_schema = schema.get("paths", {}).get(
            write_endpoint, {}).get("post", {})
        responses = post_schema.get("responses", {})
        responses.pop("422", None)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi

    @app.get("/intents/status")
    async def intent_status(intent_id: str = Query(..., min_length=1)) -> Dict[str, Any]:
        with app.state.state_lock:
            status_row = app.state.intent_status.get(str(intent_id))
            if status_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="intent_id not found")
            return dict(status_row)

    return app


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shadow Telemetry domain service")
    parser.add_argument(
        "--config-dir",
        default="config/aurora",
        help="Path to Aurora config directory (default: config/aurora)",
    )
    parser.add_argument("--host", default=None, help="Override API host")
    parser.add_argument("--port", type=int, default=None,
                        help="Override API port")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    project_root = _resolve_project_root()
    cfg_dir = Path(args.config_dir)
    if not cfg_dir.is_absolute():
        cfg_dir = (project_root / cfg_dir).resolve()

    config = ConfigLoader(config_dir=cfg_dir).load_config()
    app = create_shadow_telemetry_app(config)

    shadow_cfg = config.domains.shadow_telemetry
    host = str(args.host or shadow_cfg.api.host)
    port = int(args.port or shadow_cfg.api.port)

    ssl_certfile = None
    ssl_keyfile = None
    if bool(shadow_cfg.api.tls):
        ssl_certfile = os.getenv(
            "SHADOW_TELEMETRY_TLS_CERT") or os.getenv("AURORA_TLS_CERT")
        ssl_keyfile = os.getenv(
            "SHADOW_TELEMETRY_TLS_KEY") or os.getenv("AURORA_TLS_KEY")
        if not ssl_certfile or not ssl_keyfile:
            raise RuntimeError(
                "TLS enabled but cert/key are missing. Set SHADOW_TELEMETRY_TLS_CERT and SHADOW_TELEMETRY_TLS_KEY."
            )

    LOG.info(
        "Starting ShadowTelemetry API host=%s port=%s tls=%s write_endpoint=%s",
        host,
        port,
        bool(shadow_cfg.api.tls),
        app.state.write_endpoint,
    )

    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=str(args.log_level).lower(),
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
