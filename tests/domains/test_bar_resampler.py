"""
Tests for Bar Resampler (Phase B1).

Tests tick → OHLCV bar aggregation logic.
"""

import pytest
from decimal import Decimal

from apps.reference.domains.feature_engineering.bar_resampler import (
    Bar,
    BarResampler,
    MultiSymbolBarResampler,
)


class TestBar:
    """Tests for Bar dataclass."""

    def test_bar_creation(self):
        """Test basic bar creation."""
        bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("10.5"),
            trade_count=100,
            start_ts_ms=1000000,
            end_ts_ms=1059999,
        )
        
        assert bar.symbol == "BTCUSDT"
        assert bar.timeframe_sec == 60
        assert bar.open == Decimal("50000")
        assert bar.high == Decimal("50100")
        assert bar.low == Decimal("49900")
        assert bar.close == Decimal("50050")
        assert bar.volume == Decimal("10.5")
        assert bar.trade_count == 100

    def test_bar_mid_property(self):
        """Test mid price calculation."""
        bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1"),
            trade_count=1,
            start_ts_ms=0,
            end_ts_ms=60000,
        )
        
        assert bar.mid == Decimal("100")  # (110 + 90) / 2

    def test_bar_range_pct(self):
        """Test range percentage calculation."""
        bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1"),
            trade_count=1,
            start_ts_ms=0,
            end_ts_ms=60000,
        )
        
        assert bar.range_pct == pytest.approx(0.2)  # (110 - 90) / 100

    def test_bar_bullish_bearish(self):
        """Test bullish/bearish detection."""
        bullish_bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=Decimal("1"),
            trade_count=1,
            start_ts_ms=0,
            end_ts_ms=60000,
        )
        
        assert bullish_bar.is_bullish is True
        assert bullish_bar.is_bearish is False
        
        bearish_bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("90"),
            close=Decimal("95"),
            volume=Decimal("1"),
            trade_count=1,
            start_ts_ms=0,
            end_ts_ms=60000,
        )
        
        assert bearish_bar.is_bullish is False
        assert bearish_bar.is_bearish is True


