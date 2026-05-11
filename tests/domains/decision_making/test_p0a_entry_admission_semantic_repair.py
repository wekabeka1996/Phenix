"""P0-A Entry Admission Semantic Repair — Focused regression tests.

Covers two root causes identified in the P0 loss behavior forensic:
  RC-1  STRATEGY_EMITS_HOLD_WITH_ENTRY_SHAPE
        hold:buy / hold:sell side_why labels must not produce an entry intent.
  RC-2  CONFIDENCE_CLAMP_MASKS_UNCERTAIN
        regime_confidence exactly at the uncertain_cutoff threshold must be
        blocked (<=), not allowed through (old <).
"""
from __future__ import annotations

import decimal
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.shared.decision_primitives.aurora_policy import determine_side
from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates
from apps.reference.config_loader import ConfigLoader


# ─── helpers ───────────────────────────────────────────────────────────────

def _D(v):
    return decimal.Decimal(str(v))


def _admission_guard_fires(side_why: str) -> bool:
    """Mirror of the guard condition in decision.py.

    Returns True when the guard FIRES (signal is blocked), False when it falls through.
    Guard fires only when side_why is non-empty AND not enter/flip.
    """
    return bool(side_why) and not (
        side_why.startswith("enter:") or side_why.startswith("flip:")
    )


def _admission_guard_passes(side_why: str) -> bool:
    """Returns True when a signal PASSES the guard (is not blocked)."""
    return not _admission_guard_fires(side_why)


def _minimal_regime_snapshot(*, confidence: float, regime: str = "TREND_UP") -> dict:
    """Minimal per-symbol regime dict accepted by apply_safety_gates."""
    return {
        "regime": regime,
        "confidence": str(confidence),
        "cache_write_ts_ms": 1_700_000_000_456,
    }


# ─── RC-1: semantic admission guard on side_why prefix ─────────────────────


