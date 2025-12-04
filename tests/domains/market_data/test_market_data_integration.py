"""
Tests for market_data domain.

Tests cover:
1. MarketDataConnector initialization and validation
2. WebSocketAggregator data processing
3. Trading modes resolution
4. Fail-fast behavior on missing config
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestMarketDataConnectorInit:
    """Test MarketDataConnector initialization and config validation."""
    
    def test_init_raises_on_empty_instruments(self):
        """Test that connector raises ValueError if no instruments configured."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        # Create mock config with empty instruments
        mock_config = MagicMock()
        mock_config.trading.instruments = {}  # Empty!
        mock_config.trading.market_data = MagicMock()
        mock_config.trading.market_data.macro_sync = MagicMock()
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = "key"
        mock_config.binance_api.testnet.api_secret = "secret"
        mock_config.binance_api.testnet.rest_url = "https://test.com"
        
        mock_fsm = MagicMock()
        
        with pytest.raises(ValueError, match="trading.instruments must contain at least one symbol"):
            MarketDataConnector(fsm=mock_fsm, config=mock_config)
    
    def test_init_raises_on_missing_macro_sync(self):
        """Test that connector raises ValueError if macro_sync not configured."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock()}
        mock_config.trading.market_data = None  # Missing!
        
        mock_fsm = MagicMock()
        
        with pytest.raises(ValueError, match="trading.market_data.macro_sync must be configured"):
            MarketDataConnector(fsm=mock_fsm, config=mock_config)

    def test_init_raises_on_missing_api_credentials(self):
        """Test that connector raises ValueError if API credentials missing."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock()}
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = None  # Missing!
        mock_config.binance_api.testnet.api_secret = "secret"
        mock_config.binance_api.testnet.rest_url = "https://test.com"
        
        mock_fsm = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="testnet"):
            with pytest.raises(ValueError, match="API configuration.*incomplete"):
                MarketDataConnector(fsm=mock_fsm, config=mock_config)


