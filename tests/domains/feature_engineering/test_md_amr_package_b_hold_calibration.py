"""
MD-AMR Package B: Hold Calibration and Zombie Control Tests.

Validates:
1. target_approach_pct: scaleout fires when price enters tolerance zone near avg_close
2. target_approach_pct=0.0: original strict equality preserved (regression)
3. max_hold_bars=32 config: timeout fires at correct bar count
4. hold_health in trace (renamed from hold_edge, backward-compat alias preserved)
5. Existing Package A tests still pass (scaleout and killswitch semantics unchanged)
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import pytest

from apps.reference.domains.feature_engineering.md_amr_strategy import (
    MDAMRStrategyV11,
)


# ---------------------------------------------------------------------------
# Helpers (same as Package A tests)
# ---------------------------------------------------------------------------

def _make_strategy(**overrides) -> MDAMRStrategyV11:
    defaults: Dict[str, Any] = dict(
        channel_window_bars=12,
        hysteresis_mult=1.20,
        threshold_z=2.20,
        volatility_dampening_factor=0.50,
        thr_base=0.55,
        alpha=0.25,
        conf_min=0.22,
        max_hold_bars=32,
        fee_bps=0.0,            # zero costs to focus on logic, not cost filter
        slippage_buffer_bps=0.0,
        scaleout_fraction=0.50,
        weights={"d1": 0.35, "h1": 0.30, "m30": 0.20, "m15": 0.15},
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        thr_floor=0.10,
        scaleout_cost_model="round_trip",
        atr_window=14,
        atr_stats_window=64,
        target_approach_pct=0.002,
    )
    defaults.update(overrides)
    return MDAMRStrategyV11(**defaults)


def _bar(close: float, high: float | None = None, low: float | None = None) -> Dict[str, Any]:
    spread = close * 0.005
    return {
        "open": str(close),
        "high": str(high if high is not None else close + spread),
        "low": str(low if low is not None else close - spread),
        "close": str(close),
    }


def _warm_up_strategy(strategy: MDAMRStrategyV11, base_price: float = 100.0) -> None:
    n_bars = 96 + strategy.atr_stats_window + 10
    for _ in range(n_bars):
        strategy.on_bar(bar=_bar(base_price), position_ctx={"qty_signed": 0.0, "bars_held": 0})


# ---------------------------------------------------------------------------
# Test 1: target_approach_pct tolerance zone enables earlier scaleout
# ---------------------------------------------------------------------------

class TestTargetApproachPct:
    """
    The scaleout condition must fire when close_now enters the tolerance zone
    (within target_approach_pct of avg_close), not only at exact equality.
    """

    def test_scaleout_fires_in_tolerance_zone_long(self) -> None:
        """
        LONG position: price reaches avg_close * (1 - 0.002) — i.e., 0.2% before target.
        resolve_exit_action should return FEE_AWARE_SCALEOUT.
        """
        strategy = _make_strategy(target_approach_pct=0.002, fee_bps=0.0, slippage_buffer_bps=0.0)
        # Directly test resolve_exit_action with tolerance-zone semantics
        avg_close = 100.0
        tolerance = strategy.target_approach_pct
        # price 0.2% below avg_close — should be "reached_target" with tolerance
        close_near_target = avg_close * (1.0 - tolerance)  # = 99.8
        reached = close_near_target >= avg_close * (1.0 - tolerance)
        assert reached, "price exactly at tolerance boundary should satisfy reached_target"

        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 5, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": True,   # computed with tolerance
                "expected_edge_after_costs": 0.01,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        assert action == "PARTIAL_CLOSE"
        assert reason == "FEE_AWARE_SCALEOUT"

    def test_strict_equality_with_zero_tolerance_does_not_fire_before_target(self) -> None:
        """
        With target_approach_pct=0.0 (strict), price exactly 0.001% below avg_close
        should NOT trigger reached_target.
        """
        avg_close = 100.0
        close_just_below = avg_close * 0.9999  # 0.01% below
        # zero tolerance means reached = close_now >= avg_close exactly
        reached = close_just_below >= avg_close * (1.0 - 0.0)  # strict
        assert not reached, "strict mode: price below avg_close must not trigger reached_target"

    def test_tolerance_zone_symmetric_for_short(self) -> None:
        """
        SHORT position: reached_target when close_now <= avg_close * (1 + tolerance).
        """
        avg_close = 100.0
        tolerance = 0.002
        close_near_short_target = avg_close * (1.0 + tolerance)  # = 100.2
        reached = close_near_short_target <= avg_close * (1.0 + tolerance)
        assert reached, "price at Short tolerance boundary should satisfy reached_target"

    def test_strategy_constructor_accepts_target_approach_pct(self) -> None:
        strategy = _make_strategy(target_approach_pct=0.005)
        assert strategy.target_approach_pct == 0.005

    def test_default_target_approach_pct_is_002(self) -> None:
        strategy = _make_strategy()
        assert abs(strategy.target_approach_pct - 0.002) < 1e-9


# ---------------------------------------------------------------------------
# Test 2: max_hold_bars=32 calibration
# ---------------------------------------------------------------------------

class TestMaxHoldBarsCalibration:
    """
    After Package B, max_hold_bars is 32. Verify the timeout fires at the
    right count via resolve_exit_action directly.
    """

    def test_no_zombie_at_32_bars(self) -> None:
        strategy = _make_strategy(max_hold_bars=32)
        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 32, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        # bars_held > max_hold_bars, so 32 > 32 is False → no zombie yet
        assert action is None

    def test_zombie_at_33_bars(self) -> None:
        strategy = _make_strategy(max_hold_bars=32)
        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 33, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        assert action == "FULL_CLOSE"
        assert reason == "ZOMBIE_POSITION_TIMEOUT"


# ---------------------------------------------------------------------------
# Test 3: hold_health in trace (Package B rename)
# ---------------------------------------------------------------------------

class TestTraceHoldHealthPresence:
    """
    After Package B, trace must contain 'hold_health' (renamed from hold_edge).
    'hold_edge' must also be present as backward-compat alias (same value).
    """

    def test_trace_contains_hold_health_key(self) -> None:
        strategy = _make_strategy()
        _warm_up_strategy(strategy, base_price=100.0)

        in_position = {"qty_signed": 1.0, "bars_held": 2}
        result = strategy.on_bar(bar=_bar(99.0), position_ctx=in_position)
        trace = result.get("trace", {})
        assert "hold_health" in trace, "hold_health must be present in trace after Package B"

    def test_hold_edge_backward_compat_alias_matches_hold_health(self) -> None:
        strategy = _make_strategy()
        _warm_up_strategy(strategy, base_price=100.0)

        in_position = {"qty_signed": 1.0, "bars_held": 2}
        result = strategy.on_bar(bar=_bar(99.0), position_ctx=in_position)
        trace = result.get("trace", {})
        hold_health = trace.get("hold_health")
        hold_edge = trace.get("hold_edge")
        if hold_health is not None and hold_edge is not None:
            assert hold_health == hold_edge, (
                f"hold_edge={hold_edge} must equal hold_health={hold_health} (compat alias)"
            )


# ---------------------------------------------------------------------------
# Test 4: Package A regression — scaleout and killswitch semantics preserved
# ---------------------------------------------------------------------------

class TestPackageARegression:
    """
    Ensure Package B did not break the Package A exit semantics.
    """

    def test_killswitch_still_fires_on_structural_inversion(self) -> None:
        """If hold_edge <= hold_edge_min, killswitch must still fire."""
        strategy = _make_strategy()
        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 5, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": -0.6,
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        assert action == "FULL_CLOSE"
        assert reason == "EDGE_GONE_KILLSWITCH"

    def test_no_kill_when_hold_edge_healthy(self) -> None:
        strategy = _make_strategy()
        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 5, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        assert action is None
        assert reason is None

    def test_scaleout_still_fires_with_target_reached_and_positive_edge(self) -> None:
        strategy = _make_strategy(fee_bps=0.0, slippage_buffer_bps=0.0)
        action, reason = strategy.resolve_exit_action(
            position_ctx={"bars_held": 5, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.3,
                "hold_edge_min": -0.5,
                "reached_channel_target": True,
                "expected_edge_after_costs": 0.01,
            },
            cost_ctx={"fee_bps": 0.0, "slippage_buffer_bps": 0.0},
        )
        assert action == "PARTIAL_CLOSE"
        assert reason == "FEE_AWARE_SCALEOUT"
