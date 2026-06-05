#!/usr/bin/env python
"""CLI: Build objective_stack joined dataset."""

from calibrators.datasets.builders.objective_stack_builder import (
    build_objective_stack_dataset,
)
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build objective_stack joined dataset",
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
        "--realized-outcome-dataset",
        default=None,
        help="Optional canonical realized_trades.jsonl path from the 03F realized outcome builder",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Fail on missing optional sources",
    )

    args = parser.parse_args()

    try:
        result = build_objective_stack_dataset(
            repo_root=args.repo_root,
            date_start=args.date_start,
            date_end=args.date_end,
            out_dir=args.out_dir,
            realized_outcome_dataset=args.realized_outcome_dataset,
        )

        print(f"✓ Built objective_stack dataset")
        print(
            f"  Decision rows: {result.data_quality_summary.get('decision_rows_count', 0)}")
        print(
            f"  Realized trade rows: {result.data_quality_summary.get('realized_rows_count', 0)}")
        print(
            f"  Exact roundtrips: {result.data_quality_summary.get('exact_roundtrip_count', 0)}")
        print(
            f"  Match coverage pct: {result.data_quality_summary.get('match_coverage_pct')}")
        print(
            f"  Coverage grade: {result.data_quality_summary.get('coverage_grade')}")
        print(
            f"  Realized source: {result.data_quality_summary.get('realized_source', 'legacy_executed_trades_master')}")
        print(
            f"  Source promotion grade: {result.data_quality_summary.get('source_promotion_grade')}")
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
