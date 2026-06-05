"""Tests for Phase R1: tools/parquet_pipeline/market_structure.py

Tests use synthetic DataFrames — no parquet I/O.
All assertions are on numeric properties (bounds, shapes, keys).
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import polars as pl
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stress_df(
    n: int = 500,
    *,
    seed: int = 42,
    close_trend: float = 0.0,   # drift per bar in close price
    close_noise: float = 1.0,
    atr_base: float = 50.0,
    atr_noise: float = 10.0,
) -> pl.DataFrame:
    """Synthetic stress-output-style DataFrame."""
    rng = np.random.default_rng(seed)
    close = 10_000.0 + np.cumsum(rng.normal(close_trend, close_noise, n))
    log_return = np.concatenate([[0.0], np.diff(np.log(np.abs(close) + 1))])
    atr = np.abs(rng.normal(atr_base, atr_noise, n))
    realized_vol = np.abs(rng.normal(0.001, 0.0002, n))
    bar_range = np.abs(rng.normal(0.003, 0.001, n))
    # z-score columns (needed for stability grid)
    z_atr = rng.normal(0, 1, n)
    z_realized_vol = rng.normal(0, 1, n)
    z_gap = rng.normal(0, 1, n)
    z_bar_range = rng.normal(0, 1, n)
    return pl.DataFrame({
        "timestamp": list(range(n)),
        "close": close.tolist(),
        "log_return": log_return.tolist(),
        "realized_vol": realized_vol.tolist(),
        "atr": atr.tolist(),
        "gap": np.abs(rng.normal(0.001, 0.0005, n)).tolist(),
        "bar_range": bar_range.tolist(),
        "z_atr": z_atr.tolist(),
        "z_realized_vol": z_realized_vol.tolist(),
        "z_gap": z_gap.tolist(),
        "z_bar_range": z_bar_range.tolist(),
    })


def _make_trending_df(n: int = 500, drift: float = 5.0) -> pl.DataFrame:
    """DataFrame with a clear upward trend in close price."""
    return _make_stress_df(n=n, close_trend=drift, close_noise=0.1)


def _make_flat_df(n: int = 500) -> pl.DataFrame:
    """DataFrame with flat (near-zero drift) close price."""
    return _make_stress_df(n=n, close_trend=0.0, close_noise=0.01)


# ── Block 1: Distribution Stats ───────────────────────────────────────────────

class TestComputeDistributionStats:

    def test_all_four_metrics_present(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = _make_stress_df()
        result = compute_distribution_stats(df)
        for m in ("atr", "realized_vol", "log_return", "bar_range"):
            assert m in result, f"Missing metric: {m}"

    def test_percentile_ordering(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = _make_stress_df()
        result = compute_distribution_stats(df)
        for m in ("atr", "realized_vol"):
            stats = result[m]
            assert stats["p25"] <= stats["p50"] <= stats["p75"] <= stats["p90"] <= stats["p99"]

    def test_all_values_finite(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = _make_stress_df()
        result = compute_distribution_stats(df)
        for m, stats in result.items():
            for k, v in stats.items():
                if v is not None:
                    assert math.isfinite(float(v)), f"{m}.{k} = {v} is not finite"

    def test_missing_columns_skipped(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = pl.DataFrame({"atr": [1.0, 2.0, 3.0]})
        result = compute_distribution_stats(df)
        assert "atr" in result
        assert "log_return" not in result
        assert "bar_range" not in result

    def test_empty_df_returns_empty(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = pl.DataFrame({"atr": pl.Series([], dtype=pl.Float64)})
        result = compute_distribution_stats(df)
        # either empty dict or atr not in result (single col with 0 rows skipped)
        assert result == {} or "atr" not in result

    def test_tail_ratio_is_nonnegative(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_distribution_stats
        df = _make_stress_df()
        result = compute_distribution_stats(df)
        for m in ("atr", "realized_vol"):
            tail = result[m].get("tail_ratio")
            if tail is not None:
                assert tail >= 0.0


# ── Block 2: Persistence Stats ────────────────────────────────────────────────

class TestComputePersistenceStats:

    def _df_with_states(self, states: list) -> pl.DataFrame:
        n = len(states)
        rng = np.random.default_rng(0)
        return pl.DataFrame({
            "state": states,
            "log_return": rng.normal(0, 0.001, n).tolist(),
            "atr": np.abs(rng.normal(50, 5, n)).tolist(),
        })

    def test_basic_run_detection(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        states = ["A"] * 10 + ["B"] * 5 + ["A"] * 3
        df = self._df_with_states(states)
        result = compute_persistence_stats(df, state_col="state")
        assert "A" in result
        assert "B" in result
        assert result["A"]["count_runs"] == 2
        assert result["B"]["count_runs"] == 1
        assert result["B"]["longest_run_bars"] == 5

    def test_all_same_state(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        states = ["X"] * 100
        df = self._df_with_states(states)
        result = compute_persistence_stats(df, state_col="state")
        assert result["X"]["count_runs"] == 1
        assert result["X"]["longest_run_bars"] == 100

    def test_alternating_states(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        states = ["A", "B"] * 20
        df = self._df_with_states(states)
        result = compute_persistence_stats(df, state_col="state")
        assert result["A"]["median_run_bars"] == 1.0
        assert result["A"]["count_runs"] == 20

    def test_autocorr_keys_present(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        df = _make_stress_df()
        df = df.with_columns(pl.lit("NORMAL").alias("state"))
        result = compute_persistence_stats(df, state_col="state")
        assert "autocorr_return_lag1" in result
        assert "autocorr_vol_lag1" in result

    def test_missing_state_col_returns_empty(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = compute_persistence_stats(df, state_col="nonexistent")
        assert result == {}

    def test_no_keyerror_without_atr(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_persistence_stats
        df = pl.DataFrame({"state": ["A", "A", "B"], "log_return": [0.001, -0.001, 0.002]})
        result = compute_persistence_stats(df, state_col="state")
        assert "autocorr_vol_lag1" not in result  # no atr column
        assert "A" in result  # but state runs are still computed


# ── Histogram helpers ────────────────────────────────────────────────────────

class TestHistogramHelpers:

    def test_bhattacharyya_identical_arrays_near_zero(self) -> None:
        from tools.parquet_pipeline.market_structure import _bhattacharyya
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0] * 20)
        dist = _bhattacharyya(arr, arr)
        assert dist < 0.1, f"Expected near-zero, got {dist}"

    def test_bhattacharyya_non_overlapping_is_large(self) -> None:
        from tools.parquet_pipeline.market_structure import _bhattacharyya
        a = np.arange(0, 100, dtype=float)
        b = np.arange(1000, 1100, dtype=float)
        dist = _bhattacharyya(a, b)
        assert dist > 2.0, f"Expected large distance, got {dist}"

    def test_histogram_overlap_identical_is_one(self) -> None:
        from tools.parquet_pipeline.market_structure import _histogram_overlap
        arr = np.linspace(0, 1, 100)
        overlap = _histogram_overlap(arr, arr)
        assert overlap > 0.95, f"Expected ~1.0, got {overlap}"

    def test_histogram_overlap_non_overlapping_is_zero(self) -> None:
        from tools.parquet_pipeline.market_structure import _histogram_overlap
        a = np.arange(0, 100, dtype=float)
        b = np.arange(1000, 1100, dtype=float)
        overlap = _histogram_overlap(a, b)
        assert overlap < 0.05, f"Expected ~0.0, got {overlap}"


# ── Block 3: Regime Separability ─────────────────────────────────────────────

class TestProxyLabels:

    def test_trending_close_gives_trend_up(self) -> None:
        from tools.parquet_pipeline.market_structure import _proxy_labels
        # Strongly trending sequence — SMA short >> SMA long
        n = 200
        close = np.cumsum(np.ones(n) * 10.0) + 1000.0
        atr = np.ones(n) * 50.0
        df = pl.DataFrame({"close": close.tolist(), "atr": atr.tolist()})
        labeled = _proxy_labels(df).drop_nulls(["directionality"])
        assert len(labeled) > 0
        majority = labeled["directionality"].mode()[0]
        assert majority == "TREND_UP"

    def test_flat_close_gives_flat(self) -> None:
        from tools.parquet_pipeline.market_structure import _proxy_labels
        n = 300
        rng = np.random.default_rng(1)
        # Flat: tiny noise around constant
        close = 1000.0 + rng.normal(0, 0.001, n)
        atr = np.ones(n) * 50.0
        df = pl.DataFrame({"close": close.tolist(), "atr": atr.tolist()})
        labeled = _proxy_labels(df).drop_nulls(["directionality"])
        majority = labeled["directionality"].mode()[0]
        assert majority == "FLAT"

    def test_vol_bucket_three_groups(self) -> None:
        from tools.parquet_pipeline.market_structure import _proxy_labels
        n = 300
        rng = np.random.default_rng(2)
        close = 1000.0 + rng.normal(0, 0.001, n)
        # Distinct ATR values to force all three buckets
        atr = np.concatenate([
            np.ones(100) * 10.0,
            np.ones(100) * 50.0,
            np.ones(100) * 200.0,
        ])
        df = pl.DataFrame({"close": close.tolist(), "atr": atr.tolist()})
        labeled = _proxy_labels(df).drop_nulls(["vol_bucket"])
        buckets = set(labeled["vol_bucket"].to_list())
        assert "LOW_VOL" in buckets
        assert "HIGH_VOL" in buckets

    def test_missing_close_returns_null_labels(self) -> None:
        from tools.parquet_pipeline.market_structure import _proxy_labels
        df = pl.DataFrame({"atr": [50.0, 50.0, 50.0]})
        labeled = _proxy_labels(df)
        assert "directionality" in labeled.columns
        # All should be null when close is missing
        assert labeled["directionality"].is_null().all()


class TestComputeRegimeSeparability:

    def test_well_separated_data_low_overlap(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_regime_separability
        n = 300
        rng = np.random.default_rng(0)
        # Strongly trending close
        close = np.cumsum(np.ones(n) * 5.0) + 1000.0
        log_return = np.concatenate([[0.0], np.diff(np.log(close))])
        atr_high = rng.normal(200, 10, n // 2)
        atr_low = rng.normal(10, 1, n // 2)
        atr = np.concatenate([atr_high, atr_low])
        df = pl.DataFrame({
            "close": close.tolist(),
            "atr": atr.tolist(),
            "log_return": log_return.tolist(),
        })
        result = compute_regime_separability(df)
        assert "error" not in result
        assert "vol_separability_by_direction" in result
        assert "return_separability_by_vol_bucket" in result

    def test_missing_close_returns_error(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_regime_separability
        df = pl.DataFrame({"atr": [50.0, 50.0]})
        result = compute_regime_separability(df)
        assert "error" in result

    def test_directionality_counts_has_keys(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_regime_separability
        df = _make_trending_df(n=500)
        result = compute_regime_separability(df)
        if "error" in result:
            pytest.skip("Insufficient data for proxy labeling")
        counts = result.get("directionality_counts", {})
        assert len(counts) > 0, "Expected at least one directionality label"

    def test_overlap_coefficients_in_range(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_regime_separability
        df = _make_stress_df(n=600)
        result = compute_regime_separability(df)
        for key, sep_dict in result.get("vol_separability_by_direction", {}).items():
            oc = sep_dict.get("overlap_coefficient")
            if oc is not None:
                assert 0.0 <= oc <= 1.0, f"{key}.overlap_coefficient={oc} out of [0,1]"

    def test_low_separability_flag_triggers(self) -> None:
        from tools.parquet_pipeline.market_structure import (
            _bhattacharyya, _histogram_overlap, SEPARABILITY_OVERLAP_WARN,
        )
        # Identical arrays → overlap = 1.0 → low_separability should trigger
        arr = np.arange(0, 100, dtype=float)
        overlap = _histogram_overlap(arr, arr)
        assert overlap > SEPARABILITY_OVERLAP_WARN


# ── Block 4: Structural Breaks ────────────────────────────────────────────────

class TestComputeStructuralBreaks:

    def test_hurst_in_unit_interval(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_structural_breaks
        df = _make_stress_df(n=500)
        result = compute_structural_breaks(df)
        assert "hurst_return" in result
        assert 0.0 <= result["hurst_return"] <= 1.0
        assert "hurst_vol" in result
        assert 0.0 <= result["hurst_vol"] <= 1.0

    def test_interpretation_key_present(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_structural_breaks
        df = _make_stress_df(n=500)
        result = compute_structural_breaks(df)
        assert "hurst_return_interpretation" in result
        assert result["hurst_return_interpretation"] in (
            "mean_reversion", "random_walk", "trending"
        )

    def test_missing_atr_no_vol_keys(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_structural_breaks
        df = pl.DataFrame({"log_return": [0.001] * 100})
        result = compute_structural_breaks(df)
        assert "hurst_vol" not in result
        assert "vol_clustering_lag1" not in result

    def test_all_metrics_finite(self) -> None:
        from tools.parquet_pipeline.market_structure import compute_structural_breaks
        df = _make_stress_df(n=500)
        result = compute_structural_breaks(df)
        for k, v in result.items():
            if isinstance(v, (int, float)):
                assert math.isfinite(v), f"{k}={v} is not finite"

    def test_short_series_hurst_returns_half(self) -> None:
        from tools.parquet_pipeline.market_structure import _hurst_rs
        result = _hurst_rs(np.array([1.0, 2.0, 3.0]))  # n < 20
        assert result == 0.5


# ── Block 5: Stability Grid ───────────────────────────────────────────────────

class TestSimulateStabilityGrid:

    def test_grid_shape(self) -> None:
        from tools.parquet_pipeline.market_structure import simulate_stability_grid
        df = _make_stress_df(n=300)
        thresholds = [0.60, 0.65]
        consecutives = [2, 4]
        min_durations = [3, 5]
        result = simulate_stability_grid(
            df,
            thresholds=thresholds,
            consecutives=consecutives,
            min_durations=min_durations,
            tf_minutes=5,
        )
        expected_rows = len(thresholds) * len(consecutives) * len(min_durations)
        assert len(result) == expected_rows

    def test_sorted_by_switches_per_day(self) -> None:
        from tools.parquet_pipeline.market_structure import simulate_stability_grid
        df = _make_stress_df(n=300)
        result = simulate_stability_grid(
            df,
            thresholds=[0.55, 0.65],
            consecutives=[2, 6],
            min_durations=[3],
            tf_minutes=5,
        )
        spd = result["switches_per_day"].to_list()
        assert spd == sorted(spd), "Result should be sorted by switches_per_day ascending"

    def test_all_numeric_columns_finite(self) -> None:
        from tools.parquet_pipeline.market_structure import simulate_stability_grid
        df = _make_stress_df(n=300)
        result = simulate_stability_grid(
            df,
            thresholds=[0.60],
            consecutives=[3],
            min_durations=[5],
            tf_minutes=5,
        )
        for col in ("switches_per_day", "pct_normal", "pct_stress", "pct_extreme"):
            for val in result[col].to_list():
                assert math.isfinite(val), f"{col}={val} is not finite"

    def test_single_combo_produces_one_row(self) -> None:
        from tools.parquet_pipeline.market_structure import simulate_stability_grid
        df = _make_stress_df(n=300)
        result = simulate_stability_grid(
            df,
            thresholds=[0.60],
            consecutives=[3],
            min_durations=[5],
            tf_minutes=5,
        )
        assert len(result) == 1


# ── _parse_months_range ───────────────────────────────────────────────────────

class TestParseMonthsRange:

    def test_single_month_range(self) -> None:
        from tools.parquet_pipeline.__main__ import _parse_months_range
        months = _parse_months_range("2024-01:2024-01")
        assert months == ["2024-01"]

    def test_multi_month_range(self) -> None:
        from tools.parquet_pipeline.__main__ import _parse_months_range
        months = _parse_months_range("2023-11:2024-02")
        assert months == ["2023-11", "2023-12", "2024-01", "2024-02"]

    def test_year_boundary(self) -> None:
        from tools.parquet_pipeline.__main__ import _parse_months_range
        months = _parse_months_range("2023-12:2024-01")
        assert months == ["2023-12", "2024-01"]

    def test_invalid_format_raises(self) -> None:
        from tools.parquet_pipeline.__main__ import _parse_months_range
        with pytest.raises(ValueError):
            _parse_months_range("2024-01")
