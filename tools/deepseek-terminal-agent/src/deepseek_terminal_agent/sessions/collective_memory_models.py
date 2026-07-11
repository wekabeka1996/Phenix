"""Typed contracts for the P41X collective-memory coordination kernel."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TokenCountKind = Literal["real", "estimate"]
CommandDispatchState = Literal[
    "not_dispatched",
    "dispatch_started",
    "fsm_accepted",
    "fsm_rejected",
    "resolved",
]


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    sequence: Optional[int] = Field(default=None, ge=1)
    event_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


CanonicalMemoryKind = Literal["decision", "reflection", "instruction_ack"]


class CanonicalMemoryRecord(BaseModel):
    """Immutable agent/session memory record written by the canonical kernel."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    sequence: int = Field(..., ge=1)
    kind: CanonicalMemoryKind
    created_at: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    instruction_version: str = Field(..., min_length=1)
    event_ids: list[str] = Field(default_factory=list)
    command_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)

    @field_validator("event_ids", "command_ids")
    @classmethod
    def references_are_non_empty_and_unique(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("references must be non-empty")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("references must be unique")
        return cleaned


class CanonicalMemorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    record_count: int = Field(..., ge=0)
    first_sequence: Optional[int] = Field(default=None, ge=1)
    last_sequence: Optional[int] = Field(default=None, ge=1)
    record_ids: list[str] = Field(default_factory=list)
    instruction_versions: dict[str, str] = Field(default_factory=dict)
    event_ids: list[str] = Field(default_factory=list)
    command_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)


