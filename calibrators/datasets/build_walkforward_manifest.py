#!/usr/bin/env python
"""CLI: Build walk-forward manifest."""

import argparse
import json
import sys

from calibrators.datasets.builders.walkforward_manifest_builder import (
    build_walkforward_manifest,
)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build walk-forward manifest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source-dataset",
        required=True,
        help="Parent dataset identifier",
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="Target dataset identifier",
    )
    parser.add_argument(
        "--train-start",
        help="Training start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--train-end",
        help="Training end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--validation-start",
        help="Validation start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--validation-end",
        help="Validation end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--forward-start",
        help="Forward/test start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--forward-end",
        help="Forward/test end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--excluded-sessions",
        help="JSON array of excluded session IDs",
        default=None,
    )
    parser.add_argument(
        "--label-horizon-bars",
        type=int,
        default=None,
        help="Label horizon in bars",
    )
    parser.add_argument(
        "--config-snapshot",
        help="JSON object with config snapshot",
        default=None,
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for manifest",
    )

    args = parser.parse_args()

    # Parse optional JSON fields
    excluded_sessions = None
    if args.excluded_sessions:
        try:
            excluded_sessions = json.loads(args.excluded_sessions)
        except json.JSONDecodeError as e:
            print(
                f"✗ Invalid JSON for --excluded-sessions: {e}", file=sys.stderr)
            return 1

    config_snapshot = None
    if args.config_snapshot:
        try:
            config_snapshot = json.loads(args.config_snapshot)
        except json.JSONDecodeError as e:
            print(
                f"✗ Invalid JSON for --config-snapshot: {e}", file=sys.stderr)
            return 1

    try:
        result = build_walkforward_manifest(
            source_dataset=args.source_dataset,
            dataset_id=args.dataset_id,
            train_start=args.train_start,
            train_end=args.train_end,
            validation_start=args.validation_start,
            validation_end=args.validation_end,
            forward_start=args.forward_start,
            forward_end=args.forward_end,
            excluded_sessions=excluded_sessions,
            label_horizon_bars=args.label_horizon_bars,
            config_snapshot=config_snapshot,
            out_dir=args.out,
        )

        print(f"✓ Built walk-forward manifest")
        print(f"  Dataset ID: {result.manifest_row['dataset_id']}")
        print(
            f"  Train: {result.manifest_row['train_start']} to {result.manifest_row['train_end']}")
        print(
            f"  Validation: {result.manifest_row['validation_start']} to {result.manifest_row['validation_end']}")
        print(
            f"  Forward: {result.manifest_row['forward_start']} to {result.manifest_row['forward_end']}")
        print(
            f"  Builder valid: {result.data_quality_summary.get('builder_valid', False)}")
        print(
            f"  Schema valid: {result.data_quality_summary.get('schema_valid', False)}")
        print(
            f"  Promotion grade: {result.data_quality_summary.get('promotion_grade', False)}")
        print(f"\n  Output: {args.out}")

        return 0

    except ValueError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
