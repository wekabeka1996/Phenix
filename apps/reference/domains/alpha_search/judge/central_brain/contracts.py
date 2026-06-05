from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.domains.regime_detector.context_envelope import (
    RegimeContextEnvelope,
)
from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    AuroraExpertOutput,
)
from apps.reference.domains.strategies.runtimes.md_amr.native_expert_adapter import (
    MDAMRExpertOutput,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.native_expert_adapter import (
    MeanReversionExpertOutput,
)


SCHEMA_VERSION = "2.0.0"
AUTHORITY_STATUS = "evidence_only"
BUILDER_VERSION = "judge_evidence_envelope_builder_v1"

QuestionType = Literal["entry", "lifecycle"]
FreshnessState = Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]
AgreementState = Literal[
    "AGREE_LONG",
    "AGREE_SHORT",
    "DISAGREE",
    "SINGLE_EXPERT",
    "NO_EXPERTS",
    "UNKNOWN",
]


class AgreementStateScores(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agree: float = Field(ge=0.0, le=1.0)
    single_expert: float = Field(ge=0.0, le=1.0)
    unknown: float = Field(ge=0.0, le=1.0)
    disagree: float = Field(ge=0.0, le=1.0)
    no_experts: float = Field(ge=0.0, le=1.0)


class VerdictThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    open_long_min_confidence: float = Field(ge=0.0, le=1.0)
    open_short_min_confidence: float = Field(ge=0.0, le=1.0)
    suppress_max_confidence: float = Field(ge=0.0, le=1.0)
    unknown_max_evidence_score: float = Field(ge=0.0, le=1.0)


class StalePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stale_regime_penalty: float = Field(ge=0.0)
    stale_market_penalty: float = Field(ge=0.0)
    missing_execution_readiness_penalty: float = Field(ge=0.0)
    missing_risk_context_penalty: float = Field(ge=0.0)
    missing_portfolio_context_penalty: float = Field(ge=0.0)


class HardUnknownConditions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    no_strategy_experts: bool
    missing_regime_context: bool
    missing_market_context: bool


class JudgeMetaScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    agreement_weight: float = Field(ge=0.0)
    confidence_weight: float = Field(ge=0.0)
    regime_weight: float = Field(ge=0.0)
    historical_surface_weight: float = Field(ge=0.0)
    missingness_penalty_weight: float = Field(ge=0.0)
    freshness_penalty_weight: float = Field(ge=0.0)
    disagreement_penalty_weight: float = Field(ge=0.0)
    no_expert_penalty: float = Field(ge=0.0)
    unknown_cap: float = Field(ge=0.0, le=1.0)
    min_confidence: float = Field(ge=0.0, le=1.0)
    max_confidence: float = Field(ge=0.0, le=1.0)
    verdict_thresholds: VerdictThresholds
    stale_policy: StalePolicy
    hard_unknown_conditions: HardUnknownConditions
    agreement_state_scores: AgreementStateScores

    @model_validator(mode="after")
    def validate_confidence_bounds(self) -> "JudgeMetaScoringConfig":
        if self.min_confidence > self.max_confidence:
            raise ValueError("min_confidence must be <= max_confidence")
        positive_weights = (
            self.agreement_weight,
            self.confidence_weight,
            self.regime_weight,
            self.historical_surface_weight,
        )
        if not any(weight > 0 for weight in positive_weights):
            raise ValueError("at least one positive scoring weight is required")
        return self


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    ts_ms: int = Field(ge=0)
    data_freshness_state: FreshnessState
    source_refs: dict[str, Any] = Field(default_factory=dict)


class RegimeContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    present: bool
    envelope: RegimeContextEnvelope | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_presence(self) -> "RegimeContextBlock":
        if self.present and self.envelope is None:
            raise ValueError("present regime_context requires envelope")
        if not self.present and not self.missing_reason:
            raise ValueError("missing regime_context requires missing_reason")
        return self


class StrategyOpinions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    aurora: AuroraExpertOutput | None = None
    mean_reversion: MeanReversionExpertOutput | None = None
    md_amr: MDAMRExpertOutput | None = None


class RiskContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    present: bool
    exposure_state: str | None = None
    risk_state: str | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_missing_reason(self) -> "RiskContextBlock":
        if not self.present and not self.missing_reason:
            raise ValueError("missing risk_context requires missing_reason")
        return self


class PortfolioContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    present: bool
    position_state: str | None = None
    symbol_exposure: float | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_missing_reason(self) -> "PortfolioContextBlock":
        if not self.present and not self.missing_reason:
            raise ValueError("missing portfolio_context requires missing_reason")
        return self


class ExecutionReadinessBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    present: bool
    readiness_state: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_missing_reason(self) -> "ExecutionReadinessBlock":
        if not self.present and not self.missing_reason:
            raise ValueError("missing execution_readiness requires missing_reason")
        return self


class HistoricalSurfaceEvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    present: bool
    surface_key: str | None = None
    sample_count: int | None = Field(default=None, ge=0)
    expectancy_net: float | None = None
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def validate_missing_reason(self) -> "HistoricalSurfaceEvidenceBlock":
        if not self.present and not self.missing_reason:
            raise ValueError(
                "missing historical_surface_evidence requires missing_reason"
            )
        return self


class FreshnessMissingnessMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    per_block: dict[str, str] = Field(default_factory=dict)
    per_field: dict[str, str] = Field(default_factory=dict)


class DisagreementMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    side_opinions: dict[str, str] = Field(default_factory=dict)
    confidence_by_expert: dict[str, float | None] = Field(default_factory=dict)
    agreement_state: AgreementState
    notes: list[str] = Field(default_factory=list)


class EnvelopeProvenanceV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_contract_versions: dict[str, str] = Field(default_factory=dict)
    builder_version: str = Field(min_length=1)
    source_refs: dict[str, Any] = Field(default_factory=dict)


class JudgeEvidenceEnvelopeV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0.0"] = SCHEMA_VERSION
    envelope_id: str = Field(min_length=1)
    created_ts_ms: int = Field(ge=0)
    cycle_key: str | None = None
    decision_id: str | None = None
    rid: str | None = None
    symbol: str = Field(min_length=1)
    question_type: QuestionType
    authority_status: Literal["evidence_only"] = AUTHORITY_STATUS
    runtime_mode: str | None = None
    market_context: MarketContext
    regime_context: RegimeContextBlock
    strategy_opinions: StrategyOpinions
    risk_context: RiskContextBlock
    portfolio_context: PortfolioContextBlock
    execution_readiness: ExecutionReadinessBlock
    historical_surface_evidence: HistoricalSurfaceEvidenceBlock
    freshness_missingness_map: FreshnessMissingnessMap
    disagreement_map: DisagreementMap
    provenance: EnvelopeProvenanceV2
