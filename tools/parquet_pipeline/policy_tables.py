"""R3-A-lite: market-context edge tables and policy derivation.

No trade data required. Computes forward-return statistics per
(trend_label × vol_label × stress_state × horizon) combination and
derives primary policy tables for Aurora (sizing) and mean_reversion
(entry filter/boost).

Key functions:
  compute_edge_table      -- raw edge stats per context cell
  derive_trend_policy     -- Aurora sizing multipliers
  derive_mr_policy        -- MR entry boost / block rules
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import polars as pl

from tools.parquet_pipeline.forward_separability import compute_forward_returns
from tools.parquet_pipeline.regime_grid import _trend_labels, _vol_labels

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_HORIZONS: List[int] = [12, 24, 48]
BASELINE_TREND: str = "FLAT"
BASELINE_VOL: str = "MID_VOL"
BASELINE_STRESS: str = "NORMAL"

# Sizing multiplier bounds (Kelly-like clamp)
_SIZE_MULT_MIN: float = 0.25
_SIZE_MULT_MAX: float = 2.50

# P-value for CVaR lower tail
_CVAR_TAIL: float = 0.05


# ── Low-level stats ──────────────────────────────────────────────────────────

def _cvar5(arr: np.ndarray) -> float:
    """Mean of bottom 5% of arr values (Expected Shortfall approximation).

    Returns 0.0 on empty or all-NaN arrays.
    """
    clean = arr[np.isfinite(arr)]
    if len(clean) == 0:
        return 0.0
    cutoff = np.percentile(clean, _CVAR_TAIL * 100)
    tail = clean[clean <= cutoff]
    return float(np.mean(tail)) if len(tail) > 0 else float(cutoff)


def _tail_uplift(arr: np.ndarray) -> float:
    """p95 - p50: upside tail extension above median."""
    clean = arr[np.isfinite(arr)]
    if len(clean) < 2:
        return 0.0
    return float(np.percentile(clean, 95) - np.percentile(clean, 50))


def _sign_acc(arr: np.ndarray) -> float:
    """P(x > 0) on finite values; 0.5 on empty."""
    clean = arr[np.isfinite(arr)]
    if len(clean) == 0:
        return 0.5
    return float(np.mean(clean > 0))


# ── Core: compute_edge_table ──────────────────────────────────────────────────

def compute_edge_table(
    df: pl.DataFrame,
    *,
    sma_short: int = 48,
    sma_long: int = 192,
    slope_threshold: float = 0.002,
    atr_window: int = 28,
    hysteresis_bars: int = 3,
    horizons: Optional[List[int]] = None,
    stress_col: Optional[str] = None,
    tf_minutes: int = 5,
) -> pl.DataFrame:
    """Compute forward-return edge statistics per context cell.

    Groups by (trend_label, vol_label, stress_state, horizon) and computes:
      n, mean_fwd_ret, std_fwd_ret, p05, p50, p95,
      sign_acc, cvar5, tail_uplift, horizon_hours

    Args:
        df:               DataFrame with ``close`` and ``bar_range`` columns.
        sma_short:        Short SMA period.
        sma_long:         Long SMA period.
        slope_threshold:  FLAT band (normalized slope).
        atr_window:       Rolling window for bar_range ATR proxy.
        hysteresis_bars:  Confirmation bars.
        horizons:         Forward return horizons (bars). Default [12, 24, 48].
        stress_col:       Name of stress state column in df (e.g. "state").
                          If None or not found, all bars treated as "NORMAL".
        tf_minutes:       Bar size in minutes (for horizon_hours column).

    Returns:
        Polars DataFrame sorted by (horizon, trend_label, vol_label, stress_state).
        One row per group cell.
    """
    if horizons is None:
        horizons = DEFAULT_HORIZONS

    # ── Apply regime labels ──────────────────────────────────────────────
    trend_series = _trend_labels(
        df, sma_short, sma_long, slope_threshold,
        hysteresis_bars=hysteresis_bars,
    )
    vol_series = _vol_labels(df, atr_window)

    df = df.with_columns([
        trend_series.alias("trend_label"),
        vol_series.alias("vol_label"),
    ])

    # ── Attach stress state ──────────────────────────────────────────────
    if stress_col and stress_col in df.columns:
        df = df.with_columns(pl.col(stress_col).alias("stress_state"))
    else:
        df = df.with_columns(pl.lit("NORMAL").alias("stress_state"))

    # ── Attach forward returns ────────────────────────────────────────────
    df = compute_forward_returns(df, horizons=horizons)

    # ── Build edge table rows ─────────────────────────────────────────────
    rows: List[Dict[str, Any]] = []
    for n in horizons:
        fwd_col = f"fwd_ret_{n}"
        if fwd_col not in df.columns:
            continue
        h_hours = round(n * tf_minutes / 60.0, 2)

        # Iterate over unique (trend, vol, stress) combinations
        groups = (
            df.select(["trend_label", "vol_label", "stress_state"])
            .unique()
            .sort(["trend_label", "vol_label", "stress_state"])
        )
        for group_row in groups.iter_rows(named=True):
            tl = group_row["trend_label"]
            vl = group_row["vol_label"]
            ss = group_row["stress_state"]

            # Filter
            mask = (
                (df["trend_label"] == tl)
                & (df["vol_label"] == vl)
                & (df["stress_state"] == ss)
            )
            arr = df.filter(mask)[fwd_col].drop_nulls().to_numpy()
            arr = arr[np.isfinite(arr)]
            n_obs = len(arr)

            if n_obs == 0:
                rows.append({
                    "horizon_bars": n,
                    "horizon_hours": h_hours,
                    "trend_label": tl,
                    "vol_label": vl,
                    "stress_state": ss,
                    "n": 0,
                    "mean_fwd_ret": None,
                    "std_fwd_ret": None,
                    "p05": None,
                    "p50": None,
                    "p95": None,
                    "sign_acc": None,
                    "cvar5": None,
                    "tail_uplift": None,
                })
                continue

            rows.append({
                "horizon_bars": n,
                "horizon_hours": h_hours,
                "trend_label": tl,
                "vol_label": vl,
                "stress_state": ss,
                "n": n_obs,
                "mean_fwd_ret": round(float(np.mean(arr)), 8),
                "std_fwd_ret": round(float(np.std(arr, ddof=1)), 8),
                "p05": round(float(np.percentile(arr, 5)), 8),
                "p50": round(float(np.percentile(arr, 50)), 8),
                "p95": round(float(np.percentile(arr, 95)), 8),
                "sign_acc": round(_sign_acc(arr), 4),
                "cvar5": round(_cvar5(arr), 8),
                "tail_uplift": round(_tail_uplift(arr), 8),
            })

    if not rows:
        return pl.DataFrame()

    return (
        pl.DataFrame(rows)
        .sort(["horizon_bars", "trend_label", "vol_label", "stress_state"])
    )


# ── Policy derivation: trend-following sizing ─────────────────────────────────

def derive_trend_policy(
    edge_df: pl.DataFrame,
    *,
    baseline_trend: str = BASELINE_TREND,
    baseline_vol: str = BASELINE_VOL,
    baseline_stress: str = BASELINE_STRESS,
    primary_horizon: int = 24,
) -> pl.DataFrame:
    """Derive Aurora sizing multipliers from edge table.

    Logic per (trend × vol × stress) cell:
      mean_uplift = mean_fwd_ret(cell) - mean_fwd_ret(baseline)
      tail_ratio  = tail_uplift(cell)  / tail_uplift(baseline)  [if baseline > 0]
      sizing_mult = clamp(1.0 + mean_uplift / baseline_std, MIN, MAX)

    Edge signal:
      mean_uplift > 0   → increase size
      mean_uplift < 0  → reduce size
      |mean_uplift| < baseline_std * 0.05 → neutral (1.0)

    Args:
        edge_df:          Output of compute_edge_table.
        baseline_trend:   Reference label for "neutral" size.
        baseline_vol:     Reference vol bucket.
        baseline_stress:  Reference stress state.
        primary_horizon:  Horizon (bars) to use for policy derivation.

    Returns:
        DataFrame with columns:
          trend_label, vol_label, stress_state, n, mean_uplift,
          tail_ratio, sizing_mult, signal (increase/neutral/reduce)
    """
    subset = edge_df.filter(pl.col("horizon_bars") == primary_horizon)
    if len(subset) == 0:
        return pl.DataFrame()

    # Find baseline row
    baseline = subset.filter(
        (pl.col("trend_label") == baseline_trend)
        & (pl.col("vol_label") == baseline_vol)
        & (pl.col("stress_state") == baseline_stress)
    )
    if len(baseline) == 0:
        return pl.DataFrame()

    baseline_mean = baseline["mean_fwd_ret"][0]
    baseline_std = baseline["std_fwd_ret"][0]
    baseline_tail = baseline["tail_uplift"][0]
    if baseline_mean is None or baseline_std is None:
        return pl.DataFrame()
    baseline_std = float(baseline_std) if baseline_std else 1e-8
    baseline_tail_f = float(baseline_tail) if baseline_tail else 1e-8

    rows: List[Dict[str, Any]] = []
    for row in subset.iter_rows(named=True):
        mu = row.get("mean_fwd_ret")
        tu = row.get("tail_uplift")
        n = row.get("n", 0)
        if mu is None:
            continue
        mean_uplift = float(mu) - float(baseline_mean)
        tail_ratio = float(tu) / baseline_tail_f if (tu is not None and baseline_tail_f > 1e-12) else 1.0

        # Raw sizing from mean uplift normalised by baseline std (Kelly-like)
        raw_mult = 1.0 + mean_uplift / max(baseline_std, 1e-8)
        sizing_mult = round(float(np.clip(raw_mult, _SIZE_MULT_MIN, _SIZE_MULT_MAX)), 3)

        noise_band = baseline_std * 0.05
        if mean_uplift > noise_band:
            signal = "increase"
        elif mean_uplift < -noise_band:
            signal = "reduce"
        else:
            signal = "neutral"

        rows.append({
            "trend_label": row["trend_label"],
            "vol_label": row["vol_label"],
            "stress_state": row["stress_state"],
            "n": n,
            "mean_uplift": round(mean_uplift, 8),
            "tail_ratio": round(tail_ratio, 3),
            "sizing_mult": sizing_mult,
            "signal": signal,
        })

    if not rows:
        return pl.DataFrame()
    return (
        pl.DataFrame(rows)
        .sort(["stress_state", "trend_label", "vol_label"])
    )


# ── Policy derivation: mean-reversion entry ──────────────────────────────────

def derive_mr_policy(
    edge_df: pl.DataFrame,
    *,
    baseline_trend: str = BASELINE_TREND,
    baseline_vol: str = BASELINE_VOL,
    baseline_stress: str = BASELINE_STRESS,
    primary_horizon: int = 12,
) -> pl.DataFrame:
    """Derive mean-reversion entry filter / boost from edge table.

    Mean-reversion trades exploit _sign_acc_ as the primary metric
    (win-rate matters more than magnitude for an MR strategy).

    Logic:
      sign_acc_delta = sign_acc(cell) - sign_acc(baseline)
      entry_policy:
        boost  → sign_acc_delta >  0.03
        allow  → sign_acc_delta >= -0.01
        reduce → sign_acc_delta >= -0.04
        block  → sign_acc_delta <  -0.04

    Also surfaces: cvar5 (downside risk), baseline_excess (relative).

    Args:
        edge_df:          Output of compute_edge_table.
        baseline_trend:   Reference label.
        baseline_vol:     Reference vol bucket.
        baseline_stress:  Reference stress state.
        primary_horizon:  Horizon to use for policy (default 12 bars = 1h).

    Returns:
        DataFrame with columns:
          trend_label, vol_label, stress_state, n, sign_acc,
          sign_acc_delta, cvar5, entry_policy
    """
    subset = edge_df.filter(pl.col("horizon_bars") == primary_horizon)
    if len(subset) == 0:
        return pl.DataFrame()

    baseline = subset.filter(
        (pl.col("trend_label") == baseline_trend)
        & (pl.col("vol_label") == baseline_vol)
        & (pl.col("stress_state") == baseline_stress)
    )
    if len(baseline) == 0:
        return pl.DataFrame()

    baseline_sa = baseline["sign_acc"][0]
    if baseline_sa is None:
        return pl.DataFrame()
    baseline_sa_f = float(baseline_sa)

    rows: List[Dict[str, Any]] = []
    for row in subset.iter_rows(named=True):
        sa = row.get("sign_acc")
        cv = row.get("cvar5")
        n = row.get("n", 0)
        if sa is None:
            continue
        delta = float(sa) - baseline_sa_f

        if delta > 0.03:
            policy = "boost"
        elif delta >= -0.01:
            policy = "allow"
        elif delta >= -0.04:
            policy = "reduce"
        else:
            policy = "block"

        rows.append({
            "trend_label": row["trend_label"],
            "vol_label": row["vol_label"],
            "stress_state": row["stress_state"],
            "n": n,
            "sign_acc": round(float(sa), 4),
            "sign_acc_delta": round(delta, 4),
            "cvar5": round(float(cv), 8) if cv is not None else None,
            "entry_policy": policy,
        })

    if not rows:
        return pl.DataFrame()
    return (
        pl.DataFrame(rows)
        .sort("sign_acc_delta", descending=True)
    )
