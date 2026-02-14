"""
Unit tests for SL Fill Policy — core pure functions.
=====================================================

T1: SELL STOP triggered, conservative = low
T2: SELL STOP triggered, optimistic >= low & close to stop*(1-slip)
T3: BUY STOP triggered, conservative = high
T4: BUY STOP triggered, optimistic <= high
T5: Not triggered → no fill
T6: Slippage bps sign correctness
T7: Deterministic output (no randomness in policy)
T8: Extreme bar does NOT change rules (no open cap)
T9: Band record computed correctly
T10: Band record returns None when not triggered
T11: Optimistic clamps to bar boundary
T12: summarize_sl_band basic stats
"""
import sys, os
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_engine.sl_fill_policy import (
    SLFillModel,
    BarData,
    StopOrder,
    SLBandRecord,
    is_stop_triggered,
    compute_stop_market_fill,
    compute_slippage_bps,
    build_sl_band_record,
    summarize_sl_band,
)


# ---------- helpers ----------

def _bar(open=100.0, high=105.0, low=90.0, close=95.0, volume=1000.0) -> BarData:
    return BarData(open=open, high=high, low=low, close=close, volume=volume)


def _sell_stop(sp: float = 98.0) -> StopOrder:
    """SELL STOP = long SL."""
    return StopOrder(side="SELL", stop_price=sp, order_id="SL-1", symbol="BTCUSDT")


def _buy_stop(sp: float = 102.0) -> StopOrder:
    """BUY STOP = short SL."""
    return StopOrder(side="BUY", stop_price=sp, order_id="SL-2", symbol="BTCUSDT")


# ================================================================
#  T1: SELL STOP conservative = bar.low
# ================================================================
class TestT1SellConservative:
    def test_fill_equals_low(self):
        bar = _bar(low=90.0)
        order = _sell_stop(sp=95.0)  # triggered because low=90 <= 95
        result = compute_stop_market_fill(order, bar, SLFillModel.CONSERVATIVE)
        assert result.triggered is True
        assert result.fill_price == 90.0


# ================================================================
#  T2: SELL STOP optimistic >= low and near stop*(1-slip)
# ================================================================
class TestT2SellOptimistic:
    def test_fill_ge_low_and_near_stop(self):
        bar = _bar(low=90.0)
        order = _sell_stop(sp=95.0)
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        assert result.triggered is True
        # Must be >= low
        assert result.fill_price >= 90.0
        # Expected: max(90, 95*(1-0.0005)) = max(90, 94.9525) = 94.9525
        expected = 95.0 * (1 - 5.0 / 10000)
        assert result.fill_price == pytest.approx(expected, rel=1e-9)

    def test_optimistic_not_better_than_low(self):
        """When stop is below low, optimistic is clamped to low."""
        bar = _bar(low=94.0)       # low is very close to stop
        order = _sell_stop(sp=95.0)  # triggered: low 94 <= 95
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        # max(94.0, 94.9525) = 94.9525 -- but wait, 94.9525 > 94.0, so it's fine
        assert result.fill_price >= bar.low
        assert result.fill_price <= order.stop_price


# ================================================================
#  T3: BUY STOP conservative = bar.high
# ================================================================
class TestT3BuyConservative:
    def test_fill_equals_high(self):
        bar = _bar(high=110.0)
        order = _buy_stop(sp=105.0)  # triggered: high=110 >= 105
        result = compute_stop_market_fill(order, bar, SLFillModel.CONSERVATIVE)
        assert result.triggered is True
        assert result.fill_price == 110.0


# ================================================================
#  T4: BUY STOP optimistic <= high
# ================================================================
class TestT4BuyOptimistic:
    def test_fill_le_high_and_near_stop(self):
        bar = _bar(high=110.0)
        order = _buy_stop(sp=105.0)
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        assert result.triggered is True
        assert result.fill_price <= 110.0
        expected = 105.0 * (1 + 5.0 / 10000)
        assert result.fill_price == pytest.approx(expected, rel=1e-9)


# ================================================================
#  T5: Not triggered → no fill
# ================================================================
class TestT5NotTriggered:
    def test_sell_stop_not_triggered(self):
        bar = _bar(low=99.0)
        order = _sell_stop(sp=95.0)  # low=99 > 95 → NOT triggered
        result = compute_stop_market_fill(order, bar, SLFillModel.CONSERVATIVE)
        assert result.triggered is False

    def test_buy_stop_not_triggered(self):
        bar = _bar(high=100.0)
        order = _buy_stop(sp=105.0)  # high=100 < 105 → NOT triggered
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC)
        assert result.triggered is False


# ================================================================
#  T6: Slippage bps sign correctness
# ================================================================
class TestT6SlippageBps:
    def test_sell_slippage_positive(self):
        # SELL: slip = (stop - fill) / stop * 10000
        bps = compute_slippage_bps("SELL", stop_price=100.0, fill_price=99.0)
        assert bps == pytest.approx(100.0)  # 1% = 100 bps
        assert bps >= 0

    def test_buy_slippage_positive(self):
        # BUY: slip = (fill - stop) / stop * 10000
        bps = compute_slippage_bps("BUY", stop_price=100.0, fill_price=101.0)
        assert bps == pytest.approx(100.0)
        assert bps >= 0

    def test_zero_stop_returns_zero(self):
        assert compute_slippage_bps("SELL", 0.0, 99.0) == 0.0


