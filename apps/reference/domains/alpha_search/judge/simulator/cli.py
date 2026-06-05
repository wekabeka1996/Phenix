"""Phase 5 Package 5F — CLI harness for the offline judge simulator.

Provides a bounded command-line entry point that:
  1. Loads simulator config from a YAML file
  2. Runs the simulation engine (Package 5A)
  3. Writes calibration dataset (Package 5D)
  4. Writes summary report (Package 5E)

This module is offline-only.  It does not import from or modify any
live runtime module, does not emit FSM events, and does not widen
JudgeCortexConfig mode admission.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

import yaml

from .config_models import SimulatorConfig

logger = logging.getLogger(__name__)

# ── exit codes ────────────────────────────────────────────────────────
EXIT_SUCCESS = 0
EXIT_BAD_CONFIG = 1
EXIT_MISSING_INPUT = 2
EXIT_SIMULATION_FAILURE = 3
EXIT_WRITE_FAILURE = 4

_DEFAULT_CONFIG_PATH = "config/judge_simulator.yaml"


def load_simulator_config(config_path: str | Path) -> SimulatorConfig:
    """Load and validate a SimulatorConfig from a YAML file.

    Parameters
    ----------
    config_path:
        Path to a YAML file containing a top-level ``judge_simulator`` key.

    Returns
    -------
    SimulatorConfig
        Validated, frozen configuration object.

    Raises
    ------
    FileNotFoundError
        If *config_path* does not exist.
    ValueError
        If YAML is malformed, the ``judge_simulator`` key is missing, or
        validation fails.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Config file does not contain a YAML mapping: {path}")

    section = raw.get("judge_simulator")
    if section is None:
        raise ValueError(
            f"Config file missing required 'judge_simulator' key: {path}"
        )
    if not isinstance(section, dict):
        raise ValueError(
            f"'judge_simulator' must be a mapping, got {type(section).__name__}: {path}"
        )

    return SimulatorConfig(**section)


def run_from_config(config: SimulatorConfig) -> "SimulationResult":  # noqa: F821
    """Run the full simulation pipeline and write outputs.

    Orchestrates:
      1. ``run_simulation(config)``
      2. ``write_calibration_dataset(...)``
      3. ``write_summary_report(...)``

    Returns
    -------
    SimulationResult
        The completed simulation result.

    Raises
    ------
    Exception
        Propagates any exception from the engine or writers.
    """
    # Late imports to keep module-level surface minimal and avoid
    # circular import risk with the engine's heavy transitive deps.
    from .calibration_dataset_writer import write_calibration_dataset
    from .simulator_engine import SimulationResult, run_simulation
    from .summary_report_writer import write_summary_report

    result: SimulationResult = run_simulation(config)

    write_calibration_dataset(
        records=result.calibration_records,
        output_path=config.calibration_dataset_path,
    )

    write_summary_report(
        report=result.summary_report,
        output_path=config.summary_report_path,
    )

    return result


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Parameters
    ----------
    argv:
        Command-line arguments.  Defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(
        prog="judge-simulator",
        description="Run the Phase 5 offline judge simulator.",
    )
    parser.add_argument(
        "--config",
        default=_DEFAULT_CONFIG_PATH,
        help=f"Path to simulator YAML config (default: {_DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args(argv)

    # ── 1. Load config ────────────────────────────────────────────────
    try:
        config = load_simulator_config(args.config)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        print(f"[judge-simulator] config error: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    print(f"[judge-simulator] config: {args.config}")

    # ── 2. Validate input paths exist ─────────────────────────────────
    for label, path_str in [
        ("judge_logs_path", config.judge_logs_path),
        ("outcome_data_path", config.outcome_data_path),
    ]:
        p = Path(path_str)
        if not p.exists():
            print(
                f"[judge-simulator] missing input: {label}={p}",
                file=sys.stderr,
            )
            return EXIT_MISSING_INPUT

    # ── 3. Run simulation + write outputs ─────────────────────────────
    try:
        result = run_from_config(config)
    except Exception as exc:
        print(f"[judge-simulator] simulation failed: {exc}", file=sys.stderr)
        return EXIT_SIMULATION_FAILURE

    # ── 4. Summary ────────────────────────────────────────────────────
    print(
        f"[judge-simulator] verdicts={result.total_verdict_records_loaded} "
        f"outcomes={result.total_outcome_records_loaded} "
        f"matched={result.matched_count}"
    )
    print(f"[judge-simulator] calibration: {config.calibration_dataset_path}")
    print(f"[judge-simulator] summary:     {config.summary_report_path}")
    print("[judge-simulator] done")

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
