"""
MarketDataConnector for market_data domain (FSMP-P1-T03).

Hybrid approach: Uses REST API to poll klines, bookTicker, and trades to calculate
real-time features (OBI, TFI, delta_price) from live Binance data.
Emits EVT:MARKET_TICK_RECEIVED with accurate feature data.

This is an async-first implementation using aiohttp WebSocket.
"""

import asyncio
import json
import logging
from typing import Any, Optional, TYPE_CHECKING

try:
    import aiohttp  # type: ignore
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore

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

    # WebSocket URLs for FUTURES (not spot!) - live and testnet
    WS_URL_LIVE = "wss://fstream.binance.com/ws"
    WS_URL_TESTNET = "wss://stream.binancefuture.com/ws"

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        if aiohttp is None:
            raise ImportError("aiohttp is required for MarketDataConnector")
        if isinstance(config, dict):
            raise TypeError(
                "MarketDataConnector requires AuroraConfig, got dict")
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
        # FSMP-ARCH-01: Removed self.feature_engineering (legacy tight coupling)

        # Background tasks
        self._ws_task: Optional[asyncio.Task] = None
        self._emit_task: Optional[asyncio.Task] = None

        # WebSocket client session and connection
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None

        # Load trading section (guaranteed valid by AuroraConfig validation).
        trading = self.config.trading

        # CFG-TRADING-YAML-BURN-DOWN-02: Use canonical config.instruments (SSOT)
        # Symbols: Load from instruments dict keys. Fail if empty.
        instruments = self.config.instruments if hasattr(
            self.config, 'instruments') else {}
        self.symbols: list[str] = list(instruments.keys())
        if not self.symbols:
            raise ValueError(
                "config.instruments must contain at least one symbol. "
                "Please configure config/aurora/instruments.yaml (SSOT).")

        # Anchors: Load from macro_sync config. Fail if None/missing.
        if not trading.market_data or not trading.market_data.macro_sync:
            raise ValueError(
                "trading.market_data.macro_sync must be configured. "
                "Please add 'market_data.macro_sync.anchors' to your config.")
        self.anchors: list[str] = trading.market_data.macro_sync.anchors

        # Poll interval: Direct access (validated by Pydantic).
        self.poll_interval_sec: int = trading.market_data.poll_interval_sec
        self.websocket_streams = list(trading.market_data.websocket_streams)
        if "bookTicker" not in self.websocket_streams:
            raise ValueError(
                "trading.market_data.websocket_streams must include bookTicker"
            )
        self.trade_event_names = {
            stream_name for stream_name in self.websocket_streams if stream_name in {"trade", "aggTrade"}
        }
        if not self.trade_event_names:
            raise ValueError(
                "trading.market_data.websocket_streams must include trade or aggTrade"
            )

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

        # Initialize BinanceAdapter for REST calls
        self.adapter = BinanceAdapter(
            api_key=str(env.api_key),
            api_secret=str(env.api_secret),
            rest_url=str(env.rest_url),
        )

        # Initialize WebSocket aggregator for real-time data collection.
        system_md = getattr(getattr(self.config, "system", None), "market_data", None)
        trade_silence_reconnect_sec = (
            getattr(system_md, "trade_silence_reconnect_sec", None)
            if system_md is not None
            else None
        )
        self.aggregator = WebSocketAggregator(
            self.symbols,
            window_seconds=60,
            anchors=self.anchors,
            trade_silence_reconnect_sec=trade_silence_reconnect_sec,
        )

        LOG.info(f"✅ MarketDataConnector initialized: symbols={self.symbols}, "
                 f"anchors={self.anchors}, mode={self.data_source_tag}")

    async def _emit_anchor_update(self, anchor: str, price: str, ts_ms: int) -> None:
        """
        Emit anchor price update as FSM event.

        FSMP-ARCH-01: Replaces direct method call to FeatureEngineering.
        This enables loose coupling and multiprocess-safe anchor updates.
        """
        self.fsm.emit(
            event_name="EVT:ANCHOR_UPDATED",
            payload={"anchor": anchor, "price": price, "ts_ms": int(ts_ms)},
            why=f"Anchor price update for {anchor}",
        )

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
            for stream_name in self.websocket_streams:
                streams.append(f"{symbol_lower}@{stream_name}")

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
        # Skip if message doesn't have event type
        event_type = msg.get("e")
        if not event_type:
            LOG.debug(f"Skipping message without event type: {msg}")
            return

        try:
            if event_type == "bookTicker":
                # Order Book Ticker Update
                symbol = msg["s"] if "s" in msg else ""
                bid_price = msg["b"] if "b" in msg else "0"
                bid_qty = msg["B"] if "B" in msg else "0"
                ask_price = msg["a"] if "a" in msg else "0"
                ask_qty = msg["A"] if "A" in msg else "0"
                if "E" not in msg:
                    return
                ts = msg["E"]

                self.aggregator.on_book_ticker(
                    symbol=symbol,
                    bid_price=bid_price,
                    bid_size=bid_qty,
                    ask_price=ask_price,
                    ask_size=ask_qty,
                    ts=ts,
                )
                # Removed LOG.debug for hot path optimization

            elif event_type in self.trade_event_names:
                # Trade event: support both raw trade and aggTrade contracts.
                symbol = msg["s"] if "s" in msg else ""
                price = msg["p"] if "p" in msg else "0"
                qty = msg["q"] if "q" in msg else "0"
                # True if buyer is maker (sell)
                is_buyer_maker = msg["m"] if "m" in msg else False
                ts = msg["T"] if "T" in msg else (
                    msg["E"] if "E" in msg else 0)
                if ts <= 0:
                    return
                # Aggregate Trade ID for deduplication
                trade_id = msg.get(
                    "a") if event_type == "aggTrade" else msg.get("t")

                self.aggregator.on_trade(
                    symbol=symbol,
                    price=price,
                    quantity=qty,
                    is_buyer_maker=is_buyer_maker,
                    ts=ts,
                    trade_id=trade_id,
                )
                # Removed LOG.debug for hot path optimization

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
        """Async version of start() - for use with run_coroutine_threadsafe."""
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        loop = asyncio.get_running_loop()
        self.running = True
        self.aggregator.set_tick_callback(self._on_tick_event)
        # FSMP-ARCH-01: Use FSM event-based anchor updates instead of direct method call
        self.aggregator.set_anchor_update_callback(self._emit_anchor_update)

        self._emit_task = loop.create_task(
            self.aggregator.periodic_emit(self.poll_interval_sec)
        )
        self._ws_task = loop.create_task(self._ws_loop())

        LOG.info("✅ MarketDataConnector emitter started (async)")

    def start(self) -> None:
        """Start WebSocket and aggregator emitter tasks using the running event loop."""
        if self.running:
            LOG.warning("MarketDataConnector already running.")
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            LOG.error(
                "Cannot start MarketDataConnector outside of an async loop.")
            return

        self.running = True
        self.aggregator.set_tick_callback(self._on_tick_event)
        # FSMP-ARCH-01: Use FSM event-based anchor updates instead of direct method call
        self.aggregator.set_anchor_update_callback(self._emit_anchor_update)

        self._emit_task = loop.create_task(
            self.aggregator.periodic_emit(self.poll_interval_sec)
        )
        self._ws_task = loop.create_task(self._ws_loop())

        LOG.info("✅ MarketDataConnector emitter started")

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
        Stop the WebSocket connector.

        Cancels the `_ws_loop` task and closes the session/connection.
        """
        if not self.running:
            LOG.warning("MarketDataConnector is not running.")
            return

        self.running = False

        # Cancel the WebSocket task
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            LOG.info("WebSocket task cancelled")
        self._ws_task = None

        # Cancel the aggregator emitter task
        if self._emit_task and not self._emit_task.done():
            self._emit_task.cancel()
            LOG.info("MarketDataConnector emitter task cancelled")
        self._emit_task = None

        # Schedule cleanup if we're in an async context
        try:
            _ = asyncio.get_running_loop()
            asyncio.create_task(self._cleanup())
        except RuntimeError:
            # Not in an async context; try to cleanup synchronously
            LOG.warning(
                "stop() called outside async context; cleanup may be incomplete")
            try:
                # Fallback: close session synchronously if possible
                if self.session:
                    # Note: This is not ideal but necessary for sync contexts
                    pass  # aiohttp session requires async close
            except Exception as e:
                LOG.debug(f"Could not cleanup session: {e}")

        LOG.info("✅ MarketDataConnector stopped")

    def _emit_market_tick(self, symbol: str, tick: dict[str, Any]) -> None:
        """Emit a market tick event with real feature data."""
        try:
            # Debug: Log what we actually received
            LOG.debug(f"🔍 Tick data for {symbol}: {tick}")

            # Defensive: Check required keys exist
            required_keys = [
                "ts",
                "price",
                "bid",
                "ask",
                "mid",
                "bid_size",
                "ask_size",
                "buy_volume",
                "sell_volume",
                "data_source",
            ]
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
                # Optional trade metadata (TASK31 additive)
                "buy_count": tick["buy_count"] if "buy_count" in tick else None,
                "sell_count": tick["sell_count"] if "sell_count" in tick else None,
                "buy_notional": tick["buy_notional"] if "buy_notional" in tick else None,
                "sell_notional": tick["sell_notional"] if "sell_notional" in tick else None,
                "trades_dropped_out_of_order": tick["trades_dropped_out_of_order"]
                if "trades_dropped_out_of_order" in tick
                else None,
                "trade_flow_state": tick.get("trade_flow_state"),
                "trade_flow_age_ms": tick.get("trade_flow_age_ms"),
                "trade_flow_last_trade_ts_ms": tick.get("trade_flow_last_trade_ts_ms"),
                "trade_flow_window_sec": tick.get("trade_flow_window_sec"),
                "data_type": "market_tick_aggregated",
                "data_source": tick["data_source"],
                "debug_info": (
                    f"BID/ASK: {tick['bid_ask_count'] if 'bid_ask_count' in tick else 'N/A'}, "
                    f"Trades: {tick['trade_count'] if 'trade_count' in tick else 'N/A'}"
                ),
            }

            def _emit(payload_to_emit: dict[str, Any]) -> None:
                self.fsm.emit(
                    event_name="EVT:MARKET_TICK_RECEIVED",
                    payload=payload_to_emit,
                    why=f"Real-time market tick for {symbol} from {tick['data_source']}",
                )

            try:
                _emit(payload)
            except Exception as emit_error:
                err_text = str(emit_error)
                # Legacy-compat fallback: some runtime schema snapshots still reject TASK31 additive fields.
                if "Additional properties are not allowed" in err_text:
                    legacy_payload = {
                        "ts": tick["ts"],
                        "symbol": symbol,
                        "price": tick["price"],
                        "bid": tick["bid"],
                        "ask": tick["ask"],
                        "mid": tick["mid"],
                        "bid_size": tick["bid_size"],
                        "ask_size": tick["ask_size"],
                        "buy_volume": tick["buy_volume"],
                        "sell_volume": tick["sell_volume"],
                        "data_type": "market_tick_aggregated",
                        "data_source": tick["data_source"],
                        "debug_info": payload["debug_info"],
                    }
                    try:
                        _emit(legacy_payload)
                        LOG.warning(
                            "MARKET_TICK_RECEIVED emitted via legacy-compatible payload for symbol=%s",
                            symbol,
                        )
                    except Exception as legacy_emit_error:
                        legacy_err_text = str(legacy_emit_error)
                        if "does not match '^[A-Z]{2,10}USDT$'" in legacy_err_text:
                            LOG.warning(
                                "Skipping tick for symbol=%s due to active runtime symbol pattern mismatch",
                                symbol,
                            )
                            return
                        raise
                elif "does not match '^[A-Z]{2,10}USDT$'" in err_text:
                    LOG.warning(
                        "Skipping tick for symbol=%s due to active runtime symbol pattern mismatch",
                        symbol,
                    )
                    return
                else:
                    raise

            trade_count = tick.get("trade_count")
            buy_trade_count = "N/A"
            sell_trade_count = "N/A"
            if trade_count:
                buy_trade_count = str(trade_count).split(":")[1].split()[0]
                sell_trade_count = str(trade_count).split(":")[2]

            LOG.info(
                f"📊 {symbol} Tick: bid={tick['bid_size']}@{tick['bid']}, "
                f"ask={tick['ask_size']}@{tick['ask']}, "
                f"trades: BUY={buy_trade_count} "
                f"SELL={sell_trade_count}"
            )

        except Exception as e:
            LOG.error(
                f"Error emitting market tick for {symbol}: {e}", exc_info=True)
