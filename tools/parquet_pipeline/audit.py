"""Parquet audit: schema, nulls, gaps, duplicates, semantic invariants."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import polars as pl

from tools.parquet_pipeline.discovery import DEFAULT_RENAME

# Canonical OHLCV columns expected after rename.
EXPECTED_CANONICAL: frozenset[str] = frozenset(
    {"timestamp", "open", "high", "low", "close", "volume"}
)

# Columns whose dtype must be numeric (after rename).
_NUMERIC_COLS = ("open", "high", "low", "close", "volume")


def audit(
    files: List[Path],
    *,
    tf_minutes: int = 5,
    column_rename: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Run full audit on parquet files.  Returns a report dict.

    Checks performed:
      1. Missing canonical columns
      2. Null counts per column
      3. Duplicate timestamps
      4. Time-gap detection (> 1.5x expected interval)
      5. OHLCV semantic invariants (high >= low, volume >= 0)
      6. Value ranges

    Args:
        files:          Parquet file paths.
        tf_minutes:     Expected bar interval in minutes.
        column_rename:  Parquet -> canonical rename map.  Defaults to DEFAULT_RENAME.

    Returns:
        Report dict with ``passed: bool`` and ``issues: list[str]``.
    """
    if column_rename is None:
        column_rename = dict(DEFAULT_RENAME)

    report: Dict[str, Any] = {
        "files": [str(f) for f in files],
        "file_count": len(files),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "issues": [],
    }

    if not files:
        report["issues"].append("no files to audit")
        report["passed"] = False
        return report

    # ------------------------------------------------------------------
    # Lazy scan
    # ------------------------------------------------------------------
    lf = pl.scan_parquet([str(f) for f in files])
    raw_schema = lf.collect_schema()
    report["raw_schema"] = {k: str(v) for k, v in raw_schema.items()}

    rename = {k: v for k, v in column_rename.items() if k in raw_schema}
    if rename:
        lf = lf.rename(rename)
    schema = lf.collect_schema()
    report["canonical_schema"] = {k: str(v) for k, v in schema.items()}
    report["column_mapping_applied"] = rename

    # ------------------------------------------------------------------
    # 1) Missing columns
    # ------------------------------------------------------------------
    missing_cols = sorted(EXPECTED_CANONICAL - set(schema.keys()))
    if missing_cols:
        for mc in missing_cols:
            report["issues"].append(f"missing column: {mc}")
        report["passed"] = False
        return report

    # ------------------------------------------------------------------
    # 2) Aggregate stats (single collect)
    # ------------------------------------------------------------------
    ohlcv_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    stats = (
        lf.select(
            [pl.len().alias("row_count")]
            + [pl.col("timestamp").min().alias("ts_min")]
            + [pl.col("timestamp").max().alias("ts_max")]
            + [pl.col(c).null_count().alias(f"null_{c}") for c in ohlcv_cols]
        )
        .collect()
    )

    row_count = stats["row_count"][0]
    report["row_count"] = row_count
    report["time_range"] = {
        "min": str(stats["ts_min"][0]),
        "max": str(stats["ts_max"][0]),
    }

    # Null counts
    null_counts: Dict[str, int] = {}
    for c in ohlcv_cols:
        nc = int(stats[f"null_{c}"][0])
        null_counts[c] = nc
        if nc > 0:
            report["issues"].append(f"column '{c}': {nc} null(s)")
    report["null_counts"] = null_counts

    # ------------------------------------------------------------------
    # 3) Duplicate timestamps
    # ------------------------------------------------------------------
    dup_count = int(
        lf.select((pl.len() - pl.col("timestamp").n_unique()).alias("d"))
        .collect()["d"][0]
    )
    report["duplicate_timestamps"] = dup_count
    if dup_count > 0:
        report["issues"].append(f"{dup_count} duplicate timestamps")

    # ------------------------------------------------------------------
    # 4) Gaps
    # ------------------------------------------------------------------
    expected_ms = tf_minutes * 60 * 1000
    diffs = (
        lf.sort("timestamp")
        .select(
            pl.col("timestamp")
            .diff()
            .dt.total_milliseconds()
            .alias("diff_ms")
        )
        .drop_nulls()
        .collect()
    )

    if len(diffs) > 0:
        gap_count = int((diffs["diff_ms"] > expected_ms * 1.5).sum())
        backwards = int((diffs["diff_ms"] <= 0).sum())
        report["gap_analysis"] = {
            "expected_interval_ms": expected_ms,
            "gaps_detected": gap_count,
            "backwards_or_zero": backwards,
            "median_interval_ms": int(diffs["diff_ms"].median()),
        }
        if gap_count > 0:
            report["issues"].append(
                f"{gap_count} gap(s) (> {expected_ms * 1.5:.0f} ms)"
            )
        if backwards > 0:
            report["issues"].append(f"{backwards} backwards/zero interval(s)")

    # ------------------------------------------------------------------
    # 5) Semantic invariants
    # ------------------------------------------------------------------
    sem = (
        lf.select([
            (pl.col("high") < pl.col("low")).sum().alias("high_lt_low"),
            (pl.col("high") < pl.col("open")).sum().alias("high_lt_open"),
            (pl.col("high") < pl.col("close")).sum().alias("high_lt_close"),
            (pl.col("low") > pl.col("open")).sum().alias("low_gt_open"),
            (pl.col("low") > pl.col("close")).sum().alias("low_gt_close"),
            (pl.col("volume") < 0).sum().alias("neg_volume"),
        ])
        .collect()
    )

    semantic_issues: Dict[str, int] = {}
    for col_name in sem.columns:
        val = int(sem[col_name][0])
        if val > 0:
            semantic_issues[col_name] = val
            report["issues"].append(f"semantic: {val} row(s) {col_name}")
    report["semantic_issues"] = semantic_issues

    # ------------------------------------------------------------------
    # 6) Value ranges
    # ------------------------------------------------------------------
    ranges = (
        lf.select([
            pl.col("open").min().alias("open_min"),
            pl.col("open").max().alias("open_max"),
            pl.col("high").max().alias("high_max"),
            pl.col("low").min().alias("low_min"),
            pl.col("close").min().alias("close_min"),
            pl.col("close").max().alias("close_max"),
            pl.col("volume").min().alias("vol_min"),
            pl.col("volume").max().alias("vol_max"),
            pl.col("volume").mean().alias("vol_mean"),
        ])
        .collect()
    )

    report["value_ranges"] = {
        "open": [float(ranges["open_min"][0]), float(ranges["open_max"][0])],
        "high_max": float(ranges["high_max"][0]),
        "low_min": float(ranges["low_min"][0]),
        "close": [float(ranges["close_min"][0]), float(ranges["close_max"][0])],
        "volume": {
            "min": float(ranges["vol_min"][0]),
            "max": float(ranges["vol_max"][0]),
            "mean": round(float(ranges["vol_mean"][0]), 2),
        },
    }

    report["passed"] = len(report["issues"]) == 0
    return report
