"""
Unit tests for DangerZoneShield — Volatility Circuit Breaker.

Tests cover:
1. Vol/spread/motion triggers → VETO (0.0)
2. All-clear → pass-through (1.0)
3. NaN/invalid input handling
4. Priority: vol → spread → motion
"""
import math
import pytest

from apps.reference.domains.decision_making.shields.danger_zone import DangerZoneShield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_dz(**kw):
    defaults = dict(vol_threshold=0.95, spread_threshold=50.0, motion_threshold=3.0)
    defaults.update(kw)
    return DangerZoneShield(**defaults)


# ---------------------------------------------------------------------------
# 1. Individual triggers → VETO
# ---------------------------------------------------------------------------
class TestTriggers:
    def test_vol_trigger(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"volatility_state": 0.96}, 0.5, 1.0)
        assert r.multiplier == 0.0
        assert "vol=" in r.reasons[0]

    def test_spread_trigger(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"spread_bps": 60.0}, 0.5, 1.0)
        assert r.multiplier == 0.0
        assert "spread=" in r.reasons[0]

    def test_motion_trigger_positive(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"price_motion_norm": 4.0}, 0.5, 1.0)
        assert r.multiplier == 0.0
        assert "motion=" in r.reasons[0]

    def test_motion_trigger_negative(self):
        """Negative motion should use abs() comparison."""
        dz = _make_dz()
        r = dz.evaluate("BTC", {"price_motion_norm": -4.0}, 0.5, 1.0)
        assert r.multiplier == 0.0

    def test_all_clear(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {
            "volatility_state": 0.5,
            "spread_bps": 10.0,
            "price_motion_norm": 1.0,
        }, 0.5, 1.0)
        assert r.multiplier == 1.0
        assert r.reasons == []

    def test_no_features_all_clear(self):
        """All features missing → cannot trigger → pass-through."""
        dz = _make_dz()
        r = dz.evaluate("BTC", {}, 0.5, 1.0)
        assert r.multiplier == 1.0


# ---------------------------------------------------------------------------
# 2. Priority: vol → spread → motion
# ---------------------------------------------------------------------------
class TestPriority:
    def test_vol_beats_spread(self):
        """When both vol and spread trigger, vol fires first."""
        dz = _make_dz()
        r = dz.evaluate("BTC", {
            "volatility_state": 0.99,
            "spread_bps": 100.0,
        }, 0.5, 1.0)
        assert "vol=" in r.reasons[0]
        assert "spread" not in r.reasons[0]


# ---------------------------------------------------------------------------
# 3. NaN/invalid handling
# ---------------------------------------------------------------------------
class TestNaNHandling:
    def test_nan_vol_skipped(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"volatility_state": float("nan")}, 0.5, 1.0)
        assert r.multiplier == 1.0  # NaN is not finite → skipped

    def test_inf_spread_skipped(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"spread_bps": float("inf")}, 0.5, 1.0)
        assert r.multiplier == 1.0

    def test_string_vol_skipped(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"volatility_state": "not_a_number"}, 0.5, 1.0)
        assert r.multiplier == 1.0

    def test_none_spread_skipped(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {"spread_bps": None}, 0.5, 1.0)
        assert r.multiplier == 1.0


# ---------------------------------------------------------------------------
# 4. Boundary conditions
# ---------------------------------------------------------------------------
class TestBoundary:
    def test_exactly_at_vol_threshold_no_trigger(self):
        """At vol=0.95 (not >), should NOT trigger."""
        dz = _make_dz(vol_threshold=0.95)
        r = dz.evaluate("BTC", {"volatility_state": 0.95}, 0.5, 1.0)
        assert r.multiplier == 1.0

    def test_just_above_vol_threshold(self):
        dz = _make_dz(vol_threshold=0.95)
        r = dz.evaluate("BTC", {"volatility_state": 0.9501}, 0.5, 1.0)
        assert r.multiplier == 0.0


# ---------------------------------------------------------------------------
# 5. Shield contract
# ---------------------------------------------------------------------------
class TestContract:
    def test_shield_name(self):
        dz = _make_dz()
        r = dz.evaluate("BTC", {}, 0.5, 1.0)
        assert r.shield_name == "DangerZoneShield"
