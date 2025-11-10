"""
FeatureEngineering domain component with Phase 1 metrics.

New metrics (Phase 1):
1. ema_bias = (EMA3 - EMA7) / EMA7
2. volume_spike = vol_window / SMA(vol, 5)
3. volatility_state = range_window / SMA(range, 10)
4. depth_imbalance = (asks + depth_half) / (bids + depth_half)
5. macro_sync = Pearson corr(symbol, anchors)
"""

import decimal
import logging
from typing import Dict, Any, TYPE_CHECKING, Optional
from collections import deque
import statistics
from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


class FeatureEngineering:
    def __init__(self, fsm: "FSMCore", config: dict[str, Any], feature_store: Optional[Any] = None) -> None:
        self.fsm = fsm
        self.config = config
        self.feature_store = feature_store
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        self.last_tick_data: Dict[str, dict] = {}

        # Phase 1: State per symbol for new metrics
        self.symbol_state: Dict[str, Dict[str, Any]] = {}

        # Config for new metrics
        try:
            if hasattr(self.config.trading, 'feature_engineering'):
                fe_config = self.config.trading.feature_engineering
            elif isinstance(self.config, dict):
                fe_config = (self.config.get("trading", {})).get(
                    "feature_engineering", {})
            else:
                fe_config = {}
        except (AttributeError, TypeError):
            fe_config = {}

        try:
            if hasattr(fe_config, 'enable_new_metrics'):
                self.enable_new_metrics = fe_config.enable_new_metrics
            else:
                self.enable_new_metrics = True
        except (AttributeError, TypeError):
            self.enable_new_metrics = True

        try:
            if hasattr(self.config.trading, 'feature_engineering') and hasattr(self.config.trading.feature_engineering, 'ema'):
                self.ema_config = self.config.trading.feature_engineering.ema
            elif isinstance(self.config, dict):
                trading_config = self.config.get("trading", {})
                fe_config = trading_config.get("feature_engineering", {})
                self.ema_config = fe_config.get("ema", {})
            else:
                self.ema_config = {}
        except (AttributeError, TypeError):
            self.ema_config = {}

        try:
            if hasattr(self.config.trading, 'feature_engineering') and hasattr(self.config.trading.feature_engineering, 'volume'):
                self.volume_config = self.config.trading.feature_engineering.volume
            elif isinstance(self.config, dict):
                trading_config = self.config.get("trading", {})
                fe_config = trading_config.get("feature_engineering", {})
                self.volume_config = fe_config.get("volume", {})
            else:
                self.volume_config = {}
        except (AttributeError, TypeError):
            self.volume_config = {}

        try:
            if hasattr(self.config.trading, 'feature_engineering') and hasattr(self.config.trading.feature_engineering, 'volatility'):
                self.volatility_config = self.config.trading.feature_engineering.volatility
            elif isinstance(self.config, dict):
                trading_config = self.config.get("trading", {})
                fe_config = trading_config.get("feature_engineering", {})
                self.volatility_config = fe_config.get("volatility", {})
            else:
                self.volatility_config = {}
        except (AttributeError, TypeError):
            self.volatility_config = {}

        try:
            if hasattr(self.config.trading, 'feature_engineering') and hasattr(self.config.trading.feature_engineering, 'liquidity'):
                self.liquidity_config = self.config.trading.feature_engineering.liquidity
            elif isinstance(self.config, dict):
                trading_config = self.config.get("trading", {})
                fe_config = trading_config.get("feature_engineering", {})
                self.liquidity_config = fe_config.get("liquidity", {})
            else:
                self.liquidity_config = {}
        except (AttributeError, TypeError):
            self.liquidity_config = {}

        # Macro sync config
        try:
            if hasattr(self.config.trading, 'market_data') and hasattr(self.config.trading.market_data, 'macro_sync'):
                self.macro_sync_config = self.config.trading.market_data.macro_sync
            elif isinstance(self.config, dict):
                self.macro_sync_config = ((self.config.get("trading", {})).get(
                    "market_data", {})).get("macro_sync", {})
            else:
                self.macro_sync_config = {}
        except (AttributeError, TypeError):
            self.macro_sync_config = {}

        try:
            if hasattr(self.macro_sync_config, 'enabled'):
                self.macro_sync_enabled = self.macro_sync_config.enabled
            else:
                self.macro_sync_enabled = False
        except (AttributeError, TypeError):
            self.macro_sync_enabled = False

        try:
            if hasattr(self.macro_sync_config, 'anchors'):
                self.anchor_symbols = self.macro_sync_config.anchors
            else:
                self.anchor_symbols = ["BTCUSDT", "ETHUSDT"]
        except (AttributeError, TypeError):
            self.anchor_symbols = ["BTCUSDT", "ETHUSDT"]

        try:
            if hasattr(self.macro_sync_config, 'window'):
                self.macro_window = self.macro_sync_config.window
            else:
                self.macro_window = 60
        except (AttributeError, TypeError):
            self.macro_window = 60

        # Anchor price buffers for macro_sync
        self.anchor_prices: Dict[str, deque] = {anchor: deque(maxlen=self.macro_window)
                                                for anchor in self.anchor_symbols}

        self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self.on_market_tick)

    def update_anchor_price(self, anchor: str, price: str) -> None:
        """Update anchor price buffer directly from MarketData."""
        try:
            if anchor in self.anchor_prices:
                self.anchor_prices[anchor].append(decimal.Decimal(price))
                self.logger.debug(f"Updated anchor {anchor} price: {price}")
        except Exception as e:
            self.logger.error(f"Error updating anchor price {anchor}: {e}")

    def _init_symbol_state(self, symbol: str) -> None:
        """Initialize state for a new symbol."""
        try:
            if hasattr(self.ema_config, 'period_short'):
                ema_short = self.ema_config.period_short
            else:
                ema_short = 3
        except (AttributeError, TypeError):
            ema_short = 3

        try:
            if hasattr(self.ema_config, 'period_long'):
                ema_long = self.ema_config.period_long
            else:
                ema_long = 7
        except (AttributeError, TypeError):
            ema_long = 7

        try:
            if hasattr(self.volume_config, 'sma_length'):
                vol_sma_len = self.volume_config.sma_length
            else:
                vol_sma_len = 5
        except (AttributeError, TypeError):
            vol_sma_len = 5

        try:
            if hasattr(self.volatility_config, 'sma_length'):
                vol_range_sma_len = self.volatility_config.sma_length
            else:
                vol_range_sma_len = 10
        except (AttributeError, TypeError):
            vol_range_sma_len = 10

        self.symbol_state[symbol] = {
            # EMA state
            "ema3": None,
            "ema7": None,
            "ema3_alpha": 2 / (ema_short + 1),
            "ema7_alpha": 2 / (ema_long + 1),
            # Volume spike state
            "vol_window_start_ts": None,
            "vol_current_ts": None,
            "vol_window_trades": 0,  # Count of trades in current window
            "vol_hist": deque(maxlen=vol_sma_len),  # Trade volumes per window
            # Volatility state
            "range_window_start_ts": None,
            "range_min": None,
            "range_max": None,
            "range_hist": deque(maxlen=vol_range_sma_len),  # Ranges per window
            # Returns for macro_sync
            "returns_buffer": deque(maxlen=self.macro_window),
            "prev_price": None,
        }

    def _update_ema(self, symbol: str, price: decimal.Decimal) -> None:
        """Update EMA3 and EMA7 for the symbol."""
        state = self.symbol_state[symbol]

        if state["ema3"] is None:
            state["ema3"] = price
            state["ema7"] = price
        else:
            state["ema3"] = price * decimal.Decimal(
                state["ema3_alpha"]) + state["ema3"] * decimal.Decimal(1 - state["ema3_alpha"])
            state["ema7"] = price * decimal.Decimal(
                state["ema7_alpha"]) + state["ema7"] * decimal.Decimal(1 - state["ema7_alpha"])

    def _compute_ema_bias(self, symbol: str) -> decimal.Decimal:
        """Compute EMA bias = (EMA3 - EMA7) / EMA7."""
        state = self.symbol_state[symbol]
        if state["ema7"] and state["ema7"] > 0:
            bias = (state["ema3"] - state["ema7"]) / state["ema7"]
            # Clamp to ±2% (-0.02, 0.02) and map to [0,1]
            bias_clamped = max(decimal.Decimal("-0.02"),
                               min(decimal.Decimal("0.02"), bias))
            phi = (bias_clamped / decimal.Decimal("0.02") +
                   decimal.Decimal("1")) / decimal.Decimal("2")
            return phi
        return decimal.Decimal("0.5")

    def _update_volume_spike(self, symbol: str, current_tick: dict, time_diff_ms: int) -> None:
        """Update volume window and compute spike (FIX #2: use real volumes, not tick count)."""
        state = self.symbol_state[symbol]
        current_ts = current_tick["ts"]

        try:
            if hasattr(self.volume_config, 'window_sec'):
                window_sec = self.volume_config.window_sec
            else:
                window_sec = 60
        except (AttributeError, TypeError):
            window_sec = 60

        window_ms = window_sec * 1000

        # Initialize or reset window if needed
        if state["vol_window_start_ts"] is None:
            state["vol_window_start_ts"] = current_ts
            state["vol_current_ts"] = current_ts

        # Check if time to close window
        if current_ts - state["vol_window_start_ts"] >= window_ms:
            # Close window and store volume count
            if state["vol_window_trades"] > 0:
                state["vol_hist"].append(state["vol_window_trades"])
            # Reset window
            state["vol_window_start_ts"] = current_ts
            state["vol_window_trades"] = 0

        # 🆕 FIX #2: Add REAL volume from buy_volume + sell_volume (not just tick count)
        buy_vol = float(current_tick.get("buy_volume", 0))
        sell_vol = float(current_tick.get("sell_volume", 0))
        current_volume = buy_vol + sell_vol

        # Accumulate real volume in current window
        state["vol_window_trades"] += current_volume
        state["vol_current_ts"] = current_ts

    def _compute_volume_spike(self, symbol: str) -> decimal.Decimal:
        """Compute volume spike = vol_window / SMA(vol, 5)."""
        state = self.symbol_state[symbol]
        if len(state["vol_hist"]) < 2:
            return decimal.Decimal("0.5")

        avg_vol = decimal.Decimal(
            sum(state["vol_hist"])) / len(state["vol_hist"])
        current_vol = decimal.Decimal(state["vol_window_trades"])

        if avg_vol > 0:
            spike = current_vol / avg_vol
            # Cap at 3.0 and map to [0,1]
            spike_capped = min(spike, decimal.Decimal("3.0"))
            phi = spike_capped / decimal.Decimal("3.0")
            return phi
        return decimal.Decimal("0.5")

    def _update_volatility_state(self, symbol: str, price: decimal.Decimal, current_tick: dict) -> None:
        """Update volatility range window."""
        state = self.symbol_state[symbol]
        current_ts = current_tick["ts"]

        try:
            if hasattr(self.volatility_config, 'window_sec'):
                window_sec = self.volatility_config.window_sec
            else:
                window_sec = 60
        except (AttributeError, TypeError):
            window_sec = 60

        window_ms = window_sec * 1000

        # Initialize window
        if state["range_window_start_ts"] is None:
            state["range_window_start_ts"] = current_ts
            state["range_min"] = price
            state["range_max"] = price

        # Check if time to close window
        if current_ts - state["range_window_start_ts"] >= window_ms:
            # Close window and store range
            if state["range_min"] is not None and state["range_max"] is not None:
                range_val = state["range_max"] - state["range_min"]
                state["range_hist"].append(range_val)
            # Reset window
            state["range_window_start_ts"] = current_ts
            state["range_min"] = price
            state["range_max"] = price

        # Update min/max in current window
        state["range_min"] = min(state["range_min"], price)
        state["range_max"] = max(state["range_max"], price)

    def _compute_volatility_state(self, symbol: str) -> decimal.Decimal:
        """Compute volatility state = range / SMA(range, 10)."""
        state = self.symbol_state[symbol]
        if len(state["range_hist"]) < 2:
            return decimal.Decimal("0.5")

        avg_range = sum(state["range_hist"]) / len(state["range_hist"])
        current_range = state["range_max"] - \
            state["range_min"] if state["range_max"] and state["range_min"] else decimal.Decimal(
                "0")

        if avg_range > 0:
            ratio = current_range / avg_range
            ratio_capped = min(ratio, decimal.Decimal("3.0"))
            phi = ratio_capped / decimal.Decimal("3.0")
            return phi
        return decimal.Decimal("0.5")

    def _compute_depth_imbalance(self, bid_size: decimal.Decimal, ask_size: decimal.Decimal) -> decimal.Decimal:
        """Compute depth imbalance from bid/ask sizes."""
        try:
            if hasattr(self.liquidity_config, 'depth_half'):
                depth_half = self.liquidity_config.depth_half
            else:
                depth_half = 1000
        except (AttributeError, TypeError):
            depth_half = 1000

        depth_half = decimal.Decimal(str(depth_half))

        # ratio = (asks + depth_half) / (bids + depth_half)
        denominator = bid_size + depth_half
        numerator = ask_size + depth_half

        if denominator > 0:
            ratio = numerator / denominator
            # Map ratio to [-1, 1]: imbalance = (ratio - 1) / (ratio + 1)
            imbalance = (ratio - decimal.Decimal("1")) / \
                (ratio + decimal.Decimal("1"))
            # Map to [0,1]
            phi = (imbalance + decimal.Decimal("1")) / decimal.Decimal("2")
            return phi
        return decimal.Decimal("0.5")

    def _update_macro_sync_buffer(self, symbol: str, price: decimal.Decimal, current_tick: dict, time_diff_ms: int) -> None:
        """Update return for macro_sync correlation."""
        state = self.symbol_state[symbol]

        if state["prev_price"] and state["prev_price"] > 0 and time_diff_ms < 5000:
            ret = (price - state["prev_price"]) / state["prev_price"]
            state["returns_buffer"].append(float(ret))

        state["prev_price"] = price

    def _compute_macro_sync(self, symbol: str) -> decimal.Decimal:
        """Compute macro_sync = correlation with anchor returns."""
        if not self.macro_sync_enabled or not self.anchor_symbols:
            return decimal.Decimal("0.5")

        state = self.symbol_state[symbol]
        if len(state["returns_buffer"]) < 3:
            return decimal.Decimal("0.5")

        # Average correlation with all anchors
        correlations = []
        for anchor in self.anchor_symbols:
            if anchor not in self.anchor_prices or len(self.anchor_prices[anchor]) < 3:
                continue

            # Compute anchor returns
            anchor_returns = []
            anchor_prices_list = list(self.anchor_prices[anchor])
            for i in range(1, len(anchor_prices_list)):
                if anchor_prices_list[i-1] > 0:
                    ret = (
                        anchor_prices_list[i] - anchor_prices_list[i-1]) / anchor_prices_list[i-1]
                    anchor_returns.append(float(ret))

            # Compute Pearson correlation
            if len(anchor_returns) == len(state["returns_buffer"]):
                try:
                    corr = self._pearson_correlation(
                        list(state["returns_buffer"]), anchor_returns)
                    correlations.append(corr)
                except Exception as e:
                    self.logger.debug(
                        f"Correlation error for {symbol} vs {anchor}: {e}")

        if correlations:
            avg_corr = statistics.mean(correlations)
            # Map from [-1, 1] to [0, 1]
            phi = (decimal.Decimal(str(avg_corr)) +
                   decimal.Decimal("1")) / decimal.Decimal("2")
            return phi

        return decimal.Decimal("0.5")

    def _pearson_correlation(self, x: list, y: list) -> float:
        """Compute Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        mean_x = sum(x) / len(x)
        mean_y = sum(y) / len(y)

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y)
                        for i in range(len(x)))
        denominator = (sum((x[i] - mean_x) ** 2 for i in range(len(x))) ** 0.5) * \
                      (sum((y[i] - mean_y) ** 2 for i in range(len(y))) ** 0.5)

        if denominator > 0:
            return numerator / denominator
        return 0.0

    def on_market_tick(self, event: Message) -> None:
        self.logger.debug(f"event.pld = {event.pld}")
        symbol = event.pld.get("symbol")
        if not symbol:
            return

        # Update anchor prices if this is an anchor
        if symbol in self.anchor_symbols:
            price = decimal.Decimal(str(event.pld.get("price", 0)))
            self.anchor_prices[symbol].append(price)

        current_tick = event.pld
        last_tick = self.last_tick_data.get(symbol)
        self.last_tick_data[symbol] = current_tick

        if not last_tick:
            self.logger.debug(
                f"No previous tick for {symbol}, skipping feature calculation")
            return

        self._calculate_and_emit_features(symbol, current_tick, last_tick)

    def _calculate_and_emit_features(self, symbol: str, current_tick: dict, last_tick: dict) -> None:
        try:
            # Initialize symbol state if needed
            if symbol not in self.symbol_state:
                self._init_symbol_state(symbol)

            bid_size = decimal.Decimal(str(current_tick.get("bid_size", 0)))
            ask_size = decimal.Decimal(str(current_tick.get("ask_size", 0)))
            buy_volume = decimal.Decimal(
                str(current_tick.get("buy_volume", 0)))
            sell_volume = decimal.Decimal(
                str(current_tick.get("sell_volume", 0)))
            price = decimal.Decimal(str(current_tick.get("price", 0)))
            prev_price = decimal.Decimal(str(last_tick.get("price", 0)))

            depth = bid_size + ask_size
            obi = (bid_size - ask_size) / \
                depth if depth > 0 else decimal.Decimal(0)

            total_flow = buy_volume + sell_volume
            tfi = ((buy_volume - sell_volume) /
                   total_flow if total_flow > 0 else decimal.Decimal(0))

            time_diff = current_tick["ts"] - last_tick["ts"]
            delta_price = price - \
                prev_price if time_diff < 5000 else decimal.Decimal(0)

            # Liquidity kappa
            try:
                if hasattr(self.liquidity_config, 'depth_half'):
                    depth_half_val = self.liquidity_config.depth_half
                else:
                    depth_half_val = 1000
            except (AttributeError, TypeError):
                depth_half_val = 1000

            depth_half = decimal.Decimal(str(depth_half_val))
            liq_ratio = (depth / (depth + depth_half)) if (depth +
                                                           depth_half) > 0 else decimal.Decimal("0")
            liq_ratio = max(decimal.Decimal("0"), min(
                decimal.Decimal("1"), liq_ratio))
            liq_kappa = max(decimal.Decimal("0.3"), min(
                decimal.Decimal("1.0"), liq_ratio))

            # Phase 1: Compute new metrics
            features = {
                "obi": str(obi),
                "tfi": str(tfi),
                "delta_price": str(delta_price),
                "absorption": "0.0",
                "price": str(price),
                "liquidity_kappa": str(liq_kappa),
            }

            if self.enable_new_metrics:
                # Update EMA and compute bias
                self._update_ema(symbol, price)
                ema_bias_phi = self._compute_ema_bias(symbol)
                features["ema_bias"] = str(ema_bias_phi)

                # Update volume and compute spike
                self._update_volume_spike(symbol, current_tick, time_diff)
                volume_spike_phi = self._compute_volume_spike(symbol)
                features["volume_spike"] = str(volume_spike_phi)

                # Update range and compute volatility
                self._update_volatility_state(symbol, price, current_tick)
                volatility_state_phi = self._compute_volatility_state(symbol)
                features["volatility_state"] = str(volatility_state_phi)

                # Compute depth imbalance
                depth_imbalance_phi = self._compute_depth_imbalance(
                    bid_size, ask_size)
                features["depth_imbalance"] = str(depth_imbalance_phi)

                # Update macro_sync buffer and compute correlation
                self._update_macro_sync_buffer(
                    symbol, price, current_tick, time_diff)
                macro_sync_phi = self._compute_macro_sync(symbol)
                features["macro_sync"] = str(macro_sync_phi)

            features_payload = {
                "ts": current_tick["ts"],
                "symbol": symbol,
                "features": features,
            }

            self.logger.info(
                f"Calculated features for {symbol}: OBI={obi:.6f}, TFI={tfi:.6f}, "
                f"delta_price={delta_price}, ema_bias={features.get('ema_bias', 'N/A')}, "
                f"volume_spike={features.get('volume_spike', 'N/A')}")

            self.fsm.emit("EVT:FEATURES_CALCULATED",
                          payload=features_payload, why="features_calculated")

            # Store features
            if self.feature_store:
                try:
                    self.feature_store.store_features(features_payload)
                    try:
                        self.feature_store.aggregate_all_timeframes(symbol)
                    except Exception as agg_e:
                        self.logger.warning(
                            f"Failed to aggregate timeframes for {symbol}: {agg_e}")
                except Exception as e:
                    self.logger.error(f"Error storing features: {e}")

        except Exception as e:
            self.logger.error(f"Error calculating features for {symbol}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

    def start(self) -> None:
        """Start the feature engineering component."""
        self.logger.info("FeatureEngineering (Phase 1) started")

    def stop(self) -> None:
        """Stop the feature engineering component."""
        self.logger.info("FeatureEngineering stopped")