class TestBarResampler:
    """Tests for BarResampler."""

    def test_init_default(self):
        """Test default initialization."""
        resampler = BarResampler()
        
        assert resampler.timeframe_sec == 60
        assert resampler.timeframe_ms == 60000
        assert resampler.max_bars == 1000
        assert resampler._current_bar is None

    def test_init_custom_timeframe(self):
        """Test custom timeframe initialization."""
        resampler = BarResampler(timeframe_sec=300)  # 5 minutes
        
        assert resampler.timeframe_sec == 300
        assert resampler.timeframe_ms == 300000

    def test_init_invalid_timeframe(self):
        """Test invalid timeframe raises error."""
        with pytest.raises(ValueError):
            BarResampler(timeframe_sec=0)
        
        with pytest.raises(ValueError):
            BarResampler(timeframe_sec=-1)

    def test_first_tick_creates_bar(self):
        """Test first tick creates current bar."""
        resampler = BarResampler(timeframe_sec=60)
        
        result = resampler.add_tick(
            symbol="BTCUSDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            ts_ms=1000000,
        )
        
        # First tick should not close a bar
        assert result is None
        
        # Current bar should exist
        bar = resampler.get_current_bar()
        assert bar is not None
        assert bar.symbol == "BTCUSDT"
        assert bar.open == Decimal("50000")
        assert bar.high == Decimal("50000")
        assert bar.low == Decimal("50000")
        assert bar.close == Decimal("50000")
        assert bar.volume == Decimal("1.5")
        assert bar.trade_count == 1

    def test_ticks_within_same_bar_update_ohlcv(self):
        """Test ticks within same bar update OHLCV."""
        resampler = BarResampler(timeframe_sec=60)
        
        # Bar starts at ts=0 (aligned)
        resampler.add_tick("BTCUSDT", Decimal("100"), Decimal("1"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), Decimal("2"), ts_ms=10000)  # New high
        resampler.add_tick("BTCUSDT", Decimal("90"), Decimal("3"), ts_ms=20000)   # New low
        resampler.add_tick("BTCUSDT", Decimal("105"), Decimal("4"), ts_ms=30000)  # New close
        
        bar = resampler.get_current_bar()
        
        assert bar.open == Decimal("100")  # First tick
        assert bar.high == Decimal("110")  # Highest
        assert bar.low == Decimal("90")    # Lowest
        assert bar.close == Decimal("105") # Last tick
        assert bar.volume == Decimal("10") # Sum of all
        assert bar.trade_count == 4

    def test_bar_closes_on_new_period(self):
        """Test bar closes when tick from new period arrives."""
        resampler = BarResampler(timeframe_sec=60)
        
        # First bar: ticks at t=0 to t=59999ms
        resampler.add_tick("BTCUSDT", Decimal("100"), Decimal("1"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), Decimal("2"), ts_ms=30000)
        
        # Tick at t=60000ms (new bar period)
        closed_bar = resampler.add_tick("BTCUSDT", Decimal("115"), Decimal("3"), ts_ms=60000)
        
        # Should return closed bar
        assert closed_bar is not None
        assert closed_bar.open == Decimal("100")
        assert closed_bar.high == Decimal("110")
        assert closed_bar.close == Decimal("110")
        assert closed_bar.volume == Decimal("3")  # 1 + 2
        assert closed_bar.trade_count == 2
        
        # Current bar should be new
        current = resampler.get_current_bar()
        assert current is not None
        assert current.open == Decimal("115")
        assert current.volume == Decimal("3")

    def test_multiple_bars_close(self):
        """Test multiple bars closing in sequence."""
        resampler = BarResampler(timeframe_sec=60)
        
        bars_closed = []
        
        # Bar 1: t=0
        resampler.add_tick("BTCUSDT", Decimal("100"), Decimal("1"), ts_ms=0)
        
        # Bar 2: t=60000
        closed = resampler.add_tick("BTCUSDT", Decimal("110"), Decimal("2"), ts_ms=60000)
        if closed:
            bars_closed.append(closed)
        
        # Bar 3: t=120000
        closed = resampler.add_tick("BTCUSDT", Decimal("120"), Decimal("3"), ts_ms=120000)
        if closed:
            bars_closed.append(closed)
        
        assert len(bars_closed) == 2
        assert bars_closed[0].close == Decimal("100")
        assert bars_closed[1].close == Decimal("110")

    def test_get_completed_bars(self):
        """Test retrieving completed bars."""
        resampler = BarResampler(timeframe_sec=60)
        
        # Create 3 completed bars
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), ts_ms=60000)
        resampler.add_tick("BTCUSDT", Decimal("120"), ts_ms=120000)
        resampler.add_tick("BTCUSDT", Decimal("130"), ts_ms=180000)
        
        # Get all completed bars
        all_bars = resampler.get_completed_bars()
        assert len(all_bars) == 3
        
        # Get last 2 bars
        last_two = resampler.get_completed_bars(n=2)
        assert len(last_two) == 2
        assert last_two[0].close == Decimal("110")
        assert last_two[1].close == Decimal("120")

    def test_get_closes(self):
        """Test retrieving close prices."""
        resampler = BarResampler(timeframe_sec=60)
        
        # Create completed bars
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), ts_ms=60000)
        resampler.add_tick("BTCUSDT", Decimal("120"), ts_ms=120000)
        
        closes = resampler.get_closes()
        
        assert len(closes) == 2
        assert closes[0] == Decimal("100")
        assert closes[1] == Decimal("110")

    def test_force_close(self):
        """Test force closing current bar."""
        resampler = BarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), ts_ms=30000)
        
        # Force close before natural bar end
        closed = resampler.force_close(ts_ms=45000)
        
        assert closed is not None
        assert closed.close == Decimal("110")
        assert closed.end_ts_ms == 45000
        
        # Current bar should be None
        assert resampler.get_current_bar() is None
        
        # Completed bars should have 1
        assert len(resampler.get_completed_bars()) == 1

    def test_reset(self):
        """Test reset clears all state."""
        resampler = BarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), ts_ms=60000)
        
        resampler.reset()
        
        assert resampler.get_current_bar() is None
        assert len(resampler.get_completed_bars()) == 0
        
        metrics = resampler.get_metrics()
        assert metrics["ticks_processed"] == 0
        assert metrics["bars_completed"] == 0

    def test_metrics(self):
        """Test metrics tracking."""
        resampler = BarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("110"), ts_ms=30000)
        resampler.add_tick("BTCUSDT", Decimal("120"), ts_ms=60000)
        
        metrics = resampler.get_metrics()
        
        assert metrics["ticks_processed"] == 3
        assert metrics["bars_completed"] == 1
        assert metrics["bars_in_memory"] == 1
        assert metrics["has_current_bar"] is True

    def test_bar_boundary_alignment(self):
        """Test bars align to time boundaries."""
        resampler = BarResampler(timeframe_sec=60)
        
        # Tick at t=12345 should create bar starting at t=0 (aligned)
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=12345)
        
        bar = resampler.get_current_bar()
        assert bar.start_ts_ms == 0

    def test_max_bars_limit(self):
        """Test max_bars limit is respected."""
        resampler = BarResampler(timeframe_sec=60, max_bars=3)
        
        # Create 5 bars
        for i in range(6):
            resampler.add_tick("BTCUSDT", Decimal(str(100 + i * 10)), ts_ms=i * 60000)
        
        bars = resampler.get_completed_bars()
        
        # Should only keep last 3
        assert len(bars) == 3
        assert bars[0].close == Decimal("120")
        assert bars[1].close == Decimal("130")
        assert bars[2].close == Decimal("140")


