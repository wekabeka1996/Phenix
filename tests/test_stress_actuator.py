"""Tests for Phase 0.2: aggregation + actuator (stress state machine).

Coverage:
  - aggregation: weighted_vote, k_of_n, max, no-active-triggers
  - actuator: pure NORMAL, NORMAL->STRESS, hysteresis holds, consecutive bars,
              min_duration, STRESS->EXTREME->STRESS->NORMAL, circuit breaker
  - CLI: --emit-state end-to-end
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import numpy as np
import polars as pl
import pytest

from tools.parquet_pipeline.actuator_rules import (
    ActuatorConfig,
    ActuatorResult,
    StressState,
    run_actuator,
)
from tools.parquet_pipeline.aggregation import compute_stress_level


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _default_actuator_config(**overrides) -> ActuatorConfig:
    defaults = dict(
        enter_stress=0.60,
        exit_stress=0.40,
        enter_extreme=0.85,
        exit_extreme=0.70,
        consecutive_bars_enter=3,
        consecutive_bars_exit=2,
        min_duration_bars=5,
        switch_window_bars=50,
        max_switches_per_window=3,
    )
    defaults.update(overrides)
    return ActuatorConfig(**defaults)


def _make_z_df(
    z_atr: list[float],
    z_vol: list[float] | None = None,
    z_gap: list[float] | None = None,
    z_range: list[float] | None = None,
) -> pl.DataFrame:
    """Build a DataFrame with z-score columns for aggregation tests."""
    n = len(z_atr)
    if z_vol is None:
        z_vol = [0.0] * n
    if z_gap is None:
        z_gap = [0.0] * n
    if z_range is None:
        z_range = [0.0] * n
    return pl.DataFrame({
        "z_atr": z_atr,
        "z_realized_vol": z_vol,
        "z_gap": z_gap,
        "z_bar_range": z_range,
    })


_DEFAULT_THRESHOLDS = {
    "atr_sigma": 2.0,
    "vol_sigma": 2.0,
    "gap_sigma": 3.0,
    "range_sigma": 2.5,
    "volume_sigma": 0.0,
    "spread_sigma": 0.0,
    "depth_drop_pct": 0.0,
}

_DEFAULT_WEIGHTS = {"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20}


# ═══════════════════════════════════════════════════════════════
# Aggregation tests
# ═══════════════════════════════════════════════════════════════

class TestAggregation:
    def test_weighted_vote_all_fire(self) -> None:
        """All z-scores above sigma -> stress_level = 1.0."""
        df = _make_z_df(
            z_atr=[5.0], z_vol=[5.0], z_gap=[5.0], z_range=[5.0],
        )
        result = compute_stress_level(
            df.lazy(),
            method="weighted_vote",
            weights=_DEFAULT_WEIGHTS,
            thresholds=_DEFAULT_THRESHOLDS,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(1.0)

    def test_weighted_vote_none_fire(self) -> None:
        """All z-scores below sigma -> stress_level = 0.0."""
        df = _make_z_df(
            z_atr=[0.5], z_vol=[0.5], z_gap=[0.5], z_range=[0.5],
        )
        result = compute_stress_level(
            df.lazy(),
            method="weighted_vote",
            weights=_DEFAULT_WEIGHTS,
            thresholds=_DEFAULT_THRESHOLDS,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(0.0)

    def test_weighted_vote_partial_fire(self) -> None:
        """Only ATR fires (weight=0.30) -> stress_level = 0.30."""
        df = _make_z_df(
            z_atr=[5.0], z_vol=[0.5], z_gap=[0.5], z_range=[0.5],
        )
        result = compute_stress_level(
            df.lazy(),
            method="weighted_vote",
            weights=_DEFAULT_WEIGHTS,
            thresholds=_DEFAULT_THRESHOLDS,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(0.30)

    def test_k_of_n_fires_exceed_k(self) -> None:
        """3 of 4 triggers fire, k=2 -> stress_level = min(3/2, 1.0) = 1.0."""
        df = _make_z_df(
            z_atr=[5.0], z_vol=[5.0], z_gap=[5.0], z_range=[0.5],
        )
        result = compute_stress_level(
            df.lazy(),
            method="k_of_n",
            weights=None,
            thresholds=_DEFAULT_THRESHOLDS,
            k=2,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(1.0)

    def test_k_of_n_fires_below_k(self) -> None:
        """1 of 4 triggers fire, k=3 -> stress_level = 1/3 ~ 0.333."""
        df = _make_z_df(
            z_atr=[5.0], z_vol=[0.5], z_gap=[0.5], z_range=[0.5],
        )
        result = compute_stress_level(
            df.lazy(),
            method="k_of_n",
            weights=None,
            thresholds=_DEFAULT_THRESHOLDS,
            k=3,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(1.0 / 3.0, abs=0.01)

    def test_max_ratio(self) -> None:
        """Max z/sigma across active triggers, clamped to [0, 1]."""
        # z_atr=4.0, sigma=2.0 -> ratio=2.0, clamped to 1.0
        df = _make_z_df(z_atr=[4.0], z_vol=[0.5])
        result = compute_stress_level(
            df.lazy(),
            method="max",
            weights=None,
            thresholds=_DEFAULT_THRESHOLDS,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(1.0)

    def test_max_ratio_below_one(self) -> None:
        """Max ratio < 1 when all z-scores are below sigma."""
        # z_atr=1.0, sigma=2.0 -> ratio=0.5
        df = _make_z_df(z_atr=[1.0], z_vol=[0.5], z_gap=[0.5], z_range=[0.5])
        result = compute_stress_level(
            df.lazy(),
            method="max",
            weights=None,
            thresholds=_DEFAULT_THRESHOLDS,
        ).collect()
        assert 0.0 <= result["stress_level"][0] <= 1.0

    def test_no_active_triggers(self) -> None:
        """All sigmas = 0 -> stress_level = 0."""
        df = _make_z_df(z_atr=[5.0])
        zero_thresholds = {k: 0.0 for k in _DEFAULT_THRESHOLDS}
        result = compute_stress_level(
            df.lazy(),
            method="weighted_vote",
            weights=_DEFAULT_WEIGHTS,
            thresholds=zero_thresholds,
        ).collect()
        assert result["stress_level"][0] == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════
# Actuator tests
# ═══════════════════════════════════════════════════════════════

class TestActuator:
    def test_pure_normal(self) -> None:
        """All stress_levels below enter_stress -> stays NORMAL."""
        cfg = _default_actuator_config()
        levels = [0.1] * 20
        result = run_actuator(levels, cfg)
        assert all(s == "NORMAL" for s in result.states)
        assert result.total_switches == 0

    def test_normal_to_stress(self) -> None:
        """Stress_level >= enter_stress for consecutive_bars_enter -> STRESS."""
        cfg = _default_actuator_config(consecutive_bars_enter=3)
        # 3 bars below, then 3 bars at 0.7 (>= 0.60)
        levels = [0.1, 0.1, 0.1, 0.7, 0.7, 0.7, 0.7, 0.7]
        result = run_actuator(levels, cfg)
        # First 3 NORMAL, bar 5 (index 5) should be STRESS (3 consecutive at 0.7)
        assert result.states[0:3] == ["NORMAL"] * 3
        assert result.states[5] == "STRESS"
        assert result.total_switches == 1

    def test_hysteresis_prevents_premature_switch(self) -> None:
        """2 bars above enter_stress but consec=3: no switch."""
        cfg = _default_actuator_config(consecutive_bars_enter=3)
        # Only 2 consecutive bars above 0.60
        levels = [0.7, 0.7, 0.1, 0.1, 0.1]
        result = run_actuator(levels, cfg)
        assert all(s == "NORMAL" for s in result.states)
        assert result.total_switches == 0

    def test_consecutive_counter_resets(self) -> None:
        """Counter resets when stress_level drops below threshold."""
        cfg = _default_actuator_config(consecutive_bars_enter=3)
        # 2 above, 1 below, 2 above -> no switch (counter resets)
        levels = [0.7, 0.7, 0.1, 0.7, 0.7, 0.1]
        result = run_actuator(levels, cfg)
        assert all(s == "NORMAL" for s in result.states)
        assert result.total_switches == 0

    def test_min_duration_blocks_early_exit(self) -> None:
        """Cannot exit STRESS before min_duration_bars."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            consecutive_bars_exit=1,
            min_duration_bars=5,
        )
        # Immediately enter STRESS, then try to exit right away
        levels = [0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        result = run_actuator(levels, cfg)
        # Enter STRESS at bar 0
        assert result.states[0] == "STRESS"
        # Bar 1-4: still STRESS due to min_duration=5
        assert result.states[1] == "STRESS"
        assert result.states[4] == "STRESS"
        # Bar 5+: can exit (min_duration met + 1 consecutive below)
        assert result.states[5] == "NORMAL"

    def test_stress_to_extreme(self) -> None:
        """STRESS -> EXTREME when stress_level >= enter_extreme."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            min_duration_bars=0,
        )
        # Enter STRESS, then push to EXTREME
        levels = [0.7, 0.9, 0.9, 0.9]
        result = run_actuator(levels, cfg)
        assert result.states[0] == "STRESS"
        assert result.states[1] == "EXTREME"

    def test_extreme_to_stress(self) -> None:
        """EXTREME -> STRESS when stress_level drops below exit_extreme."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            consecutive_bars_exit=1,
            min_duration_bars=2,
        )
        # Enter STRESS, then EXTREME, then drop
        levels = [0.7, 0.9, 0.5, 0.5, 0.5]
        result = run_actuator(levels, cfg)
        assert result.states[0] == "STRESS"
        assert result.states[1] == "EXTREME"
        # Bar 2: still EXTREME (min_duration=2, bars_in_state=1)
        assert result.states[2] == "EXTREME"
        # Bar 3: can exit (min_duration met)
        assert result.states[3] == "STRESS"

    def test_full_cycle(self) -> None:
        """NORMAL -> STRESS -> EXTREME -> STRESS -> NORMAL."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            consecutive_bars_exit=1,
            min_duration_bars=1,
            max_switches_per_window=10,  # allow enough for full cycle
        )
        levels = [
            0.7,  # -> STRESS
            0.9,  # -> EXTREME
            0.5,  # -> STRESS (below exit_extreme=0.70)
            0.1,  # -> NORMAL (below exit_stress=0.40)
        ]
        result = run_actuator(levels, cfg)
        assert result.states == ["STRESS", "EXTREME", "STRESS", "NORMAL"]
        assert result.total_switches == 4

    def test_circuit_breaker(self) -> None:
        """Excessive switching triggers circuit breaker (halt)."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            consecutive_bars_exit=1,
            min_duration_bars=1,
            switch_window_bars=20,
            max_switches_per_window=2,
        )
        # Force 2 switches quickly, then try a 3rd
        levels = [
            0.7,  # -> STRESS (switch 1)
            0.1,  # -> NORMAL (switch 2)
            0.7,  # CB: halt (switch 3 blocked)
            0.7,
            0.7,
        ]
        result = run_actuator(levels, cfg)
        assert result.states[0] == "STRESS"
        assert result.states[1] == "NORMAL"
        # Bar 2+: circuit breaker blocks transition
        assert result.states[2] == "NORMAL"
        assert "CB:halt" in result.whys[2]

    def test_empty_input(self) -> None:
        cfg = _default_actuator_config()
        result = run_actuator([], cfg)
        assert result.states == []
        assert result.total_switches == 0

    def test_switches_cumulative(self) -> None:
        """Cumulative switch count increments correctly."""
        cfg = _default_actuator_config(
            consecutive_bars_enter=1,
            consecutive_bars_exit=1,
            min_duration_bars=1,
        )
        levels = [0.7, 0.9, 0.5, 0.1, 0.1]
        result = run_actuator(levels, cfg)
        # Monotonically increasing
        for i in range(1, len(result.switches_cumulative)):
            assert result.switches_cumulative[i] >= result.switches_cumulative[i - 1]
        assert result.switches_cumulative[-1] == result.total_switches

    def test_why_max_80_chars(self) -> None:
        """All why strings are <= 80 characters."""
        cfg = _default_actuator_config(consecutive_bars_enter=1)
        levels = [0.7, 0.9, 0.5, 0.1] * 5
        result = run_actuator(levels, cfg)
        for w in result.whys:
            assert len(w) <= 80, f"why too long ({len(w)}): {w}"


