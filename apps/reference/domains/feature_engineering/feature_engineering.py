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
from apps.reference.config_features import resolve_feature_engineering_config

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


class FeatureEngineering:
    def __init__(self, fsm: "FSMCore", config: dict[str, Any], feature_store: Optional[Any] = None) -> None:
        self.fsm = fsm
        self.raw_config = config
        self.feature_store = feature_store
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        self.last_tick_data: Dict[str, dict] = {}

        # Phase 1: State per symbol for new metrics
        self.symbol_state: Dict[str, Dict[str, Any]] = {}

        # ✅ REFACTORED: Use dual-mode resolver (v2 primary, legacy fallback)
        from apps.reference.config_loader import reload_config
        aurora_config = reload_config()
        self.config = resolve_feature_engineering_config(aurora_config)

        self.logger.info(
            "Resolved feature engineering config",
            extra={
                "source": self.config.source,
                "enable_new_metrics": self.config.enable_new_metrics,
                "ema_period_short": self.config.ema_period_short,
                "ema_period_long": self.config.ema_period_long,
                "macro_sync_enabled": self.config.macro_sync_enabled,
            },
        )

        # Extract frequently used values for convenience
        self.enable_new_metrics = self.config.enable_new_metrics
        self.macro_sync_enabled = self.config.macro_sync_enabled
        self.anchor_symbols = self.config.macro_sync_anchors
        self.macro_window = self.config.macro_sync_window

        # Anchor price buffers for macro_sync
        self.anchor_prices: Dict[str, deque] = {
            anchor: deque(maxlen=self.macro_window)
            for anchor in self.anchor_symbols
        }

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
        # ✅ REFACTORED: Direct access to config properties (no try-except needed)
        ema_short = self.config.ema_period_short
        ema_long = self.config.ema_period_long
        vol_sma_len = self.config.volume_sma_length
        vol_range_sma_len = self.config.volatility_sma_length

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
            # ✅ REFACTORED: Use config value instead of magic number 0.02
            bias_clamp = decimal.Decimal(str(self.config.ema_bias_clamp))
            bias_clamped = max(-bias_clamp, min(bias_clamp, bias))
            phi = (bias_clamped / bias_clamp + decimal.Decimal("1")) / \
                decimal.Decimal("2")
            return phi
        return decimal.Decimal("0.5")

    def _update_volume_spike(self, symbol: str, current_tick: dict, time_diff_ms: int) -> None:
        """Update volume window and compute spike (FIX #2: use real volumes, not tick count)."""
        state = self.symbol_state[symbol]
        # ts can be string or int - convert to int for arithmetic
        current_ts = int(current_tick["ts"]) if isinstance(current_tick["ts"], str) else current_tick["ts"]

        # ✅ REFACTORED: Direct config access
        window_sec = self.config.volume_window_sec
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
            # ✅ REFACTORED: Use config value instead of magic number 3.0
            spike_cap = decimal.Decimal(str(self.config.volume_spike_cap))
            spike_capped = min(spike, spike_cap)
            phi = spike_capped / spike_cap
            return phi
        return decimal.Decimal("0.5")

    def _update_volatility_state(self, symbol: str, price: decimal.Decimal, current_tick: dict) -> None:
        """Update volatility range window."""
        state = self.symbol_state[symbol]
        # ts can be string or int - convert to int for arithmetic
        current_ts = int(current_tick["ts"]) if isinstance(current_tick["ts"], str) else current_tick["ts"]

        # ✅ REFACTORED: Direct config access
        window_sec = self.config.volatility_window_sec
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
            # ✅ REFACTORED: Use config value instead of magic number 3.0
            ratio_cap = decimal.Decimal(str(self.config.volatility_ratio_cap))
            ratio_capped = min(ratio, ratio_cap)
            phi = ratio_capped / ratio_cap
            return phi
        return decimal.Decimal("0.5")

    def _compute_depth_imbalance(self, bid_size: decimal.Decimal, ask_size: decimal.Decimal) -> decimal.Decimal:
        """Compute depth imbalance from bid/ask sizes."""
        # ✅ REFACTORED: Direct config access
        depth_half = decimal.Decimal(str(self.config.liquidity_depth_half))

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

            # ts can be string or int - convert to int for arithmetic
            current_ts = int(current_tick["ts"]) if isinstance(current_tick["ts"], str) else current_tick["ts"]
            last_ts = int(last_tick["ts"]) if isinstance(last_tick["ts"], str) else last_tick["ts"]
            time_diff = current_ts - last_ts
            delta_price = price - \
                prev_price if time_diff < 5000 else decimal.Decimal(0)

            # Liquidity kappa
            # ✅ REFACTORED: Direct config access
            depth_half = decimal.Decimal(str(self.config.liquidity_depth_half))
            liq_ratio = (depth / (depth + depth_half)) if (depth +
                                                           depth_half) > 0 else decimal.Decimal("0")
            liq_ratio = max(decimal.Decimal("0"), min(
                decimal.Decimal("1"), liq_ratio))
            # ✅ REFACTORED: Use config values instead of magic numbers 0.3 and 1.0
            kappa_min = decimal.Decimal(str(self.config.liquidity_kappa_min))
            kappa_max = decimal.Decimal(str(self.config.liquidity_kappa_max))
            liq_kappa = max(kappa_min, min(kappa_max, liq_ratio))

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