class TestMarketDataConnectorSuccessfulInit:
    """Test successful MarketDataConnector initialization."""
    
    def test_init_with_valid_config(self):
        """Test connector initializes correctly with valid config."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {
            "SOLUSDT": MagicMock(),
            "ETHUSDT": MagicMock()
        }
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT", "ETHUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = "test_key"
        mock_config.binance_api.testnet.api_secret = "test_secret"
        mock_config.binance_api.testnet.rest_url = "https://testnet.binance.com"
        
        mock_fsm = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="testnet"):
            with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter'):
                with patch('apps.reference.domains.market_data.market_data_connector.WebSocketAggregator'):
                    connector = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        
        assert connector.symbols == ["SOLUSDT", "ETHUSDT"]
        assert connector.anchors == ["BTCUSDT", "ETHUSDT"]
        assert connector.data_source_tag == "testnet"
        assert connector.poll_interval_sec == 2


class TestTradingModes:
    """Test trading mode resolution utilities."""
    
    def test_get_domain_mode_testnet(self):
        """Test domain mode resolution for testnet."""
        from apps.reference.utils.trading_modes import get_domain_mode_from_mapping
        
        config = {"trading": {"mode": "testnet"}}
        mode = get_domain_mode_from_mapping(config, "market_data")
        
        assert mode == "testnet"
    
    def test_get_domain_mode_live(self):
        """Test domain mode resolution for live."""
        from apps.reference.utils.trading_modes import get_domain_mode_from_mapping
        
        config = {"trading": {"mode": "live"}}
        mode = get_domain_mode_from_mapping(config, "market_data")
        
        assert mode == "live"
    
    def test_get_domain_mode_shadow_live(self):
        """Test domain mode resolution for shadow_live (hybrid mode)."""
        from apps.reference.utils.trading_modes import get_domain_mode_from_mapping
        
        config = {"trading": {"mode": "shadow_live"}}
        mode = get_domain_mode_from_mapping(config, "market_data")
        
        # In shadow_live, market_data should use live data
        assert mode == "live"
    
    def test_get_domain_mode_with_override(self):
        """Test domain mode with per-domain override."""
        from apps.reference.utils.trading_modes import get_domain_mode_from_mapping
        
        config = {
            "trading": {
                "mode": "testnet",
                "domain_configuration": {
                    "market_data": {"trading_mode": "live"}
                }
            }
        }
        mode = get_domain_mode_from_mapping(config, "market_data")
        
        assert mode == "live"


class TestWebSocketAggregator:
    """Test WebSocketAggregator functionality."""
    
    def test_aggregator_initializes(self):
        """Test aggregator initializes with symbols and anchors."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT", "ETHUSDT"],
            window_seconds=60,
            anchors=["BTCUSDT"]
        )
        
        assert "SOLUSDT" in aggregator.symbols
        assert "ETHUSDT" in aggregator.symbols
        assert aggregator.window_seconds == 60

    def test_aggregator_on_book_ticker(self):
        """Test aggregator processes bookTicker data correctly."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # Send bookTicker update
        aggregator.on_book_ticker(
            symbol="SOLUSDT",
            bid_price="100.50",
            bid_size="10.5",
            ask_price="100.60",
            ask_size="8.3",
            ts=1700000000000
        )
        
        # Check state was updated
        state = aggregator.state["SOLUSDT"]
        assert float(state["bid_price"]) == 100.50
        assert float(state["ask_price"]) == 100.60
        assert float(state["bid_size"]) == 10.5
        assert float(state["ask_size"]) == 8.3

    def test_aggregator_on_trade(self):
        """Test aggregator processes trade data correctly."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # Send trade (buyer is maker = sell)
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.55",
            quantity="5.0",
            is_buyer_maker=True,  # Sell
            ts=1700000000000,
            trade_id=12345
        )
        
        state = aggregator.state["SOLUSDT"]
        assert state["sell_trades"] == 1
        assert state["buy_trades"] == 0
        
        # Send trade (buyer is taker = buy)
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.56",
            quantity="3.0",
            is_buyer_maker=False,  # Buy
            ts=1700000001000,
            trade_id=12346
        )
        
        assert state["sell_trades"] == 1
        assert state["buy_trades"] == 1

    def test_aggregator_trade_deduplication(self):
        """Test aggregator deduplicates trades by trade_id."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # Send same trade twice
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.55",
            quantity="5.0",
            is_buyer_maker=True,
            ts=1700000000000,
            trade_id=99999  # Same ID
        )
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.55",
            quantity="5.0",
            is_buyer_maker=True,
            ts=1700000000000,
            trade_id=99999  # Same ID - should be ignored!
        )
        
        state = aggregator.state["SOLUSDT"]
        # Should only count once due to deduplication
        assert state["sell_trades"] == 1

    def test_aggregator_get_market_tick(self):
        """Test aggregator generates market tick with all required fields."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # Set up some data
        aggregator.on_book_ticker(
            symbol="SOLUSDT",
            bid_price="100.50",
            bid_size="10.5",
            ask_price="100.60",
            ask_size="8.3",
            ts=1700000000000
        )
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.55",
            quantity="5.0",
            is_buyer_maker=False,
            ts=1700000000000,
            trade_id=1
        )
        
        tick = aggregator.get_market_tick("SOLUSDT")
        
        # Check required fields
        assert tick is not None
        assert "ts" in tick
        assert "price" in tick
        assert "bid" in tick
        assert "ask" in tick
        assert "mid" in tick
        assert "bid_size" in tick
        assert "ask_size" in tick
        assert "buy_volume" in tick
        assert "sell_volume" in tick
        assert "data_source" in tick


class TestMarketWSClient:
    """Test MarketWSClient functionality."""
    
    def test_client_builds_stream_url(self):
        """Test WebSocket client builds correct stream URL."""
        from apps.reference.domains.market_data.market_ws_client import MarketWSClient
        
        client = MarketWSClient(
            symbols=["SOLUSDT", "ETHUSDT"],
            on_book_ticker=lambda x: None,
            on_trade=lambda x: None,
        )
        
        url = client._build_stream_url()
        
        assert "solusdt@bookTicker" in url
        assert "solusdt@aggTrade" in url
        assert "ethusdt@bookTicker" in url
        assert "ethusdt@aggTrade" in url


