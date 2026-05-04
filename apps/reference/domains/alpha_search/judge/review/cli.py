"""CLI for offline Phase 6 review artifact generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .config_schema_validator import (
    validate_review_config_file,
    validate_review_paths,
)
from .engine import run_review
from .report_writer import (
    write_csv_rows,
    write_markdown_summary,
    write_review_bundle,
)

EXIT_SUCCESS = 0
EXIT_BAD_CONFIG = 1
EXIT_MISSING_INPUT = 2
EXIT_REVIEW_FAILURE = 3
EXIT_WRITE_FAILURE = 4

_DEFAULT_CONFIG_PATH = "config/judge_review.yaml"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="judge-review",
        description="Generate offline Phase 6 review artifacts.",
    )
    parser.add_argument(
        "--config",
        default=_DEFAULT_CONFIG_PATH,
        help=f"Path to review YAML config (default: {_DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args(argv)

    try:
        config = validate_review_config_file(args.config)
        validate_review_paths(config)
    except FileNotFoundError as exc:
        print(f"[judge-review] missing input: {exc}", file=sys.stderr)
        return EXIT_MISSING_INPUT
    except ValueError as exc:
        print(f"[judge-review] config error: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    try:
        result = run_review(config)
    except FileNotFoundError as exc:
        print(f"[judge-review] missing evidence: {exc}", file=sys.stderr)
        return EXIT_MISSING_INPUT
    except Exception as exc:
        print(
            f"[judge-review] review generation failed: {exc}", file=sys.stderr)
        return EXIT_REVIEW_FAILURE

    bundle = dict(result["bundle"])
    artifact_paths = dict(bundle["artifact_paths"])

    try:
        write_review_bundle(bundle, artifact_paths["review_bundle_json"])
        write_markdown_summary(
            str(result["summary_markdown"]),
            artifact_paths["review_summary_md"],
        )
        write_csv_rows(
            result["comparison_rows"],
            artifact_paths["comparison_segments_csv"],
            fieldnames=result["fieldnames"]["comparison_rows"],
        )
        write_csv_rows(
            result["suppression_rows"],
            artifact_paths["suppression_unknown_csv"],
            fieldnames=result["fieldnames"]["suppression_rows"],
        )
        write_csv_rows(
            result["disagreement_rows"],
            artifact_paths["disagreement_buckets_csv"],
            fieldnames=result["fieldnames"]["disagreement_rows"],
        )
        write_csv_rows(
            result["calibration_rows"],
            artifact_paths["calibration_slices_csv"],
            fieldnames=result["fieldnames"]["calibration_rows"],
        )
        write_csv_rows(
            result["surface_rows"],
            artifact_paths["surface_support_csv"],
            fieldnames=result["fieldnames"]["surface_rows"],
        )
    except Exception as exc:
        print(f"[judge-review] write failure: {exc}", file=sys.stderr)
        return EXIT_WRITE_FAILURE

    output_dir = Path(config.output_dir)
    print(f"[judge-review] config: {args.config}")
    print(f"[judge-review] output_dir: {output_dir}")
    print(
        f"[judge-review] entry_verdicts={bundle['input_coverage']['entry_verdict_count']} "
        f"matched={bundle['input_coverage']['matched_count']}"
    )
    print(f"[judge-review] bundle:  {artifact_paths['review_bundle_json']}")
    print(f"[judge-review] summary: {artifact_paths['review_summary_md']}")
    print("[judge-review] done")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
