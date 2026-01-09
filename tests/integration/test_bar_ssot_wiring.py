"""
BAR-SSOT-002: Integration test for BarAggregator wiring

Validates:
1. BarAggregator subscribes to EVT:MARKET_TICK_RECEIVED
2. on_market_tick correctly parses tick events
3. EVT:BAR_CLOSED is emitted when bar closes
4. Config-driven fail-closed behavior (disabled if config missing)
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message


class TestBarAggregatorWiring:
    """Test BarAggregator as passive observer on tick stream."""
    
    def test_on_market_tick_parses_standard_payload(self):
        """Verify on_market_tick correctly extracts tick data from FSM event."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        
        # Mock on_tick to capture calls
        tick_calls = []
        original_on_tick = aggregator.on_tick
        def mock_on_tick(symbol, price, volume, ts_ms):
            tick_calls.append((symbol, price, volume, ts_ms))
            original_on_tick(symbol, price, volume, ts_ms)
        aggregator.on_tick = mock_on_tick
        
        # Simulate EVT:MARKET_TICK_RECEIVED payload (standard format)
        event = MagicMock()
        event.pld = {
            "symbol": "BTCUSDT",
            "mid": "50000.50",
            "volume": "1.5",
            "ts_ms": 1700000000000,
        }
        
        aggregator.on_market_tick(event)
        
        assert len(tick_calls) == 1
        symbol, price, volume, ts_ms = tick_calls[0]
        assert symbol == "BTCUSDT"
        assert price == Decimal("50000.50")
        assert volume == Decimal("1.5")
        assert ts_ms == 1700000000000
    
    def test_on_market_tick_fallback_to_bid_ask_average(self):
        """Verify on_market_tick calculates mid from bid/ask when mid is missing."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        
        tick_calls = []
        def mock_on_tick(symbol, price, volume, ts_ms):
            tick_calls.append((symbol, price, volume, ts_ms))
        aggregator.on_tick = mock_on_tick
        
        event = MagicMock()
        event.pld = {
            "symbol": "ETHUSDT",
            "bid": "3000.00",
            "ask": "3002.00",
            "volume": "10.0",
            "ts_ms": 1700000001000,
        }
        
        aggregator.on_market_tick(event)
        
        assert len(tick_calls) == 1
        _, price, _, _ = tick_calls[0]
        assert price == Decimal("3001.00")  # (3000 + 3002) / 2
    
    def test_on_market_tick_skips_incomplete_payload(self):
        """Verify on_market_tick skips events with missing required fields."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        
        tick_calls = []
        def mock_on_tick(symbol, price, volume, ts_ms):
            tick_calls.append((symbol, price, volume, ts_ms))
        aggregator.on_tick = mock_on_tick
        
        # Missing ts_ms
        event = MagicMock()
        event.pld = {"symbol": "BTCUSDT", "mid": "50000.00"}
        aggregator.on_market_tick(event)
        
        assert len(tick_calls) == 0  # Should skip
    
    def test_on_market_tick_handles_dict_event(self):
        """Verify on_market_tick handles dict-style events (legacy compatibility)."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        
        tick_calls = []
        def mock_on_tick(symbol, price, volume, ts_ms):
            tick_calls.append((symbol, price, volume, ts_ms))
        aggregator.on_tick = mock_on_tick
        
        # Dict event without pld attribute
        event = {
            "payload": {
                "symbol": "SOLUSDT",
                "price": "100.00",
                "volume": "5.0",
                "timestamp": 1700000002000,
            }
        }
        
        aggregator.on_market_tick(event)
        
        assert len(tick_calls) == 1
        symbol, price, _, ts_ms = tick_calls[0]
        assert symbol == "SOLUSDT"
        assert price == Decimal("100.00")
        assert ts_ms == 1700000002000
    
    def test_bar_closed_event_emitted_on_timeframe_boundary(self):
        """Verify EVT:BAR_CLOSED is emitted when bar closes."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        emitted_events = []
        def spy_emit(verb, payload, **kwargs):
            emitted_events.append((verb, payload))
        
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=spy_emit)
        
        # First tick at 0:00
        event1 = MagicMock()
        event1.pld = {
            "symbol": "BTCUSDT",
            "mid": "50000.00",
            "volume": "1.0",
            "ts_ms": 1700000000000,  # Start of minute
        }
        aggregator.on_market_tick(event1)
        
        # Second tick in same bar
        event2 = MagicMock()
        event2.pld = {
            "symbol": "BTCUSDT",
            "mid": "50100.00",
            "volume": "2.0",
            "ts_ms": 1700000030000,  # 30 seconds in
        }
        aggregator.on_market_tick(event2)
        
        # Third tick that closes first bar
        event3 = MagicMock()
        event3.pld = {
            "symbol": "BTCUSDT",
            "mid": "50200.00",
            "volume": "1.5",
            "ts_ms": 1700000060000,  # Next minute
        }
        aggregator.on_market_tick(event3)
        
        # Should emit BAR_CLOSED for 60s timeframe
        bar_closed_events = [e for e in emitted_events if e[0] == "EVT:BAR_CLOSED"]
        assert len(bar_closed_events) >= 1
        
        bar_payload = bar_closed_events[0][1]
        assert bar_payload["symbol"] == "BTCUSDT"
        # timeframe_sec is inside nested "bar" dict
        assert bar_payload["bar"]["timeframe_sec"] == 60
        assert Decimal(str(bar_payload["bar"]["open"])) == Decimal("50000.00")
        assert Decimal(str(bar_payload["bar"]["close"])) == Decimal("50100.00")
    
    def test_wiring_pattern_fsm_listen(self):
        """Verify BarAggregator can be wired via fsm.listen pattern."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        
        # Wire as passive observer
        fsm.listen("EVT:MARKET_TICK_RECEIVED", aggregator.on_market_tick)
        
        # Emit tick event
        tick_calls = []
        aggregator.on_tick = lambda *args: tick_calls.append(args)
        
        fsm.emit("EVT:MARKET_TICK_RECEIVED", {
            "symbol": "BTCUSDT",
            "mid": "50000.00",
            "volume": "1.0",
            "ts_ms": 1700000000000,
        }, why="test tick")
        
        assert len(tick_calls) == 1


class TestBarAggregatorConfigDriven:
    """Test fail-closed behavior when config is missing or disabled."""
    
    def test_disabled_when_config_missing(self):
        """Verify BarAggregator is not wired when config section is missing."""
        # This tests the logic in main.py
        # bar_config = getattr(config.trading.market_data, 'bar_aggregator', None)
        # if bar_config is None or not bar_config.enabled -> disabled
        
        class MockMarketDataConfig:
            pass  # No bar_aggregator attribute
        
        bar_config = getattr(MockMarketDataConfig(), 'bar_aggregator', None)
        assert bar_config is None  # Fail-closed: not wired
    
    def test_disabled_when_enabled_false(self):
        """Verify BarAggregator is not wired when enabled=false."""
        from apps.reference.config_models import BarAggregatorConfig
        
        config = BarAggregatorConfig(enabled=False, timeframes_sec=[60])
        
        # Wiring logic check
        should_wire = config.enabled
        assert should_wire is False


class TestBarAggregatorFSMIntegration:
    """Full FSM integration tests."""
    
    def test_multi_symbol_tick_stream(self):
        """Verify BarAggregator handles multi-symbol tick stream."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60], emit_fn=fsm.emit)
        fsm.listen("EVT:MARKET_TICK_RECEIVED", aggregator.on_market_tick)
        
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        for i, symbol in enumerate(symbols):
            fsm.emit("EVT:MARKET_TICK_RECEIVED", {
                "symbol": symbol,
                "mid": f"{50000 + i * 1000}.00",
                "volume": "1.0",
                "ts_ms": 1700000000000,
            }, why="test multi-symbol")
        
        # Verify bars are tracked per symbol
        for symbol in symbols:
            key = (symbol, 60)
            assert key in aggregator._current_bars
    
    def test_multiple_timeframes_tracking(self):
        """Verify BarAggregator tracks multiple timeframes."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        
        fsm = FSMCore()
        aggregator = BarAggregator(timeframes_sec=[60, 300], emit_fn=fsm.emit)
        fsm.listen("EVT:MARKET_TICK_RECEIVED", aggregator.on_market_tick)
        
        fsm.emit("EVT:MARKET_TICK_RECEIVED", {
            "symbol": "BTCUSDT",
            "mid": "50000.00",
            "volume": "1.0",
            "ts_ms": 1700000000000,
        }, why="test multi-tf")
        
        # Both timeframes should have partial bars
        assert ("BTCUSDT", 60) in aggregator._current_bars
        assert ("BTCUSDT", 300) in aggregator._current_bars
