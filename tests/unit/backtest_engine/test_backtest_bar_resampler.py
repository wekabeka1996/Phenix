"""Unit tests for BacktestBarResampler."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from backtest_engine.backtest_bar_resampler import (
    BacktestBarResampler,
    _HTFBarAccumulator,
    _align_to_boundary,
)


# ============================================================================
# _align_to_boundary
# ============================================================================

class TestAlignToBoundary:
    def test_m15_exact(self):
        """Exact M15 boundary stays the same."""
        boundary = 900 * 1000 * 10  # 10th M15 period
        assert _align_to_boundary(boundary, 900) == boundary

    def test_m15_mid_bar(self):
        """Mid-bar timestamp floors to period start."""
        boundary = 900 * 1000 * 10
        mid = boundary + 450 * 1000  # 7.5 minutes into bar
        assert _align_to_boundary(mid, 900) == boundary

    def test_d1_utc(self):
        """D1 boundary aligns to UTC day start."""
        # 2024-01-05 00:00:00 UTC = 1704412800000 ms
        day_start_ms = 1704412800000
        mid_day_ms = day_start_ms + 12 * 3600 * 1000  # noon
        assert _align_to_boundary(mid_day_ms, 86400) == day_start_ms

    def test_h4_alignment(self):
        """H4 boundary aligns to 4-hour blocks."""
        # H4 = 14400 sec = 14400000 ms
        boundary = 14400 * 1000 * 5  # 5th H4 period
        ts = boundary + 7200 * 1000  # 2 hours in
        assert _align_to_boundary(ts, 14400) == boundary


# ============================================================================
# _HTFBarAccumulator
# ============================================================================

class TestHTFBarAccumulator:
    def test_empty_on_init(self):
        acc = _HTFBarAccumulator(tf_sec=900)
        assert acc.is_empty

    def test_single_bar(self):
        acc = _HTFBarAccumulator(tf_sec=900)
        acc.update({"open": "100", "high": "110", "low": "90", "close": "105", "volume": "50"})
        assert acc.open == 100.0
        assert acc.high == 110.0
        assert acc.low == 90.0
        assert acc.close == 105.0
        assert acc.volume == 50.0
        assert acc.bar_count == 1
        assert not acc.is_empty

    def test_multi_bar_ohlcv(self):
        """OHLCV aggregation: O=first, H=max, L=min, C=last, V=sum."""
        acc = _HTFBarAccumulator(tf_sec=900)
        acc.update({"open": "100", "high": "110", "low": "90", "close": "105", "volume": "50"})
        acc.update({"open": "105", "high": "120", "low": "95", "close": "115", "volume": "30"})
        acc.update({"open": "115", "high": "108", "low": "85", "close": "100", "volume": "20"})

        assert acc.open == 100.0    # First bar's open
        assert acc.high == 120.0    # Max of all highs
        assert acc.low == 85.0      # Min of all lows
        assert acc.close == 100.0   # Last bar's close
        assert acc.volume == 100.0  # Sum
        assert acc.bar_count == 3

    def test_reset(self):
        acc = _HTFBarAccumulator(tf_sec=900)
        acc.update({"open": "100", "high": "110", "low": "90", "close": "105", "volume": "50"})
        acc.reset()
        assert acc.is_empty
        assert acc.bar_count == 0
        assert acc.volume == 0.0

    def test_to_bar_payload(self):
        acc = _HTFBarAccumulator(tf_sec=14400)
        acc.update({"open": "100", "high": "120", "low": "80", "close": "110", "volume": "1000",
                    "start_ts_ms": 1000000})
        payload = acc.to_bar_payload("BTCUSDT", 1000000 + 14400 * 1000)
        assert payload["tf_sec"] == 14400
        assert payload["bar"]["symbol"] == "BTCUSDT"
        assert float(payload["bar"]["open"]) == 100.0
        assert float(payload["bar"]["high"]) == 120.0
        assert float(payload["bar"]["low"]) == 80.0
        assert float(payload["bar"]["close"]) == 110.0
        assert payload["bar_meta"]["source"] == "backtest_resampler"


# ============================================================================
# BacktestBarResampler
# ============================================================================

class TestBacktestBarResampler:
    def _make_bar(self, open_px=100, high=110, low=90, close=105, volume=10):
        return {
            "open": str(open_px), "high": str(high), "low": str(low),
            "close": str(close), "volume": str(volume),
            "buy_volume": "5", "sell_volume": "5",
            "buy_count": 10, "sell_count": 10,
            "buy_notional": "500", "sell_notional": "500",
        }

    def test_no_emit_within_same_boundary(self):
        """No HTF bar emitted if all 5m bars are in the same period."""
        events = []
        def mock_emit(event_name, payload, why):
            events.append(payload)

        resampler = BacktestBarResampler(emit_fn=mock_emit, pillar_timeframes_sec=[900])
        base = 900 * 1000 * 100  # boundary-aligned

        for i in range(3):
            resampler.on_5m_bar("BTC", self._make_bar(), base + i * 300_000 + 1)

        assert len(events) == 0

    def test_emit_on_boundary_cross(self):
        """HTF bar emitted when 5m bar crosses M15 boundary."""
        events = []
        def mock_emit(event_name, payload, why):
            events.append(payload)

        resampler = BacktestBarResampler(emit_fn=mock_emit, pillar_timeframes_sec=[900])
        base = 900 * 1000 * 100

        # 3 bars in first M15 period
        for i in range(3):
            resampler.on_5m_bar("BTC", self._make_bar(close=100 + i), base + i * 300_000 + 1)

        # First bar of NEXT M15 period
        resampler.on_5m_bar("BTC", self._make_bar(close=200), base + 900_000 + 1)

        assert len(events) == 1
        assert events[0]["tf_sec"] == 900
        assert events[0]["bar"]["symbol"] == "BTC"
        assert int(events[0]["bar_meta"]["basis_bars"]) == 3

    def test_multi_tf_simultaneous(self):
        """Multiple TFs can emit at different cadences."""
        events = []
        def mock_emit(event_name, payload, why):
            events.append(payload)

        # M15 (900s) and H4 (14400s = 48 × 300s)
        resampler = BacktestBarResampler(emit_fn=mock_emit, pillar_timeframes_sec=[900, 14400])
        base = 14400 * 1000 * 10  # aligned to both

        # Feed 48 5m bars (= 1 H4 period = 16 M15 periods)
        for i in range(48):
            resampler.on_5m_bar("BTC", self._make_bar(), base + i * 300_000 + 1)

        # No emissions yet (all within first H4/M15 boundaries)
        # Actually, M15 should close after every 3 5m bars crossing boundary
        # But all bars are within [base, base + 48*300s) so M15 closes happen
        # when boundary changes (every 3 bars for M15)

        # This test verifies multi-TF coexistence
        m15_events = [e for e in events if e["tf_sec"] == 900]
        h4_events = [e for e in events if e["tf_sec"] == 14400]

        # In 48 5m bars = 16 M15 periods: 15 boundary crosses → 15 M15 bars
        assert len(m15_events) == 15, f"Expected 15 M15 bars, got {len(m15_events)}"
        assert len(h4_events) == 0  # No H4 boundary crossed yet

    def test_d1_emit_after_day_cross(self):
        """D1 bar emitted when day boundary is crossed."""
        events = []
        def mock_emit(event_name, payload, why):
            events.append(payload)

        resampler = BacktestBarResampler(emit_fn=mock_emit, pillar_timeframes_sec=[86400])

        # Start at 2024-01-05 00:00 UTC
        day_start = 1704412800000
        bars_per_day = 288  # 24h * 60min / 5min

        # Feed full day of 5m bars
        for i in range(bars_per_day):
            resampler.on_5m_bar("BTC", self._make_bar(), day_start + i * 300_000 + 1)

        # No D1 bar emitted yet (still within same day)
        assert len(events) == 0

        # First bar of next day
        resampler.on_5m_bar("BTC", self._make_bar(), day_start + 86400_000 + 1)

        assert len(events) == 1
        assert events[0]["tf_sec"] == 86400
        assert int(events[0]["bar_meta"]["basis_bars"]) == 288

    def test_metrics(self):
        resampler = BacktestBarResampler(emit_fn=lambda **kw: None, pillar_timeframes_sec=[900])
        base = 900 * 1000 * 100

        resampler.on_5m_bar("BTC", self._make_bar(), base + 1)
        metrics = resampler.get_metrics()
        assert metrics["total_5m_bars_processed"] == 1
        assert metrics["active_accumulators"] == 1

    def test_multi_symbol(self):
        """Each symbol has independent accumulation."""
        events = []
        def mock_emit(event_name, payload, why):
            events.append(payload)

        resampler = BacktestBarResampler(emit_fn=mock_emit, pillar_timeframes_sec=[900])
        base = 900 * 1000 * 100

        # 3 bars each for BTC and ETH in same M15 period
        for i in range(3):
            resampler.on_5m_bar("BTC", self._make_bar(close=100), base + i * 300_000 + 1)
            resampler.on_5m_bar("ETH", self._make_bar(close=200), base + i * 300_000 + 1)

        # Cross boundary for both
        resampler.on_5m_bar("BTC", self._make_bar(close=110), base + 900_000 + 1)
        resampler.on_5m_bar("ETH", self._make_bar(close=210), base + 900_000 + 1)

        btc_events = [e for e in events if e["bar"]["symbol"] == "BTC"]
        eth_events = [e for e in events if e["bar"]["symbol"] == "ETH"]
        assert len(btc_events) == 1
        assert len(eth_events) == 1
        assert float(btc_events[0]["bar"]["close"]) == 100.0
        assert float(eth_events[0]["bar"]["close"]) == 200.0
