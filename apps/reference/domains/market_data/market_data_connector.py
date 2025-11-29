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

from apps.reference.adapters.binance_adapter import BinanceAdapter
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
        # Will be set after init
        self.feature_engineering: Optional[Any] = None

        # 🆕 FIX: Read trading config directly (not from system.trading)
        # Config structure: merged_config = {trading: {...}, system: {...}}
        if hasattr(self.config, "trading"):
            trading_section = self.config.trading
        elif isinstance(self.config, dict):
            trading_section = self.config.get("trading", {})
        else:
            trading_section = {}

        # Get symbols from config.instruments (SOLUSDT, ETHUSDT), NOT hardcoded defaults
        try:
            if hasattr(trading_section, "instruments"):
                instruments = trading_section.instruments or {}
            elif isinstance(trading_section, dict):
                instruments = trading_section.get("instruments", {})
            else:
                instruments = {}
        except Exception:
            instruments = {}
        self.symbols = list(instruments.keys()) if instruments else [
            "SOLUSDT", "ETHUSDT"]

        # Get anchor symbols from config.market_data.macro_sync.anchors
        macro_sync_config = trading_section.get(
            "market_data", {}).get("macro_sync", {})
        try:
            self.anchors = self.config.trading.market_data.macro_sync.anchors
        except Exception:
            # Fallback to dict-based anchors resolution
            try:
                self.anchors = list((trading_section.get("market_data", {})
                                     .get("macro_sync", {})
                                     .get("anchors", [])) or [])
            except Exception:
                self.anchors = []
        LOG.info(f"✅ Macro sync anchors: {self.anchors}")

        # Configure polling interval and streams (Pydantic-first with dict fallback)
        poll_interval_sec = 2.0
        websocket_streams = ["bookTicker", "trade"]
        try:
            if hasattr(trading_section, "market_data") and getattr(trading_section, "market_data"):
                md = trading_section.market_data
                poll_interval_sec = float(
                    getattr(md, "poll_interval_sec", poll_interval_sec))
                websocket_streams = list(
                    getattr(md, "websocket_streams", websocket_streams))
            elif isinstance(trading_section, dict):
                md = trading_section.get("market_data", {})
                poll_interval_sec = float(
                    md.get("poll_interval_sec", poll_interval_sec))
                websocket_streams = list(
                    md.get("websocket_streams", websocket_streams))
        except Exception:
            pass
        self.poll_interval_sec = poll_interval_sec
        self.websocket_streams = websocket_streams

        # Initialize the BinanceAdapter based on the domain-level trading_mode
        mode = "live"  # Default for market_data domain

        # Try to get domain-specific mode first
        if hasattr(config, "get_domain_mode"):
            try:
                mode = config.get_domain_mode("market_data")
                LOG.info(
                    f"MarketDataConnector using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                mode = getattr(self.config, "trading_mode", "testnet") if not isinstance(
                    self.config, dict) else self.config.get("trading_mode", "testnet")
        else:
            # Fallback to global mode
            if hasattr(self.config, "trading_mode"):
                mode = self.config.trading_mode
            elif isinstance(self.config, dict):
                mode = self.config.get("trading_mode", "testnet")
            else:
                mode = "testnet"
            LOG.info(f"MarketDataConnector using global trading_mode: {mode}")

        # Resolve API env config (Pydantic-first with dict fallback)
        api_key = api_secret = rest_url = None
        if hasattr(self.config, "binance_api"):
            bapi = self.config.binance_api
            if mode in ["live", "hybrid_live_data_testnet_exec"]:
                env = getattr(bapi, "live", None)
                self.data_source_tag = "live"
                LOG.info(
                    "MarketDataConnector is configured to use LIVE data source.")
            else:
                env = getattr(bapi, "testnet", None)
                self.data_source_tag = "testnet"
                LOG.info(
                    "MarketDataConnector is configured to use TESTNET data source.")

            if env is not None:
                api_key = getattr(env, "api_key", None)
                api_secret = getattr(env, "api_secret", None)
                rest_url = getattr(env, "rest_url", None)
        elif isinstance(self.config, dict):
            bapi = self.config.get("binance_api", {})
            env_dict = bapi.get("live", {}) if mode in [
                "live", "hybrid_live_data_testnet_exec"] else bapi.get("testnet", {})
            self.data_source_tag = "live" if mode in [
                "live", "hybrid_live_data_testnet_exec"] else "testnet"
            api_key = env_dict.get("api_key")
            api_secret = env_dict.get("api_secret")
            rest_url = env_dict.get("rest_url")

        if not all([api_key, api_secret, rest_url]):
            raise ValueError(
                f"API configuration for '{mode}' mode is incomplete.")

        self.adapter = BinanceAdapter(
            api_key=str(api_key),
            api_secret=str(api_secret),
            rest_url=str(rest_url),
        )

        # Initialize WebSocket aggregator for real-time data collection
        self.aggregator = WebSocketAggregator(
            self.symbols, window_seconds=60, anchors=self.anchors)
        LOG.info(
            f"✅ WebSocket Aggregator initialized for {self.symbols} with anchors: {self.anchors}")

    def set_feature_engineering(self, fe: Any) -> None:
        """
        Set the FeatureEngineering component to receive anchor updates.

        Args:
            fe: FeatureEngineering instance
        """
        self.feature_engineering = fe
        # Set callback for anchor price updates
        self.aggregator.set_anchor_update_callback(self._on_anchor_update)
        LOG.info("✅ FeatureEngineering linked for anchor updates")

    async def _on_anchor_update(self, anchor: str, price: str) -> None:
        """
        Callback when an anchor price is updated.

        Args:
            anchor: Anchor symbol (e.g., 'BTCUSDT')
            price: Updated price
        """
        if self.feature_engineering:
            self.feature_engineering.update_anchor_price(anchor, price)

    def start(self) -> None:
        """Start the data polling in a background thread."""
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        LOG.info(
            f"MarketDataConnector started for symbols: {self.symbols} with {self.poll_interval_sec}s interval."
        )

    def stop(self) -> None:
        """Stop the data polling thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        # Close the adapter's session (without asyncio.run() to avoid conflicts)
        try:
            import sys

            if sys.platform == "win32":
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
        LOG.debug("🔄 Starting data fetch cycle")
        
        tasks = [self._fetch_symbol_data(symbol) for symbol in self.symbols]
        
        if self.anchors:
            LOG.debug(f"📌 Fetching anchor prices: {self.anchors}")
            tasks.extend([self._fetch_anchor_data(anchor) for anchor in self.anchors])
            
        await asyncio.gather(*tasks)

    async def _fetch_symbol_data(self, symbol: str) -> None:
        try:
            LOG.debug(f"📡 Fetching data for {symbol}")

            # Fetch REAL bid/ask sizes from bookTicker
            book_data = await self.adapter.get_book_ticker(symbol=symbol)
            if book_data:
                LOG.debug(f"📗 BookTicker for {symbol}: {book_data}")
                bid_price = book_data.get("bidPrice", "0")
                bid_size = book_data.get("bidQty", "0")
                ask_price = book_data.get("askPrice", "0")
                ask_size = book_data.get("askQty", "0")
                ts = int(time.time() * 1000)

                # Feed data to aggregator
                self.aggregator.on_book_ticker(
                    symbol, bid_price, bid_size, ask_price, ask_size, ts
                )
            else:
                LOG.warning(f"❌ No bookTicker data for {symbol}")

            # Fetch REAL recent trades
            limit = 50
            try:
                if hasattr(self.config, "market_data") and self.config.market_data:
                    limit = self.config.market_data.api_call_limits.get_recent_trades
                elif isinstance(self.config, dict):
                    limit = self.config.get("market_data", {}).get("api_call_limits", {}).get("get_recent_trades", 50)
            except Exception:
                pass

            trades_data = await self.adapter.get_recent_trades(
                symbol=symbol, limit=limit
            )
            if trades_data:
                LOG.debug(f"📈 Got {len(trades_data)} trades for {symbol}")
                for trade in trades_data:
                    self.aggregator.on_trade(
                        symbol,
                        price=trade.get("price", "0"),
                        quantity=trade.get("qty", "0"),
                        is_buyer_maker=trade.get(
                            "m", True
                        ),  # m=True means buyer is maker (sell)
                        ts=trade.get("time", int(time.time() * 1000)),
                        trade_id=trade.get("id")
                    )
            else:
                LOG.warning(f"❌ No trades data for {symbol}")

            # Fetch klines for delta_price calculation
            kline_interval = "1m"
            kline_limit = 2
            try:
                if hasattr(self.config, "market_data") and self.config.market_data:
                    klines_cfg = self.config.market_data.api_call_limits.get_klines
                    if isinstance(klines_cfg, dict):
                        kline_interval = klines_cfg.get("interval", "1m")
                        kline_limit = klines_cfg.get("limit", 2)
                elif isinstance(self.config, dict):
                        klines_cfg = self.config.get("market_data", {}).get("api_call_limits", {}).get("get_klines", {})
                        kline_interval = klines_cfg.get("interval", "1m")
                        kline_limit = klines_cfg.get("limit", 2)
            except Exception:
                pass

            klines = await self.adapter.get_klines(
                symbol=symbol, interval=kline_interval, limit=kline_limit
            )
            if klines and len(klines) >= 2:
                LOG.debug(f"📊 Got {len(klines)} klines for {symbol}")
                # Update price history
                for kline in klines:
                    price = kline[4]  # close price
                    ts = kline[6]  # close time
                    self.aggregator.on_trade(
                        symbol,
                        price=str(price),
                        quantity="0",
                        is_buyer_maker=False,
                        ts=ts,
                    )
            else:
                LOG.warning(f"❌ No klines data for {symbol}")

            # Get aggregated market tick with REAL features
            tick = self.aggregator.get_market_tick(symbol)
            if tick:
                LOG.debug(f"✅ Got tick for {symbol}: {tick}")
                self._emit_market_tick(symbol, tick)
            else:
                LOG.debug(f"⏳ Not enough data yet for {symbol}")

        except Exception as e:
            LOG.error(
                f"❌ Failed to fetch data for {symbol}: {e}", exc_info=True)

    async def _fetch_anchor_data(self, anchor: str) -> None:
        try:
            LOG.debug(f"📡 Fetching anchor {anchor}")
            book_data = await self.adapter.get_book_ticker(symbol=anchor)
            if book_data:
                bid_price = float(book_data.get("bidPrice", "0"))
                ask_price = float(book_data.get("askPrice", "0"))
                mid_price = (bid_price + ask_price) / 2.0
                ts = int(time.time() * 1000)

                # Feed anchor data to aggregator
                self.aggregator.on_book_ticker(
                    anchor,
                    bid_price=str(bid_price),
                    bid_size=book_data.get("bidQty", "0"),
                    ask_price=str(ask_price),
                    ask_size=book_data.get("askQty", "0"),
                    ts=ts
                )

                # Trigger callback to FeatureEngineering
                await self._on_anchor_update(anchor, str(mid_price))
                LOG.debug(
                    f"✅ Anchor {anchor} price updated: {mid_price}")
            else:
                LOG.warning(
                    f"❌ No bookTicker data for anchor {anchor}")
        except Exception as e:
            LOG.warning(f"❌ Failed to fetch anchor {anchor}: {e}")

    def _emit_market_tick(self, symbol: str, tick: dict[str, Any]) -> None:
        """Emit a market tick event with real feature data."""
        try:
            # Debug: Log what we actually received
            LOG.debug(f"🔍 Tick data for {symbol}: {tick}")

            # Defensive: Check required keys exist
            required_keys = ["ts", "price", "bid", "ask", "mid", "bid_size",
                             "ask_size", "buy_volume", "sell_volume", "data_source"]
            missing_keys = [key for key in required_keys if key not in tick]
            if missing_keys:
                LOG.error(
                    f"❌ Tick data missing required keys for {symbol}: {missing_keys}. Available keys: {list(tick.keys())}")
                return

            payload = {
                "ts": tick["ts"],
                "symbol": symbol,
                "price": tick["price"],
                "bid": tick["bid"],
                "ask": tick["ask"],
                "mid": tick["mid"],
                "bid_size": tick["bid_size"],  # ✅ NOW REAL!
                "ask_size": tick["ask_size"],  # ✅ NOW REAL!
                "buy_volume": tick["buy_volume"],  # ✅ NOW REAL!
                "sell_volume": tick["sell_volume"],  # ✅ NOW REAL!
                "data_type": "market_tick_aggregated",
                "data_source": tick["data_source"],
                "debug_info": f"BID/ASK: {tick.get('bid_ask_count', 'N/A')}, Trades: {tick.get('trade_count', 'N/A')}",
            }

            self.fsm.emit(
                event_name="EVT:MARKET_TICK_RECEIVED",
                payload=payload,
                why=f"Real-time market tick for {symbol} from {tick['data_source']}",
            )

            LOG.info(
                f"📊 {symbol} Tick: bid={tick['bid_size']}@{tick['bid']}, "
                f"ask={tick['ask_size']}@{tick['ask']}, "
                f"trades: BUY={tick.get('trade_count', 'N/A').split(':')[1].split()[0] if tick.get('trade_count') else 'N/A'} "
                f"SELL={tick.get('trade_count', 'N/A').split(':')[2] if tick.get('trade_count') else 'N/A'}"
            )

        except Exception as e:
            LOG.error(
                f"Error emitting market tick for {symbol}: {e}", exc_info=True)
