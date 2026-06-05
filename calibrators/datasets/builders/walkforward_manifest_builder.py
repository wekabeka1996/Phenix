"""Walk-forward manifest builder.

Creates calibration_walkforward_manifest_v1 manifest rows for time-series
cross-validation splits.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from calibrators.datasets.builders.common import (
    compute_basic_data_quality_summary,
    write_manifest_json,
)
from calibrators.datasets.schema_registry import validate_row


@dataclass
class BuilderResult:
    """Result of manifest builder run."""

    manifest_row: dict[str, Any]
    data_quality_summary: dict[str, Any]
    blockers: list[str]
    warnings: list[str]


def build_walkforward_manifest(
    source_dataset: str,
    dataset_id: str,
    train_start: Optional[str] = None,
    train_end: Optional[str] = None,
    validation_start: Optional[str] = None,
    validation_end: Optional[str] = None,
    forward_start: Optional[str] = None,
    forward_end: Optional[str] = None,
    excluded_sessions: Optional[list[str]] = None,
    label_horizon_bars: Optional[int] = None,
    config_snapshot: Optional[dict[str, Any]] = None,
    out_dir: Optional[str | Path] = None,
) -> BuilderResult:
    """Build walk-forward manifest.

    Args:
        source_dataset: Parent dataset identifier.
        dataset_id: Target dataset identifier.
        train_start/train_end: Training split bounds (ISO dates).
        validation_start/validation_end: Validation split bounds.
        forward_start/forward_end: Forward/test split bounds.
        excluded_sessions: List of excluded session IDs/dates.
        label_horizon_bars: Label horizon in bars if applicable.
        config_snapshot: Calibration config dict at split creation.
        out_dir: Output directory for manifest JSON.

    Returns:
        BuilderResult with validated manifest row.

    Raises:
        ValueError: If required fields are missing.
    """
    # Validate required fields
    if not all(
        [train_start, train_end, validation_start,
            validation_end, forward_start, forward_end]
    ):
        raise ValueError(
            "Must provide all of: train_start, train_end, validation_start, "
            "validation_end, forward_start, forward_end"
        )

    manifest_row = {
        "dataset_schema": "calibration_walkforward_manifest_v1",
        "dataset_version": "1.0.0",
        "dataset_id": dataset_id,
        "source_dataset": source_dataset,
        "train_start": train_start,
        "train_end": train_end,
        "validation_start": validation_start,
        "validation_end": validation_end,
        "forward_start": forward_start,
        "forward_end": forward_end,
        "excluded_sessions": excluded_sessions or [],
        "label_horizon_bars": label_horizon_bars,
        "config_snapshot": config_snapshot or {},
        "synthetic_allowed": False,
        "notes": None,
    }

    # Validate against schema
    validate_row("calibration_walkforward_manifest_v1", manifest_row)

    summary = compute_basic_data_quality_summary(
        rows=[manifest_row],
        blockers=[],
        warnings=[],
        rows_valid=1,
        rows_invalid=0,
        has_realized_outcomes=None,
        exact_roundtrip_count=None,
        diagnostics_only=False,
    )

    # Write output if directory specified
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_manifest_json(
            out_dir / "walkforward_manifest.json", manifest_row)

    return BuilderResult(
        manifest_row=manifest_row,
        data_quality_summary=summary,
        blockers=list(summary["promotion_blockers"]),
        warnings=list(summary["warnings"]),
    )
