"""
P6 dataset hygiene / provenance contracts.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ObjectiveFamily = Literal[
    "representation",
    "regime_supervision",
    "execution_quality",
    "policy",
]
EligibilityStatus = Literal[
    "trainable",
    "eval_only",
    "diagnostics_only",
    "quarantined",
    "rejected",
]


class DatasetSampleProvenance(BaseModel):
    """Canonical provenance metadata for one dataset-eligible sample."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    dataset_sample_id: str
    objective_family: ObjectiveFamily
    source_type: str
    source_ref: str
    source_event_type: str
    event_ts_ms: int
    symbol: Optional[str] = None
    lifecycle_id: Optional[str] = None
    trade_id: Optional[str] = None
    ingestion_mode: Optional[str] = None
    legacy_causal_mode: bool = False
    sequence_contract_mode: Optional[str] = None
    policy_training_mode: Optional[str] = None
    eligibility_status: EligibilityStatus
    exclusion_reasons: List[str] = Field(default_factory=list)
    quarantine_reasons: List[str] = Field(default_factory=list)


class DatasetEvaluatedSample(BaseModel):
    """Raw sample plus explicit dataset eligibility assessment."""

    model_config = ConfigDict(extra='forbid')

    objective_family: ObjectiveFamily
    eligibility_status: EligibilityStatus
    is_trainable: bool
    sample: Dict[str, Any]
    provenance: DatasetSampleProvenance


class DatasetSplitManifest(BaseModel):
    """One deterministic time-ordered dataset split."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    split_name: Literal["train", "val", "test"]
    sample_ids: List[str]
    sample_count: int
    start_event_ts_ms: Optional[int] = None
    end_event_ts_ms: Optional[int] = None


class DatasetManifest(BaseModel):
    """Canonical reproducible manifest for one dataset build."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    dataset_id: str
    objective_family: ObjectiveFamily
    build_time_ms: int
    manifest_version: int
    config_signature: Dict[str, Any]
    source_inventory: List[str]
    time_window: Dict[str, Any]
    sample_counts: Dict[str, int]
    exclusion_reason_counts: Dict[str, int]
    quarantine_reason_counts: Dict[str, int]
    symbols: List[str]
    legacy_non_causal_count: int
    reward_complete_stats: Dict[str, int]
    sequence_contract_modes: List[str]
    splits: List[DatasetSplitManifest]


class DatasetCutoverSummary(BaseModel):
    """Aggregate facts used to decide whether a dataset is eligible for cutover."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    total_rows: int
    trainable_rows: int
    diagnostics_only_rows: int
    invalid_rows_by_reason: Dict[str, int]
    real_executed_rows: int
    synthetic_rows: int
    used_synthetic_fallback: bool
    reward_valid: bool
    reward_methodology: Optional[str] = None
    terminal_complete_rows: int
    terminal_incomplete_rows: int
    cutover_allowed: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)


class DatasetCutoverDecision(DatasetCutoverSummary):
    """Final dataset cutover verdict with blocking reasons."""

    model_config = ConfigDict(extra='forbid', frozen=True)
