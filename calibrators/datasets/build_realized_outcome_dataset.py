from __future__ import annotations
from calibrators.datasets.builders.realized_outcome_builder import (
    build_realized_outcome_dataset,
)

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build canonical realized outcome dataset for calibration",
    )
    parser.add_argument("--out-dir", required=True,
                        help="Output directory for dataset artifacts")
    parser.add_argument("--repo-root", default=None,
                        help="Repository root path (auto-detect if omitted)")
    parser.add_argument("--decision-ledger", default=None,
                        help="Override decision ledger JSONL path")
    parser.add_argument("--order-log", default=None,
                        help="Override order_log JSONL path")
    parser.add_argument("--trade-lifecycle", default=None,
                        help="Optional trade_lifecycle JSONL path")
    parser.add_argument("--date-start", default=None,
                        help="Inclusive UTC start date YYYY-MM-DD")
    parser.add_argument("--date-end", default=None,
                        help="Inclusive UTC end date YYYY-MM-DD")
    parser.add_argument("--strict", action="store_true",
                        default=False, help="Fail if required sources are missing")
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Maximum number of eligible decision rows to process")
    parser.add_argument(
        "--include-diagnostics",
        type=_parse_bool,
        default=True,
        help="Whether to emit diagnostics-only rows when exact_roundtrip is incomplete (default: true)",
    )
    parser.add_argument(
        "--snapshot-sources",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy the exact builder source files into <out-dir>/source_snapshot (default: true)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(
        __file__).resolve().parents[2]
    result = build_realized_outcome_dataset(
        out_dir=Path(args.out_dir),
        repo_root=repo_root,
        decision_ledger=args.decision_ledger,
        order_log=args.order_log,
        trade_lifecycle=args.trade_lifecycle,
        date_start=args.date_start,
        date_end=args.date_end,
        strict=args.strict,
        max_rows=args.max_rows,
        include_diagnostics=args.include_diagnostics,
        snapshot_sources=args.snapshot_sources,
    )

    print("Built canonical realized outcome dataset")
    print(
        f"  Rows emitted: {result.data_quality_summary.get('rows_emitted', 0)}")
    print(
        f"  Exact roundtrips: {result.data_quality_summary.get('exact_roundtrip_count', 0)}")
    print(
        f"  Match coverage pct: {result.data_quality_summary.get('match_coverage_pct')}")
    print(
        f"  Coverage grade: {result.data_quality_summary.get('coverage_grade')}")
    print(
        f"  Diagnostics only: {result.data_quality_summary.get('diagnostics_only', False)}")
    print(
        f"  Promotion grade: {result.data_quality_summary.get('promotion_grade', False)}")
    print(f"  Blockers: {result.data_quality_summary.get('blocker_count', 0)}")
    print(f"  Warnings: {result.data_quality_summary.get('warning_count', 0)}")
    if result.blockers and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
