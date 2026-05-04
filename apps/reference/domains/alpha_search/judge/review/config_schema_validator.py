"""Offline review config and path validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.simulator.config_schema_validator import (
    validate_simulator_config_file,
    validate_simulator_paths,
)

from .config_models import ReviewConfig


def validate_review_config_file(config_path: str | Path) -> ReviewConfig:
    """Load, parse, and validate a review config YAML file."""

    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Review config file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        try:
            raw = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Malformed YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"Review config file does not contain a YAML mapping: {path}"
        )

    section = raw.get("judge_review")
    if section is None:
        raise ValueError(
            f"Review config file missing required 'judge_review' key: {path}"
        )
    if not isinstance(section, dict):
        raise ValueError(
            f"'judge_review' must be a mapping, got {type(section).__name__}: {path}"
        )

    return ReviewConfig(**section)


def validate_review_paths(config: ReviewConfig) -> dict[str, object]:
    """Validate review paths and reuse simulator-path validation."""

    errors: list[str] = []
    notes: list[str] = []
    optional_artifacts: dict[str, dict[str, object]] = {}

    simulator_config_path = Path(config.judge_simulator_config_path)
    if not simulator_config_path.is_file():
        errors.append(
            f"judge_simulator_config_path does not exist: {simulator_config_path}"
        )
        simulator_config = None
    else:
        simulator_config = validate_simulator_config_file(
            simulator_config_path)
        simulator_path_result = validate_simulator_paths(simulator_config)
        notes.extend(str(note)
                     for note in simulator_path_result.get("notes", []))

    output_dir = Path(config.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"Cannot create output_dir {output_dir}: {exc}")

    if simulator_config is not None:
        optional_artifacts = {
            "existing_calibration_dataset": {
                "path": simulator_config.calibration_dataset_path,
                "exists": Path(simulator_config.calibration_dataset_path).is_file(),
            },
            "existing_summary_report": {
                "path": simulator_config.summary_report_path,
                "exists": Path(simulator_config.summary_report_path).is_file(),
            },
        }
        for label, info in optional_artifacts.items():
            if not bool(info["exists"]):
                notes.append(
                    f"optional artifact missing: {label}={info['path']}"
                )

    if errors:
        raise ValueError(
            "Review path validation failed:\n  - " + "\n  - ".join(errors)
        )

    return {
        "ok": True,
        "notes": notes,
        "optional_artifacts": optional_artifacts,
    }


def run_review_preflight(config_path: str | Path) -> dict[str, object]:
    """Run review config and simulator-surface preflight."""

    notes: list[str] = []
    config_ok = False
    simulator_ok = False
    paths_ok = False
    review_config: ReviewConfig | None = None
    simulator_config: SimulatorConfig | None = None
    optional_artifacts: dict[str, dict[str, object]] = {}

    try:
        review_config = validate_review_config_file(config_path)
        config_ok = True
    except (FileNotFoundError, ValueError) as exc:
        notes.append(f"review_config: FAIL — {exc}")

    if review_config is not None:
        try:
            simulator_config = validate_simulator_config_file(
                review_config.judge_simulator_config_path
            )
            simulator_ok = True
        except (FileNotFoundError, ValueError) as exc:
            notes.append(f"judge_simulator_config: FAIL — {exc}")

        try:
            path_result = validate_review_paths(review_config)
            paths_ok = True
            notes.extend(str(note) for note in path_result.get("notes", []))
            optional_artifacts = dict(
                # type: ignore[arg-type]
                path_result.get("optional_artifacts", {})
            )
        except ValueError as exc:
            notes.append(f"paths: FAIL — {exc}")

    return {
        "config_ok": config_ok,
        "simulator_ok": simulator_ok,
        "paths_ok": paths_ok,
        "validated_review_config_path": str(Path(config_path)),
        "validated_simulator_config_path": (
            review_config.judge_simulator_config_path
            if review_config is not None
            else None
        ),
        "output_dir": review_config.output_dir if review_config is not None else None,
        "optional_artifacts": optional_artifacts,
        "notes": notes,
    }
