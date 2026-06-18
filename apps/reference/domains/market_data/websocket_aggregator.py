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
_FLOAT_RESIDUAL_EPS = 1e-7


def _clamp_accumulator(value: float, *, field_name: str, symbol: str) -> float:
    """Clamp float accumulator noise to zero before payload serialization."""
    if not math.isfinite(value):
        LOG.warning(
            "Resetting non-finite %s accumulator for %s: %r",
            field_name,
            symbol,
            value,
        )
        return 0.0
    if abs(value) <= _FLOAT_RESIDUAL_EPS:
        return 0.0
    if value < 0:
        LOG.warning(
            "Resetting negative %s accumulator for %s: %r",
            field_name,
            symbol,
            value,
        )
        return 0.0
    return value


def _format_fixed_point(value: float) -> str:
    """Serialize numeric values without scientific notation."""
    fixed = format(decimal.Decimal(str(value)), "f")
    if "." in fixed:
        fixed = fixed.rstrip("0").rstrip(".")
    return fixed


@dataclass(frozen=True, slots=True)
class TradeTick:
    ts_ms: int
    qty: float
    side: str  # "buy" | "sell" (aggressor side)
    price: Optional[float]
    trade_id: Optional[Any] = None


class WebSocketAggregator:
    """Aggregates WebSocket data streams into market tick events."""

    @staticmethod
    def _increment_drop_reason(state: Dict[str, Any], reason: str) -> None:
        state["trade_dropped"] += 1
        drop_reason_counts = state["drop_reason_counts"]
        drop_reason_counts[reason] = int(drop_reason_counts.get(reason, 0)) + 1

    def __init__(
        self,
        symbols: list[str],
        window_seconds: int = 60,
        anchors: Optional[list[str]] = None,
        out_of_order_tolerance_ms: int = 0,
        trade_silence_reconnect_sec: Optional[float] = None,
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
        self.trade_silence_reconnect_ms = (
            int(float(trade_silence_reconnect_sec) * 1000)
            if trade_silence_reconnect_sec is not None
            else None
        )

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
                "aggtrade_raw_seen": 0,
                "aggtrade_route_attempted": 0,
                "on_trade_called": 0,
                "trade_accepted": 0,
                "trade_dropped": 0,
                "drop_reason_counts": {},
                "tick_emit_count": 0,
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

    def note_aggtrade_raw_seen(self, symbol: str) -> None:
        if symbol not in self.state:
            return
        self.state[symbol]["aggtrade_raw_seen"] += 1

    def note_aggtrade_route_attempted(self, symbol: str) -> None:
        if symbol not in self.state:
            return
        self.state[symbol]["aggtrade_route_attempted"] += 1

    def get_trade_observability_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        if symbol not in self.state:
            return None

        self._cleanup_window(symbol)
        state = self.state[symbol]
        return {
            "symbol": symbol,
            "aggtrade_raw_seen": int(state["aggtrade_raw_seen"]),
            "aggtrade_route_attempted": int(state["aggtrade_route_attempted"]),
            "on_trade_called": int(state["on_trade_called"]),
            "trade_accepted": int(state["trade_accepted"]),
            "trade_dropped": int(state["trade_dropped"]),
            "drop_reason_counts": dict(state["drop_reason_counts"]),
            "buy_count": int(state["buy_trades"]),
            "sell_count": int(state["sell_trades"]),
            "buy_volume": _format_fixed_point(float(state["buy_qty"])),
            "sell_volume": _format_fixed_point(float(state["sell_qty"])),
            "last_trade_ts_ms": int(state["last_trade_ts_ms"] or 0),
            "tick_emit_count": int(state["tick_emit_count"]),
        }

    def get_all_trade_observability_snapshots(self) -> Dict[str, Dict[str, Any]]:
        snapshots: Dict[str, Dict[str, Any]] = {}
        for symbol in self.state:
            snapshot = self.get_trade_observability_snapshot(symbol)
            if snapshot is not None:
                snapshots[symbol] = snapshot
        return snapshots

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
        state["bid_price"] = decimal.Decimal(bid_price)
        state["bid_size"] = decimal.Decimal(bid_size)
        state["ask_price"] = decimal.Decimal(ask_price)
        state["ask_size"] = decimal.Decimal(ask_size)
        state["bid_ask_time"] = ts
        state["last_book_ts_ms"] = int(ts) if ts else 0

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
        state["on_trade_called"] += 1

        ts_ms = int(ts) if ts else 0
        if ts_ms <= 0:
            state["trades_dropped_missing_ts"] += 1
            self._increment_drop_reason(state, "missing_ts")
            return

        try:
            qty = float(quantity)
        except Exception:
            state["trades_dropped_bad_qty"] += 1
            self._increment_drop_reason(state, "bad_qty")
            return
        if (not math.isfinite(qty)) or qty <= 0:
            state["trades_dropped_bad_qty"] += 1
            self._increment_drop_reason(state, "bad_qty")
            return

        try:
            trade_price = float(price)
        except Exception:
            trade_price = None
        if trade_price is not None and ((not math.isfinite(trade_price)) or trade_price <= 0):
            trade_price = None

        # Deduplication check (only for accepted trades; do not "burn" ids on drops)
        if trade_id is not None and trade_id in state["seen_trade_ids"]:
            self._increment_drop_reason(state, "duplicate_trade_id")
            return

        last_ts_ms = int(state["last_trade_ts_ms"] or 0)
        if last_ts_ms > 0 and ts_ms < last_ts_ms:
            lag_ms = last_ts_ms - ts_ms
            if lag_ms <= self.out_of_order_tolerance_ms:
                ts_ms = last_ts_ms
            else:
                state["trades_dropped_out_of_order"] += 1
                self._increment_drop_reason(state, "out_of_order")
                return

        if trade_id is not None:
            state["seen_trade_ids"].add(trade_id)

        # Binance futures aggTrade: m=True (buyer is maker) => aggressor SELL.
        side = _SIDE_SELL if is_buyer_maker else _SIDE_BUY

        # OPTIMIZATION: don't clean up on every trade; cleanup happens lazily.
        state["trades_window"].append(
            TradeTick(ts_ms=ts_ms, qty=qty, side=side,
                      price=trade_price, trade_id=trade_id)
        )
        state["trade_accepted"] += 1
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
        current_ts_ms = max(int(state["last_book_ts_ms"] or 0), int(
            state["last_trade_ts_ms"] or 0))
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

        state["buy_qty"] = _clamp_accumulator(
            float(state["buy_qty"]), field_name="buy_qty", symbol=symbol
        )
        state["sell_qty"] = _clamp_accumulator(
            float(state["sell_qty"]), field_name="sell_qty", symbol=symbol
        )
        state["buy_notional"] = _clamp_accumulator(
            float(state["buy_notional"]), field_name="buy_notional", symbol=symbol
        )
        state["sell_notional"] = _clamp_accumulator(
            float(state["sell_notional"]), field_name="sell_notional", symbol=symbol
        )

    def _trade_flow_metadata(self, state: Dict[str, Any]) -> Dict[str, Any]:
        now_ms = max(int(state["last_book_ts_ms"] or 0), int(state["last_trade_ts_ms"] or 0))
        last_trade_ts_ms = int(state["last_trade_ts_ms"] or 0)
        if last_trade_ts_ms <= 0 or now_ms <= 0:
            return {
                "trade_flow_state": "unknown",
                "trade_flow_age_ms": None,
                "trade_flow_last_trade_ts_ms": None,
                "trade_flow_window_sec": int(self.window_seconds),
            }

        age_ms = max(0, int(now_ms - last_trade_ts_ms))
        if self.trade_silence_reconnect_ms is not None and age_ms > self.trade_silence_reconnect_ms:
            flow_state = "stale"
        elif age_ms > self.window_ms:
            flow_state = "degraded"
        else:
            flow_state = "fresh"
        return {
            "trade_flow_state": flow_state,
            "trade_flow_age_ms": age_ms,
            "trade_flow_last_trade_ts_ms": last_trade_ts_ms,
            "trade_flow_window_sec": int(self.window_seconds),
        }

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

        # Need bookTicker and at least one observed trade price.
        # When the rolling trade window has been fully cleaned up, keep emitting a
        # schema-valid zero-volume tick so downstream can distinguish stale flow
        # from "no price observed yet".
        if state["bid_ask_time"] is None or not state["prices"]:
            return None

        # Calculate features
        bid_size = state["bid_size"]
        ask_size = state["ask_size"]
        buy_trades = state["buy_trades"]
        sell_trades = state["sell_trades"]
        buy_qty = float(state["buy_qty"])
        sell_qty = float(state["sell_qty"])
        state["tick_emit_count"] += 1

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
            "ts": state["bid_ask_time"],
            "symbol": symbol,
            "price": str(state["latest_price"]),
            "bid": str(state["bid_price"]),
            "ask": str(state["ask_price"]),
            "mid": str((state["bid_price"] + state["ask_price"]) / 2),
            "bid_size": str(bid_size),  # NOW REAL!
            "ask_size": str(ask_size),  # NOW REAL!
            "buy_volume": _format_fixed_point(buy_qty),  # quantity (windowed)
            # quantity (windowed)
            "sell_volume": _format_fixed_point(sell_qty),
            "buy_count": int(buy_trades),
            "sell_count": int(sell_trades),
            "buy_notional": _format_fixed_point(float(state["buy_notional"])),
            "sell_notional": _format_fixed_point(float(state["sell_notional"])),
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
            **self._trade_flow_metadata(state),
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
                        ts_ms = int(self.state[anchor].get(
                            "last_price_ts_ms") or 0)
                        if price and self.on_anchor_update_callback and ts_ms > 0:
                            await self.on_anchor_update_callback(anchor, str(price), ts_ms)

                await asyncio.sleep(interval_seconds)
            except Exception as e:
                LOG.error(f"Error in periodic_emit: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
