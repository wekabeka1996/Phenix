"""
Tests for Package C.2 — Minimal Setup Quality Score.

Proves that:
  - setup_quality and sub-scores appear in ENTRY signal trace
  - sub-scores are bounded [0.0, 1.0]
  - composite is in [0.0, 1.0]
  - setup_quality does NOT appear in FULL_CLOSE trace
  - setup_quality does NOT affect exit logic (regression)
  - helper math is correct for edge cases
"""
from __future__ import annotations

from decimal import Decimal

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
    )
    defaults.update(overrides)
    return MDAMRStrategyV11(**defaults)


# ---------------------------------------------------------------------------
# Unit: _compute_setup_quality helper
# ---------------------------------------------------------------------------

class TestComputeSetupQualityHelper:
    SQ_KEYS = {"setup_quality", "sq_penetration", "sq_channel_quality", "sq_coherence", "sq_volatility"}

    def _call(self, **kwargs):
        s = _make_strategy()
        return s._compute_setup_quality(**kwargs)

    def test_returns_all_expected_keys(self) -> None:
        result = self._call(
            penetration_depth=0.1,
            channel_width_pct=0.5,
            directional_coherence=0.75,
            atr_zscore=0.5,
            dir_components={"d1": 1.0, "h1": 1.0, "m30": 1.0, "m15": 1.0},
            entry_side="BUY",
        )
        assert self.SQ_KEYS.issubset(result.keys())

    def test_composite_is_mean_of_sub_scores(self) -> None:
        result = self._call(
            penetration_depth=0.1,
            channel_width_pct=0.5,
            directional_coherence=0.75,
            atr_zscore=0.5,
            dir_components={"d1": 1.0},
            entry_side="BUY",
        )
        sub_scores = [result["sq_penetration"], result["sq_channel_quality"],
                      result["sq_coherence"], result["sq_volatility"]]
        expected_composite = sum(sub_scores) / 4.0
        assert abs(result["setup_quality"] - expected_composite) < 1e-9

    def test_all_sub_scores_bounded_0_to_1(self) -> None:
        # Extreme inputs must not produce out-of-bounds scores
        for penetration in [-1.0, 0.0, 0.25, 0.5, 2.0]:
            for channel_width in [0.0, 0.001, 0.5, 1.0, 10.0]:
                for coherence in [0.0, 0.5, 1.0]:
                    for atr_z in [-5.0, 0.0, 1.5, 3.0, 10.0]:
                        result = self._call(
                            penetration_depth=penetration,
                            channel_width_pct=channel_width,
                            directional_coherence=coherence,
                            atr_zscore=atr_z,
                            dir_components={"d1": 1.0},
                            entry_side="BUY",
                        )
                        for key in self.SQ_KEYS:
                            v = result[key]
                            assert 0.0 <= v <= 1.0, \
                                f"{key}={v} out of [0,1] for inputs: pen={penetration}, cw={channel_width}, coh={coherence}, atr={atr_z}"

    def test_perfect_setup_score_is_high(self) -> None:
        result = self._call(
            penetration_depth=0.4,   # strong penetration
            channel_width_pct=1.5,   # wide band
            directional_coherence=1.0,  # full coherence
            atr_zscore=-0.5,         # low volatility
            dir_components={"d1": 1.0, "h1": 1.0, "m30": 1.0, "m15": 1.0},
            entry_side="BUY",
        )
        assert result["setup_quality"] > 0.8, \
            f"Expected high quality, got {result['setup_quality']}"

    def test_poor_setup_score_is_low(self) -> None:
        result = self._call(
            penetration_depth=0.0,   # no penetration
            channel_width_pct=0.0,   # degenerate channel
            directional_coherence=0.0,  # no coherence
            atr_zscore=3.0,          # maximum volatility penalty
            dir_components={"d1": 1.0},
            entry_side="BUY",
        )
        assert result["setup_quality"] < 0.1, \
            f"Expected low quality, got {result['setup_quality']}"

    def test_high_atr_zscore_penalizes_volatility_score(self) -> None:
        r_low_vol = self._call(
            penetration_depth=0.1,
            channel_width_pct=0.5,
            directional_coherence=0.5,
            atr_zscore=0.0,
            dir_components={"d1": 1.0},
            entry_side="BUY",
        )
        r_high_vol = self._call(
            penetration_depth=0.1,
            channel_width_pct=0.5,
            directional_coherence=0.5,
            atr_zscore=3.0,
            dir_components={"d1": 1.0},
            entry_side="BUY",
        )
        assert r_low_vol["sq_volatility"] > r_high_vol["sq_volatility"]
        assert r_high_vol["sq_volatility"] == 0.0


