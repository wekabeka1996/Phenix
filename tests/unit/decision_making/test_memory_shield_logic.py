"""
Unit tests for MemoryShield — Doctrine v2.6, S2-R1.

Tests:
  A) Hash stability (real FE feature keys)
  B) Decay math (via explicit record_visit)
  C) Multiplier thresholds (via explicit record_visit)
  D) BaseShield protocol compliance
  E) Backtest mode — no filesystem I/O
  F) LRU eviction
  G) Idempotent record_visit (dedup per bar)
  H) Persistence throttling
  I) Pure-read evaluate() — no side effects
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from unittest import mock

import pytest

from apps.reference.domains.decision_making.shields.base import ShieldResult
from apps.reference.domains.decision_making.shields.memory_shield import (
    MemoryShield,
    _regime_bucket,
    _vol_bucket_atr_pct,
    _vol_bucket_state,
    _strength_bucket,
    _quality_bucket,
)

# ---------------------------------------------------------------------------
# Fixtures — uses REAL FE feature keys
# ---------------------------------------------------------------------------
_FULL = {
    "regime": "TREND_UP",
    "volatility": {"atr_pct": 0.003, "atr_14": 150.0, "atr_ready": True},
    "volatility_state": "0.5",
    "pillar_operator": 0.5,
    "pillar_strategist": 0.6,
    "bar_close_ts": 1_700_000_000,
}


def _ts(days_ago: int = 0, base: int = 1_700_000_000) -> int:
    """Return a UNIX timestamp (seconds) *days_ago* before *base*."""
    return base - days_ago * 86400


# =========================================================================
# A) Hash stability (real FE keys)
# =========================================================================
class TestHashStability:
    def test_same_inputs_same_hash(self):
        h1, m1 = MemoryShield._get_state_hash(_FULL)
        h2, m2 = MemoryShield._get_state_hash(dict(_FULL))
        assert h1 == h2
        assert m1 == [] and m2 == []

    def test_different_regime_different_hash(self):
        h_up, _ = MemoryShield._get_state_hash(dict(_FULL, regime="TREND_UP"))
        h_dn, _ = MemoryShield._get_state_hash(dict(_FULL, regime="TREND_DOWN"))
        assert h_up != h_dn

    def test_vol_bucket_from_atr_pct(self):
        """Uses features['volatility']['atr_pct'] for vol bucket."""
        low = dict(_FULL, volatility={"atr_pct": 0.001})
        norm = dict(_FULL, volatility={"atr_pct": 0.003})
        high = dict(_FULL, volatility={"atr_pct": 0.006})
        h_low, _ = MemoryShield._get_state_hash(low)
        h_norm, _ = MemoryShield._get_state_hash(norm)
        h_high, _ = MemoryShield._get_state_hash(high)
        assert "LOW" in h_low
        assert "NORM" in h_norm
        assert "HIGH" in h_high
        assert h_low != h_norm != h_high

    def test_vol_fallback_to_volatility_state(self):
        """If atr_pct missing, falls back to volatility_state."""
        features = dict(_FULL, volatility={"atr_pct": None}, volatility_state="0.8")
        h, missing = MemoryShield._get_state_hash(features)
        assert "HIGH" in h
        assert "volatility" not in missing

    def test_strength_from_pillar_operator(self):
        weak = dict(_FULL, pillar_operator=0.1)
        mid = dict(_FULL, pillar_operator=0.5)
        strong = dict(_FULL, pillar_operator=0.8)
        h_w, _ = MemoryShield._get_state_hash(weak)
        h_m, _ = MemoryShield._get_state_hash(mid)
        h_s, _ = MemoryShield._get_state_hash(strong)
        assert "WEAK" in h_w
        assert "MID" in h_m
        assert "STRONG" in h_s

    def test_quality_from_pillar_strategist(self):
        dirty = dict(_FULL, pillar_strategist=0.2)
        clean = dict(_FULL, pillar_strategist=0.7)
        h_d, _ = MemoryShield._get_state_hash(dirty)
        h_c, _ = MemoryShield._get_state_hash(clean)
        assert "DIRTY" in h_d
        assert "CLEAN" in h_c

    def test_regime_bucket_values(self):
        assert _regime_bucket("TREND_UP") == "UP"
        assert _regime_bucket("TREND_DOWN") == "DOWN"
        assert _regime_bucket("RANGING") == "FLAT"
        assert _regime_bucket(None) == "FLAT"

    def test_missing_features_returns_unknown_hash(self):
        h, missing = MemoryShield._get_state_hash({})
        assert "UNKNOWN" in h
        assert len(missing) >= 3

    def test_hash_format_pipe_separated(self):
        h, _ = MemoryShield._get_state_hash(_FULL)
        parts = h.split("|")
        assert len(parts) == 4

    def test_no_missing_with_full_fe_features(self):
        """With real FE keys present, missing list should be empty."""
        _, missing = MemoryShield._get_state_hash(_FULL)
        assert missing == []


# =========================================================================
# B) Decay math  (evaluate is pure-read → record_visit for write)
# =========================================================================
class TestDecayMath:
    def test_single_visit_no_decay(self):
        shield = MemoryShield(decay_rate=0.95)
        now = _ts(0)
        features = dict(_FULL, bar_close_ts=now)
        shield.record_visit("BTC", features)
        h, _ = MemoryShield._get_state_hash(features)
        ev = shield.get_effective_visits(h, now)
        assert ev == pytest.approx(1.0, abs=1e-6)

    def test_decay_after_30_days(self):
        shield = MemoryShield(decay_rate=0.95)
        base = 1_700_000_000
        ts_30_ago = base - 30 * 86400
        ts_now = base

        shield.record_visit("BTC", dict(_FULL, bar_close_ts=ts_30_ago))
        shield.record_visit("BTC", dict(_FULL, bar_close_ts=ts_now))

        h, _ = MemoryShield._get_state_hash(_FULL)
        ev = shield.get_effective_visits(h, ts_now)
        expected = 1.0 + 0.95 ** 30
        assert ev == pytest.approx(expected, abs=0.01)

    def test_decay_rate_respected(self):
        base = 1_700_000_000
        ts0 = base - 10 * 86400
        ts1 = base

        for rate in (0.90, 0.95, 0.99):
            shield = MemoryShield(decay_rate=rate)
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=ts0))
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=ts1))
            h, _ = MemoryShield._get_state_hash(_FULL)
            ev = shield.get_effective_visits(h, ts1)
            expected = 1.0 + rate ** 10
            assert ev == pytest.approx(expected, abs=0.01), f"rate={rate}"


# =========================================================================
# C) Multiplier thresholds (record first, then evaluate to read)
# =========================================================================
class TestMultiplierThresholds:
    def test_below_unknown_threshold(self):
        shield = MemoryShield(unknown_threshold=10, exploring_threshold=50)
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert result.multiplier == pytest.approx(0.6)
        assert "UNKNOWN" in result.reasons[0]

    def test_at_unknown_threshold_transitions(self):
        shield = MemoryShield(unknown_threshold=3, exploring_threshold=50)
        base = 1_700_000_000
        for i in range(4):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i))
        result = shield.evaluate("BTC", dict(_FULL, bar_close_ts=base + 4), 0.5, 0.25)
        assert result.multiplier == pytest.approx(0.8)
        assert "EXPLORING" in result.reasons[0]

    def test_at_exploring_threshold_transitions(self):
        shield = MemoryShield(unknown_threshold=2, exploring_threshold=5)
        base = 1_700_000_000
        for i in range(6):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i))
        result = shield.evaluate("BTC", dict(_FULL, bar_close_ts=base + 6), 0.5, 0.25)
        assert result.multiplier == pytest.approx(1.0)
        assert "KNOWN" in result.reasons[0]

    def test_custom_multiplier_values(self):
        shield = MemoryShield(
            unknown_multiplier=0.3,
            exploring_multiplier=0.7,
            known_multiplier=0.95,
            unknown_threshold=2,
            exploring_threshold=4,
        )
        base = 1_700_000_000
        r1 = shield.evaluate("BTC", dict(_FULL, bar_close_ts=base), 0.5, 0.25)
        assert r1.multiplier == pytest.approx(0.3)

        # 3 visits → ev >= 2 → EXPLORING
        for i in range(3):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i))
        r2 = shield.evaluate("BTC", dict(_FULL, bar_close_ts=base + 3), 0.5, 0.25)
        assert r2.multiplier == pytest.approx(0.7)

        # 5 visits total → ev >= 4 → KNOWN
        for i in range(3, 6):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i))
        r3 = shield.evaluate("BTC", dict(_FULL, bar_close_ts=base + 6), 0.5, 0.25)
        assert r3.multiplier == pytest.approx(0.95)


# =========================================================================
# D) Protocol compliance
# =========================================================================
class TestProtocol:
    def test_returns_shield_result(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert isinstance(result, ShieldResult)

    def test_multiplier_clamped_0_1(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert 0.0 <= result.multiplier <= 1.0

    def test_callable_protocol(self):
        shield = MemoryShield()
        mult, reasons = shield("BTC", _FULL, 0.5, 0.25)
        assert isinstance(mult, float)
        assert isinstance(reasons, list)
        assert 0.0 <= mult <= 1.0

    def test_name_property(self):
        assert MemoryShield().name == "MEMORY"

    def test_missing_features_still_returns_valid(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", {}, 0.5, 0.25)
        assert isinstance(result, ShieldResult)
        assert 0.0 <= result.multiplier <= 1.0
        assert "MISSING_FEATURES" in result.reasons[0]

    def test_shield_name_in_result(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert result.shield_name == "MEMORY"

    def test_details_contains_state_hash(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert "memory_state_hash" in result.details

    def test_missing_features_details_contains_keys(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", {}, 0.5, 0.25)
        assert "missing_keys" in result.details
        assert len(result.details["missing_keys"]) >= 3


# =========================================================================
# E) Backtest mode — no filesystem I/O
# =========================================================================
class TestBacktestNoIO:
    def test_no_storage_path_no_file(self, tmp_path):
        """Default (no storage_path) → RAM-only, no file created."""
        shield = MemoryShield()
        for _ in range(20):
            shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert shield._storage_path is None

    def test_default_is_ram_only(self):
        shield = MemoryShield()
        assert shield._storage_path is None

    def test_live_mode_persists(self, tmp_path):
        path = str(tmp_path / "memory_state.json")
        shield = MemoryShield(storage_path=path, flush_interval_sec=1.0)
        # Force immediate flush for testing
        shield._last_flush_wall = 0.0
        shield.record_visit("BTC", _FULL)
        shield.flush()
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert len(data) >= 1

    def test_live_mode_reload(self, tmp_path):
        path = str(tmp_path / "memory_state.json")
        ts = 1_700_000_000
        features = dict(_FULL, bar_close_ts=ts)

        s1 = MemoryShield(storage_path=path, flush_interval_sec=1.0)
        s1._last_flush_wall = 0.0
        for i in range(5):
            s1.record_visit("BTC", dict(features, bar_close_ts=ts + i))
        s1.flush()

        s2 = MemoryShield(storage_path=path)
        h, _ = MemoryShield._get_state_hash(features)
        ev = s2.get_effective_visits(h, ts + 4)
        assert ev == pytest.approx(5.0, abs=0.1)


# =========================================================================
# F) LRU eviction
# =========================================================================
class TestLRUEviction:
    def test_max_states_enforced(self):
        shield = MemoryShield(max_states=3)
        base = 1_700_000_000
        for i in range(5):
            features = dict(_FULL, regime=f"REGIME_{i}", bar_close_ts=base + i)
            shield.record_visit("BTC", features)
        assert shield.state_count() <= 3

    def test_oldest_evicted_first(self):
        shield = MemoryShield(max_states=2)
        base = 1_700_000_000
        f1 = dict(_FULL, regime="TREND_UP", bar_close_ts=base)
        f2 = dict(_FULL, regime="TREND_DOWN", bar_close_ts=base + 1)
        f3 = dict(_FULL, regime="RANGING", bar_close_ts=base + 2)
        shield.record_visit("BTC", f1)
        shield.record_visit("BTC", f2)
        shield.record_visit("BTC", f3)
        h1, _ = MemoryShield._get_state_hash(f1)
        assert shield.get_effective_visits(h1) == 0.0


# =========================================================================
# G) Idempotent record_visit (dedup per bar)
# =========================================================================
class TestIdempotentVisits:
    def test_repeated_record_same_bar_no_inflation(self):
        """Multiple record_visit() calls with same bar_close_ts → only 1 visit."""
        shield = MemoryShield(decay_rate=0.95)
        ts = 1_700_000_000
        features = dict(_FULL, bar_close_ts=ts)
        for _ in range(5):
            shield.record_visit("BTC", features)
        h, _ = MemoryShield._get_state_hash(features)
        ev = shield.get_effective_visits(h, ts)
        assert ev == pytest.approx(1.0, abs=1e-6), "Should be 1 visit despite 5 calls"

    def test_different_bars_accumulate(self):
        """Different bar_close_ts → each counts as separate visit."""
        shield = MemoryShield(decay_rate=0.95)
        base = 1_700_000_000
        for i in range(5):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i * 300))
        h, _ = MemoryShield._get_state_hash(_FULL)
        ev = shield.get_effective_visits(h, base + 4 * 300)
        assert ev == pytest.approx(5.0, abs=0.1), "5 different bars = 5 visits"

    def test_same_bar_different_state_hash(self):
        """Same bar_close_ts but different state → separate visits."""
        shield = MemoryShield(decay_rate=0.95)
        ts = 1_700_000_000
        f_up = dict(_FULL, regime="TREND_UP", bar_close_ts=ts)
        f_dn = dict(_FULL, regime="TREND_DOWN", bar_close_ts=ts)
        shield.record_visit("BTC", f_up)
        shield.record_visit("BTC", f_dn)
        h_up, _ = MemoryShield._get_state_hash(f_up)
        h_dn, _ = MemoryShield._get_state_hash(f_dn)
        assert shield.get_effective_visits(h_up, ts) == pytest.approx(1.0)
        assert shield.get_effective_visits(h_dn, ts) == pytest.approx(1.0)

    def test_dedup_set_bounded(self):
        """Dedup set doesn't grow unbounded — older entries are evicted."""
        shield = MemoryShield(decay_rate=0.99)
        base = 1_700_000_000
        for i in range(600):
            shield.record_visit("BTC", dict(_FULL, bar_close_ts=base + i * 300))
        assert len(shield._seen_keys) <= 512 + 1


