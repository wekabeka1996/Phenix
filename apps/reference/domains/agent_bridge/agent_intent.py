"""Immutable no-model AgentIntentV0 representation for P18 dry-run only."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .action_review import SCENARIO_IDS


IntentAction = Literal[
    "WAIT", "OBSERVE", "NO_ACTION",
    "DRY_RUN_OPEN_LONG", "DRY_RUN_OPEN_SHORT", "DRY_RUN_CLOSE",
    "DRY_RUN_PROTECT", "DRY_RUN_CANCEL", "DRY_RUN_AMEND",
]
IntentSide = Literal["LONG", "SHORT", "NONE"]


class IntentExpectedScenarioV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    confidence: float = Field(ge=0, le=1)
    thesis: str = Field(min_length=3, max_length=320)

    @model_validator(mode="after")
    def known_scenario(self):
        if self.scenario_id not in SCENARIO_IDS:
            raise ValueError("unknown scenario id")
        return self


class RequestedExecutionSemanticsV0(BaseModel):
    """A non-executable shape request; never an order command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shape: Literal["NONE", "MARKET", "LIMIT", "STOP", "REFERENCE_ONLY"] = "NONE"
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    limit_price: Optional[Decimal] = Field(default=None, gt=0)
    stop_price: Optional[Decimal] = Field(default=None, gt=0)
    reduce_only_requested: bool = False
    context_ref: Optional[str] = Field(default=None, max_length=240)
    non_executable: Literal[True] = True


class AgentIntentV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-intent/v0"] = "agent-intent/v0"
    intent_id: str = Field(pattern=r"^intent_[a-z0-9_]{4,120}$")
    created_ts_ms: int = Field(ge=0)
    source: Literal["deterministic_fixture", "manual_no_model", "test_sample", "model_packet_benchmark"]
    agent_id: str = Field(min_length=3, max_length=120)
    model_id: Optional[str] = Field(default=None, max_length=160)
    model_call_ref: Optional[str] = Field(default=None, max_length=240)
    rank: Literal["unranked_no_model", "unranked_benchmark"] = "unranked_no_model"
    mode: Literal["dry_run_no_execution"] = "dry_run_no_execution"
    symbol: str = Field(pattern=r"^[A-Z0-9_-]{2,32}$")
    horizon: str = Field(min_length=2, max_length=64)
    action: IntentAction
    side: IntentSide
    confidence: float = Field(ge=0, le=1)
    thesis: str = Field(min_length=3, max_length=600)
    invalidation: str = Field(min_length=3, max_length=600)
    expected_scenarios: list[IntentExpectedScenarioV0] = Field(min_length=1, max_length=3)
    used_packet_refs: list[str] = Field(min_length=1, max_length=8)
    used_memory_refs: list[str] = Field(default_factory=list, max_length=8)
    acknowledged_warnings: list[str] = Field(default_factory=list, max_length=12)
    requested_execution_semantics: RequestedExecutionSemanticsV0
    risk_note: str = Field(min_length=3, max_length=600)
    expiry_ts_ms: int = Field(ge=0)
    trace_id: str = Field(pattern=r"^trace_[a-z0-9_]{4,120}$")

    @model_validator(mode="after")
    def validate_scope(self):
        if self.source == "model_packet_benchmark":
            if not self.model_id or not self.model_call_ref or self.rank != "unranked_benchmark":
                raise ValueError("benchmark intents require model identity/call ref and benchmark rank")
        elif self.model_id is not None or self.model_call_ref is not None or self.rank != "unranked_no_model":
            raise ValueError("no-model intents forbid model identity")
        if self.expiry_ts_ms <= self.created_ts_ms:
            raise ValueError("expiry must be after creation")
        if self.action in {"WAIT", "OBSERVE", "NO_ACTION"} and self.side != "NONE":
            raise ValueError("non-mechanical actions require side NONE")
        if self.action == "DRY_RUN_OPEN_LONG" and self.side != "LONG":
            raise ValueError("open-long requires LONG side")
        if self.action == "DRY_RUN_OPEN_SHORT" and self.side != "SHORT":
            raise ValueError("open-short requires SHORT side")
        return self


__all__ = [
    "AgentIntentV0", "IntentAction", "IntentExpectedScenarioV0", "IntentSide",
    "RequestedExecutionSemanticsV0",
]
