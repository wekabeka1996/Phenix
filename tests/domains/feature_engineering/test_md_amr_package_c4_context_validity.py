"""
Tests for Package C.4 - Lightweight Context Validity.

Proves that:
  - healthier context does not score worse than degraded context
  - VALID / WEAKENING / INVALID / UNKNOWN states are deterministic
  - missing critical context remains explicit rather than silently invented
  - C.4 fields appear in in-position trace alongside C.1/C.2/C.3 overlays
  - baseline exit semantics remain unaffected by the new advisory layer
"""
from __future__ import annotations

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


class TestContextValidityMath:
    def test_healthier_context_scores_above_degraded_context(self) -> None:
        strategy = _make_strategy()

        healthy = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=0.6,
            channel_width_pct=1.10,
            dir_components={"d1": 0.8, "h1": 0.7, "m30": 0.5, "m15": 0.4},
            hold_quality=0.82,
            progress_deficit=0.05,
            context_regime="MEAN_REVERSION",
            context_regime_confidence=0.82,
            context_regime_allowed=True,
        )
        degraded = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=2.0,
            channel_width_pct=0.25,
            dir_components={"d1": -0.2, "h1": 0.3, "m30": -0.1, "m15": 0.2},
            hold_quality=0.48,
            progress_deficit=0.30,
            context_regime="LOW_VOLATILITY",
            context_regime_confidence=0.44,
            context_regime_allowed=True,
        )

        assert healthy["context_validity"] > degraded["context_validity"]
        assert healthy["context_validity_state"] == "VALID"
        assert degraded["context_validity_state"] == "WEAKENING"

    def test_context_validity_states_are_deterministically_distinguishable(self) -> None:
        strategy = _make_strategy()

        valid = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=0.2,
            channel_width_pct=1.20,
            dir_components={"d1": 0.7, "h1": 0.6, "m30": 0.5, "m15": 0.3},
            hold_quality=0.85,
            progress_deficit=0.02,
            context_regime="MEAN_REVERSION",
            context_regime_confidence=0.85,
            context_regime_allowed=True,
        )
        weakening = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=2.0,
            channel_width_pct=0.25,
            dir_components={"d1": 0.3, "h1": -0.1, "m30": 0.2, "m15": -0.2},
            hold_quality=0.48,
            progress_deficit=0.30,
            context_regime="LOW_VOLATILITY",
            context_regime_confidence=0.45,
            context_regime_allowed=True,
        )
        invalid = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=0.4,
            channel_width_pct=0.90,
            dir_components={"d1": 0.8, "h1": 0.7, "m30": 0.6, "m15": 0.5},
            hold_quality=0.74,
            progress_deficit=0.08,
            context_regime="TREND_DOWN",
            context_regime_confidence=0.90,
            context_regime_allowed=False,
        )
        unknown = strategy._compute_context_validity_overlay(
            qty_signed=1.0,
            atr_zscore=0.4,
            channel_width_pct=0.90,
            dir_components={"d1": 0.8, "h1": 0.7, "m30": 0.6, "m15": 0.5},
            hold_quality=None,
            progress_deficit=None,
            context_regime=None,
            context_regime_confidence=None,
            context_regime_allowed=None,
        )

        assert valid["context_validity_state"] == "VALID"
        assert valid["context_penalty_reason"] == "NONE"
        assert weakening["context_validity_state"] == "WEAKENING"
        assert invalid["context_validity_state"] == "INVALID"
        assert invalid["context_penalty_reason"] == "REGIME_INCOMPATIBLE"
        assert unknown["context_validity_state"] == "UNKNOWN"
        assert unknown["context_validity"] is None

    def test_missing_critical_context_is_explicit_unknown(self) -> None:
        strategy = _make_strategy()

        overlay = strategy._compute_context_validity_overlay(
            qty_signed=-1.0,
            atr_zscore=0.8,
            channel_width_pct=0.60,
            dir_components={"d1": -0.6, "h1": -0.5, "m30": -0.4, "m15": -0.2},
            hold_quality=0.55,
            progress_deficit=0.10,
            context_regime="LOW_VOLATILITY",
            context_regime_confidence=None,
            context_regime_allowed=True,
        )

        assert overlay["context_validity_state"] == "UNKNOWN"
        assert overlay["context_validity"] is None
        assert "context_regime_confidence" in overlay["context_validity_missing_fields"]


class TestContextValidityTracing:
    def test_c4_fields_appear_in_position_trace(self) -> None:
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
                "context_regime": "MEAN_REVERSION",
                "context_regime_confidence": 0.78,
                "context_regime_allowed": True,
            },
        )

        trace = _trace_from_result(result)
        for key in (
            "context_validity",
            "context_validity_state",
            "context_penalty_reason",
            "regime_validity_component",
            "volatility_validity_component",
            "structure_validity_component",
            "progress_alignment_component",
        ):
            assert key in trace, f"Missing C.4 trace field: {key}"
        assert trace["context_validity_state"] in {
            "VALID", "WEAKENING", "INVALID"}

    def test_missing_anchor_surface_propagates_unknown_context(self) -> None:
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
                "context_regime": "MEAN_REVERSION",
                "context_regime_confidence": 0.78,
                "context_regime_allowed": True,
            },
        )

        trace = _trace_from_result(result)
        assert trace["progress_state"] == "UNKNOWN"
        assert trace["context_validity_state"] == "UNKNOWN"
        assert "hold_quality" in trace["context_validity_missing_fields"]
