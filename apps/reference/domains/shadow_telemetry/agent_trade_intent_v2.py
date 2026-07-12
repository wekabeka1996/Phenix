"""Typed no-sizing agent intent and narrow Phenix sizing boundary."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentTradeIntentV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2.0"]
    session_id: str = Field(..., min_length=1)
    participant_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=2, max_length=20)
    intent_type: Literal["OPEN"]
    side: Literal["BUY", "SELL"]
    strategy_or_reason: str = Field(..., min_length=3, max_length=500)
    confidence: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))
    max_position_horizon_sec: int = Field(..., ge=1)
    context_version: int = Field(..., ge=1)
    context_ack_version: int = Field(..., ge=1)
    evidence_refs: list[str] = Field(..., min_length=1)
    subagent_acknowledgements: list[str] = Field(default_factory=list)
    lease_reference: str = Field(..., min_length=1)
    client_intent_id: str = Field(..., min_length=8, max_length=256)
    created_at: datetime

    @field_validator("symbol", "side")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if not normalized.isalnum():
            raise ValueError("must contain only letters and digits")
        return normalized

    @field_validator(
        "session_id",
        "participant_id",
        "agent_id",
        "strategy_or_reason",
        "lease_reference",
        "client_intent_id",
    )
    @classmethod
    def non_empty(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("must be non-empty")
        return cleaned

    @field_validator("evidence_refs", "subagent_acknowledgements")
    @classmethod
    def unique_non_empty_refs(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned) or len(cleaned) != len(set(cleaned)):
            raise ValueError("references must be unique non-empty strings")
        return cleaned

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def context_ack_cannot_exceed_observed_version(self) -> "AgentTradeIntentV2":
        if self.context_ack_version > self.context_version:
            raise ValueError("context_ack_version cannot exceed context_version")
        return self


class AgentIntentAuthoritySnapshotV2(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    session_known: bool
    session_active: bool
    participant_known: bool
    participant_is_main_agent: bool
    participant_agent_id: str
    session_symbols: list[str]
    lease_reference: Optional[str]
    lease_valid: bool
    current_context_version: int = Field(..., ge=1)
    required_context_ack_version: int = Field(..., ge=1)
    max_horizon_sec: int = Field(..., ge=1)
    intent_ttl_sec: int = Field(..., ge=1)
    lifecycle_allows_open: bool
    portfolio: Optional[dict[str, Any]]
    account_snapshot_ref: Optional[str]
    reference_price: Optional[Decimal]
    market_snapshot_ref: Optional[str]
    config_version: Optional[str]
    order_type: Optional[Literal["LIMIT"]]
    time_in_force: Optional[Literal["GTC", "GTX", "IOC", "FOK"]]
    valid_for_ms: Optional[int] = Field(default=None, ge=1000)
    observed_at: datetime


class AgentIntentSizingDecisionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    sizing_decision_id: str
    symbol: str
    approved: bool
    derived_quantity: Optional[Decimal]
    reference_price: Optional[Decimal]
    account_snapshot_ref: Optional[str]
    market_snapshot_ref: Optional[str]
    config_version: Optional[str]
    risk_checks: list[str]
    rejection_reasons: list[str]
    created_at: datetime


class AgentIntentProcessingResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AgentTradeIntentV2
    sizing: AgentIntentSizingDecisionV2
    downstream_command: Optional[dict[str, Any]] = None


class AgentIntentAcceptedResponseV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: str
    request_id: str
    state: Literal["queued"] = "queued"


AuthorityProviderV2 = Callable[[AgentTradeIntentV2], AgentIntentAuthoritySnapshotV2]


class PositionQueriesSizingAdapterV2:
    """Adapts the existing PositionQueries sizing owner without duplicating it."""

    def __init__(self, position_queries: Any) -> None:
        self.position_queries = position_queries

    def size(
        self,
        intent: AgentTradeIntentV2,
        snapshot: AgentIntentAuthoritySnapshotV2,
    ) -> AgentIntentSizingDecisionV2:
        now = snapshot.observed_at
        base = {
            "intent_id": intent.client_intent_id,
            "sizing_decision_id": f"sizing:{intent.client_intent_id}",
            "symbol": intent.symbol,
            "account_snapshot_ref": snapshot.account_snapshot_ref,
            "market_snapshot_ref": snapshot.market_snapshot_ref,
            "config_version": snapshot.config_version,
            "created_at": now,
        }
        missing: list[str] = []
        if not isinstance(snapshot.portfolio, dict):
            missing.append("ACCOUNT_TRUTH_MISSING")
        if snapshot.reference_price is None or snapshot.reference_price <= 0:
            missing.append("MARKET_PRICE_MISSING")
        if not snapshot.config_version:
            missing.append("SIZING_CONFIG_MISSING")
        if missing:
            return AgentIntentSizingDecisionV2(
                **base,
                approved=False,
                derived_quantity=None,
                reference_price=snapshot.reference_price,
                risk_checks=[],
                rejection_reasons=missing,
            )
        qty, why, reason_code, debug = self.position_queries.calculate_position_size(
            intent.symbol,
            snapshot.reference_price,
            intent.side,
            {"portfolio": snapshot.portfolio},
        )
        if qty is None or qty <= 0:
            return AgentIntentSizingDecisionV2(
                **base,
                approved=False,
                derived_quantity=None,
                reference_price=snapshot.reference_price,
                risk_checks=[f"POSITION_QUERIES:{why}"],
                rejection_reasons=[reason_code or "RISK_REJECTED"],
            )
        return AgentIntentSizingDecisionV2(
            **base,
            approved=True,
            derived_quantity=Decimal(str(qty)),
            reference_price=snapshot.reference_price,
            risk_checks=[
                "ACCOUNT_TRUTH_PRESENT",
                "MARKET_PRICE_PRESENT",
                "CONFIG_PRESENT",
                f"POSITION_QUERIES:{why}",
                f"STEP_SIZE:{debug.get('step_size')}",
            ],
            rejection_reasons=[],
        )


class AgentTradeIntentV2Processor:
    def __init__(
        self,
        *,
        authority_provider: AuthorityProviderV2,
        sizing_adapter: PositionQueriesSizingAdapterV2,
    ) -> None:
        self.authority_provider = authority_provider
        self.sizing_adapter = sizing_adapter

    def process(self, intent: AgentTradeIntentV2) -> AgentIntentProcessingResultV2:
        snapshot = self.authority_provider(intent)
        rejection = self._validate_authority(intent, snapshot)
        if rejection:
            sizing = AgentIntentSizingDecisionV2(
                intent_id=intent.client_intent_id,
                sizing_decision_id=f"sizing:{intent.client_intent_id}",
                symbol=intent.symbol,
                approved=False,
                derived_quantity=None,
                reference_price=snapshot.reference_price,
                account_snapshot_ref=snapshot.account_snapshot_ref,
                market_snapshot_ref=snapshot.market_snapshot_ref,
                config_version=snapshot.config_version,
                risk_checks=[],
                rejection_reasons=[rejection],
                created_at=datetime.now(timezone.utc),
            )
            return AgentIntentProcessingResultV2(intent=intent, sizing=sizing)
        sizing = self.sizing_adapter.size(intent, snapshot)
        if not sizing.approved or sizing.derived_quantity is None:
            return AgentIntentProcessingResultV2(intent=intent, sizing=sizing)
        downstream = {
            "rid": intent.client_intent_id,
            "intent_id": intent.client_intent_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": str(sizing.derived_quantity),
            "order_type": snapshot.order_type,
            "price": str(sizing.reference_price),
            "tif": snapshot.time_in_force,
            "valid_for_ms": snapshot.valid_for_ms,
            "idempotent_key": intent.client_intent_id,
            "source": "external_llm",
            "snapshot_ref": {
                "account": sizing.account_snapshot_ref,
                "market": sizing.market_snapshot_ref,
                "context_version": intent.context_version,
            },
            "why_short": intent.strategy_or_reason[:80],
            "sizing_decision_id": sizing.sizing_decision_id,
            "session_id": intent.session_id,
            "participant_id": intent.participant_id,
            "agent_id": intent.agent_id,
        }
        return AgentIntentProcessingResultV2(
            intent=intent,
            sizing=sizing,
            downstream_command=downstream,
        )

    @staticmethod
    def _validate_authority(
        intent: AgentTradeIntentV2,
        snapshot: AgentIntentAuthoritySnapshotV2,
    ) -> Optional[str]:
        if not snapshot.session_known:
            return "SESSION_UNKNOWN"
        if not snapshot.session_active:
            return "SESSION_INACTIVE"
        if not snapshot.participant_known:
            return "PARTICIPANT_UNKNOWN"
        if not snapshot.participant_is_main_agent:
            return "SUBAGENT_FORBIDDEN"
        if snapshot.participant_agent_id != intent.agent_id:
            return "AGENT_MISMATCH"
        if intent.symbol not in {symbol.upper() for symbol in snapshot.session_symbols}:
            return "SYMBOL_NOT_IN_SESSION"
        if not snapshot.lease_reference:
            return "LEASE_MISSING"
        if snapshot.lease_reference != intent.lease_reference or not snapshot.lease_valid:
            return "LEASE_INVALID"
        if (
            intent.context_version != snapshot.current_context_version
            or intent.context_ack_version < snapshot.required_context_ack_version
        ):
            return "CONTEXT_STALE"
        if intent.max_position_horizon_sec > snapshot.max_horizon_sec:
            return "HORIZON_EXCEEDED"
        age = snapshot.observed_at - intent.created_at
        if age.total_seconds() < 0 or age.total_seconds() > snapshot.intent_ttl_sec:
            return "INTENT_EXPIRED"
        if not snapshot.lifecycle_allows_open:
            return "LIFECYCLE_STATE_REJECTED"
        if not snapshot.order_type or not snapshot.time_in_force or not snapshot.valid_for_ms:
            return "EXECUTION_POLICY_MISSING"
        return None
