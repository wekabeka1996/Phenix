"""Forward separability analysis for Phase R3-B.

Validates whether the SMA-slope trend label carries predictive edge
over forward return horizons (12, 24, 48 bars = 1h/2h/4h at 5m).

Key functions:
  compute_forward_returns   -- attach fwd_ret_N columns to df
  run_forward_separability  -- per-label stats, Cohen's d, sign lift, edge verdict

No new dependencies beyond polars + numpy.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import polars as pl

from tools.parquet_pipeline.market_structure import _histogram_overlap, _bhattacharyya
from tools.parquet_pipeline.regime_grid import _trend_labels, _vol_labels

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_HORIZONS: List[int] = [12, 24, 48]

# Edge verdict thresholds (Cohen's d and sign lift)
_STRONG_D: float = 0.20
_STRONG_LIFT: float = 0.05
_MODERATE_D: float = 0.10
_MODERATE_LIFT: float = 0.02
_WEAK_D: float = 0.05
_WEAK_LIFT: float = 0.01

TREND_LABELS = ("TREND_UP", "TREND_DOWN", "FLAT")
VOL_LABELS = ("LOW_VOL", "MID_VOL", "HIGH_VOL")


# ── Forward return computation ───────────────────────────────────────────────

def compute_forward_returns(
    df: pl.DataFrame,
    horizons: Optional[List[int]] = None,
) -> pl.DataFrame:
    """Attach forward log-return columns to df.

    fwd_ret_N[t] = log(close[t+N] / close[t])
                 = sum(log_return[t+1..t+N])

    Args:
        df:       DataFrame with a ``close`` column.
        horizons: List of bar horizons N to compute (default [12, 24, 48]).

    Returns:
        df with additional ``fwd_ret_{N}`` columns (Float64).
        Last N rows have NaN for each horizon N.
    """
    if horizons is None:
        horizons = DEFAULT_HORIZONS

    if "close" not in df.columns:
        for n in horizons:
            df = df.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(f"fwd_ret_{n}")
            )
        return df

    close_arr = df["close"].to_numpy().astype(float)
    for n in horizons:
        fwd = np.full(len(close_arr), np.nan)
        valid = len(close_arr) - n
        if valid > 0:
            with np.errstate(divide="ignore", invalid="ignore"):
                ratios = close_arr[n:n + valid] / close_arr[:valid]
                fwd[:valid] = np.where(
                    (ratios > 0) & np.isfinite(ratios),
                    np.log(ratios),
                    np.nan,
                )
        df = df.with_columns(pl.Series(f"fwd_ret_{n}", fwd, dtype=pl.Float64))

    return df


# ── Cohen's d ────────────────────────────────────────────────────────────────

def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d: standardized mean difference between two samples.

    Uses pooled standard deviation. Returns 0.0 when either array is empty
    or pooled std is near zero.
    """
    if len(a) < 2 or len(b) < 2:
        return 0.0
    mean_a = float(np.mean(a))
    mean_b = float(np.mean(b))
    std_a = float(np.std(a, ddof=1))
    std_b = float(np.std(b, ddof=1))
    pooled = math.sqrt((std_a ** 2 + std_b ** 2) / 2.0)
    if pooled < 1e-12:
        return 0.0
    return (mean_a - mean_b) / pooled


# ── Sign accuracy ────────────────────────────────────────────────────────────

def _sign_accuracy(arr: np.ndarray) -> float:
    """Fraction of positive values in arr (NaN excluded).

    Returns 0.5 when arr is empty (neutral baseline).
    """
    clean = arr[np.isfinite(arr)]
    if len(clean) == 0:
        return 0.5
    return float(np.mean(clean > 0))


# ── Edge verdict ─────────────────────────────────────────────────────────────

def _edge_verdict(cohens_d_val: float, sign_lift: float) -> str:
    """Classify edge strength from Cohen's d and sign lift.

    Verdicts (strongest to weakest):
      strong:   |d| > 0.20 AND |lift| > 0.05
      moderate: |d| > 0.10 AND |lift| > 0.02
      weak:     |d| > 0.05 OR  |lift| > 0.01
      none:     below all thresholds
    """
    abs_d = abs(cohens_d_val)
    abs_lift = abs(sign_lift)
    if abs_d > _STRONG_D and abs_lift > _STRONG_LIFT:
        return "strong"
    if abs_d > _MODERATE_D and abs_lift > _MODERATE_LIFT:
        return "moderate"
    if abs_d > _WEAK_D or abs_lift > _WEAK_LIFT:
        return "weak"
    return "none"


# ── Per-label stats ───────────────────────────────────────────────────────────

