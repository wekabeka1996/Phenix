"""
WebSocket Data Aggregator for real-time market data.

Aggregates live data from bookTicker and trade streams to calculate
real features (OBI, TFI) for trading decisions.
"""

import asyncio
import decimal
import logging
from collections import deque
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta

LOG = logging.getLogger(__name__)


class WebSocketAggregator:
    """Aggregates WebSocket data streams into market tick events."""

    def __init__(self, symbols: list[str], window_seconds: int = 60, anchors: Optional[list[str]] = None):
        """
        Initialize the aggregator.

        Args:
            symbols: List of trading symbols (e.g., ['BTCUSDT', 'ETHUSDT'])
            window_seconds: Time window for trade aggregation (default 60s)
            anchors: List of anchor symbols for macro_sync (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        self.symbols = symbols
        self.window_seconds = window_seconds
        self.anchors = anchors or []

        # All symbols we track (trading + anchors)
        all_tracked = set(symbols + self.anchors)

        # Per-symbol state
        self.state: Dict[str, Dict[str, Any]] = {
            symbol: {
                # BookTicker data (latest)
                "bid_price": decimal.Decimal(0),
                "bid_size": decimal.Decimal(0),
                "ask_price": decimal.Decimal(0),
                "ask_size": decimal.Decimal(0),
                "bid_ask_time": None,
                # Trade flow data (windowed)
                "trades_window": deque(),  # (time, is_seller_maker)
                "buy_trades": 0,
                "sell_trades": 0,
                "window_start_time": None,
                # Price history
                "prices": deque(maxlen=10),
                "latest_price": decimal.Decimal(0),
                # EP-TRADE-ID: Last trade ID for TCA correlation
                "last_trade_id": None,
            }
            for symbol in all_tracked
        }

        self.on_tick_callback: Optional[Callable] = None
        self.on_anchor_update_callback: Optional[Callable] = None

    def set_tick_callback(self, callback: Callable) -> None:
        """
        Set callback to be called when a market tick is ready.

        Args:
            callback: Async function(symbol, tick_data)
        """
        self.on_tick_callback = callback

    def set_anchor_update_callback(self, callback: Callable) -> None:
        """
        Set callback to be called when an anchor price is updated.

        Args:
            callback: Async function(anchor_symbol, price)
        """
        self.on_anchor_update_callback = callback

    def on_book_ticker(
        self,
        symbol: str,
        bid_price: str,
        bid_size: str,
        ask_price: str,
        ask_size: str,
        ts: int,
    ) -> None:
        """
        Process bookTicker stream update. O(1) non-blocking update.

        Args:
            symbol: Trading symbol.
            bid_price: Bid price (string for precision).
            bid_size: Bid size quantity (string).
            ask_price: Ask price (string).
            ask_size: Ask size quantity (string).
            ts: Timestamp in milliseconds.
        """
        if symbol not in self.state:
            return

        state = self.state[symbol]
        state["bid_price"] = decimal.Decimal(bid_price)
        state["bid_size"] = decimal.Decimal(bid_size)
        state["ask_price"] = decimal.Decimal(ask_price)
        state["ask_size"] = decimal.Decimal(ask_size)
        state["bid_ask_time"] = ts

        LOG.debug(
            f"BookTicker {symbol}: bid={bid_price}@{bid_size}, "
            f"ask={ask_price}@{ask_size}"
        )

    def on_trade(
        self, symbol: str, price: str, quantity: str, is_buyer_maker: bool, ts: int,
        trade_id: Optional[int] = None,
    ) -> None:
        """
        Process trade stream update. O(1) amortized non-blocking update.

        Args:
            symbol: Trading symbol.
            price: Trade price (string for precision).
            quantity: Trade quantity (string).
            is_buyer_maker: True if buyer is maker (sell), False if seller is maker (buy).
            ts: Timestamp in milliseconds.
            trade_id: Unique Binance trade ID (optional, for TCA correlation).
        """
        if symbol not in self.state:
            return

        state = self.state[symbol]
        current_time = datetime.now()

        # Initialize window if needed
        if state["window_start_time"] is None:
            state["window_start_time"] = current_time

        # Clean up old trades outside window (amortized O(1) per call)
        window_cutoff = current_time - timedelta(seconds=self.window_seconds)
        while state["trades_window"] and state["trades_window"][0][0] < window_cutoff:
            old_is_seller_maker = state["trades_window"].popleft()[1]
            if old_is_seller_maker:
                state["sell_trades"] = max(0, state["sell_trades"] - 1)
            else:
                state["buy_trades"] = max(0, state["buy_trades"] - 1)

        # Add new trade to window and update counters
        state["trades_window"].append((current_time, is_buyer_maker))
        if is_buyer_maker:
            state["sell_trades"] += 1
        else:
            state["buy_trades"] += 1

        # Update price (Decimal for precision)
        state["latest_price"] = decimal.Decimal(price)
        state["prices"].append(decimal.Decimal(price))

        # EP-TRADE-ID: Store last trade_id for TCA correlation
        if trade_id is not None:
            state["last_trade_id"] = trade_id

        LOG.debug(
            f"Trade {symbol}: price={price}, qty={quantity}, "
            f"is_seller_maker={is_buyer_maker}, trade_id={trade_id}, "
            f"buy_trades={state['buy_trades']}, sell_trades={state['sell_trades']}"
        )

    def get_market_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current market tick with calculated features.

        All numeric fields are returned as strings for JSON serialization.
        Schema: { ts, symbol, price, bid, ask, mid, bid_size, ask_size, buy_volume, sell_volume, features, data_source, bid_ask_count, trade_count }

        Args:
            symbol: Trading symbol.

        Returns:
            Dictionary with market data and calculated features (all numeric as strings), or None if insufficient data.
        """
        if symbol not in self.state:
            return None

        state = self.state[symbol]

        # Need both bookTicker and trade data
        if state["bid_ask_time"] is None or not state["prices"]:
            return None

        # Calculate features using Decimal for precision
        bid_size = state["bid_size"]
        ask_size = state["ask_size"]
        buy_trades = state["buy_trades"]
        sell_trades = state["sell_trades"]

        # OBI: Order Book Imbalance (Decimal -> string for JSON)
        depth = bid_size + ask_size
        obi = (bid_size - ask_size) / \
            depth if depth > 0 else decimal.Decimal(0)

        # TFI: Trade Flow Imbalance (Decimal -> string for JSON)
        total_trades = buy_trades + sell_trades
        tfi = (
            decimal.Decimal(buy_trades - sell_trades) /
            decimal.Decimal(total_trades)
            if total_trades > 0
            else decimal.Decimal(0)
        )

        # delta_price: Price change (Decimal -> string for JSON)
        if len(state["prices"]) >= 2:
            prev_price = state["prices"][-2]
            delta_price = (
                (state["latest_price"] - prev_price) / prev_price
                if prev_price > 0
                else decimal.Decimal(0)
            )
        else:
            delta_price = decimal.Decimal(0)

        # Return tick with all numeric fields as strings (JSON-safe)
        return {
            "ts": str(state["bid_ask_time"]),
            "symbol": symbol,
            "price": str(state["latest_price"]),
            "bid": str(state["bid_price"]),
            "ask": str(state["ask_price"]),
            "mid": str((state["bid_price"] + state["ask_price"]) / 2),
            "bid_size": str(bid_size),  # String for JSON serialization
            "ask_size": str(ask_size),  # String for JSON serialization
            "buy_volume": str(buy_trades),  # String (real trade count)
            "sell_volume": str(sell_trades),  # String (real trade count)
            "features": {
                "obi": str(obi),
                "tfi": str(tfi),
                "delta_price": str(delta_price),
                "absorption": "0.0",
            },
            "data_source": "websocket_live",  # Will be dynamic in Phase 2
            "bid_ask_count": f"{int(bid_size)}/{int(ask_size)}",
            "trade_count": f"BUY:{buy_trades} SELL:{sell_trades}",
            # EP-TRADE-ID: Last trade ID for TCA correlation
            "last_trade_id": state.get("last_trade_id"),
        }

    async def periodic_emit(self, interval_seconds: float = 1.0) -> None:
        """
        Periodically emit market ticks for all symbols and anchors.

        Exception handling is per-callback to ensure one failing callback does not crash the loop.

        Args:
            interval_seconds: Emission interval in seconds.
        """
        while True:
            try:
                # Emit trading symbol ticks
                for symbol in self.symbols:
                    try:
                        tick = self.get_market_tick(symbol)
                        if tick and self.on_tick_callback:
                            LOG.debug(f"📤 Emitting MARKET_TICK for {symbol}")
                            await self.on_tick_callback(symbol, tick)
                        elif not tick:
                            LOG.debug(f"⚠️ No tick data for {symbol}")
                    except Exception as e:
                        LOG.error(
                            f"Error emitting tick for {symbol}: {e}", exc_info=True)

                # Log tick summary every 30 iterations (every ~2.5 min at 5s interval)
                # This provides visibility without spam

                # Emit anchor price updates
                for anchor in self.anchors:
                    try:
                        if anchor in self.state:
                            price = self.state[anchor]["latest_price"]
                            if price and self.on_anchor_update_callback:
                                LOG.debug(
                                    f"📤 Emitting anchor update for {anchor}: {price}")
                                await self.on_anchor_update_callback(anchor, str(price))
                    except Exception as e:
                        LOG.error(
                            f"Error emitting anchor update for {anchor}: {e}", exc_info=True)

                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                LOG.info("periodic_emit cancelled")
                break
            except Exception as e:
                LOG.error(
                    f"Unexpected error in periodic_emit: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
