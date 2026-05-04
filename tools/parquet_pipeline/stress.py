"""Stress v0: compute stress metrics from OHLCV bars.

Metrics (all based on canonical column names after rename):

  log_return     ln(close[t] / close[t-1])
  realized_vol   rolling std of log_return  (window)
  atr            rolling mean of True Range (window)
  gap            |open[t] - close[t-1]| / close[t-1]
  bar_range      (high - low) / close

Z-scores (no-lookahead):
  z_{metric}     (value - shifted_rolling_mean) / shifted_rolling_std
                 Baseline is shifted by 1 so bar t's z-score uses [t-window, ..., t-1].
                 min_periods=1 so burn-in rows still get partial z-scores.
"""

from __future__ import annotations

from typing import List

import polars as pl

# Stress v0 trigger metrics.
STRESS_V0_METRICS: tuple[str, ...] = (
    "realized_vol",
    "atr",
    "gap",
    "bar_range",
)

# Columns written to stress_timeseries.parquet.
STRESS_OUTPUT_COLUMNS: List[str] = [
    "timestamp",
    "close",
    "log_return",
    "realized_vol",
    "atr",
    "gap",
    "bar_range",
    "z_realized_vol",
    "z_atr",
    "z_gap",
    "z_bar_range",
]


def compute_stress_v0(
    lf: pl.LazyFrame,
    *,
    window: int = 100,
    burn_in: int = 120,
) -> pl.LazyFrame:
    """Compute stress v0 timeseries.

    Args:
        lf:       LazyFrame with canonical columns
                  (timestamp, open, high, low, close, volume).
        window:   Rolling window for baseline statistics.
        burn_in:  Number of initial bars to drop (insufficient history).

    Returns:
        LazyFrame with stress columns appended, burn-in rows dropped.
    """
    lf = lf.sort("timestamp")

    # ── Raw per-bar metrics ──────────────────────────────────────────
    lf = lf.with_columns([
        # Log return
        (pl.col("close") / pl.col("close").shift(1)).log().alias("log_return"),

        # True Range = max(H-L, |H-prev_close|, |L-prev_close|)
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("close").shift(1)).abs(),
            (pl.col("low") - pl.col("close").shift(1)).abs(),
        ).alias("true_range"),

        # Inter-bar gap
        (
            (pl.col("open") - pl.col("close").shift(1)).abs()
            / pl.col("close").shift(1)
        ).alias("gap"),

        # Normalized bar range
        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range"),
    ])

    # ── Rolling aggregates ───────────────────────────────────────────
    lf = lf.with_columns([
        pl.col("log_return")
        .rolling_std(window_size=window, min_periods=window)
        .alias("realized_vol"),

        pl.col("true_range")
        .rolling_mean(window_size=window, min_periods=window)
        .alias("atr"),
    ])

    # ── Z-scores (no-lookahead: .shift(1) so bar t uses [t-w..t-1]) ──
    z_exprs: list[pl.Expr] = []
    for m in STRESS_V0_METRICS:
        baseline_mean = pl.col(m).rolling_mean(window_size=window, min_periods=1).shift(1)
        baseline_std = pl.col(m).rolling_std(window_size=window, min_periods=1).shift(1)
        z_exprs.append(
            ((pl.col(m) - baseline_mean) / baseline_std).alias(f"z_{m}")
        )
    lf = lf.with_columns(z_exprs)

    # ── Clean inf/NaN z-scores -> 0.0 (div-by-zero when std=0) ──────
    z_clean: list[pl.Expr] = []
    for m in STRESS_V0_METRICS:
        z_col = f"z_{m}"
        z_clean.append(
            pl.when(pl.col(z_col).is_finite())
            .then(pl.col(z_col))
            .otherwise(pl.lit(0.0))
            .alias(z_col)
        )
    lf = lf.with_columns(z_clean)

    # ── Drop burn-in rows ────────────────────────────────────────────
    lf = lf.with_row_index("__idx").filter(pl.col("__idx") >= burn_in).drop("__idx")

    return lf
