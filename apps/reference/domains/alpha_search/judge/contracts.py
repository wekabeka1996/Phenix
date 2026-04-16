"""
LLM Judge Phase 1 — Typed Contracts

Canonical contract models for the LLM Judge bicameral policy cortex.
Authority: docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md

Phase 1 scope: type surface only. No runtime evaluation. No event emission.

SSOT: Pydantic-first. JSON schemas kept in sync manually
      (cross-validated by test_serialization.py).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Canonical vocabulary types (frozen by concept authority)
# ---------------------------------------------------------------------------

EntryVerdict = Literal["OPEN_LONG", "OPEN_SHORT",
                       "NO_ENTRY", "SUPPRESS", "UNKNOWN"]

LifecycleVerdict = Literal["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"]

CortexMode = Literal[
    "off",
    "shadow",
    "hybrid_advisory",
    "guarded_entry_authority",
    "guarded_lifecycle_authority",
]


# ---------------------------------------------------------------------------
# Supporting sub-models
# ---------------------------------------------------------------------------

class PositionContextSnapshot(BaseModel):
    """Current position state for lifecycle evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_position: bool
    side: Optional[Literal["LONG", "SHORT"]] = None
    unrealized_pnl_pct: Optional[float] = None
    hold_duration_sec: Optional[int] = Field(default=None, ge=0)
    bracket_state: Optional[Literal["ACTIVE", "PENDING", "NONE"]] = None


class EnvelopeProvenance(BaseModel):
    """Traceability metadata for evidence assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cortex_version: str = Field(..., min_length=1)
    prompt_template_id: Optional[str] = None  # Phase 2+
    model_version: Optional[str] = None  # Phase 2+
    assembly_source: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# ExpertOutput
# ---------------------------------------------------------------------------

class ExpertOutput(BaseModel):
    """Typed output from one expert perspective on a trading decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expert_id: str = Field(..., min_length=1)
    expert_version: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    entry_verdict: Optional[EntryVerdict] = None
    lifecycle_verdict: Optional[LifecycleVerdict] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    signal_direction: Optional[Literal["LONG", "SHORT", "NEUTRAL"]] = None
    reasoning: List[str] = Field(..., min_length=1)
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def validate_verdict_xor(self) -> ExpertOutput:
        """Exactly one of entry_verdict or lifecycle_verdict must be set."""
        has_entry = self.entry_verdict is not None
        has_lifecycle = self.lifecycle_verdict is not None
        if has_entry == has_lifecycle:
            raise ValueError(
                "ExpertOutput requires exactly one of entry_verdict or "
                "lifecycle_verdict to be set (XOR)"
            )
        return self

    @model_validator(mode="after")
    def validate_suppress_reason(self) -> ExpertOutput:
        """SUPPRESS verdict requires reasoning (already enforced by min_length=1,
        but this makes the semantic intent explicit)."""
        verdict = self.entry_verdict or self.lifecycle_verdict
        if verdict == "SUPPRESS" and len(self.reasoning) < 1:
            raise ValueError(
                "SUPPRESS verdict requires at least one reasoning item"
            )
        return self


# ---------------------------------------------------------------------------
# ChamberAggregate
# ---------------------------------------------------------------------------

class ChamberAggregate(BaseModel):
    """Aggregation of all expert outputs for one evaluation cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chamber_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    expert_outputs: List[ExpertOutput] = Field(default_factory=list)
    expert_count: int = Field(..., ge=0)
    responding_count: int = Field(..., ge=0)
    abstaining_count: int = Field(..., ge=0)
    consensus_direction: Optional[Literal["LONG",
                                          "SHORT", "NEUTRAL", "SPLIT"]] = None
    consensus_strength: float = Field(..., ge=0.0, le=1.0)
    admissibility: Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def validate_counts(self) -> ChamberAggregate:
        """responding_count + abstaining_count <= expert_count."""
        if self.responding_count + self.abstaining_count > self.expert_count:
            raise ValueError(
                f"responding_count ({self.responding_count}) + "
                f"abstaining_count ({self.abstaining_count}) must be <= "
                f"expert_count ({self.expert_count})"
            )
        return self

    @model_validator(mode="after")
    def validate_expert_output_scope(self) -> ChamberAggregate:
        """All expert_outputs must match the chamber's verdict_scope."""
        for eo in self.expert_outputs:
            if self.verdict_scope == "ENTRY" and eo.entry_verdict is None:
                raise ValueError(
                    f"ENTRY chamber contains expert output from "
                    f"'{eo.expert_id}' without entry_verdict"
                )
            if self.verdict_scope == "LIFECYCLE" and eo.lifecycle_verdict is None:
                raise ValueError(
                    f"LIFECYCLE chamber contains expert output from "
                    f"'{eo.expert_id}' without lifecycle_verdict"
                )
        return self


