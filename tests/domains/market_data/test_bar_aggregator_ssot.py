"""
Tests for BarAggregator SSOT.

BAR-SSOT-001: SSOT Bar Aggregator + EVT:BAR_CLOSED

Tests:
- 180s (3m) bar construction and EVT:BAR_CLOSED emission
- 300s (5m) bar construction and EVT:BAR_CLOSED emission
- Out-of-order tick handling (drop, don't corrupt)
- Multi-symbol isolation
- Gap detection
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, call

from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.feature_engineering.bar_resampler import Bar


class TestBarAggregator180s:
    """Tests for 180s (3 minute) bar construction."""
    
    def test_builds_180s_bar_and_emits_bar_closed(self):
        """
        Given ticks spanning > 180s, aggregator should:
        1. Build complete bar with correct OHLCV
        2. Emit EVT:BAR_CLOSED with bar payload
        """
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[180], emit_fn=emit_spy)
        
        # T=0: First tick at bar boundary (for simplicity)
        base_ts = 180_000  # 180s in ms, aligned
        
        # Tick 1: Open
        agg.on_tick("BTCUSDT", Decimal("100.00"), Decimal("1.0"), base_ts + 1000)
        
        # Tick 2: High
        agg.on_tick("BTCUSDT", Decimal("105.00"), Decimal("2.0"), base_ts + 60_000)
        
        # Tick 3: Low (will also be close since it's last tick before boundary)
        agg.on_tick("BTCUSDT", Decimal("95.00"), Decimal("3.0"), base_ts + 120_000)
        
        # No bar closed yet
        assert emit_spy.call_count == 0
        
        # Tick 4: This tick triggers bar close, but belongs to NEW bar
        # (this is standard bar aggregation behavior: tick at boundary starts new bar)
        completed = agg.on_tick("BTCUSDT", Decimal("102.00"), Decimal("4.0"), base_ts + 180_000)
        
        # Should have completed 1 bar
        assert len(completed) == 1
        bar = completed[0]
        
        # Verify OHLCV - close is the LAST tick before boundary (tick 3)
        assert bar.symbol == "BTCUSDT"
        assert bar.timeframe_sec == 180
        assert bar.open == Decimal("100.00")
        assert bar.high == Decimal("105.00")
        assert bar.low == Decimal("95.00")
        assert bar.close == Decimal("95.00")  # Last tick before boundary
        assert bar.volume == Decimal("6.0")  # 1+2+3 (tick 4 is in new bar)
        assert bar.trade_count == 3
        
        # Verify EVT:BAR_CLOSED emitted
        assert emit_spy.call_count == 1
        call_args = emit_spy.call_args
        assert call_args[0][0] == "EVT:BAR_CLOSED"
        
        payload = call_args[0][1]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["bar"]["timeframe_sec"] == 180
        assert payload["bar"]["open"] == "100.00"
        assert payload["bar"]["high"] == "105.00"
        assert payload["bar"]["low"] == "95.00"
        assert payload["bar"]["close"] == "95.00"  # Last tick before boundary
        
        # BAR-FEATURES-001: why is now passed as kwarg, not in payload
        why = call_args[1].get("why") if len(call_args) > 1 else None
        assert why is not None, "emit should have why kwarg"
        assert len(why) <= 80


class TestBarAggregator300s:
    """Tests for 300s (5 minute) bar construction."""
    
    def test_builds_300s_bar_and_emits_bar_closed(self):
        """
        Given ticks spanning > 300s, aggregator should:
        1. Build complete 5m bar
        2. Emit EVT:BAR_CLOSED
        """
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        
        base_ts = 300_000  # Aligned to 300s boundary
        
        # Build bar over 5 minutes
        agg.on_tick("ETHUSDT", Decimal("2000.00"), Decimal("10"), base_ts + 1000)  # Open
        agg.on_tick("ETHUSDT", Decimal("2100.00"), Decimal("20"), base_ts + 100_000)  # High
        agg.on_tick("ETHUSDT", Decimal("1950.00"), Decimal("30"), base_ts + 200_000)  # Low (and close)
        
        # Tick that closes bar (at next 300s boundary) - this tick starts NEW bar
        completed = agg.on_tick("ETHUSDT", Decimal("2050.00"), Decimal("40"), base_ts + 300_000)
        
        assert len(completed) == 1
        bar = completed[0]
        
        # Close is last tick BEFORE boundary
        assert bar.symbol == "ETHUSDT"
        assert bar.timeframe_sec == 300
        assert bar.open == Decimal("2000.00")
        assert bar.high == Decimal("2100.00")
        assert bar.low == Decimal("1950.00")
        assert bar.close == Decimal("1950.00")  # Last tick before boundary
        assert bar.volume == Decimal("60")  # 10+20+30 (tick at boundary is in new bar)
        
        # Verify emission
        assert emit_spy.call_count == 1
        payload = emit_spy.call_args[0][1]
        assert payload["bar"]["timeframe_sec"] == 300


class TestOutOfOrderTicks:
    """Tests for out-of-order tick handling."""
    
    def test_out_of_order_tick_is_ignored_and_does_not_corrupt_bar(self):
        """
        Given an out-of-order tick (ts <= last_ts):
        1. Tick should be dropped
        2. Bar should NOT be corrupted
        3. Metrics should track the drop
        """
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[180], emit_fn=emit_spy)
        
        base_ts = 180_000
        
        # Normal tick sequence
        agg.on_tick("BTCUSDT", Decimal("100.00"), Decimal("1"), base_ts + 1000)
        agg.on_tick("BTCUSDT", Decimal("105.00"), Decimal("1"), base_ts + 60_000)  # High at T+60s
        
        # Out-of-order tick (goes back in time)
        agg.on_tick("BTCUSDT", Decimal("999.00"), Decimal("999"), base_ts + 30_000)  # T+30s < T+60s
        
        # Verify bar is NOT corrupted by OOO tick
        current = agg.get_current_bar("BTCUSDT", 180)
        assert current.high == Decimal("105.00"), "High should be unchanged"
        assert current.close == Decimal("105.00"), "Close should be unchanged"
        assert current.volume == Decimal("2"), "Volume should be 2, not 1001"
        
        # Verify metrics
        metrics = agg.get_metrics()
        assert metrics["ticks_dropped_ooo"] >= 1
    
    def test_duplicate_timestamp_is_dropped(self):
        """
        Given a tick with same timestamp as last tick:
        - Should be dropped (ts <= last_ts includes equality)
        """
        agg = BarAggregator(timeframes_sec=[180])
        
        ts = 180_000
        agg.on_tick("BTCUSDT", Decimal("100.00"), Decimal("1"), ts)
        agg.on_tick("BTCUSDT", Decimal("200.00"), Decimal("1"), ts)  # Duplicate ts
        
        current = agg.get_current_bar("BTCUSDT", 180)
        assert current.close == Decimal("100.00"), "Duplicate should be dropped"
        assert current.trade_count == 1


class TestMultiTimeframe:
    """Tests for multi-timeframe support."""
    
    def test_aggregates_both_180s_and_300s_simultaneously(self):
        """
        Given both 180s and 300s configured:
        - Both timeframes should build bars independently
        - 180s bar should close before 300s
        """
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[180, 300], emit_fn=emit_spy)
        
        base_ts = 0
        
        # Ticks over 5+ minutes
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), base_ts + 1000)
        agg.on_tick("BTCUSDT", Decimal("101"), Decimal("1"), base_ts + 90_000)
        
        # At 180s - only 180s bar should close
        completed = agg.on_tick("BTCUSDT", Decimal("102"), Decimal("1"), base_ts + 180_000)
        
        # Should have 1 completed bar (180s)
        tf_secs = [b.timeframe_sec for b in completed]
        assert 180 in tf_secs
        assert 300 not in tf_secs
        
        # Continue to 300s
        agg.on_tick("BTCUSDT", Decimal("103"), Decimal("1"), base_ts + 250_000)
        
        # At 300s - 300s bar closes
        completed = agg.on_tick("BTCUSDT", Decimal("104"), Decimal("1"), base_ts + 300_000)
        
        tf_secs = [b.timeframe_sec for b in completed]
        assert 300 in tf_secs


class TestMultiSymbol:
    """Tests for multi-symbol isolation."""
    
    def test_symbols_are_isolated(self):
        """
        Given multiple symbols:
        - Each symbol should have independent bars
        - One symbol's data should not affect another
        """
        agg = BarAggregator(timeframes_sec=[180])
        
        base_ts = 180_000
        
        # BTC ticks
        agg.on_tick("BTCUSDT", Decimal("50000"), Decimal("1"), base_ts + 1000)
        agg.on_tick("BTCUSDT", Decimal("51000"), Decimal("1"), base_ts + 60_000)
        
        # ETH ticks (completely different prices)
        agg.on_tick("ETHUSDT", Decimal("3000"), Decimal("2"), base_ts + 30_000)
        agg.on_tick("ETHUSDT", Decimal("3100"), Decimal("2"), base_ts + 90_000)
        
        # Verify isolation
        btc_bar = agg.get_current_bar("BTCUSDT", 180)
        eth_bar = agg.get_current_bar("ETHUSDT", 180)
        
        assert btc_bar.open == Decimal("50000")
        assert btc_bar.high == Decimal("51000")
        assert btc_bar.volume == Decimal("2")
        
        assert eth_bar.open == Decimal("3000")
        assert eth_bar.high == Decimal("3100")
        assert eth_bar.volume == Decimal("4")


class TestGapDetection:
    """Tests for gap detection in bars."""
    
    def test_gap_bar_is_flagged(self):
        """
        Given a large time gap between ticks:
        - New bar should have is_gap_bar=True
        - gap_bars_skipped should count missing bars
        """
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[180], emit_fn=emit_spy)
        
        base_ts = 180_000
        
        # First bar
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), base_ts + 1000)
        
        # Close first bar and create gap (skip 2 bars worth = 360s)
        # First bar ends at 180_000 + 180_000 = 360_000
        # Gap: 360_000 to 720_000 (2 bars skipped)
        completed = agg.on_tick("BTCUSDT", Decimal("110"), Decimal("1"), base_ts + 540_000)  # 720s total
        
        assert len(completed) == 1
        
        # Check that new bar is marked as gap
        new_bar = agg.get_current_bar("BTCUSDT", 180)
        assert new_bar.is_gap_bar is True
        assert new_bar.gap_bars_skipped >= 1


class TestEdgeCases:
    """Edge case tests."""
    
    def test_no_emit_fn_does_not_crash(self):
        """
        Given no emit_fn provided:
        - Aggregator should still work
        - Just no events emitted
        """
        agg = BarAggregator(timeframes_sec=[180], emit_fn=None)
        
        base_ts = 180_000
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), base_ts + 1000)
        completed = agg.on_tick("BTCUSDT", Decimal("101"), Decimal("1"), base_ts + 180_000)
        
        # Should complete bar without crash
        assert len(completed) == 1
    
    def test_zero_volume_ticks(self):
        """
        Given ticks with zero volume:
        - Should still build valid bar
        """
        agg = BarAggregator(timeframes_sec=[180])
        
        base_ts = 180_000
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("0"), base_ts + 1000)
        agg.on_tick("BTCUSDT", Decimal("101"), Decimal("0"), base_ts + 60_000)
        
        bar = agg.get_current_bar("BTCUSDT", 180)
        assert bar.volume == Decimal("0")
        assert bar.open == Decimal("100")
        assert bar.close == Decimal("101")
    
    def test_invalid_timeframe_raises(self):
        """
        Given invalid timeframe (<=0):
        - Should raise ValueError
        """
        with pytest.raises(ValueError):
            BarAggregator(timeframes_sec=[0])
        
        with pytest.raises(ValueError):
            BarAggregator(timeframes_sec=[-60])
    
    def test_reset_clears_state(self):
        """
        Given populated aggregator:
        - reset() should clear all state
        """
        agg = BarAggregator(timeframes_sec=[180])
        
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), 180_001)
        agg.on_tick("ETHUSDT", Decimal("3000"), Decimal("1"), 180_001)
        
        assert agg.get_current_bar("BTCUSDT", 180) is not None
        assert agg.get_current_bar("ETHUSDT", 180) is not None
        
        agg.reset()
        
        assert agg.get_current_bar("BTCUSDT", 180) is None
        assert agg.get_current_bar("ETHUSDT", 180) is None
    
    def test_partial_reset_by_symbol(self):
        """
        Given multiple symbols:
        - reset(symbol=X) should only clear that symbol
        """
        agg = BarAggregator(timeframes_sec=[180])
        
        agg.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), 180_001)
        agg.on_tick("ETHUSDT", Decimal("3000"), Decimal("1"), 180_001)
        
        agg.reset(symbol="BTCUSDT")
        
        assert agg.get_current_bar("BTCUSDT", 180) is None
        assert agg.get_current_bar("ETHUSDT", 180) is not None
