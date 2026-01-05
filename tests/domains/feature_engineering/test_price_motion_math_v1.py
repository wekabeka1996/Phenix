from __future__ import annotations

from collections import deque
from decimal import Decimal

from apps.reference.domains.feature_engineering.price_motion import compute_price_motion_block


def test_price_motion_clip_pm_norm_to_unit_interval():
    hist = deque()
    t0 = 1_700_000_000_000

    compute_price_motion_block(hist, ts_ms=t0, price=Decimal("100"), k_vol=2.0)
    compute_price_motion_block(hist, ts_ms=t0 + 5_000, price=Decimal("100.1"), k_vol=2.0)
    compute_price_motion_block(hist, ts_ms=t0 + 9_000, price=Decimal("100.2"), k_vol=2.0)
    out = compute_price_motion_block(hist, ts_ms=t0 + 10_000, price=Decimal("102.0"), k_vol=2.0)

    assert out["ret_10s"] is not None
    assert abs(out["ret_10s"] - 0.02) < 1e-6
    assert out["vol_pct_10s"] is not None
    assert out["pm_norm_10s"] == 1.0


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

