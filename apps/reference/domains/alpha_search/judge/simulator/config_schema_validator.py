"""Phase 5 Package 5H — config/schema validation tooling.

Provides bounded preflight checks for the offline judge simulator:

1. **Config-file validation** — loads and validates ``judge_simulator.yaml``
   through the existing ``SimulatorConfig`` Pydantic model.
2. **Schema-set validation** — compiles the three simulator-owned JSON
   schemas (outcome input, calibration dataset, summary report).
3. **Path checks** — verifies input paths exist, output parent dirs are
   viable, and no output/input path collisions.
4. **Preflight orchestration** — ``run_simulator_preflight()`` chains
   the above three and returns a deterministic structured summary
   without running the simulator or writing any files.

This module is offline-only.  It does not import from or modify any
live runtime module, does not emit FSM events, and does not widen
``JudgeCortexConfig`` mode admission.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

import jsonschema
import yaml

from .config_models import SimulatorConfig

logger = logging.getLogger(__name__)

# ── schema inventory ─────────────────────────────────────────────────

_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

_SIMULATOR_SCHEMAS: dict[str, str] = {
    "outcome_input_v1": "outcome_input_v1.json",
    "calibration_dataset_v1": "calibration_dataset_v1.json",
    "summary_report_v1": "summary_report_v1.json",
}


# ── 1. Config-file validation ───────────────────────────────────────


def validate_simulator_config_file(config_path: str | Path) -> SimulatorConfig:
    """Load, parse, and validate a simulator config YAML file.

    Reuses the same loading logic as 5F ``cli.load_simulator_config``
    but is importable without pulling in the full CLI module.

    Parameters
    ----------
    config_path:
        Path to a YAML file containing a top-level ``judge_simulator`` key.

    Returns
    -------
    SimulatorConfig
        Validated, frozen configuration.

    Raises
    ------
    FileNotFoundError
        If *config_path* does not exist.
    ValueError
        If YAML is malformed, the ``judge_simulator`` key is missing,
        or Pydantic validation fails.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(f"Malformed YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"Config file does not contain a YAML mapping: {path}"
        )

    section = raw.get("judge_simulator")
    if section is None:
        raise ValueError(
            f"Config file missing required 'judge_simulator' key: {path}"
        )
    if not isinstance(section, dict):
        raise ValueError(
            f"'judge_simulator' must be a mapping, "
            f"got {type(section).__name__}: {path}"
        )

    return SimulatorConfig(**section)


# ── 2. Schema-set validation ────────────────────────────────────────


def validate_simulator_schema_set(
    schemas_dir: str | Path | None = None,
) -> dict[str, object]:
    """Compile and validate all simulator-owned JSON schemas.

    Parameters
    ----------
    schemas_dir:
        Override for the schemas directory.  Defaults to the
        ``schemas/`` directory next to this module.

    Returns
    -------
    dict
        ``{"ok": True, "schemas": {name: {"path": ..., "title": ...}}}``
        on success.

    Raises
    ------
    FileNotFoundError
        If a required schema file is missing.
    ValueError
        If a schema file contains invalid JSON or fails compilation.
    """
    base = Path(schemas_dir) if schemas_dir else _SCHEMAS_DIR
    result: dict[str, dict[str, str]] = {}

    for name, filename in _SIMULATOR_SCHEMAS.items():
        schema_path = base / filename

        if not schema_path.is_file():
            raise FileNotFoundError(
                f"Required simulator schema missing: {schema_path}"
            )

        with open(schema_path, "r", encoding="utf-8") as fh:
            try:
                schema_obj = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in schema {schema_path}: {exc}"
                ) from exc

        # Compile (validates meta-schema compliance)
        try:
            jsonschema.Draft7Validator.check_schema(schema_obj)
        except jsonschema.SchemaError as exc:
            raise ValueError(
                f"Schema compilation failed for {schema_path}: {exc.message}"
            ) from exc

        result[name] = {
            "path": str(schema_path),
            "title": schema_obj.get("title", ""),
        }

    return {"ok": True, "schemas": result}


# ── 3. Path checks ──────────────────────────────────────────────────