# =========================================================================
# H) Persistence throttling
# =========================================================================
class TestPersistenceThrottling:
    def test_no_immediate_flush(self, tmp_path):
        """With flush_interval_sec=60, first record_visit doesn't write to disk."""
        path = str(tmp_path / "memory_state.json")
        shield = MemoryShield(storage_path=path, flush_interval_sec=60.0)
        shield.record_visit("BTC", _FULL)
        assert not os.path.exists(path)

    def test_flush_after_interval(self, tmp_path):
        """After flush interval elapses, save happens."""
        path = str(tmp_path / "memory_state.json")
        shield = MemoryShield(storage_path=path, flush_interval_sec=1.0)
        shield.record_visit("BTC", _FULL)
        shield._last_flush_wall = time.monotonic() - 2.0
        shield.record_visit("BTC", dict(_FULL, bar_close_ts=1_700_000_001))
        assert os.path.exists(path)

    def test_explicit_flush_works(self, tmp_path):
        """shield.flush() forces immediate save regardless of interval."""
        path = str(tmp_path / "memory_state.json")
        shield = MemoryShield(storage_path=path, flush_interval_sec=9999.0)
        shield.record_visit("BTC", _FULL)
        assert not os.path.exists(path)
        shield.flush()
        assert os.path.exists(path)


