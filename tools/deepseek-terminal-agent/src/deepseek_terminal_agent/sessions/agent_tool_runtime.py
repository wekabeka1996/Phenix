"""Schema-validated agent tools backed by the P41X coordination kernel."""
from __future__ import annotations

from typing import Any, Literal, Optional, Type
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .collective_memory import CollectiveMemoryStore
from .collective_memory_models import SourceReference, utc_now_iso
from .coordination_config import CoordinationConfig


AgentToolName = Literal[
    "GET_MARKET_CONTEXT",
    "GET_FEATURES",
    "GET_PORTFOLIO_STATE",
    "GET_OWN_POSITIONS",
    "GET_PEER_PUBLICATIONS",
    "READ_COLLECTIVE_MEMORY",
    "PUBLISH_OBSERVATION",
    "PUBLISH_RISK_WARNING",
    "WRITE_PRIVATE_REFLECTION",
    "ASK_SUBAGENT",
    "REQUEST_ORDER",
    "REQUEST_CANCEL",
    "REQUEST_CLOSE",
    "EMIT_SOS",
    "ACK_INSTRUCTIONS",
]


class ToolIdentityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)


class ReadOwnedInput(ToolIdentityInput):
    symbols: list[str] = Field(default_factory=list)


class PeerPublicationInput(ToolIdentityInput):
    cursor_sequence: Optional[int] = Field(default=None, ge=0)


class PublishObservationInput(ToolIdentityInput):
    kind: Literal[
        "market_regime",
        "feature_trust",
        "peer_observation",
        "unresolved_question",
        "active_hypothesis",
    ]
    summary: str = Field(..., min_length=1)
    symbol: Optional[str] = None
    source_refs: list[SourceReference] = Field(default_factory=list)
    idempotency_key: str = Field(..., min_length=1)
    expected_version: Optional[int] = Field(default=None, ge=0)


class PublishRiskWarningInput(ToolIdentityInput):
    summary: str = Field(..., min_length=1)
    symbol: Optional[str] = None
    source_refs: list[SourceReference] = Field(default_factory=list)
    idempotency_key: str = Field(..., min_length=1)
    expected_version: Optional[int] = Field(default=None, ge=0)


class PrivateReflectionInput(ToolIdentityInput):
    target_agent_id: str = Field(..., min_length=1)
    kind: Literal["reasoning_summary", "hypothesis", "feature_trust", "reflection"]
    summary: str = Field(..., min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)
    idempotency_key: str = Field(..., min_length=1)


class AskSubagentInput(ToolIdentityInput):
    symbol: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    context_refs: list[SourceReference] = Field(default_factory=list)
    idempotency_key: str = Field(..., min_length=1)


class CommandInput(ToolIdentityInput):
    symbol: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    intent_ref: str = Field(..., min_length=1)
    command_id: Optional[str] = None
    idempotency_key: str = Field(..., min_length=1)


class OrderCommandInput(CommandInput):
    sizing_ref: str = Field(..., min_length=1)


class SOSEventInput(ToolIdentityInput):
    reason: str = Field(..., min_length=1)
    symbol: Optional[str] = None
    source_refs: list[SourceReference] = Field(default_factory=list)
    idempotency_key: str = Field(..., min_length=1)


class InstructionAckInput(ToolIdentityInput):
    manifest_version: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(..., min_length=1)
    tool_name: AgentToolName
    ok: bool
    status: str = Field(..., min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any]


class AgentToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: AgentToolName
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission: str
    symbol_scope: str
    timeout_seconds: int
    retry_policy: dict[str, Any]
    idempotency: str
    audit_fields: list[str]
    failure_classes: list[str]


INPUT_MODELS: dict[str, Type[ToolIdentityInput]] = {
    "GET_MARKET_CONTEXT": ReadOwnedInput,
    "GET_FEATURES": ReadOwnedInput,
    "GET_PORTFOLIO_STATE": ToolIdentityInput,
    "GET_OWN_POSITIONS": ToolIdentityInput,
    "GET_PEER_PUBLICATIONS": PeerPublicationInput,
    "READ_COLLECTIVE_MEMORY": ToolIdentityInput,
    "PUBLISH_OBSERVATION": PublishObservationInput,
    "PUBLISH_RISK_WARNING": PublishRiskWarningInput,
    "WRITE_PRIVATE_REFLECTION": PrivateReflectionInput,
    "ASK_SUBAGENT": AskSubagentInput,
    "REQUEST_ORDER": OrderCommandInput,
    "REQUEST_CANCEL": CommandInput,
    "REQUEST_CLOSE": CommandInput,
    "EMIT_SOS": SOSEventInput,
    "ACK_INSTRUCTIONS": InstructionAckInput,
}


