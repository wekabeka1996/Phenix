"""
MD_AMR Package D.1 — Matched-Cohort Overlay Analysis

Analysis-only script. Reads per-trade integrated-validation data and produces:
  1. reports/md_amr_overlay_cohort_analysis.csv
  2. reports/md_amr_overlay_threshold_sweep.csv
  3. reports/md_amr_overlay_by_symbol.csv
  4. reports/md_amr_overlay_slow_reversion_protection.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_HOLD_BARS_A1 = 16
SLOW_REVERSION_MIN_BARS = int(MAX_HOLD_BARS_A1 * 0.85)  # 13+

SETUP_QUALITY_COL = "entry_setup_quality"
HOLD_QUALITY_COL = "exit_hold_quality"
CONTEXT_VALIDITY_COL = "exit_context_validity"
PROGRESS_DEFICIT_COL = "progress_deficit"  # derived

HOLD_QUALITY_THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
CONTEXT_VALIDITY_THRESHOLDS = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Keep only integrated arm (has overlay data)
    df = df[df["arm"] == "integrated_c1234"].copy()
    df["net_return_ratio"] = pd.to_numeric(
        df["net_return_ratio"], errors="coerce")
    df["holding_bars"] = pd.to_numeric(
        df["holding_bars"], errors="coerce").fillna(0).astype(int)
    df["is_win"] = df["net_return_ratio"] > 0
    for col in [SETUP_QUALITY_COL, HOLD_QUALITY_COL, CONTEXT_VALIDITY_COL,
                "min_hold_quality", "min_context_validity",
                "max_progress_pct", "exit_progress_pct",
                "max_elapsed_hold_frac"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Derive progress_deficit: expected - actual (proxy: elapsed_frac - progress_pct)
    df["progress_deficit"] = (df["max_elapsed_hold_frac"].fillna(
        0) - df["exit_progress_pct"].fillna(0)).clip(lower=0)
    # Tag slow profitable reversions
    df["is_slow_profitable_reversion"] = (
        df["is_win"] &
        (df["holding_bars"] >= SLOW_REVERSION_MIN_BARS)
    )
    # Tag exit type buckets
    df["exit_bucket"] = df["primary_exit_reason"].fillna("UNKNOWN")
    return df


def _cohort_stats(group: pd.DataFrame, label: str) -> dict:
    n = len(group)
    if n == 0:
        return {"cohort": label, "n": 0}
    return {
        "cohort": label,
        "n": n,
        "win_rate": float(group["is_win"].mean()),
        "net_return_sum": float(group["net_return_ratio"].sum()),
        "net_return_mean": float(group["net_return_ratio"].mean()),
        "net_return_median": float(group["net_return_ratio"].median()),
        "avg_holding_bars": float(group["holding_bars"].mean()),
        "slow_rev_count": int(group["is_slow_profitable_reversion"].sum()),
        "timeout_count": int(group["has_timeout"].sum()) if "has_timeout" in group.columns else 0,
        "stop_hit_count": int(group["has_stop_hit"].sum()) if "has_stop_hit" in group.columns else 0,
        "scaleout_count": int(group["has_scaleout"].sum()) if "has_scaleout" in group.columns else 0,
        "target_hit_count": int(group["has_target_hit"].sum()) if "has_target_hit" in group.columns else 0,
    }


# ---------------------------------------------------------------------------
# Q1-Q3: Median / Quartile cohort splits
# ---------------------------------------------------------------------------

def _split_analysis(df: pd.DataFrame, col: str, symbol: str) -> list[dict]:
    rows = []
    valid = df[df[col].notna()].copy()
    if valid.empty:
        return rows

    median_val = float(valid[col].median())
    q25 = float(valid[col].quantile(0.25))
    q75 = float(valid[col].quantile(0.75))

    # Median split
    below = valid[valid[col] < median_val]
    above = valid[valid[col] >= median_val]
    r_below = _cohort_stats(below, f"below_median(<{median_val:.4f})")
    r_above = _cohort_stats(above, f"above_median(>={median_val:.4f})")
    for r in (r_below, r_above):
        r.update({"overlay": col, "symbol": symbol, "split_type": "median",
                  "threshold": median_val})
    rows.extend([r_below, r_above])

    # Quartile split
    for q_label, q_lo, q_hi in [
        ("Q1", float("-inf"), q25),
        ("Q2", q25, median_val),
        ("Q3", median_val, q75),
        ("Q4", q75, float("inf")),
    ]:
        mask = (valid[col] >= q_lo) if q_lo == float(
            "-inf") else (valid[col] >= q_lo)
        mask = mask & ((valid[col] < q_hi) if q_hi != float("inf") else True)
        cohort = valid[mask]
        r = _cohort_stats(cohort, q_label)
        r.update({"overlay": col, "symbol": symbol, "split_type": "quartile",
                  "threshold": f"{q_lo:.4f}-{q_hi:.4f}"})
        rows.append(r)

    return rows


# ---------------------------------------------------------------------------
# Q4: Threshold sweep
# ---------------------------------------------------------------------------

def _threshold_sweep(
    df: pd.DataFrame, col: str, thresholds: list[float], symbol: str,
    direction: str = "below_is_bad",
) -> list[dict]:
    """Sweep thresholds: if direction='below_is_bad', trades with score < threshold would be filtered."""
    rows = []
    valid = df[df[col].notna()].copy()
    if valid.empty:
        return rows

    total_pnl = float(valid["net_return_ratio"].sum())
    total_n = len(valid)
    total_slow_rev = int(valid["is_slow_profitable_reversion"].sum())

    for thr in thresholds:
        if direction == "below_is_bad":
            filtered = valid[valid[col] < thr]  # these would be removed
            surviving = valid[valid[col] >= thr]
        else:
            filtered = valid[valid[col] > thr]  # these would be removed
            surviving = valid[valid[col] <= thr]

        n_filtered = len(filtered)
        n_surviving = len(surviving)
        pnl_filtered = float(filtered["net_return_ratio"].sum())
        pnl_surviving = float(surviving["net_return_ratio"].sum())
        slow_rev_lost = int(filtered["is_slow_profitable_reversion"].sum())
        slow_rev_surviving = int(
            surviving["is_slow_profitable_reversion"].sum())
        bad_trades_filtered = int(
            (~filtered["is_win"]).sum()) if n_filtered > 0 else 0
        good_trades_filtered = int(
            filtered["is_win"].sum()) if n_filtered > 0 else 0

        rows.append({
            "overlay": col,
            "symbol": symbol,
            "threshold": thr,
            "direction": direction,
            "total_trades": total_n,
            "trades_filtered": n_filtered,
            "trades_surviving": n_surviving,
            "pct_filtered": round(n_filtered / max(total_n, 1) * 100, 1),
            "total_pnl": round(total_pnl, 8),
            "pnl_filtered": round(pnl_filtered, 8),
            "pnl_surviving": round(pnl_surviving, 8),
            "pnl_delta": round(pnl_surviving - total_pnl, 8),
            "slow_rev_total": total_slow_rev,
            "slow_rev_lost": slow_rev_lost,
            "slow_rev_surviving": slow_rev_surviving,
            "slow_rev_pct_lost": round(slow_rev_lost / max(total_slow_rev, 1) * 100, 1),
            "bad_trades_filtered": bad_trades_filtered,
            "good_trades_filtered": good_trades_filtered,
            "net_tradeoff": f"remove {n_filtered} trades ({bad_trades_filtered} bad, {good_trades_filtered} good), lose {slow_rev_lost}/{total_slow_rev} slow revs, pnl delta {pnl_surviving - total_pnl:+.6f}",
        })

    return rows


# ---------------------------------------------------------------------------
# Slow reversion protection table
# ---------------------------------------------------------------------------

def _slow_reversion_detail(df: pd.DataFrame) -> pd.DataFrame:
    sr = df[df["is_slow_profitable_reversion"]].copy()
    if sr.empty:
        return pd.DataFrame()
    cols = [
        "symbol", "trade_id", "side", "holding_bars", "net_return_ratio",
        SETUP_QUALITY_COL, HOLD_QUALITY_COL, CONTEXT_VALIDITY_COL,
        "min_hold_quality", "min_context_validity",
        "exit_progress_pct", "exit_context_validity_state", "exit_bucket",
    ]
    return sr[[c for c in cols if c in sr.columns]].copy()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="D.1 Matched-Cohort Overlay Analysis")
    parser.add_argument(
        "--trades-csv", default="reports/md_amr_integrated_validation_trades.csv")
    parser.add_argument(
        "--cohort-out", default="reports/md_amr_overlay_cohort_analysis.csv")
    parser.add_argument(
        "--sweep-out", default="reports/md_amr_overlay_threshold_sweep.csv")
    parser.add_argument("--by-symbol-out",
                        default="reports/md_amr_overlay_by_symbol.csv")
    parser.add_argument(
        "--slow-rev-out", default="reports/md_amr_overlay_slow_reversion_protection.csv")
    args = parser.parse_args()

    trades_path = Path(args.trades_csv)
    if not trades_path.exists():
        print(f"ERROR: trades CSV not found at {trades_path}", file=sys.stderr)
        return 1

    df = _load_trades(trades_path)
    print(f"Loaded {len(df)} integrated trades from {trades_path}")
    symbols = sorted(df["symbol"].unique().tolist())
    print(f"Symbols: {symbols}")
    print(
        f"Slow profitable reversions: {df['is_slow_profitable_reversion'].sum()}")

    # -----------------------------------------------------------------------
    # 1. Cohort analysis (median + quartile splits)
    # -----------------------------------------------------------------------
    cohort_rows: list[dict] = []
    for symbol in symbols + ["COMBINED"]:
        subset = df if symbol == "COMBINED" else df[df["symbol"] == symbol]
        for col in [SETUP_QUALITY_COL, HOLD_QUALITY_COL, CONTEXT_VALIDITY_COL, "progress_deficit"]:
            cohort_rows.extend(_split_analysis(subset, col, symbol))

    cohort_df = pd.DataFrame(cohort_rows)
    cohort_df.to_csv(args.cohort_out, index=False)
    print(f"Wrote cohort analysis: {args.cohort_out} ({len(cohort_df)} rows)")

    # -----------------------------------------------------------------------
    # 2. Threshold sweep
    # -----------------------------------------------------------------------
    sweep_rows: list[dict] = []
    for symbol in symbols + ["COMBINED"]:
        subset = df if symbol == "COMBINED" else df[df["symbol"] == symbol]

        # setup_quality: use percentile thresholds
        sq_valid = subset[subset[SETUP_QUALITY_COL].notna()][SETUP_QUALITY_COL]
        if not sq_valid.empty:
            sq_thresholds = [
                round(float(sq_valid.quantile(0.25)), 4),
                round(float(sq_valid.median()), 4),
                round(float(sq_valid.quantile(0.75)), 4),
            ]
            sweep_rows.extend(_threshold_sweep(
                subset, SETUP_QUALITY_COL, sq_thresholds, symbol, "below_is_bad"))

        # hold_quality: fixed ladder
        sweep_rows.extend(_threshold_sweep(
            subset, HOLD_QUALITY_COL, HOLD_QUALITY_THRESHOLDS, symbol, "below_is_bad"))

        # context_validity: fixed ladder
        sweep_rows.extend(_threshold_sweep(
            subset, CONTEXT_VALIDITY_COL, CONTEXT_VALIDITY_THRESHOLDS, symbol, "below_is_bad"))

    sweep_df = pd.DataFrame(sweep_rows)
    sweep_df.to_csv(args.sweep_out, index=False)
    print(f"Wrote threshold sweep: {args.sweep_out} ({len(sweep_df)} rows)")

    # -----------------------------------------------------------------------
    # 3. By-symbol summary
    # -----------------------------------------------------------------------
    by_symbol_rows: list[dict] = []
    for symbol in symbols + ["COMBINED"]:
        subset = df if symbol == "COMBINED" else df[df["symbol"] == symbol]
        row = _cohort_stats(subset, "ALL")
        row["symbol"] = symbol
        for col in [SETUP_QUALITY_COL, HOLD_QUALITY_COL, CONTEXT_VALIDITY_COL, "progress_deficit"]:
            valid = subset[col].dropna()
            if not valid.empty:
                row[f"{col}_mean"] = round(float(valid.mean()), 6)
                row[f"{col}_median"] = round(float(valid.median()), 6)
                row[f"{col}_p25"] = round(float(valid.quantile(0.25)), 6)
                row[f"{col}_p75"] = round(float(valid.quantile(0.75)), 6)
                row[f"{col}_std"] = round(float(valid.std()), 6)
                # Correlation with net_return
                mask = subset[col].notna()
                if mask.sum() > 2:
                    corr = float(np.corrcoef(
                        subset.loc[mask, col].values,
                        subset.loc[mask, "net_return_ratio"].values
                    )[0, 1])
                    row[f"{col}_return_corr"] = round(corr, 6)
                # Win-rate split
                above_med = subset[mask & (subset[col] >= valid.median())]
                below_med = subset[mask & (subset[col] < valid.median())]
                if len(above_med) > 0:
                    row[f"{col}_above_median_win_rate"] = round(
                        float(above_med["is_win"].mean()), 4)
                    row[f"{col}_above_median_pnl"] = round(
                        float(above_med["net_return_ratio"].sum()), 8)
                if len(below_med) > 0:
                    row[f"{col}_below_median_win_rate"] = round(
                        float(below_med["is_win"].mean()), 4)
                    row[f"{col}_below_median_pnl"] = round(
                        float(below_med["net_return_ratio"].sum()), 8)
        by_symbol_rows.append(row)

    by_symbol_df = pd.DataFrame(by_symbol_rows)
    by_symbol_df.to_csv(args.by_symbol_out, index=False)
    print(f"Wrote by-symbol: {args.by_symbol_out} ({len(by_symbol_df)} rows)")

    # -----------------------------------------------------------------------
    # 4. Slow reversion protection detail
    # -----------------------------------------------------------------------
    sr_df = _slow_reversion_detail(df)
    sr_df.to_csv(args.slow_rev_out, index=False)
    print(
        f"Wrote slow-reversion detail: {args.slow_rev_out} ({len(sr_df)} rows)")

    # -----------------------------------------------------------------------
    # Summary print
    # -----------------------------------------------------------------------
    print("\n=== QUICK SUMMARY ===")
    for symbol in symbols + ["COMBINED"]:
        subset = df if symbol == "COMBINED" else df[df["symbol"] == symbol]
        print(f"\n--- {symbol} ({len(subset)} trades) ---")
        for col in [SETUP_QUALITY_COL, HOLD_QUALITY_COL, CONTEXT_VALIDITY_COL]:
            valid = subset[col].dropna()
            if valid.empty:
                continue
            mask = subset[col].notna()
            corr = float(np.corrcoef(
                subset.loc[mask, col].values,
                subset.loc[mask, "net_return_ratio"].values
            )[0, 1]) if mask.sum() > 2 else float("nan")
            print(
                f"  {col}: mean={valid.mean():.4f} median={valid.median():.4f} corr_w_return={corr:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