class TestConfigSymbolsFailFast:
    """Test config_symbols module fail-fast behavior."""
    
    def test_get_trading_symbols_raises_on_no_config(self):
        """Test that get_trading_symbols raises ValueError when no config available."""
        from apps.reference.config_symbols import get_trading_symbols
        
        # Mock both config sources to fail
        with patch('apps.reference.config_loader.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.trading.instruments = {}
            mock_get_config.return_value = mock_config
            
            with pytest.raises(ValueError, match="No trading symbols configured"):
                get_trading_symbols()


class TestConfigModelsValidation:
    """Test Pydantic config models validation."""
    
    def test_symbols_to_track_in_trading_config(self):
        """Test that symbols_to_track is properly validated."""
        from apps.reference.config_models import TradingConfig
        
        # Valid config
        config = TradingConfig(
            mode="testnet",
            symbols_to_track=["BTCUSDT", "ETHUSDT"]
        )
        assert config.symbols_to_track == ["BTCUSDT", "ETHUSDT"]
    
    def test_symbols_to_track_defaults_to_empty(self):
        """Test that symbols_to_track defaults to empty list."""
        from apps.reference.config_models import TradingConfig
        
        config = TradingConfig(mode="testnet")
        assert config.symbols_to_track == []
    
    def test_aurora_config_loads_symbols_to_track(self):
        """Test AuroraConfig loads symbols_to_track from nested trading."""
        from apps.reference.config_models import AuroraConfig
        
        config = AuroraConfig(
            trading_mode="testnet",
            trading={"symbols_to_track": ["SOLUSDT", "AVAXUSDT"]},
            binance_api={"testnet": {"api_key": "k", "api_secret": "s"}}
        )
        assert config.trading.symbols_to_track == ["SOLUSDT", "AVAXUSDT"]


class TestMarketDataConnectorMethods:
    """Test MarketDataConnector async methods."""
    
    def test_get_ws_url_testnet(self):
        """Test WebSocket URL for testnet mode."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock()}
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = "key"
        mock_config.binance_api.testnet.api_secret = "secret"
        mock_config.binance_api.testnet.rest_url = "https://test.com"
        
        mock_fsm = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="testnet"):
            with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter'):
                with patch('apps.reference.domains.market_data.market_data_connector.WebSocketAggregator'):
                    connector = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        
        url = connector._get_ws_url()
        assert "testnet" in url

    def test_get_ws_url_live(self):
        """Test WebSocket URL for live mode."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock()}
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.live.api_key = "key"
        mock_config.binance_api.live.api_secret = "secret"
        mock_config.binance_api.live.rest_url = "https://live.com"
        
        mock_fsm = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="live"):
            with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter'):
                with patch('apps.reference.domains.market_data.market_data_connector.WebSocketAggregator'):
                    connector = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        
        url = connector._get_ws_url()
        assert "stream.binance.com" in url

    def test_make_subscribe_payload(self):
        """Test subscription payload construction."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock(), "ETHUSDT": MagicMock()}
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = "key"
        mock_config.binance_api.testnet.api_secret = "secret"
        mock_config.binance_api.testnet.rest_url = "https://test.com"
        
        mock_fsm = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="testnet"):
            with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter'):
                with patch('apps.reference.domains.market_data.market_data_connector.WebSocketAggregator'):
                    connector = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        
        payload = connector._make_subscribe_payload()
        
        assert payload["method"] == "SUBSCRIBE"
        assert "solusdt@bookTicker" in payload["params"]
        assert "solusdt@trade" in payload["params"]
        assert "ethusdt@bookTicker" in payload["params"]
        assert "ethusdt@trade" in payload["params"]


class TestTradeIdDeduplication:
    """Test trade_id deduplication through the full chain."""

    def test_handle_message_passes_trade_id(self):
        """Test that _handle_message correctly extracts and passes trade_id to aggregator."""
        from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
        
        mock_config = MagicMock()
        mock_config.trading.instruments = {"SOLUSDT": MagicMock()}
        mock_config.trading.market_data.macro_sync.anchors = ["BTCUSDT"]
        mock_config.trading.market_data.poll_interval_sec = 2
        mock_config.binance_api.testnet.api_key = "key"
        mock_config.binance_api.testnet.api_secret = "secret"
        mock_config.binance_api.testnet.rest_url = "https://test.com"
        
        mock_fsm = MagicMock()
        mock_aggregator = MagicMock()
        
        with patch('apps.reference.domains.market_data.market_data_connector.get_domain_mode_from_mapping', return_value="testnet"):
            with patch('apps.reference.domains.market_data.market_data_connector.BinanceAdapter'):
                with patch('apps.reference.domains.market_data.market_data_connector.WebSocketAggregator', return_value=mock_aggregator):
                    connector = MarketDataConnector(fsm=mock_fsm, config=mock_config)
        
        # Simulate trade message from Binance WebSocket
        trade_msg = {
            "e": "trade",
            "E": 1700000000000,
            "s": "SOLUSDT",
            "t": 123456789,  # Trade ID
            "p": "100.50",
            "q": "5.0",
            "T": 1700000000000,
            "m": True
        }
        
        connector._handle_message(trade_msg)
        
        # Verify on_trade was called with trade_id
        mock_aggregator.on_trade.assert_called_once()
        call_kwargs = mock_aggregator.on_trade.call_args
        
        # Check that trade_id was passed
        assert call_kwargs.kwargs.get("trade_id") == 123456789 or call_kwargs[1].get("trade_id") == 123456789

    def test_duplicate_trades_not_counted_twice(self):
        """Test that duplicate trades with same trade_id are not double-counted in TFI."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # First unique trade (buy)
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.00",
            quantity="1.0",
            is_buyer_maker=False,  # Buy
            ts=1700000000000,
            trade_id=1001
        )
        
        # Second unique trade (sell)
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.01",
            quantity="1.0",
            is_buyer_maker=True,  # Sell
            ts=1700000001000,
            trade_id=1002
        )
        
        # DUPLICATE of first trade (should be ignored)
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.00",
            quantity="1.0",
            is_buyer_maker=False,  # Buy
            ts=1700000000000,
            trade_id=1001  # Same ID!
        )
        
        state = aggregator.state["SOLUSDT"]
        
        # Should have 1 buy and 1 sell, not 2 buys and 1 sell
        assert state["buy_trades"] == 1, f"Expected 1 buy trade, got {state['buy_trades']}"
        assert state["sell_trades"] == 1, f"Expected 1 sell trade, got {state['sell_trades']}"
        
        # Verify trade_id is tracked
        assert 1001 in state["seen_trade_ids"]
        assert 1002 in state["seen_trade_ids"]

    def test_tfi_accuracy_with_deduplication(self):
        """Test that TFI is correctly calculated when duplicates are filtered."""
        from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
        
        aggregator = WebSocketAggregator(
            symbols=["SOLUSDT"],
            window_seconds=60,
            anchors=[]
        )
        
        # Setup bookTicker first
        aggregator.on_book_ticker(
            symbol="SOLUSDT",
            bid_price="100.00",
            bid_size="10.0",
            ask_price="100.10",
            ask_size="10.0",
            ts=1700000000000
        )
        
        # 3 buy trades
        for i in range(3):
            aggregator.on_trade(
                symbol="SOLUSDT",
                price="100.05",
                quantity="1.0",
                is_buyer_maker=False,  # Buy
                ts=1700000000000 + i * 100,
                trade_id=1000 + i
            )
        
        # 1 sell trade
        aggregator.on_trade(
            symbol="SOLUSDT",
            price="100.04",
            quantity="1.0",
            is_buyer_maker=True,  # Sell
            ts=1700000001000,
            trade_id=2000
        )
        
        # Try to duplicate all buy trades (should be ignored)
        for i in range(3):
            aggregator.on_trade(
                symbol="SOLUSDT",
                price="100.05",
                quantity="1.0",
                is_buyer_maker=False,
                ts=1700000000000 + i * 100,
                trade_id=1000 + i  # Same IDs!
            )
        
        tick = aggregator.get_market_tick("SOLUSDT")
        
        # TFI = (buys - sells) / total = (3 - 1) / 4 = 0.5
        tfi = float(tick["features"]["tfi"])
        assert abs(tfi - 0.5) < 0.01, f"Expected TFI ~0.5, got {tfi}"

