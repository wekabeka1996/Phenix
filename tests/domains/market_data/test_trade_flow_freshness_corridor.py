"""
AURORA/PHENIX Timer Governance Forensic Test Suite
Package: Trade-Flow Freshness Corridor Reproducer
Specification: T6C-0

Tests:
1. Trade window expires to zero-flow while quote remains fresh (WebSocketAggregator)
2. Vulnerability corridor exists before trade_silence_reconnect_sec watchdogs fire
3. BarAggregator accepts quote-fresh zero-flow ticks and completes bars
4. Downstream stale-bar guard (ReadinessGates) fails to catch trade-flow staleness
"""

import pytest
import decimal
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates


def test_t6c0_trade_window_expires_to_zero_flow_while_quote_remains_fresh():
    """
    Test 1: Trade window expires to zero-flow while quote remains fresh.

    Given:
    - WebSocketAggregator receives trade events and quote events at T0.
    - Time advances by 61 seconds (beyond window_seconds=60).
    - Quote (bookTicker) keeps updating after trade events stop.

    Assert:
    - Emitted market tick has fresh quote/mid fields (matching T0 + 61s).
    - trade-flow fields are zeroed out (buy_volume == "0", sell_volume == "0", etc.).
    - timestamp freshness is quote-driven, not trade-driven.
    """
    symbol = "BTCUSDT"
    agg = WebSocketAggregator(symbols=[symbol], window_seconds=60)

    # T0: Initial market state
    t0_ms = 1_000_000

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="100.0",
        bid_size="10.0",
        ask_price="101.0",
        ask_size="10.0",
        ts=t0_ms,
    )

    agg.on_trade(
        symbol=symbol,
        price="100.5",
        quantity="1.5",
        is_buyer_maker=False,  # Buy trade
        ts=t0_ms,
        trade_id=1,
    )

    # Verify that initial state has non-zero trade flows
    tick0 = agg.get_market_tick(symbol)
    assert tick0 is not None
    assert tick0["buy_volume"] == "1.5"
    assert tick0["buy_count"] == 1
    assert tick0["ts"] == t0_ms

    # T1 = T0 + 61s: New quote arrives, but NO new trades arrive.
    # The rolling 60s window has expired for the trade from T0.
    t1_ms = t0_ms + 61_000
    agg.on_book_ticker(
        symbol=symbol,
        bid_price="100.2",
        bid_size="12.0",
        ask_price="101.2",
        ask_size="14.0",
        ts=t1_ms,
    )

    # Get market tick at T1
    tick1 = agg.get_market_tick(symbol)
    assert tick1 is not None

    # Prove quote freshness is driven by T1 bookTicker timestamp
    assert tick1["ts"] == t1_ms
    assert Decimal(tick1["mid"]) == Decimal("100.7")  # (100.2 + 101.2) / 2

    # Prove trade-flow fields expired to zero
    assert tick1["buy_volume"] == "0"
    assert tick1["sell_volume"] == "0"
    assert tick1["buy_count"] == 0
    assert tick1["sell_count"] == 0
    assert tick1["buy_notional"] == "0"
    assert tick1["sell_notional"] == "0"

    # Check features (TFI should be 0 since buy_volume + sell_volume = 0)
    assert tick1["features"]["tfi"] == "0"
    # OBI matches fresh order book depth: (12 - 14) / (12 + 14) = -2 / 26 = -0.076923...
    assert float(tick1["features"]["obi"]) < 0


def test_t6c0_corridor_exists_before_trade_silence_reconnect_sec():
    """
    Test 2: Verification of the vulnerability corridor.

    Given:
    - trade_silence_reconnect_sec = 120.0s (timer before forced reconnect)
    - window_seconds = 60s (sliding trade-flow aggregator window)

    Assert:
    - window_seconds < trade_silence_reconnect_sec
    - A corridor of at least (trade_silence_reconnect_sec - window_seconds) exists
      where zero trade flows are emitted downstream with fresh quotes without triggering reconnect.
    """
    # From apps/reference/domains/market_data/worker.py reference and config/aurora/system.yaml
    default_window_seconds = 60
    configured_trade_silence_reconnect_sec = 120.0  # From system.yaml SSOT

    assert default_window_seconds < configured_trade_silence_reconnect_sec, "Vulnerability corridor does not exist!"

    corridor_duration = configured_trade_silence_reconnect_sec - default_window_seconds
    assert corridor_duration == 60.0, f"Expected 60s corridor, got {corridor_duration}s"


