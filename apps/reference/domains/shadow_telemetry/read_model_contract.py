"""Versioned, bounded contracts for read-only Cockpit runtime projections."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


FreshnessState = Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadModelCommon(FrozenModel):
    schema_version: Literal["p46.read-model.v1"]
    runtime_id: str = Field(..., min_length=1)
    environment: Literal["binance_futures_testnet"]
    generated_at: datetime
    config_version: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    data_version: str = Field(..., min_length=1)
    source_timestamp: Optional[datetime]
    freshness_state: FreshnessState
    source_references: tuple[str, ...]


class TradingSessionProjection(FrozenModel):
    session_id: str
    state: str
    created_at: datetime
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    instrument_universe: tuple[str, ...]
    session_version: str


class ParticipantProjection(FrozenModel):
    participant_id: str
    agent_id: str
    participant_role: str
    state: Literal["ENABLED", "DISABLED"]
    instruction_version: str
    owned_symbols: tuple[str, ...]
    capabilities: tuple[str, ...]
    last_seen_at: Optional[datetime]


class SymbolLeaseProjection(FrozenModel):
    lease_id: str
    symbol: str
    owner_participant_id: str
    lease_state: Literal["ACTIVE", "EXPIRED", "RELEASED"]
    lease_version: int
    acquired_at: datetime
    expires_at: datetime


class ContextItemProjection(FrozenModel):
    item_id: str
    kind: str
    summary: str = Field(..., max_length=240)
    created_at: datetime
    source_references: tuple[str, ...]


class ContextProjection(FrozenModel):
    manifest_version: str
    previous_manifest_version: Optional[str]
    content_hash: str
    instruction_version: str
    created_at: datetime
    stale_after: datetime
    freshness_state: FreshnessState
    critical_items: tuple[ContextItemProjection, ...]
    unresolved_items: tuple[ContextItemProjection, ...]
    checkpoint_identity: Optional[str]
    carryover_identity: Optional[str]
    source_references: tuple[str, ...]


class LifecycleItemProjection(FrozenModel):
    item_id: str
    symbol: Optional[str]
    state: str
    side: Optional[str] = None
    quantity: Optional[str] = None
    updated_at: datetime
    source_reference: str


class LifecycleProjection(FrozenModel):
    positions: tuple[LifecycleItemProjection, ...]
    open_orders: tuple[LifecycleItemProjection, ...]
    pending_intents: tuple[LifecycleItemProjection, ...]
    pending_commands: tuple[LifecycleItemProjection, ...]
    latest_fsm_decisions: tuple[LifecycleItemProjection, ...]
    reconciliation_state: str
    reconciliation_divergence: bool
    last_reconciled_at: Optional[datetime]
    freshness_state: FreshnessState
    source_kind: str


class PhenixRuntimeReadModel(ReadModelCommon):
    session: TradingSessionProjection
    participants: tuple[ParticipantProjection, ...]
    leases: tuple[SymbolLeaseProjection, ...]
    context: ContextProjection
    lifecycle: LifecycleProjection


class ReadModelHealth(FrozenModel):
    schema_version: Literal["p46.read-model.v1"]
    runtime_id: str
    environment: Literal["binance_futures_testnet"]
    generated_at: datetime
    configured: bool
    authority_available: bool
    source_references: tuple[str, ...]


class ContextSourceSnapshot(FrozenModel):
    manifest_version: str
    previous_manifest_version: Optional[str] = None
    content_hash: str
    instruction_version: str
    created_at: datetime
    stale_after: datetime
    critical_items: tuple[ContextItemProjection, ...] = ()
    unresolved_items: tuple[ContextItemProjection, ...] = ()
    checkpoint_identity: Optional[str] = None
    carryover_identity: Optional[str] = None
    source_references: tuple[str, ...]


class LifecycleSourceSnapshot(FrozenModel):
    positions: tuple[LifecycleItemProjection, ...] = ()
    open_orders: tuple[LifecycleItemProjection, ...] = ()
    pending_intents: tuple[LifecycleItemProjection, ...] = ()
    pending_commands: tuple[LifecycleItemProjection, ...] = ()
    latest_fsm_decisions: tuple[LifecycleItemProjection, ...] = ()
    reconciliation_state: str
    reconciliation_divergence: bool
    last_reconciled_at: Optional[datetime]
    source_kind: str
    source_references: tuple[str, ...]

    @field_validator("source_references")
    @classmethod
    def sources_required(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("lifecycle source references are required")
        return value
