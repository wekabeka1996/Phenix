"""Writers for offline Phase 6 review artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field


class ReviewBundleModel(BaseModel):
    """Top-level machine-readable review bundle contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^1$")
    tooling_scope: str
    generated_at_ms: int
    no_automatic_promotion_verdict: bool
    simulator_config_path: str
    output_dir: str
    input_coverage: dict[str, object]
    baseline_availability: dict[str, object]
    segmentation_coverage: dict[str, object]
    review_surface_support: dict[str, object]
    evidence_class_support: dict[str, object]
    verdict_class_counts: dict[str, object]
    chamber_class_counts: dict[str, object]
    suppression_unknown_accounting: dict[str, object]
    disagreement_metrics: dict[str, object]
    calibration_support: dict[str, object]
    existing_phase5_artifacts: dict[str, object]
    not_enough_evidence_flags: list[str]
    caution_notes: list[str]
    facts: list[str]
    inferences: list[str]
    assumptions: list[str]
    unknowns: list[str]
    artifact_paths: dict[str, str]


def write_review_bundle(bundle: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    if path.is_dir():
        raise IsADirectoryError(f"Review bundle path is a directory: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError("Review bundle path must use a .json extension")

    validated = ReviewBundleModel.model_validate(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(validated.model_dump(mode="json"),
                  handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def write_markdown_summary(markdown: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    if path.is_dir():
        raise IsADirectoryError(f"Review summary path is a directory: {path}")
    if path.suffix.lower() != ".md":
        raise ValueError("Review summary path must use a .md extension")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown.rstrip())
        handle.write("\n")
    return path


def write_csv_rows(
    rows: Sequence[dict[str, object]],
    output_path: str | Path,
    *,
    fieldnames: list[str],
) -> Path:
    path = Path(output_path)
    if path.is_dir():
        raise IsADirectoryError(f"CSV output path is a directory: {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError("CSV output path must use a .csv extension")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})
    return path