class TestMultiSymbolBarResampler:
    """Tests for MultiSymbolBarResampler."""

    def test_multi_symbol_init(self):
        """Test multi-symbol initialization."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        assert resampler.timeframe_sec == 60
        assert len(resampler._resamplers) == 0

    def test_multi_symbol_separate_bars(self):
        """Test each symbol has separate bars."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        # Add ticks for two symbols
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=0)
        
        resampler.add_tick("BTCUSDT", Decimal("51000"), ts_ms=30000)
        resampler.add_tick("ETHUSDT", Decimal("3100"), ts_ms=30000)
        
        # Get current bars
        btc = resampler.get_resampler("BTCUSDT").get_current_bar()
        eth = resampler.get_resampler("ETHUSDT").get_current_bar()
        
        assert btc.symbol == "BTCUSDT"
        assert btc.high == Decimal("51000")
        
        assert eth.symbol == "ETHUSDT"
        assert eth.high == Decimal("3100")

    def test_multi_symbol_independent_close(self):
        """Test symbols close bars independently."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=30000)
        
        # Only BTC closes (tick at 60000)
        btc_closed = resampler.add_tick("BTCUSDT", Decimal("51000"), ts_ms=60000)
        
        assert btc_closed is not None
        assert btc_closed.symbol == "BTCUSDT"
        
        # ETH still in first bar
        eth = resampler.get_resampler("ETHUSDT").get_current_bar()
        assert eth.start_ts_ms == 0

    def test_multi_symbol_get_closes(self):
        """Test get_closes for specific symbol."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        # Create bars for BTC
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("51000"), ts_ms=60000)
        resampler.add_tick("BTCUSDT", Decimal("52000"), ts_ms=120000)
        
        # Create bars for ETH
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=0)
        resampler.add_tick("ETHUSDT", Decimal("3100"), ts_ms=60000)
        
        btc_closes = resampler.get_closes("BTCUSDT")
        eth_closes = resampler.get_closes("ETHUSDT")
        
        assert btc_closes == [Decimal("50000"), Decimal("51000")]
        assert eth_closes == [Decimal("3000")]

    def test_multi_symbol_reset_all(self):
        """Test reset all symbols."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=0)
        
        resampler.reset()
        
        assert len(resampler._resamplers) == 0

    def test_multi_symbol_reset_single(self):
        """Test reset single symbol."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=0)
        
        resampler.reset("BTCUSDT")
        
        # BTC should be reset
        btc = resampler.get_resampler("BTCUSDT")
        assert btc.get_current_bar() is None
        
        # ETH should still have bar
        eth = resampler.get_resampler("ETHUSDT")
        assert eth.get_current_bar() is not None

    def test_multi_symbol_metrics(self):
        """Test metrics for all symbols."""
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        resampler.add_tick("BTCUSDT", Decimal("50000"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("51000"), ts_ms=60000)
        resampler.add_tick("ETHUSDT", Decimal("3000"), ts_ms=0)
        
        metrics = resampler.get_metrics()
        
        assert "BTCUSDT" in metrics
        assert "ETHUSDT" in metrics
        assert metrics["BTCUSDT"]["ticks_processed"] == 2
        assert metrics["ETHUSDT"]["ticks_processed"] == 1


# ============================================================
# P2-1 Regression Tests: Gap Detection
# ============================================================

class TestBarResamplerGapDetection:
    """P2-1 REGRESSION: Gap detection in bar resampler."""

    def test_no_gap_normal_ticks(self):
        """Normal consecutive ticks should not trigger gap detection."""
        resampler = BarResampler(timeframe_sec=60)  # 1 minute bars
        
        # Tick 1: start bar at 0
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        
        # Tick 2: close bar at 60s, start new bar
        bar = resampler.add_tick("BTCUSDT", Decimal("101"), ts_ms=60_000)
        
        assert bar is not None  # Bar closed
        
        # Get current bar (new one)
        current = resampler.get_current_bar()
        assert current.is_gap_bar is False
        assert current.gap_bars_skipped == 0
        assert resampler.get_metrics()["gaps_detected"] == 0

    def test_gap_one_bar_skipped(self):
        """Gap of 1 minute (1 bar skipped) should be detected."""
        resampler = BarResampler(timeframe_sec=60)  # 1 minute bars
        
        # Tick 1: start bar at 0
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        
        # Tick 2: close bar at 60s
        bar1 = resampler.add_tick("BTCUSDT", Decimal("101"), ts_ms=60_000)
        assert bar1 is not None
        
        # Tick 3: gap! Skip to 180s (3rd minute) - 1 bar skipped
        bar2 = resampler.add_tick("BTCUSDT", Decimal("102"), ts_ms=180_000)
        assert bar2 is not None  # 2nd bar closed
        
        # Current bar (3rd) should have gap flag
        current = resampler.get_current_bar()
        assert current.is_gap_bar is True
        assert current.gap_bars_skipped == 1
        assert resampler.get_metrics()["gaps_detected"] == 1

    def test_gap_multiple_bars_skipped(self):
        """Gap of 5 minutes (5 bars skipped) should be detected."""
        resampler = BarResampler(timeframe_sec=60)  # 1 minute bars
        
        # Tick 1: start bar at minute 0
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        
        # Tick 2: close bar at minute 1, skip to minute 7 (6 bars skipped: 1,2,3,4,5,6)
        bar = resampler.add_tick("BTCUSDT", Decimal("101"), ts_ms=7 * 60_000)
        
        assert bar is not None  # Bar 0-1 closed
        
        # Current bar (minute 7) should have gap flag
        current = resampler.get_current_bar()
        assert current.is_gap_bar is True
        assert current.gap_bars_skipped == 6  # bars 1,2,3,4,5,6 skipped (bar 0 was closed)
        assert resampler.get_metrics()["gaps_detected"] == 1

    def test_gap_detection_reset(self):
        """Reset should clear gap counter."""
        resampler = BarResampler(timeframe_sec=60)
        
        # Create a gap
        resampler.add_tick("BTCUSDT", Decimal("100"), ts_ms=0)
        resampler.add_tick("BTCUSDT", Decimal("101"), ts_ms=180_000)  # 2 minute gap
        
        assert resampler.get_metrics()["gaps_detected"] == 1
        
        resampler.reset()
        
        assert resampler.get_metrics()["gaps_detected"] == 0
