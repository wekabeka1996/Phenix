"""Phase R2: Regime Grid Calibration.

Grid-search over (sma_short, sma_long, slope_threshold, atr_window, hysteresis_bars)
to find configurations that are stable (low churn), separable (distinct
return/vol distributions per label), and balanced (no state < 1% or > 80%).

Input: stress_df from compute_stress_v0() — columns close, log_return, atr, bar_range.
No scipy.  No raw OHLC needed.
"""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List

import numpy as np
import polars as pl

from tools.parquet_pipeline.market_structure import _bhattacharyya, _histogram_overlap

# ── Defaults (mirroring user R2 spec) ────────────────────────────────────────

GRID_SMA_SHORTS: List[int] = [24, 36, 48]
GRID_SMA_LONGS: List[int] = [96, 144, 192]
GRID_SLOPE_THRESHOLDS: List[float] = [0.0005, 0.001, 0.0015, 0.002]
GRID_ATR_WINDOWS: List[int] = [14, 21, 28]
GRID_HYSTERESIS: List[int] = [1, 2, 3]

_BARS_PER_DAY_5M: int = 288  # 24 * 60 / 5

# Scoring constants
_CHURN_TARGET: float = 5.0   # switches/day above which stability_score → 0
_W_STABILITY: float = 0.5
_W_SEP: float = 0.4
_W_COVERAGE: float = 0.1    # subtracted as penalty
_MIN_STATE_PCT: float = 0.01  # states below this trigger coverage violation
_MAX_STATE_PCT: float = 0.80  # states above this trigger coverage violation


# ── Label helpers ─────────────────────────────────────────────────────────────

def _sma_slope(close: pl.Series, sma_short: int, sma_long: int) -> pl.Series:
    """Normalized slope = (SMA_short - SMA_long) / close.

    Returns null for the first sma_long - 1 bars (warmup).
    Uses polars expression form for API stability across versions.
    """
    tmp = pl.DataFrame({"close": close})
    return tmp.select(
        (
            pl.col("close").rolling_mean(window_size=sma_short, min_periods=sma_short)
            - pl.col("close").rolling_mean(window_size=sma_long, min_periods=sma_long)
        )
        / pl.col("close")
    ).to_series()


def _apply_hysteresis(labels: pl.Series, n: int) -> pl.Series:
    """N-bar confirmation hysteresis on a string Series (no nulls expected).

    A label change commits only after n consecutive identical bars.
    Reverting to the current committed state commits immediately (no exit-hysteresis).
    For n <= 1, returns labels unchanged.
    O(len) time.
    """
    if n <= 1:
        return labels
    raw: List[str] = labels.to_list()
    if not raw:
        return labels
    out: List[str] = list(raw)
    committed: str = raw[0]
    pending: str = raw[0]
    pending_cnt: int = 1
    for i in range(1, len(raw)):
        if raw[i] == pending:
            pending_cnt += 1
        else:
            pending = raw[i]
            pending_cnt = 1
        # Commit when: count threshold reached OR already returning to committed state
        if pending_cnt >= n or pending == committed:
            committed = pending
        out[i] = committed
    return pl.Series(labels.name, out, dtype=pl.Utf8)


def _trend_labels(
    df: pl.DataFrame,
    sma_short: int,
    sma_long: int,
    slope_threshold: float,
    hysteresis_bars: int = 1,
) -> pl.Series:
    """TREND_UP / TREND_DOWN / FLAT per bar.

    Warmup bars (first sma_long - 1) are filled with FLAT before hysteresis.
    """
    slope_series = _sma_slope(df["close"], sma_short, sma_long)
    slope_np = slope_series.fill_null(0.0).to_numpy()
    raw = np.where(
        slope_np > slope_threshold,
        "TREND_UP",
        np.where(slope_np < -slope_threshold, "TREND_DOWN", "FLAT"),
    )
    return _apply_hysteresis(
        pl.Series("trend_state", raw.tolist(), dtype=pl.Utf8),
        hysteresis_bars,
    )


