"""
Tests for ExposureGuard rejection metrics logging (NRR-011/012/013).
Focus: ensure metrics_logger.reject_count increments on hard rejects.
"""

from decimal import Decimal
import time

from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.metrics_aggregator import (
    metrics_logger,
)


def make_guard(config: dict | None = None) -> ExposureGuard:
    cfg = config or {}
    return ExposureGuard(cfg, fsm=None)


def reset_metrics():
    # Reset aggregator counters between tests
    metrics_logger.aggregator.reject_count = 0
    metrics_logger.aggregator.clip_count = 0
    metrics_logger.aggregator.events = []


def test_reject_metrics_margin_cap_nrr011():
    reset_metrics()
    guard = make_guard()

    # equity=1000 => margin_limit = 0.20 * 1000 = 200
    # open_positions_margin_usd=250 (>200) ensures allowed_extra <= 0 and hard path
    portfolio_state = {
        "equity_free_usdt": 1000,
        "open_positions_margin_usd": 250,
        "positions_last_ts_ms": int(time.time() * 1000),
        "positions_by_side": {"long_margin": 0, "short_margin": 0},
    }

    res = guard.can_open("ETHUSDT", Decimal("100"), portfolio_state)
    assert res["allowed"] is False
    # One reject event expected
    assert metrics_logger.aggregator.reject_count >= 1


def test_reject_metrics_side_cap_nrr012_sell_side():
    reset_metrics()
    guard = make_guard()

    # equity=1000 => side_limit(short)=0.12*1000=120
    # short_margin already 130 (>120), default order_side=SELL => reject
    portfolio_state = {
        "equity_free_usdt": 1000,
        "open_positions_margin_usd": 0,
        "positions_last_ts_ms": int(time.time() * 1000),
        "positions_by_side": {"long_margin": 0, "short_margin": 130},
    }

    res = guard.can_open("ETHUSDT", Decimal("100"), portfolio_state)
    assert res["allowed"] is False
    assert metrics_logger.aggregator.reject_count >= 1


def test_reject_metrics_directional_ratio_nrr013():
    reset_metrics()
    guard = make_guard()

    # Strong imbalance: long=500, short=10 => ratio=50 (>2.0)
    portfolio_state = {
        "equity_free_usdt": 1000,
        "open_positions_margin_usd": 0,
        "positions_last_ts_ms": int(time.time() * 1000),
        "positions_by_side": {"long_margin": 500, "short_margin": 10},
    }

    res = guard.can_open("ETHUSDT", Decimal("100"), portfolio_state)
    assert res["allowed"] is False
    assert metrics_logger.aggregator.reject_count >= 1
