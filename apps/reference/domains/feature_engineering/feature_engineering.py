"""
FeatureEngineering domain component.
"""

import decimal
import logging
from typing import Dict, Any, TYPE_CHECKING
from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


class FeatureEngineering:
    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.last_tick_data: Dict[str, dict] = {}
        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)

    def on_market_tick(self, event: Message) -> None:
        print(f"DEBUG: event.pld = {event.pld}")
        print(f"DEBUG: event.pld type = {type(event.pld)}")
        symbol = event.pld.get("symbol")
        print(f"DEBUG: symbol = {symbol}, type = {type(symbol)}")
        if not symbol:
            return

        current_tick = event.pld
        last_tick = self.last_tick_data.get(symbol)
        self.last_tick_data[symbol] = current_tick

        if not last_tick:
            return

        self._calculate_and_emit_features(symbol, current_tick, last_tick)

    def _calculate_and_emit_features(
        self, symbol: str, current_tick: dict, last_tick: dict
    ) -> None:
        try:
            print(f"DEBUG: _calculate_and_emit_features called with symbol={symbol}")
            print(f"DEBUG: current_tick={current_tick}")
            print(f"DEBUG: last_tick={last_tick}")

            bid_size = decimal.Decimal(str(current_tick.get("bid_size", 0)))
            ask_size = decimal.Decimal(str(current_tick.get("ask_size", 0)))
            buy_volume = decimal.Decimal(str(current_tick.get("buy_volume", 0)))
            sell_volume = decimal.Decimal(str(current_tick.get("sell_volume", 0)))
            price = decimal.Decimal(str(current_tick.get("price", 0)))
            prev_price = decimal.Decimal(str(last_tick.get("price", 0)))

            depth = bid_size + ask_size
            obi = (bid_size - ask_size) / depth if depth > 0 else decimal.Decimal(0)

            total_flow = buy_volume + sell_volume
            tfi = (
                (buy_volume - sell_volume) / total_flow
                if total_flow > 0
                else decimal.Decimal(0)
            )

            time_diff = current_tick["ts"] - last_tick["ts"]
            delta_price = price - prev_price if time_diff < 1000 else decimal.Decimal(0)

            features = {
                "obi": str(obi),
                "tfi": str(tfi),
                "delta_price": str(delta_price),
                "absorption": "0.0",  # Placeholder
                "price": str(price),
            }

            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "features": features,
            }
            self.fsm.emit(
                "EVT:FEATURES_CALCULATED",
                payload=features_payload,
                why="features_calculated",
            )

        except Exception as e:
            print(f"DEBUG: Exception type: {type(e)}, value: {e}")
            import traceback

            traceback.print_exc()
            self.logger.error(f"Error calculating features for {symbol}: {e}")

    def start(self) -> None:
        """Start the feature engineering component."""
        self.logger.info("FeatureEngineering started")

    def stop(self) -> None:
        """Stop the feature engineering component."""
        self.logger.info("FeatureEngineering stopped")
