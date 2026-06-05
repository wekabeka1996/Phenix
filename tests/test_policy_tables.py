"""Tests for R3-A-lite: tools/parquet_pipeline/policy_tables.py"""

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


def _make_df_with_stress(n: int = 600) -> pl.DataFrame:
    """Adds state column cycling through NORMAL/STRESS."""
    df = _make_df(n=n)
    states = (["NORMAL"] * 20 + ["STRESS"] * 5) * (n // 25 + 1)
    return df.with_columns(pl.Series("state", states[:n]))


# ── _cvar5 ────────────────────────────────────────────────────────────────────

class TestCvar5:

    def test_all_negative_returns_bottom(self) -> None:
        from tools.parquet_pipeline.policy_tables import _cvar5
        arr = np.array([-0.10, -0.05, -0.01, 0.01, 0.05])
        val = _cvar5(arr)
        # bottom 5% (1 element = -0.10)
        assert val <= -0.09

    def test_empty_returns_zero(self) -> None:
        from tools.parquet_pipeline.policy_tables import _cvar5
        assert _cvar5(np.array([])) == 0.0

    def test_all_positive_cvar_nonnegative_or_small(self) -> None:
        from tools.parquet_pipeline.policy_tables import _cvar5
        arr = np.array([0.01, 0.02, 0.03, 0.04, 0.05] * 20)
        val = _cvar5(arr)
        # all positive → bottom 5% still positive (or near-zero)
        assert val < 0.05


class TestTailUplift:

    def test_wide_distribution_has_large_uplift(self) -> None:
        from tools.parquet_pipeline.policy_tables import _tail_uplift
        arr = np.array([-5.0, 0.0, 1.0, 2.0, 3.0, 10.0, 20.0])
        uplift = _tail_uplift(arr)
        assert uplift > 5.0

    def test_constant_array_zero(self) -> None:
        from tools.parquet_pipeline.policy_tables import _tail_uplift
        arr = np.ones(100) * 5.0
        assert _tail_uplift(arr) == 0.0

    def test_empty_returns_zero(self) -> None:
        from tools.parquet_pipeline.policy_tables import _tail_uplift
        assert _tail_uplift(np.array([])) == 0.0


# ── compute_edge_table ────────────────────────────────────────────────────────

class TestComputeEdgeTable:

    def _run(self, df: pl.DataFrame | None = None, **kw):
        from tools.parquet_pipeline.policy_tables import compute_edge_table
        if df is None:
            df = _make_df(n=600)
        defaults = dict(
            sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12, 24], tf_minutes=5,
        )
        defaults.update(kw)
        return compute_edge_table(df, **defaults)

    def test_returns_dataframe(self) -> None:
        result = self._run()
        assert isinstance(result, pl.DataFrame)
        assert len(result) > 0

    def test_expected_columns_present(self) -> None:
        result = self._run()
        for col in ("horizon_bars", "trend_label", "vol_label", "stress_state",
                    "n", "mean_fwd_ret", "sign_acc", "cvar5", "tail_uplift"):
            assert col in result.columns, f"Missing column: {col}"

    def test_both_horizons_present(self) -> None:
        result = self._run(horizons=[12, 24])
        assert set(result["horizon_bars"].unique().to_list()) == {12, 24}

    def test_sign_acc_in_unit_interval(self) -> None:
        result = self._run()
        for val in result["sign_acc"].drop_nulls().to_list():
            assert 0.0 <= val <= 1.0, f"sign_acc={val} out of [0,1]"

    def test_all_numeric_values_finite(self) -> None:
        result = self._run()
        float_cols = [c for c in result.columns
                      if result[c].dtype in (pl.Float64, pl.Float32)]
        for col in float_cols:
            for val in result[col].drop_nulls().to_list():
                assert math.isfinite(float(val)), f"{col}={val} not finite"

    def test_stress_col_used_when_present(self) -> None:
        df = _make_df_with_stress(n=600)
        from tools.parquet_pipeline.policy_tables import compute_edge_table
        result = compute_edge_table(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12], tf_minutes=5,
            stress_col="state",
        )
        stress_states = set(result["stress_state"].unique().to_list())
        assert "STRESS" in stress_states or "NORMAL" in stress_states

    def test_no_stress_col_defaults_to_normal(self) -> None:
        df = _make_df(n=400)
        from tools.parquet_pipeline.policy_tables import compute_edge_table
        result = compute_edge_table(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12], tf_minutes=5,
            stress_col=None,
        )
        assert (result["stress_state"] == "NORMAL").all()

    def test_p05_le_p50_le_p95(self) -> None:
        result = self._run()
        for row in result.filter(pl.col("n") > 5).iter_rows(named=True):
            p05 = row["p05"]
            p50 = row["p50"]
            p95 = row["p95"]
            if p05 is not None and p50 is not None and p95 is not None:
                assert p05 <= p50 <= p95, f"p05={p05} p50={p50} p95={p95}"

    def test_horizon_hours_correct(self) -> None:
        result = self._run(horizons=[12], tf_minutes=5)
        # 12 bars * 5 min / 60 = 1.0h
        for val in result["horizon_hours"].to_list():
            assert abs(val - 1.0) < 0.01