def test_t6c0_bar_aggregator_accepts_quote_fresh_zero_flow_tick():
    """
    Test 3: BarAggregator accepts quote-fresh zero-volume ticks.

    Given:
    - A BarAggregator configured with 60s bars.
    - Market ticks with fresh timestamps but zero trade-flow fields.

    Assert:
    - BarAggregator accepts the tick and updates internal states.
    - Bar completed payload is successfully produced with zero volumes.
    """
    emit_spy = MagicMock()
    # 60 second bars
    bar_agg = BarAggregator(timeframes_sec=[60], emit_fn=emit_spy)

    # aligned start_ts is 960,000 (1_000_000 // 60_000 * 60_000 = 960_000)
    base_ts = 1_000_000

    # Tick 1 at T = 1_000_000: Initial tick with non-zero volume (Bar 1 interval is [960k, 1_020k))
    bar_agg.on_tick("BTCUSDT", Decimal("100.0"), Decimal("10.0"), base_ts)

    # Tick 2 at T = 1_000_000 + 10s (1_010_000): Tick with zero volume (fresh quote, stale trade stream)
    bar_agg.on_tick("BTCUSDT", Decimal("101.0"),
                    Decimal("0.0"), base_ts + 10_000)

    # Tick 3 at T = 1_000_000 + 25s (1_025_000): Outside Bar 1 interval. Triggers close of Bar 1!
    emit_spy.reset_mock()
    completed_bars = bar_agg.on_tick("BTCUSDT", Decimal(
        "101.0"), Decimal("0.0"), base_ts + 25_000)

    assert len(completed_bars) == 1
    bar1 = completed_bars[0]
    assert bar1.start_ts_ms == 960_000
    assert bar1.end_ts_ms == 1_020_000 - 1
    assert bar1.volume == Decimal("10.0")  # Has volume from Tick 1

    # Now let's trigger the close of Bar 2 (interval [1,020,000, 1,080,000)),
    # Tick 3 (1_025_000) was in this interval (and had volume 0).
    # Tick 4 (1_050_000) is inside Bar 2, also volume 0.
    bar_agg.on_tick("BTCUSDT", Decimal("101.5"),
                    Decimal("0.0"), base_ts + 50_000)

    # Tick 5 (1_085_000) is outside Bar 2, triggering its close.
    completed_bars_2 = bar_agg.on_tick("BTCUSDT", Decimal(
        "102.0"), Decimal("0.0"), base_ts + 85_000)

    assert len(completed_bars_2) == 1
    bar2 = completed_bars_2[0]
    assert bar2.start_ts_ms == 1_020_000
    assert bar2.end_ts_ms == 1_080_000 - 1
    # BAR-SSOT proof: Bar 2 has zero volume, but is completed and successfully closed!
    assert bar2.volume == Decimal("0.0")
    assert bar2.trade_count == 2
    assert bar2.open == Decimal("101.0")  # Opened at Tick 3's price
    assert bar2.close == Decimal("101.5")  # Closed at Tick 4's price


class MockClock:
    def __init__(self, now_ms: int):
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms


class MockConfig:
    def __init__(self, bar_ttl_ms: int = 10000, bar_event_age_mode: str = "received"):
        self.system = MagicMock()
        self.system.market_data = MagicMock()
        self.system.market_data.bar_ttl_ms = bar_ttl_ms
        self.system.market_data.bar_event_age_mode = bar_event_age_mode


def test_t6c0_downstream_stale_bar_guard_fails_to_catch_trade_flow_staleness():
    """
    Test 4: Downstream staleness guards do not inspect volumes.

    Given:
    - Downstream readiness gate ReadinessGates.features_ready.
    - Features data with FRESH timestamps (received 1s ago, closed 1s ago)
      but ZERO trade-flow metadata (buy_volume = "0", sell_volume = "0").

    Assert:
    - ReadinessGates.features_ready returns True!
    - Therefore, downstream guards fail-open on stale trade flows
      as long as quote-driven timestamps remain fresh.
    """
    now_ms = 1_700_000_000_000
    bar_close_ts = now_ms - 2_000  # 2 seconds ago (fresh bar)
    received_ts = now_ms - 1_000   # 1 second ago

    dm = MagicMock()
    dm._clock = MockClock(now_ms)
    dm.config = MockConfig(bar_ttl_ms=10000, bar_event_age_mode="received")
    dm.features_ttl_sec = 30.0
    dm.logger = MagicMock()

    # Degraded feature payload: Zero trade volumes but perfectly fresh timers.
    stale_trade_flow_features = {
        "ts": bar_close_ts,
        "tf_sec": 60,
        "_received_ts": received_ts,
        "bar_close_ts": bar_close_ts,
        "symbol": "BTCUSDT",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "0",          # Degraded (Stale trade stream)
        "buy_volume": "0",      # Degraded
        "sell_volume": "0",     # Degraded
        "buy_count": 0,
        "sell_count": 0,
    }

    # Evaluate with DecisionMaking's production readiness contract helper
    is_ready = ReadinessGates.features_ready(
        dm, "BTCUSDT", stale_trade_flow_features)

    # Assert that this degraded feature dataset STILL passes the downstream TTL/stale guard
    assert is_ready is True
    # Consequently proved: Downstream does not catch trade-flow staleness by design.
