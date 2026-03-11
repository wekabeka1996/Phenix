"""
P9 evaluation / calibration / disagreement contracts.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


EvaluationObjectiveFamily = Literal["regime_supervision", "execution_quality"]
CalibrationStatus = Literal["available", "not_available"]
AdvisoryStatus = Literal["forbidden", "not_ready"]


class CalibrationBinSummary(BaseModel):
    """One calibration bin summary."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    bin_index: int
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_confidence: Optional[float] = None
    empirical_accuracy: Optional[float] = None


class ShadowEvaluationReport(BaseModel):
    """Objective-family-specific offline evaluation report."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    evaluation_id: str
    evaluated_at_ms: int
    objective_family: EvaluationObjectiveFamily
    time_window: Dict[str, Optional[int]]
    sample_counts: Dict[str, int]
    key_metrics: Dict[str, Any]
    unresolved_count: int
    diagnostics_only_count: int
    symbols_coverage: Dict[str, int]
    regimes_coverage: Dict[str, int]


class CalibrationReport(BaseModel):
    """Confidence / calibration summary for one objective family."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    report_id: str
    evaluated_at_ms: int
    objective_family: EvaluationObjectiveFamily
    confidence_source: str
    status: CalibrationStatus
    number_of_bins: int
    counts_per_bin: List[int]
    empirical_outcome_per_bin: List[Optional[float]]
    bin_summaries: List[CalibrationBinSummary]
    reliability_summary: Dict[str, Any]
    message: str


class ShadowDisagreementSample(BaseModel):
    """One comparison row between Aurora and neocortex shadow output."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    comparison_id: str
    event_ts_ms: int
    symbol: str
    shadow_action: str
    aurora_action: Optional[str] = None
    shadow_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    regime: Optional[str] = None
    severity: Optional[str] = None
    comparison_status: Literal["comparable", "unresolved"] = "comparable"


class DisagreementReport(BaseModel):
    """Deterministic shadow-vs-Aurora disagreement report."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    report_id: str
    evaluated_at_ms: int
    total_compared: int
    disagreement_count: int
    disagreement_rate: float
    by_symbol: Dict[str, int]
    by_regime: Dict[str, int]
    by_confidence_bucket: Dict[str, int]
    severity_buckets: Dict[str, int]
    unresolved_comparison_count: int


class AdvisoryReadinessPrereqReport(BaseModel):
    """Machine-readable advisory hardening prerequisite report."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    report_id: str
    evaluated_at_ms: int
    advisory_status: AdvisoryStatus
    production_shadow_status: Literal["ready", "not_ready"]
    satisfied_prereqs: List[str]
    unsatisfied_prereqs: List[str]
    blocking_reasons: List[str]
    recommended_next_packages: List[str]
