"""Tests for Phase R2: tools/parquet_pipeline/regime_grid.py

All tests use synthetic DataFrames — no parquet I/O.
Numeric assertions are on bounds, shapes, and monotone comparisons.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import polars as pl
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_grid_df(
    n: int = 500,
    *,
    seed: int = 42,
    close_trend: float = 5.0,
    close_noise: float = 1.0,
    atr_base: float = 50.0,
    bar_range_base: float = 0.003,
) -> pl.DataFrame:
    """Minimal stress-df compatible DataFrame for regime_grid tests.

    Contains: timestamp, close, log_return, atr, bar_range.
    """
    rng = np.random.default_rng(seed)
    close = 10_000.0 + np.cumsum(rng.normal(close_trend, close_noise, n))
    log_return = np.concatenate([[0.0], np.diff(np.log(np.abs(close) + 1))])
    atr = np.abs(rng.normal(atr_base, atr_base * 0.2, n))
    bar_range = np.abs(rng.normal(bar_range_base, bar_range_base * 0.3, n))
    return pl.DataFrame({
        "timestamp": list(range(n)),
        "close": close.tolist(),
        "log_return": log_return.tolist(),
        "atr": atr.tolist(),
        "bar_range": bar_range.tolist(),
    })


def _make_distinct_vol_df(n: int = 600) -> pl.DataFrame:
    """DataFrame with three clearly distinct vol regimes in bar_range."""
    rng = np.random.default_rng(7)
    close = 10_000.0 + np.cumsum(rng.normal(0, 1, n))
    log_return = np.concatenate([[0.0], np.diff(np.log(np.abs(close) + 1))])
    atr = np.abs(rng.normal(50, 5, n))
    bar_range = np.concatenate([
        np.ones(n // 3) * 0.001,       # LOW_VOL band
        np.ones(n // 3) * 0.005,       # MID_VOL band
        np.ones(n - 2 * (n // 3)) * 0.015,  # HIGH_VOL band
    ])
    return pl.DataFrame({
        "timestamp": list(range(n)),
        "close": close.tolist(),
        "log_return": log_return.tolist(),
        "atr": atr.tolist(),
        "bar_range": bar_range.tolist(),
    })


# ── Block 1: _apply_hysteresis / _trend_labels ───────────────────────────────

class TestApplyHysteresis:

    def test_n1_is_identity(self) -> None:
        from tools.parquet_pipeline.regime_grid import _apply_hysteresis
        labels = pl.Series("x", ["A", "B", "A", "B", "A"], dtype=pl.Utf8)
        result = _apply_hysteresis(labels, n=1)
        assert result.to_list() == labels.to_list()

    def test_isolated_flip_filtered(self) -> None:
        from tools.parquet_pipeline.regime_grid import _apply_hysteresis
        # One-bar flip in the middle should be suppressed with n=2
        labels = pl.Series("x", ["A", "A", "B", "A", "A", "A"], dtype=pl.Utf8)
        result = _apply_hysteresis(labels, n=2)
        # "B" appears only once — doesn't commit, stays as "A" at that bar
        assert result[2] == "A"

    def test_two_consecutive_commits(self) -> None:
        from tools.parquet_pipeline.regime_grid import _apply_hysteresis
        labels = pl.Series("x", ["A", "A", "B", "B", "B"], dtype=pl.Utf8)
        result = _apply_hysteresis(labels, n=2)
        # B appears at bars 2,3,4 — commits at bar 3 (2 consecutive)
        assert result[3] == "B"
        assert result[4] == "B"

    def test_empty_series(self) -> None:
        from tools.parquet_pipeline.regime_grid import _apply_hysteresis
        labels = pl.Series("x", [], dtype=pl.Utf8)
        result = _apply_hysteresis(labels, n=2)
        assert len(result) == 0


class TestTrendLabels:

    def test_strong_uptrend_labels_trend_up(self) -> None:
        from tools.parquet_pipeline.regime_grid import _trend_labels
        # Strongly rising close: SMA_short >> SMA_long
        n = 300
        close = np.cumsum(np.ones(n) * 10.0) + 1000.0
        df = pl.DataFrame({"close": close.tolist()})
        labels = _trend_labels(df, sma_short=10, sma_long=50, slope_threshold=0.001)
        valid = labels.drop_nulls()
        # Most labels after warmup should be TREND_UP
        majority = valid.mode()[0]
        assert majority == "TREND_UP"

    def test_strong_downtrend_labels_trend_down(self) -> None:
        from tools.parquet_pipeline.regime_grid import _trend_labels
        n = 300
        close = 5000.0 - np.cumsum(np.ones(n) * 5.0)
        close = np.maximum(close, 1.0)  # avoid negative prices
        df = pl.DataFrame({"close": close.tolist()})
        labels = _trend_labels(df, sma_short=10, sma_long=50, slope_threshold=0.001)
        counts = labels.value_counts()
        td_count = (
            counts.filter(pl.col("trend_state") == "TREND_DOWN")["count"].to_list()
        )
        assert td_count and td_count[0] > 0

    def test_flat_constant_close_labels_flat(self) -> None:
        from tools.parquet_pipeline.regime_grid import _trend_labels
        n = 200
        df = pl.DataFrame({"close": [1000.0] * n})
        labels = _trend_labels(df, sma_short=10, sma_long=50, slope_threshold=0.001)
        # All valid bars must be FLAT (slope == 0)
        valid = [lbl for lbl in labels.to_list() if lbl is not None]
        assert all(lbl == "FLAT" for lbl in valid)

    def test_hysteresis_reduces_switches(self) -> None:
        from tools.parquet_pipeline.regime_grid import _trend_labels, _count_switches
        df = _make_grid_df(n=400, close_trend=0.1, close_noise=5.0, seed=99)
        raw_labels = _trend_labels(df, 24, 96, 0.001, hysteresis_bars=1)
        hyst_labels = _trend_labels(df, 24, 96, 0.001, hysteresis_bars=3)
        assert _count_switches(hyst_labels) <= _count_switches(raw_labels)

    def test_output_length_matches_input(self) -> None:
        from tools.parquet_pipeline.regime_grid import _trend_labels
        df = _make_grid_df(n=300)
        labels = _trend_labels(df, 24, 96, 0.001)
        assert len(labels) == 300


# ── Block 2: _vol_labels ──────────────────────────────────────────────────────

class TestVolLabels:

    def test_three_distinct_groups_all_present(self) -> None:
        from tools.parquet_pipeline.regime_grid import _vol_labels
        df = _make_distinct_vol_df(n=600)
        labels = _vol_labels(df, atr_window=5)
        unique = set(labels.to_list())
        assert "LOW_VOL" in unique
        assert "MID_VOL" in unique
        assert "HIGH_VOL" in unique

    def test_constant_bar_range_all_mid(self) -> None:
        from tools.parquet_pipeline.regime_grid import _vol_labels
        n = 100
        df = pl.DataFrame({
            "bar_range": [0.005] * n,
            "close": [1000.0] * n,
        })
        labels = _vol_labels(df, atr_window=5)
        # All same → p33 == p66 → everything is MID_VOL
        valid = [lbl for lbl in labels.to_list() if lbl is not None]
        assert all(lbl == "MID_VOL" for lbl in valid)

    def test_atr_window_14_vs_28_may_differ(self) -> None:
        from tools.parquet_pipeline.regime_grid import _vol_labels
        rng = np.random.default_rng(30)
        n = 400
        br = np.abs(rng.normal(0.003, 0.002, n))
        df = pl.DataFrame({"bar_range": br.tolist()})
        l14 = _vol_labels(df, atr_window=14)
        l28 = _vol_labels(df, atr_window=28)
        # They are the same type but can differ — just check no crash and same length
        assert len(l14) == len(l28) == n

    def test_short_df_no_crash(self) -> None:
        from tools.parquet_pipeline.regime_grid import _vol_labels
        df = pl.DataFrame({"bar_range": [0.001, 0.002, 0.003, 0.010, 0.020]})
        labels = _vol_labels(df, atr_window=3)
        assert len(labels) == 5


# ── Block 3: compute_grid_row ─────────────────────────────────────────────────

_EXPECTED_KEYS = {
    "sma_short", "sma_long", "slope_threshold", "atr_window", "hysteresis_bars",
    "pct_trend_up", "pct_trend_down", "pct_flat",
    "pct_low_vol", "pct_mid_vol", "pct_high_vol",
    "min_state_pct", "coverage_ok",
    "trend_switches_per_day", "vol_switches_per_day",
    "median_trend_run_bars", "median_vol_run_bars",
    "trend_return_overlap", "vol_atr_overlap",
    "trend_bhatt", "vol_bhatt",
    "score",
}


class TestComputeGridRow:

    def _row(self, **kw):
        from tools.parquet_pipeline.regime_grid import compute_grid_row
        df = _make_grid_df(n=500)
        defaults = dict(
            sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, tf_minutes=5,
        )
        defaults.update(kw)
        return compute_grid_row(df, **defaults)

    def test_all_expected_keys_present(self) -> None:
        row = self._row()
        assert set(row.keys()) == _EXPECTED_KEYS

    def test_switches_per_day_nonnegative(self) -> None:
        row = self._row()
        assert row["trend_switches_per_day"] >= 0.0
        assert row["vol_switches_per_day"] >= 0.0

    def test_trend_coverage_sums_to_one(self) -> None:
        row = self._row()
        total = row["pct_trend_up"] + row["pct_trend_down"] + row["pct_flat"]
        assert abs(total - 1.0) < 0.001

    def test_vol_coverage_sums_to_one(self) -> None:
        row = self._row()
        total = row["pct_low_vol"] + row["pct_mid_vol"] + row["pct_high_vol"]
        assert abs(total - 1.0) < 0.001

    def test_overlap_in_unit_interval(self) -> None:
        row = self._row()
        for k in ("trend_return_overlap", "vol_atr_overlap"):
            assert 0.0 <= row[k] <= 1.0, f"{k}={row[k]} out of [0,1]"

    def test_all_numeric_values_finite(self) -> None:
        row = self._row()
        for k, v in row.items():
            if isinstance(v, (int, float)):
                assert math.isfinite(float(v)), f"{k}={v} not finite"

    def test_score_in_valid_range(self) -> None:
        row = self._row()
        assert -0.15 <= row["score"] <= 1.0


# ── Block 4: _score_grid_row ──────────────────────────────────────────────────

class TestScoreGridRow:

    def _perfect_row(self) -> dict:
        """Row with ideal properties: low churn, high sep, coverage ok."""
        return {
            "trend_switches_per_day": 0.5,
            "trend_return_overlap": 0.1,
            "vol_atr_overlap": 0.1,
            "coverage_ok": True,
        }

    def test_near_max_for_perfect_row(self) -> None:
        from tools.parquet_pipeline.regime_grid import _score_grid_row
        row = self._perfect_row()
        score = _score_grid_row(row)
        # churn_score ≈ 0.9, sep_score ≈ 0.9 → score ≈ 0.5*0.9 + 0.4*0.9 = 0.81
        assert score > 0.70

    def test_high_churn_reduces_stability(self) -> None:
        from tools.parquet_pipeline.regime_grid import _score_grid_row
        good = self._perfect_row()
        bad = dict(good, trend_switches_per_day=20.0)
        assert _score_grid_row(bad) < _score_grid_row(good)

    def test_high_overlap_reduces_separability(self) -> None:
        from tools.parquet_pipeline.regime_grid import _score_grid_row
        good = self._perfect_row()
        bad = dict(good, trend_return_overlap=0.95, vol_atr_overlap=0.95)
        assert _score_grid_row(bad) < _score_grid_row(good)

    def test_coverage_violation_penalizes(self) -> None:
        from tools.parquet_pipeline.regime_grid import _score_grid_row
        ok_row = self._perfect_row()
        vio_row = dict(ok_row, coverage_ok=False)
        assert _score_grid_row(vio_row) < _score_grid_row(ok_row)


# ── Block 5: run_regime_grid ──────────────────────────────────────────────────

class TestRunRegimeGrid:

    def test_sorted_by_score_desc(self) -> None:
        from tools.parquet_pipeline.regime_grid import run_regime_grid
        df = _make_grid_df(n=400)
        result = run_regime_grid(
            df,
            sma_shorts=[24], sma_longs=[96], slope_thresholds=[0.001, 0.002],
            atr_windows=[14], hysteresis_bars=[1],
        )
        scores = result["score"].to_list()
        assert scores == sorted(scores, reverse=True)

    def test_grid_shape_correct(self) -> None:
        from tools.parquet_pipeline.regime_grid import run_regime_grid
        df = _make_grid_df(n=400)
        result = run_regime_grid(
            df,
            sma_shorts=[24, 36], sma_longs=[96, 144],
            slope_thresholds=[0.001],
            atr_windows=[14],
            hysteresis_bars=[1],
        )
        # 2×2=4 sma combos, all valid (24<96, 24<144, 36<96, 36<144)
        # × 1 threshold × 1 atr_win × 1 hyst = 4 rows
        assert len(result) == 4

    def test_invalid_sma_combos_skipped(self) -> None:
        from tools.parquet_pipeline.regime_grid import run_regime_grid
        df = _make_grid_df(n=400)
        # sma_short=96 >= sma_long=96 → invalid; sma_short=24 < sma_long=96 → valid
        result = run_regime_grid(
            df,
            sma_shorts=[96, 24], sma_longs=[96],
            slope_thresholds=[0.001],
            atr_windows=[14],
            hysteresis_bars=[1],
        )
        assert len(result) == 1  # only (24, 96) is valid

    def test_single_combo_one_row(self) -> None:
        from tools.parquet_pipeline.regime_grid import run_regime_grid
        df = _make_grid_df(n=400)
        result = run_regime_grid(
            df,
            sma_shorts=[24], sma_longs=[96],
            slope_thresholds=[0.001],
            atr_windows=[14],
            hysteresis_bars=[1],
        )
        assert len(result) == 1

    def test_all_numeric_columns_finite(self) -> None:
        from tools.parquet_pipeline.regime_grid import run_regime_grid
        df = _make_grid_df(n=400)
        result = run_regime_grid(
            df,
            sma_shorts=[24], sma_longs=[96, 144],
            slope_thresholds=[0.001],
            atr_windows=[14],
            hysteresis_bars=[1],
        )
        float_cols = [c for c in result.columns if result[c].dtype in (pl.Float64, pl.Float32)]
        for col in float_cols:
            for val in result[col].to_list():
                if val is not None:
                    assert math.isfinite(float(val)), f"{col}={val} not finite"
