from __future__ import annotations

from collections import deque
from decimal import Decimal

from apps.reference.domains.feature_engineering.price_motion import compute_price_motion_block


def test_price_motion_clip_pm_norm_to_extended_interval():
    """VOL-ADJ-GATES-01: pm_norm clips to [-10, 10] for Anti-FOMO detection."""
    hist = deque()
    t0 = 1_700_000_000_000

    compute_price_motion_block(hist, ts_ms=t0, price=Decimal("100"), k_vol=2.0)
    compute_price_motion_block(hist, ts_ms=t0 + 5_000, price=Decimal("100.1"), k_vol=2.0)
    compute_price_motion_block(hist, ts_ms=t0 + 9_000, price=Decimal("100.2"), k_vol=2.0)
    out = compute_price_motion_block(hist, ts_ms=t0 + 10_000, price=Decimal("102.0"), k_vol=2.0)

    assert out["ret_10s"] is not None
    assert abs(out["ret_10s"] - 0.02) < 1e-6
    assert out["vol_pct_10s"] is not None
    # Extreme spike clips to 10.0 (not 1.0) - enables Anti-FOMO gate
    assert out["pm_norm_10s"] == 10.0


def test_price_motion_insufficient_history_returns_none_for_long_windows():
    hist = deque()
    t0 = 1_700_000_000_000

    compute_price_motion_block(hist, ts_ms=t0, price=Decimal("100"), k_vol=2.0)
    out = compute_price_motion_block(hist, ts_ms=t0 + 12_000, price=Decimal("100.1"), k_vol=2.0)

    assert out["ret_10s"] is not None
    assert out["ret_60s"] is None
    assert out["ret_300s"] is None
    assert out["pm_norm_60s"] is None
    assert out["pm_norm_300s"] is None


def test_price_motion_vol_zero_yields_pm_norm_none():
    hist = deque()
    t0 = 1_700_000_000_000

    compute_price_motion_block(hist, ts_ms=t0, price=Decimal("100"), k_vol=2.0)
    compute_price_motion_block(hist, ts_ms=t0 + 5_000, price=Decimal("100"), k_vol=2.0)
    out = compute_price_motion_block(hist, ts_ms=t0 + 10_000, price=Decimal("100"), k_vol=2.0)

    assert out["ret_10s"] == 0.0
    assert out["vol_pct_10s"] is None
    assert out["pm_norm_10s"] is None


# =====================================================================
# Phase 2 Tests: 900s (15m) Window Support
# =====================================================================

def test_price_motion_900s_returns_finite_with_enough_history():
    """pm_norm_900s is finite when 15+ minutes of price history exists."""
    hist = deque()
    t0 = 1_700_000_000_000
    
    # Seed history: 1 tick every 30 seconds for 16 minutes (32 ticks)
    for i in range(32):
        ts = t0 + i * 30_000  # 30 second intervals
        # Simulate small price movements (+/- 0.1%)
        price = Decimal("100") + Decimal(str((i % 5) * 0.1 - 0.2))
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=2.0)
    
    # Final tick at t0 + 960_000 (16 minutes)
    out = compute_price_motion_block(hist, ts_ms=t0 + 960_000, price=Decimal("101.0"), k_vol=2.0)
    
    # 900s window should be available
    assert out.get("ret_900s") is not None, "ret_900s should be finite with 15+ min history"
    assert out.get("vol_pct_900s") is not None, "vol_pct_900s should be finite with 15+ min history"
    assert out.get("pm_norm_900s") is not None, "pm_norm_900s should be finite with 15+ min history"
    # VOL-ADJ-GATES-01: pm_norm clips to [-10, 10] for Anti-FOMO detection
    assert -10.0 <= out["pm_norm_900s"] <= 10.0


def test_price_motion_900s_returns_none_during_warmup():
    """pm_norm_900s is None when less than 15 minutes of history exists."""
    hist = deque()
    t0 = 1_700_000_000_000
    
    # Only 5 minutes of history (10 ticks at 30s intervals)
    for i in range(10):
        ts = t0 + i * 30_000
        price = Decimal("100") + Decimal(str(i * 0.01))
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=2.0)
    
    out = compute_price_motion_block(hist, ts_ms=t0 + 300_000, price=Decimal("100.5"), k_vol=2.0)
    
    # 300s should be available, 900s should NOT
    assert out.get("ret_300s") is not None, "ret_300s should be available at 5 min"
    assert out.get("pm_norm_300s") is not None, "pm_norm_300s should be available at 5 min"
    assert out.get("ret_900s") is None, "ret_900s should be None during warmup (< 15 min)"
    assert out.get("pm_norm_900s") is None, "pm_norm_900s should be None during warmup"


def test_price_motion_900s_key_always_present():
    """ret_900s, vol_pct_900s, pm_norm_900s keys exist even if None."""
    hist = deque()
    t0 = 1_700_000_000_000
    
    out = compute_price_motion_block(hist, ts_ms=t0, price=Decimal("100"), k_vol=2.0)
    
    # Keys must exist (may be None)
    assert "ret_900s" in out, "ret_900s key must always be present"
    assert "vol_pct_900s" in out, "vol_pct_900s key must always be present"
    assert "pm_norm_900s" in out, "pm_norm_900s key must always be present"