def _label_stats(
    df: pl.DataFrame,
    trend_col: str,
    horizon: int,
) -> Dict[str, Any]:
    """Compute per-label forward return stats for one horizon.

    Returns dict with keys: {label: {mean, std, sign_accuracy, n}}.
    """
    fwd_col = f"fwd_ret_{horizon}"
    if fwd_col not in df.columns or trend_col not in df.columns:
        return {}

    stats: Dict[str, Any] = {}
    for label in TREND_LABELS:
        mask = df[trend_col] == label
        arr = (
            df.filter(mask)[fwd_col]
            .drop_nulls()
            .to_numpy()
        )
        arr = arr[np.isfinite(arr)]
        if len(arr) == 0:
            stats[label] = {"mean": None, "std": None, "sign_accuracy": None, "n": 0}
            continue
        stats[label] = {
            "mean": round(float(np.mean(arr)), 8),
            "std": round(float(np.std(arr, ddof=1)), 8),
            "sign_accuracy": round(_sign_accuracy(arr), 4),
            "n": len(arr),
        }
    return stats


# ── Main public function ──────────────────────────────────────────────────────

def run_forward_separability(
    df: pl.DataFrame,
    *,
    sma_short: int = 48,
    sma_long: int = 192,
    slope_threshold: float = 0.002,
    atr_window: int = 28,
    hysteresis_bars: int = 3,
    horizons: Optional[List[int]] = None,
    tf_minutes: int = 5,
) -> Dict[str, Any]:
    """Compute forward separability analysis for a single symbol DataFrame.

    Labels bars with TREND_UP/DOWN/FLAT and LOW/MID/HIGH_VOL using
    winning R2 params (or user-supplied params), then measures whether
    TREND_UP labels have predictive edge over consecutive forward returns.

    Args:
        df:               DataFrame with ``close`` and ``bar_range`` columns.
        sma_short:        Short SMA period (regime label param).
        sma_long:         Long SMA period (regime label param).
        slope_threshold:  FLAT band threshold (normalized slope).
        atr_window:       Rolling window for bar_range ATR proxy.
        hysteresis_bars:  Confirmation bars for label commitment.
        horizons:         Forward return horizons in bars (default [12,24,48]).
        tf_minutes:       Bar timeframe in minutes (used for display only).

    Returns:
        Nested dict:
          params:            Input regime params.
          horizons:          List of N values.
          tf_minutes:        Timeframe.
          per_horizon:       {N: {per_label_stats, UP_vs_FLAT, DOWN_vs_FLAT, edge_verdict}}
          vol_interaction:   {N: {vol_bucket × trend_label: sign_accuracy, mean, n}}
          label_distribution: {label: count, pct}
    """
    if horizons is None:
        horizons = DEFAULT_HORIZONS

    # ── Attach regime labels ─────────────────────────────────────────────
    trend_series = _trend_labels(
        df, sma_short, sma_long, slope_threshold,
        hysteresis_bars=hysteresis_bars,
    )
    vol_series = _vol_labels(df, atr_window)

    df = df.with_columns([
        trend_series.alias("trend_label"),
        vol_series.alias("vol_label"),
    ])

    # ── Attach forward returns ───────────────────────────────────────────
    df = compute_forward_returns(df, horizons=horizons)

    # ── Label distribution ───────────────────────────────────────────────
    n_total = len(df)
    label_dist: Dict[str, Any] = {}
    for label in TREND_LABELS:
        n_label = int((df["trend_label"] == label).sum())
        label_dist[label] = {
            "count": n_label,
            "pct": round(n_label / n_total * 100, 2) if n_total > 0 else 0.0,
        }

    # ── Per-horizon analysis ─────────────────────────────────────────────
    per_horizon: Dict[int, Any] = {}
    for n in horizons:
        fwd_col = f"fwd_ret_{n}"

        # Per-label stats
        label_stats = _label_stats(df, "trend_label", n)

        # UP vs FLAT comparison
        up_arr = (
            df.filter(pl.col("trend_label") == "TREND_UP")[fwd_col]
            .drop_nulls()
            .to_numpy()
        )
        up_arr = up_arr[np.isfinite(up_arr)]

        down_arr = (
            df.filter(pl.col("trend_label") == "TREND_DOWN")[fwd_col]
            .drop_nulls()
            .to_numpy()
        )
        down_arr = down_arr[np.isfinite(down_arr)]

        flat_arr = (
            df.filter(pl.col("trend_label") == "FLAT")[fwd_col]
            .drop_nulls()
            .to_numpy()
        )
        flat_arr = flat_arr[np.isfinite(flat_arr)]

        # UP vs FLAT
        up_vs_flat: Dict[str, Any] = {}
        if len(up_arr) >= 5 and len(flat_arr) >= 5:
            d_up = _cohens_d(up_arr, flat_arr)
            sa_up = _sign_accuracy(up_arr)
            sa_flat = _sign_accuracy(flat_arr)
            lift_up = sa_up - sa_flat
            overlap = _histogram_overlap(up_arr, flat_arr)
            bhatt = _bhattacharyya(up_arr, flat_arr)
            up_vs_flat = {
                "cohens_d": round(d_up, 4),
                "sign_accuracy_up": round(sa_up, 4),
                "sign_accuracy_flat": round(sa_flat, 4),
                "sign_lift": round(lift_up, 4),
                "overlap_coefficient": round(overlap, 4),
                "bhattacharyya_distance": round(bhatt, 4),
                "edge_verdict": _edge_verdict(d_up, lift_up),
            }

        # DOWN vs FLAT
        down_vs_flat: Dict[str, Any] = {}
        if len(down_arr) >= 5 and len(flat_arr) >= 5:
            d_down = _cohens_d(down_arr, flat_arr)
            sa_down = _sign_accuracy(down_arr)
            sa_flat_d = _sign_accuracy(flat_arr)
            lift_down = sa_down - sa_flat_d
            overlap_d = _histogram_overlap(down_arr, flat_arr)
            bhatt_d = _bhattacharyya(down_arr, flat_arr)
            down_vs_flat = {
                "cohens_d": round(d_down, 4),
                "sign_accuracy_down": round(sa_down, 4),
                "sign_accuracy_flat": round(sa_flat_d, 4),
                "sign_lift": round(lift_down, 4),
                "overlap_coefficient": round(overlap_d, 4),
                "bhattacharyya_distance": round(bhatt_d, 4),
                "edge_verdict": _edge_verdict(d_down, lift_down),
            }

        per_horizon[n] = {
            "label_stats": label_stats,
            "UP_vs_FLAT": up_vs_flat,
            "DOWN_vs_FLAT": down_vs_flat,
        }

    # ── Vol-interaction matrix ────────────────────────────────────────────
    vol_interaction: Dict[int, Any] = {}
    for n in horizons:
        fwd_col = f"fwd_ret_{n}"
        matrix: Dict[str, Any] = {}
        for trend_lbl in TREND_LABELS:
            for vol_lbl in VOL_LABELS:
                key = f"{trend_lbl}|{vol_lbl}"
                arr = (
                    df.filter(
                        (pl.col("trend_label") == trend_lbl)
                        & (pl.col("vol_label") == vol_lbl)
                    )[fwd_col]
                    .drop_nulls()
                    .to_numpy()
                )
                arr = arr[np.isfinite(arr)]
                if len(arr) == 0:
                    matrix[key] = {"n": 0, "mean": None, "sign_accuracy": None}
                else:
                    matrix[key] = {
                        "n": len(arr),
                        "mean": round(float(np.mean(arr)), 8),
                        "sign_accuracy": round(_sign_accuracy(arr), 4),
                    }
        vol_interaction[n] = matrix

    return {
        "params": {
            "sma_short": sma_short,
            "sma_long": sma_long,
            "slope_threshold": slope_threshold,
            "atr_window": atr_window,
            "hysteresis_bars": hysteresis_bars,
        },
        "horizons": horizons,
        "tf_minutes": tf_minutes,
        "label_distribution": label_dist,
        "per_horizon": per_horizon,
        "vol_interaction": vol_interaction,
    }