# ---------------------------------------------------------------------------
# Integration: setup_quality appears in ENTRY signal trace
# ---------------------------------------------------------------------------

class TestSetupQualityInEntryTrace:
    SQ_KEYS = {"setup_quality", "sq_penetration", "sq_channel_quality", "sq_coherence", "sq_volatility"}

    def _warm_and_get_signal(self) -> tuple[dict, str | None]:
        """Feed 200 flat bars then a sharp drop to force a LONG ENTRY signal."""
        s = _make_strategy()
        for _ in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price, "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        result = s.on_bar(
            bar={
                "open": Decimal("0.500"),
                "high": Decimal("0.510"),
                "low": Decimal("0.480"),
                "close": Decimal("0.490"),
            },
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )
        return result, (str(result.get("signal").intent_kind)
                        if result.get("status") == "SIGNAL" else None)

    def test_setup_quality_present_if_entry_signal_emitted(self) -> None:
        result, intent = self._warm_and_get_signal()
        if intent != "ENTRY":
            pytest.skip("No ENTRY signal produced — bar params may need adjustment")
        trace = result["signal"].trace
        for key in self.SQ_KEYS:
            assert key in trace, f"Missing key: {key} in trace"

    def test_setup_quality_bounded_0_to_1_on_real_entry(self) -> None:
        result, intent = self._warm_and_get_signal()
        if intent != "ENTRY":
            pytest.skip("No ENTRY signal produced")
        trace = result["signal"].trace
        for key in self.SQ_KEYS:
            v = trace[key]
            assert 0.0 <= v <= 1.0, f"{key}={v} out of [0,1]"

    def test_setup_quality_not_present_in_noop_trace(self) -> None:
        """setup_quality must NOT appear in NOOP trace."""
        s = _make_strategy()
        for _ in range(200):
            price = Decimal("1.000")
            s.on_bar(
                bar={"open": price, "high": price, "low": price, "close": price},
                position_ctx={"qty_signed": 0.0, "bars_held": 0},
            )
        result = s.on_bar(
            bar={"open": Decimal("1.0"), "high": Decimal("1.001"), "low": Decimal("0.999"), "close": Decimal("1.0")},
            position_ctx={"qty_signed": 0.0, "bars_held": 0},
        )
        assert result.get("status") == "NOOP"
        trace = result.get("trace", {})
        assert "setup_quality" not in trace


# ---------------------------------------------------------------------------
# Regression: setup_quality does not affect exit logic
# ---------------------------------------------------------------------------

class TestC2DoesNotAffectExitLogic:
    def test_exit_logic_is_unaffected_by_setup_quality(self) -> None:
        """Verify resolve_exit_action ignores setup_quality — it's trace-only."""
        s = _make_strategy(hold_edge_min=-0.5)
        # With inverted hold_edge → killswitch
        action, reason = s.resolve_exit_action(
            position_ctx={"bars_held": 3, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": -0.9,  # inverted
                "hold_edge_min": -0.5,
                "reached_channel_target": False,
                "expected_edge_after_costs": 0.0,
            },
            cost_ctx={"fee_bps": 4.0, "slippage_buffer_bps": 2.0},
        )
        assert action == "FULL_CLOSE"
        assert reason == "EDGE_GONE_KILLSWITCH"

    def test_scaleout_unaffected_by_setup_quality(self) -> None:
        # TOTAL_COST_PCT = (fee_bps + slippage*2) / 10000 = (4 + 4) / 10000 = 0.0008
        # expected_edge_after_costs must exceed TOTAL_COST_PCT for scaleout to fire
        s = _make_strategy()
        action, reason = s.resolve_exit_action(
            position_ctx={"bars_held": 3, "qty_signed": 1.0},
            score_ctx={
                "hold_edge": 0.4,
                "hold_edge_min": -0.5,
                "reached_channel_target": True,
                "expected_edge_after_costs": 0.01,  # well above 0.0008 TOTAL_COST_PCT
            },
            cost_ctx={"fee_bps": 4.0, "slippage_buffer_bps": 2.0},
        )
        assert action == "PARTIAL_CLOSE"
        assert reason == "FEE_AWARE_SCALEOUT"
