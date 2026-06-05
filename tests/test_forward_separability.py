"""Tests for Phase R3-B: tools/parquet_pipeline/forward_separability.py

All tests use synthetic DataFrames — no parquet I/O.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import polars as pl
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(
    n: int = 600,
    *,
    seed: int = 42,
    close_trend: float = 5.0,
    close_noise: float = 1.0,
    bar_range_base: float = 0.003,
) -> pl.DataFrame:
    """Minimal DataFrame compatible with forward_separability functions."""
    rng = np.random.default_rng(seed)
    close = 10_000.0 + np.cumsum(rng.normal(close_trend, close_noise, n))
    log_return = np.concatenate([[0.0], np.diff(np.log(np.abs(close) + 1))])
    atr = np.abs(rng.normal(50.0, 10.0, n))
    bar_range = np.abs(rng.normal(bar_range_base, bar_range_base * 0.3, n))
    return pl.DataFrame({
        "timestamp": list(range(n)),
        "close": close.tolist(),
        "log_return": log_return.tolist(),
        "atr": atr.tolist(),
        "bar_range": bar_range.tolist(),
    })


def _make_flat_df(n: int = 600) -> pl.DataFrame:
    """Flat close — slope always near zero → mostly FLAT labels."""
    return _make_df(n=n, close_trend=0.0, close_noise=0.001)


def _make_trending_df(n: int = 600) -> pl.DataFrame:
    """Strong uptrend — slope should produce TREND_UP labels."""
    return _make_df(n=n, close_trend=50.0, close_noise=0.1)


# ── compute_forward_returns ───────────────────────────────────────────────────

class TestComputeForwardReturns:

    def test_columns_added(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        df = _make_df(n=200)
        result = compute_forward_returns(df, horizons=[12, 24])
        assert "fwd_ret_12" in result.columns
        assert "fwd_ret_24" in result.columns

    def test_last_n_bars_are_nan(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        df = _make_df(n=100)
        result = compute_forward_returns(df, horizons=[10])
        tail = result["fwd_ret_10"].tail(10).to_list()
        assert all(v is None or (isinstance(v, float) and math.isnan(v)) for v in tail)

    def test_first_bar_valid(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        df = _make_df(n=100)
        result = compute_forward_returns(df, horizons=[5])
        val = result["fwd_ret_5"][0]
        assert val is not None and math.isfinite(float(val))

    def test_output_length_unchanged(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        n = 150
        df = _make_df(n=n)
        result = compute_forward_returns(df, horizons=[12, 24, 48])
        assert len(result) == n

    def test_no_close_column_returns_nulls(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
        result = compute_forward_returns(df, horizons=[2])
        assert "fwd_ret_2" in result.columns
        assert result["fwd_ret_2"].is_null().all()

    def test_default_horizons_applied(self) -> None:
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        df = _make_df(n=100)
        result = compute_forward_returns(df)
        for n in [12, 24, 48]:
            assert f"fwd_ret_{n}" in result.columns

    def test_fwd_ret_is_log_ratio(self) -> None:
        """Verify fwd_ret_N[0] approximates log(close[N]/close[0])."""
        from tools.parquet_pipeline.forward_separability import compute_forward_returns
        close_vals = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        df = pl.DataFrame({"close": close_vals})
        result = compute_forward_returns(df, horizons=[3])
        expected = math.log(103.0 / 100.0)
        actual = float(result["fwd_ret_3"][0])
        assert abs(actual - expected) < 1e-6


# ── _cohens_d ─────────────────────────────────────────────────────────────────

class TestCohensD:

    def test_identical_arrays_zero(self) -> None:
        from tools.parquet_pipeline.forward_separability import _cohens_d
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert _cohens_d(arr, arr) == 0.0

    def test_well_separated_large(self) -> None:
        from tools.parquet_pipeline.forward_separability import _cohens_d
        a = np.ones(100) * 10.0
        b = np.ones(100) * 0.0
        d = _cohens_d(a, b)
        # near-zero std → large pooled std won't apply; but constant arrays have std=0
        # small ddof=1 std: use std ~0 → fallback 0
        # Use slightly noisy arrays to get meaningful result
        rng = np.random.default_rng(0)
        a2 = 10.0 + rng.normal(0, 1, 100)
        b2 = 0.0 + rng.normal(0, 1, 100)
        d2 = _cohens_d(a2, b2)
        assert d2 > 5.0  # ~10 SD apart with std=1

    def test_empty_arrays_returns_zero(self) -> None:
        from tools.parquet_pipeline.forward_separability import _cohens_d
        assert _cohens_d(np.array([]), np.array([])) == 0.0

    def test_sign(self) -> None:
        from tools.parquet_pipeline.forward_separability import _cohens_d
        rng = np.random.default_rng(1)
        a = 5.0 + rng.normal(0, 1, 100)
        b = 0.0 + rng.normal(0, 1, 100)
        assert _cohens_d(a, b) > 0  # a has higher mean → positive d


# ── _sign_accuracy ────────────────────────────────────────────────────────────

class TestSignAccuracy:

    def test_all_positive_is_one(self) -> None:
        from tools.parquet_pipeline.forward_separability import _sign_accuracy
        assert _sign_accuracy(np.array([0.01, 0.02, 0.03])) == 1.0

    def test_all_negative_is_zero(self) -> None:
        from tools.parquet_pipeline.forward_separability import _sign_accuracy
        assert _sign_accuracy(np.array([-0.01, -0.02, -0.03])) == 0.0

    def test_half_and_half(self) -> None:
        from tools.parquet_pipeline.forward_separability import _sign_accuracy
        arr = np.array([1.0, -1.0, 1.0, -1.0])
        assert abs(_sign_accuracy(arr) - 0.5) < 1e-6

    def test_empty_returns_half(self) -> None:
        from tools.parquet_pipeline.forward_separability import _sign_accuracy
        assert _sign_accuracy(np.array([])) == 0.5

    def test_nan_excluded(self) -> None:
        from tools.parquet_pipeline.forward_separability import _sign_accuracy
        arr = np.array([1.0, np.nan, 1.0, np.nan])
        assert _sign_accuracy(arr) == 1.0


# ── _edge_verdict ─────────────────────────────────────────────────────────────

class TestEdgeVerdict:

    def test_strong_verdict(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(0.25, 0.08) == "strong"

    def test_moderate_verdict(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(0.15, 0.03) == "moderate"

    def test_weak_verdict_d_only(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(0.06, 0.005) == "weak"

    def test_weak_verdict_lift_only(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(0.01, 0.02) == "weak"

    def test_none_verdict(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(0.01, 0.005) == "none"

    def test_negative_d_strong(self) -> None:
        from tools.parquet_pipeline.forward_separability import _edge_verdict
        assert _edge_verdict(-0.25, -0.08) == "strong"


# ── run_forward_separability ──────────────────────────────────────────────────

class TestRunForwardSeparability:

    def _run(self, df: pl.DataFrame | None = None, **kw) -> dict:
        from tools.parquet_pipeline.forward_separability import run_forward_separability
        if df is None:
            df = _make_df(n=600)
        defaults = dict(
            sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12, 24], tf_minutes=5,
        )
        defaults.update(kw)
        return run_forward_separability(df, **defaults)

    def test_top_level_keys_present(self) -> None:
        result = self._run()
        for k in ("params", "horizons", "tf_minutes", "label_distribution",
                   "per_horizon", "vol_interaction"):
            assert k in result, f"Missing key: {k}"

    def test_per_horizon_has_all_horizons(self) -> None:
        result = self._run(horizons=[12, 24])
        assert set(result["per_horizon"].keys()) == {12, 24}

    def test_label_distribution_keys(self) -> None:
        result = self._run()
        for lbl in ("TREND_UP", "TREND_DOWN", "FLAT"):
            assert lbl in result["label_distribution"]

    def test_label_distribution_pct_sums_to_100(self) -> None:
        result = self._run()
        total = sum(v["pct"] for v in result["label_distribution"].values())
        assert abs(total - 100.0) < 1.0

    def test_per_horizon_contains_label_stats(self) -> None:
        result = self._run(horizons=[12])
        h_data = result["per_horizon"][12]
        assert "label_stats" in h_data

    def test_sign_accuracy_in_unit_interval(self) -> None:
        result = self._run(horizons=[12])
        for lbl, st in result["per_horizon"][12]["label_stats"].items():
            sa = st.get("sign_accuracy")
            if sa is not None:
                assert 0.0 <= sa <= 1.0, f"{lbl}.sign_accuracy={sa}"

    def test_all_finite_values(self) -> None:
        result = self._run(horizons=[12])
        for n, h_data in result["per_horizon"].items():
            for cmp_key in ("UP_vs_FLAT", "DOWN_vs_FLAT"):
                for k, v in h_data.get(cmp_key, {}).items():
                    if isinstance(v, float):
                        assert math.isfinite(v), f"horizon={n} {cmp_key}.{k}={v}"

    def test_edge_verdict_values_valid(self) -> None:
        from tools.parquet_pipeline.forward_separability import run_forward_separability
        df = _make_trending_df(n=600)
        result = run_forward_separability(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[24], tf_minutes=5,
        )
        valid = {"strong", "moderate", "weak", "none"}
        for h_data in result["per_horizon"].values():
            for cmp_key in ("UP_vs_FLAT", "DOWN_vs_FLAT"):
                ev = h_data.get(cmp_key, {}).get("edge_verdict")
                if ev is not None:
                    assert ev in valid, f"Invalid verdict: {ev}"

    def test_vol_interaction_has_all_combos(self) -> None:
        from tools.parquet_pipeline.forward_separability import (
            TREND_LABELS, VOL_LABELS,
        )
        result = self._run(horizons=[12])
        matrix = result["vol_interaction"][12]
        for tl in TREND_LABELS:
            for vl in VOL_LABELS:
                assert f"{tl}|{vl}" in matrix


# ── flatten_separability_to_df ────────────────────────────────────────────────

class TestFlattenSeparabilityToDf:

    def test_shape_correct(self) -> None:
        from tools.parquet_pipeline.forward_separability import (
            run_forward_separability, flatten_separability_to_df, TREND_LABELS,
        )
        df = _make_df(n=400)
        result = run_forward_separability(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12, 24], tf_minutes=5,
        )
        out = flatten_separability_to_df(result, "BTCUSDT")
        # 3 labels × 2 horizons = 6 rows
        assert len(out) == len(TREND_LABELS) * 2

    def test_symbol_column_correct(self) -> None:
        from tools.parquet_pipeline.forward_separability import (
            run_forward_separability, flatten_separability_to_df,
        )
        df = _make_df(n=400)
        result = run_forward_separability(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12], tf_minutes=5,
        )
        out = flatten_separability_to_df(result, "ETHUSDT")
        assert (out["symbol"] == "ETHUSDT").all()

    def test_no_crash_empty_result(self) -> None:
        from tools.parquet_pipeline.forward_separability import flatten_separability_to_df
        out = flatten_separability_to_df({"per_horizon": {}, "tf_minutes": 5}, "X")
        assert len(out) == 0