def test_pm_norm_can_exceed_1_for_extreme_impulse():
    """
    VOL-ADJ-GATES-01: Prove pm_norm_900s can be > 1 (or clip_max >= 4).
    
    Anti-FOMO gate requires |pm_norm| > 4.0 detection.
    Previously pm_norm was clipped to [-1, 1] - this test proves the fix.
    
    Scenario: Price spikes 10% in a low-volatility environment (vol ~ 0.1%).
    Expected: pm_norm = ret / (k_vol * vol) = 0.10 / (2.0 * 0.001) = 50 → clipped to 10
    """
    hist = deque()
    t0 = 1_700_000_000_000
    k_vol = 2.0
    
    # Build 15+ minutes of stable history with tiny volatility (~0.01% moves)
    # 1000 ticks at 1-second intervals = ~16 min of history
    for i in range(1000):
        ts = t0 + i * 1000
        # Tiny oscillation: 100.000 ± 0.01 (0.01% volatility)
        price = Decimal("100.0") + Decimal(str((i % 2) * 0.01))
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=k_vol)
    
    # Now: 900s ago price was ~100.0, current price ~100.0
    # Let's inject a SPIKE: price jumps to 110 (10% move)
    final_ts = t0 + 1000 * 1000  # 1000 seconds in
    spike_price = Decimal("110.0")  # 10% spike
    
    out = compute_price_motion_block(hist, ts_ms=final_ts, price=spike_price, k_vol=k_vol)
    
    pm_norm_900s = out.get("pm_norm_900s")
    
    # Assertions:
    assert pm_norm_900s is not None, "pm_norm_900s should be computed"
    assert pm_norm_900s > 1.0, f"pm_norm_900s={pm_norm_900s} must be > 1.0 for Anti-FOMO"
    assert pm_norm_900s >= 4.0, f"pm_norm_900s={pm_norm_900s} should reach >= 4.0 for extreme spike"
    assert pm_norm_900s <= 10.0, f"pm_norm_900s={pm_norm_900s} should be clipped to 10.0 max"


# =====================================================================
# VOL-ADJ-GATES-CLIP-CONFIG-01: Config-driven clip_abs Tests
# =====================================================================

def test_clip_abs_default_clips_to_10():
    """
    VOL-ADJ-GATES-CLIP-CONFIG-01: Default clip_abs=10.0.
    
    With default config, extreme impulse yields pm_norm > 4.0 but <= 10.0.
    """
    hist = deque()
    t0 = 1_700_000_000_000
    k_vol = 2.0
    
    # Build stable history with tiny volatility
    for i in range(1000):
        ts = t0 + i * 1000
        price = Decimal("100.0") + Decimal(str((i % 2) * 0.01))
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=k_vol)
    
    # 10% spike
    final_ts = t0 + 1000 * 1000
    out = compute_price_motion_block(
        hist,
        ts_ms=final_ts,
        price=Decimal("110.0"),
        k_vol=k_vol,
        # Default clip_abs=10.0 (not specified)
    )
    
    pm = out.get("pm_norm_900s")
    assert pm is not None
    assert pm > 4.0, f"pm_norm_900s={pm} should exceed Anti-FOMO threshold"
    assert pm == 10.0, f"pm_norm_900s={pm} should be clipped to default 10.0"


def test_clip_abs_override_clips_to_custom_value():
    """
    VOL-ADJ-GATES-CLIP-CONFIG-01: Override clip_abs=3.0.
    
    With clip_abs=3.0, the same extreme impulse should be clipped to 3.0.
    This proves config override affects runtime output.
    """
    hist = deque()
    t0 = 1_700_000_000_000
    k_vol = 2.0
    
    # Build stable history with tiny volatility
    for i in range(1000):
        ts = t0 + i * 1000
        price = Decimal("100.0") + Decimal(str((i % 2) * 0.01))
        # Build history with default clip (doesn't matter for history)
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=k_vol)
    
    # 10% spike with CUSTOM clip_abs=3.0
    final_ts = t0 + 1000 * 1000
    out = compute_price_motion_block(
        hist,
        ts_ms=final_ts,
        price=Decimal("110.0"),
        k_vol=k_vol,
        clip_abs=3.0,  # Override!
    )
    
    pm = out.get("pm_norm_900s")
    assert pm is not None
    assert abs(pm) <= 3.0, f"pm_norm_900s={pm} should be clipped to custom 3.0"
    assert pm == 3.0, f"pm_norm_900s={pm} should be exactly 3.0 (clipped)"


def test_clip_abs_negative_spike_clips_correctly():
    """
    VOL-ADJ-GATES-CLIP-CONFIG-01: Negative spike clips to -clip_abs.
    """
    hist = deque()
    t0 = 1_700_000_000_000
    k_vol = 2.0
    
    # Build stable history around 110.0
    for i in range(1000):
        ts = t0 + i * 1000
        price = Decimal("110.0") + Decimal(str((i % 2) * 0.01))
        compute_price_motion_block(hist, ts_ms=ts, price=price, k_vol=k_vol)
    
    # -10% crash with clip_abs=5.0
    final_ts = t0 + 1000 * 1000
    out = compute_price_motion_block(
        hist,
        ts_ms=final_ts,
        price=Decimal("99.0"),  # ~10% drop
        k_vol=k_vol,
        clip_abs=5.0,
    )
    
    pm = out.get("pm_norm_900s")
    assert pm is not None
    assert pm < 0, f"pm_norm_900s={pm} should be negative for crash"
    assert pm == -5.0, f"pm_norm_900s={pm} should be clipped to -5.0"