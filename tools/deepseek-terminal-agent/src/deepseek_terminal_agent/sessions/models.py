"""Structured session, model, and artifact primitives for the workbench runtime."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ThinkingType = Literal["enabled", "disabled"]
ReasoningEffort = Literal["high", "max"]
ResponseFormatType = Literal["text", "json_object"]
ToolMode = Literal["auto", "none", "required"]
ModelSource = Literal["live", "cached", "static_fallback"]
TurnRole = Literal["user", "assistant", "tool", "system"]
SessionStatus = Literal["idle", "running", "completed", "failed", "cancelled"]
ArtifactType = Literal["evidence_pack", "test_report",
                       "log_scan", "context_pack", "summary",
                       "doc_draft", "critic_review"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class DeepSeekModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    model_id: str = Field(..., min_length=1)
    source: ModelSource = "live"
    name: Optional[str] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    source: ModelSource
    models: list[DeepSeekModelInfo] = Field(default_factory=list)
    warning: Optional[str] = None
    refreshed_at: str = Field(default_factory=utc_now_iso)


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    profile_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    thinking_type: ThinkingType = "enabled"
    reasoning_effort: ReasoningEffort = "high"
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: int = 8192
    response_format: ResponseFormatType = "text"
    stream: bool = False
    tool_mode: ToolMode = "auto"
    max_iterations: int = 20
    command_timeout_sec: int = 120
    max_command_output_chars: int = 20000
    context_budget_chars: int = 800000
    memory_atom_budget: int = 8
    recent_turns_budget: int = 12
    tool_output_budget_chars: int = 60000

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, value: float) -> float:
        if not 0.0 <= value <= 2.0:
            raise ValueError("temperature must be within 0..2")
        return value

    @field_validator("top_p")
    @classmethod
    def top_p_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("top_p must be within 0..1")
        return value

    @field_validator(
        "max_tokens",
        "max_iterations",
        "command_timeout_sec",
        "max_command_output_chars",
        "context_budget_chars",
        "memory_atom_budget",
        "recent_turns_budget",
        "tool_output_budget_chars",
    )
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump()


class ChatSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    session_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    active_profile: ModelProfile
    pinned_memory_atom_ids: list[str] = Field(default_factory=list)
    current_spine_id: Optional[str] = None
    status: SessionStatus = "idle"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    turn_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    role: TurnRole
    visible_content: str = ""
    internal_reasoning_content: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    model_id: Optional[str] = None
    model_profile_snapshot: Optional[dict[str, Any]] = None
    created_at: str = Field(default_factory=utc_now_iso)
    token_usage: Optional[TokenUsage] = None
    source_run_id: Optional[str] = None
    is_compacted: bool = False
    compacted_into_spine_id: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump()
        payload.pop("internal_reasoning_content", None)
        return payload


class SessionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    message: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionSpine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    spine_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    decisions: list[str] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    source_turn_ids: list[str] = Field(default_factory=list)


class ArtifactFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    claim: str = Field(..., min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within 0..1")
        return value


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    artifact_id: str = Field(..., min_length=1)
    artifact_type: ArtifactType
    parent_session_id: str = Field(..., min_length=1)
    child_session_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    findings: list[ArtifactFinding] = Field(default_factory=list)
    files_read: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_next_context: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    trusted: bool = False

    def render_compact(self, *, max_findings: int = 5, max_refs: int = 3) -> str:
        lines = [
            f"Artifact {self.artifact_id} ({self.artifact_type})",
            f"Role: {self.role}",
            f"Task: {self.task}",
            f"Trust: {'trusted' if self.trusted else 'untrusted'}",
            f"Summary: {self.summary}",
        ]
        if self.findings:
            lines.append("Findings:")
            for finding in self.findings[:max_findings]:
                lines.append(
                    f"- {finding.claim} [confidence={finding.confidence:.2f}]"
                )
                for ref in finding.evidence_refs[:max_refs]:
                    lines.append(f"  evidence: {ref}")
        if self.risks:
            lines.append("Risks:")
            lines.extend(f"- {item}" for item in self.risks[:3])
        if self.open_questions:
            lines.append("Open Questions:")
            lines.extend(f"- {item}" for item in self.open_questions[:3])
        return "\n".join(lines)

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.model_dump()
        payload["compact_summary"] = self.render_compact()
        return payload


class ContextReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    included_sections: list[str] = Field(default_factory=list)
    approximate_chars: int = 0
    approximate_tokens: int = 0
    section_char_totals: dict[str, int] = Field(default_factory=dict)
    memory_atoms_included: list[str] = Field(default_factory=list)
    artifacts_included: list[str] = Field(default_factory=list)
    recent_turns_included: list[str] = Field(default_factory=list)
    omitted_turns_count: int = 0
    compacted_turns_count: int = 0
    warnings: list[str] = Field(default_factory=list)