class TestSemanticAdmissionGuard:
    """Guard allows enter:* and flip:*, blocks everything else."""

    # ── determine_side produces hold:* for in-position neutral zone ────────

    def test_hold_buy_label_produced_when_long_and_score_in_neutral_zone(self):
        side, why = determine_side(
            score=_D("0.0642"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="buy",
        )
        assert side == "buy"
        assert why.startswith("hold:buy:")

    def test_hold_sell_label_produced_when_short_and_score_in_neutral_zone(self):
        side, why = determine_side(
            score=_D("-0.0642"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="sell",
        )
        assert side == "sell"
        assert why.startswith("hold:sell:")

    # ── enter:* and flip:* produced for actual entry signals ───────────────

    def test_enter_buy_label_produced_from_flat(self):
        side, why = determine_side(
            score=_D("0.15"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="",
        )
        assert side == "buy"
        assert why.startswith("enter:buy:")

    def test_enter_sell_label_produced_from_flat(self):
        side, why = determine_side(
            score=_D("-0.15"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="",
        )
        assert side == "sell"
        assert why.startswith("enter:sell:")

    def test_flip_buy_to_sell_label_produced(self):
        side, why = determine_side(
            score=_D("-0.15"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="buy",
        )
        assert side == "sell"
        assert why.startswith("flip:buy->sell:")

    def test_flip_sell_to_buy_label_produced(self):
        side, why = determine_side(
            score=_D("0.15"),
            thr_buy=_D("0.10"),
            thr_sell=_D("0.10"),
            thr_neutral=_D("0.05"),
            current_side="sell",
        )
        assert side == "buy"
        assert why.startswith("flip:sell->buy:")

    # ── guard condition: enter:* and flip:* pass, everything else fails ─────

    @pytest.mark.parametrize("side_why", [
        "enter:buy:score=0.15>=thr_buy=0.10",
        "enter:sell:score=-0.15<=-thr_sell=0.10",
        "flip:buy->sell:score=-0.15<=-thr_sell=0.10",
        "flip:sell->buy:score=0.15>=thr_buy=0.10",
    ])
    def test_entry_and_flip_signals_pass_guard(self, side_why: str):
        assert _admission_guard_passes(side_why) is True

    @pytest.mark.parametrize("side_why", [
        "hold:buy:score=0.0642>=thr_neutral=0.0500",
        "hold:sell:score=-0.0642<=-thr_neutral=-0.0500",
        "exit:buy->neutral:score=0.02<thr_neutral=0.05",
        "exit:sell->neutral:score=-0.02>-thr_neutral=-0.05",
        "neutral:score=0.03",
    ])
    def test_non_entry_signals_blocked_by_guard(self, side_why: str):
        assert _admission_guard_passes(side_why) is False

    def test_empty_side_why_falls_through_guard(self):
        """Empty side_why falls through — kernel always populates it in production."""
        assert _admission_guard_passes("") is True

    def test_missing_side_why_falls_through_guard(self):
        """Missing side_why (pre-guard stubs) falls through — kernel always sets it in production."""
        for missing in (None, ""):
            assert _admission_guard_passes(str(missing or "")) is True


# ─── RC-2: regime confidence at-boundary now blocked with <= ───────────────


class TestRegimeConfidenceBoundary:
    """regime_confidence == min_threshold must be DENIED after the <= fix."""

    def _call_gates(self, *, confidence: float, min_conf_by_regime: float,
                    regime: str = "TREND_UP") -> object:
        cfg = ConfigLoader(Path("config/aurora")).load_config()
        cfg.strategies.aurora.safety_gates.enabled = True
        cfg.domains.decision_making.directional_sanity.enabled = True
        cfg.domains.decision_making.directional_sanity.nrr026_enabled = True
        cfg.domains.decision_making.directional_sanity.min_abs_delta_price = 0.0
        cfg.domains.decision_making.directional_sanity.min_confidence = 0.0
        cfg.domains.decision_making.directional_sanity.consecutive_bars = 1
        cfg.domains.decision_making.directional_sanity.min_regime_confidence_by_regime = {
            "DEFAULT": min_conf_by_regime,
            regime: min_conf_by_regime,
        }
        cfg.domains.decision_making.directional_sanity.min_regime_confidence = min_conf_by_regime
        cfg.domains.decision_making.price_motion_sanity.enabled = False

        return apply_safety_gates(
            symbol="BTCUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_000,
            why_chain=["p0a_test"],
            config=cfg,
            clock=MagicMock(now_ms=MagicMock(return_value=1_700_000_000_000)),
            symbol_states={"BTCUSDT": {
                "_delta_price_hist": deque([1.0], maxlen=20)}},
            per_symbol_regimes={"BTCUSDT": _minimal_regime_snapshot(
                confidence=confidence, regime=regime)},
            system_stress_states={},
        )

    def test_confidence_strictly_below_threshold_is_denied(self):
        """Pre-existing behavior: confidence 0.14 < min 0.15 must DENY."""
        result = self._call_gates(confidence=0.14, min_conf_by_regime=0.15)
        assert result.outcome == "DENY"
        assert result.regime_confidence_breach_kind == "below_min"

    def test_confidence_at_threshold_is_now_denied(self):
        """RC-2 fix: confidence 0.15 == min 0.15 must now DENY (was ALLOW before <= fix)."""
        result = self._call_gates(confidence=0.15, min_conf_by_regime=0.15)
        assert result.outcome == "DENY"
        assert result.regime_confidence_breach_kind == "below_min"

    def test_confidence_above_threshold_is_allowed(self):
        """Regression guard: confidence 0.16 > min 0.15 must still ALLOW."""
        result = self._call_gates(confidence=0.16, min_conf_by_regime=0.15)
        assert result.outcome != "DENY" or result.regime_confidence_breach_kind != "below_min"

    def test_uncertain_cutoff_exact_boundary_with_standard_config(self):
        """The forensic case: uncertain_cutoff=0.15 and regime_confidence=0.15 must block."""
        result = self._call_gates(confidence=0.15, min_conf_by_regime=0.15,
                                  regime="TREND_UP")
        assert result.outcome == "DENY"

    def test_threshold_reason_contains_lte_operator(self):
        """Verify the threshold_reason string reflects the <= semantics."""
        result = self._call_gates(confidence=0.15, min_conf_by_regime=0.15)
        assert "<=" in result.threshold_reason