# ═══════════════════════════════════════════════════════════════
# CLI --emit-state integration test
# ═══════════════════════════════════════════════════════════════

class TestCLIEmitState:
    def test_emit_state_produces_state_parquet(self, tmp_path: Path) -> None:
        from tests.test_parquet_pipeline import _write_parquet_pair
        from tools.parquet_pipeline.__main__ import main

        data_dir = tmp_path / "data"
        _write_parquet_pair(data_dir, n=300)
        out = tmp_path / "out"

        rc = main([
            "--symbol", "BTCUSDT",
            "--tf", "5m",
            "--data-dir", str(data_dir),
            "--output-dir", str(out),
            "--window", "20",
            "--burn-in", "30",
            "--emit-state",
        ])
        assert rc == 0
        assert (out / "stress_state_timeseries.parquet").exists()
        assert (out / "stress_summary.md").exists()

        # Verify state parquet content
        state_df = pl.read_parquet(str(out / "stress_state_timeseries.parquet"))
        assert "timestamp" in state_df.columns
        assert "stress_level" in state_df.columns
        assert "state" in state_df.columns
        assert "why" in state_df.columns
        assert "switches_total" in state_df.columns

        # All states must be valid
        valid_states = {"NORMAL", "STRESS", "EXTREME"}
        actual_states = set(state_df["state"].unique().to_list())
        assert actual_states.issubset(valid_states)

        # Provenance should show state_computed=True
        prov = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
        assert prov["state_computed"] is True

    def test_emit_state_summary_has_state_section(self, tmp_path: Path) -> None:
        from tests.test_parquet_pipeline import _write_parquet_pair
        from tools.parquet_pipeline.__main__ import main

        data_dir = tmp_path / "data"
        _write_parquet_pair(data_dir, n=300)
        out = tmp_path / "out"

        main([
            "--symbol", "BTCUSDT",
            "--tf", "5m",
            "--data-dir", str(data_dir),
            "--output-dir", str(out),
            "--window", "20",
            "--burn-in", "30",
            "--emit-state",
        ])

        summary = (out / "stress_summary.md").read_text(encoding="utf-8")
        assert "## State Summary" in summary
        assert "Total switches" in summary
        assert "Longest stable run" in summary