def _vol_labels(df: pl.DataFrame, atr_window: int) -> pl.Series:
    """LOW_VOL / MID_VOL / HIGH_VOL using rolling ATR proxy from bar_range.

    atr_proxy = rolling_mean(bar_range, atr_window).
    Global p33/p66 tertiles of proxy define bucket boundaries.
    Warmup bars (< atr_window) get MID_VOL.
    """
    tmp = pl.DataFrame({"br": df["bar_range"]})
    proxy = tmp.select(
        pl.col("br").rolling_mean(window_size=atr_window, min_periods=atr_window).alias("p")
    ).to_series()

    non_null_np = proxy.drop_nulls().to_numpy()
    if len(non_null_np) < 3:
        return pl.Series("vol_state", ["MID_VOL"] * len(df), dtype=pl.Utf8)

    p33 = float(np.percentile(non_null_np, 33))
    p66 = float(np.percentile(non_null_np, 66))

    # NaN comparisons are always False → nulls land in MID_VOL branch
    proxy_np = proxy.to_numpy(allow_copy=True)
    labels = np.where(
        proxy_np < p33,
        "LOW_VOL",
        np.where(proxy_np > p66, "HIGH_VOL", "MID_VOL"),
    )
    return pl.Series("vol_state", labels.tolist(), dtype=pl.Utf8)


# ── Switch / run helpers ──────────────────────────────────────────────────────

def _count_switches(labels: pl.Series) -> int:
    """Count label transitions (arr[i] != arr[i-1])."""
    arr = labels.to_numpy()
    if len(arr) < 2:
        return 0
    return int(np.sum(arr[1:] != arr[:-1]))


def _median_run_bars(labels: pl.Series) -> float:
    """Median run length across all same-label consecutive streaks."""
    items: List[str] = labels.to_list()
    if not items:
        return 0.0
    runs: List[int] = []
    cur, cnt = items[0], 1
    for lbl in items[1:]:
        if lbl == cur:
            cnt += 1
        else:
            runs.append(cnt)
            cur, cnt = lbl, 1
    runs.append(cnt)
    return float(np.median(runs))


# ── Core grid-row computation ─────────────────────────────────────────────────

def compute_grid_row(
    df: pl.DataFrame,
    *,
    sma_short: int,
    sma_long: int,
    slope_threshold: float,
    atr_window: int,
    hysteresis_bars: int,
    tf_minutes: int = 5,
) -> Dict[str, Any]:
    """Compute all metrics for one (sma_short, sma_long, slope_threshold,
    atr_window, hysteresis_bars) combination.

    Returns a flat dict with 23 fields: 5 params + 8 coverage + 4 stability +
    4 separability + 1 score + 1 coverage_ok flag.
    """
    bars_per_day = 1440.0 / tf_minutes
    n = len(df)

    trend_s = _trend_labels(df, sma_short, sma_long, slope_threshold, hysteresis_bars)
    vol_s = _vol_labels(df, atr_window)

    labeled = df.with_columns([
        trend_s.alias("trend_state"),
        vol_s.alias("vol_state"),
    ])

    # ── Coverage ─────────────────────────────────────────────────────────────
    def _pct(col: str) -> Dict[str, float]:
        vc = labeled.group_by(col).agg(pl.len().alias("cnt"))
        return {row[col]: row["cnt"] / n for row in vc.to_dicts()}

    tp = _pct("trend_state")
    vp = _pct("vol_state")

    pct_tu = tp.get("TREND_UP", 0.0)
    pct_td = tp.get("TREND_DOWN", 0.0)
    pct_fl = tp.get("FLAT", 0.0)
    pct_lv = vp.get("LOW_VOL", 0.0)
    pct_mv = vp.get("MID_VOL", 0.0)
    pct_hv = vp.get("HIGH_VOL", 0.0)

    all_pcts = [pct_tu, pct_td, pct_fl, pct_lv, pct_mv, pct_hv]
    min_pct = min(all_pcts)
    coverage_ok: bool = min_pct >= _MIN_STATE_PCT and max(all_pcts) <= _MAX_STATE_PCT

    # ── Stability ─────────────────────────────────────────────────────────────
    t_sw = _count_switches(labeled["trend_state"])
    v_sw = _count_switches(labeled["vol_state"])
    days = n / bars_per_day

    t_spd = t_sw / max(days, 1.0)
    v_spd = v_sw / max(days, 1.0)
    t_med = _median_run_bars(labeled["trend_state"])
    v_med = _median_run_bars(labeled["vol_state"])

    # ── Separability ──────────────────────────────────────────────────────────
    flat_ret = (
        labeled.filter(pl.col("trend_state") == "FLAT")["log_return"].drop_nulls().to_numpy()
    )
    trend_ret = (
        labeled.filter(pl.col("trend_state") != "FLAT")["log_return"].drop_nulls().to_numpy()
    )
    low_atr = (
        labeled.filter(pl.col("vol_state") == "LOW_VOL")["atr"].drop_nulls().to_numpy()
    )
    high_atr = (
        labeled.filter(pl.col("vol_state") == "HIGH_VOL")["atr"].drop_nulls().to_numpy()
    )

    if len(flat_ret) < 10 or len(trend_ret) < 10:
        t_overlap, t_bhatt = 1.0, 0.0
    else:
        t_overlap = _histogram_overlap(flat_ret, trend_ret)
        t_bhatt = _bhattacharyya(flat_ret, trend_ret)

    if len(low_atr) < 10 or len(high_atr) < 10:
        v_overlap, v_bhatt = 1.0, 0.0
    else:
        v_overlap = _histogram_overlap(low_atr, high_atr)
        v_bhatt = _bhattacharyya(low_atr, high_atr)

    row: Dict[str, Any] = {
        # params
        "sma_short": sma_short,
        "sma_long": sma_long,
        "slope_threshold": slope_threshold,
        "atr_window": atr_window,
        "hysteresis_bars": hysteresis_bars,
        # coverage
        "pct_trend_up": round(pct_tu, 4),
        "pct_trend_down": round(pct_td, 4),
        "pct_flat": round(pct_fl, 4),
        "pct_low_vol": round(pct_lv, 4),
        "pct_mid_vol": round(pct_mv, 4),
        "pct_high_vol": round(pct_hv, 4),
        "min_state_pct": round(min_pct, 4),
        "coverage_ok": coverage_ok,
        # stability
        "trend_switches_per_day": round(t_spd, 3),
        "vol_switches_per_day": round(v_spd, 3),
        "median_trend_run_bars": round(t_med, 1),
        "median_vol_run_bars": round(v_med, 1),
        # separability
        "trend_return_overlap": round(t_overlap, 4),
        "vol_atr_overlap": round(v_overlap, 4),
        "trend_bhatt": round(t_bhatt, 4),
        "vol_bhatt": round(v_bhatt, 4),
    }
    row["score"] = round(_score_grid_row(row), 4)
    return row


