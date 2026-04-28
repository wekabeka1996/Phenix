"""Pydantic contracts for the synchronous Neocortex authority hook."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ControlDecisionAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    FALLBACK = "FALLBACK"


class ControlDecisionRequest(BaseModel):
    """Authority request sent from DecisionMaking to Neocortex."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    rid: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    proposed_action: str = Field(min_length=1)
    deadline_ms: int = Field(ge=1)
    decision_basis_ts: int = Field(ge=1)
    causal_state_snapshot: dict[str, Any] = Field(default_factory=dict)


class ControlDecisionResponse(BaseModel):
    """Authority response returned to the fast FSM boundary."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    action: ControlDecisionAction
    apply_result: str | None = None
    fallback_reason: str | None = None
    ttl_ms: int = Field(ge=0)
    model_action: ControlDecisionAction | None = None
    enforcement_mode: Literal["shadow", "enforce"] | None = None
    shadow_logged: bool = False

    @model_validator(mode="after")
    def validate_fallback_reason(self) -> "ControlDecisionResponse":
        if self.action == ControlDecisionAction.FALLBACK and not self.fallback_reason:
            raise ValueError(
                "fallback_reason is required when action=FALLBACK")
        if self.action != ControlDecisionAction.FALLBACK and self.fallback_reason:
            raise ValueError(
                "fallback_reason is only valid when action=FALLBACK")
        return self