def validate_simulator_paths(config: SimulatorConfig) -> dict[str, object]:
    """Run bounded path-level checks on a validated SimulatorConfig.

    Checks:
    - ``judge_logs_path`` exists
    - ``outcome_data_path`` exists
    - parent directory for ``calibration_dataset_path`` exists or is creatable
    - parent directory for ``summary_report_path`` exists or is creatable
    - ``calibration_dataset_path != summary_report_path``
    - output paths do not collide with input paths

    Parameters
    ----------
    config:
        A validated ``SimulatorConfig``.

    Returns
    -------
    dict
        ``{"ok": True, "notes": [...]}`` on success.

    Raises
    ------
    ValueError
        If any check fails.
    """
    notes: list[str] = []
    errors: list[str] = []

    # Input existence
    judge_logs = Path(config.judge_logs_path)
    if not judge_logs.exists():
        errors.append(
            f"judge_logs_path does not exist: {judge_logs}"
        )

    outcome_data = Path(config.outcome_data_path)
    if not outcome_data.exists():
        errors.append(
            f"outcome_data_path does not exist: {outcome_data}"
        )

    # Output parent dirs
    cal_path = Path(config.calibration_dataset_path)
    sum_path = Path(config.summary_report_path)

    for label, p in [
        ("calibration_dataset_path", cal_path),
        ("summary_report_path", sum_path),
    ]:
        parent = p.parent
        if not parent.exists():
            # Check if parent is creatable by testing upward
            try:
                parent.mkdir(parents=True, exist_ok=True)
                notes.append(f"Created output directory: {parent}")
            except OSError as exc:
                errors.append(
                    f"Cannot create parent directory for {label}: "
                    f"{parent} ({exc})"
                )

    # Output path collision: calibration vs summary
    cal_resolved = cal_path.resolve()
    sum_resolved = sum_path.resolve()
    if cal_resolved == sum_resolved:
        errors.append(
            f"calibration_dataset_path and summary_report_path "
            f"resolve to the same file: {cal_resolved}"
        )

    # Output vs input collision
    input_resolved = set()
    if judge_logs.exists():
        if judge_logs.is_file():
            input_resolved.add(judge_logs.resolve())
        elif judge_logs.is_dir():
            # judge_logs_path is a directory; outputs should not land inside it
            # but exact file collision is the bounded check
            pass
    if outcome_data.exists():
        input_resolved.add(outcome_data.resolve())

    for label, resolved in [
        ("calibration_dataset_path", cal_resolved),
        ("summary_report_path", sum_resolved),
    ]:
        if resolved in input_resolved:
            errors.append(
                f"{label} collides with an input path: {resolved}"
            )

    if errors:
        raise ValueError(
            "Simulator path validation failed:\n  - "
            + "\n  - ".join(errors)
        )

    return {"ok": True, "notes": notes}


# ── 4. Preflight orchestration ──────────────────────────────────────


def run_simulator_preflight(
    config_path: str | Path,
    schemas_dir: str | Path | None = None,
) -> dict[str, object]:
    """Run the full simulator preflight: config + schemas + paths.

    Does NOT run the simulator, write outputs, or mutate files (except
    creating missing output parent directories, which is a necessary
    side-effect of path validation).

    Parameters
    ----------
    config_path:
        Path to ``judge_simulator.yaml``.
    schemas_dir:
        Optional override for the schemas directory.

    Returns
    -------
    dict
        Structured preflight summary with keys:
        ``config_ok``, ``schemas_ok``, ``paths_ok``,
        ``validated_config_path``, ``validated_schema_paths``, ``notes``.
    """
    notes: list[str] = []

    # ── config ────────────────────────────────────────────────────
    config_ok = False
    config: SimulatorConfig | None = None
    try:
        config = validate_simulator_config_file(config_path)
        config_ok = True
    except (FileNotFoundError, ValueError) as exc:
        notes.append(f"config: FAIL — {exc}")

    # ── schemas ───────────────────────────────────────────────────
    schemas_ok = False
    schema_paths: dict[str, str] = {}
    try:
        schema_result = validate_simulator_schema_set(schemas_dir)
        schemas_ok = schema_result["ok"]  # type: ignore[assignment]
        schema_paths = {
            k: v["path"]  # type: ignore[index]
            # type: ignore[union-attr]
            for k, v in schema_result["schemas"].items()
        }
    except (FileNotFoundError, ValueError) as exc:
        notes.append(f"schemas: FAIL — {exc}")

    # ── paths ─────────────────────────────────────────────────────
    paths_ok = False
    if config is not None:
        try:
            path_result = validate_simulator_paths(config)
            paths_ok = path_result["ok"]  # type: ignore[assignment]
            # type: ignore[arg-type]
            notes.extend(path_result.get("notes", []))
        except ValueError as exc:
            notes.append(f"paths: FAIL — {exc}")
    else:
        notes.append("paths: SKIPPED — config validation failed")

    return {
        "config_ok": config_ok,
        "schemas_ok": schemas_ok,
        "paths_ok": paths_ok,
        "validated_config_path": str(config_path),
        "validated_schema_paths": schema_paths,
        "notes": notes,
    }
