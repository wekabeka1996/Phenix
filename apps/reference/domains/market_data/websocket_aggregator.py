"""
WebSocket Data Aggregator for real-time market data.

Aggregates live data from bookTicker and trade streams to calculate
real features (OBI, TFI) for trading decisions.
"""

import asyncio
import decimal
import logging
import math
from collections import deque
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable

LOG = logging.getLogger(__name__)

_SIDE_BUY = "buy"
_SIDE_SELL = "sell"


@dataclass(frozen=True, slots=True)
class TradeTick:
    ts_ms: int
    qty: float
    side: str  # "buy" | "sell" (aggressor side)
    price: Optional[float]
    trade_id: Optional[Any] = None


class WebSocketAggregator:
    """Aggregates WebSocket data streams into market tick events."""

    def __init__(
        self,
        symbols: list[str],
        window_seconds: int = 60,
        anchors: Optional[list[str]] = None,
        out_of_order_tolerance_ms: int = 0,
    ):
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
        self.window_ms = int(window_seconds) * 1000
        self.out_of_order_tolerance_ms = max(0, int(out_of_order_tolerance_ms))

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
                "trades_window": deque(),  # deque[TradeTick]
                "seen_trade_ids": set(),
                "buy_trades": 0,  # count
                "sell_trades": 0,  # count
                "buy_qty": 0.0,
                "sell_qty": 0.0,
                "buy_notional": 0.0,
                "sell_notional": 0.0,
                "trades_dropped_out_of_order": 0,
                "trades_dropped_missing_ts": 0,
                "trades_dropped_bad_qty": 0,
                # Price history
                "prices": deque(maxlen=10),
                "latest_price": decimal.Decimal(0),
                # Exchange-derived timestamps (ms) for SSOT time alignment
                "last_book_ts_ms": 0,
                "last_trade_ts_ms": 0,
                "last_price_ts_ms": 0,
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
            callback: Async function(anchor_symbol, price, ts_ms)
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
        Process bookTicker stream update.

        Args:
            symbol: Trading symbol
            bid_price: Bid price
            bid_size: Bid size (quantity)
            ask_price: Ask price
            ask_size: Ask size (quantity)
            ts: Timestamp
        """
        if symbol not in self.state:
            return

        state = self.state[symbol]
        ts_ms = int(ts) if ts else 0
        last_book_ts_ms = int(state["last_book_ts_ms"] or 0)
        if ts_ms <= 0:
            return
        if last_book_ts_ms > 0 and ts_ms < last_book_ts_ms:
            return

        state["bid_price"] = decimal.Decimal(bid_price)
        state["bid_size"] = decimal.Decimal(bid_size)
        state["ask_price"] = decimal.Decimal(ask_price)
        state["ask_size"] = decimal.Decimal(ask_size)
        state["bid_ask_time"] = ts_ms
        state["last_book_ts_ms"] = ts_ms

        # Removed LOG.debug for hot path optimization

    def on_trade(
        self, symbol: str, price: str, quantity: str, is_buyer_maker: bool, ts: int, trade_id: Optional[Any] = None
    ) -> None:
        """
        Process trade stream update.

        Args:
            symbol: Trading symbol
            price: Trade price
            quantity: Trade quantity
            is_buyer_maker: True if buyer is maker (sell), False if seller is maker (buy)
            ts: Timestamp in milliseconds
            trade_id: Unique trade identifier (to prevent duplicates)
        """
        if symbol not in self.state:
            return

        state = self.state[symbol]

        ts_ms = int(ts) if ts else 0
        if ts_ms <= 0:
            state["trades_dropped_missing_ts"] += 1
            return

        try:
            qty = float(quantity)
        except Exception:
            state["trades_dropped_bad_qty"] += 1
            return
        if (not math.isfinite(qty)) or qty <= 0:
            state["trades_dropped_bad_qty"] += 1
            return

        try:
            trade_price = float(price)
        except Exception:
            trade_price = None
        if trade_price is not None and ((not math.isfinite(trade_price)) or trade_price <= 0):
            trade_price = None

        # Deduplication check (only for accepted trades; do not "burn" ids on drops)
        if trade_id is not None and trade_id in state["seen_trade_ids"]:
            return

        last_ts_ms = int(state["last_trade_ts_ms"] or 0)
        if last_ts_ms > 0 and ts_ms < last_ts_ms:
            lag_ms = last_ts_ms - ts_ms
            if lag_ms <= self.out_of_order_tolerance_ms:
                ts_ms = last_ts_ms
            else:
                state["trades_dropped_out_of_order"] += 1
                return

        if trade_id is not None:
            state["seen_trade_ids"].add(trade_id)

        # Binance futures aggTrade: m=True (buyer is maker) => aggressor SELL.
        side = _SIDE_SELL if is_buyer_maker else _SIDE_BUY

        # OPTIMIZATION: don't clean up on every trade; cleanup happens lazily.
        state["trades_window"].append(
            TradeTick(ts_ms=ts_ms, qty=qty, side=side, price=trade_price, trade_id=trade_id)
        )
        if side == _SIDE_BUY:
            state["buy_trades"] += 1
            state["buy_qty"] += qty
            if trade_price is not None:
                state["buy_notional"] += qty * trade_price
        else:
            state["sell_trades"] += 1
            state["sell_qty"] += qty
            if trade_price is not None:
                state["sell_notional"] += qty * trade_price

        # Update price (use float for speed; convert to Decimal only when needed)
        if trade_price is not None:
            state["latest_price"] = trade_price
            state["prices"].append(state["latest_price"])
        # Exchange-derived timestamp for the last price update (SSOT)
        state["last_trade_ts_ms"] = ts_ms
        state["last_price_ts_ms"] = ts_ms

        # Trigger anchor update callback if this is an anchor
        if symbol in self.anchors and self.on_anchor_update_callback:
            try:
                # We'll call it asynchronously later (from async context)
                pass  # Async callback will be handled in periodic_emit
            except Exception as e:
                LOG.error(f"Error in anchor callback for {symbol}: {e}")

        # Removed LOG.debug for hot path optimization

    def _cleanup_window(self, symbol: str) -> None:
        """Lazy cleanup of old trades from the window."""
        state = self.state[symbol]
        current_ts_ms = max(int(state["last_book_ts_ms"] or 0), int(state["last_trade_ts_ms"] or 0))
        if current_ts_ms <= 0:
            return
        window_cutoff_ts_ms = current_ts_ms - self.window_ms

        while state["trades_window"] and state["trades_window"][0].ts_ms < window_cutoff_ts_ms:
            popped: TradeTick = state["trades_window"].popleft()
            if popped.side == _SIDE_BUY:
                state["buy_trades"] = max(0, state["buy_trades"] - 1)
                state["buy_qty"] -= popped.qty
                if popped.price is not None:
                    state["buy_notional"] -= popped.qty * popped.price
            else:
                state["sell_trades"] = max(0, state["sell_trades"] - 1)
                state["sell_qty"] -= popped.qty
                if popped.price is not None:
                    state["sell_notional"] -= popped.qty * popped.price

            if popped.trade_id is not None and popped.trade_id in state["seen_trade_ids"]:
                state["seen_trade_ids"].remove(popped.trade_id)

    def get_market_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current market tick with calculated features.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with market data and calculated features, or None
        """
        if symbol not in self.state:
            return None

        # Perform lazy cleanup before calculation
        self._cleanup_window(symbol)

        state = self.state[symbol]

        # Need both bookTicker and trade data
        if state["bid_ask_time"] is None or not state["prices"]:
            return None

        tick_ts_ms = max(
            int(state["last_book_ts_ms"] or 0),
            int(state["last_trade_ts_ms"] or 0),
            int(state["last_price_ts_ms"] or 0),
        )
        if tick_ts_ms <= 0:
            return None

        # Calculate features
        bid_size = state["bid_size"]
        ask_size = state["ask_size"]
        buy_trades = state["buy_trades"]
        sell_trades = state["sell_trades"]
        buy_qty = float(state["buy_qty"])
        sell_qty = float(state["sell_qty"])

        # OBI: Order Book Imbalance
        depth = bid_size + ask_size
        obi = (bid_size - ask_size) / \
            depth if depth > 0 else decimal.Decimal(0)

        # TFI: Trade Flow Imbalance (volume-weighted)
        total_qty = buy_qty + sell_qty
        tfi = (
            decimal.Decimal(str((buy_qty - sell_qty) / total_qty))
            if total_qty > 0
            else decimal.Decimal(0)
        )

        # delta_price (Handle float/Decimal mix)
        if len(state["prices"]) >= 2:
            prev_price = float(state["prices"][-2])
            curr_price = float(state["latest_price"])
            delta_price = (
                (curr_price - prev_price) / prev_price
                if prev_price > 0
                else 0.0
            )
        else:
            delta_price = 0.0

        return {
            "ts": tick_ts_ms,
            "symbol": symbol,
            "price": str(state["latest_price"]),
            "bid": str(state["bid_price"]),
            "ask": str(state["ask_price"]),
            "mid": str((state["bid_price"] + state["ask_price"]) / 2),
            "bid_size": str(bid_size),  # NOW REAL!
            "ask_size": str(ask_size),  # NOW REAL!
            "buy_volume": str(buy_qty),  # quantity (windowed)
            "sell_volume": str(sell_qty),  # quantity (windowed)
            "buy_count": int(buy_trades),
            "sell_count": int(sell_trades),
            "buy_notional": str(float(state["buy_notional"])),
            "sell_notional": str(float(state["sell_notional"])),
            "trades_dropped_out_of_order": int(state["trades_dropped_out_of_order"]),
            "features": {
                "obi": str(obi),
                "tfi": str(tfi),
                "delta_price": str(delta_price),
                "absorption": "0.0",
            },
            "data_source": "websocket_live",
            "bid_ask_count": f"{int(bid_size)}/{int(ask_size)}",
            "trade_count": f"BUY:{buy_trades} SELL:{sell_trades}",
        }

    async def periodic_emit(self, interval_seconds: float = 1.0) -> None:
        """
        Periodically emit market ticks for all symbols.

        Args:
            interval_seconds: How often to emit ticks
        """
        while True:
            try:
                # Emit trading symbols
                for symbol in self.symbols:
                    tick = self.get_market_tick(symbol)
                    if tick and self.on_tick_callback:
                        await self.on_tick_callback(symbol, tick)

                # Emit anchor price updates
                for anchor in self.anchors:
                    if anchor in self.state:
                        price = self.state[anchor]["latest_price"]
                        ts_ms = int(self.state[anchor].get("last_price_ts_ms") or 0)
                        if price and self.on_anchor_update_callback and ts_ms > 0:
                            await self.on_anchor_update_callback(anchor, str(price), ts_ms)

                await asyncio.sleep(interval_seconds)
            except Exception as e:
                LOG.error(f"Error in periodic_emit: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
