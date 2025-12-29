"""
MarketDataConnector for market_data domain (FSMP-P1-T03).

Hybrid approach: Uses REST API to poll klines, bookTicker, and trades to calculate
real-time features (OBI, TFI, delta_price) from live Binance data.
Emits EVT:MARKET_TICK_RECEIVED with accurate feature data.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional, TYPE_CHECKING

import aiohttp

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.utils import get_domain_mode_from_mapping
from .websocket_aggregator import WebSocketAggregator

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

from apps.reference.config_models import AuroraConfig

LOG = logging.getLogger(__name__)


class MarketDataConnector:
    """
    Hybrid data source: REST API polls + WebSocket aggregation.

    Fetches:
    1. bookTicker - for real bid_size, ask_size (OBI)
    2. Recent trades - for real buy_trades, sell_trades (TFI)
    3. Klines - for delta_price

    Results in REAL features, not constants!
    """

    # WebSocket URLs for live and testnet
    WS_URL_LIVE = "wss://stream.binance.com:9443/ws"
    WS_URL_TESTNET = "wss://stream.testnet.binance.vision/ws"

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        """
        Initialize the connector with validated Config V2 object.

        Args:
            fsm: FSM core instance for event emission.
            config: AuroraConfig V2 object (validated on load).

        Raises:
            ValueError: If required config keys are missing.
        """
        self.fsm = fsm
        self.config = config
        self.running = False
        self.feature_engineering: Optional[Any] = None

        # Background tasks
        self._ws_task: Optional[asyncio.Task] = None
        self._emit_task: Optional[asyncio.Task] = None
        self._emit_thread: Optional[threading.Thread] = None

        # WebSocket client session and connection
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None

        # Load trading section (guaranteed valid by AuroraConfig validation).
        trading = self.config.trading

        # Symbols: Load from instruments dict keys. Fail if empty.
        self.symbols: list[str] = list(trading.instruments.keys())
        if not self.symbols:
            raise ValueError(
                "trading.instruments must contain at least one symbol")

        # Anchors: Load from macro_sync config. Fail if None/missing.
        if not trading.market_data or not trading.market_data.macro_sync:
            raise ValueError(
                "trading.market_data.macro_sync must be configured")
        self.anchors: list[str] = trading.market_data.macro_sync.anchors

        # Poll interval: Direct access (validated by Pydantic).
        self.poll_interval_sec: int = trading.market_data.poll_interval_sec
        self.websocket_streams = ["bookTicker", "trade"]

        # Resolve domain mode (live vs testnet).
        mode = get_domain_mode_from_mapping(self.config, "market_data")
        self.data_source_tag = "live" if mode in [
            "live", "hybrid_live_data_testnet_exec"] else "testnet"

        # Load API credentials based on resolved mode.
        env = (self.config.binance_api.live
               if self.data_source_tag == "live"
               else self.config.binance_api.testnet)
        if not all([env.api_key, env.api_secret, env.rest_url]):
            raise ValueError(
                f"API configuration for '{self.data_source_tag}' mode is incomplete: "
                f"missing api_key/api_secret/rest_url")

        # Initialize BinanceAdapter with clean credentials.
        self.adapter = BinanceAdapter(
            api_key=str(env.api_key),
            api_secret=str(env.api_secret),
            rest_url=str(env.rest_url),
        )

        # Initialize WebSocket aggregator for real-time data collection.
        self.aggregator = WebSocketAggregator(
            self.symbols, window_seconds=60, anchors=self.anchors)

        LOG.info(f"✅ MarketDataConnector initialized: symbols={self.symbols}, "
                 f"anchors={self.anchors}, mode={self.data_source_tag}")

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

    def _get_ws_url(self) -> str:
        """
        Get the correct WebSocket URL based on data_source_tag.

        Returns:
            WebSocket URL string (live or testnet).
        """
        if self.data_source_tag == "live":
            return self.WS_URL_LIVE
        else:
            return self.WS_URL_TESTNET

    def _make_subscribe_payload(self) -> dict:
        """
        Construct the JSON subscription payload for all trading symbols.

        Each symbol subscribes to:
        - <symbol>@bookTicker (order book updates)
        - <symbol>@trade (trade stream)

        Returns:
            Subscription payload dict with format:
            {"method": "SUBSCRIBE", "params": [...], "id": 1}
        """
        streams: list[str] = []
        for symbol in self.symbols:
            # Binance requires lowercase symbols for streams
            symbol_lower = symbol.lower()
            streams.append(f"{symbol_lower}@bookTicker")
            streams.append(f"{symbol_lower}@trade")

        return {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1,
        }

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """
        Parse and dispatch incoming WebSocket message to aggregator.

        Handles:
        - bookTicker events: update order book state
        - trade events: update trade flow state
        - ping: application-level keep-alive (though aiohttp may handle low-level pings)

        Args:
            msg: Parsed JSON message from WebSocket.
        """
        # Binance Combined Stream wraps messages in {"stream": "...", "data": {...}}
        # Unwrap if this is a combined stream message
        if "stream" in msg and "data" in msg:
            msg = msg["data"]

        # Skip subscription responses
        if "result" in msg or "id" in msg and "result" in msg:
            LOG.debug(f"Subscription response: {msg}")
            return

        # Detect event type - Binance Spot bookTicker doesn't have 'e' field!
        # Must detect by presence of specific keys
        event_type = msg.get("e")

        # BookTicker detection: has 'b', 'B', 'a', 'A', 's' but no 'e'
        if not event_type and all(k in msg for k in ["b", "B", "a", "A", "s"]):
            event_type = "bookTicker"

        # Trade detection: has 'p', 'q', 'm', 's' but no 'e' (some streams)
        if not event_type and all(k in msg for k in ["p", "q", "m", "s"]):
            event_type = "trade"

        if not event_type:
            LOG.debug(f"Skipping message without event type: {msg}")
            return

        try:
            if event_type == "bookTicker":
                # Order Book Ticker Update
                symbol = msg.get("s", "")
                bid_price = msg.get("b", "0")
                bid_qty = msg.get("B", "0")
                ask_price = msg.get("a", "0")
                ask_qty = msg.get("A", "0")
                ts = msg.get("E", int(time.time() * 1000))

                self.aggregator.on_book_ticker(
                    symbol=symbol,
                    bid_price=bid_price,
                    bid_size=bid_qty,
                    ask_price=ask_price,
                    ask_size=ask_qty,
                    ts=ts,
                )
                LOG.debug(
                    f"📗 BookTicker {symbol}: bid={bid_price}@{bid_qty}, ask={ask_price}@{ask_qty}"
                )

            elif event_type == "trade":
                # Trade Event
                symbol = msg.get("s", "")
                price = msg.get("p", "0")
                qty = msg.get("q", "0")
                # True if buyer is maker (sell)
                is_buyer_maker = msg.get("m", False)
                ts = msg.get("T", int(time.time() * 1000))
                # EP-TRADE-ID: Extract trade_id from WebSocket message
                trade_id = msg.get("t")  # Binance trade ID (unique per trade)

                self.aggregator.on_trade(
                    symbol=symbol,
                    price=price,
                    quantity=qty,
                    is_buyer_maker=is_buyer_maker,
                    ts=ts,
                    trade_id=trade_id,
                )
                LOG.debug(
                    f"📈 Trade {symbol}: price={price}, qty={qty}, is_buyer_maker={is_buyer_maker}, trade_id={trade_id}"
                )

            elif event_type == "ping":
                # Application-level ping (respond with pong if needed)
                LOG.debug(
                    "Received ping, aiohttp should handle low-level pings automatically")

            else:
                LOG.debug(
                    f"Unknown event type '{event_type}' in message: {msg}")

        except KeyError as e:
            LOG.error(f"Missing field in message: {e}, msg={msg}")
        except Exception as e:
            LOG.error(f"Error handling WebSocket message: {e}", exc_info=True)

    async def _on_tick_event(self, symbol: str, tick: dict[str, Any]) -> None:
        """Async wrapper to forward aggregator ticks to the synchronous emitter."""
        self._emit_market_tick(symbol, tick)

    async def start_async(self) -> None:
        """
        Async version of start() - for use with run_coroutine_threadsafe.

        Uses hybrid architecture: async WebSocket + sync emit thread.
        """
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        self.running = True

        # Start WebSocket task
        loop = asyncio.get_running_loop()
        self._ws_task = loop.create_task(self._ws_loop())

        # Start sync emit loop in dedicated thread
        self._emit_thread = threading.Thread(
            target=self._sync_emit_loop,
            name="MarketDataEmitter",
            daemon=True
        )
        self._emit_thread.start()

        LOG.info("✅ MarketDataConnector started (async entry, hybrid architecture)")

    def _sync_emit_loop(self) -> None:
        """
        Synchronous emit loop running in dedicated thread.

        This decouples market tick emission from the async event loop,
        preventing FSM listener processing from blocking WebSocket handling.
        """
        LOG.info("🚀 Sync emit loop started (interval=%ds)",
                 self.poll_interval_sec)
        iteration = 0
        while self.running:
            try:
                iteration += 1
                emitted_count = 0

                # Emit trading symbol ticks
                for symbol in self.symbols:
                    try:
                        tick = self.aggregator.get_market_tick(symbol)
                        if tick:
                            self._emit_market_tick(symbol, tick)
                            emitted_count += 1
                        else:
                            LOG.debug(f"⚠️ No tick data for {symbol}")
                    except Exception as e:
                        LOG.error(
                            f"Error emitting tick for {symbol}: {e}", exc_info=True)

                # Emit anchor price updates
                for anchor in self.anchors:
                    try:
                        if anchor in self.aggregator.state:
                            price = self.aggregator.state[anchor].get(
                                "latest_price")
                            if price and self.feature_engineering:
                                self.feature_engineering.update_anchor_price(
                                    anchor, str(price))
                    except Exception as e:
                        LOG.error(
                            f"Error updating anchor {anchor}: {e}", exc_info=True)

                # Log summary every 10 iterations
                if iteration % 10 == 0:
                    LOG.debug(
                        f"📊 Sync emit iteration {iteration}: emitted {emitted_count}/{len(self.symbols)} ticks")

                time.sleep(self.poll_interval_sec)
            except Exception as e:
                LOG.error(f"Error in sync emit loop: {e}", exc_info=True)
                time.sleep(1)  # Backoff on error

        LOG.info("🛑 Sync emit loop stopped")

    def start(self) -> None:
        """
        Start WebSocket and sync emitter.

        Architecture:
        - WebSocket runs in async context (receives live data from Binance)
        - Sync emit loop runs in dedicated thread (emits FSM events)

        This hybrid approach ensures FSM listener processing doesn't block
        the WebSocket event loop.
        """
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        self.running = True

        # Start WebSocket in async context (if available)
        try:
            loop = asyncio.get_running_loop()
            self._ws_task = loop.create_task(self._ws_loop())
            LOG.info("✅ WebSocket task started in async loop")
        except RuntimeError:
            LOG.warning("No async loop available, WebSocket will not start")

        # Start sync emit loop in dedicated thread
        self._emit_thread = threading.Thread(
            target=self._sync_emit_loop,
            name="MarketDataEmitter",
            daemon=True
        )
        self._emit_thread.start()

        LOG.info("✅ MarketDataConnector started (hybrid: async WS + sync emit)")

    async def _ws_loop(self) -> None:
        """Maintain a WS connection with exponential backoff upon failure."""

        retry_delay = 1.0
        while self.running:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()

            ws_url = self._get_ws_url()
            LOG.info(f"🔗 Connecting to WebSocket: {ws_url}")

            try:
                async with self.session.ws_connect(ws_url) as ws:
                    self.ws = ws
                    LOG.info(f"✅ Connected to Binance WebSocket ({ws_url})")

                    payload = self._make_subscribe_payload()
                    await ws.send_json(payload)
                    LOG.info(
                        f"✅ Subscription sent: {len(payload['params'])} streams")

                    retry_delay = 1.0
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                self._handle_message(data)
                            except json.JSONDecodeError as e:
                                LOG.error(
                                    f"Failed to decode JSON: {e}, msg={msg.data}"
                                )
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            LOG.error(f"WebSocket error: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            LOG.info("WebSocket closed by server")
                            break

            except asyncio.CancelledError:
                LOG.info("WebSocket task cancelled (stopping)")
                break
            except Exception as e:
                LOG.error(
                    f"WebSocket connection failed: {e}. Retrying in {retry_delay}s...",
                    exc_info=True,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
                continue
            finally:
                self.ws = None
                LOG.debug(
                    "WebSocket context exited, will retry if still running")

        self.running = False
        LOG.info("WebSocket loop ended")

    async def _cleanup(self) -> None:
        """Close aiohttp session and WebSocket connection gracefully."""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None
                LOG.debug("WebSocket connection closed")

            if self.session:
                await self.session.close()
                self.session = None
                LOG.debug("aiohttp ClientSession closed")
        except Exception as e:
            LOG.error(f"Error during cleanup: {e}")

    def stop(self) -> None:
        """
        Stop the WebSocket connector and sync emitter gracefully.
        """
        if not self.running:
            LOG.warning("MarketDataConnector is not running.")
            return

        LOG.info("Stopping MarketDataConnector...")
        self.running = False

        # Stop sync emit thread
        if self._emit_thread and self._emit_thread.is_alive():
            LOG.info("Waiting for emit thread to stop...")
            self._emit_thread.join(timeout=5.0)
            if self._emit_thread.is_alive():
                LOG.warning("Emit thread did not stop gracefully within 5s")
        self._emit_thread = None

        # Cancel the WebSocket task
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            LOG.info("WebSocket task cancelled")
        self._ws_task = None

        # Cancel the async emitter task (legacy, may not be used)
        if self._emit_task and not self._emit_task.done():
            self._emit_task.cancel()
            LOG.info("Async emitter task cancelled")
        self._emit_task = None

        # Schedule cleanup if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._cleanup())
        except RuntimeError:
            LOG.debug(
                "stop() called outside async context; async cleanup skipped")

        LOG.info("✅ MarketDataConnector stopped")

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
