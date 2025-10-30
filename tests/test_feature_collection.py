"""
Test script to collect feature parameters (obi, tfi, delta_price) from Binance for ETHUSDT and BTCUSDT over 30 seconds.
"""

import decimal
import logging
import os
import time
from collections import defaultdict
from typing import Dict

from dotenv import load_dotenv
from unicorn_binance_websocket_api import BinanceWebSocketApiManager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class FeatureCollector:
    def __init__(self, symbols: list[str]):
        load_dotenv()
        self.symbols = symbols
        self.last_tick_data: Dict[str, dict] = {}
        self.features_collected: Dict[str, list] = defaultdict(list)
        self.start_time = time.time()

        # Initialize Binance WebSocket
        testnet = os.getenv("USE_TESTNET", "false").lower() == "true"
        exchange = "binance.com-testnet" if testnet else "binance.com"
        logger.info(f"Using exchange: {exchange}")
        self.bwam = BinanceWebSocketApiManager(exchange=exchange)
        self.streams = []

        for symbol in symbols:
            stream_id = self.bwam.create_stream(
                "ticker", symbol.lower(), stream_label=f"{symbol}_ticker"
            )
            self.streams.append(stream_id)
            logger.info(f"Created stream for {symbol}: {stream_id}")

    def collect_features(self, duration_seconds: int = 30):
        """Collect features for the specified duration."""
        logger.info(f"Starting feature collection for {duration_seconds} seconds...")

        while time.time() - self.start_time < duration_seconds:
            if self.bwam.is_manager_stopping():
                break

            stream_data = self.bwam.pop_stream_data_from_stream_buffer()
            if stream_data:
                self._process_stream_data(stream_data)

            time.sleep(0.1)  # Small delay to avoid busy loop

        self.bwam.stop_manager_with_all_streams()
        logger.info("Feature collection completed.")

    def _process_stream_data(self, stream_data: dict):
        """Process incoming stream data and calculate features."""
        try:
            logger.debug(f"Raw stream_data: {stream_data}")
            if not isinstance(stream_data, dict) or "data" not in stream_data:
                logger.debug(f"Skipping invalid stream_data: {type(stream_data)}")
                return
            data = stream_data.get("data", {})
            logger.debug(f"Received data: {data}")
            symbol = data.get("s", "").upper()
            if symbol not in self.symbols:
                return
            logger.info(f"Processing {symbol} data: keys={list(data.keys())}")

            # Convert to tick format similar to project
            current_tick = {
                "symbol": symbol,
                "price": data.get("c", "0"),  # Close price
                "bid_size": data.get("B", "0"),  # Bid quantity
                "ask_size": data.get("A", "0"),  # Ask quantity
                "buy_volume": data.get("v", "0"),  # Volume
                "sell_volume": data.get("q", "0"),  # Quote volume (approximate)
                "ts": int(data.get("E", time.time() * 1000)),  # Event time
            }

            last_tick = self.last_tick_data.get(symbol)
            self.last_tick_data[symbol] = current_tick

            if not last_tick:
                return

            # Calculate features (same as feature_engineering.py)
            features = self._calculate_features(current_tick, last_tick)
            self.features_collected[symbol].append(features)

        except Exception as e:
            logger.error(f"Error processing stream data: {e}")

    def _calculate_features(self, current_tick: dict, last_tick: dict) -> dict:
        """Calculate obi, tfi, delta_price."""
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

        return {
            "obi": float(obi),
            "tfi": float(tfi),
            "delta_price": float(delta_price),
            "price": float(price),
        }

    def get_summary(self) -> dict:
        """Get summary of collected features."""
        summary = {}
        for symbol, features_list in self.features_collected.items():
            if not features_list:
                continue

            obi_values = [f["obi"] for f in features_list]
            tfi_values = [f["tfi"] for f in features_list]
            delta_price_values = [f["delta_price"] for f in features_list]

            summary[symbol] = {
                "count": len(features_list),
                "obi_avg": sum(obi_values) / len(obi_values) if obi_values else 0,
                "tfi_avg": sum(tfi_values) / len(tfi_values) if tfi_values else 0,
                "delta_price_avg": sum(delta_price_values) / len(delta_price_values)
                if delta_price_values
                else 0,
                "obi_range": (min(obi_values), max(obi_values))
                if obi_values
                else (0, 0),
                "tfi_range": (min(tfi_values), max(tfi_values))
                if tfi_values
                else (0, 0),
                "delta_price_range": (min(delta_price_values), max(delta_price_values))
                if delta_price_values
                else (0, 0),
            }
        return summary


def main():
    symbols = ["ETHUSDT", "BTCUSDT"]
    collector = FeatureCollector(symbols)
    collector.collect_features(30)
    summary = collector.get_summary()

    print("\n=== Feature Collection Summary ===")
    for symbol, stats in summary.items():
        print(f"\n{symbol}:")
        print(f"  Samples: {stats['count']}")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")


if __name__ == "__main__":
    main()
