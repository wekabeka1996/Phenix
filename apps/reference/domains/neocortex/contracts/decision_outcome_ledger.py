from __future__ import annotations
from typing import Literal

from apps.reference.domains.neocortex.contracts.causal_time import DatasetVisibility
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from enum import Enum

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, object] | list[object]
CounterfactualSupport = Literal["supported", "unsupported"]


DECISION_OUTCOME_LEDGER_SCHEMA_PASSPORT_ID = "neocortex.decision_outcome_ledger_row.v1"
DECISION_OUTCOME_LEDGER_VERSION = "1.0.0"


class DecisionOutcomeTerminalStatus(str, Enum):
    EXECUTED_AND_CLOSED = "EXECUTED_AND_CLOSED"
    VETOED = "VETOED"
    BASELINE_FALLBACK_NO_EXECUTION = "BASELINE_FALLBACK_NO_EXECUTION"
    BASELINE_FALLBACK_EXECUTED = "BASELINE_FALLBACK_EXECUTED"
    REJECTED_UPSTREAM = "REJECTED_UPSTREAM"
    INVALID_FOR_DATASET = "INVALID_FOR_DATASET"


class ExecutionOutcome(str, Enum):
    EXECUTED = "EXECUTED"
    FSM_BLOCKED = "FSM_BLOCKED"
    EXCHANGE_REJECTED = "EXCHANGE_REJECTED"
    PENDING_TIMEOUT = "PENDING_TIMEOUT"


class LedgerRevisionStatus(str, Enum):
    SEED_PENDING_OUTCOME = "SEED_PENDING_OUTCOME"
    DECISION_TERMINAL = "DECISION_TERMINAL"
    OUTCOME_FINAL = "OUTCOME_FINAL"
    TIMEOUT_FINAL = "TIMEOUT_FINAL"


class DecisionOutcomeStatus(str, Enum):
    REALIZED = "REALIZED"
    UNRESOLVED_ACCEPTED = "UNRESOLVED_ACCEPTED"
    UNRESOLVED_TIMEOUT = "UNRESOLVED_TIMEOUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def map_terminal_status_to_execution_outcome(
    terminal_status: DecisionOutcomeTerminalStatus,
) -> ExecutionOutcome:
    if terminal_status in {
        DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
        DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
    }:
        return ExecutionOutcome.EXECUTED
    if terminal_status == DecisionOutcomeTerminalStatus.REJECTED_UPSTREAM:
        return ExecutionOutcome.EXCHANGE_REJECTED
    if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
        return ExecutionOutcome.PENDING_TIMEOUT
    return ExecutionOutcome.FSM_BLOCKED


def map_terminal_status_to_revision_status(
    terminal_status: DecisionOutcomeTerminalStatus,
    invalid_reason_code: str | None,
) -> LedgerRevisionStatus:
    if terminal_status in {
        DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
        DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
    }:
        return LedgerRevisionStatus.OUTCOME_FINAL
    if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
        if invalid_reason_code == "OUTCOME_UNRESOLVED":
            return LedgerRevisionStatus.SEED_PENDING_OUTCOME
        if invalid_reason_code == "TERMINAL_EVENT_MISSING":
            return LedgerRevisionStatus.TIMEOUT_FINAL
        return LedgerRevisionStatus.OUTCOME_FINAL
    return LedgerRevisionStatus.DECISION_TERMINAL


def map_terminal_status_to_outcome_status(
    terminal_status: DecisionOutcomeTerminalStatus,
    invalid_reason_code: str | None,
) -> DecisionOutcomeStatus:
    if terminal_status in {
        DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
        DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
    }:
        return DecisionOutcomeStatus.REALIZED
    if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
        if invalid_reason_code == "OUTCOME_UNRESOLVED":
            return DecisionOutcomeStatus.UNRESOLVED_ACCEPTED
        if invalid_reason_code == "TERMINAL_EVENT_MISSING":
            return DecisionOutcomeStatus.UNRESOLVED_TIMEOUT
    return DecisionOutcomeStatus.NOT_APPLICABLE