# ── derive_trend_policy ───────────────────────────────────────────────────────

class TestDeriveTrendPolicy:

    def _edge(self, **kw):
        from tools.parquet_pipeline.policy_tables import compute_edge_table
        df = _make_df(n=600, close_trend=10.0)
        defaults = dict(
            sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[24], tf_minutes=5,
        )
        defaults.update(kw)
        return compute_edge_table(df, **defaults)

    def test_returns_dataframe(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_trend_policy
        edge = self._edge()
        result = derive_trend_policy(edge, primary_horizon=24)
        assert isinstance(result, pl.DataFrame)

    def test_sizing_mult_in_bounds(self) -> None:
        from tools.parquet_pipeline.policy_tables import (
            derive_trend_policy, _SIZE_MULT_MIN, _SIZE_MULT_MAX,
        )
        edge = self._edge()
        result = derive_trend_policy(edge, primary_horizon=24)
        if len(result) == 0:
            pytest.skip("No rows in trend policy (baseline not found)")
        for val in result["sizing_mult"].to_list():
            assert _SIZE_MULT_MIN <= val <= _SIZE_MULT_MAX, f"sizing_mult={val} out of bounds"

    def test_signal_values_valid(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_trend_policy
        edge = self._edge()
        result = derive_trend_policy(edge, primary_horizon=24)
        valid = {"increase", "neutral", "reduce"}
        for val in result["signal"].to_list():
            assert val in valid, f"Invalid signal: {val}"

    def test_baseline_cell_is_neutral(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_trend_policy
        edge = self._edge()
        result = derive_trend_policy(edge, primary_horizon=24)
        if len(result) == 0:
            pytest.skip("No rows")
        bl = result.filter(
            (pl.col("trend_label") == "FLAT")
            & (pl.col("vol_label") == "MID_VOL")
            & (pl.col("stress_state") == "NORMAL")
        )
        if len(bl) > 0:
            assert bl["mean_uplift"][0] == 0.0 or abs(bl["mean_uplift"][0]) < 1e-9


# ── derive_mr_policy ─────────────────────────────────────────────────────────

class TestDeriveMrPolicy:

    def _edge(self):
        from tools.parquet_pipeline.policy_tables import compute_edge_table
        df = _make_df(n=600)
        return compute_edge_table(
            df, sma_short=24, sma_long=96, slope_threshold=0.001,
            atr_window=14, hysteresis_bars=1, horizons=[12], tf_minutes=5,
        )

    def test_returns_dataframe(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_mr_policy
        edge = self._edge()
        result = derive_mr_policy(edge, primary_horizon=12)
        assert isinstance(result, pl.DataFrame)

    def test_entry_policy_values_valid(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_mr_policy
        edge = self._edge()
        result = derive_mr_policy(edge, primary_horizon=12)
        if len(result) == 0:
            pytest.skip("No rows")
        valid = {"boost", "allow", "reduce", "block"}
        for val in result["entry_policy"].to_list():
            assert val in valid, f"Invalid entry_policy: {val}"

    def test_sorted_by_sign_acc_delta_desc(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_mr_policy
        edge = self._edge()
        result = derive_mr_policy(edge, primary_horizon=12)
        if len(result) < 2:
            pytest.skip("Not enough rows")
        deltas = result["sign_acc_delta"].to_list()
        assert deltas == sorted(deltas, reverse=True)

    def test_sign_acc_in_unit_interval(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_mr_policy
        edge = self._edge()
        result = derive_mr_policy(edge, primary_horizon=12)
        for val in result["sign_acc"].drop_nulls().to_list():
            assert 0.0 <= val <= 1.0

    def test_all_expected_columns(self) -> None:
        from tools.parquet_pipeline.policy_tables import derive_mr_policy
        edge = self._edge()
        result = derive_mr_policy(edge, primary_horizon=12)
        for col in ("trend_label", "vol_label", "stress_state",
                    "n", "sign_acc", "sign_acc_delta", "cvar5", "entry_policy"):
            assert col in result.columns
