"""
Tests for Package C.3 - Hold Quality / Soft Decay.

Proves that:
  - time_decay is monotonic when time passes without progress
  - progress_deficit reflects expected-progress lag deterministically
  - hold_quality stays bounded and separates healthy vs stale holds
  - C.3 fields appear in in-position trace alongside C.1 fields
  - missing anchors remain explicit rather than silently defaulted
  - existing exit semantics are unchanged by the overlay
"""
from __future__ import annotations

import math
from decimal import Decimal

import pytest

from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11


def _make_strategy(**overrides) -> MDAMRStrategyV11:
    defaults = dict(
        channel_window_bars=12,
        hysteresis_mult=1.20,
        threshold_z=2.20,
        volatility_dampening_factor=0.50,
        thr_base=0.55,
        alpha=0.25,
        conf_min=0.22,
        max_hold_bars=16,
        fee_bps=4.0,
        slippage_buffer_bps=2.0,
        scaleout_fraction=0.50,
        weights={"d1": 0.35, "h1": 0.30, "m30": 0.20, "m15": 0.15},
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        thr_floor=0.10,
        scaleout_cost_model="round_trip",
        atr_window=14,
        atr_stats_window=64,
        hold_edge_min=-0.50,
        target_approach_pct=0.0,
        progress_tracking_early_progress_max_pct=0.25,
        progress_tracking_partial_progress_max_pct=0.70,
        progress_tracking_near_completion_max_pct=1.00,
        setup_quality_penetration_depth_full_scale=0.50,
        setup_quality_channel_width_pct_full_scale=1.00,
        setup_quality_volatility_z_full_penalty=3.00,
        hold_quality_expected_progress_grace_frac=0.25,
        hold_quality_time_decay_weight=0.35,
        hold_quality_progress_deficit_weight=0.45,
        context_validity_regime_confidence_floor=0.35,
        context_validity_regime_confidence_valid=0.60,
        context_validity_volatility_z_weakening=1.50,
        context_validity_volatility_z_invalid=3.00,
        context_validity_channel_width_pct_floor=0.10,
        context_validity_channel_width_pct_valid=1.00,
        context_validity_regime_weight=0.35,
        context_validity_volatility_weight=0.20,
        context_validity_structure_weight=0.20,
        context_validity_progress_alignment_weight=0.25,
        context_validity_valid_score_min=0.70,
        context_validity_invalid_score_max=0.35,
    )
    defaults.update(overrides)
    return MDAMRStrategyV11(**defaults)


def _warm_up_strategy(strategy: MDAMRStrategyV11, bars: int = 200) -> None:
    price = Decimal("1.000")
    for _ in range(bars):
        strategy.on_bar(
            bar={"open": price, "high": price, "low": price, "close": price},
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )


def _trace_from_result(result: dict) -> dict:
    if result.get("status") == "SIGNAL":
        return result["signal"].trace
    return result.get("trace", {})


