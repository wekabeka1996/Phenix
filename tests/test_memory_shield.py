"""
Unit tests for MemoryShield — State-Familiarity Attenuation.

Tests cover:
1. evaluate() is read-only (no side effects on counters)
2. record_visit() idempotent per (state_hash, bar_ts)
3. Exponential decay
4. LRU eviction
5. Familiarity tiers: UNKNOWN/EXPLORING/KNOWN
"""
import pytest
from unittest.mock import patch

from apps.reference.domains.decision_making.shields.memory_shield import (
    MemoryShield,
    _regime_bucket,
    _vol_bucket_atr_pct,
    _strength_bucket,
    _quality_bucket,
    _StateEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_ms(**kw):
    defaults = dict(
        decay_rate=0.95,
        max_states=200,
        unknown_threshold=10.0,
        exploring_threshold=50.0,
        unknown_multiplier=0.6,
        exploring_multiplier=0.8,
        known_multiplier=1.0,
    )
    defaults.update(kw)
    return MemoryShield(**defaults)


def _features(
    regime="TREND_UP",
    atr_pct=0.003,
    pillar_operator=0.5,
    pillar_strategist=0.6,
    bar_close_ts=1_700_000_000,
):
    f = {"regime": regime, "pillar_operator": pillar_operator, "pillar_strategist": pillar_strategist}
    if atr_pct is not None:
        f["volatility"] = {"atr_pct": atr_pct}
    if bar_close_ts is not None:
        f["bar_close_ts"] = bar_close_ts
    return f


# ---------------------------------------------------------------------------
# 1. Bucket helpers
# ---------------------------------------------------------------------------
class TestBucketHelpers:
    def test_regime_bucket_up(self):
        assert _regime_bucket("TREND_UP") == "UP"

    def test_regime_bucket_down(self):
        assert _regime_bucket("TREND_DOWN") == "DOWN"

    def test_regime_bucket_flat(self):
        assert _regime_bucket("HIGH_VOLATILITY") == "FLAT"

    def test_regime_bucket_none(self):
        assert _regime_bucket(None) == "FLAT"

    def test_vol_bucket_low(self):
        assert _vol_bucket_atr_pct(0.001) == "LOW"

    def test_vol_bucket_norm(self):
        assert _vol_bucket_atr_pct(0.003) == "NORM"

    def test_vol_bucket_high(self):
        assert _vol_bucket_atr_pct(0.01) == "HIGH"

    def test_strength_weak(self):
        assert _strength_bucket(0.1) == "WEAK"

    def test_strength_mid(self):
        assert _strength_bucket(0.5) == "MID"

    def test_strength_strong(self):
        assert _strength_bucket(0.8) == "STRONG"

    def test_quality_clean(self):
        assert _quality_bucket(0.6) == "CLEAN"

    def test_quality_dirty(self):
        assert _quality_bucket(0.3) == "DIRTY"


# ---------------------------------------------------------------------------
# 2. evaluate() is read-only
# ---------------------------------------------------------------------------
class TestEvaluateReadOnly:
    def test_evaluate_does_not_change_state_count(self):
        ms = _make_ms()
        assert ms.state_count() == 0
        ms.evaluate("BTC", _features(), 0.5, 1.0)
        ms.evaluate("BTC", _features(), 0.5, 1.0)
        # evaluate() should NOT add states
        assert ms.state_count() == 0

    def test_evaluate_unknown_without_visits(self):
        ms = _make_ms()
        r = ms.evaluate("BTC", _features(), 0.5, 1.0)
        assert r.multiplier == 0.6
        assert "UNKNOWN" in r.reasons[0]


# ---------------------------------------------------------------------------
# 3. record_visit() idempotent
# ---------------------------------------------------------------------------
class TestRecordVisitIdempotent:
    def test_double_record_same_bar(self):
        ms = _make_ms()
        f = _features(bar_close_ts=1000)
        ms.record_visit("BTC", f, bar_close_ts=1000, state_hash="A|B|C|D")
        ms.record_visit("BTC", f, bar_close_ts=1000, state_hash="A|B|C|D")
        # Should only count once
        ev = ms.get_effective_visits("A|B|C|D", now_ts=1000)
        assert ev == pytest.approx(1.0, abs=0.01)

    def test_different_bars_count_separately(self):
        ms = _make_ms()
        ms.record_visit("BTC", {}, bar_close_ts=1000, state_hash="A|B|C|D")
        ms.record_visit("BTC", {}, bar_close_ts=1001, state_hash="A|B|C|D")
        ev = ms.get_effective_visits("A|B|C|D", now_ts=1001)
        assert ev > 1.5  # ~2 with minimal decay


# ---------------------------------------------------------------------------
# 4. Familiarity tiers
# ---------------------------------------------------------------------------
class TestFamiliarityTiers:
    def test_unknown_tier(self):
        ms = _make_ms(unknown_threshold=10)
        # 0 visits → UNKNOWN
        r = ms.evaluate("BTC", _features(), 0.5, 1.0)
        assert r.multiplier == 0.6

    def test_exploring_tier(self):
        ms = _make_ms(unknown_threshold=2, exploring_threshold=20)
        # Record 5 visits at ts close to evaluate's ts → EXPLORING (2 < 5 < 20)
        for i in range(5):
            ms.record_visit("BTC", {}, bar_close_ts=1_700_000_000 + i, state_hash="UP|NORM|MID|CLEAN")
        r = ms.evaluate("BTC", _features(bar_close_ts=1_700_000_005), 0.5, 1.0)
        assert r.multiplier == 0.8
        assert "EXPLORING" in r.reasons[0]

    def test_known_tier(self):
        ms = _make_ms(unknown_threshold=2, exploring_threshold=5)
        # Record 10 visits → KNOWN (> 5)
        for i in range(10):
            ms.record_visit("BTC", {}, bar_close_ts=1_700_000_000 + i, state_hash="UP|NORM|MID|CLEAN")
        r = ms.evaluate("BTC", _features(bar_close_ts=1_700_000_010), 0.5, 1.0)
        assert r.multiplier == 1.0
        assert "KNOWN" in r.reasons[0]


# ---------------------------------------------------------------------------
# 5. Exponential decay
# ---------------------------------------------------------------------------
class TestDecay:
    def test_decay_reduces_visits(self):
        entry = _StateEntry(visits=100.0, last_ts=1000)
        # 1 day later, decay_rate=0.95
        ev = entry.effective(1000 + 86400, 0.95)
        assert 94 < ev < 96  # ~95

    def test_severe_decay_after_10_days(self):
        entry = _StateEntry(visits=100.0, last_ts=1000)
        ev = entry.effective(1000 + 86400 * 10, 0.95)
        assert ev < 70  # 0.95^10 ≈ 0.60


# ---------------------------------------------------------------------------
# 6. LRU eviction
# ---------------------------------------------------------------------------
class TestLRU:
    def test_eviction_at_capacity(self):
        ms = _make_ms(max_states=3)
        for i in range(5):
            ms.record_visit("BTC", {}, bar_close_ts=1000 + i, state_hash=f"S{i}")
        # Only 3 most recent should remain
        assert ms.state_count() == 3
        assert ms.get_effective_visits("S0", now_ts=1005) == 0.0
        assert ms.get_effective_visits("S1", now_ts=1005) == 0.0
        assert ms.get_effective_visits("S2", now_ts=1005) > 0
        assert ms.get_effective_visits("S4", now_ts=1005) > 0


# ---------------------------------------------------------------------------
# 7. Missing features
# ---------------------------------------------------------------------------
class TestMissingFeatures:
    def test_missing_regime(self):
        ms = _make_ms()
        f = {"pillar_operator": 0.5, "pillar_strategist": 0.6,
             "volatility": {"atr_pct": 0.003}, "bar_close_ts": 1000}
        r = ms.evaluate("BTC", f, 0.5, 1.0)
        # Missing regime → MISSING_FEATURES path
        assert r.multiplier == 0.6
        assert "MISSING" in r.reasons[0] or "UNKNOWN" in r.reasons[0]

    def test_all_features_present(self):
        ms = _make_ms()
        r = ms.evaluate("BTC", _features(), 0.5, 1.0)
        assert r.shield_name == "MEMORY"


# ---------------------------------------------------------------------------
# 8. State hash in details
# ---------------------------------------------------------------------------
class TestStateHashInDetails:
    def test_details_contain_hash(self):
        ms = _make_ms()
        r = ms.evaluate("BTC", _features(), 0.5, 1.0)
        assert "memory_state_hash" in r.details
