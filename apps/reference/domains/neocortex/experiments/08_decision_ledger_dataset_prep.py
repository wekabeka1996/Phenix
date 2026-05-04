#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from _decision_ledger_baseline import (
    DEFAULT_DATASET_PATH,
    DEFAULT_LEDGER_PATH,
    DEFAULT_METADATA_PATH,
    prepare_dataset,
    render_table,
    save_dataset_artifacts,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a model-ready dataset from the shadow telemetry decision ledger.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH,
                        help="Path to decision_ledger_v1.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_DATASET_PATH,
                        help="CSV output path for the prepared dataset")
    parser.add_argument("--metadata-output", type=Path, default=DEFAULT_METADATA_PATH,
                        help="JSON output path for dataset metadata")
    parser.add_argument("--min-real-rows", type=int, default=240,
                        help="Minimum executed real rows before synthetic fallback is disabled")
    parser.add_argument("--synthetic-rows", type=int, default=420,
                        help="Synthetic rows to generate when the live ledger is missing or insufficient")
    parser.add_argument("--seed", type=int, default=7,
                        help="Random seed for synthetic fallback generation")
    parser.add_argument("--toxic-pnl-threshold", type=float, default=0.0,
                        help="Trades with pnl <= threshold are labeled toxic")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = prepare_dataset(
        ledger_path=args.ledger,
        min_real_rows=args.min_real_rows,
        synthetic_rows=args.synthetic_rows,
        seed=args.seed,
        toxic_pnl_threshold=args.toxic_pnl_threshold,
    )
    save_dataset_artifacts(result.frame, result.metadata,
                           args.output, args.metadata_output)

    summary = pd.DataFrame(
        [
            {
                "rows": int(result.metadata["total_rows"]),
                "feature_cols": len(result.metadata["feature_columns"]),
                "real_rows": int(result.metadata["real_executed_rows"]),
                "synthetic_rows": int(result.metadata["synthetic_rows"]),
                "used_synthetic_fallback": bool(result.metadata["used_synthetic_fallback"]),
                "synthetic_reasons": ",".join(result.metadata["synthetic_reasons"]) or "none",
            }
        ]
    )
    class_balance = pd.DataFrame(
        [
            {
                "label": "non_toxic",
                "rows": int((result.frame["toxic_label"] == 0).sum()),
            },
            {
                "label": "toxic",
                "rows": int((result.frame["toxic_label"] == 1).sum()),
            },
        ]
    )

    print(render_table("=== Decision Ledger Dataset Prep ===", summary))
    print()
    print(render_table("=== Class Balance ===", class_balance))
    print()
    print(f"Dataset CSV : {args.output}")
    print(f"Metadata JSON: {args.metadata_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
