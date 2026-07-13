"""Canonical no-command proposal dry-run over existing V2 authority and sizing."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from threading import RLock
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentIntentAuthoritySnapshotV2,
    AgentTradeIntentV2,
    PositionQueriesSizingAdapterV2,
)
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    AuthorityStoreError,
    TradingSessionAuthorityStore,
)


FORBIDDEN_PROPOSAL_FIELDS = frozenset({
    "qty", "quantity", "size", "notional", "amount", "leverage", "margin",
    "margin_pct", "risk_fraction", "position_size", "exchange_order",
    "client_order_id", "raw_exchange_params", "api_key", "api_secret", "credentials",
})


class ProposalValidationError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _scan_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_PROPOSAL_FIELDS or normalized.startswith("raw_exchange"):
                raise ProposalValidationError("PROPOSAL_FORBIDDEN_FIELD")
            _scan_forbidden(nested)
    elif isinstance(value, list):
        for item in value:
            _scan_forbidden(item)


class CockpitTradeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["p46.trade-proposal.v1"]
    proposal_id: str = Field(..., min_length=8, max_length=256)
    cockpit_session_id: str = Field(..., min_length=1)
    phenix_session_id: str = Field(..., min_length=1)
    binding_id: str = Field(..., min_length=1)
    proposer_id: str = Field(..., min_length=1)
    proposer_role: Literal["OPERATOR", "MAIN_AGENT", "CLI_AGENT"]
    participant_id: str = Field(..., min_length=1)
    intent_kind: Literal["OPEN"]
    symbol: str = Field(..., min_length=2, max_length=20)
    side: Literal["BUY", "SELL"]
    entry_preference: Literal["CURRENT_MARKET"]
    rationale_summary: str = Field(..., min_length=3, max_length=500)
    confidence: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))
    horizon_sec: int = Field(..., ge=1)
    context_manifest_version: str = Field(..., min_length=1)
    instruction_version: str = Field(..., min_length=1)
    lease_id: str = Field(..., min_length=1)
    lease_version: int = Field(..., ge=1)
    created_at: datetime
    expires_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must be alphanumeric")
        return normalized

    @field_validator("created_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("proposal timestamps require timezone")
        return value


def validate_proposal_payload(payload: Any) -> CockpitTradeProposal:
    _scan_forbidden(payload)
    try:
        proposal = CockpitTradeProposal.model_validate(payload)
    except Exception as exc:
        raise ProposalValidationError("PROPOSAL_SCHEMA_INVALID") from exc
    if proposal.expires_at <= proposal.created_at:
        raise ProposalValidationError("PROPOSAL_EXPIRED")
    return proposal


class ProposalDryRunAuthoritySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    v2: AgentIntentAuthoritySnapshotV2
    context_manifest_version: str
    instruction_version: str
    lease_version: int = Field(..., ge=1)
    source_references: tuple[str, ...]


class ExposurePreviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exposure_decision_id: str
    approved: bool
    reason_codes: tuple[str, ...]


class DryRunSideEffects(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_mutations: Literal[0] = 0
    lease_mutations: Literal[0] = 0
    exposure_reservations: Literal[0] = 0
    command_emissions: Literal[0] = 0
    fsm_calls: Literal[0] = 0
    adapter_calls: Literal[0] = 0
    exchange_calls: Literal[0] = 0


class ProposalDryRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["p46.proposal-dry-run-result.v1"] = "p46.proposal-dry-run-result.v1"
    dry_run_id: str
    proposal_id: str
    session_id: str
    participant_id: str
    symbol: str
    decision: Literal["ACCEPTED", "REJECTED", "STALE", "CONFLICT", "UNAVAILABLE"]
    reason_codes: tuple[str, ...]
    config_version: Optional[str]
    context_manifest_version: str
    instruction_version: str
    lease_id: str
    lease_version: int
    sizing_decision_id: Optional[str]
    exposure_decision_id: Optional[str]
    derived_quantity: Optional[Decimal]
    derived_notional: Optional[Decimal]
    reference_price: Optional[Decimal]
    account_snapshot_ref: Optional[str]
    market_snapshot_ref: Optional[str]
    generated_at: datetime
    valid_until: datetime
    execution_state: Literal["DRY_RUN_ONLY"] = "DRY_RUN_ONLY"
    source_references: tuple[str, ...]
    side_effects: DryRunSideEffects = DryRunSideEffects()


SnapshotReader = Callable[[CockpitTradeProposal], ProposalDryRunAuthoritySnapshot]
ExposurePreview = Callable[[CockpitTradeProposal, Decimal, Decimal, ProposalDryRunAuthoritySnapshot], ExposurePreviewDecision]


def _stable_id(prefix: str, payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}:{hashlib.sha256(body.encode('utf-8')).hexdigest()}"


def proposal_to_agent_trade_intent_v2(
    proposal: CockpitTradeProposal,
    *,
    agent_id: str,
    source: ProposalDryRunAuthoritySnapshot,
) -> AgentTradeIntentV2:
    """Map proposal identity and rationale only; executable sizing is impossible here."""
    return AgentTradeIntentV2(
        contract_version="2.0",
        session_id=proposal.phenix_session_id,
        participant_id=proposal.participant_id,
        agent_id=agent_id,
        symbol=proposal.symbol,
        intent_type="OPEN",
        side=proposal.side,
        strategy_or_reason=proposal.rationale_summary,
        confidence=proposal.confidence,
        max_position_horizon_sec=proposal.horizon_sec,
        context_version=source.v2.current_context_version,
        context_ack_version=source.v2.required_context_ack_version,
        evidence_refs=list(source.source_references),
        subagent_acknowledgements=[],
        lease_reference=proposal.lease_id,
        client_intent_id=proposal.proposal_id,
        created_at=proposal.created_at,
    )


class ProposalDryRunService:
    def __init__(self, *, authority: TradingSessionAuthorityStore, snapshot_reader: SnapshotReader,
                 sizing_adapter: PositionQueriesSizingAdapterV2, exposure_preview: ExposurePreview,
                 clock: Callable[[], datetime]) -> None:
        if any(item is None for item in (authority, snapshot_reader, sizing_adapter, exposure_preview, clock)):
            raise ValueError("dry-run authorities are explicit")
        self.authority = authority
        self.snapshot_reader = snapshot_reader
        self.sizing_adapter = sizing_adapter
        self.exposure_preview = exposure_preview
        self.clock = clock
        self._proposals: dict[str, CockpitTradeProposal] = {}
        self._results: dict[str, ProposalDryRunResult] = {}
        self._lock = RLock()

    def get(self, proposal_id: str) -> ProposalDryRunResult:
        try:
            return self._results[proposal_id]
        except KeyError as exc:
            raise ProposalValidationError("DRY_RUN_NOT_FOUND") from exc

    def evaluate(self, proposal: CockpitTradeProposal) -> ProposalDryRunResult:
        with self._lock:
            prior = self._proposals.get(proposal.proposal_id)
            if prior is not None:
                if prior == proposal:
                    return self._results[proposal.proposal_id]
                return self._rejected(proposal, "CONFLICT", ("PROPOSAL_ID_CONFLICT",), None)
            self._proposals[proposal.proposal_id] = proposal
        now = self.clock()
        if proposal.expires_at <= now:
            result = self._rejected(proposal, "STALE", ("PROPOSAL_EXPIRED",), None)
            self._results[proposal.proposal_id] = result
            return result
        try:
            source = self.snapshot_reader(proposal)
            participant = self.authority.read_participant(proposal.participant_id)
            intent = proposal_to_agent_trade_intent_v2(
                proposal, agent_id=participant.agent_id, source=source
            )
            _, _, lease = self.authority.validate_execution_authority(intent)
            if lease.version != proposal.lease_version or source.lease_version != proposal.lease_version:
                raise ProposalValidationError("LEASE_VERSION_MISMATCH")
            if source.context_manifest_version != proposal.context_manifest_version:
                raise ProposalValidationError("CONTEXT_VERSION_MISMATCH")
            if source.instruction_version != proposal.instruction_version:
                raise ProposalValidationError("INSTRUCTION_VERSION_MISMATCH")
            sizing = self.sizing_adapter.size(intent, source.v2)
            if not sizing.approved or sizing.derived_quantity is None or sizing.reference_price is None:
                result = self._rejected(proposal, "REJECTED", tuple(sizing.rejection_reasons or ["SIZING_REJECTED"]), source,
                                        sizing_decision_id=sizing.sizing_decision_id)
            else:
                notional = sizing.derived_quantity * sizing.reference_price
                exposure = self.exposure_preview(proposal, sizing.derived_quantity, notional, source)
                if not exposure.approved:
                    result = self._rejected(proposal, "REJECTED", exposure.reason_codes or ("EXPOSURE_REJECTED",), source,
                                            sizing_decision_id=sizing.sizing_decision_id,
                                            exposure_decision_id=exposure.exposure_decision_id)
                else:
                    result = ProposalDryRunResult(
                        dry_run_id=_stable_id("dry-run", proposal.model_dump(mode="json")), proposal_id=proposal.proposal_id,
                        session_id=proposal.phenix_session_id, participant_id=proposal.participant_id, symbol=proposal.symbol,
                        decision="ACCEPTED", reason_codes=(), config_version=source.v2.config_version,
                        context_manifest_version=source.context_manifest_version, instruction_version=source.instruction_version,
                        lease_id=proposal.lease_id, lease_version=proposal.lease_version,
                        sizing_decision_id=sizing.sizing_decision_id, exposure_decision_id=exposure.exposure_decision_id,
                        derived_quantity=sizing.derived_quantity, derived_notional=notional,
                        reference_price=sizing.reference_price, account_snapshot_ref=sizing.account_snapshot_ref,
                        market_snapshot_ref=sizing.market_snapshot_ref, generated_at=now,
                        valid_until=proposal.expires_at, source_references=tuple(sorted(set(source.source_references))),
                    )
        except AuthorityStoreError as exc:
            result = self._rejected(proposal, "REJECTED", (exc.reason,), None)
        except ProposalValidationError as exc:
            decision = "STALE" if "VERSION" in exc.reason or "EXPIRED" in exc.reason else "REJECTED"
            result = self._rejected(proposal, decision, (exc.reason,), None)
        except Exception:
            result = self._rejected(proposal, "UNAVAILABLE", ("DRY_RUN_AUTHORITY_UNAVAILABLE",), None)
        self._results[proposal.proposal_id] = result
        return result

    def _rejected(self, proposal: CockpitTradeProposal, decision: str, reasons: tuple[str, ...],
                  source: Optional[ProposalDryRunAuthoritySnapshot], *, sizing_decision_id: Optional[str] = None,
                  exposure_decision_id: Optional[str] = None) -> ProposalDryRunResult:
        now = self.clock()
        return ProposalDryRunResult(
            dry_run_id=_stable_id("dry-run", [proposal.proposal_id, decision, reasons]), proposal_id=proposal.proposal_id,
            session_id=proposal.phenix_session_id, participant_id=proposal.participant_id, symbol=proposal.symbol,
            decision=decision, reason_codes=reasons, config_version=source.v2.config_version if source else None,
            context_manifest_version=proposal.context_manifest_version, instruction_version=proposal.instruction_version,
            lease_id=proposal.lease_id, lease_version=proposal.lease_version,
            sizing_decision_id=sizing_decision_id, exposure_decision_id=exposure_decision_id,
            derived_quantity=None, derived_notional=None, reference_price=source.v2.reference_price if source else None,
            account_snapshot_ref=source.v2.account_snapshot_ref if source else None,
            market_snapshot_ref=source.v2.market_snapshot_ref if source else None,
            generated_at=now, valid_until=proposal.expires_at,
            source_references=tuple(sorted(set(source.source_references))) if source else (),
        )