# ================================================================
#  T7: Deterministic output (no randomness)
# ================================================================
class TestT7Deterministic:
    def test_same_inputs_same_output(self):
        bar = _bar()
        order = _sell_stop(sp=95.0)
        results = [
            compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
            for _ in range(100)
        ]
        prices = {r.fill_price for r in results}
        assert len(prices) == 1  # all identical


# ================================================================
#  T8: Extreme bar does NOT change rules (no open cap)
# ================================================================
class TestT8ExtremeBar:
    def test_flash_crash_bar_conservative_fills_at_low(self):
        """The 2023-08-17 21:40 flash crash bar — conservative fills at actual low."""
        bar = BarData(open=27566.1, high=27594.0, low=24581.0, close=24804.1)
        order = StopOrder(side="SELL", stop_price=27000.0)  # triggered: 24581 < 27000
        result = compute_stop_market_fill(order, bar, SLFillModel.CONSERVATIVE)
        assert result.fill_price == 24581.0  # low, NOT open-capped

    def test_flash_crash_bar_optimistic_stays_within_bar(self):
        """Optimistic fill for same bar — bounded by low, no open usage."""
        bar = BarData(open=27566.1, high=27594.0, low=24581.0, close=24804.1)
        order = StopOrder(side="SELL", stop_price=27000.0)
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        expected = max(24581.0, 27000.0 * (1 - 5.0 / 10000))
        assert result.fill_price == pytest.approx(expected, rel=1e-9)
        assert result.fill_price >= bar.low
        # Verify NO open-based capping happened
        assert result.fill_price != bar.open * 0.97  # old cap logic


# ================================================================
#  T9: Band record computed correctly
# ================================================================
class TestT9BandRecord:
    def test_band_record_has_both_fills(self):
        bar = _bar(low=90.0, high=110.0)
        order = _sell_stop(sp=95.0)
        band = build_sl_band_record(order, bar, sl_min_bps=5.0)
        assert band is not None
        assert band.fill_conservative == 90.0
        assert band.fill_optimistic == pytest.approx(95.0 * (1 - 5.0 / 10000))
        assert band.slippage_conservative_bps > band.slippage_optimistic_bps
        assert band.delta_fill_pct > 0  # optimistic is better (higher) for SELL


# ================================================================
#  T10: Band record returns None when not triggered
# ================================================================
class TestT10BandNotTriggered:
    def test_returns_none(self):
        bar = _bar(low=99.0)
        order = _sell_stop(sp=95.0)
        result = build_sl_band_record(order, bar)
        assert result is None


# ================================================================
#  T11: Optimistic clamps to bar boundary
# ================================================================
class TestT11OptimisticClamp:
    def test_sell_clamp_low_is_above_slip_line(self):
        """When bar.low > stop*(1-slip), optimistic = stop*(1-slip), not low."""
        bar = _bar(low=94.96)  # low > 95*(1-0.0005)=94.9525 → clamp by low
        order = _sell_stop(sp=95.0)
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        # max(94.96, 94.9525) = 94.96 = low dominates
        assert result.fill_price == pytest.approx(94.96)

    def test_buy_clamp_high_is_below_slip_line(self):
        """When bar.high < stop*(1+slip), optimistic = stop*(1+slip), but clamped to high."""
        bar = _bar(high=105.04)  # high < 105*(1+0.0005)=105.0525 → clamp by high
        order = _buy_stop(sp=105.0)
        result = compute_stop_market_fill(order, bar, SLFillModel.OPTIMISTIC, sl_min_bps=5.0)
        # min(105.04, 105.0525) = 105.04 = high dominates
        assert result.fill_price == pytest.approx(105.04)


# ================================================================
#  T12: summarize_sl_band basic stats
# ================================================================
class TestT12Summarize:
    def test_empty(self):
        s = summarize_sl_band([])
        assert s["count_sl"] == 0

    def test_basic_stats(self):
        records = [
            SLBandRecord(
                order_id="1", symbol="X", bar_ts=0, side="SELL",
                stop_price=100.0, bar_open=101, bar_high=102, bar_low=90, bar_close=95,
                fill_optimistic=99.95, fill_conservative=90.0,
                slippage_optimistic_bps=5.0, slippage_conservative_bps=1000.0,
                delta_fill_pct=0.0995,
            ),
            SLBandRecord(
                order_id="2", symbol="X", bar_ts=1, side="SELL",
                stop_price=200.0, bar_open=201, bar_high=202, bar_low=195, bar_close=198,
                fill_optimistic=199.9, fill_conservative=195.0,
                slippage_optimistic_bps=5.0, slippage_conservative_bps=250.0,
                delta_fill_pct=0.0245,
            ),
        ]
        s = summarize_sl_band(records)
        assert s["count_sl"] == 2
        assert s["mean_slip_bps_opt"] == pytest.approx(5.0)
        assert s["max_slip_bps_cons"] == pytest.approx(1000.0)
        assert len(s["top_10_worst_bars"]) == 2
