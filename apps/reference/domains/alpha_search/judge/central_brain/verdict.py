from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "2.0.0"
AUTHORITY_STATUS = "shadow_only"
CONFIDENCE_SOURCE = "judge_meta_scorer_v1"
BRIDGE_MODE = "none"

PolicyVerdict = Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]


class ConfidenceBand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float | None = Field(default=None, ge=0.0, le=1.0)
    max: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str | None = None

    @model_validator(mode="after")
    def validate_band_bounds(self) -> "ConfidenceBand":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("confidence_band.min must be <= confidence_band.max")
        return self


class VerdictRationale(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1)
    supporting_experts: list[str] = Field(default_factory=list)
    dissenting_experts: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)
    disagreement_state: str = Field(min_length=1)


class ScoreComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agreement_component: float
    expert_confidence_component: float
    regime_component: float
    historical_surface_component: float
    missingness_penalty: float = Field(ge=0.0)
    freshness_penalty: float = Field(ge=0.0)
    disagreement_penalty: float = Field(ge=0.0)
    final_score_before_clamp: float
    final_confidence: float = Field(ge=0.0, le=1.0)


class PolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_mode: str | None = None
    bridge_mode: Literal["none"] = BRIDGE_MODE
    source_envelope_version: Literal["2.0.0"] = SCHEMA_VERSION


class VerdictSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_id: str = Field(min_length=1)
    decision_id: str | None = None
    rid: str | None = None
    cycle_key: str | None = None


class JudgePolicyVerdictV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0.0"] = SCHEMA_VERSION
    verdict_id: str = Field(min_length=1)
    envelope_id: str = Field(min_length=1)
    created_ts_ms: int = Field(ge=0)
    symbol: str = Field(min_length=1)
    question_type: Literal["entry", "lifecycle"]
    authority_status: Literal["shadow_only"] = AUTHORITY_STATUS
    applied: Literal[False] = False
    verdict: PolicyVerdict
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_source: Literal["judge_meta_scorer_v1"] = CONFIDENCE_SOURCE
    confidence_band: ConfidenceBand
    rationale: VerdictRationale
    score_components: ScoreComponents
    policy_context: PolicyContext
    source_refs: VerdictSourceRefs

    @model_validator(mode="after")
    def validate_confidence_matches_components(self) -> "JudgePolicyVerdictV2":
        if self.confidence != self.score_components.final_confidence:
            raise ValueError("confidence must equal score_components.final_confidence")
        if self.envelope_id != self.source_refs.envelope_id:
            raise ValueError("envelope_id must match source_refs.envelope_id")
        return self
