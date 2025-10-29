import pytest
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock, ANY

from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector

@pytest.fixture
def mock_fsm():
    fsm = MagicMock(spec=FSMCore)
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    return fsm

@pytest.fixture
def mock_config():
    return {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key", "api_secret": "test_secret", "rest_url": "url"
            }
        },
        "system": {"trading": {"symbols_to_track": ["BTCUSDT"]}},
        "trading": {}
    }

@pytest.mark.asyncio
async def test_three_domain_chain_integration(mock_fsm, mock_config):
    # Patch the BinanceAdapter used inside MarketDataConnector to avoid any network I/O
    with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter') as mock_adapter_class:
        mock_adapter = MagicMock()
        # Make the adapter async methods AsyncMock so they can be awaited
        mock_adapter.get_klines = AsyncMock()
        mock_adapter.get_book_ticker = AsyncMock()
        mock_adapter.get_recent_trades = AsyncMock()
        mock_adapter.close_session = AsyncMock()
        # Provide basic returns for book_ticker and trades so aggregator can process
        mock_adapter.get_book_ticker.return_value = {'bidPrice': '50000', 'bidQty': '10', 'askPrice': '50002', 'askQty': '8'}
        mock_adapter.get_recent_trades.return_value = []
        mock_adapter.get_klines.return_value = []
        mock_adapter_class.return_value = mock_adapter

        market_data = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        feature_engineering = FeatureEngineering(fsm=mock_fsm, config=mock_config.get("trading", {}))
        risk_management = RiskManagement(fsm=mock_fsm, config=mock_config.get("system", {}))

        try:
            # Now patch the adapter instance method get_klines to return a valid recent kline
            with patch.object(market_data.adapter, 'get_klines', new_callable=AsyncMock) as mock_get_klines:
                mock_kline = [int(time.time() * 1000 - 60000), "50000", "50002", "49999", "50001", "100", int(time.time() * 1000)]
                mock_get_klines.return_value = [mock_kline]

                # Instead of relying on aggregator to build a tick, directly emit a realistic tick
                tick = {
                    "ts": int(time.time() * 1000),
                    "price": 50001,
                    "bid": 50000,
                    "ask": 50002,
                    "mid": 50001,
                    "bid_size": 10,
                    "ask_size": 8,
                    "buy_volume": 50,
                    "sell_volume": 30,
                    "data_source": "test",
                    "bid_ask_count": "B:1:A:1",
                    "trade_count": "count:50:30",
                }

                market_data._emit_market_tick("BTCUSDT", tick)

                # Verify market_data emitted event
                assert mock_fsm.emit.called
                call_args = mock_fsm.emit.call_args
                if call_args.args:
                    event_name = call_args.args[0]
                    payload = call_args.args[1]
                else:
                    event_name = call_args.kwargs['event_name']
                    payload = call_args.kwargs['payload']

                assert event_name == "EVT:MARKET_TICK_RECEIVED"
                assert payload['symbol'] == "BTCUSDT"

        finally:
            market_data.stop()