class AgentToolRuntime:
    """Registered tool boundary. It records commands but never imports an exchange client."""

    def __init__(self, config: CoordinationConfig, store: CollectiveMemoryStore) -> None:
        self.config = config
        self.store = store

    def contracts(self) -> list[AgentToolContract]:
        output_schema = AgentToolResult.model_json_schema()
        contracts: list[AgentToolContract] = []
        for name in sorted(INPUT_MODELS):
            policy = self.config.tool_permissions[name]
            contracts.append(
                AgentToolContract(
                    tool_name=name,
                    input_schema=INPUT_MODELS[name].model_json_schema(),
                    output_schema=output_schema,
                    permission=policy.permission,
                    symbol_scope=policy.symbol_scope,
                    timeout_seconds=policy.timeout_seconds,
                    retry_policy=policy.retry.model_dump(),
                    idempotency=policy.idempotency,
                    audit_fields=[
                        "tool_call_id",
                        "tool_name",
                        "session_id",
                        "agent_id",
                        "agent_number",
                        "created_at",
                        "idempotency_key",
                    ],
                    failure_classes=[
                        "validation_error",
                        "permission_denied",
                        "symbol_scope_rejected",
                        "stale_state",
                        "lease_expired",
                        "session_missing",
                        "runtime_unavailable",
                    ],
                )
            )
        return contracts

    def invoke(self, tool_name: AgentToolName, raw_input: dict[str, Any]) -> AgentToolResult:
        model = INPUT_MODELS.get(tool_name)
        if model is None:
            raise ValueError(f"unregistered agent tool: {tool_name}")
        payload = model.model_validate(raw_input)
        identity = self.config.agent(payload.agent_id)
        if identity.agent_number != payload.agent_number:
            raise ValueError("agent identity mismatch")
        policy = self.config.tool_permissions[tool_name]
        if payload.agent_id not in policy.allowed_agents:
            raise PermissionError(f"{payload.agent_id} is not allowed to invoke {tool_name}")
        tool_call_id = f"tool-{uuid4().hex}"
        data, status = self._dispatch(tool_name, payload)
        return AgentToolResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            ok=True,
            status=status,
            data=data,
            audit={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "session_id": payload.session_id,
                "agent_id": payload.agent_id,
                "agent_number": payload.agent_number,
                "created_at": utc_now_iso(),
                "idempotency_key": getattr(payload, "idempotency_key", None),
                "environment": self.config.environment,
                "raw_exchange_client_exposed": False,
            },
        )

    def _dispatch(self, tool_name: str, payload: ToolIdentityInput) -> tuple[dict[str, Any], str]:
        state = self.store.get_state(payload.session_id)
        identity = self.config.agent(payload.agent_id)
        if tool_name == "GET_MARKET_CONTEXT":
            requested = {symbol.upper() for symbol in getattr(payload, "symbols", [])} or set(identity.symbols)
            if not requested.issubset(set(identity.symbols)):
                raise PermissionError("market context request exceeds owned symbol scope")
            publications = [
                item.model_dump()
                for item in state.publications
                if item.kind in {"market_regime", "peer_observation"}
                and (item.symbol is None or item.symbol in requested)
            ]
            return {"symbols": sorted(requested), "publications": publications}, "ok"
        if tool_name == "GET_FEATURES":
            requested = {symbol.upper() for symbol in getattr(payload, "symbols", [])} or set(identity.symbols)
            if not requested.issubset(set(identity.symbols)):
                raise PermissionError("feature request exceeds owned symbol scope")
            features = {key: value.model_dump() for key, value in state.feature_trust_states.items()}
            return {"symbols": sorted(requested), "feature_trust": features}, "ok"
        if tool_name == "GET_PORTFOLIO_STATE":
            return {"portfolio": state.portfolio.model_dump() if state.portfolio else None}, "ok"
        if tool_name == "GET_OWN_POSITIONS":
            positions = state.portfolio.active_positions if state.portfolio else []
            owned = [item for item in positions if str(item.get("symbol", "")).upper() in identity.symbols]
            return {"positions": owned, "symbols": identity.symbols}, "ok"
        if tool_name == "GET_PEER_PUBLICATIONS":
            assert isinstance(payload, PeerPublicationInput)
            items = self.store.get_peer_publications(
                session_id=payload.session_id,
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                cursor_sequence=payload.cursor_sequence,
            )
            next_cursor = max((item.sequence for item in items), default=payload.cursor_sequence or 0)
            return {"publications": [item.model_dump() for item in items], "next_cursor": next_cursor}, "ok"
        if tool_name == "READ_COLLECTIVE_MEMORY":
            bounded = state.model_dump(exclude={"processed_idempotency_keys"})
            return {"collective_state": bounded}, "ok"
        if tool_name == "PUBLISH_OBSERVATION":
            assert isinstance(payload, PublishObservationInput)
            write = self.store.publish_observation(
                session_id=payload.session_id,
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                kind=payload.kind,
                summary=payload.summary,
                symbol=payload.symbol,
                source_refs=payload.source_refs,
                idempotency_key=payload.idempotency_key,
                expected_version=payload.expected_version,
            )
            return write.model_dump(), "deduplicated" if write.deduplicated else "recorded"
        if tool_name == "PUBLISH_RISK_WARNING":
            assert isinstance(payload, PublishRiskWarningInput)
            write = self.store.publish_risk_warning(
                session_id=payload.session_id,
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                summary=payload.summary,
                symbol=payload.symbol,
                source_refs=payload.source_refs,
                idempotency_key=payload.idempotency_key,
                expected_version=payload.expected_version,
            )
            return write.model_dump(), "deduplicated" if write.deduplicated else "recorded"
        if tool_name == "WRITE_PRIVATE_REFLECTION":
            assert isinstance(payload, PrivateReflectionInput)
            reflection = self.store.write_private_reflection(
                session_id=payload.session_id,
                actor_agent_id=payload.agent_id,
                actor_agent_number=payload.agent_number,
                target_agent_id=payload.target_agent_id,
                kind=payload.kind,
                summary=payload.summary,
                source_refs=payload.source_refs,
                idempotency_key=payload.idempotency_key,
            )
            return {"reflection": reflection.model_dump()}, "recorded"
        if tool_name == "ASK_SUBAGENT":
            assert isinstance(payload, AskSubagentInput)
            self.store.validate_configured_symbol_scope(payload.agent_id, payload.agent_number, payload.symbol)
            write = self.store.append_evidence(
                session_id=payload.session_id,
                event_type="SUBAGENT_REVIEW_REQUESTED",
                category="subagent",
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                idempotency_key=payload.idempotency_key,
                source_refs=payload.context_refs,
                payload={
                    "request_id": f"subagent-request-{uuid4().hex}",
                    "symbol": payload.symbol.upper(),
                    "question": payload.question,
                    "context_refs": [item.model_dump() for item in payload.context_refs],
                    "execution": "recorded_for_registered_subagent_runtime",
                },
            )
            return write.model_dump(), "recorded"
        if tool_name in {"REQUEST_ORDER", "REQUEST_CANCEL", "REQUEST_CLOSE"}:
            assert isinstance(payload, CommandInput)
            write = self.store.request_command(
                session_id=payload.session_id,
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                command_kind=tool_name,
                symbol=payload.symbol,
                rationale=payload.rationale,
                intent_ref=payload.intent_ref,
                sizing_ref=payload.sizing_ref if isinstance(payload, OrderCommandInput) else None,
                command_id=payload.command_id,
                idempotency_key=payload.idempotency_key,
            )
            return write.model_dump(), "deduplicated" if write.deduplicated else "pending_fsm"
        if tool_name == "EMIT_SOS":
            assert isinstance(payload, SOSEventInput)
            if payload.symbol:
                self.store.validate_configured_symbol_scope(payload.agent_id, payload.agent_number, payload.symbol)
            write = self.store.append_evidence(
                session_id=payload.session_id,
                event_type="SOS_EMITTED",
                category="risk",
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                idempotency_key=payload.idempotency_key,
                source_refs=payload.source_refs,
                payload={
                    "reason": payload.reason,
                    "symbol": payload.symbol.upper() if payload.symbol else None,
                    "source_refs": [item.model_dump() for item in payload.source_refs],
                },
                critical=True,
            )
            return write.model_dump(), "pending_fsm"
        if tool_name == "ACK_INSTRUCTIONS":
            assert isinstance(payload, InstructionAckInput)
            write = self.store.ack_instructions(
                session_id=payload.session_id,
                agent_id=payload.agent_id,
                agent_number=payload.agent_number,
                manifest_version=payload.manifest_version,
                idempotency_key=payload.idempotency_key,
            )
            return write.model_dump(), "acknowledged"
        raise ValueError(f"unhandled registered tool: {tool_name}")
