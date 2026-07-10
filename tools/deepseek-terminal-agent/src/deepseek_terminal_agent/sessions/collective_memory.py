"""Concurrent, append-only collective and private memory coordination kernel."""
from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional
from uuid import uuid4

from ..config import Settings
from .collective_memory_models import (
    AgentHeartbeatState,
    AgentPrivateCheckpoint,
    AgentPrivateReflection,
    ArenaEvidenceEvent,
    CarryoverBundle,
    CollectiveStateSnapshot,
    CommandDispatchResult,
    CompressionManifest,
    CompressionStatistics,
    FeatureTrustState,
    FeatureTrustUpdate,
    FSMDispatchResult,
    InstructionVersionState,
    MemoryCheckpoint,
    MemorySegment,
    PeerPublicationAck,
    PendingCommand,
    PortfolioState,
    PublicationRecord,
    RecoveryReport,
    SourceReference,
    SymbolLease,
    WriteResult,
    utc_now_iso,
)
from .coordination_config import CoordinationConfig, load_coordination_config
from .persistence import append_jsonl_record, read_jsonl_records, write_json_atomic
from .store import SessionStore


class StaleCollectiveStateError(ValueError):
    pass


class SymbolAuthorityError(ValueError):
    pass


class PrivateMemoryAccessError(ValueError):
    pass


class CoordinationLockTimeout(RuntimeError):
    pass


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _as_utc(value: Optional[datetime]) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    return resolved if resolved.tzinfo is not None else resolved.replace(tzinfo=timezone.utc)


