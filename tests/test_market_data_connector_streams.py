from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    from apps.reference.domains.market_data import market_data_connector as mdc
except (ModuleNotFoundError, ImportError) as exc:  # pragma: no cover
    pytest.skip(f"MarketDataConnector deps not available: {exc}", allow_module_level=True)

if getattr(mdc, "aiohttp", None) is None:  # pragma: no cover
    pytest.skip("aiohttp not available for MarketDataConnector", allow_module_level=True)


def _make_config(websocket_streams: list[str]) -> SimpleNamespace:
    env = SimpleNamespace(
        api_key="test-key",
        api_secret="test-secret",
        rest_url="https://example.test",
    )
    trading_market_data = SimpleNamespace(
        poll_interval_sec=5.0,
        websocket_streams=list(websocket_streams),
        macro_sync=SimpleNamespace(anchors=["BTCUSDT"]),
    )
    trading = SimpleNamespace(
        mode="hybrid_live_data_testnet_exec",
        market_data=trading_market_data,
        domain_configuration=SimpleNamespace(
            market_data=SimpleNamespace(trading_mode="live")
        ),
    )
    return SimpleNamespace(
        instruments={"BTCUSDT": {}, "ETHUSDT": {}},
        trading=trading,
        binance_api=SimpleNamespace(live=env, testnet=env),
    )


def test_connector_subscribe_payload_uses_configured_streams():
    with patch.object(mdc, "BinanceAdapter"):
        connector = mdc.MarketDataConnector(
            MagicMock(),
            _make_config(["bookTicker", "trade"]),
        )

    assert connector.trade_event_names == {"trade"}

    payload = connector._make_subscribe_payload()

    assert payload["method"] == "SUBSCRIBE"
    assert payload["id"] == 1
    assert "btcusdt@bookTicker" in payload["params"]
    assert "btcusdt@trade" in payload["params"]
    assert "ethusdt@trade" in payload["params"]
    assert "btcusdt@aggTrade" not in payload["params"]


def test_connector_handles_raw_trade_when_configured():
    with patch.object(mdc, "BinanceAdapter"):
        connector = mdc.MarketDataConnector(
            MagicMock(),
            _make_config(["bookTicker", "trade"]),
        )

    connector.aggregator.on_trade = MagicMock()

    connector._handle_message(
        {
            "e": "trade",
            "s": "BTCUSDT",
            "p": "95000.5",
            "q": "0.1",
            "m": False,
            "t": 321,
            "T": 1234567890000,
        }
    )

    connector.aggregator.on_trade.assert_called_once_with(
        symbol="BTCUSDT",
        price="95000.5",
        quantity="0.1",
        is_buyer_maker=False,
        ts=1234567890000,
        trade_id=321,
    )


def test_connector_requires_trade_or_aggtrade_stream():
    with patch.object(mdc, "BinanceAdapter"):
        with pytest.raises(ValueError, match="trade or aggTrade"):
            mdc.MarketDataConnector(
                MagicMock(),
                _make_config(["bookTicker"]),
            )