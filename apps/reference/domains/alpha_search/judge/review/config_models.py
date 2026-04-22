"""Strict config models for offline Phase 6 review tooling."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SegmentDimension = Literal["symbol", "regime", "tf_sec", "source_file"]


class ReviewConfig(BaseModel):
    """Offline review tooling config.

    This config does not redefine Phase 5 input authority. It points at the
    existing judge simulator config and adds only review-specific output and
    segmentation controls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    judge_simulator_config_path: str = Field(..., min_length=1)
    output_dir: str = Field(..., min_length=1)
    segment_dimensions: tuple[SegmentDimension, ...]
    confidence_bucket_edges: tuple[float, ...]

    @field_validator("judge_simulator_config_path", "output_dir")
    @classmethod
    def non_empty_path(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("path fields must be a non-empty string")
        return value

    @field_validator("segment_dimensions")
    @classmethod
    def validate_segment_dimensions(
        cls, values: tuple[SegmentDimension, ...]
    ) -> tuple[SegmentDimension, ...]:
        if not values:
            raise ValueError("segment_dimensions must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("segment_dimensions must not contain duplicates")
        return values

    @field_validator("confidence_bucket_edges")
    @classmethod
    def validate_confidence_edges(
        cls, values: tuple[float, ...]
    ) -> tuple[float, ...]:
        if len(values) < 3:
            raise ValueError(
                "confidence_bucket_edges must contain at least 3 values"
            )
        previous = None
        for value in values:
            if value < 0.0 or value > 1.0:
                raise ValueError(
                    "confidence_bucket_edges must stay in [0.0, 1.0]"
                )
            if previous is not None and value <= previous:
                raise ValueError(
                    "confidence_bucket_edges must be strictly increasing"
                )
            previous = value
        return values

    @model_validator(mode="after")
    def validate_bucket_bounds(self) -> "ReviewConfig":
        if self.confidence_bucket_edges[0] != 0.0:
            raise ValueError(
                "confidence_bucket_edges must start at 0.0"
            )
        if self.confidence_bucket_edges[-1] != 1.0:
            raise ValueError(
                "confidence_bucket_edges must end at 1.0"
            )
        return self
