"""Market structure analysis for Phase R1.

Five analysis blocks — all pure functions, polars-native where possible.
No scipy dependency. Histogram-based statistics throughout.

Block 1: compute_distribution_stats   – percentile tables and shape stats
Block 2: compute_persistence_stats    – run-length distributions + autocorr
Block 3: compute_regime_separability  – 2-axis proxy labeling + Bhattacharyya
Block 4: compute_structural_breaks    – Hurst R/S, vol clustering, rolling shift
Block 5: simulate_stability_grid      – threshold/hysteresis sweep (optional)

Input DataFrames are expected to contain STRESS_OUTPUT_COLUMNS from stress.py:
  timestamp, close, log_return, realized_vol, atr, gap, bar_range, z_*
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import polars as pl

# ── Constants ───────────────────────────────────────────────────────────────

# Metrics produced by stress.py analysed in Block 1
DISTRIBUTION_METRICS: Tuple[str, ...] = (
    "atr",
    "realized_vol",
    "log_return",
    "bar_range",
)

# SMA periods mirror config/aurora/regime.yaml models.sma_trend
_SMA_SHORT: int = 24
_SMA_LONG: int = 96

# Normalized slope threshold defining FLAT zone (0.2%)
_SLOPE_FLAT_THRESHOLD: float = 0.002

# Fraction of distributional overlap that triggers LOW_SEPARABILITY flag
SEPARABILITY_OVERLAP_WARN: float = 0.70

# Histogram bins for Bhattacharyya
_N_BINS: int = 50


# ── Block 1: Distribution Stats ─────────────────────────────────────────────

def compute_distribution_stats(df: pl.DataFrame) -> Dict[str, Any]:
    """Compute percentile tables and shape statistics for key stress metrics.

    Args:
        df: DataFrame with columns from stress.py output
            (atr, realized_vol, log_return, bar_range).

    Returns:
        Nested dict {metric: {count, mean, std, skew, kurtosis, p25..p99, tail_ratio}}.
        Missing metrics are silently skipped.
    """
    result: Dict[str, Any] = {}
    for m in DISTRIBUTION_METRICS:
        if m not in df.columns:
            continue
        col = df[m].drop_nulls()
        if len(col) < 2:
            continue
        p50 = float(col.quantile(0.50, interpolation="nearest"))
        p99 = float(col.quantile(0.99, interpolation="nearest"))
        tail_ratio: Optional[float] = None
        if p50 and abs(p50) > 1e-12:
            tail_ratio = round(abs(p99 / p50), 3)
        result[m] = {
            "count": len(col),
            "mean": round(float(col.mean()), 8),
            "std": round(float(col.std()), 8),
            "skew": round(float(col.skew()), 4),
            "kurtosis": round(float(col.kurtosis()), 4),
            "p25": round(float(col.quantile(0.25, interpolation="nearest")), 8),
            "p50": round(p50, 8),
            "p75": round(float(col.quantile(0.75, interpolation="nearest")), 8),
            "p90": round(float(col.quantile(0.90, interpolation="nearest")), 8),
            "p95": round(float(col.quantile(0.95, interpolation="nearest")), 8),
            "p99": round(p99, 8),
            "tail_ratio": tail_ratio,
        }
    return result


# ── Block 2: Persistence Stats ───────────────────────────────────────────────

def compute_persistence_stats(df: pl.DataFrame, state_col: str) -> Dict[str, Any]:
    """Compute run-length statistics per state and signal autocorrelation.

    Args:
        df:        DataFrame with the state column plus optional
                   log_return and atr columns.
        state_col: Name of the discrete state column (e.g. "state").

    Returns:
        Dict with per-state run statistics and autocorrelation values.
        Returns {} if state_col missing or df is empty.
    """
    if state_col not in df.columns or len(df) == 0:
        return {}

    states_list = df[state_col].to_list()

    # ── Run-length encoding ──────────────────────────────────────────────
    per_state: Dict[Any, List[int]] = defaultdict(list)
    cur = states_list[0]
    cur_len = 1
    for s in states_list[1:]:
        if s == cur:
            cur_len += 1
        else:
            per_state[str(cur)].append(cur_len)
            cur = s
            cur_len = 1
    per_state[str(cur)].append(cur_len)

    result: Dict[str, Any] = {}
    for state, lengths in per_state.items():
        arr = np.array(lengths, dtype=float)
        result[state] = {
            "count_runs": len(arr),
            "mean_run_bars": round(float(arr.mean()), 2),
            "median_run_bars": round(float(np.median(arr)), 2),
            "p25_run": round(float(np.percentile(arr, 25)), 1),
            "p75_run": round(float(np.percentile(arr, 75)), 1),
            "p90_run": round(float(np.percentile(arr, 90)), 1),
            "longest_run_bars": int(arr.max()),
        }

    # ── Signal autocorrelation ──────────────────────────────────────────
    if "log_return" in df.columns:
        ret = df["log_return"].drop_nulls().to_numpy()
        if len(ret) > 2:
            result["autocorr_return_lag1"] = round(
                float(np.corrcoef(ret[:-1], ret[1:])[0, 1]), 4
            )

    if "atr" in df.columns:
        atr = df["atr"].drop_nulls().to_numpy()
        if len(atr) > 1:
            result["autocorr_vol_lag1"] = round(
                float(np.corrcoef(atr[:-1], atr[1:])[0, 1]), 4
            )
        if len(atr) > 5:
            result["autocorr_vol_lag5"] = round(
                float(np.corrcoef(atr[:-5], atr[5:])[0, 1]), 4
            )

    return result


# ── Block 3: Regime Separability ────────────────────────────────────────────

def _proxy_labels(df: pl.DataFrame) -> pl.DataFrame:
    """Add 2-axis proxy regime labels to DataFrame.

    Directionality axis: TREND_UP / TREND_DOWN / FLAT (normalized SMA slope).
    Vol bucket axis:     LOW_VOL / MID_VOL / HIGH_VOL (ATR percentile tertiles).

    Requires columns: close, atr.
    NaN rows (during warmup) are labeled None and should be dropped by caller.
    """
    if "close" not in df.columns or "atr" not in df.columns:
        return df.with_columns([
            pl.lit(None, dtype=pl.Utf8).alias("directionality"),
            pl.lit(None, dtype=pl.Utf8).alias("vol_bucket"),
        ])

    # Normalized SMA slope
    df = df.with_columns([
        pl.col("close")
        .rolling_mean(window_size=_SMA_SHORT, min_periods=_SMA_SHORT)
        .alias("_sma_short"),
        pl.col("close")
        .rolling_mean(window_size=_SMA_LONG, min_periods=_SMA_LONG)
        .alias("_sma_long"),
    ])
    df = df.with_columns([
        ((pl.col("_sma_short") - pl.col("_sma_long")) / pl.col("close"))
        .alias("_slope"),
    ])
    df = df.with_columns([
        pl.when(pl.col("_slope") > _SLOPE_FLAT_THRESHOLD)
        .then(pl.lit("TREND_UP"))
        .when(pl.col("_slope") < -_SLOPE_FLAT_THRESHOLD)
        .then(pl.lit("TREND_DOWN"))
        .otherwise(pl.lit("FLAT"))
        .alias("directionality"),
    ])

    # ATR percentile tertiles (dynamic: uses data's own p33/p66)
    atr_clean = df["atr"].drop_nulls()
    atr_p33 = float(atr_clean.quantile(0.333, interpolation="nearest"))
    atr_p66 = float(atr_clean.quantile(0.667, interpolation="nearest"))
    df = df.with_columns([
        pl.when(pl.col("atr").is_null())
        .then(pl.lit(None, dtype=pl.Utf8))
        .when(pl.col("atr") < atr_p33)
        .then(pl.lit("LOW_VOL"))
        .when(pl.col("atr") < atr_p66)
        .then(pl.lit("MID_VOL"))
        .otherwise(pl.lit("HIGH_VOL"))
        .alias("vol_bucket"),
    ])

    return df.drop(["_sma_short", "_sma_long", "_slope"])


def _histogram_overlap(a: np.ndarray, b: np.ndarray, n_bins: int = _N_BINS) -> float:
    """Histogram overlap coefficient: sum(min(p_i, q_i)) on shared bins.

    Returns value in [0, 1]: 1.0 = identical distributions, 0.0 = no overlap.
    """
    c_min = float(min(a.min(), b.min()))
    c_max = float(max(a.max(), b.max()))
    if c_max <= c_min:
        return 1.0
    bins = np.linspace(c_min, c_max, n_bins + 1)
    h_a, _ = np.histogram(a, bins=bins)
    h_b, _ = np.histogram(b, bins=bins)
    p_a = h_a / (h_a.sum() + 1e-12)
    p_b = h_b / (h_b.sum() + 1e-12)
    return float(np.minimum(p_a, p_b).sum())


def _bhattacharyya(a: np.ndarray, b: np.ndarray, n_bins: int = _N_BINS) -> float:
    """Bhattacharyya distance (histogram-based, no scipy).

    Returns value >= 0: 0 = identical distributions, larger = more separated.
    """
    c_min = float(min(a.min(), b.min()))
    c_max = float(max(a.max(), b.max()))
    if c_max <= c_min:
        return 0.0
    bins = np.linspace(c_min, c_max, n_bins + 1)
    h_a, _ = np.histogram(a, bins=bins)
    h_b, _ = np.histogram(b, bins=bins)
    p_a = h_a / (h_a.sum() + 1e-12)
    p_b = h_b / (h_b.sum() + 1e-12)
    bc_coeff = float(np.sqrt(p_a * p_b).sum())
    return float(-math.log(bc_coeff + 1e-12))


def compute_regime_separability(df: pl.DataFrame) -> Dict[str, Any]:
    """Compute separability metrics between proxy-labeled regimes.

    Proxy labeling is 2-axis:
      - Directionality: TREND_UP / TREND_DOWN / FLAT (SMA slope vs threshold)
      - Vol bucket:     LOW_VOL / MID_VOL / HIGH_VOL (ATR percentile tertiles)

    Separability measured as histogram-based Bhattacharyya distance and
    overlap coefficient. Flags pairs with overlap > SEPARABILITY_OVERLAP_WARN.

    Args:
        df: DataFrame with columns: close, atr, log_return.

    Returns:
        Dict with label counts, Bhattacharyya distances, overlap coefficients,
        and LOW_SEPARABILITY flags.
    """
    if "close" not in df.columns or "atr" not in df.columns:
        return {"error": "Missing required columns: close, atr"}

    labeled = _proxy_labels(df).drop_nulls(["directionality", "vol_bucket"])
    if len(labeled) == 0:
        return {"error": "No labeled rows after proxy labeling (insufficient warmup data)"}

    result: Dict[str, Any] = {}

    # ── Label distribution counts ─────────────────────────────────────────
    dir_counts = (
        labeled.group_by("directionality").len().sort("directionality").to_dicts()
    )
    vol_counts = (
        labeled.group_by("vol_bucket").len().sort("vol_bucket").to_dicts()
    )
    result["directionality_counts"] = {
        r["directionality"]: r["len"] for r in dir_counts
    }
    result["vol_bucket_counts"] = {r["vol_bucket"]: r["len"] for r in vol_counts}

    # ── Vol separability across directionality labels ─────────────────────
    dir_pairs = [
        ("TREND_UP", "FLAT"),
        ("TREND_DOWN", "FLAT"),
        ("TREND_UP", "TREND_DOWN"),
    ]
    vol_sep: Dict[str, Any] = {}
    for label_a, label_b in dir_pairs:
        a_arr = (
            labeled.filter(pl.col("directionality") == label_a)["atr"]
            .drop_nulls()
            .to_numpy()
        )
        b_arr = (
            labeled.filter(pl.col("directionality") == label_b)["atr"]
            .drop_nulls()
            .to_numpy()
        )
        if len(a_arr) < 5 or len(b_arr) < 5:
            continue
        overlap = _histogram_overlap(a_arr, b_arr)
        bhatt = _bhattacharyya(a_arr, b_arr)
        vol_sep[f"{label_a}_vs_{label_b}"] = {
            "metric": "atr",
            "overlap_coefficient": round(overlap, 4),
            "bhattacharyya_distance": round(bhatt, 4),
            "low_separability": bool(overlap > SEPARABILITY_OVERLAP_WARN),
        }
    result["vol_separability_by_direction"] = vol_sep

    # ── Return separability across vol bucket labels ──────────────────────
    ret_sep: Dict[str, Any] = {}
    if "log_return" in labeled.columns:
        vol_pairs = [
            ("LOW_VOL", "HIGH_VOL"),
            ("LOW_VOL", "MID_VOL"),
            ("MID_VOL", "HIGH_VOL"),
        ]
        for label_a, label_b in vol_pairs:
            a_arr = (
                labeled.filter(pl.col("vol_bucket") == label_a)["log_return"]
                .drop_nulls()
                .to_numpy()
            )
            b_arr = (
                labeled.filter(pl.col("vol_bucket") == label_b)["log_return"]
                .drop_nulls()
                .to_numpy()
            )
            if len(a_arr) < 5 or len(b_arr) < 5:
                continue
            overlap = _histogram_overlap(a_arr, b_arr)
            bhatt = _bhattacharyya(a_arr, b_arr)
            ret_sep[f"{label_a}_vs_{label_b}"] = {
                "metric": "log_return",
                "overlap_coefficient": round(overlap, 4),
                "bhattacharyya_distance": round(bhatt, 4),
                "low_separability": bool(overlap > SEPARABILITY_OVERLAP_WARN),
            }
    result["return_separability_by_vol_bucket"] = ret_sep

    return result


# ── Block 4: Structural Breaks ───────────────────────────────────────────────

def _hurst_rs(series: np.ndarray, min_chunk: int = 10) -> float:
    """Estimate Hurst exponent via Rescaled Range (R/S) analysis.

    H < 0.5 → mean-reversion tendency
    H ≈ 0.5 → random walk (efficient market)
    H > 0.5 → trending tendency (momentum)

    Returns value in [0, 1]; 0.5 on insufficient data.
    """
    n = len(series)
    if n < 20:
        return 0.5

    chunk_sizes: List[int] = []
    cs = min_chunk
    while cs <= n // 2:
        chunk_sizes.append(cs)
        cs = int(cs * 1.5) + 1
    # deduplicate while preserving order
    seen: set[int] = set()
    chunk_sizes = [x for x in chunk_sizes if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    if len(chunk_sizes) < 2:
        return 0.5

    rs_log_pairs: List[Tuple[float, float]] = []
    for cs in chunk_sizes:
        rs_list: List[float] = []
        for start in range(0, n - cs + 1, cs):
            chunk = series[start: start + cs]
            mean = float(chunk.mean())
            deviations = np.cumsum(chunk - mean)
            r = float(deviations.max() - deviations.min())
            s = float(chunk.std(ddof=1))
            if s > 1e-12:
                rs_list.append(r / s)
        if rs_list:
            rs_log_pairs.append(
                (math.log(cs), math.log(float(np.mean(rs_list))))
            )

    if len(rs_log_pairs) < 2:
        return 0.5

    xs = np.array([x for x, _ in rs_log_pairs])
    ys = np.array([y for _, y in rs_log_pairs])
    slope = float(np.polyfit(xs, ys, 1)[0])
    return float(np.clip(slope, 0.0, 1.0))


def compute_structural_breaks(
    df: pl.DataFrame,
    rolling_window: int = 100,
) -> Dict[str, Any]:
    """Compute structural break indicators.

    Metrics:
      hurst_return:            Hurst exponent on log_return (R/S method)
      hurst_vol:               Hurst exponent on atr (R/S method)
      vol_clustering_lag1:     autocorr(atr, lag=1) — GARCH-like vol memory
      vol_clustering_lag5:     autocorr(atr, lag=5)
      rolling_mean_shift:      std(rolling_mean(return, window)) — trend instability
      rolling_var_shift:       std(rolling_std(atr, window)) — regime instability
      hurst_return_interpretation: "mean_reversion" | "random_walk" | "trending"

    Args:
        df:             DataFrame with log_return and atr columns.
        rolling_window: Window for rolling statistics (default 100 bars).

    Returns:
        Dict of structural metrics. Only computes what columns are available.
    """
    result: Dict[str, Any] = {}

    if "log_return" in df.columns:
        ret = df["log_return"].drop_nulls().to_numpy()
        if len(ret) >= 20:
            result["hurst_return"] = round(_hurst_rs(ret), 4)
        if len(ret) >= rolling_window * 2:
            step = rolling_window // 2
            rolling_means = np.array([
                ret[i: i + rolling_window].mean()
                for i in range(0, len(ret) - rolling_window + 1, step)
            ])
            result["rolling_mean_shift"] = round(float(rolling_means.std()), 8)

    if "atr" in df.columns:
        atr = df["atr"].drop_nulls().to_numpy()
        if len(atr) >= 20:
            result["hurst_vol"] = round(_hurst_rs(atr), 4)
        if len(atr) > 1:
            result["vol_clustering_lag1"] = round(
                float(np.corrcoef(atr[:-1], atr[1:])[0, 1]), 4
            )
        if len(atr) > 5:
            result["vol_clustering_lag5"] = round(
                float(np.corrcoef(atr[:-5], atr[5:])[0, 1]), 4
            )
        if len(atr) >= rolling_window * 2:
            step = rolling_window // 2
            rolling_stds = np.array([
                atr[i: i + rolling_window].std()
                for i in range(0, len(atr) - rolling_window + 1, step)
            ])
            result["rolling_var_shift"] = round(float(rolling_stds.std()), 8)

    # Interpretation hint
    hurst_return = result.get("hurst_return")
    if hurst_return is not None:
        if hurst_return < 0.45:
            result["hurst_return_interpretation"] = "mean_reversion"
        elif hurst_return > 0.55:
            result["hurst_return_interpretation"] = "trending"
        else:
            result["hurst_return_interpretation"] = "random_walk"

    return result


# ── Block 5: Stability Grid (optional) ──────────────────────────────────────

def simulate_stability_grid(
    df: pl.DataFrame,
    *,
    thresholds: Optional[List[float]] = None,
    consecutives: Optional[List[int]] = None,
    min_durations: Optional[List[int]] = None,
    weights: Optional[Dict[str, float]] = None,
    z_thresholds: Optional[Dict[str, float]] = None,
    tf_minutes: int = 5,
) -> pl.DataFrame:
    """Grid search over stress actuator config space on real data.

    Reuses existing actuator_rules.run_actuator and aggregation.compute_stress_level.
    Requires z-score columns from stress.py output in df.

    Args:
        df:             DataFrame with z_atr, z_realized_vol, z_gap, z_bar_range.
        thresholds:     enter_stress values (default [0.55, 0.60, 0.65, 0.70]).
        consecutives:   consecutive_bars_enter (default [2, 3, 4, 6, 8]).
        min_durations:  min_duration_bars (default [3, 5, 10, 15, 20]).
        weights:        Aggregation weights (default: atr=0.30, vol=0.30, gap=0.20, range=0.20).
        z_thresholds:   Per-trigger sigma thresholds (default: atr=2.0, vol=2.0, gap=3.0, range=2.5).
        tf_minutes:     Timeframe in minutes for switches/day calculation.

    Returns:
        DataFrame with one row per grid combination, sorted by switches_per_day ascending.
        Columns: threshold, consecutive, min_duration, total_switches,
                 switches_per_day, pct_normal, pct_stress, pct_extreme, longest_normal_run.
    """
    from tools.parquet_pipeline.actuator_rules import ActuatorConfig, run_actuator
    from tools.parquet_pipeline.aggregation import compute_stress_level

    if thresholds is None:
        thresholds = [0.55, 0.60, 0.65, 0.70]
    if consecutives is None:
        consecutives = [2, 3, 4, 6, 8]
    if min_durations is None:
        min_durations = [3, 5, 10, 15, 20]
    if weights is None:
        weights = {"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20}
    if z_thresholds is None:
        z_thresholds = {
            "atr_sigma": 2.0,
            "vol_sigma": 2.0,
            "gap_sigma": 3.0,
            "range_sigma": 2.5,
        }

    # Compute stress_level once (shared across all grid combos)
    stress_df = compute_stress_level(
        df.lazy(),
        method="weighted_vote",
        weights=weights,
        thresholds=z_thresholds,
        k=None,
    ).collect()
    sl_list = stress_df["stress_level"].to_list()

    n_bars = len(sl_list)
    bars_per_day = (24 * 60) / max(tf_minutes, 1)

    rows: List[Dict[str, Any]] = []
    for thresh in thresholds:
        for consec in consecutives:
            for min_dur in min_durations:
                cfg = ActuatorConfig(
                    enter_stress=thresh,
                    exit_stress=max(0.0, thresh - 0.20),
                    enter_extreme=0.85,
                    exit_extreme=0.70,
                    consecutive_bars_enter=consec,
                    consecutive_bars_exit=max(2, consec - 1),
                    min_duration_bars=min_dur,
                    switch_window_bars=200,
                    max_switches_per_window=3,
                )
                res = run_actuator(sl_list, cfg)
                states = res.states
                n_stress = states.count("STRESS")
                n_extreme = states.count("EXTREME")
                n_normal = states.count("NORMAL")
                days = n_bars / bars_per_day if bars_per_day > 0 else 1.0

                # Longest NORMAL run
                longest_normal = 0
                cur_len = 0
                for s in states:
                    if s == "NORMAL":
                        cur_len += 1
                        if cur_len > longest_normal:
                            longest_normal = cur_len
                    else:
                        cur_len = 0

                rows.append({
                    "threshold": thresh,
                    "consecutive": consec,
                    "min_duration": min_dur,
                    "total_switches": res.total_switches,
                    "switches_per_day": round(res.total_switches / max(days, 1), 3),
                    "pct_normal": round(n_normal / n_bars * 100, 1) if n_bars else 0.0,
                    "pct_stress": round(n_stress / n_bars * 100, 1) if n_bars else 0.0,
                    "pct_extreme": round(n_extreme / n_bars * 100, 1) if n_bars else 0.0,
                    "longest_normal_run": longest_normal,
                })

    return pl.DataFrame(rows).sort("switches_per_day")
