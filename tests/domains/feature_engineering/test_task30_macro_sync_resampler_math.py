import random

import pytest

from apps.reference.domains.feature_engineering.macro_sync_resampler import MacroSyncResampler


def _build_resampler() -> MacroSyncResampler:
    return MacroSyncResampler(
        bin_ms=1000,
        window_bins=60,
        min_bins=20,
        ttl_ms=60_000,
        max_gap_bins=2,
        eps=1e-12,
    )


def test_macro_sync_high_corr_with_async_ticks_after_timegrid():
    r = random.Random(1337)
    resampler = _build_resampler()

    symbol = "SOLUSDT"
    anchor = "BTCUSDT"

    p_sym = 100.0
    p_anc = 200.0
    start_ts = 1_700_000_000_000

    for i in range(120):
        bin_ts = start_ts + i * 1000
        base_ret = r.gauss(0.0, 0.001)
        noise = r.gauss(0.0, 0.0001)

        p_sym *= (2.718281828459045 ** base_ret)
        p_anc *= (2.718281828459045 ** (base_ret + noise))

        ts_sym = bin_ts + r.randint(0, 900)
        ts_anc = bin_ts + r.randint(0, 900)

        resampler.update_symbol(symbol, ts_ms=ts_sym, price=p_sym)
        resampler.update_anchor(anchor, ts_ms=ts_anc, price=p_anc)

    result = resampler.compute(symbol, anchors=[anchor], now_ts_ms=start_ts + 119 * 1000)
    assert result.ready is True
    assert result.why is None
    assert result.phi > 0.75


def test_macro_sync_uncorrelated_series_phi_near_neutral():
    r = random.Random(42)
    resampler = _build_resampler()

    symbol = "SOLUSDT"
    anchor = "BTCUSDT"

    p_sym = 100.0
    p_anc = 200.0
    start_ts = 1_700_000_000_000

    for i in range(120):
        bin_ts = start_ts + i * 1000
        ret_sym = r.gauss(0.0, 0.001)
        ret_anc = r.gauss(0.0, 0.001)

        p_sym *= (2.718281828459045 ** ret_sym)
        p_anc *= (2.718281828459045 ** ret_anc)

        resampler.update_symbol(symbol, ts_ms=bin_ts + 10, price=p_sym)
        resampler.update_anchor(anchor, ts_ms=bin_ts + 20, price=p_anc)

    result = resampler.compute(symbol, anchors=[anchor], now_ts_ms=start_ts + 119 * 1000)
    assert result.ready is True
    assert 0.4 < result.phi < 0.6


def test_macro_sync_not_ready_on_insufficient_bins():
    resampler = _build_resampler()

    symbol = "SOLUSDT"
    anchor = "BTCUSDT"
    start_ts = 1_700_000_000_000

    p_sym = 100.0
    p_anc = 200.0
    for i in range(10):  # < min_bins
        bin_ts = start_ts + i * 1000
        p_sym *= 1.0001
        p_anc *= 1.0001
        resampler.update_symbol(symbol, ts_ms=bin_ts + 1, price=p_sym)
        resampler.update_anchor(anchor, ts_ms=bin_ts + 2, price=p_anc)

    result = resampler.compute(symbol, anchors=[anchor], now_ts_ms=start_ts + 9 * 1000)
    assert result.ready is False
    assert result.why == "insufficient_bins"


def test_macro_sync_drops_out_of_order_and_sets_reason():
    resampler = _build_resampler()

    symbol = "SOLUSDT"
    anchor = "BTCUSDT"
    start_ts = 1_700_000_000_000

    p_sym = 100.0
    p_anc = 200.0
    for i in range(60):
        bin_ts = start_ts + i * 1000
        p_sym *= 1.0001
        p_anc *= 1.0001
        resampler.update_symbol(symbol, ts_ms=bin_ts + 10, price=p_sym)
        resampler.update_anchor(anchor, ts_ms=bin_ts + 20, price=p_anc)

    # Out-of-order anchor update (should be dropped and fail-closed)
    resampler.update_anchor(anchor, ts_ms=start_ts + 5 * 1000, price=p_anc)

    result = resampler.compute(symbol, anchors=[anchor], now_ts_ms=start_ts + 59 * 1000)
    assert result.ready is False
    assert result.why == "out_of_order"
    assert result.drops_out_of_order >= 1


def test_macro_sync_gap_too_large_not_ready():
    resampler = MacroSyncResampler(
        bin_ms=1000,
        window_bins=60,
        min_bins=3,
        ttl_ms=60_000,
        max_gap_bins=1,
        eps=1e-12,
    )

    symbol = "SOLUSDT"
    anchor = "BTCUSDT"
    start_ts = 1_700_000_000_000

    resampler.update_symbol(symbol, ts_ms=start_ts + 10, price=100.0)
    resampler.update_anchor(anchor, ts_ms=start_ts + 10, price=200.0)

    # Jump by > max_gap_bins (gap_bins=3)
    resampler.update_symbol(symbol, ts_ms=start_ts + 5_000 + 10, price=100.1)
    resampler.update_anchor(anchor, ts_ms=start_ts + 5_000 + 10, price=200.2)

    result = resampler.compute(symbol, anchors=[anchor], now_ts_ms=start_ts + 5_000)
    assert result.ready is False
    assert result.why == "gap_too_large"