# =========================================================================
# I) Pure-read evaluate() — no side effects  (S2-R1)
# =========================================================================
class TestPureReadEvaluate:
    def test_evaluate_does_not_record_visit(self):
        """evaluate() alone never creates state entries."""
        shield = MemoryShield()
        for _ in range(10):
            shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert shield.state_count() == 0

    def test_evaluate_does_not_dirty_storage(self, tmp_path):
        """evaluate() never marks storage dirty."""
        path = str(tmp_path / "memory_state.json")
        shield = MemoryShield(storage_path=path, flush_interval_sec=1.0)
        shield._last_flush_wall = 0.0  # force next write to succeed if dirty
        shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert not shield._dirty
        assert not os.path.exists(path)

    def test_evaluate_missing_features_no_side_effects(self):
        """Missing features path also never records."""
        shield = MemoryShield()
        for _ in range(10):
            shield.evaluate("BTC", {}, 0.5, 0.25)
        assert shield.state_count() == 0
        assert not shield._dirty

    def test_evaluate_then_record_produces_visit(self):
        """Verify the intended workflow: evaluate() → record_visit()."""
        shield = MemoryShield()
        ts = 1_700_000_000
        features = dict(_FULL, bar_close_ts=ts)
        result = shield.evaluate("BTC", features, 0.5, 0.25)
        assert result.multiplier == pytest.approx(0.6)  # UNKNOWN

        # Now explicitly record
        shield.record_visit("BTC", features)
        h, _ = MemoryShield._get_state_hash(features)
        assert shield.get_effective_visits(h, ts) == pytest.approx(1.0)

    def test_evaluate_idempotent_on_repeated_calls(self):
        """Calling evaluate() 100 times returns same result (no state drift)."""
        shield = MemoryShield()
        results = [
            shield.evaluate("BTC", _FULL, 0.5, 0.25).multiplier
            for _ in range(100)
        ]
        assert all(m == results[0] for m in results)
