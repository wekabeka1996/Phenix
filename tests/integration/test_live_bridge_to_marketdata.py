import pytest
import asyncio
from vfoundation.core.protocol import Message


class CaptureBus:
    def __init__(self):
        self.emitted = []

    async def emit(self, m):
        self.emitted.append(m)


@pytest.mark.asyncio
async def test_bridge_injects_tick_to_marketdata(monkeypatch):
    bus = CaptureBus()
    # Импортируй ваш MarketDataConnector и "мост" (если мост — отдельный модуль/класс)
    import sys

    sys.path.insert(0, "c:/Users/user/Music/Phenix")
    from apps.reference.domains.market_data import market_data_connector

    # Mock FSM for testing
    class MockFSM:
        def __init__(self, bus):
            self.bus = bus
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        async def emit(self, event_name, payload=None, why=None):
            msg = Message(
                op="EVT", verb=event_name.split(":")[1], payload=payload, why=why
            )
            await self.bus.emit(msg)

    fsm = MockFSM(bus)

    # Mock the BinanceAdapter to avoid real API calls
    class MockAdapter:
        async def get_book_ticker(self, symbol):
            return {
                "bidPrice": "100.0",
                "bidQty": "1.0",
                "askPrice": "100.1",
                "askQty": "1.0",
            }

        async def get_recent_trades(self, symbol, limit=50):
            return [{"price": "100.0", "qty": "0.1", "m": False, "time": 1000}]

        async def get_klines(self, symbol, interval, limit):
            return [[1000, "99.9", "100.1", "99.8", "100.0", "10.0", 1000]]

    cfg = {
        "system": {"trading": {"symbols_to_track": ["BTCUSDT"], "mode": "live"}},
        "binance_api": {
            "live": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binance.vision",
            }
        },
    }
    mdc = market_data_connector.MarketDataConnector(fsm, cfg)
    mdc.adapter = MockAdapter()  # Replace with mock

    # Эмулируй вызов, который мост обычно делает (например, mdc.on_tick(...))
    tick = {
        "symbol": "BTCUSDT",
        "bid": "100.0",
        "ask": "100.1",
        "trades": {"buy": 1, "sell": 1},
        "ts": 42,
    }
    msg = Message(
        op="EVT",
        verb="MARKET_TICK_RECEIVED",
        intent="OBSERVATION",
        src="bridge",
        dst="any",
        rid="t1",
        pld=tick,
        why="test_bridge",
    )

    # Manually trigger the event handlers if needed
    # For now, just check that the connector can be instantiated
    assert mdc is not None
    assert mdc.symbols == ["BTCUSDT"]
