"""Pydantic contracts for immutable decision outcome ledger rows."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.domains.decision_making.schemas.control_decision import ControlDecisionAction


class ExecutionOutcome(str, Enum):
    EXECUTED = "EXECUTED"
    FSM_BLOCKED = "FSM_BLOCKED"
    EXCHANGE_REJECTED = "EXCHANGE_REJECTED"
    PENDING_TIMEOUT = "PENDING_TIMEOUT"


class DecisionOutcomeLedgerRow(BaseModel):
    """Immutable joined dataset row for offline Neocortex training."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    rid: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    decision_ts_ms: int = Field(ge=1)
    causal_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    neocortex_action: ControlDecisionAction
    fallback_reason: str | None = None
    execution_outcome: ExecutionOutcome
    realized_pnl_net: float | None = None
    data_quality_flags: dict[str, Any] = Field(default_factory=dict)