# ── Flat output for parquet export ────────────────────────────────────────────

def flatten_separability_to_df(
    result: Dict[str, Any],
    symbol: str,
) -> pl.DataFrame:
    """Convert run_forward_separability output to a flat polars DataFrame.

    One row per (label, horizon) combination. Suitable for parquet export.

    Columns:
      symbol, trend_label, horizon_bars, n, mean_fwd_ret,
      std_fwd_ret, sign_accuracy, cohens_d_vs_flat, sign_lift_vs_flat,
      overlap_vs_flat, bhatt_vs_flat, edge_verdict
    """
    rows: list[Dict[str, Any]] = []
    per_horizon = result.get("per_horizon", {})
    for n, h_data in per_horizon.items():
        label_stats: Dict[str, Any] = h_data.get("label_stats", {})
        up_vs_flat = h_data.get("UP_vs_FLAT", {})
        down_vs_flat = h_data.get("DOWN_vs_FLAT", {})

        for label in TREND_LABELS:
            st = label_stats.get(label, {})
            if label == "TREND_UP":
                cmp = up_vs_flat
                d_key = "cohens_d"
                lift_key = "sign_lift"
                ov_key = "overlap_coefficient"
                bhatt_key = "bhattacharyya_distance"
                ev_key = "edge_verdict"
            elif label == "TREND_DOWN":
                cmp = down_vs_flat
                d_key = "cohens_d"
                lift_key = "sign_lift"
                ov_key = "overlap_coefficient"
                bhatt_key = "bhattacharyya_distance"
                ev_key = "edge_verdict"
            else:
                cmp = {}
                d_key = lift_key = ov_key = bhatt_key = ev_key = ""

            rows.append({
                "symbol": symbol,
                "trend_label": label,
                "horizon_bars": n,
                "horizon_hours": round(n * result["tf_minutes"] / 60.0, 2),
                "n": st.get("n", 0),
                "mean_fwd_ret": st.get("mean"),
                "std_fwd_ret": st.get("std"),
                "sign_accuracy": st.get("sign_accuracy"),
                "cohens_d_vs_flat": cmp.get(d_key) if d_key else None,
                "sign_lift_vs_flat": cmp.get(lift_key) if lift_key else None,
                "overlap_vs_flat": cmp.get(ov_key) if ov_key else None,
                "bhatt_vs_flat": cmp.get(bhatt_key) if bhatt_key else None,
                "edge_verdict": cmp.get(ev_key) if ev_key else "reference",
            })

    return pl.DataFrame(rows)
