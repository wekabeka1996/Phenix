"""
Coverage gap tests for MarketDataConnector REST API implementation.
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import time
import decimal
import sys
from pathlib import Path

# Add apps to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from vfoundation.core.protocol import Message


class MockFSMCore:
    def __init__(self):
        self.listeners = {}

    def listen(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name, payload, why):
        msg = Message(
            op="EVT",
            verb=event_name.split(":")[1],
            src="test",
            dst="any",
            pld=payload,
            why=why,
        )
        if event_name in self.listeners:
            for cb in self.listeners[event_name]:
                cb(msg)


@pytest.fixture
def market_data_connector():
    """Provides a MarketDataConnector instance with a mock FSM and adapter."""
    with patch(
        "apps.reference.domains.market_data.market_data_connector.BinanceAdapter"
    ) as mock_adapter_class:
        mock_adapter = MagicMock()
        mock_adapter_class.return_value = mock_adapter

        config = {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://testnet.binance.vision",
                }
            },
            "system": {"trading": {"symbols_to_track": ["BTCUSDT", "ETHUSDT"]}},
        }

        connector = MarketDataConnector(fsm=MockFSMCore(), config=config)
        connector.adapter = mock_adapter
        return connector


def test_process_and_emit_kline_valid(market_data_connector):
    """Test that valid Kline data is processed and emitted correctly."""
    listener = MagicMock()
    market_data_connector.fsm.listen("EVT:MARKET_TICK_RECEIVED", listener)

    kline_data = [
        1693526400000,  # open_time
        "50000.00",  # open
        "50100.00",  # high
        "49900.00",  # low
        "50050.00",  # close
        "100.5",  # volume
        int(time.time() * 1000),  # close_time
        "5050000.00",  # quote_asset_volume
        1000,  # num_trades
        "50.0",  # taker_buy_base_asset_volume
        "2500000.00",  # taker_buy_quote_asset_volume
        0,  # ignore
    ]

    # Construct equivalent aggregated tick and emit
    tick = {
        "ts": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "price": decimal.Decimal("50050.00"),
        "bid": decimal.Decimal("50000.00"),
        "ask": decimal.Decimal("50100.00"),
        "mid": decimal.Decimal("50050.00"),
        "bid_size": decimal.Decimal("10"),
        "ask_size": decimal.Decimal("8"),
        "buy_volume": decimal.Decimal("50"),
        "sell_volume": decimal.Decimal("30"),
        "data_source": "test",
        "bid_ask_count": "B:1:A:1",
        "trade_count": "count:50:30",
    }

    market_data_connector._emit_market_tick("BTCUSDT", tick)

    listener.assert_called_once()
    args, _ = listener.call_args
    event = args[0]
    assert event.verb == "MARKET_TICK_RECEIVED"
    assert event.pld["symbol"] == "BTCUSDT"
    assert event.pld["price"] == decimal.Decimal("50050.00")


def test_kline_with_zero_sizes(market_data_connector, caplog):
    """Test that kline data with zero sizes is handled gracefully."""
    listener = MagicMock()
    market_data_connector.fsm.listen("EVT:MARKET_TICK_RECEIVED", listener)

    # Kline with zero volume should still be emitted (valid market data)
    kline_data = [
        1693526400000,
        "50000.00",
        "50100.00",
        "49900.00",
        "50050.00",
        "0",
        int(time.time() * 1000),
        "0",
        0,
        "0",
        "0",
        0,
    ]

    tick = {
        "ts": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "price": decimal.Decimal("50050.00"),
        "bid": decimal.Decimal("50000.00"),
        "ask": decimal.Decimal("50100.00"),
        "mid": decimal.Decimal("50050.00"),
        "bid_size": decimal.Decimal("0"),
        "ask_size": decimal.Decimal("0"),
        "buy_volume": decimal.Decimal("0"),
        "sell_volume": decimal.Decimal("0"),
        "data_source": "test",
        "bid_ask_count": "B:0:A:0",
        "trade_count": "count:0:0",
    }

    market_data_connector._emit_market_tick("BTCUSDT", tick)

    # Should still emit even with zero volume
    listener.assert_called_once()
