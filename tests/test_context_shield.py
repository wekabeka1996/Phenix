"""
Unit tests for ContextShield — Regime-Aware Signal Attenuation.

Tests cover:
1. REGIME-FIX-01: Correct UPPERCASE regime name matching
2. TTL-STALE-01: Stale regime detection and penalty application
3. Edge cases: missing regime, missing timestamps, boundary conditions
"""
import pytest

from apps.reference.domains.decision_making.shields.context_shield import ContextShield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_DEFAULT_MULTIPLIERS = {
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "HIGH_VOLATILITY": 0.3,
    "LOW_VOLATILITY": 0.7,
    "MEAN_REVERSION": 0.7,
    "UNCERTAIN": 0.5,
}

_4H_MS = 14_400_000  # 4 hours in ms


def _make_shield(**overrides):
    """Create a ContextShield with sensible defaults."""
    kwargs = dict(
        regime_multipliers=_DEFAULT_MULTIPLIERS,
        default_multiplier=1.0,
        no_regime_multiplier=0.5,
        ttl_ms=_4H_MS,
        stale_mult_normal=0.7,
        stale_mult_danger=0.35,
        danger_regimes=["HIGH_VOLATILITY"],
    )
    kwargs.update(overrides)
    return ContextShield(**kwargs)


def _features(regime=None, bar_close_ts=0, regime_ts_ms=0):
    """Build a minimal features dict."""
    f = {}
    if regime is not None:
        f["regime"] = regime
    if bar_close_ts:
        f["bar_close_ts"] = bar_close_ts
    if regime_ts_ms:
        f["regime_ts_ms"] = regime_ts_ms
    return f


