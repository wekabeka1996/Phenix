"""
Test TF propagation from bar to FEATURES_CALCULATED.

TF-BAR-SSOT-003: Verify FE propagates tf_sec correctly from BAR_CLOSED events.
"""
import pytest
import time
from types import SimpleNamespace
from decimal import Decimal
from unittest.mock import MagicMock, patch


@pytest.mark.parametrize("tf_sec", [180, 300])
def test_on_bar_closed_stores_per_symbol_tf(tf_sec, monkeypatch):
    """FE on_bar_closed stores bar with (symbol, tf_sec) key."""
    from apps.reference.domains.feature_engineering.bar_resampler import Bar
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    with patch.object(FeatureEngineering, '__init__', lambda self, **kw: None):
        fe = FeatureEngineering()
        fe.last_bar = {}
        fe.last_tick_data = {}  # BAR-FEATURES-001: on_bar_closed now uses last_tick_data
        fe.logger = MagicMock()

    symbol = "BTCUSDT"
    t0 = int(time.time() * 1000)
    bar = Bar(
        symbol=symbol,
        timeframe_sec=tf_sec,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        trade_count=1,
        start_ts_ms=t0,
        end_ts_ms=t0,
        gap_bars_skipped=0,
        is_gap_bar=False
    )

    fe.on_bar_closed(SimpleNamespace(pld={"bar": bar}))
    
    # Verify bar stored with (symbol, tf_sec) key
    assert (symbol, tf_sec) in fe.last_bar, f"Bar not stored for ({symbol}, {tf_sec})"
    assert fe.last_bar[(symbol, tf_sec)].timeframe_sec == tf_sec


def test_calculate_calls_with_tf_sec_zero_for_tick_features(monkeypatch):
    """FIX-TICK-FE-GATE-001: Tick-features use tf_sec=0, not bar-based TFs.
    
    _calculate_and_emit_features should call _calculate_and_emit_features_for_tf
    with tf_sec=0 (tick-level), not iterate over bar timeframes.
    """
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    called_tf_secs = []

    with patch.object(FeatureEngineering, '__init__', lambda self, **kw: None):
        fe = FeatureEngineering()
        fe.last_bar = {}  # Empty - no bars!
        fe.logger = MagicMock()
        
        # Mock the inner method to track calls
        def mock_emit_for_tf(symbol, tf_sec, current_tick, last_tick):
            called_tf_secs.append(tf_sec)
        fe._calculate_and_emit_features_for_tf = mock_emit_for_tf

    symbol = "BTCUSDT"
    t0 = int(time.time() * 1000)
    
    tick1 = {"symbol": symbol, "ts": t0, "price": "1"}
    tick2 = {"symbol": symbol, "ts": t0 + 1000, "price": "1.01"}

    fe._calculate_and_emit_features(symbol, tick2, tick1)

    # Should have called with tf_sec=0 (tick-level)
    assert 0 in called_tf_secs, "Expected call for tf_sec=0 (tick-features)"
    assert len(called_tf_secs) == 1, f"Expected 1 call with tf_sec=0, got {len(called_tf_secs)}"


def test_multi_tf_no_overwrite(monkeypatch):
    """FE stores bars per (symbol, tf_sec) without overwriting."""
    from apps.reference.domains.feature_engineering.bar_resampler import Bar
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    with patch.object(FeatureEngineering, '__init__', lambda self, **kw: None):
        fe = FeatureEngineering()
        fe.last_bar = {}
        fe.last_tick_data = {}  # BAR-FEATURES-001
        fe.logger = MagicMock()

    symbol = "BTCUSDT"
    t0 = int(time.time() * 1000)
    
    bar_180 = Bar(
        symbol=symbol,
        timeframe_sec=180,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        trade_count=1,
        start_ts_ms=t0,
        end_ts_ms=t0,
        gap_bars_skipped=0,
        is_gap_bar=False
    )
    bar_300 = Bar(
        symbol=symbol,
        timeframe_sec=300,
        open=Decimal("2"),  # Different open price
        high=Decimal("2"),
        low=Decimal("2"),
        close=Decimal("2"),
        volume=Decimal("2"),
        trade_count=2,
        start_ts_ms=t0,
        end_ts_ms=t0,
        gap_bars_skipped=0,
        is_gap_bar=False
    )
    
    fe.on_bar_closed(SimpleNamespace(pld={"bar": bar_180}))
    fe.on_bar_closed(SimpleNamespace(pld={"bar": bar_300}))
    
    # Both bars should be stored separately
    assert (symbol, 180) in fe.last_bar, "Bar 180 not stored"
    assert (symbol, 300) in fe.last_bar, "Bar 300 not stored"
    
    # Verify they are different bars (not overwritten)
    assert fe.last_bar[(symbol, 180)].open == Decimal("1"), "Bar 180 was overwritten"
    assert fe.last_bar[(symbol, 300)].open == Decimal("2"), "Bar 300 has wrong value"


def test_on_bar_closed_preserves_trade_counts_for_large_trade_imbalance(monkeypatch):
    """BAR-FEATURES-001: bar_tick must preserve buy_count/sell_count from last tick snapshot."""
    from apps.reference.domains.feature_engineering.bar_resampler import Bar
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    captured: dict = {}

    with patch.object(FeatureEngineering, "__init__", lambda self, **kw: None):
        fe = FeatureEngineering()
        fe.last_bar = {}
        fe.last_tick_data = {
            "BTCUSDT": {
                "bid_size": "1",
                "ask_size": "1",
                "buy_volume": "10",
                "sell_volume": "5",
                "buy_count": 7,
                "sell_count": 3,
                "buy_notional": "1000",
                "sell_notional": "500",
                "trades_dropped_out_of_order": 0,
                "bid": "1",
                "ask": "1",
            }
        }
        fe.logger = MagicMock()

        def _capture(symbol, tf_sec, current_tick, last_tick, bar_data=None):
            captured["symbol"] = symbol
            captured["tf_sec"] = tf_sec
            captured["current_tick"] = dict(current_tick)

        fe._calculate_and_emit_features_for_tf = _capture

    t0 = int(time.time() * 1000)
    bar = Bar(
        symbol="BTCUSDT",
        timeframe_sec=180,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        trade_count=1,
        start_ts_ms=t0,
        end_ts_ms=t0,
        gap_bars_skipped=0,
        is_gap_bar=False,
    )

    fe.on_bar_closed(SimpleNamespace(pld={"bar": bar}))

    assert captured["symbol"] == "BTCUSDT"
    assert captured["tf_sec"] == 180
    tick = captured["current_tick"]
    assert tick.get("buy_count") == 7
    assert tick.get("sell_count") == 3
    assert tick.get("buy_notional") == "1000"
    assert tick.get("sell_notional") == "500"
    assert tick.get("trades_dropped_out_of_order") == 0
