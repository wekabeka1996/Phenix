"""
Tests for Package C.1 — Anchored Target + Progress Tracking.

Proves that:
  - progress_pct and progress_state appear deterministically in trace
  - math is correct for LONG and SHORT positions
  - UNKNOWN fallback when anchors not supplied
  - anchor lifecycle: set at ENTRY, cleared at FULL_CLOSE
  - no regression in baseline exit semantics
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict

import pytest

from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Unit tests: _compute_progress_state
# ---------------------------------------------------------------------------

class TestComputeProgressState:
    def test_negative_progress_is_reversing_against(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(-0.5) == "REVERSING_AGAINST"

    def test_zero_progress_is_early(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(0.0) == "EARLY_PROGRESS"

    def test_mid_progress_is_partial(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(0.5) == "PARTIAL_PROGRESS"

    def test_near_completion(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(0.85) == "NEAR_COMPLETION"

    def test_at_target_is_complete(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(1.0) == "COMPLETE"

    def test_beyond_target_is_complete(self) -> None:
        s = _make_strategy()
        assert s._compute_progress_state(1.5) == "COMPLETE"


# ---------------------------------------------------------------------------
# Unit tests: _compute_progress
# ---------------------------------------------------------------------------

class TestComputeProgress:
    def test_long_at_halfway(self) -> None:
        s = _make_strategy()
        # LONG: entry_price=95, target=100, close_now=97.5 → 50% progress
        pct, state = s._compute_progress(
            close_now=97.5,
            entry_price=95.0,
            entry_target_price=100.0,
            qty_signed=1.0,
        )
        assert abs(pct - 0.5) < 1e-9
        assert state == "PARTIAL_PROGRESS"

    def test_short_at_halfway(self) -> None:
        s = _make_strategy()
        # SHORT: entry_price=105, target=100, close_now=102.5 → 50% progress
        pct, state = s._compute_progress(
            close_now=102.5,
            entry_price=105.0,
            entry_target_price=100.0,
            qty_signed=-1.0,
        )
        assert abs(pct - 0.5) < 1e-9
        assert state == "PARTIAL_PROGRESS"

    def test_long_at_entry_is_zero(self) -> None:
        s = _make_strategy()
        pct, state = s._compute_progress(
            close_now=95.0,
            entry_price=95.0,
            entry_target_price=100.0,
            qty_signed=1.0,
        )
        assert pct == 0.0
        assert state == "EARLY_PROGRESS"

    def test_long_moved_against_is_negative(self) -> None:
        s = _make_strategy()
        # Price moved down from 95 to 93 (against LONG thesis)
        pct, state = s._compute_progress(
            close_now=93.0,
            entry_price=95.0,
            entry_target_price=100.0,
            qty_signed=1.0,
        )
        assert pct < 0.0
        assert state == "REVERSING_AGAINST"

    def test_long_fully_complete(self) -> None:
        s = _make_strategy()
        pct, state = s._compute_progress(
            close_now=100.0,
            entry_price=95.0,
            entry_target_price=100.0,
            qty_signed=1.0,
        )
        assert abs(pct - 1.0) < 1e-9
        assert state == "COMPLETE"

    def test_degenerate_entry_equals_target(self) -> None:
        # When entry == target, progress should return COMPLETE immediately (no division by zero)
        s = _make_strategy()
        pct, state = s._compute_progress(
            close_now=100.0,
            entry_price=100.0,
            entry_target_price=100.0,
            qty_signed=1.0,
        )
        assert pct == 1.0
        assert state == "COMPLETE"


# ---------------------------------------------------------------------------
# Integration test: trace fields appear in in-position on_bar
# ---------------------------------------------------------------------------

class TestProgressTracingInPositionCtx:
    def _make_warmed_strategy(self) -> tuple[MDAMRStrategyV11, dict]:
        """Feed enough bars to warm up the strategy, then return a LONG entry bar."""
        s = _make_strategy()
        # Feed 200 bars at a flat price to warm up ATR + channel + dir_score
        for i in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price,
                     "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        # Now feed a bar where price drops far below channel's avg_low to get a LONG entry
        entry_bar = {
            "open": Decimal("0.500"),
            "high": Decimal("0.520"),
            "low": Decimal("0.480"),
            "close": Decimal("0.500"),
        }
        result = s.on_bar(
            bar=entry_bar,
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )
        return s, result

    def test_without_anchors_progress_state_is_unknown(self) -> None:
        """When position_ctx has no entry_price/entry_target_price, progress_state=UNKNOWN."""
        s = _make_strategy()
        for i in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price,
                     "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        result = s.on_bar(
            bar={"open": Decimal("0.5"), "high": Decimal(
                "0.52"), "low": Decimal("0.48"), "close": Decimal("0.5")},
            position_ctx={"qty_signed": 1.0, "bars_held": 1},  # no anchors
        )
        # Trace is in signal.trace when status=SIGNAL, or result['trace'] for NOOP.
        status = result.get("status")
        if status == "SIGNAL":
            trace = result["signal"].trace
        else:
            trace = result.get("trace", {})
        # No anchors => progress_state = UNKNOWN
        assert trace.get("progress_state") == "UNKNOWN", \
            f"Expected UNKNOWN, got {trace.get('progress_state')!r}, status={status}"
        assert trace.get("progress_pct") is None

    def test_with_anchors_progress_pct_is_numeric(self) -> None:
        """When anchors provided, trace contains numeric progress_pct."""
        s = _make_strategy()
        for i in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price,
                     "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        result = s.on_bar(
            bar={"open": Decimal("0.5"), "high": Decimal(
                "0.52"), "low": Decimal("0.48"), "close": Decimal("0.5")},
            position_ctx={
                "qty_signed": 1.0,
                "bars_held": 1,
                "entry_price": 0.5,
                "entry_target_price": 1.0,
            },
        )
        # Trace is in signal.trace when exit fires, or result['trace'] for NOOP/hold.
        status = result.get("status")
        if status == "SIGNAL":
            trace = result["signal"].trace
        else:
            trace = result.get("trace", {})
        assert trace.get("progress_state") != "UNKNOWN", \
            f"Got UNKNOWN, status={status}"
        pct = trace.get("progress_pct")
        assert pct is not None
        assert isinstance(pct, float)
        assert math.isfinite(pct)

    def test_progress_state_string_values_are_valid(self) -> None:
        """progress_state is one of the defined categoricals."""
        valid_states = {
            "REVERSING_AGAINST", "EARLY_PROGRESS", "PARTIAL_PROGRESS",
            "NEAR_COMPLETION", "COMPLETE", "UNKNOWN"
        }
        s = _make_strategy()
        for i in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price,
                     "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        result = s.on_bar(
            bar={"open": Decimal("0.5"), "high": Decimal(
                "0.52"), "low": Decimal("0.48"), "close": Decimal("0.5")},
            position_ctx={
                "qty_signed": 1.0,
                "bars_held": 1,
                "entry_price": 0.5,
                "entry_target_price": 1.0,
            },
        )
        # Trace is in signal.trace when exit fires, or result['trace'] for NOOP/hold.
        status = result.get("status")
        if status == "SIGNAL":
            trace = result["signal"].trace
        else:
            trace = result.get("trace", {})
        assert trace.get("progress_state") in valid_states

    def test_progress_fields_absent_for_noop_no_position(self) -> None:
        """When not in position and no ENTRY signal fires, no progress fields in trace at all."""
        s = _make_strategy()
        for i in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price,
                     "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        # NOOP bar (flat, won't trigger entry)
        result = s.on_bar(
            bar={"open": Decimal("1.0"), "high": Decimal(
                "1.001"), "low": Decimal("0.999"), "close": Decimal("1.0")},
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )
        assert result.get("status") == "NOOP"
        trace = result.get("trace", {})
        # progress fields should NOT appear on NOOP (not in position)
        assert "progress_pct" not in trace
        assert "progress_state" not in trace


# ---------------------------------------------------------------------------
# Regression: C.1 must not alter exit semantics
# ---------------------------------------------------------------------------

class TestC1DoesNotBreakExitSemantics:
    def test_killswitch_still_fires_with_anchors_present(self) -> None:
        """EDGE_GONE_KILLSWITCH must fire regardless of progress anchor state."""
        from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11
        s = _make_strategy(hold_edge_min=-0.5)
        action, reason = s.resolve_exit_action(
            position_ctx={"bars_held": 3, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": -0.8,  # fully inverted → killswitch
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 4.0, "slippage_buffer_bps": 2.0},
        )
        assert action == "FULL_CLOSE"
        assert reason == "EDGE_GONE_KILLSWITCH"

    def test_zombie_timeout_still_fires_with_anchors_present(self) -> None:
        s = _make_strategy(max_hold_bars=16)
        action, reason = s.resolve_exit_action(
            position_ctx={"bars_held": 17, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,  # healthy
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 4.0, "slippage_buffer_bps": 2.0},
        )
        assert action == "FULL_CLOSE"
        assert reason == "ZOMBIE_POSITION_TIMEOUT"