# ---------------------------------------------------------------------------
# 1. REGIME-FIX-01: Correct UPPERCASE matching
# ---------------------------------------------------------------------------
class TestRegimeMultipliers:
    """Verify that UPPERCASE regime names from RegimeDetector match correctly."""

    def test_trend_up_full_pass(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000  # some timestamp in ms
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 1.0
        assert "TREND_UP" in r.reasons[0]

    def test_trend_down_full_pass(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_DOWN", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 1.0

    def test_high_volatility_attenuated(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "HIGH_VOLATILITY", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 0.3
        assert "HIGH_VOLATILITY" in r.reasons[0]

    def test_low_volatility(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "LOW_VOLATILITY", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 0.7

    def test_mean_reversion(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "MEAN_REVERSION", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 0.7

    def test_uncertain_regime(self):
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "UNCERTAIN", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 0.5

    def test_unknown_regime_uses_default(self):
        """A regime not in the multipliers dict falls back to default_multiplier."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        r = shield.evaluate("BTCUSDT", _features(
            "SOME_NEW_REGIME", now_ms, now_ms - 1000), 0.5, 1.0)
        assert r.multiplier == 1.0
        assert "default_mult" in r.reasons[0]


# ---------------------------------------------------------------------------
# 2. No regime / missing regime
# ---------------------------------------------------------------------------
class TestNoRegime:
    def test_no_regime_returns_no_regime_multiplier(self):
        shield = _make_shield()
        r = shield.evaluate("BTCUSDT", _features(), 0.5, 1.0)
        assert r.multiplier == 0.5
        assert "no_regime" in r.reasons[0]

    def test_none_regime_explicit(self):
        shield = _make_shield()
        f = {"regime": None}
        r = shield.evaluate("BTCUSDT", f, 0.5, 1.0)
        assert r.multiplier == 0.5


# ---------------------------------------------------------------------------
# 3. TTL-STALE-01: Stale regime detection
# ---------------------------------------------------------------------------
class TestTTLStalePolicy:
    def test_fresh_regime_not_penalized(self):
        """Regime within TTL should use normal multiplier."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        fresh_ts = now_ms - (_4H_MS - 1000)  # 1 second before TTL
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, fresh_ts), 0.5, 1.0)
        assert r.multiplier == 1.0  # normal TREND_UP multiplier
        assert "STALE" not in r.reasons[0]

    def test_stale_normal_regime(self):
        """Stale non-danger regime → stale_mult_normal (0.7)."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        stale_ts = now_ms - (_4H_MS + 1000)  # 1 second past TTL
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, stale_ts), 0.5, 1.0)
        assert r.multiplier == 0.7
        assert "STALE" in r.reasons[0]
        assert "danger=False" in r.reasons[0]

    def test_stale_danger_regime(self):
        """Stale danger regime → stale_mult_danger (0.35)."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        stale_ts = now_ms - (_4H_MS + 1000)
        r = shield.evaluate("BTCUSDT", _features(
            "HIGH_VOLATILITY", now_ms, stale_ts), 0.5, 1.0)
        assert r.multiplier == 0.35
        assert "STALE" in r.reasons[0]
        assert "danger=True" in r.reasons[0]

    def test_stale_exactly_at_boundary(self):
        """Exactly at TTL boundary → NOT stale (age_ms == ttl_ms, not >)."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        boundary_ts = now_ms - _4H_MS  # exactly at TTL
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, boundary_ts), 0.5, 1.0)
        assert r.multiplier == 1.0  # NOT stale (> not >=)

    def test_very_stale_regime_24h(self):
        """24h old regime → definitely stale."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        very_stale_ts = now_ms - (24 * 3_600_000)  # 24 hours old
        r = shield.evaluate("BTCUSDT", _features(
            "MEAN_REVERSION", now_ms, very_stale_ts), 0.5, 1.0)
        assert r.multiplier == 0.7
        assert "STALE" in r.reasons[0]
        assert "24.0h" in r.reasons[0]

    def test_custom_ttl(self):
        """Custom TTL of 1 hour."""
        shield = _make_shield(ttl_ms=3_600_000)  # 1 hour
        now_ms = 1_700_000_000_000
        ts_2h_old = now_ms - (2 * 3_600_000)
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, ts_2h_old), 0.5, 1.0)
        assert r.multiplier == 0.7
        assert "STALE" in r.reasons[0]

    def test_zero_ttl_disables_stale_penalty(self):
        """ttl_ms=0 disables the stale branch and falls back to regime lookup."""
        shield = _make_shield(ttl_ms=0)
        now_ms = 1_700_000_000_000
        ts_24h_old = now_ms - (24 * 3_600_000)
        r = shield.evaluate("BTCUSDT", _features(
            "TREND_UP", now_ms, ts_24h_old), 0.5, 1.0)
        assert r.multiplier == 1.0
        assert "STALE" not in r.reasons[0]


# ---------------------------------------------------------------------------
# 4. Edge cases: missing timestamps → skip TTL check
# ---------------------------------------------------------------------------
class TestMissingTimestamps:
    def test_missing_regime_ts_ms_skips_ttl(self):
        """No regime_ts_ms → skip TTL, use regime multiplier as-is."""
        shield = _make_shield()
        now_ms = 1_700_000_000_000
        f = {"regime": "TREND_UP", "bar_close_ts": now_ms}
        r = shield.evaluate("BTCUSDT", f, 0.5, 1.0)
        assert r.multiplier == 1.0
        assert "STALE" not in r.reasons[0]

    def test_missing_bar_close_ts_skips_ttl(self):
        """No bar_close_ts → skip TTL, use regime multiplier as-is."""
        shield = _make_shield()
        f = {"regime": "HIGH_VOLATILITY", "regime_ts_ms": 1_700_000_000_000}
        r = shield.evaluate("BTCUSDT", f, 0.5, 1.0)
        assert r.multiplier == 0.3  # normal HIGH_VOL multiplier
        assert "STALE" not in r.reasons[0]

    def test_zero_regime_ts_ms_skips_ttl(self):
        """regime_ts_ms=0 (warmup) → skip TTL."""
        shield = _make_shield()
        f = {"regime": "TREND_UP",
             "bar_close_ts": 1_700_000_000_000, "regime_ts_ms": 0}
        r = shield.evaluate("BTCUSDT", f, 0.5, 1.0)
        assert r.multiplier == 1.0


# ---------------------------------------------------------------------------
# 5. ShieldResult contract
# ---------------------------------------------------------------------------
class TestShieldResultContract:
    def test_shield_name(self):
        shield = _make_shield()
        r = shield.evaluate("BTCUSDT", _features("TREND_UP", 1, 1), 0.5, 1.0)
        assert r.shield_name == "ContextShield"

    def test_multiplier_clamped_to_0_1(self):
        """Even if config says >1, multiplier is clamped."""
        shield = _make_shield(regime_multipliers={"BAD": 5.0})
        f = {"regime": "BAD", "bar_close_ts": 1, "regime_ts_ms": 1}
        r = shield.evaluate("BTCUSDT", f, 0.5, 1.0)
        assert r.multiplier <= 1.0

    def test_reasons_is_list(self):
        shield = _make_shield()
        r = shield.evaluate("BTCUSDT", _features("TREND_UP", 1, 1), 0.5, 1.0)
        assert isinstance(r.reasons, list)
        assert len(r.reasons) >= 1
