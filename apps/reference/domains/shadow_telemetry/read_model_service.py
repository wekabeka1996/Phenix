"""Pure read-model assembly over explicit canonical runtime authorities."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Protocol

from apps.reference.domains.shadow_telemetry.read_model_contract import (
    ContextProjection,
    ContextSourceSnapshot,
    FreshnessState,
    LifecycleProjection,
    LifecycleSourceSnapshot,
    ParticipantProjection,
    PhenixRuntimeReadModel,
    SymbolLeaseProjection,
    TradingSessionProjection,
)
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    AuthorityStoreError,
    TradingSessionAuthorityStore,
)


class ReadModelUnavailableError(RuntimeError):
    pass


class ContextReader(Protocol):
    def __call__(self, session_id: str) -> ContextSourceSnapshot: ...


class LifecycleReader(Protocol):
    def __call__(self, session_id: str) -> LifecycleSourceSnapshot: ...


def _version(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def _freshness(timestamp: datetime | None, stale_after: datetime | None, now: datetime) -> FreshnessState:
    if timestamp is None:
        return "MISSING"
    if timestamp.tzinfo is None:
        return "UNKNOWN"
    if stale_after is None or stale_after.tzinfo is None:
        return "UNKNOWN"
    return "FRESH" if now < stale_after else "STALE"


class PhenixReadModelService:
    def __init__(
        self,
        *,
        authority: TradingSessionAuthorityStore,
        context_reader: ContextReader,
        lifecycle_reader: LifecycleReader,
        policy: object,
        clock: Callable[[], datetime],
    ) -> None:
        if any(value is None for value in (authority, context_reader, lifecycle_reader, policy, clock)):
            raise ValueError("read-model authorities, policy, and clock are explicit")
        self.authority = authority
        self.context_reader = context_reader
        self.lifecycle_reader = lifecycle_reader
        self.policy = policy
        self.clock = clock

    def snapshot(self, session_id: str) -> PhenixRuntimeReadModel:
        now = self.clock()
        if now.tzinfo is None:
            raise ReadModelUnavailableError("READ_MODEL_CLOCK_NOT_TIMEZONE_AWARE")
        try:
            session = self.authority.read_session(session_id)
            participants = self.authority.participants_for_session(session_id)
            leases = self.authority.leases_for_session(session_id)
        except AuthorityStoreError as exc:
            raise ReadModelUnavailableError(exc.reason) from exc
        context_source = self.context_reader(session_id)
        lifecycle_source = self.lifecycle_reader(session_id)
        max_items = int(self.policy.max_items_per_section)

        lease_views = tuple(SymbolLeaseProjection(
            lease_id=lease.lease_id,
            symbol=lease.symbol,
            owner_participant_id=lease.owner_participant_id,
            lease_state="RELEASED" if released else ("EXPIRED" if lease.expires_at <= now else "ACTIVE"),
            lease_version=lease.version,
            acquired_at=lease.acquired_at,
            expires_at=lease.expires_at,
        ) for lease, released in leases[:max_items])
        active_symbols: dict[str, list[str]] = {}
        for lease in lease_views:
            if lease.lease_state == "ACTIVE":
                active_symbols.setdefault(lease.owner_participant_id, []).append(lease.symbol)
        participant_views = tuple(ParticipantProjection(
            participant_id=item.participant_id,
            agent_id=item.agent_id,
            participant_role=item.participant_type,
            state="ENABLED" if item.enabled else "DISABLED",
            instruction_version=session.instruction_version,
            owned_symbols=tuple(sorted(active_symbols.get(item.participant_id, []))),
            capabilities=("READ", "EXECUTION_ELIGIBLE") if item.participant_type == "MAIN_AGENT" and item.enabled else ("READ",),
            last_seen_at=None,
        ) for item in participants[:max_items])
        context_freshness = _freshness(context_source.created_at, context_source.stale_after, now)
        lifecycle_stale_after = None
        if lifecycle_source.last_reconciled_at is not None:
            from datetime import timedelta
            lifecycle_stale_after = lifecycle_source.last_reconciled_at + timedelta(seconds=int(self.policy.lifecycle_stale_after_sec))
        lifecycle_freshness = _freshness(lifecycle_source.last_reconciled_at, lifecycle_stale_after, now)
        context = ContextProjection(
            **context_source.model_dump(exclude={"critical_items", "unresolved_items"}),
            freshness_state=context_freshness,
            critical_items=context_source.critical_items[:max_items],
            unresolved_items=context_source.unresolved_items[:max_items],
        )
        lifecycle = LifecycleProjection(
            positions=tuple(sorted(lifecycle_source.positions, key=lambda x: (x.symbol or "", x.item_id)))[:max_items],
            open_orders=tuple(sorted(lifecycle_source.open_orders, key=lambda x: (x.symbol or "", x.item_id)))[:max_items],
            pending_intents=tuple(sorted(lifecycle_source.pending_intents, key=lambda x: x.item_id))[:max_items],
            pending_commands=tuple(sorted(lifecycle_source.pending_commands, key=lambda x: x.item_id))[:max_items],
            latest_fsm_decisions=tuple(sorted(lifecycle_source.latest_fsm_decisions, key=lambda x: (x.updated_at, x.item_id), reverse=True))[:max_items],
            reconciliation_state=lifecycle_source.reconciliation_state,
            reconciliation_divergence=lifecycle_source.reconciliation_divergence,
            last_reconciled_at=lifecycle_source.last_reconciled_at,
            freshness_state=lifecycle_freshness,
            source_kind=lifecycle_source.source_kind,
        )
        session_payload = session.model_dump(mode="json")
        session_version = _version("session", session_payload)
        session_view = TradingSessionProjection(
            session_id=session.session_id,
            state=session.status,
            created_at=session.created_at,
            started_at=session.started_at,
            stopped_at=session.expires_at if session.status in {"CLOSED", "EXPIRED"} else None,
            instrument_universe=tuple(session.instrument_universe),
            session_version=session_version,
        )
        sources = tuple(sorted(set((
            f"phenix://authority/session/{session_id}",
            *context.source_references,
            *lifecycle_source.source_references,
        ))))
        component_states = [context_freshness, lifecycle_freshness]
        aggregate_freshness: FreshnessState = "STALE" if "STALE" in component_states else ("MISSING" if "MISSING" in component_states else ("UNKNOWN" if "UNKNOWN" in component_states else "FRESH"))
        source_times = [value for value in (context.created_at, lifecycle.last_reconciled_at) if value is not None]
        body = {
            "session": session_view.model_dump(mode="json"),
            "participants": [item.model_dump(mode="json") for item in participant_views],
            "leases": [item.model_dump(mode="json") for item in lease_views],
            "context": context.model_dump(mode="json"),
            "lifecycle": lifecycle.model_dump(mode="json"),
        }
        return PhenixRuntimeReadModel(
            schema_version=self.policy.schema_version,
            runtime_id=self.policy.runtime_id,
            environment=self.policy.environment,
            generated_at=now,
            config_version=session.config_version,
            session_id=session.session_id,
            data_version=_version("read-model", body),
            source_timestamp=max(source_times) if source_times else None,
            freshness_state=aggregate_freshness,
            source_references=sources,
            **body,
        )
