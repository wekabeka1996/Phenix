"""Append-only trading-session memory for arena agents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReflectionKind = Literal[
    "opening_assumptions",
    "feature_trust_update",
    "decision_review",
    "session_self_audit",
    "behavior_drift",
]


def utc_dt() -> datetime:
    return datetime.now(timezone.utc)


class FeatureTrustNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1)
    trust_delta: float = Field(..., ge=-1.0, le=1.0)
    reason: str = Field(..., min_length=1)
    supporting_event_ids: list[str] = Field(default_factory=list)
    observed_effect: str = Field(..., min_length=1)


class ReflectionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reflection_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=utc_dt)
    kind: ReflectionKind
    related_event_ids: list[str] = Field(default_factory=list)
    related_command_ids: list[str] = Field(default_factory=list)
    feature_influence_notes: list[FeatureTrustNote] = Field(default_factory=list)
    confidence_before: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_after: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    content: str = Field(..., min_length=1)


class AgentTradingSessionMemory(BaseModel):
    """Durable append-only memory for one agent in one Cockpit session."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    started_at: datetime = Field(default_factory=utc_dt)
    instruction_manifest_version: str = Field(..., min_length=1)
    context_budget_target_tokens: int = Field(default=1_000_000, ge=1)
    reflection_budget_target_tokens: int = Field(default=300_000, ge=1)
    tokens_consumed_estimate: int = Field(default=0, ge=0)
    active_context_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    trade_refs: list[str] = Field(default_factory=list)
    reflection_refs: list[str] = Field(default_factory=list)
    reflections: list[ReflectionEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def reflection_refs_consistent(self) -> "AgentTradingSessionMemory":
        known = {entry.reflection_id for entry in self.reflections}
        missing = [ref for ref in self.reflection_refs if ref not in known]
        if missing:
            raise ValueError(f"reflection_refs missing entries: {missing}")
        return self

    def append_reflection(self, entry: ReflectionEntry, *, token_estimate: int = 0) -> None:
        if entry.session_id != self.session_id:
            raise ValueError("reflection session_id does not match memory session")
        if entry.agent_id != self.agent_id:
            raise ValueError("reflection agent_id does not match memory agent")
        if any(existing.reflection_id == entry.reflection_id for existing in self.reflections):
            raise ValueError(f"duplicate reflection_id: {entry.reflection_id}")
        self.reflections.append(entry)
        self.reflection_refs.append(entry.reflection_id)
        if token_estimate > 0:
            self.tokens_consumed_estimate += token_estimate

    def append_event_ref(self, event_id: str) -> None:
        event_id = str(event_id or "").strip()
        if event_id and event_id not in self.event_refs:
            self.event_refs.append(event_id)

    def append_trade_ref(self, trade_id: str) -> None:
        trade_id = str(trade_id or "").strip()
        if trade_id and trade_id not in self.trade_refs:
            self.trade_refs.append(trade_id)

    def append_context_ref(self, context_ref: str) -> None:
        context_ref = str(context_ref or "").strip()
        if context_ref and context_ref not in self.active_context_refs:
            self.active_context_refs.append(context_ref)

    def compact_summary(self) -> dict:
        kinds: dict[str, int] = {}
        for entry in self.reflections:
            kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_number": self.agent_number,
            "started_at": self.started_at.isoformat(),
            "instruction_manifest_version": self.instruction_manifest_version,
            "tokens_consumed_estimate": self.tokens_consumed_estimate,
            "total_reflections": len(self.reflections),
            "reflection_kind_counts": kinds,
            "total_event_refs": len(self.event_refs),
            "total_trade_refs": len(self.trade_refs),
            "total_context_refs": len(self.active_context_refs),
        }

    def next_session_carryover_md(self) -> str:
        summary = self.compact_summary()
        lines = [
            "# Agent Session Carryover",
            "",
            f"Session ID: `{self.session_id}`",
            f"Agent ID: `{self.agent_id}`",
            f"Agent Number: `{self.agent_number}`",
            f"Instruction Manifest: `{self.instruction_manifest_version}`",
            "",
            "## Summary",
            f"- Reflections: {summary['total_reflections']}",
            f"- Event refs: {summary['total_event_refs']}",
            f"- Trade refs: {summary['total_trade_refs']}",
            f"- Context refs: {summary['total_context_refs']}",
            "",
            "## Recent Reflections",
        ]
        for entry in self.reflections[-3:]:
            lines.append(f"- `{entry.kind}` `{entry.reflection_id}`: {entry.content}")
        return "\n".join(lines)
