from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetCutoverDecision,
    DatasetCutoverSummary,
)


class ObservationEvidenceSummary(BaseModel):
    """ObservationEnvelope-side report-only evidence counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_envelope_count: int = Field(default=0, ge=0)
    causal_valid_count: int = Field(default=0, ge=0)
    trainable_count: int = Field(default=0, ge=0)
    diagnostics_only_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)


class DecisionOutcomeEvidenceSummary(BaseModel):
    """DecisionOutcomeLedger-side report-only evidence counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_row_count: int = Field(default=0, ge=0)
    trainable_count: int = Field(default=0, ge=0)
    diagnostics_only_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    decision_id_join_count: int = Field(default=0, ge=0)
    rid_join_count: int = Field(default=0, ge=0)
    lifecycle_id_join_count: int = Field(default=0, ge=0)
    trade_id_join_count: int = Field(default=0, ge=0)
    no_join_count: int = Field(default=0, ge=0)
    terminal_joined_count: int = Field(default=0, ge=0)
    terminal_missing_count: int = Field(default=0, ge=0)
    synthetic_fallback_count: int = Field(default=0, ge=0)
    reward_valid_rows_count: int = Field(default=0, ge=0)


class EvidenceCollectionSummary(BaseModel):
    """Aggregate report-only evidence bundle summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: ObservationEvidenceSummary = Field(
        default_factory=ObservationEvidenceSummary
    )
    decision_outcome: DecisionOutcomeEvidenceSummary = Field(
        default_factory=DecisionOutcomeEvidenceSummary
    )
    invalid_reason_histogram: dict[str, int] = Field(default_factory=dict)
    reward_methodology: Optional[str] = Field(default=None)
    reward_methodology_present: bool = False
    reward_valid_requested: bool = False
    reward_valid: bool = False
    dataset_cutover_summary: Optional[DatasetCutoverSummary] = Field(
        default=None)
    dataset_cutover_decision: Optional[DatasetCutoverDecision] = Field(
        default=None
    )
    legacy_experiments_imported: bool = False
    legacy_experiments_modules: tuple[str, ...] = Field(default_factory=tuple)
    evidence_bundle_complete: bool = False


class EvidenceCollectionBundle(BaseModel):
    """Serializable report-only bundle emitted by the collector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str = Field(default="2026-04-30")
    generated_at_ms: int = Field(ge=1)
    summary: EvidenceCollectionSummary