def _score_grid_row(row: Dict[str, Any]) -> float:
    """Composite score ∈ [-0.1, 0.9] — higher is better.

    50% stability (low trend churn), 40% separability (low overlap),
    10% coverage sanity (penalty if violated).
    """
    churn_score = max(0.0, 1.0 - row["trend_switches_per_day"] / _CHURN_TARGET)
    sep_score = (
        0.5 * (1.0 - row["trend_return_overlap"])
        + 0.5 * (1.0 - row["vol_atr_overlap"])
    )
    cov_pen = 0.0 if row["coverage_ok"] else 1.0
    return _W_STABILITY * churn_score + _W_SEP * sep_score - _W_COVERAGE * cov_pen


# ── Full grid runner ──────────────────────────────────────────────────────────

def run_regime_grid(
    df: pl.DataFrame,
    *,
    sma_shorts: List[int] = GRID_SMA_SHORTS,
    sma_longs: List[int] = GRID_SMA_LONGS,
    slope_thresholds: List[float] = GRID_SLOPE_THRESHOLDS,
    atr_windows: List[int] = GRID_ATR_WINDOWS,
    hysteresis_bars: List[int] = GRID_HYSTERESIS,
    tf_minutes: int = 5,
) -> pl.DataFrame:
    """Run all valid parameter combinations and return sorted results.

    Skips sma_short >= sma_long (undefined).
    Returns polars DataFrame sorted by score descending.
    """
    rows: List[Dict[str, Any]] = []
    for sms, sml, st, aw, hb in product(
        sma_shorts, sma_longs, slope_thresholds, atr_windows, hysteresis_bars
    ):
        if sms >= sml:
            continue
        rows.append(
            compute_grid_row(
                df,
                sma_short=sms,
                sma_long=sml,
                slope_threshold=st,
                atr_window=aw,
                hysteresis_bars=hb,
                tf_minutes=tf_minutes,
            )
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("score", descending=True)
