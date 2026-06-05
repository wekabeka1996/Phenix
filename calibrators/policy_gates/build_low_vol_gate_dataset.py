#!/usr/bin/env python
"""CLI: Build low_vol_cost_floor joined dataset."""

import argparse
import sys
from pathlib import Path

from calibrators.datasets.builders.low_vol_gate_builder import (
    build_low_vol_gate_dataset,
)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build low_vol_cost_floor joined dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for dataset files and reports",
    )
    parser.add_argument(
        "--date-start",
        default=None,
        help="Start date filter (YYYY-MM-DD), optional",
    )
    parser.add_argument(
        "--date-end",
        default=None,
        help="End date filter (YYYY-MM-DD), optional",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (auto-detected if not specified)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Fail on missing optional sources",
    )
    parser.add_argument(
        "--objective-dataset",
        default=None,
        help="Path to objective_stack dataset output (for join if available)",
    )

    args = parser.parse_args()

    try:
        result = build_low_vol_gate_dataset(
            repo_root=args.repo_root,
            date_start=args.date_start,
            date_end=args.date_end,
            out_dir=args.out_dir,
        )

        print(f"✓ Built low_vol_gate dataset")
        print(
            f"  Gate rows: {result.data_quality_summary.get('gate_rows_count', 0)}")
        print(
            f"  Exact roundtrips: {result.data_quality_summary.get('exact_roundtrip_count', 0)}")
        print(
            f"  Blockers: {result.data_quality_summary.get('blocker_count', 0)}")
        print(
            f"  Warnings: {result.data_quality_summary.get('warning_count', 0)}")
        print(
            f"  Builder valid: {result.data_quality_summary.get('builder_valid', False)}")
        print(
            f"  Schema valid: {result.data_quality_summary.get('schema_valid', False)}")
        print(
            f"  Diagnostics only: {result.data_quality_summary.get('diagnostics_only', False)}")
        print(
            f"  Promotion grade: {result.data_quality_summary.get('promotion_grade', False)}")
        print(f"\n  Output: {args.out_dir}")

        if result.blockers and args.strict:
            print("\n✗ Strict mode: blockers present, aborting")
            return 1

        return 0

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
