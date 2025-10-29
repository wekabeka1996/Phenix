"""
MarketDataConnector for market_data domain (FSMP-P1-T03).

Hybrid approach: Uses REST API to poll klines, bookTicker, and trades to calculate
real-time features (OBI, TFI, delta_price) from live Binance data.
Emits EVT:MARKET_TICK_RECEIVED with accurate feature data.
"""
import asyncio
import decimal
import logging
import threading
import time
from typing import Any, Optional, TYPE_CHECKING

from vfoundation.adapters.binance_adapter import BinanceAdapter
from .websocket_aggregator import WebSocketAggregator

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)

# Check if unicorn_binance_websocket_api is available (for backward compatibility testing)
try:
    import unicorn_binance_websocket_api
    HAS_UNICORN = True
except ImportError:
    HAS_UNICORN = False

class MarketDataConnector:
    """
    Hybrid data source: REST API polls + WebSocket aggregation.

    Fetches:
    1. bookTicker - for real bid_size, ask_size (OBI)
    2. Recent trades - for real buy_trades, sell_trades (TFI)
    3. Klines - for delta_price

    Results in REAL features, not constants!
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        """
        Initialize the connector.

        Args:
            fsm: FSM core instance for event emission.
            config: Full configuration dictionary.
        """
        self.fsm = fsm
        self.config = config
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.data_source_tag = "testnet"
        
        system_config = config.get('system', {})
        trading_section = system_config.get('trading', {})
        self.symbols = trading_section.get('symbols_to_track', ["BTCUSDT", "ETHUSDT"])
        
        # Configure polling interval - now faster for WebSocket-like responsiveness
        market_data_config = trading_section.get('market_data', {})
        self.poll_interval_sec = market_data_config.get('poll_interval_sec', 2.0)  # 2s instead of 5s
        self.websocket_streams = market_data_config.get('websocket_streams', ["bookTicker", "trade"])

        # Initialize the BinanceAdapter based on the domain-level trading_mode
        mode = "live"  # Default for market_data domain
        
        # Try to get domain-specific mode first
        if hasattr(config, 'get_domain_mode'):
            try:
                mode = config.get_domain_mode("market_data")
                LOG.info(f"MarketDataConnector using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                mode = config.get("trading_mode", "live")
        else:
            # Fallback to global mode
            mode = config.get("trading_mode", "live")
            LOG.info(f"MarketDataConnector using global trading_mode: {mode}")
        
        api_config = config.get("binance_api", {})
        
        env_config = {}
        if mode in ["live", "hybrid_live_data_testnet_exec"]:
            env_config = api_config.get("live", {})
            self.data_source_tag = "live"
            LOG.info("MarketDataConnector is configured to use LIVE data source.")
        else:
            env_config = api_config.get("testnet", {})
            self.data_source_tag = "testnet"
            LOG.info("MarketDataConnector is configured to use TESTNET data source.")

        if not all([env_config.get("api_key"), env_config.get("api_secret"), env_config.get("rest_url")]):
            raise ValueError(f"API configuration for '{mode}' mode is incomplete.")

        self.adapter = BinanceAdapter(
            api_key=env_config["api_key"],
            api_secret=env_config["api_secret"],
            rest_url=env_config["rest_url"]
        )

        # Initialize WebSocket aggregator for real-time data collection
        self.aggregator = WebSocketAggregator(self.symbols, window_seconds=60)
        LOG.info(f"✅ WebSocket Aggregator initialized for {self.symbols}")

    def start(self) -> None:
        """Start the data polling in a background thread."""
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        LOG.info(f"MarketDataConnector started for symbols: {self.symbols} with {self.poll_interval_sec}s interval.")

    def stop(self) -> None:
        """Stop the data polling thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        # Close the adapter's session (without asyncio.run() to avoid conflicts)
        try:
            import sys
            if sys.platform == 'win32':
                # On Windows, use a safer approach
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.adapter.close_session())
                finally:
                    loop.close()
            else:
                asyncio.run(self.adapter.close_session())
        except RuntimeError:
            # If asyncio.run() fails (e.g., inside async test), skip
            LOG.debug("Could not close adapter session (already in event loop)")
        LOG.info("MarketDataConnector stopped.")

    def _poll_loop(self) -> None:
        """Main polling loop that runs in the background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self.running:
                loop.run_until_complete(self._fetch_and_emit_data())
                time.sleep(self.poll_interval_sec)
        finally:
            loop.close()
            LOG.info("Polling loop has ended.")

    async def _fetch_and_emit_data(self) -> None:
        """
        Fetch real-time market data (bookTicker + trades) and emit FSM events.

        This is the KEY FIX: Instead of using constant values,
        we now fetch REAL bid/ask sizes and REAL trade volumes.
        """
        for symbol in self.symbols:
            try:
                # Fetch REAL bid/ask sizes from bookTicker
                book_data = await self.adapter.get_book_ticker(symbol=symbol)
                if book_data:
                    bid_price = book_data.get('bidPrice', '0')
                    bid_size = book_data.get('bidQty', '0')
                    ask_price = book_data.get('askPrice', '0')
                    ask_size = book_data.get('askQty', '0')
                    ts = int(time.time() * 1000)

                    # Feed data to aggregator
                    self.aggregator.on_book_ticker(
                        symbol, bid_price, bid_size, ask_price, ask_size, ts
                    )

                # Fetch REAL recent trades
                trades_data = await self.adapter.get_recent_trades(symbol=symbol, limit=50)
                if trades_data:
                    for trade in trades_data:
                        self.aggregator.on_trade(
                            symbol,
                            price=trade.get('price', '0'),
                            quantity=trade.get('qty', '0'),
                            is_buyer_maker=trade.get('m', True),  # m=True means buyer is maker (sell)
                            ts=trade.get('time', int(time.time() * 1000))
                        )

                # Fetch klines for delta_price calculation
                klines = await self.adapter.get_klines(symbol=symbol, interval="1m", limit=2)
                if klines and len(klines) >= 2:
                    # Update price history
                    for kline in klines:
                        price = kline[4]  # close price
                        ts = kline[6]  # close time
                        self.aggregator.on_trade(
                            symbol,
                            price=str(price),
                            quantity='0',
                            is_buyer_maker=False,
                            ts=ts
                        )

                # Get aggregated market tick with REAL features
                tick = self.aggregator.get_market_tick(symbol)
                if tick:
                    self._emit_market_tick(symbol, tick)
                else:
                    LOG.debug(f"Not enough data yet for {symbol}")

            except Exception as e:
                LOG.error(f"Failed to fetch data for {symbol}: {e}", exc_info=True)

    def _emit_market_tick(self, symbol: str, tick: dict[str, Any]) -> None:
        """Emit a market tick event with real feature data."""
        try:
            payload = {
                "ts": tick['ts'],
                "symbol": symbol,
                "price": tick['price'],
                "bid": tick['bid'],
                "ask": tick['ask'],
                "mid": tick['mid'],
                "bid_size": tick['bid_size'],    # ✅ NOW REAL!
                "ask_size": tick['ask_size'],    # ✅ NOW REAL!
                "buy_volume": tick['buy_volume'],  # ✅ NOW REAL!
                "sell_volume": tick['sell_volume'],  # ✅ NOW REAL!
                "data_type": "market_tick_aggregated",
                "data_source": tick['data_source'],
                "debug_info": f"BID/ASK: {tick['bid_ask_count']}, Trades: {tick['trade_count']}"
            }

            self.fsm.emit(
                event_name="EVT:MARKET_TICK_RECEIVED",
                payload=payload,
                why=f"Real-time market tick for {symbol} from {tick['data_source']}"
            )

            LOG.info(
                f"📊 {symbol} Tick: bid={tick['bid_size']}@{tick['bid']}, "
                f"ask={tick['ask_size']}@{tick['ask']}, "
                f"trades: BUY={tick['trade_count'].split(':')[1].split()[0]} "
                f"SELL={tick['trade_count'].split(':')[2]}"
            )


        except Exception as e:
            LOG.error(f"Error emitting market tick for {symbol}: {e}", exc_info=True)
