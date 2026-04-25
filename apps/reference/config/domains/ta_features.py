from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TAFeaturesDomainConfig(BaseModel):
    """Canonical ta_features domain configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Master switch for ta_features runtime wiring."
    )
    timeframes_sec: List[int] = Field(
        ..., min_length=1,
        description="Configured BAR_CLOSED timeframes that ta_features consumes.",
    )
    warm_up_bars: int = Field(
        ..., ge=20,
        description="Bars required before ta_features marks payloads is_warm=true.",
    )
    buffer_max_bars: int = Field(
        ..., ge=20,
        description="Rolling OHLCV buffer length per (symbol, tf_sec). Must be >= warm_up_bars.",
    )
    log_calculations: bool = Field(
        ..., description="Write per-symbol JSONL calculation logs under logs/ta_features/.",
    )
    log_max_bytes: int = Field(
        ..., ge=1,
        description="Rotating JSONL maxBytes per symbol log file.",
    )
    log_backup_count: int = Field(
        ..., ge=0,
        description="Rotating JSONL backupCount per symbol log file.",
    )

    @field_validator("timeframes_sec")
    @classmethod
    def validate_timeframes(cls, value: List[int]) -> List[int]:
        if not all(60 <= tf_sec <= 3600 for tf_sec in value):
            raise ValueError(
                "All ta_features timeframes must be between 60 and 3600 seconds"
            )
        if len(value) != len(set(value)):
            raise ValueError("ta_features.timeframes_sec must be unique")
        return value

    @model_validator(mode="after")
    def validate_buffer_length(self) -> "TAFeaturesDomainConfig":
        if self.buffer_max_bars < self.warm_up_bars:
            raise ValueError(
                "ta_features.buffer_max_bars must be >= ta_features.warm_up_bars"
            )
        return self
