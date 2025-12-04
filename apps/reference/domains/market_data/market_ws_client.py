"""
WebSocket client for Binance Market Data.
Handles connection, subscription, and message routing for bookTicker and aggTrade.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Callable, Optional

try:
    import websockets
except ImportError:
    websockets = None

LOG = logging.getLogger(__name__)


class MarketWSClient:
    """
    WebSocket client for Binance Market Data.
    Handles connection, subscription, and message routing for bookTicker and aggTrade.
    """

    BASE_URL = "wss://fstream.binance.com/stream"

    def __init__(
        self,
        symbols: List[str],
        on_book_ticker: Callable[[Dict[str, Any]], None],
        on_trade: Callable[[Dict[str, Any]], None],
        reconnect_interval_sec: int = 5,
    ):
        """
        Initialize the WebSocket client.

        Args:
            symbols: List of trading symbols (e.g., ['BTCUSDT', 'ETHUSDT'])
            on_book_ticker: Callback for bookTicker events
            on_trade: Callback for trade events
            reconnect_interval_sec: Interval between reconnect attempts
        """
        self.symbols = [s.lower() for s in symbols]
        self.on_book_ticker = on_book_ticker
        self.on_trade = on_trade
        self.reconnect_interval_sec = reconnect_interval_sec
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start the WebSocket client loop in a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        LOG.info(f"MarketWSClient started for {len(self.symbols)} symbols")

    async def stop(self) -> None:
        """Stop the WebSocket client."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        LOG.info("MarketWSClient stopped")

    def _build_stream_url(self) -> str:
        """Construct the WebSocket URL with streams."""
        streams = []
        for s in self.symbols:
            streams.append(f"{s}@bookTicker")
            streams.append(f"{s}@aggTrade")

        query = "/".join(streams)
        return f"{self.BASE_URL}?streams={query}"

    async def _run_loop(self) -> None:
        """Main connection loop with reconnect logic."""
        if not websockets:
            LOG.error(
                "websockets library not installed. MarketWSClient cannot run.")
            return

        url = self._build_stream_url()

        while self._running:
            try:
                LOG.info(f"Connecting to Market WS: {url[:50]}...")
                async with websockets.connect(url) as ws:
                    LOG.info("Market WS connected")
                    while self._running:
                        msg = await ws.recv()
                        self._handle_message(msg)
            except Exception as e:
                if not self._running:
                    break
                LOG.warning(
                    f"Market WS connection error: {e}. Reconnecting in {self.reconnect_interval_sec}s...")
                await asyncio.sleep(self.reconnect_interval_sec)

    def _handle_message(self, raw_msg: str) -> None:
        """Parse and route incoming messages."""
        try:
            data = json.loads(raw_msg)
            stream = data.get("stream", "")
            payload = data.get("data", {})

            if "bookTicker" in stream:
                self.on_book_ticker(payload)
            elif "aggTrade" in stream:
                self.on_trade(payload)
            else:
                LOG.debug(f"Unknown stream: {stream}")

        except Exception as e:
            LOG.error(f"Error handling Market WS message: {e}", exc_info=True)
