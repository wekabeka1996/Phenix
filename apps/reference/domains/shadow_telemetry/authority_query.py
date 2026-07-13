"""Typed bounded query/reply bridge between the FastAPI edge and main runtime."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpRequestError,
    JsonlTcpRequestReplyClient,
)
from apps.reference.domains.shadow_telemetry.proposal_dry_run import (
    ProposalDryRunService,
    ProposalValidationError,
    validate_proposal_payload,
)
from apps.reference.domains.shadow_telemetry.read_model_service import (
    PhenixReadModelService,
    ReadModelUnavailableError,
)


QueryKind = Literal[
    "QUERY:AUTHORITY_COMPATIBILITY_V1",
    "QUERY:READ_MODEL_SESSION_V1",
    "QUERY:PROPOSAL_DRY_RUN_V1",
    "QUERY:PROPOSAL_DRY_RUN_RESULT_V1",
]
QueryStatus = Literal["OK", "REJECTED", "UNAVAILABLE", "STALE", "CONFLICT", "TIMEOUT"]
QUERY_KINDS = frozenset((
    "QUERY:AUTHORITY_COMPATIBILITY_V1",
    "QUERY:READ_MODEL_SESSION_V1",
    "QUERY:PROPOSAL_DRY_RUN_V1",
    "QUERY:PROPOSAL_DRY_RUN_RESULT_V1",
))


class AuthorityQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["p46.authority-query.v1"]
    request_kind: QueryKind
    request_id: str = Field(..., min_length=8, max_length=256)
    correlation_id: str = Field(..., min_length=8, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=256)
    deadline: datetime
    requested_at: datetime
    caller_runtime_id: str = Field(..., min_length=1)
    expected_environment: Literal["binance_futures_testnet"]
    payload: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def semantic_payload(self) -> "AuthorityQueryRequest":
        if self.deadline.tzinfo is None or self.requested_at.tzinfo is None:
            raise ValueError("query timestamps require timezone")
        if self.deadline <= self.requested_at:
            raise ValueError("query deadline must follow request time")
        if self.request_kind == "QUERY:PROPOSAL_DRY_RUN_V1" and not isinstance(self.payload, dict):
            raise ValueError("proposal dry-run query requires payload")
        if self.request_kind == "QUERY:PROPOSAL_DRY_RUN_RESULT_V1" and not self.payload:
            raise ValueError("dry-run result query requires proposal identity")
        return self


class AuthorityQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["p46.authority-query-response.v1"] = "p46.authority-query-response.v1"
    request_id: str
    correlation_id: str
    status: QueryStatus
    generated_at: datetime
    source_runtime_id: str
    environment: Literal["binance_futures_testnet"]
    runtime_generation: str
    source_versions: dict[str, str]
    payload: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None

    @model_validator(mode="after")
    def status_shape(self) -> "AuthorityQueryResponse":
        if self.generated_at.tzinfo is None:
            raise ValueError("response timestamp requires timezone")
        if self.status == "OK" and self.payload is None:
            raise ValueError("OK response requires payload")
        if self.status != "OK" and not self.error_code:
            raise ValueError("non-OK response requires error_code")
        return self


def _stable_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class RuntimeAuthorityQueryService:
    """Main-process-only semantic dispatcher over explicit runtime-owned readers."""

    def __init__(self, *, read_model: PhenixReadModelService, dry_run: ProposalDryRunService,
                 runtime_id: str, environment: str, runtime_generation: str,
                 supported_kinds: list[str], max_idempotency_entries: int,
                 clock: Callable[[], datetime]) -> None:
        if any(value is None for value in (read_model, dry_run, clock)):
            raise ValueError("main-process query authorities are explicit")
        if read_model.authority is not dry_run.authority:
            raise ValueError("read-model and dry-run must share one main-process authority")
        if set(supported_kinds) != QUERY_KINDS:
            raise ValueError("query registry must declare the exact supported semantic kinds")
        if environment != "binance_futures_testnet":
            raise ValueError("authority query bridge is testnet-only")
        self.read_model = read_model
        self.dry_run = dry_run
        self.runtime_id = runtime_id
        self.environment = environment
        self.runtime_generation = runtime_generation
        self.max_idempotency_entries = int(max_idempotency_entries)
        if self.max_idempotency_entries < 16:
            raise ValueError("idempotency cache bound is required")
        self.clock = clock
        self._lock = RLock()
        self._replies: dict[str, tuple[str, AuthorityQueryResponse]] = {}
        self.handler_calls = 0
        self.dry_run_handler_calls = 0

    def handle(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            request = AuthorityQueryRequest.model_validate(raw)
        except Exception:
            return self._response_from_raw(raw, "REJECTED", "QUERY_SCHEMA_INVALID").model_dump(mode="json")
        digest = _stable_hash(request.model_dump(mode="json"))
        with self._lock:
            prior = self._replies.get(request.request_id)
            if prior is not None:
                if prior[0] == digest:
                    return prior[1].model_dump(mode="json")
                return self._response(request, "CONFLICT", "QUERY_ID_CONFLICT").model_dump(mode="json")
            self.handler_calls += 1
            response = self._dispatch(request)
            while len(self._replies) >= self.max_idempotency_entries:
                self._replies.pop(next(iter(self._replies)))
            self._replies[request.request_id] = (digest, response)
            return response.model_dump(mode="json")

    def _dispatch(self, request: AuthorityQueryRequest) -> AuthorityQueryResponse:
        now = self.clock()
        if request.deadline <= now:
            return self._response(request, "TIMEOUT", "QUERY_DEADLINE_EXCEEDED")
        if request.expected_environment != self.environment:
            return self._response(request, "REJECTED", "QUERY_ENVIRONMENT_MISMATCH")
        if request.caller_runtime_id != self.runtime_id:
            return self._response(request, "REJECTED", "QUERY_RUNTIME_ID_MISMATCH")
        try:
            if request.request_kind == "QUERY:AUTHORITY_COMPATIBILITY_V1":
                payload = {
                    "main_runtime_reachable": True,
                    "runtime_id": self.runtime_id,
                    "environment": self.environment,
                    "runtime_generation": self.runtime_generation,
                    "supported_query_schema_versions": ["p46.authority-query.v1"],
                    "read_model_available": True,
                    "dry_run_available": True,
                }
                return self._response(request, "OK", payload=payload)
            if request.request_kind == "QUERY:READ_MODEL_SESSION_V1":
                payload = self.read_model.snapshot(request.session_id).model_dump(mode="json")
                return self._response(request, "OK", payload=payload, source_versions={
                    "read_model": str(payload["data_version"]),
                    "config": str(payload["config_version"]),
                })
            if request.request_kind == "QUERY:PROPOSAL_DRY_RUN_V1":
                self.dry_run_handler_calls += 1
                proposal = validate_proposal_payload(request.payload)
                if proposal.phenix_session_id != request.session_id:
                    return self._response(request, "REJECTED", "SESSION_ID_MISMATCH")
                result = self.dry_run.evaluate(proposal)
                status: QueryStatus = {
                    "ACCEPTED": "OK", "REJECTED": "REJECTED", "STALE": "STALE",
                    "CONFLICT": "CONFLICT", "UNAVAILABLE": "UNAVAILABLE",
                }[result.decision]
                return self._response(
                    request, status,
                    None if status == "OK" else (result.reason_codes[0] if result.reason_codes else result.decision),
                    payload=result.model_dump(mode="json"),
                    source_versions={
                        "config": str(result.config_version or "unavailable"),
                        "context": result.context_manifest_version,
                        "instruction": result.instruction_version,
                        "lease": str(result.lease_version),
                    },
                )
            proposal_id = str((request.payload or {}).get("proposal_id") or "")
            result = self.dry_run.get(proposal_id)
            return self._response(request, "OK", payload=result.model_dump(mode="json"))
        except ReadModelUnavailableError as exc:
            return self._response(request, "REJECTED" if str(exc) == "SESSION_NOT_FOUND" else "UNAVAILABLE", str(exc))
        except ProposalValidationError as exc:
            return self._response(request, "REJECTED", exc.reason)
        except Exception:
            return self._response(request, "UNAVAILABLE", "QUERY_AUTHORITY_UNAVAILABLE")

    def _response(self, request: AuthorityQueryRequest, status: QueryStatus,
                  error_code: Optional[str] = None, *, payload: Optional[dict[str, Any]] = None,
                  source_versions: Optional[dict[str, str]] = None) -> AuthorityQueryResponse:
        return AuthorityQueryResponse(
            request_id=request.request_id, correlation_id=request.correlation_id,
            status=status, generated_at=self.clock(), source_runtime_id=self.runtime_id,
            environment=self.environment, runtime_generation=self.runtime_generation,
            source_versions=source_versions or {}, payload=payload, error_code=error_code,
        )

    def _response_from_raw(self, raw: dict[str, Any], status: QueryStatus, error: str) -> AuthorityQueryResponse:
        return AuthorityQueryResponse(
            request_id=str(raw.get("request_id") or "invalid-request"),
            correlation_id=str(raw.get("correlation_id") or "invalid-correlation"),
            status=status, generated_at=self.clock(), source_runtime_id=self.runtime_id,
            environment=self.environment, runtime_generation=self.runtime_generation,
            source_versions={}, error_code=error,
        )


class MainProcessAuthorityQueryClient:
    """FastAPI-edge semantic client; it owns no authority and caches no result."""

    def __init__(self, transport: JsonlTcpRequestReplyClient, *, runtime_id: str,
                 environment: str, timeout_ms: int, clock: Callable[[], datetime]) -> None:
        self.transport = transport
        self.runtime_id = runtime_id
        self.environment = environment
        self.timeout_ms = int(timeout_ms)
        self.clock = clock
        self.runtime_generation: Optional[str] = None

    def handshake(self) -> dict[str, Any]:
        response = self._query("QUERY:AUTHORITY_COMPATIBILITY_V1", "compatibility")
        self.runtime_generation = response.runtime_generation
        return dict(response.payload or {})

    def read_model(self, session_id: str) -> dict[str, Any]:
        return self._payload(self._query("QUERY:READ_MODEL_SESSION_V1", session_id))

    def dry_run(self, session_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        return self._payload(self._query("QUERY:PROPOSAL_DRY_RUN_V1", session_id, proposal))

    def dry_run_result(self, proposal_id: str) -> dict[str, Any]:
        return self._payload(self._query(
            "QUERY:PROPOSAL_DRY_RUN_RESULT_V1", "dry-run-result", {"proposal_id": proposal_id}
        ))

    def _payload(self, response: AuthorityQueryResponse) -> dict[str, Any]:
        if response.payload is None:
            raise JsonlTcpRequestError(response.error_code or "IPC_REPLY_INVALID")
        if response.status not in {"OK", "REJECTED", "STALE", "CONFLICT"}:
            raise JsonlTcpRequestError(response.error_code or "IPC_QUERY_UNAVAILABLE")
        return dict(response.payload)

    def _query(self, kind: QueryKind, session_id: str,
               payload: Optional[dict[str, Any]] = None) -> AuthorityQueryResponse:
        now = self.clock()
        from datetime import timedelta
        request_id = f"query-{uuid.uuid4()}"
        correlation_id = f"correlation-{uuid.uuid4()}"
        request = AuthorityQueryRequest(
            schema_version="p46.authority-query.v1", request_kind=kind,
            request_id=request_id, correlation_id=correlation_id, session_id=session_id,
            deadline=now + timedelta(milliseconds=self.timeout_ms), requested_at=now,
            caller_runtime_id=self.runtime_id, expected_environment=self.environment,
            payload=payload,
        )
        raw = self.transport.request(request.model_dump(mode="json"))
        try:
            response = AuthorityQueryResponse.model_validate(raw)
        except Exception as exc:
            raise JsonlTcpRequestError("IPC_REPLY_INVALID") from exc
        if response.request_id != request_id or response.correlation_id != correlation_id:
            raise JsonlTcpRequestError("IPC_CORRELATION_MISMATCH")
        if response.source_runtime_id != self.runtime_id or response.environment != self.environment:
            raise JsonlTcpRequestError("IPC_COMPATIBILITY_MISMATCH")
        if self.runtime_generation is not None and response.runtime_generation != self.runtime_generation:
            self.runtime_generation = None
            raise JsonlTcpRequestError("IPC_RUNTIME_GENERATION_CHANGED")
        if response.status == "TIMEOUT":
            raise JsonlTcpRequestError("IPC_QUERY_TIMEOUT")
        if response.status == "UNAVAILABLE":
            raise JsonlTcpRequestError(response.error_code or "IPC_QUERY_UNAVAILABLE")
        return response