class CollectiveMemoryStore:
    """Owns the P41X evidence ledger and derived coordination state.

    The JSONL evidence ledger is authoritative and never compacted in place.
    The JSON state and checkpoints are rebuildable read models.
    """

    EVENTS_NAME = "arena_evidence.jsonl"
    STATE_NAME = "collective_state.json"
    PRIVATE_REFLECTIONS_NAME = "private_reflections.jsonl"

    def __init__(
        self,
        settings: Settings,
        *,
        root_dir: str | Path = ".",
        config: Optional[CoordinationConfig] = None,
        session_store: Optional[SessionStore] = None,
    ) -> None:
        self.settings = settings
        self.config = config or load_coordination_config()
        self.root_dir = Path(root_dir)
        self.sessions_root = self.root_dir / settings.sessions.root_dir
        self.session_store = session_store or SessionStore(settings, root_dir=root_dir)
        self.quarantine_root = self.root_dir / ".agent_memory" / "quarantine"

    def discover_sessions(self) -> list[str]:
        discovered: list[str] = []
        if not self.sessions_root.exists():
            return discovered
        for child in self.sessions_root.iterdir():
            if child.is_dir() and (child / "coordination" / self.EVENTS_NAME).exists():
                discovered.append(child.name)
        return sorted(discovered)

    def initialize_session(
        self,
        session_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> CollectiveStateSnapshot:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            state_path = self._state_path(session_id)
            if state_path.exists():
                return self._load_consistent_state_locked(session_id)
            return self._initialize_locked(session_id, _as_utc(now))

    def get_state(self, session_id: str) -> CollectiveStateSnapshot:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            if not self._state_path(session_id).exists():
                return self._initialize_locked(session_id, datetime.now(timezone.utc))
            return self._load_consistent_state_locked(session_id)

    def list_events(self, session_id: str) -> list[ArenaEvidenceEvent]:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            events = self._read_events_locked(session_id)
            self._validate_sequence(events)
            return events

    def append_evidence(
        self,
        *,
        session_id: str,
        event_type: str,
        category: str,
        payload: Optional[dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        agent_number: Optional[int] = None,
        command_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        expected_version: Optional[int] = None,
        source_refs: Optional[list[SourceReference]] = None,
        event_id: Optional[str] = None,
        created_at: Optional[str] = None,
        critical: Optional[bool] = None,
    ) -> WriteResult:
        self._validate_session(session_id)
        if agent_id is not None:
            self._validate_agent(agent_id, agent_number)
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            return self._commit_event_locked(
                state=state,
                event_type=event_type,
                category=category,
                payload=payload or {},
                agent_id=agent_id,
                agent_number=agent_number,
                command_id=command_id,
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                source_refs=source_refs or [],
                event_id=event_id,
                created_at=created_at,
                critical=critical,
            )

    def record_heartbeat(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        idempotency_key: str,
        now: Optional[datetime] = None,
    ) -> WriteResult:
        resolved = _as_utc(now)
        expires = resolved + timedelta(seconds=self.config.symbol_leases.heartbeat_expiry_seconds)
        return self.append_evidence(
            session_id=session_id,
            event_type="AGENT_HEARTBEAT",
            category="agent_lifecycle",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            payload={
                "heartbeat_at": resolved.isoformat(),
                "expires_at": expires.isoformat(),
            },
        )

    def renew_symbol_lease(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        symbol: str,
        idempotency_key: str,
        now: Optional[datetime] = None,
    ) -> WriteResult:
        identity = self._validate_agent(agent_id, agent_number)
        normalized = str(symbol or "").strip().upper()
        if normalized not in identity.symbols:
            raise SymbolAuthorityError(f"{agent_id} does not own {normalized}")
        resolved = _as_utc(now)
        event_id = f"evt-{uuid4().hex}"
        lease = SymbolLease(
            lease_id=f"lease-{session_id}-{normalized}",
            session_id=session_id,
            symbol=normalized,
            agent_id=agent_id,
            agent_number=agent_number,
            issued_at=resolved.isoformat(),
            renewed_at=resolved.isoformat(),
            expires_at=(resolved + timedelta(seconds=self.config.symbol_leases.ttl_seconds)).isoformat(),
            source_event_id=event_id,
        )
        return self.append_evidence(
            session_id=session_id,
            event_type="SYMBOL_LEASE_RENEWED",
            category="authority",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            event_id=event_id,
            payload={"lease": lease.model_dump()},
        )

    def validate_symbol_authority(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        symbol: str,
        now: Optional[datetime] = None,
    ) -> SymbolLease:
        identity = self._validate_agent(agent_id, agent_number)
        normalized = str(symbol or "").strip().upper()
        if normalized not in identity.symbols:
            raise SymbolAuthorityError(f"wrong-symbol request: {agent_id} does not own {normalized}")
        state = self.get_state(session_id)
        return self._validate_symbol_authority_in_state(
            state=state,
            agent_id=agent_id,
            symbol=normalized,
            now=_as_utc(now),
        )

    def _validate_symbol_authority_in_state(
        self,
        *,
        state: CollectiveStateSnapshot,
        agent_id: str,
        symbol: str,
        now: datetime,
    ) -> SymbolLease:
        lease = state.symbol_leases.get(symbol)
        if lease is None or lease.agent_id != agent_id:
            raise SymbolAuthorityError(f"no active symbol lease for {agent_id}/{symbol}")
        if _parse_time(lease.expires_at) <= now:
            raise SymbolAuthorityError(f"symbol lease expired for {agent_id}/{symbol}")
        if state.portfolio is not None and state.portfolio.emergency_stop:
            raise SymbolAuthorityError("portfolio emergency stop is active")
        return lease

    def heartbeat_status(
        self,
        session_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> dict[str, dict[str, Any]]:
        state = self.get_state(session_id)
        resolved = _as_utc(now)
        status: dict[str, dict[str, Any]] = {}
        for identity in self.config.agents:
            heartbeat = state.heartbeats.get(identity.agent_id)
            fresh = heartbeat is not None and _parse_time(heartbeat.expires_at) > resolved
            status[identity.agent_id] = {
                "agent_number": identity.agent_number,
                "interface": identity.interface,
                "symbols": identity.symbols,
                "fresh": fresh,
                "heartbeat_at": heartbeat.heartbeat_at if heartbeat else None,
                "expires_at": heartbeat.expires_at if heartbeat else None,
            }
        return status

    def publish_observation(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        kind: str,
        summary: str,
        symbol: Optional[str],
        source_refs: list[SourceReference],
        idempotency_key: str,
        expected_version: Optional[int] = None,
    ) -> WriteResult:
        allowed_kinds = {
            "market_regime",
            "feature_trust",
            "peer_observation",
            "unresolved_question",
            "active_hypothesis",
        }
        if kind not in allowed_kinds:
            raise ValueError(f"unsupported publication kind: {kind}")
        if symbol:
            self.validate_configured_symbol_scope(agent_id, agent_number, symbol)
        event_id = f"evt-{uuid4().hex}"
        return self.append_evidence(
            session_id=session_id,
            event_type="PUBLICATION_CREATED",
            category="collective_memory",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            event_id=event_id,
            source_refs=source_refs,
            payload={
                "publication_id": f"pub-{uuid4().hex}",
                "kind": kind,
                "summary": str(summary or "")[: self.config.memory.max_summary_chars],
                "symbol": str(symbol).upper() if symbol else None,
                "source_refs": [item.model_dump() for item in source_refs],
            },
        )

    def publish_risk_warning(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        summary: str,
        symbol: Optional[str],
        source_refs: list[SourceReference],
        idempotency_key: str,
        expected_version: Optional[int] = None,
    ) -> WriteResult:
        if symbol:
            self.validate_configured_symbol_scope(agent_id, agent_number, symbol)
        event_id = f"evt-{uuid4().hex}"
        return self.append_evidence(
            session_id=session_id,
            event_type="RISK_WARNING_PUBLISHED",
            category="risk",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            event_id=event_id,
            source_refs=source_refs,
            payload={
                "publication_id": f"risk-{uuid4().hex}",
                "kind": "risk_warning",
                "summary": str(summary or "")[: self.config.memory.max_summary_chars],
                "symbol": str(symbol).upper() if symbol else None,
                "source_refs": [item.model_dump() for item in source_refs],
            },
        )

    def get_peer_publications(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        cursor_sequence: Optional[int] = None,
    ) -> list[PublicationRecord]:
        self._validate_agent(agent_id, agent_number)
        state = self.get_state(session_id)
        stored = state.publication_cursors.get(agent_id)
        cursor = cursor_sequence if cursor_sequence is not None else (stored.cursor_sequence if stored else 0)
        return [
            publication
            for publication in state.publications
            if publication.agent_id != agent_id and publication.sequence > cursor
        ]

    def ack_peer_publications(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        cursor_sequence: int,
        idempotency_key: str,
    ) -> WriteResult:
        self._validate_agent(agent_id, agent_number)
        state = self.get_state(session_id)
        if cursor_sequence < 0 or cursor_sequence > state.last_sequence:
            raise ValueError("publication cursor must reference an observed sequence")
        event_id = f"evt-{uuid4().hex}"
        return self.append_evidence(
            session_id=session_id,
            event_type="PEER_PUBLICATION_ACKED",
            category="coordination",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            event_id=event_id,
            payload={
                "cursor_sequence": cursor_sequence,
                "acknowledged_at": utc_now_iso(),
                "source_event_id": event_id,
            },
        )

    def write_private_reflection(
        self,
        *,
        session_id: str,
        actor_agent_id: str,
        actor_agent_number: int,
        target_agent_id: str,
        kind: str,
        summary: str,
        source_refs: list[SourceReference],
        idempotency_key: str,
    ) -> AgentPrivateReflection:
        self._validate_session(session_id)
        self._validate_agent(actor_agent_id, actor_agent_number)
        if actor_agent_id != target_agent_id:
            raise PrivateMemoryAccessError("peer agents cannot modify another agent's private memory")
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            existing_event_id = state.processed_idempotency_keys.get(idempotency_key)
            if existing_event_id:
                event = self._event_by_id_locked(session_id, existing_event_id)
                reflection_id = str(event.payload["reflection_id"])
                return self._private_reflection_by_id_locked(session_id, target_agent_id, reflection_id)
            reflections = self._read_private_reflections_locked(session_id, target_agent_id)
            if len(reflections) >= self.config.memory.max_private_reflections:
                raise ValueError("private reflection limit reached; checkpoint required")
            reflection = AgentPrivateReflection(
                reflection_id=f"private-{uuid4().hex}",
                session_id=session_id,
                agent_id=target_agent_id,
                agent_number=actor_agent_number,
                kind=kind,
                summary=str(summary or "")[: self.config.memory.max_summary_chars],
                source_refs=source_refs,
            )
            append_jsonl_record(self._private_reflections_path(session_id, target_agent_id), reflection.model_dump())
            self._commit_event_locked(
                state=state,
                event_type="PRIVATE_REFLECTION_WRITTEN",
                category="private_memory_index",
                payload={
                    "reflection_id": reflection.reflection_id,
                    "target_agent_id": target_agent_id,
                    "source_refs": [item.model_dump() for item in source_refs],
                },
                agent_id=actor_agent_id,
                agent_number=actor_agent_number,
                idempotency_key=idempotency_key,
                source_refs=source_refs,
            )
            return reflection

    def read_private_reflections(
        self,
        *,
        session_id: str,
        actor_agent_id: str,
        actor_agent_number: int,
        target_agent_id: str,
    ) -> list[AgentPrivateReflection]:
        self._validate_session(session_id)
        self._validate_agent(actor_agent_id, actor_agent_number)
        if actor_agent_id != target_agent_id:
            raise PrivateMemoryAccessError("peer agents cannot read another agent's private memory")
        with self._session_lock(session_id):
            return self._read_private_reflections_locked(session_id, target_agent_id)

    def update_feature_trust(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        feature_name: str,
        trust: float,
        reason: str,
        source_refs: list[SourceReference],
        idempotency_key: str,
        expected_version: Optional[int] = None,
    ) -> WriteResult:
        self._validate_session(session_id)
        self._validate_agent(agent_id, agent_number)
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            key = f"{agent_id}:{feature_name}"
            current = state.feature_trust_states.get(key)
            history = list(current.history) if current else []
            history.append(FeatureTrustUpdate(trust=trust, reason=reason, source_refs=source_refs))
            feature_state = FeatureTrustState(
                feature_name=feature_name,
                agent_id=agent_id,
                version=(current.version + 1) if current else 1,
                current_trust=trust,
                history=history,
            )
            return self._commit_event_locked(
                state=state,
                event_type="FEATURE_TRUST_UPDATED",
                category="feature_trust",
                agent_id=agent_id,
                agent_number=agent_number,
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                source_refs=source_refs,
                payload={"key": key, "feature_trust_state": feature_state.model_dump()},
            )

    def ack_instructions(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        manifest_version: str,
        idempotency_key: str,
        acknowledged_at: Optional[str] = None,
    ) -> WriteResult:
        event_id = f"evt-{uuid4().hex}"
        instruction = InstructionVersionState(
            agent_id=agent_id,
            agent_number=agent_number,
            manifest_version=manifest_version,
            acknowledged_at=acknowledged_at or utc_now_iso(),
            source_event_id=event_id,
        )
        return self.append_evidence(
            session_id=session_id,
            event_type="INSTRUCTIONS_ACKED",
            category="instructions",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            event_id=event_id,
            payload={"instruction": instruction.model_dump()},
        )

    def reconcile_portfolio(
        self,
        *,
        session_id: str,
        portfolio: PortfolioState,
        idempotency_key: str,
        source_refs: list[SourceReference],
        expected_version: Optional[int] = None,
    ) -> WriteResult:
        limits = self.config.portfolio_limits
        breaches: list[str] = []
        if portfolio.total_margin_usage > limits.max_total_margin_usage:
            breaches.append("total_margin_usage")
        if abs(portfolio.total_directional_exposure) > limits.max_total_directional_exposure:
            breaches.append("total_directional_exposure")
        if portfolio.correlated_exposure > limits.max_correlated_exposure:
            breaches.append("correlated_exposure")
        if portfolio.global_drawdown_pct > limits.max_global_drawdown_pct:
            breaches.append("global_drawdown")
        if breaches and limits.emergency_stop_fails_closed:
            portfolio = portfolio.model_copy(update={"emergency_stop": True})
        return self.append_evidence(
            session_id=session_id,
            event_type="PORTFOLIO_RECONCILED",
            category="portfolio",
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            source_refs=source_refs,
            payload={"portfolio": portfolio.model_dump(), "limit_breaches": breaches},
            critical=bool(breaches),
        )

    def request_command(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        command_kind: str,
        symbol: str,
        rationale: str,
        intent_ref: str,
        idempotency_key: str,
        command_id: Optional[str] = None,
        sizing_ref: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> WriteResult:
        normalized_kind = str(command_kind).strip().upper()
        if normalized_kind not in {"REQUEST_ORDER", "REQUEST_CANCEL", "REQUEST_CLOSE"}:
            raise ValueError(f"unsupported command kind: {command_kind}")
        if normalized_kind == "REQUEST_ORDER" and not str(sizing_ref or "").strip():
            raise ValueError("REQUEST_ORDER requires an explicit YAML/Pydantic sizing_ref")
        self._validate_session(session_id)
        identity = self._validate_agent(agent_id, agent_number)
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_symbol not in identity.symbols:
            raise SymbolAuthorityError(
                f"wrong-symbol request: {agent_id} does not own {normalized_symbol}"
            )
        resolved_now = _as_utc(now)
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            lease = self._validate_symbol_authority_in_state(
                state=state,
                agent_id=agent_id,
                symbol=normalized_symbol,
                now=resolved_now,
            )
            resolved_command_id = command_id or f"cmd-{uuid4().hex}"
            event_id = f"evt-{uuid4().hex}"
            command = PendingCommand(
                command_id=resolved_command_id,
                event_id=event_id,
                session_id=session_id,
                agent_id=agent_id,
                agent_number=agent_number,
                command_kind=normalized_kind,
                symbol=lease.symbol,
                rationale=rationale,
                intent_ref=intent_ref,
                sizing_ref=sizing_ref,
                idempotency_key=idempotency_key,
                created_at=resolved_now.isoformat(),
                status="pending_fsm",
            )
            event_type = {
                "REQUEST_ORDER": "ORDER_REQUESTED",
                "REQUEST_CANCEL": "CANCEL_REQUESTED",
                "REQUEST_CLOSE": "CLOSE_REQUESTED",
            }[normalized_kind]
            return self._commit_event_locked(
                state=state,
                event_type=event_type,
                category="command",
                agent_id=agent_id,
                agent_number=agent_number,
                command_id=resolved_command_id,
                idempotency_key=idempotency_key,
                event_id=event_id,
                payload={
                    "command": command.model_dump(),
                    "environment": self.config.environment,
                    "fsm_execution_owner": True,
                    "raw_exchange_client_exposed": False,
                },
            )

    def dispatch_command_to_fsm(
        self,
        *,
        session_id: str,
        command_id: str,
        fsm_gateway: Callable[[PendingCommand], FSMDispatchResult | dict[str, Any]],
    ) -> CommandDispatchResult:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            command = state.pending_commands.get(command_id)
            if command is None:
                raise KeyError(f"pending command not found: {command_id}")
            if command.dispatch_state != "not_dispatched":
                return CommandDispatchResult(command=command, deduplicated=True)
            self._commit_event_locked(
                state=state,
                event_type="COMMAND_DISPATCH_STARTED",
                category="fsm",
                payload={"command_id": command_id, "started_at": utc_now_iso()},
                agent_id=command.agent_id,
                agent_number=command.agent_number,
                command_id=command_id,
                idempotency_key=f"dispatch-start:{command_id}",
                critical=True,
            )
            command = state.pending_commands[command_id]

        try:
            raw_result = fsm_gateway(command.model_copy(deep=True))
            result = raw_result if isinstance(raw_result, FSMDispatchResult) else FSMDispatchResult.model_validate(raw_result)
        except Exception as exc:
            self.append_evidence(
                session_id=session_id,
                event_type="FSM_DISPATCH_ERROR",
                category="fsm",
                payload={"command_id": command_id, "error_type": type(exc).__name__, "error": str(exc)},
                agent_id=command.agent_id,
                agent_number=command.agent_number,
                command_id=command_id,
                idempotency_key=f"dispatch-error:{command_id}",
                critical=True,
            )
            raise

        write = self.append_evidence(
            session_id=session_id,
            event_type="FSM_DECISION",
            category="fsm",
            payload={
                "command_id": command_id,
                "accepted": result.accepted,
                "reason": result.reason,
                "source_refs": [item.model_dump() for item in result.source_refs],
            },
            agent_id=command.agent_id,
            agent_number=command.agent_number,
            command_id=command_id,
            idempotency_key=f"fsm-decision:{command_id}",
            source_refs=result.source_refs,
            critical=True,
        )
        return CommandDispatchResult(
            command=write.state.pending_commands[command_id],
            fsm_result=result,
            deduplicated=False,
        )

    def create_checkpoint(self, session_id: str) -> MemoryCheckpoint:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            state = self._ensure_state_locked(session_id)
            events = self._read_events_locked(session_id)
            self._validate_sequence(events)
            refs = [self._source_ref(event) for event in events]
            canonical_ids = "|".join(f"{event.sequence}:{event.event_id}" for event in events)
            deterministic_hash = hashlib.sha256(canonical_ids.encode("utf-8")).hexdigest()
            checkpoint_id = f"checkpoint-{deterministic_hash[:20]}"
            raw_text = self._canonical_json([event.model_dump() for event in events])
            raw_tokens, token_kind = self._count_tokens(raw_text)
            segments = self._build_segments(events)
            active_payload = self._active_context_payload(
                state=state,
                segments=segments,
                checkpoint_id=checkpoint_id,
            )
            active_tokens, active_kind = self._count_tokens(self._canonical_json(active_payload))
            if token_kind != active_kind:
                token_kind = "estimate"
            omitted = sorted({category for segment in segments for category in segment.omitted_categories})
            manifest = CompressionManifest(
                checkpoint_id=checkpoint_id,
                session_id=session_id,
                start_sequence=events[0].sequence if events else 0,
                end_sequence=events[-1].sequence if events else 0,
                raw_event_count=len(events),
                raw_tokens=raw_tokens,
                active_context_tokens=active_tokens,
                token_count_kind=token_kind,
                source_references=refs,
                critical_event_ids=[event.event_id for event in events if event.critical],
                omitted_categories=omitted,
                deterministic_hash=deterministic_hash,
            )
            private_ids: dict[str, str] = {}
            for identity in self.config.agents:
                private = self._create_private_checkpoint_locked(session_id, identity.agent_id, identity.agent_number, checkpoint_id)
                private_ids[identity.agent_id] = private.checkpoint_id
            carryover = CarryoverBundle(
                bundle_id=f"carryover-{deterministic_hash[:20]}",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                collective_state_version=state.version,
                agent_private_checkpoint_ids=private_ids,
                instruction_versions={key: value.manifest_version for key, value in state.instruction_versions.items()},
                pending_command_ids=sorted(state.pending_commands),
                source_refs=refs,
            )
            checkpoint = MemoryCheckpoint(
                checkpoint_id=checkpoint_id,
                session_id=session_id,
                snapshot=state.model_copy(deep=True),
                segments=segments,
                manifest=manifest,
                carryover=carryover,
            )
            stats = CompressionStatistics(
                raw_event_count=len(events),
                raw_tokens=raw_tokens,
                active_context_tokens=active_tokens,
                token_count_kind=token_kind,
                checkpoint_bytes=0,
                compression_ratio=(active_tokens / raw_tokens) if raw_tokens else 1.0,
                critical_event_count=len(manifest.critical_event_ids),
                source_reference_count=len(refs),
            )
            checkpoint.snapshot.compression_statistics = stats
            checkpoint_path = self._checkpoint_path(session_id, checkpoint_id)
            write_json_atomic(checkpoint_path, checkpoint.model_dump())
            for _ in range(2):
                actual_bytes = checkpoint_path.stat().st_size
                if stats.checkpoint_bytes == actual_bytes:
                    break
                stats.checkpoint_bytes = actual_bytes
                checkpoint.snapshot.compression_statistics = stats
                write_json_atomic(checkpoint_path, checkpoint.model_dump())
            checkpoint_ref = SourceReference(
                source_id=checkpoint_id,
                source_type="compression_manifest",
                sequence=manifest.end_sequence or None,
            )
            self._commit_event_locked(
                state=state,
                event_type="MEMORY_CHECKPOINT_CREATED",
                category="memory_checkpoint",
                payload={
                    "checkpoint_id": checkpoint_id,
                    "manifest_end_sequence": manifest.end_sequence,
                    "compression_statistics": stats.model_dump(),
                },
                idempotency_key=f"checkpoint:{checkpoint_id}",
                source_refs=[checkpoint_ref],
            )
            return checkpoint

    def latest_checkpoint(self, session_id: str) -> Optional[MemoryCheckpoint]:
        self._validate_session(session_id)
        with self._session_lock(session_id):
            return self._latest_checkpoint_locked(session_id)

    def recover_session(
        self,
        session_id: str,
        *,
        now: Optional[datetime] = None,
        exchange_reconciler: Optional[Callable[[list[PendingCommand]], dict[str, Any]]] = None,
    ) -> RecoveryReport:
        self._validate_session(session_id)
        resolved = _as_utc(now)
        with self._session_lock(session_id):
            checkpoint = self._latest_checkpoint_locked(session_id)
            events = self._read_events_locked(session_id)
            self._validate_sequence(events)
            if checkpoint is None:
                state = self._blank_state(session_id)
                checkpoint_sequence = 0
                checkpoint_id = None
            else:
                state = checkpoint.snapshot.model_copy(deep=True)
                checkpoint_sequence = checkpoint.manifest.end_sequence
                checkpoint_id = checkpoint.checkpoint_id
            replay = [event for event in events if event.sequence > checkpoint_sequence]
            for event in replay:
                self._apply_event(state, event)
            state.recovery_state = "replayed"
            write_json_atomic(self._state_path(session_id), state.model_dump())

        valid_leases = sorted(
            symbol for symbol, lease in state.symbol_leases.items() if _parse_time(lease.expires_at) > resolved
        )
        expired_leases = sorted(set(state.symbol_leases).difference(valid_leases))
        if expired_leases and self.config.recovery.reacquire_expired_symbol_leases:
            for symbol in list(expired_leases):
                owner = self.config.owner_for_symbol(symbol)
                self.renew_symbol_lease(
                    session_id=session_id,
                    agent_id=owner.agent_id,
                    agent_number=owner.agent_number,
                    symbol=symbol,
                    idempotency_key=f"recovery-lease:{symbol}:{resolved.isoformat()}",
                    now=resolved,
                )
            state = self.get_state(session_id)
            valid_leases = sorted(
                symbol for symbol, lease in state.symbol_leases.items() if _parse_time(lease.expires_at) > resolved
            )
            expired_leases = sorted(set(state.symbol_leases).difference(valid_leases))
        pending = list(state.pending_commands.values())
        in_doubt = [command for command in pending if command.dispatch_state == "dispatch_started"]
        reconciliation_status = "not_required"
        ready = not expired_leases
        if in_doubt and self.config.recovery.require_exchange_reconciliation_for_dispatch_in_doubt:
            if exchange_reconciler is None:
                reconciliation_status = "required_hook_missing"
                ready = False
            else:
                result = exchange_reconciler([command.model_copy(deep=True) for command in in_doubt])
                reconciliation_status = str(result.get("status") or "completed")
                ready = ready and reconciliation_status in {"completed", "reconciled", "no_external_order"}
        report = RecoveryReport(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            checkpoint_sequence=checkpoint_sequence,
            replayed_event_count=len(replay),
            recovered_state_version=state.version,
            instruction_versions_restored={key: value.manifest_version for key, value in state.instruction_versions.items()},
            valid_symbol_leases=valid_leases,
            expired_symbol_leases=expired_leases,
            pending_command_ids=sorted(state.pending_commands),
            dispatch_in_doubt_command_ids=sorted(command.command_id for command in in_doubt),
            exchange_reconciliation_status=reconciliation_status,
            duplicate_submit_prevention_active=self.config.recovery.duplicate_submit_prevention_required,
            ready=ready,
        )
        self.append_evidence(
            session_id=session_id,
            event_type="RECOVERY_COMPLETED",
            category="recovery",
            payload={"report": report.model_dump()},
            idempotency_key=f"recovery:{report.created_at}",
        )
        return report

    def cockpit_status(self, session_id: str, *, now: Optional[datetime] = None) -> dict[str, Any]:
        state = self.get_state(session_id)
        checkpoint = self.latest_checkpoint(session_id)
        resolved = _as_utc(now)
        leases = []
        for symbol, lease in sorted(state.symbol_leases.items()):
            leases.append({**lease.model_dump(), "fresh": _parse_time(lease.expires_at) > resolved})
        return {
            "session_id": session_id,
            "collective_state_version": state.version,
            "last_event_sequence": state.last_sequence,
            "active_agents": self.heartbeat_status(session_id, now=resolved),
            "symbol_ownership": leases,
            "collective_memory": {
                "publication_count": len(state.publications),
                "risk_warning_count": len(state.risk_warnings),
                "unresolved_question_count": len(state.unresolved_questions),
                "active_hypothesis_count": len(state.active_hypotheses),
            },
            "last_checkpoint": checkpoint.manifest.model_dump() if checkpoint else None,
            "instruction_ack_versions": {
                key: value.model_dump() for key, value in state.instruction_versions.items()
            },
            "peer_publications": [item.model_dump() for item in state.publications[-20:]],
            "portfolio_state": state.portfolio.model_dump() if state.portfolio else None,
            "pending_commands": [item.model_dump() for item in state.pending_commands.values()],
            "recovery_state": state.recovery_state,
            "compression_statistics": (
                state.compression_statistics.model_dump() if state.compression_statistics else None
            ),
        }

    def _initialize_locked(self, session_id: str, now: datetime) -> CollectiveStateSnapshot:
        state = self._blank_state(session_id)
        self._commit_event_locked(
            state=state,
            event_type="SESSION_COORDINATION_INITIALIZED",
            category="session_lifecycle",
            payload={
                "active_agents": [agent.agent_id for agent in self.config.agents],
                "environment": self.config.environment,
            },
            idempotency_key=f"bootstrap:{session_id}",
        )
        for identity in self.config.agents:
            for symbol in identity.symbols:
                event_id = f"evt-{uuid4().hex}"
                lease = SymbolLease(
                    lease_id=f"lease-{session_id}-{symbol}",
                    session_id=session_id,
                    symbol=symbol,
                    agent_id=identity.agent_id,
                    agent_number=identity.agent_number,
                    issued_at=now.isoformat(),
                    renewed_at=now.isoformat(),
                    expires_at=(now + timedelta(seconds=self.config.symbol_leases.ttl_seconds)).isoformat(),
                    source_event_id=event_id,
                )
                self._commit_event_locked(
                    state=state,
                    event_type="SYMBOL_LEASE_RENEWED",
                    category="authority",
                    payload={"lease": lease.model_dump()},
                    agent_id=identity.agent_id,
                    agent_number=identity.agent_number,
                    idempotency_key=f"bootstrap-lease:{identity.agent_id}:{symbol}",
                    event_id=event_id,
                )
        return state.model_copy(deep=True)

    def _blank_state(self, session_id: str) -> CollectiveStateSnapshot:
        return CollectiveStateSnapshot(
            session_id=session_id,
            version=0,
            last_sequence=0,
            active_agents=[agent.agent_id for agent in self.config.agents],
        )

    def _ensure_state_locked(self, session_id: str) -> CollectiveStateSnapshot:
        if not self._state_path(session_id).exists():
            return self._initialize_locked(session_id, datetime.now(timezone.utc))
        return self._load_consistent_state_locked(session_id)

    def _load_consistent_state_locked(self, session_id: str) -> CollectiveStateSnapshot:
        state = CollectiveStateSnapshot.model_validate(
            json.loads(self._state_path(session_id).read_text(encoding="utf-8"))
        )
        events = self._read_events_locked(session_id)
        self._validate_sequence(events)
        for event in events:
            if event.sequence > state.last_sequence:
                self._apply_event(state, event)
        if events and state.last_sequence != events[-1].sequence:
            raise RuntimeError("collective state could not catch up to evidence ledger")
        write_json_atomic(self._state_path(session_id), state.model_dump())
        return state

    def _commit_event_locked(
        self,
        *,
        state: CollectiveStateSnapshot,
        event_type: str,
        category: str,
        payload: dict[str, Any],
        agent_id: Optional[str] = None,
        agent_number: Optional[int] = None,
        command_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        expected_version: Optional[int] = None,
        source_refs: Optional[list[SourceReference]] = None,
        event_id: Optional[str] = None,
        created_at: Optional[str] = None,
        critical: Optional[bool] = None,
    ) -> WriteResult:
        if expected_version is not None and expected_version != state.version:
            raise StaleCollectiveStateError(
                f"stale collective state: expected {expected_version}, current {state.version}"
            )
        if idempotency_key and idempotency_key in state.processed_idempotency_keys:
            existing = self._event_by_id_locked(state.session_id, state.processed_idempotency_keys[idempotency_key])
            return WriteResult(event=existing, state=state.model_copy(deep=True), deduplicated=True)
        if command_id:
            existing_command = state.pending_commands.get(command_id)
            if existing_command is not None and event_type in {"ORDER_REQUESTED", "CANCEL_REQUESTED", "CLOSE_REQUESTED"}:
                existing = self._event_by_id_locked(state.session_id, existing_command.event_id)
                return WriteResult(event=existing, state=state.model_copy(deep=True), deduplicated=True)
        event = ArenaEvidenceEvent(
            event_id=event_id or f"evt-{uuid4().hex}",
            session_id=state.session_id,
            sequence=state.last_sequence + 1,
            event_type=event_type,
            category=category,
            created_at=created_at or utc_now_iso(),
            agent_id=agent_id,
            agent_number=agent_number,
            command_id=command_id,
            idempotency_key=idempotency_key,
            critical=(event_type in self.config.memory.critical_event_types) if critical is None else critical,
            payload=payload,
            source_refs=source_refs or [],
        )
        append_jsonl_record(self._events_path(state.session_id), event.model_dump())
        self._apply_event(state, event)
        write_json_atomic(self._state_path(state.session_id), state.model_dump())
        return WriteResult(event=event, state=state.model_copy(deep=True), deduplicated=False)

    def _apply_event(self, state: CollectiveStateSnapshot, event: ArenaEvidenceEvent) -> None:
        payload = event.payload
        event_type = event.event_type
        if event_type == "SESSION_COORDINATION_INITIALIZED":
            state.active_agents = list(payload.get("active_agents", state.active_agents))
        elif event_type == "AGENT_HEARTBEAT":
            assert event.agent_id is not None and event.agent_number is not None
            state.heartbeats[event.agent_id] = AgentHeartbeatState(
                agent_id=event.agent_id,
                agent_number=event.agent_number,
                heartbeat_at=payload["heartbeat_at"],
                expires_at=payload["expires_at"],
                last_sequence=event.sequence,
            )
        elif event_type == "SYMBOL_LEASE_RENEWED":
            lease = SymbolLease.model_validate(payload["lease"])
            state.symbol_leases[lease.symbol] = lease
        elif event_type in {"PUBLICATION_CREATED", "RISK_WARNING_PUBLISHED"}:
            assert event.agent_id is not None and event.agent_number is not None
            publication = PublicationRecord(
                publication_id=payload["publication_id"],
                session_id=event.session_id,
                sequence=event.sequence,
                agent_id=event.agent_id,
                agent_number=event.agent_number,
                kind=payload["kind"],
                symbol=payload.get("symbol"),
                summary=payload["summary"],
                source_refs=[SourceReference.model_validate(item) for item in payload.get("source_refs", [])],
                created_at=event.created_at,
            )
            state.publications.append(publication)
            state.publications = state.publications[-self.config.memory.max_active_publications :]
            if publication.kind == "risk_warning":
                state.risk_warnings.append(publication.publication_id)
            elif publication.kind == "unresolved_question":
                state.unresolved_questions.append(publication.publication_id)
            elif publication.kind == "active_hypothesis":
                state.active_hypotheses.append(publication.publication_id)
        elif event_type == "PEER_PUBLICATION_ACKED":
            assert event.agent_id is not None and event.agent_number is not None
            state.publication_cursors[event.agent_id] = PeerPublicationAck(
                agent_id=event.agent_id,
                agent_number=event.agent_number,
                cursor_sequence=payload["cursor_sequence"],
                acknowledged_at=payload["acknowledged_at"],
                source_event_id=payload["source_event_id"],
            )
        elif event_type == "FEATURE_TRUST_UPDATED":
            state.feature_trust_states[payload["key"]] = FeatureTrustState.model_validate(
                payload["feature_trust_state"]
            )
        elif event_type == "INSTRUCTIONS_ACKED":
            instruction = InstructionVersionState.model_validate(payload["instruction"])
            state.instruction_versions[instruction.agent_id] = instruction
        elif event_type == "PORTFOLIO_RECONCILED":
            state.portfolio = PortfolioState.model_validate(payload["portfolio"])
        elif event_type in {"ORDER_REQUESTED", "CANCEL_REQUESTED", "CLOSE_REQUESTED"}:
            command = PendingCommand.model_validate(payload["command"])
            state.pending_commands[command.command_id] = command
        elif event_type == "COMMAND_DISPATCH_STARTED":
            command = state.pending_commands[payload["command_id"]]
            state.pending_commands[command.command_id] = command.model_copy(
                update={"dispatch_state": "dispatch_started", "dispatch_started_at": payload["started_at"]}
            )
        elif event_type == "FSM_DECISION":
            command = state.pending_commands[payload["command_id"]]
            accepted = bool(payload["accepted"])
            refs = [SourceReference.model_validate(item) for item in payload.get("source_refs", [])]
            state.pending_commands[command.command_id] = command.model_copy(
                update={
                    "status": "accepted_by_fsm" if accepted else "rejected_by_fsm",
                    "dispatch_state": "fsm_accepted" if accepted else "fsm_rejected",
                    "resolution_refs": refs,
                }
            )
        elif event_type == "COMMAND_RESOLVED":
            command = state.pending_commands[payload["command_id"]]
            state.pending_commands[command.command_id] = command.model_copy(
                update={"status": "resolved", "dispatch_state": "resolved"}
            )
        elif event_type == "MEMORY_CHECKPOINT_CREATED":
            state.last_checkpoint_id = payload["checkpoint_id"]
            state.compression_statistics = CompressionStatistics.model_validate(
                payload["compression_statistics"]
            )
        elif event_type == "RECOVERY_COMPLETED":
            state.recovery_state = "ready" if payload["report"]["ready"] else "blocked"
        state.version = event.sequence
        state.last_sequence = event.sequence
        state.updated_at = event.created_at
        if event.idempotency_key:
            state.processed_idempotency_keys[event.idempotency_key] = event.event_id

    def _build_segments(self, events: list[ArenaEvidenceEvent]) -> list[MemorySegment]:
        size = self.config.memory.segment_size_events
        segments: list[MemorySegment] = []
        for index in range(0, len(events), size):
            chunk = events[index : index + size]
            counts: dict[str, int] = {}
            for event in chunk:
                counts[event.event_type] = counts.get(event.event_type, 0) + 1
            summary = "; ".join(f"{name}={counts[name]}" for name in sorted(counts))
            summary = f"seq {chunk[0].sequence}-{chunk[-1].sequence}; {summary}"
            summary = summary[: self.config.memory.max_summary_chars]
            refs = [self._source_ref(event) for event in chunk]
            critical_events = [event for event in chunk if event.critical]
            omitted = sorted({event.category for event in chunk if not event.critical})
            tokens, kind = self._count_tokens(summary + self._canonical_json([ref.model_dump() for ref in refs]))
            segments.append(
                MemorySegment(
                    segment_id=f"segment-{chunk[0].sequence}-{chunk[-1].sequence}",
                    start_sequence=chunk[0].sequence,
                    end_sequence=chunk[-1].sequence,
                    event_count=len(chunk),
                    summary=summary,
                    source_refs=refs,
                    critical_events=critical_events,
                    omitted_categories=omitted,
                    token_count=tokens,
                    token_count_kind=kind,
                )
            )
        return segments

    def _create_private_checkpoint_locked(
        self,
        session_id: str,
        agent_id: str,
        agent_number: int,
        collective_checkpoint_id: str,
    ) -> AgentPrivateCheckpoint:
        reflections = self._read_private_reflections_locked(session_id, agent_id)
        source_refs = [
            SourceReference(
                source_id=item.reflection_id,
                source_type="private_reflection",
                created_at=item.created_at,
            )
            for item in reflections
        ]
        counts: dict[str, int] = {}
        for reflection in reflections:
            counts[reflection.kind] = counts.get(reflection.kind, 0) + 1
        summary = "; ".join(f"{name}={counts[name]}" for name in sorted(counts))
        private = AgentPrivateCheckpoint(
            checkpoint_id=f"private-checkpoint-{agent_id}-{collective_checkpoint_id.split('-', 1)[-1]}",
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            reflection_count=len(reflections),
            summary=summary,
            source_refs=source_refs,
        )
        write_json_atomic(
            self._private_checkpoint_path(session_id, agent_id, private.checkpoint_id),
            private.model_dump(),
        )
        return private

    def _latest_checkpoint_locked(self, session_id: str) -> Optional[MemoryCheckpoint]:
        directory = self._coordination_dir(session_id) / "checkpoints"
        if not directory.exists():
            return None
        checkpoints: list[MemoryCheckpoint] = []
        for path in directory.glob("*.json"):
            checkpoints.append(MemoryCheckpoint.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda item: (item.manifest.end_sequence, item.created_at))

    def _count_tokens(self, text: str) -> tuple[int, str]:
        try:
            import tiktoken  # type: ignore

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text)), "real"
        except (ImportError, ModuleNotFoundError, KeyError):
            ratio = self.config.memory.token_estimate_chars_per_token
            return (len(text) + ratio - 1) // ratio, "estimate"

    def validate_configured_symbol_scope(self, agent_id: str, agent_number: int, symbol: str) -> None:
        identity = self._validate_agent(agent_id, agent_number)
        normalized = str(symbol or "").strip().upper()
        if normalized not in identity.symbols:
            raise SymbolAuthorityError(f"{agent_id} cannot publish for unowned symbol {normalized}")

    def _active_context_payload(
        self,
        *,
        state: CollectiveStateSnapshot,
        segments: list[MemorySegment],
        checkpoint_id: str,
    ) -> dict[str, Any]:
        """Build a bounded prompt view without weakening checkpoint evidence."""
        feature_trust = {
            key: {
                "feature_name": value.feature_name,
                "agent_id": value.agent_id,
                "version": value.version,
                "current_trust": value.current_trust,
                "latest_update": value.history[-1].model_dump() if value.history else None,
            }
            for key, value in state.feature_trust_states.items()
        }
        snapshot_view = {
            "session_id": state.session_id,
            "version": state.version,
            "last_sequence": state.last_sequence,
            "active_agents": state.active_agents,
            "heartbeats": {key: value.model_dump() for key, value in state.heartbeats.items()},
            "symbol_leases": {key: value.model_dump() for key, value in state.symbol_leases.items()},
            "publications": [
                {
                    "publication_id": item.publication_id,
                    "sequence": item.sequence,
                    "agent_id": item.agent_id,
                    "kind": item.kind,
                    "symbol": item.symbol,
                    "summary": item.summary,
                    "source_ids": [ref.source_id for ref in item.source_refs],
                }
                for item in state.publications[-20:]
            ],
            "portfolio": state.portfolio.model_dump() if state.portfolio else None,
            "risk_warnings": state.risk_warnings[-20:],
            "unresolved_questions": state.unresolved_questions[-20:],
            "active_hypotheses": state.active_hypotheses[-20:],
            "feature_trust": feature_trust,
            "instruction_versions": {
                key: value.model_dump() for key, value in state.instruction_versions.items()
            },
            "pending_commands": {
                key: value.model_dump() for key, value in state.pending_commands.items()
            },
        }
        segment_views = [
            {
                "segment_id": segment.segment_id,
                "summary": segment.summary,
                "source_ids": [ref.source_id for ref in segment.source_refs],
                "critical_events": [event.model_dump() for event in segment.critical_events],
            }
            for segment in segments
        ]
        payload: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "snapshot": snapshot_view,
            "segments": segment_views,
            "omitted_active_segments": [],
            "full_source_manifest_ref": f"checkpoint://{checkpoint_id}/manifest",
        }
        limit = self.config.memory.active_context_token_limit
        tokens, _ = self._count_tokens(self._canonical_json(payload))
        while tokens > limit and len(payload["segments"]) > 1:
            omitted = payload["segments"].pop(0)
            payload["omitted_active_segments"].append(
                {
                    "segment_id": omitted["segment_id"],
                    "source_manifest_ref": f"checkpoint://{checkpoint_id}/segments/{omitted['segment_id']}",
                    "reason": "active_context_budget",
                }
            )
            tokens, _ = self._count_tokens(self._canonical_json(payload))
        return payload

    def _validate_agent(self, agent_id: str, agent_number: Optional[int]):
        identity = self.config.agent(str(agent_id or "").strip())
        if agent_number is None or identity.agent_number != agent_number:
            raise ValueError(f"agent identity mismatch for {agent_id}")
        return identity

    def _validate_session(self, session_id: str) -> None:
        self.session_store.get_session(session_id)

    def _read_events_locked(self, session_id: str) -> list[ArenaEvidenceEvent]:
        records = read_jsonl_records(self._events_path(session_id), quarantine_root=self.quarantine_root)
        return [ArenaEvidenceEvent.model_validate(record) for _, record in records]

    def _read_private_reflections_locked(
        self, session_id: str, agent_id: str
    ) -> list[AgentPrivateReflection]:
        records = read_jsonl_records(
            self._private_reflections_path(session_id, agent_id), quarantine_root=self.quarantine_root
        )
        return [AgentPrivateReflection.model_validate(record) for _, record in records]

    def _private_reflection_by_id_locked(
        self, session_id: str, agent_id: str, reflection_id: str
    ) -> AgentPrivateReflection:
        for reflection in self._read_private_reflections_locked(session_id, agent_id):
            if reflection.reflection_id == reflection_id:
                return reflection
        raise KeyError(reflection_id)

    def _event_by_id_locked(self, session_id: str, event_id: str) -> ArenaEvidenceEvent:
        for event in self._read_events_locked(session_id):
            if event.event_id == event_id:
                return event
        raise KeyError(event_id)

    @staticmethod
    def _validate_sequence(events: list[ArenaEvidenceEvent]) -> None:
        for expected, event in enumerate(events, start=1):
            if event.sequence != expected:
                raise RuntimeError(
                    f"arena evidence sequence is not monotonic: expected {expected}, got {event.sequence}"
                )
        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise RuntimeError("arena evidence contains duplicate event_id values")

    @staticmethod
    def _source_ref(event: ArenaEvidenceEvent) -> SourceReference:
        return SourceReference(
            source_id=event.event_id,
            source_type="arena_event",
            sequence=event.sequence,
            event_id=event.event_id,
            created_at=event.created_at,
        )

    @staticmethod
    def _canonical_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def _coordination_dir(self, session_id: str) -> Path:
        safe = SessionStore._session_dir(self.session_store, session_id)
        path = safe / "coordination"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _events_path(self, session_id: str) -> Path:
        return self._coordination_dir(session_id) / self.EVENTS_NAME

    def _state_path(self, session_id: str) -> Path:
        return self._coordination_dir(session_id) / self.STATE_NAME

    def _checkpoint_path(self, session_id: str, checkpoint_id: str) -> Path:
        path = self._coordination_dir(session_id) / "checkpoints" / f"{checkpoint_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _private_dir(self, session_id: str, agent_id: str) -> Path:
        safe_agent = str(agent_id or "").strip()
        if not safe_agent or any(part in safe_agent for part in ("..", "/", "\\")):
            raise ValueError("agent_id must be a safe path segment")
        path = self._coordination_dir(session_id) / "private" / safe_agent
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _private_reflections_path(self, session_id: str, agent_id: str) -> Path:
        return self._private_dir(session_id, agent_id) / self.PRIVATE_REFLECTIONS_NAME

    def _private_checkpoint_path(self, session_id: str, agent_id: str, checkpoint_id: str) -> Path:
        path = self._private_dir(session_id, agent_id) / "checkpoints" / f"{checkpoint_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @contextmanager
    def _session_lock(self, session_id: str) -> Iterator[None]:
        lock_path = self._coordination_dir(session_id) / ".coordination.lock"
        deadline = time.monotonic() + self.config.memory.lock_timeout_seconds
        fd: Optional[int] = None
        while fd is None:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except (FileExistsError, PermissionError):
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > self.config.memory.lock_stale_seconds:
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise CoordinationLockTimeout(f"timed out acquiring session lock: {session_id}")
                time.sleep(0.01)
        try:
            os.write(fd, f"pid={os.getpid()} acquired={utc_now_iso()}".encode("utf-8"))
            os.fsync(fd)
            yield
        finally:
            os.close(fd)
            lock_path.unlink(missing_ok=True)