class DecisionOutcomeLedgerRow(BaseModel):
    """Canonical Phase 6 decision outcome row keyed by decision_id."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    rid: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    authority_mode: str = Field(min_length=1)
    request_ts_ms: int = Field(ge=1)
    response_ts_ms: int = Field(ge=1)
    apply_result: str | None = None
    fallback_reason: str | None = None
    downstream_rid: str | None = None
    lifecycle_id: str | None = None
    trade_id: str | None = None
    cycle_key: str | None = None
    event_ts_ms: int | None = Field(default=None, ge=1)
    tf_sec: int | None = Field(default=None, ge=1)
    bar_close_ts_ms: int | None = Field(default=None, ge=1)
    strategy_id: str | None = None
    side: str | None = None
    intent_id: str | None = None
    accepted_or_rejected: Literal["ACCEPTED", "REJECTED"] | None = None
    reject_reason: str | None = None
    regime: str | None = None
    regime_confidence: float | None = None
    decision_surface: str | None = None
    raw_score: float | None = None
    decision_score: float | None = None
    active_threshold: float | None = None
    score_to_threshold_ratio: float | None = None
    gate_chain_result: str | None = None
    terminal_status: DecisionOutcomeTerminalStatus
    close_reason: str | None = None
    close_ts_ms: int | None = Field(default=None, ge=1)
    close_actor: str | None = None
    realized_pnl_gross: float | None = None
    realized_pnl_net: float | None = None
    fees: float | None = None
    stress_metrics: dict[str, JsonValue] = Field(default_factory=dict)
    support_quality: dict[str, JsonValue] = Field(default_factory=dict)
    dataset_visibility: DatasetVisibility
    counterfactual_support: CounterfactualSupport | None = None
    invalid_reason_code: str | None = None
    revision_status: LedgerRevisionStatus | None = None
    outcome_status: DecisionOutcomeStatus | None = None
    causal_state_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    neocortex_action: str = Field(min_length=1)
    data_quality_flags: dict[str, JsonValue] = Field(default_factory=dict)
    execution_outcome: ExecutionOutcome | None = None
    schema_passport_id: str = DECISION_OUTCOME_LEDGER_SCHEMA_PASSPORT_ID
    version: str = DECISION_OUTCOME_LEDGER_VERSION

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("authority_mode")
    @classmethod
    def normalize_authority_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "enforce":
            return "gated"
        return normalized

    @field_validator("neocortex_action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized == "DENY":
            return "BLOCK"
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> "DecisionOutcomeLedgerRow":
        if self.response_ts_ms < self.request_ts_ms:
            raise ValueError("response_ts_ms must be >= request_ts_ms")
        if (
            self.terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET
            and not self.invalid_reason_code
        ):
            raise ValueError(
                "invalid_reason_code is required when terminal_status=INVALID_FOR_DATASET"
            )
        if self.dataset_visibility == "trainable" and self.invalid_reason_code is not None:
            raise ValueError(
                "trainable rows cannot carry invalid_reason_code"
            )
        if self.counterfactual_support is None:
            self.counterfactual_support = (
                "supported" if self.dataset_visibility == "trainable" else "unsupported"
            )
        if self.dataset_visibility == "trainable" and self.counterfactual_support != "supported":
            raise ValueError(
                "trainable rows must carry counterfactual_support='supported'"
            )
        expected_execution_outcome = map_terminal_status_to_execution_outcome(
            self.terminal_status
        )
        if self.execution_outcome is None:
            self.execution_outcome = expected_execution_outcome
        elif self.execution_outcome != expected_execution_outcome:
            raise ValueError(
                "execution_outcome must match terminal_status compatibility mapping"
            )
        expected_revision_status = map_terminal_status_to_revision_status(
            self.terminal_status,
            self.invalid_reason_code,
        )
        if self.revision_status is None:
            self.revision_status = expected_revision_status
        elif self.revision_status != expected_revision_status:
            raise ValueError(
                "revision_status must match terminal_status and invalid_reason_code"
            )
        expected_outcome_status = map_terminal_status_to_outcome_status(
            self.terminal_status,
            self.invalid_reason_code,
        )
        if self.outcome_status is None:
            self.outcome_status = expected_outcome_status
        elif self.outcome_status != expected_outcome_status:
            raise ValueError(
                "outcome_status must match terminal_status and invalid_reason_code"
            )
        return self


__all__ = [
    "DECISION_OUTCOME_LEDGER_SCHEMA_PASSPORT_ID",
    "DECISION_OUTCOME_LEDGER_VERSION",
    "CounterfactualSupport",
    "DecisionOutcomeStatus",
    "DecisionOutcomeLedgerRow",
    "DecisionOutcomeTerminalStatus",
    "ExecutionOutcome",
    "LedgerRevisionStatus",
    "map_terminal_status_to_execution_outcome",
    "map_terminal_status_to_outcome_status",
    "map_terminal_status_to_revision_status",
]
