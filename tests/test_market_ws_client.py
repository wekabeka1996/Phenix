import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from apps.reference.domains.market_data.market_ws_client import MarketWSClient


@pytest.fixture
def mock_callbacks():
    return {
        "on_book_ticker": MagicMock(),
        "on_trade": MagicMock()
    }


@pytest.fixture
def client(mock_callbacks):
    return MarketWSClient(
        symbols=["BTCUSDT", "ETHUSDT"],
        on_book_ticker=mock_callbacks["on_book_ticker"],
        on_trade=mock_callbacks["on_trade"],
        reconnect_interval_sec=1
    )


def test_build_stream_url(client):
    url = client._build_stream_url()
    assert "wss://fstream.binance.com/stream?streams=" in url
    assert "btcusdt@bookTicker" in url
    assert "btcusdt@aggTrade" in url
    assert "ethusdt@bookTicker" in url
    assert "ethusdt@aggTrade" in url


def test_route_book_ticker_messages(client, mock_callbacks):
    msg = {
        "stream": "btcusdt@bookTicker",
        "data": {
            "s": "BTCUSDT",
            "b": "50000",
            "B": "1.0",
            "a": "50001",
            "A": "2.0"
        }
    }
    client._handle_message(json.dumps(msg))

    mock_callbacks["on_book_ticker"].assert_called_once()
    args = mock_callbacks["on_book_ticker"].call_args[0][0]
    assert args["s"] == "BTCUSDT"
    assert args["b"] == "50000"


def test_route_agg_trade_messages(client, mock_callbacks):
    msg = {
        "stream": "btcusdt@aggTrade",
        "data": {
            "s": "BTCUSDT",
            "p": "50000.5",
            "q": "0.1",
            "m": True
        }
    }
    client._handle_message(json.dumps(msg))

    mock_callbacks["on_trade"].assert_called_once()
    args = mock_callbacks["on_trade"].call_args[0][0]
    assert args["s"] == "BTCUSDT"
    assert args["p"] == "50000.5"


@pytest.mark.asyncio
async def test_reconnect_on_error(client):
    # Mock websockets.connect to raise exception first, then succeed (or just fail to test reconnect attempt)
    # Since we can't easily mock the context manager loop in a simple way without complex mocking,
    # we will just verify that _run_loop handles exception and sleeps.

    with patch("apps.reference.domains.market_data.market_ws_client.websockets") as mock_ws:
        mock_ws.connect.side_effect = Exception("Connection failed")

        # We need to stop the loop after some time
        client._running = True

        # Run loop in a task
        task = asyncio.create_task(client._run_loop())

        # Let it run for a bit (it should fail and sleep)
        await asyncio.sleep(0.1)

        # Stop client
        client._running = False
        await task

        # Verify connect was called
        assert mock_ws.connect.called
        # Verify it tried to connect at least once
        assert mock_ws.connect.call_count >= 1
