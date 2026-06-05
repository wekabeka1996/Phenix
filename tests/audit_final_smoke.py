"""
FINAL audit smoke tests (math/logic integrity).

These tests are intentionally narrow and integration-oriented: they exercise the
current production implementations to detect "silent killer" failure modes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.reference.domains.feature_engineering.indicators import compute_bollinger_bands
from apps.reference.domains.feature_engineering.price_motion import (
    compute_price_motion_block,
    update_price_history,
)
from apps.reference.domains.risk_management.daily_gate import DailyRiskState


@dataclass
class _MockTrading:
    risk: dict


@dataclass
class _MockConfig:
    trading: _MockTrading


def _mock_daily_gate_config(*, max_drawdown_pct: float = 10.0) -> _MockConfig:
    return _MockConfig(
        trading=_MockTrading(
            risk={
                "daily": {
                    "enabled": True,
                    "max_drawdown_pct": max_drawdown_pct,
                    "reset_time_utc": "00:00",
                }
            }
        )
    )


def test_daily_gate_amnesia_restart_resets_equity_open__audit():
    """
    Hypothesis: restarting DailyGate resets the daily equity-open anchor, allowing infinite losses.

    Expected-safe behavior: on restart within the same trading day, the component must
    NOT silently re-anchor equity_open to the current (already-drawn-down) equity.
    """
    now = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    cfg = _mock_daily_gate_config(max_drawdown_pct=10.0)

    gate = DailyRiskState(cfg)
    gate.on_portfolio({"equity_free_usdt": "1000"}, now=now)
    gate.on_portfolio({"equity_free_usdt": "960"}, now=now)  # -$40 (4% drawdown)

    allowed, _reason = gate.can_open()
    assert allowed is True  # sanity: 4% drawdown under 10% limit should allow opens

    restarted = DailyRiskState(cfg)
    restarted.on_portfolio({"equity_free_usdt": "960"}, now=now)

    assert restarted._equity_open == Decimal("1000"), (
        "Daily gate appears to re-anchor equity_open on restart (amnesia). "
        f"Observed equity_open={restarted._equity_open} expected=1000."
    )


def test_price_motion_infinity_low_volatility_is_clipped__audit():
    """
    Hypothesis: extremely low (but non-zero) volatility causes division spikes in pm_norm.

    Expected-safe behavior: pm_norm is clipped to a sane bound (here: +/-1.0).
    """
    history = deque()
    base_ts_ms = 1_700_000_000_000  # already-ms epoch

    # Build a 10s window where realized vol is ~1e-9 (tiny), but net return is +1%.
    # Many tiny moves + one big jump makes median(|ret|) tiny.
    start_price = Decimal("100")
    tiny_step = Decimal("0.0000001")  # 1e-7 => ~1e-9 fractional return at ~100
    for i in range(0, 100):
        update_price_history(
            history,
            ts_ms=base_ts_ms + i * 100,
            price=start_price + (tiny_step * Decimal(i)),
            max_window_ms=20_000,
        )

    out = compute_price_motion_block(
        history,
        ts_ms=base_ts_ms + 10_000,
        price=Decimal("101"),  # +1% net move from ~100 at start
        k_vol=1.0,
        windows_sec=(10,),
        clip_abs=1.0,
    )

    pm = out["pm_norm_10s"]
    assert pm is not None, "Expected non-None pm_norm_10s for non-zero volatility."
    assert pm == pytest.approx(1.0, abs=1e-12), f"Expected clipping to 1.0, got {pm!r}."


def test_bollinger_bands_do_not_repaint_from_current_price__audit():
    """
    Hypothesis: passing current_price changes the bands intra-bar (repainting / signal flicker).

    Expected-safe behavior: current_price may affect %B, but must not affect the band levels.
    """
    closes = [Decimal("100"), Decimal("100"), Decimal("100")]

    bb_spike = compute_bollinger_bands(closes, window=3, num_std=2.0, current_price=Decimal("110"))
    bb_retrace = compute_bollinger_bands(closes, window=3, num_std=2.0, current_price=Decimal("100"))

    assert bb_spike is not None and bb_retrace is not None
    assert bb_spike.upper == bb_retrace.upper, (
        "Upper band changed when only current_price changed; indicator appears to repaint."
    )
