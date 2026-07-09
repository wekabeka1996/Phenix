"""Agent Trading Session Memory — Durable session memory layout for arena agents.

Provides append-only session memory with token-budget metadata tracking,
reflection entries, feature trust notes, compact summary, and next-session
carryover markdown generation.

No silent overwrites. Every reflection is linked to session/agent/time.
Token budgets are metadata counters — not tokenizer calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# ── Literal types ──────────────────────────────────────────────────────────────

ReflectionKind = Literal[
    "opening_assumptions",
    "feature_trust_update",
    "decision_review",
    "session_self_audit",
    "behavior_drift",
]


# ── Sub-models ─────────────────────────────────────────────────────────────────


class FeatureTrustNote(BaseModel):
    """Records a shift in how much an agent trusts a specific signal or feature."""

    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1, description="Name of the feature/signal being assessed.")
    trust_delta: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Change in trust level: -1.0 (complete distrust) to +1.0 (full trust).",
    )
    reason: str = Field(..., min_length=1, description="Rationale for the trust shift.")
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="Event IDs that provide evidence for this trust assessment.",
    )
    observed_effect: str = Field(
        ...,
        min_length=1,
        description="What actually happened in the market/session that informed this note.",
    )


class ReflectionEntry(BaseModel):
    """A single agent reflection linked to session, agent identity, and time."""

    model_config = ConfigDict(extra="forbid")

    reflection_id: str = Field(..., min_length=1, description="Unique reflection identifier.")
    session_id: str = Field(..., min_length=1, description="Session this reflection belongs to.")
    agent_id: str = Field(..., min_length=1, description="Agent that produced this reflection.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of reflection creation.",
    )
    kind: ReflectionKind = Field(..., description="Category of this reflection.")
    related_event_ids: list[str] = Field(
        default_factory=list,
        description="FSM event IDs this reflection relates to.",
    )
    related_command_ids: list[str] = Field(
        default_factory=list,
        description="Command IDs this reflection relates to.",
    )
    feature_influence_notes: list[FeatureTrustNote] = Field(
        default_factory=list,
        description="Feature trust deltas observed at time of reflection.",
    )
    confidence_before: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Agent confidence score before this decision (0–1). Optional.",
    )
    confidence_after: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Agent confidence score after this decision (0–1). Optional.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Full reflection text. Should be substantive and attributable.",
    )


class AgentTradingSessionMemory(BaseModel):
    """Durable append-only trading session memory for one agent session.

    Token budgets are tracked as metadata integers — not live tokenizer calls.
    All writes are append-only: reflection_refs, event_refs, trade_refs,
    active_context_refs, and reflections cannot be overwritten.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, description="Schema version for forward compatibility.")
    session_id: str = Field(..., min_length=1, description="Globally unique session identifier.")
    agent_id: str = Field(..., min_length=1, description="Identifier of the agent owning this session.")
    agent_number: int = Field(..., ge=0, description="Canonical agent number (non-negative integer).")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the session was started.",
    )
    instruction_manifest_version: str = Field(
        ...,
        min_length=1,
        description="Version of the instruction manifest in effect at session start.",
    )

    # Token budget metadata (not real tokenizer; tracked as counters)
    context_budget_target_tokens: int = Field(
        default=1_000_000,
        ge=1,
        description="Target token budget for full context window (metadata, not tokenizer).",
    )
    reflection_budget_target_tokens: int = Field(
        default=300_000,
        ge=1,
        description="Token budget reserved for self-reflection, trust analysis, decision impact.",
    )
    tokens_consumed_estimate: int = Field(
        default=0,
        ge=0,
        description="Running estimate of tokens consumed (incremented on append, never decremented).",
    )

    # Append-only reference lists
    active_context_refs: list[str] = Field(
        default_factory=list,
        description="References to active context documents/snapshots for this session.",
    )
    event_refs: list[str] = Field(
        default_factory=list,
        description="FSM event IDs observed during this session (append-only).",
    )
    trade_refs: list[str] = Field(
        default_factory=list,
        description="Trade/order identifiers produced during this session (append-only).",
    )
    reflection_refs: list[str] = Field(
        default_factory=list,
        description="reflection_id list for quick lookup (append-only, mirrors reflections).",
    )

    # Reflections store
    reflections: list[ReflectionEntry] = Field(
        default_factory=list,
        description="Ordered append-only list of reflection entries.",
    )

    @model_validator(mode="after")
    def reflection_refs_consistent(self) -> "AgentTradingSessionMemory":
        """Ensure reflection_refs matches the IDs present in reflections list."""
        ids_in_list = [r.reflection_id for r in self.reflections]
        # reflection_refs is a subset of ids_in_list (it may be populated separately)
        for ref in self.reflection_refs:
            if ref not in ids_in_list:
                raise ValueError(
                    f"reflection_ref '{ref}' not found in reflections list. "
                    "Use append_reflection() to keep them in sync."
                )
        return self

    # ── Append-only mutation helpers ───────────────────────────────────────────

    def append_reflection(self, entry: ReflectionEntry, token_estimate: int = 0) -> None:
        """Append a reflection entry. Raises if reflection_id already exists (no silent overwrite)."""
        existing_ids = {r.reflection_id for r in self.reflections}
        if entry.reflection_id in existing_ids:
            raise ValueError(
                f"Duplicate reflection_id='{entry.reflection_id}'. "
                "append_reflection() is append-only; silent overwrites are forbidden."
            )
        if entry.session_id != self.session_id:
            raise ValueError(
                f"ReflectionEntry.session_id='{entry.session_id}' does not match "
                f"session session_id='{self.session_id}'."
            )
        if entry.agent_id != self.agent_id:
            raise ValueError(
                f"ReflectionEntry.agent_id='{entry.agent_id}' does not match "
                f"session agent_id='{self.agent_id}'."
            )
        self.reflections.append(entry)
        if entry.reflection_id not in self.reflection_refs:
            self.reflection_refs.append(entry.reflection_id)
        if token_estimate > 0:
            self.tokens_consumed_estimate += token_estimate
        logger.debug(
            "Appended reflection reflection_id=%s kind=%s session_id=%s",
            entry.reflection_id,
            entry.kind,
            self.session_id,
        )

    def append_event_ref(self, event_id: str) -> None:
        """Append an FSM event reference. Idempotent (no duplicate refs)."""
        if event_id not in self.event_refs:
            self.event_refs.append(event_id)

    def append_trade_ref(self, trade_id: str) -> None:
        """Append a trade/order reference. Idempotent (no duplicate refs)."""
        if trade_id not in self.trade_refs:
            self.trade_refs.append(trade_id)

    def append_context_ref(self, context_ref: str) -> None:
        """Append an active context document reference. Idempotent."""
        if context_ref not in self.active_context_refs:
            self.active_context_refs.append(context_ref)

    # ── Summary / carryover output ─────────────────────────────────────────────

    def compact_summary(self) -> dict:
        """Generate a compact session summary dict for cross-session handoff or logging."""
        kinds: dict[str, int] = {}
        for r in self.reflections:
            kinds[r.kind] = kinds.get(r.kind, 0) + 1

        feature_trust: dict[str, float] = {}
        for r in self.reflections:
            for note in r.feature_influence_notes:
                feature_trust[note.feature_name] = (
                    feature_trust.get(note.feature_name, 0.0) + note.trust_delta
                )

        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_number": self.agent_number,
            "started_at": self.started_at.isoformat(),
            "instruction_manifest_version": self.instruction_manifest_version,
            "schema_version": self.schema_version,
            "context_budget_target_tokens": self.context_budget_target_tokens,
            "reflection_budget_target_tokens": self.reflection_budget_target_tokens,
            "tokens_consumed_estimate": self.tokens_consumed_estimate,
            "total_reflections": len(self.reflections),
            "reflection_kind_counts": kinds,
            "total_event_refs": len(self.event_refs),
            "total_trade_refs": len(self.trade_refs),
            "total_context_refs": len(self.active_context_refs),
            "cumulative_feature_trust_deltas": feature_trust,
        }

    def next_session_carryover_md(self) -> str:
        """Generate a markdown carryover document for the next session.

        Contains: identity, reflection summary, feature trust notes, open trades,
        and a list of last reflections for continuity. Suitable for injection
        into the next session's opening context.
        """
        summary = self.compact_summary()
        lines: list[str] = [
            "# Agent Session Carryover",
            "",
            f"**Session ID**: `{self.session_id}`",
            f"**Agent ID**: `{self.agent_id}` (Agent #{self.agent_number})",
            f"**Started At**: {self.started_at.isoformat()}",
            f"**Instruction Manifest**: `{self.instruction_manifest_version}`",
            "",
            "## Token Budget Status",
            f"- Context budget target: {self.context_budget_target_tokens:,} tokens",
            f"- Reflection budget target: {self.reflection_budget_target_tokens:,} tokens",
            f"- Consumed estimate: {self.tokens_consumed_estimate:,} tokens",
            "",
            "## Session Activity",
            f"- Total reflections: {summary['total_reflections']}",
            f"- Event refs: {summary['total_event_refs']}",
            f"- Trade refs: {summary['total_trade_refs']}",
            f"- Context refs: {summary['total_context_refs']}",
            "",
        ]

        # Reflection kind breakdown
        if summary["reflection_kind_counts"]:
            lines.append("## Reflection Breakdown")
            for kind, count in sorted(summary["reflection_kind_counts"].items()):
                lines.append(f"- `{kind}`: {count}")
            lines.append("")

        # Feature trust summary
        trust = summary["cumulative_feature_trust_deltas"]
        if trust:
            lines.append("## Cumulative Feature Trust Deltas")
            lines.append("*(Positive = more trusted, Negative = less trusted this session)*")
            lines.append("")
            for feature, delta in sorted(trust.items(), key=lambda x: -abs(x[1])):
                sign = "+" if delta >= 0 else ""
                lines.append(f"- `{feature}`: {sign}{delta:.3f}")
            lines.append("")

        # Open trade refs
        if self.trade_refs:
            lines.append("## Open / Observed Trade References")
            for t in self.trade_refs:
                lines.append(f"- `{t}`")
            lines.append("")

        # Last 3 reflections for continuity
        recent = self.reflections[-3:] if len(self.reflections) >= 3 else self.reflections
        if recent:
            lines.append("## Last Reflections (Continuity Context)")
            for r in recent:
                lines.append(f"### [{r.kind}] `{r.reflection_id}` — {r.created_at.isoformat()}")
                lines.append(r.content)
                if r.confidence_before is not None or r.confidence_after is not None:
                    before = f"{r.confidence_before:.2f}" if r.confidence_before is not None else "n/a"
                    after = f"{r.confidence_after:.2f}" if r.confidence_after is not None else "n/a"
                    lines.append(f"*Confidence: {before} → {after}*")
                lines.append("")

        lines.append("---")
        lines.append("*Carryover generated by AgentTradingSessionMemory.next_session_carryover_md()*")

        return "\n".join(lines)