# ---------------------------------------------------------------------------
# JudgeEvidenceEnvelope
# ---------------------------------------------------------------------------

class JudgeEvidenceEnvelope(BaseModel):
    """Typed, bounded, timestamped evidence package for judge evaluation.

    Design note: Does NOT duplicate transport-envelope metadata (rid, span_id,
    ts, why, idempotent_key, mode) already carried by vfoundation Message.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    chamber_aggregate: ChamberAggregate
    strategy_id: str = Field(..., min_length=1)
    regime: Optional[str] = None
    regime_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    features_ref: Optional[str] = None
    position_context: Optional[PositionContextSnapshot] = None
    freshness_deadline_ms: int = Field(..., gt=0)
    provenance: EnvelopeProvenance
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def validate_lifecycle_requires_position(self) -> JudgeEvidenceEnvelope:
        """LIFECYCLE scope requires position_context."""
        if self.verdict_scope == "LIFECYCLE" and self.position_context is None:
            raise ValueError(
                "verdict_scope='LIFECYCLE' requires position_context to be set"
            )
        return self

    @model_validator(mode="after")
    def validate_scope_consistency(self) -> JudgeEvidenceEnvelope:
        """chamber_aggregate.verdict_scope must match envelope verdict_scope."""
        if self.chamber_aggregate.verdict_scope != self.verdict_scope:
            raise ValueError(
                f"Envelope verdict_scope '{self.verdict_scope}' does not match "
                f"chamber_aggregate verdict_scope "
                f"'{self.chamber_aggregate.verdict_scope}'"
            )
        return self


# ---------------------------------------------------------------------------
# JudgeVerdict
# ---------------------------------------------------------------------------

class JudgeVerdict(BaseModel):
    """Final judge policy verdict for a specific evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict_id: str = Field(..., min_length=1)
    envelope_id: str = Field(..., min_length=1)
    chamber_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    entry_verdict: Optional[EntryVerdict] = None
    lifecycle_verdict: Optional[LifecycleVerdict] = None
    suppression_reason: Optional[str] = None
    suppression_code: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: List[str] = Field(..., min_length=1)
    dissent_noted: bool
    authority_mode: CortexMode
    applied: bool
    strategy_id: str = Field(..., min_length=1)
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def validate_verdict_scope_xor(self) -> JudgeVerdict:
        """Verdict-scope-consistent XOR: ENTRY requires entry_verdict,
        LIFECYCLE requires lifecycle_verdict."""
        if self.verdict_scope == "ENTRY":
            if self.entry_verdict is None:
                raise ValueError(
                    "verdict_scope='ENTRY' requires entry_verdict to be set"
                )
            if self.lifecycle_verdict is not None:
                raise ValueError(
                    "verdict_scope='ENTRY' requires lifecycle_verdict to be None"
                )
        elif self.verdict_scope == "LIFECYCLE":
            if self.lifecycle_verdict is None:
                raise ValueError(
                    "verdict_scope='LIFECYCLE' requires lifecycle_verdict to be set"
                )
            if self.entry_verdict is not None:
                raise ValueError(
                    "verdict_scope='LIFECYCLE' requires entry_verdict to be None"
                )
        return self

    @model_validator(mode="after")
    def validate_suppress_requires_reason(self) -> JudgeVerdict:
        """SUPPRESS verdict requires suppression_reason."""
        verdict = self.entry_verdict or self.lifecycle_verdict
        if verdict == "SUPPRESS":
            if not self.suppression_reason:
                raise ValueError(
                    "SUPPRESS verdict requires non-empty suppression_reason"
                )
        return self

    @model_validator(mode="after")
    def validate_applied_mode_consistency(self) -> JudgeVerdict:
        """off/shadow modes require applied=False."""
        if self.authority_mode in ("off", "shadow") and self.applied:
            raise ValueError(
                f"authority_mode='{self.authority_mode}' requires applied=False"
            )
        return self