class ArenaEvidenceEvent(BaseModel):
    """Immutable evidence row. Sequence is assigned under the session lock."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    event_type: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    agent_id: Optional[str] = None
    agent_number: Optional[int] = Field(default=None, ge=1)
    command_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    critical: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity_is_complete(self) -> "ArenaEvidenceEvent":
        if (self.agent_id is None) != (self.agent_number is None):
            raise ValueError("agent_id and agent_number must be supplied together")
        return self


class AgentHeartbeatState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    heartbeat_at: str
    expires_at: str
    last_sequence: int = Field(..., ge=1)


class SymbolLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    issued_at: str
    renewed_at: str
    expires_at: str
    source_event_id: str = Field(..., min_length=1)


class PublicationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    kind: Literal[
        "market_regime",
        "feature_trust",
        "peer_observation",
        "risk_warning",
        "unresolved_question",
        "active_hypothesis",
    ]
    symbol: Optional[str] = None
    summary: str = Field(..., min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class PeerPublicationAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    cursor_sequence: int = Field(..., ge=0)
    acknowledged_at: str = Field(default_factory=utc_now_iso)
    source_event_id: str = Field(..., min_length=1)


class FeatureTrustUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class FeatureTrustState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1)
    agent_id: Optional[str] = None
    version: int = Field(..., ge=1)
    current_trust: float = Field(..., ge=0.0, le=1.0)
    history: list[FeatureTrustUpdate] = Field(default_factory=list)


class InstructionVersionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    manifest_version: str = Field(..., min_length=1)
    acknowledged_at: str
    source_event_id: str = Field(..., min_length=1)


class PortfolioState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_margin_usage: float = Field(..., ge=0.0)
    total_directional_exposure: float
    correlated_exposure: float = Field(..., ge=0.0)
    active_positions: list[dict[str, Any]] = Field(default_factory=list)
    active_orders: list[dict[str, Any]] = Field(default_factory=list)
    global_drawdown_pct: float = Field(..., ge=0.0)
    risk_budget_available: float = Field(..., ge=0.0)
    emergency_stop: bool
    reconciled_at: str
    source_refs: list[SourceReference] = Field(default_factory=list)


class PendingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    command_kind: Literal["REQUEST_ORDER", "REQUEST_CANCEL", "REQUEST_CLOSE"]
    symbol: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    intent_ref: str = Field(..., min_length=1)
    sizing_ref: Optional[str] = None
    idempotency_key: str = Field(..., min_length=1)
    created_at: str
    status: Literal["pending_fsm", "accepted_by_fsm", "rejected_by_fsm", "resolved"]
    dispatch_state: CommandDispatchState = "not_dispatched"
    dispatch_started_at: Optional[str] = None
    resolution_refs: list[SourceReference] = Field(default_factory=list)


class AgentPrivateReflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reflection_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    kind: Literal["reasoning_summary", "hypothesis", "feature_trust", "reflection"]
    summary: str = Field(..., min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class AgentPrivateCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    reflection_count: int = Field(..., ge=0)
    summary: str
    source_refs: list[SourceReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class CompressionStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_event_count: int = Field(..., ge=0)
    raw_tokens: int = Field(..., ge=0)
    active_context_tokens: int = Field(..., ge=0)
    token_count_kind: TokenCountKind
    checkpoint_bytes: int = Field(..., ge=0)
    compression_ratio: float = Field(..., ge=0.0)
    critical_event_count: int = Field(..., ge=0)
    source_reference_count: int = Field(..., ge=0)


class CollectiveStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    session_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=0)
    last_sequence: int = Field(..., ge=0)
    updated_at: str = Field(default_factory=utc_now_iso)
    active_agents: list[str] = Field(default_factory=list)
    heartbeats: dict[str, AgentHeartbeatState] = Field(default_factory=dict)
    symbol_leases: dict[str, SymbolLease] = Field(default_factory=dict)
    publications: list[PublicationRecord] = Field(default_factory=list)
    publication_cursors: dict[str, PeerPublicationAck] = Field(default_factory=dict)
    portfolio: Optional[PortfolioState] = None
    risk_warnings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    active_hypotheses: list[str] = Field(default_factory=list)
    feature_trust_states: dict[str, FeatureTrustState] = Field(default_factory=dict)
    instruction_versions: dict[str, InstructionVersionState] = Field(default_factory=dict)
    pending_commands: dict[str, PendingCommand] = Field(default_factory=dict)
    processed_idempotency_keys: dict[str, str] = Field(default_factory=dict)
    last_checkpoint_id: Optional[str] = None
    recovery_state: str = "not_recovered"
    compression_statistics: Optional[CompressionStatistics] = None


class MemorySegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(..., min_length=1)
    start_sequence: int = Field(..., ge=1)
    end_sequence: int = Field(..., ge=1)
    event_count: int = Field(..., ge=1)
    summary: str
    source_refs: list[SourceReference]
    critical_events: list[ArenaEvidenceEvent] = Field(default_factory=list)
    omitted_categories: list[str] = Field(default_factory=list)
    token_count: int = Field(..., ge=0)
    token_count_kind: TokenCountKind


class CompressionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    start_sequence: int = Field(..., ge=0)
    end_sequence: int = Field(..., ge=0)
    raw_event_count: int = Field(..., ge=0)
    raw_tokens: int = Field(..., ge=0)
    active_context_tokens: int = Field(..., ge=0)
    token_count_kind: TokenCountKind
    source_references: list[SourceReference] = Field(default_factory=list)
    critical_event_ids: list[str] = Field(default_factory=list)
    omitted_categories: list[str] = Field(default_factory=list)
    deterministic_hash: str = Field(..., min_length=1)


class CarryoverBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    checkpoint_id: str = Field(..., min_length=1)
    collective_state_version: int = Field(..., ge=0)
    agent_private_checkpoint_ids: dict[str, str] = Field(default_factory=dict)
    instruction_versions: dict[str, str] = Field(default_factory=dict)
    pending_command_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class MemoryCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    snapshot: CollectiveStateSnapshot
    segments: list[MemorySegment] = Field(default_factory=list)
    manifest: CompressionManifest
    carryover: CarryoverBundle


class RecoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    checkpoint_id: Optional[str]
    checkpoint_sequence: int = Field(..., ge=0)
    replayed_event_count: int = Field(..., ge=0)
    recovered_state_version: int = Field(..., ge=0)
    instruction_versions_restored: dict[str, str] = Field(default_factory=dict)
    valid_symbol_leases: list[str] = Field(default_factory=list)
    expired_symbol_leases: list[str] = Field(default_factory=list)
    pending_command_ids: list[str] = Field(default_factory=list)
    dispatch_in_doubt_command_ids: list[str] = Field(default_factory=list)
    exchange_reconciliation_status: str
    duplicate_submit_prevention_active: bool
    ready: bool
    created_at: str = Field(default_factory=utc_now_iso)


class WriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: ArenaEvidenceEvent
    state: CollectiveStateSnapshot
    deduplicated: bool = False

