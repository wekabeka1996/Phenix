"""Strict config models for the offline judge simulator."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SimulatorConfig(BaseModel):
    """Phase 5 Package 5A simulator configuration.

    This config is intentionally independent from JudgeCortexConfig and is
    used only by the offline simulator foundation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    judge_logs_path: str = Field(..., min_length=1)
    outcome_data_path: str = Field(..., min_length=1)
    calibration_dataset_path: str = Field(..., min_length=1)
    summary_report_path: str = Field(..., min_length=1)
    fee_per_cycle_bps: float = Field(default=25.0, ge=0.0)
    slippage_pct: float = Field(default=0.1, ge=0.0)

    @field_validator(
        "judge_logs_path",
        "outcome_data_path",
        "calibration_dataset_path",
        "summary_report_path",
    )
    @classmethod
    def path_must_be_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("path fields must be a non-empty string")
        return value
