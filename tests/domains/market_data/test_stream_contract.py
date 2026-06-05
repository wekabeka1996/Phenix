from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
from apps.reference.domains.market_data.worker import MarketDataWorker


class MockQueue:
    def put_nowait(self, item):
        return None

    def get_nowait(self):
        raise RuntimeError("unused")

    def qsize(self):
        return 0


def _worker_config(*, websocket_streams, include_trade_silence=True):
    market_data_system = {
        "ws_heartbeat_sec": 20.0,
        "ws_receive_timeout_sec": 60.0,
    }
    if include_trade_silence:
        market_data_system["trade_silence_reconnect_sec"] = 120.0

    return {
        "instruments": {"BTCUSDT": {}},
        "system": {"market_data": market_data_system},
        "trading": {
            "market_data": {
                "poll_interval_sec": 1,
                "websocket_streams": list(websocket_streams),
                "macro_sync": {"anchors": []},
            },
            "domain_configuration": {"market_data": {"trading_mode": "live"}},
        },
        "binance_api": {},
    }


def _connector_config(*, websocket_streams):
    return SimpleNamespace(
        trading=SimpleNamespace(
            market_data=SimpleNamespace(
                poll_interval_sec=1,
                websocket_streams=list(websocket_streams),
                macro_sync=SimpleNamespace(anchors=[]),
            )
        ),
        instruments={"BTCUSDT": {}},
        binance_api=SimpleNamespace(
            live=SimpleNamespace(api_key="k", api_secret="s",
                                 rest_url="https://example.invalid"),
            testnet=SimpleNamespace(
                api_key="k", api_secret="s", rest_url="https://example.invalid"),
        ),
    )


def test_worker_subscribe_payload_uses_configured_trade_stream():
    worker = MarketDataWorker(
        MockQueue(),
        _worker_config(websocket_streams=["bookTicker", "trade"]),
        MagicMock(),
    )

    payload = worker._make_subscribe_payload()

    assert payload == {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@bookTicker", "btcusdt@trade"],
        "id": 1,
    }


def test_worker_accepts_trade_event_when_trade_stream_is_configured():
    worker = MarketDataWorker(
        MockQueue(),
        _worker_config(websocket_streams=["bookTicker", "trade"]),
        MagicMock(),
    )

    worker.on_tick(
        {
            "e": "trade",
            "s": "BTCUSDT",
            "p": "78300.50",
            "q": "0.006",
            "m": False,
            "T": 1777035615715,
            "t": 123,
        }
    )

    snapshot = worker._aggregator.get_trade_observability_snapshot("BTCUSDT")
    assert snapshot is not None
    assert snapshot["aggtrade_raw_seen"] == 1
    assert snapshot["aggtrade_route_attempted"] == 1
    assert snapshot["on_trade_called"] == 1
    assert snapshot["trade_accepted"] == 1
    assert snapshot["buy_count"] == 1
    assert snapshot["buy_volume"] == "0.006"


def test_worker_accepts_aggtrade_event_when_aggtrade_stream_is_configured():
    worker = MarketDataWorker(
        MockQueue(),
        _worker_config(websocket_streams=["bookTicker", "aggTrade"]),
        MagicMock(),
    )

    worker.on_tick(
        {
            "e": "aggTrade",
            "s": "BTCUSDT",
            "p": "78300.50",
            "q": "0.006",
            "m": False,
            "T": 1777035615715,
            "a": 321,
        }
    )

    snapshot = worker._aggregator.get_trade_observability_snapshot("BTCUSDT")
    assert snapshot is not None
    assert snapshot["on_trade_called"] == 1
    assert snapshot["trade_accepted"] == 1
    assert snapshot["buy_count"] == 1


def test_worker_requires_explicit_trade_silence_reconnect_sec():
    with pytest.raises(ValueError, match="trade_silence_reconnect_sec"):
        MarketDataWorker(
            MockQueue(),
            _worker_config(
                websocket_streams=["bookTicker", "trade"],
                include_trade_silence=False,
            ),
            MagicMock(),
        )


def test_connector_subscribe_payload_uses_configured_trade_stream():
    with patch(
        "apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping",
        return_value="live",
    ), patch("apps.reference.domains.market_data.market_data_connector.BinanceAdapter"):
        connector = MarketDataConnector(
            MagicMock(),
            _connector_config(websocket_streams=["bookTicker", "trade"]),
        )

    payload = connector._make_subscribe_payload()

    assert payload == {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@bookTicker", "btcusdt@trade"],
        "id": 1,
    }


def test_connector_accepts_trade_event_when_trade_stream_is_configured():
    with patch(
        "apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping",
        return_value="live",
    ), patch("apps.reference.domains.market_data.market_data_connector.BinanceAdapter"):
        connector = MarketDataConnector(
            MagicMock(),
            _connector_config(websocket_streams=["bookTicker", "trade"]),
        )

    connector._handle_message(
        {
            "e": "trade",
            "s": "BTCUSDT",
            "p": "78300.50",
            "q": "0.006",
            "m": False,
            "T": 1777035615715,
            "t": 123,
        }
    )

    snapshot = connector.aggregator.get_trade_observability_snapshot("BTCUSDT")
    assert snapshot is not None
    assert snapshot["on_trade_called"] == 1
    assert snapshot["trade_accepted"] == 1
    assert snapshot["buy_count"] == 1
    assert snapshot["buy_volume"] == "0.006"


def test_connector_accepts_aggtrade_event_when_aggtrade_stream_is_configured():
    with patch(
        "apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping",
        return_value="live",
    ), patch("apps.reference.domains.market_data.market_data_connector.BinanceAdapter"):
        connector = MarketDataConnector(
            MagicMock(),
            _connector_config(websocket_streams=["bookTicker", "aggTrade"]),
        )

    connector._handle_message(
        {
            "e": "aggTrade",
            "s": "BTCUSDT",
            "p": "78300.50",
            "q": "0.006",
            "m": False,
            "T": 1777035615715,
            "a": 123,
        }
    )

    snapshot = connector.aggregator.get_trade_observability_snapshot("BTCUSDT")
    assert snapshot is not None
    assert snapshot["on_trade_called"] == 1
    assert snapshot["trade_accepted"] == 1


def test_websocket_aggregator_returns_zero_volume_tick_when_trade_window_expires():
    agg = WebSocketAggregator(symbols=["BTCUSDT"], window_seconds=60)

    agg.on_book_ticker(
        symbol="BTCUSDT",
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_000_000,
    )
    agg.on_trade(
        symbol="BTCUSDT",
        price="100.0",
        quantity="1.0",
        is_buyer_maker=False,
        ts=1_000_010,
        trade_id=1,
    )
    agg.on_book_ticker(
        symbol="BTCUSDT",
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_061_500,
    )
    agg.state["BTCUSDT"]["last_trade_ts_ms"] = 1_061_500
    agg.state["BTCUSDT"]["last_price_ts_ms"] = 1_061_500

    tick = agg.get_market_tick("BTCUSDT")

    assert tick is not None
    assert tick["buy_count"] == 0
    assert tick["sell_count"] == 0
    assert tick["buy_volume"] == "0"
    assert tick["sell_volume"] == "0"
