"""Canonical single-process session, participant, and symbol-lease authority."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentIntentAuthoritySnapshotV2,
    AgentTradeIntentV2,
    AuthorityProviderRejectedV2,
)


SessionStatus = Literal["CREATED", "ACTIVE", "PAUSED", "CLOSED", "EXPIRED"]
ParticipantType = Literal["MAIN_AGENT", "SUBAGENT", "OPERATOR"]


def _snapshot_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if value is None:
        return None
    try:
        numeric = Decimal(str(value))
    except Exception:
        return None
    if numeric <= 0:
        return None
    seconds = numeric / Decimal("1000") if numeric >= Decimal("100000000000") else numeric
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value


class TradingSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    status: SessionStatus
    created_at: datetime
    started_at: Optional[datetime]
    expires_at: datetime
    instrument_universe: list[str] = Field(..., min_length=1)
    participants: list[str]
    config_version: str = Field(..., min_length=1)
    instruction_version: str = Field(..., min_length=1)

    @field_validator("created_at", "started_at", "expires_at")
    @classmethod
    def aware_times(cls, value: Optional[datetime], info: Any) -> Optional[datetime]:
        return None if value is None else _aware(value, info.field_name)

    @field_validator("instrument_universe")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        normalized = [str(symbol).strip().upper() for symbol in value]
        if any(not symbol or not symbol.isalnum() for symbol in normalized):
            raise ValueError("instrument_universe contains an invalid symbol")
        if len(normalized) != len(set(normalized)):
            raise ValueError("instrument_universe must be unique")
        return normalized


class Participant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    participant_type: ParticipantType
    enabled: bool
    session_id: str = Field(..., min_length=1)


class SymbolLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=2)
    owner_participant_id: str = Field(..., min_length=1)
    acquired_at: datetime
    expires_at: datetime
    version: int = Field(..., ge=1)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must be alphanumeric")
        return normalized

    @field_validator("acquired_at", "expires_at")
    @classmethod
    def aware_times(cls, value: datetime, info: Any) -> datetime:
        return _aware(value, info.field_name)


class AuthorityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    participant_id: str
    agent_id: str
    symbol: str
    lease_id: Optional[str]
    lease_version: Optional[int]
    client_intent_id: str
    authority_decision: Literal["ACCEPTED", "REJECTED"]
    rejection_reason: Optional[str]
    config_version: str
    timestamp: datetime


class AuthorityStoreError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TradingSessionAuthorityStore:
    """One process-local owner; memory stores are deliberately not authority inputs."""

    def __init__(self, policy: Any, clock: Callable[[], datetime]) -> None:
        if policy is None or clock is None:
            raise ValueError("explicit policy and clock are required")
        self.policy = policy
        self.clock = clock
        self._sessions: dict[str, TradingSession] = {}
        self._participants: dict[str, Participant] = {}
        self._leases: dict[tuple[str, str], SymbolLease] = {}
        self._released_lease_ids: set[str] = set()
        self._decisions: list[AuthorityDecision] = []
        self._lock = RLock()

    def create_session(self, session: TradingSession) -> TradingSession:
        with self._lock:
            if session.session_id in self._sessions:
                if self._sessions[session.session_id] == session:
                    return session
                raise AuthorityStoreError("SESSION_CONFLICT")
            if session.status not in self.policy.supported_session_statuses:
                raise AuthorityStoreError("SESSION_STATUS_UNSUPPORTED")
            if not set(session.instrument_universe).issubset(
                set(self.policy.session_instrument_universe)
            ):
                raise AuthorityStoreError("SYMBOL_NOT_IN_SESSION_UNIVERSE")
            if session.config_version != self.policy.config_version:
                raise AuthorityStoreError("CONFIG_VERSION_MISMATCH")
            if session.expires_at <= session.created_at:
                raise AuthorityStoreError("SESSION_EXPIRY_INVALID")
            self._sessions[session.session_id] = session
            return session

    def read_session(self, session_id: str) -> TradingSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise AuthorityStoreError("SESSION_NOT_FOUND") from exc

    def set_session_status(self, session_id: str, status: SessionStatus) -> TradingSession:
        with self._lock:
            session = self.read_session(session_id)
            started_at = session.started_at
            if status == "ACTIVE" and started_at is None:
                started_at = self.clock()
            updated = session.model_copy(update={"status": status, "started_at": started_at})
            self._sessions[session_id] = updated
            return updated

    def activate_session(self, session_id: str) -> TradingSession:
        return self.set_session_status(session_id, "ACTIVE")

    def pause_session(self, session_id: str) -> TradingSession:
        return self.set_session_status(session_id, "PAUSED")

    def close_session(self, session_id: str) -> TradingSession:
        return self.set_session_status(session_id, "CLOSED")

    def register_participant(self, participant: Participant) -> Participant:
        with self._lock:
            session = self.read_session(participant.session_id)
            if participant.participant_type not in self.policy.allowed_participant_types:
                raise AuthorityStoreError("PARTICIPANT_TYPE_UNSUPPORTED")
            existing = self._participants.get(participant.participant_id)
            if existing is not None:
                if existing == participant:
                    return participant
                raise AuthorityStoreError("PARTICIPANT_CONFLICT")
            self._participants[participant.participant_id] = participant
            if participant.participant_id not in session.participants:
                self._sessions[session.session_id] = session.model_copy(
                    update={"participants": [*session.participants, participant.participant_id]}
                )
            return participant

    def read_participant(self, participant_id: str) -> Participant:
        try:
            return self._participants[participant_id]
        except KeyError as exc:
            raise AuthorityStoreError("PARTICIPANT_NOT_FOUND") from exc

    def acquire_lease(self, lease: SymbolLease) -> SymbolLease:
        with self._lock:
            now = self.clock()
            session = self.read_session(lease.session_id)
            participant = self.read_participant(lease.owner_participant_id)
            self._validate_lease_candidate(session, participant, lease, now)
            key = (lease.session_id, lease.symbol)
            current = self._leases.get(key)
            if current and current.expires_at > now and current.lease_id not in self._released_lease_ids:
                if current == lease:
                    return current
                raise AuthorityStoreError("LEASE_CONFLICT")
            self._leases[key] = lease
            return lease

    def renew_lease(self, lease_id: str, owner_participant_id: str, expected_version: int) -> SymbolLease:
        with self._lock:
            lease = self._lease_by_id(lease_id)
            if lease.owner_participant_id != owner_participant_id:
                raise AuthorityStoreError("LEASE_OWNER_MISMATCH")
            if lease.version != expected_version:
                raise AuthorityStoreError("LEASE_VERSION_CONFLICT")
            now = self.clock()
            if lease.expires_at <= now:
                raise AuthorityStoreError("LEASE_EXPIRED")
            renewed = lease.model_copy(update={
                "expires_at": now + timedelta(seconds=self.policy.lease_ttl_sec),
                "version": lease.version + 1,
            })
            self._leases[(lease.session_id, lease.symbol)] = renewed
            return renewed

    def release_lease(self, lease_id: str, owner_participant_id: str, expected_version: int) -> None:
        with self._lock:
            lease = self._lease_by_id(lease_id)
            if lease.owner_participant_id != owner_participant_id:
                raise AuthorityStoreError("LEASE_OWNER_MISMATCH")
            if lease.version != expected_version:
                raise AuthorityStoreError("LEASE_VERSION_CONFLICT")
            self._released_lease_ids.add(lease_id)

    def resolve_current_owner(self, session_id: str, symbol: str) -> Optional[Participant]:
        lease = self._leases.get((session_id, symbol.upper()))
        if not lease or lease.lease_id in self._released_lease_ids or lease.expires_at <= self.clock():
            return None
        return self.read_participant(lease.owner_participant_id)

    def validate_execution_authority(self, intent: AgentTradeIntentV2) -> tuple[TradingSession, Participant, SymbolLease]:
        now = self.clock()
        session = self.read_session(intent.session_id)
        if session.expires_at <= now or session.status != "ACTIVE":
            raise AuthorityStoreError("SESSION_NOT_ACTIVE")
        participant = self.read_participant(intent.participant_id)
        if participant.session_id != session.session_id:
            raise AuthorityStoreError("PARTICIPANT_SESSION_MISMATCH")
        if not participant.enabled:
            raise AuthorityStoreError("PARTICIPANT_DISABLED")
        if participant.participant_type == "SUBAGENT":
            raise AuthorityStoreError("SUBAGENT_EXECUTION_FORBIDDEN")
        if participant.participant_type != "MAIN_AGENT":
            raise AuthorityStoreError("PARTICIPANT_ROLE_FORBIDDEN")
        if participant.agent_id != intent.agent_id:
            raise AuthorityStoreError("AGENT_MISMATCH")
        if intent.symbol not in session.instrument_universe:
            raise AuthorityStoreError("SYMBOL_NOT_IN_SESSION_UNIVERSE")
        lease = self._leases.get((session.session_id, intent.symbol))
        if lease is None or lease.lease_id in self._released_lease_ids:
            raise AuthorityStoreError("LEASE_NOT_FOUND")
        if lease.lease_id != intent.lease_reference or lease.owner_participant_id != participant.participant_id:
            raise AuthorityStoreError("LEASE_OWNER_MISMATCH")
        if lease.expires_at <= now:
            raise AuthorityStoreError("LEASE_EXPIRED")
        if intent.max_position_horizon_sec > self.policy.max_position_horizon_sec:
            raise AuthorityStoreError("HORIZON_EXCEEDED")
        return session, participant, lease

    def record_decision(self, intent: AgentTradeIntentV2, reason: Optional[str], lease: Optional[SymbolLease]) -> None:
        self._decisions.append(AuthorityDecision(
            session_id=intent.session_id,
            participant_id=intent.participant_id,
            agent_id=intent.agent_id,
            symbol=intent.symbol,
            lease_id=lease.lease_id if lease else None,
            lease_version=lease.version if lease else None,
            client_intent_id=intent.client_intent_id,
            authority_decision="REJECTED" if reason else "ACCEPTED",
            rejection_reason=reason,
            config_version=self.policy.config_version,
            timestamp=self.clock(),
        ))

    def decisions(self) -> list[AuthorityDecision]:
        return list(self._decisions)

    def _lease_by_id(self, lease_id: str) -> SymbolLease:
        for lease in self._leases.values():
            if lease.lease_id == lease_id and lease_id not in self._released_lease_ids:
                return lease
        raise AuthorityStoreError("LEASE_NOT_FOUND")

    def _validate_lease_candidate(
        self, session: TradingSession, participant: Participant, lease: SymbolLease, now: datetime
    ) -> None:
        if participant.session_id != session.session_id:
            raise AuthorityStoreError("PARTICIPANT_SESSION_MISMATCH")
        if not participant.enabled:
            raise AuthorityStoreError("PARTICIPANT_DISABLED")
        if participant.participant_type == "SUBAGENT":
            raise AuthorityStoreError("SUBAGENT_EXECUTION_FORBIDDEN")
        if participant.participant_type != "MAIN_AGENT":
            raise AuthorityStoreError("PARTICIPANT_ROLE_FORBIDDEN")
        if lease.symbol not in session.instrument_universe:
            raise AuthorityStoreError("SYMBOL_NOT_IN_SESSION_UNIVERSE")
        if lease.acquired_at != now:
            raise AuthorityStoreError("LEASE_ACQUIRED_AT_MISMATCH")
        if lease.expires_at != now + timedelta(seconds=self.policy.lease_ttl_sec):
            raise AuthorityStoreError("LEASE_EXPIRY_POLICY_MISMATCH")


class CanonicalV2AuthorityProvider:
    """Narrow adapter from canonical authority plus existing DecisionMaking truth."""

    def __init__(self, store: TradingSessionAuthorityStore, decision_making: Any) -> None:
        self.store = store
        self.decision_making = decision_making

    def __call__(self, intent: AgentTradeIntentV2) -> AgentIntentAuthoritySnapshotV2:
        lease: Optional[SymbolLease] = None
        try:
            session, participant, lease = self.store.validate_execution_authority(intent)
        except AuthorityStoreError as exc:
            self.store.record_decision(intent, exc.reason, lease)
            raise AuthorityProviderRejectedV2(exc.reason, self.store.clock()) from exc

        symbol_state = getattr(self.decision_making, "symbol_states", {}).get(intent.symbol, {})
        price_raw = symbol_state.get("current_price")
        portfolio = getattr(self.decision_making, "latest_portfolio", None)
        price = Decimal(str(price_raw)) if price_raw is not None else None
        now = self.store.clock()
        self.store.record_decision(intent, None, lease)
        return AgentIntentAuthoritySnapshotV2(
            session_known=True,
            session_active=True,
            participant_known=True,
            participant_is_main_agent=True,
            participant_agent_id=participant.agent_id,
            session_symbols=session.instrument_universe,
            lease_reference=lease.lease_id,
            lease_valid=True,
            current_context_version=intent.context_version,
            required_context_ack_version=intent.context_ack_version,
            max_horizon_sec=self.store.policy.max_position_horizon_sec,
            intent_ttl_sec=self.store.policy.intent_ttl_sec,
            lifecycle_allows_open=True,
            portfolio=portfolio,
            account_snapshot_ref=getattr(self.decision_making, "latest_portfolio_ref", None),
            account_snapshot_at=_snapshot_time(
                portfolio.get("ts_ms") or portfolio.get("timestamp")
                if isinstance(portfolio, dict) else None
            ),
            account_snapshot_max_age_sec=self.store.policy.account_snapshot_max_age_sec,
            reference_price=price,
            market_snapshot_ref=symbol_state.get("snapshot_ref"),
            market_snapshot_at=_snapshot_time(
                symbol_state.get("timestamp_ms") or symbol_state.get("timestamp")
            ),
            market_snapshot_max_age_sec=self.store.policy.market_snapshot_max_age_sec,
            config_version=self.store.policy.config_version,
            order_type=self.store.policy.execution_order_type,
            time_in_force=self.store.policy.execution_time_in_force,
            valid_for_ms=self.store.policy.execution_valid_for_ms,
            observed_at=now,
        )