class TestHoldQualityOverlayMath:
    def test_time_decay_is_monotonic_without_progress(self) -> None:
        strategy = _make_strategy()

        early = strategy._compute_hold_quality_overlay(
            bars_held=2,
            hold_health=0.4,
            progress_pct=0.0,
        )
        middle = strategy._compute_hold_quality_overlay(
            bars_held=8,
            hold_health=0.4,
            progress_pct=0.0,
        )
        late = strategy._compute_hold_quality_overlay(
            bars_held=14,
            hold_health=0.4,
            progress_pct=0.0,
        )

        assert early["time_decay"] <= middle["time_decay"] <= late["time_decay"]

    def test_progress_deficit_increases_when_actual_progress_lags(self) -> None:
        strategy = _make_strategy()

        lagging = strategy._compute_hold_quality_overlay(
            bars_held=12,
            hold_health=0.4,
            progress_pct=0.10,
        )
        on_schedule = strategy._compute_hold_quality_overlay(
            bars_held=12,
            hold_health=0.4,
            progress_pct=0.80,
        )

        assert lagging["progress_deficit"] > on_schedule["progress_deficit"]
        assert on_schedule["progress_deficit"] == 0.0

    def test_overlay_matches_closed_form_expected_values(self) -> None:
        strategy = _make_strategy()

        overlay = strategy._compute_hold_quality_overlay(
            bars_held=8,
            hold_health=0.5,
            progress_pct=0.25,
        )

        assert overlay["elapsed_hold_frac"] == pytest.approx(0.5)
        assert overlay["remaining_hold_frac"] == pytest.approx(0.5)
        assert overlay["expected_progress_pct"] == pytest.approx(1.0 / 3.0)
        assert overlay["progress_deficit"] == pytest.approx(1.0 / 12.0)
        assert overlay["time_decay"] == pytest.approx(0.375)
        assert overlay["structural_hold_quality"] == pytest.approx(0.75)
        assert overlay["hold_quality_penalty"] == pytest.approx(0.16875)
        assert overlay["hold_quality"] == pytest.approx(0.58125)

    def test_hold_quality_is_bounded_and_distinguishes_stale_holds(self) -> None:
        strategy = _make_strategy()

        healthy = strategy._compute_hold_quality_overlay(
            bars_held=6,
            hold_health=0.7,
            progress_pct=0.55,
        )
        stale = strategy._compute_hold_quality_overlay(
            bars_held=14,
            hold_health=0.7,
            progress_pct=0.05,
        )

        for value in (healthy["hold_quality"], stale["hold_quality"]):
            assert 0.0 <= value <= 1.0
            assert math.isfinite(value)

        assert healthy["hold_quality"] > stale["hold_quality"]


class TestHoldQualityTracing:
    def test_c3_fields_appear_in_position_trace_with_anchors(self) -> None:
        strategy = _make_strategy()
        _warm_up_strategy(strategy)

        result = strategy.on_bar(
            bar={
                "open": Decimal("0.550"),
                "high": Decimal("0.560"),
                "low": Decimal("0.540"),
                "close": Decimal("0.550"),
            },
            position_ctx={
                "qty_signed": 1.0,
                "bars_held": 8,
                "entry_price": 0.5,
                "entry_target_price": 1.0,
            },
        )

        trace = _trace_from_result(result)
        for key in (
            "progress_pct",
            "progress_state",
            "elapsed_hold_frac",
            "remaining_hold_frac",
            "expected_progress_pct",
            "progress_deficit",
            "time_decay",
            "hold_quality",
        ):
            assert key in trace, f"Missing C.3 trace field: {key}"
        assert trace["progress_state"] != "UNKNOWN"
        assert isinstance(trace["hold_quality"], float)

    def test_missing_anchors_leave_explicit_unknown_c3_surface(self) -> None:
        strategy = _make_strategy()
        _warm_up_strategy(strategy)

        result = strategy.on_bar(
            bar={
                "open": Decimal("0.550"),
                "high": Decimal("0.560"),
                "low": Decimal("0.540"),
                "close": Decimal("0.550"),
            },
            position_ctx={"qty_signed": 1.0, "bars_held": 8},
        )

        trace = _trace_from_result(result)
        assert trace["progress_state"] == "UNKNOWN"
        assert trace["progress_pct"] is None
        assert trace["expected_progress_pct"] == pytest.approx(1.0 / 3.0)
        assert trace["progress_deficit"] is None
        assert trace["time_decay"] is None
        assert trace["hold_quality"] is None


class TestC3Regression:
    def test_timeout_reason_is_unchanged(self) -> None:
        strategy = _make_strategy(max_hold_bars=16)

        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 17, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 4.0, "slippage_buffer_bps": 2.0},
        )

        assert action == "FULL_CLOSE"
        assert reason == "ZOMBIE_POSITION_TIMEOUT"
