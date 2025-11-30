"""
Feature Calculation Engine - Pure Business Logic.

FTR-04: Extracted from feature_engineering.py for Separation of Concerns.

This module contains:
- FeatureCalculationEngine: All _update_* and _compute_* methods
- No FSM imports, no event handling
- Pure functions operating on HotState/ColdState via FeatureEngineeringConfig

Architecture:
- Input: HotState, ColdState, tick data, config
- Output: Decimal feature values
- No side effects beyond state mutation
"""

import decimal
import math
import statistics
from typing import Dict, Deque, Optional, Any, List
from collections import deque

from apps.reference.domains.feature_engineering.types import (
    HotState,
    ColdState,
    SymbolFeatureState,
    FeatureEngineeringConfig,
)
from apps.reference.domains.feature_engineering.utils import (
    FeatureUtils,
    WelfordAggregate,
)


class FeatureCalculationEngine:
    """
    Pure calculation engine for feature engineering.
    
    FTR-04: Extracted from FeatureEngineering for Separation of Concerns.
    Contains all _update_* and _compute_* methods.
    NO FSM, NO event handling - pure business logic only.
    """
    
    def __init__(self, cfg: FeatureEngineeringConfig):
        """
        Initialize with configuration.
        
        Args:
            cfg: FeatureEngineeringConfig instance
        """
        self.cfg = cfg
    
    # =========================================================================
    # EMA CALCULATIONS
    # =========================================================================
    
    def update_ema(self, state: HotState, price: decimal.Decimal) -> None:
        """Update EMA values for the symbol."""
        alpha_short = decimal.Decimal(str(state.ema_short_alpha))
        alpha_long = decimal.Decimal(str(state.ema_long_alpha))

        if state.ema_short is None:
            state.ema_short = price
            state.ema_long = price
        else:
            state.ema_short = price * alpha_short + state.ema_short * (1 - alpha_short)
            state.ema_long = price * alpha_long + state.ema_long * (1 - alpha_long)

    def compute_ema_bias(self, state: HotState) -> decimal.Decimal:
        """Compute EMA bias = (EMA_short - EMA_long) / EMA_long, normalized to [0,1]."""
        ema_long = state.ema_long
        
        if ema_long and ema_long > 0:
            bias = (state.ema_short - ema_long) / ema_long
            # Clamp to configured range
            bias_clamped = max(self.cfg.ema_bias_clamp_min, 
                              min(self.cfg.ema_bias_clamp_max, bias))
            # Normalize to [0, 1]
            clamp_range = self.cfg.ema_bias_clamp_max - self.cfg.ema_bias_clamp_min
            phi = (bias_clamped - self.cfg.ema_bias_clamp_min) / clamp_range
            return phi
        return self.cfg.neutral_value

    # =========================================================================
    # VOLUME SPIKE CALCULATIONS (FTR-03: O(1) Welford)
    # =========================================================================

    def update_volume_spike(self, state: HotState, current_tick: dict) -> None:
        """
        Update volume window with real volumes.
        
        FTR-03: O(1) implementation using Welford's Algorithm.
        The deque stores values for FIFO removal, Welford stats for O(1) mean.
        """
        current_ts = current_tick["ts"]
        window_ms = self.cfg.volume_window_ms

        # Initialize or reset window
        if state.vol_window_start_ts is None:
            state.vol_window_start_ts = current_ts
            state.vol_current_ts = current_ts

        # Check if time to close window
        if current_ts - state.vol_window_start_ts >= window_ms:
            if state.vol_window_trades > 0:
                new_val = state.vol_window_trades
                
                # FTR-03: O(1) sliding window with Welford
                # Remove oldest if window full BEFORE append
                maxlen = state.vol_hist.maxlen or self.cfg.volume_sma_length
                if len(state.vol_hist) >= maxlen:
                    old_val = state.vol_hist[0]
                    state.vol_stats = FeatureUtils.welford_remove_tuple(state.vol_stats, old_val)
                
                # Append new value (deque auto-pops if maxlen set)
                state.vol_hist.append(new_val)
                
                # Update Welford stats
                state.vol_stats = FeatureUtils.welford_update(state.vol_stats, new_val)
                
            state.vol_window_start_ts = current_ts
            state.vol_window_trades = 0.0

        # Accumulate REAL volume (not tick count)
        buy_vol = float(current_tick.get("buy_volume", 0))
        sell_vol = float(current_tick.get("sell_volume", 0))
        state.vol_window_trades += buy_vol + sell_vol
        state.vol_current_ts = current_ts

    def compute_volume_spike(self, state: HotState) -> decimal.Decimal:
        """
        Compute volume spike = vol_window / mean(vol), normalized to [0,1].
        
        FTR-03: O(1) implementation - uses Welford mean instead of sum()/len().
        """
        count, mean, _ = state.vol_stats
        
        if count < 2:
            return self.cfg.neutral_value

        # O(1) mean access from Welford stats
        avg_vol = decimal.Decimal(str(mean))
        current_vol = decimal.Decimal(str(state.vol_window_trades))

        if avg_vol > 0:
            spike = current_vol / avg_vol
            spike_capped = min(spike, self.cfg.volume_spike_cap)
            phi = spike_capped / self.cfg.volume_spike_cap
            return phi
        return self.cfg.neutral_value
    
    def compute_volume_zscore(self, state: HotState) -> decimal.Decimal:
        """
        Compute volume Z-score = (current_vol - mean) / stddev, normalized via tanh.
        
        FTR-03: V2 feature - Z-score with tanh normalization to [0, 1].
        """
        count, mean, m2 = state.vol_stats
        
        if count < 2:
            return self.cfg.neutral_value
        
        current_vol = state.vol_window_trades
        z_score = FeatureUtils.compute_z_score(current_vol, state.vol_stats, clip_sigma=5.0)
        
        # Normalize to [0, 1] using tanh: phi = (tanh(z) + 1) / 2
        phi = (math.tanh(z_score) + 1.0) / 2.0
        return decimal.Decimal(str(round(phi, 8)))

    # =========================================================================
    # VOLATILITY STATE CALCULATIONS (FTR-03: O(1) Welford)
    # =========================================================================

    def update_volatility_state(self, state: HotState, price: decimal.Decimal, current_tick: dict) -> None:
        """
        Update volatility range window.
        
        FTR-03: O(1) implementation using Welford's Algorithm.
        """
        current_ts = current_tick["ts"]
        window_ms = self.cfg.volatility_window_ms

        # Initialize window
        if state.range_window_start_ts is None:
            state.range_window_start_ts = current_ts
            state.range_min = price
            state.range_max = price

        # Check if time to close window
        if current_ts - state.range_window_start_ts >= window_ms:
            if state.range_min is not None and state.range_max is not None:
                range_val = float(state.range_max - state.range_min)  # Convert to float for Welford
                
                # FTR-03: O(1) sliding window with Welford
                maxlen = state.range_hist.maxlen or self.cfg.volatility_sma_length
                if len(state.range_hist) >= maxlen:
                    old_val = state.range_hist[0]
                    state.range_stats = FeatureUtils.welford_remove_tuple(state.range_stats, old_val)
                
                state.range_hist.append(range_val)
                state.range_stats = FeatureUtils.welford_update(state.range_stats, range_val)
                
            state.range_window_start_ts = current_ts
            state.range_min = price
            state.range_max = price

        # Update min/max
        state.range_min = min(state.range_min, price)
        state.range_max = max(state.range_max, price)

    def compute_volatility_state(self, state: HotState) -> decimal.Decimal:
        """
        Compute volatility state = range / mean(range), normalized to [0,1].
        
        FTR-03: O(1) implementation - uses Welford mean instead of sum()/len().
        """
        count, mean, _ = state.range_stats
        
        if count < 2:
            return self.cfg.neutral_value

        # O(1) mean access from Welford stats
        avg_range = decimal.Decimal(str(mean))
        current_range = (
            state.range_max - state.range_min
            if state.range_max and state.range_min
            else decimal.Decimal("0")
        )

        if avg_range > 0:
            ratio = current_range / avg_range
            ratio_capped = min(ratio, self.cfg.volatility_state_cap)
            phi = ratio_capped / self.cfg.volatility_state_cap
            return phi
        return self.cfg.neutral_value

    # =========================================================================
    # V2 FEATURES (FTR-03)
    # =========================================================================
    
    def compute_spread_bps(
        self, 
        best_bid: decimal.Decimal, 
        best_ask: decimal.Decimal,
        mid_price: decimal.Decimal,
    ) -> decimal.Decimal:
        """
        Compute bid-ask spread in basis points.
        
        FTR-03: V2 feature.
        spread_bps = (ask - bid) / mid_price * 10000
        
        Returns:
            Spread in basis points (bps). 100 bps = 1%.
            Returns 0 if prices invalid.
        """
        if mid_price <= 0:
            return decimal.Decimal("0")
        
        spread = best_ask - best_bid
        if spread < 0:
            return decimal.Decimal("0")
        
        spread_bps = (spread / mid_price) * decimal.Decimal("10000")
        return spread_bps.quantize(decimal.Decimal("0.01"))
    
    def compute_large_trade_imbalance(
        self,
        current_tick: dict,
    ) -> decimal.Decimal:
        """
        Compute large trade imbalance from buy/sell trade counts.
        
        FTR-03: V2 feature.
        Uses average trade size to detect institutional flow.
        
        Formula:
            avg_buy = buy_volume / buy_count
            avg_sell = sell_volume / sell_count
            imbalance = (avg_buy - avg_sell) / max(avg_buy, avg_sell)
            
        Returns:
            Normalized imbalance in [-1, 1]. >0 = larger buys, <0 = larger sells.
            Returns 0 if counts not available.
        """
        # Extract trade counts (optional fields)
        buy_count = float(current_tick.get("buy_count", 0))
        sell_count = float(current_tick.get("sell_count", 0))
        buy_volume = float(current_tick.get("buy_volume", 0))
        sell_volume = float(current_tick.get("sell_volume", 0))
        
        # Need both counts to compute
        if buy_count <= 0 or sell_count <= 0:
            return self.cfg.neutral_value  # Return 0.5 when data unavailable
        
        avg_buy = buy_volume / buy_count
        avg_sell = sell_volume / sell_count
        
        max_avg = max(avg_buy, avg_sell)
        if max_avg <= 0:
            return self.cfg.neutral_value
        
        # Raw imbalance: [-1, 1]
        imbalance = (avg_buy - avg_sell) / max_avg
        
        # Normalize to [0, 1]: phi = (imbalance + 1) / 2
        phi = (decimal.Decimal(str(imbalance)) + decimal.Decimal("1")) / decimal.Decimal("2")
        return phi

    # =========================================================================
    # DEPTH IMBALANCE
    # =========================================================================

    def compute_depth_imbalance(self, bid_size: decimal.Decimal, ask_size: decimal.Decimal) -> decimal.Decimal:
        """Compute depth imbalance with Laplace smoothing, normalized to [0,1]."""
        depth_half = self.cfg.depth_half
        denominator = bid_size + depth_half
        numerator = ask_size + depth_half

        if denominator > 0:
            ratio = numerator / denominator
            imbalance = (ratio - decimal.Decimal("1")) / (ratio + decimal.Decimal("1"))
            phi = (imbalance + decimal.Decimal("1")) / decimal.Decimal("2")
            return phi
        return self.cfg.neutral_value

    # =========================================================================
    # MACRO SYNC (Correlation with anchors)
    # =========================================================================

    def update_macro_sync_buffer(
        self, 
        state: HotState, 
        price: decimal.Decimal, 
        time_diff_ms: int
    ) -> None:
        """Update return for macro_sync correlation."""
        if (state.prev_price and 
            state.prev_price > 0 and 
            time_diff_ms < self.cfg.delta_price_spike_filter_ms):
            ret = (price - state.prev_price) / state.prev_price
            state.returns_buffer.append(float(ret))

        state.prev_price = price

    def compute_macro_sync(
        self, 
        state: HotState,
        anchor_prices: Dict[str, Deque],
    ) -> decimal.Decimal:
        """Compute macro_sync = correlation with anchor returns, normalized to [0,1]."""
        if not self.cfg.macro_sync_enabled or not self.cfg.macro_sync_anchors:
            return self.cfg.neutral_value

        if len(state.returns_buffer) < self.cfg.macro_sync_min_buffer:
            return self.cfg.neutral_value

        correlations = []
        for anchor in self.cfg.macro_sync_anchors:
            if anchor not in anchor_prices or len(anchor_prices[anchor]) < 3:
                continue

            # Compute anchor returns
            anchor_returns = []
            anchor_prices_list = list(anchor_prices[anchor])
            for i in range(1, len(anchor_prices_list)):
                if anchor_prices_list[i-1] > 0:
                    ret = (anchor_prices_list[i] - anchor_prices_list[i-1]) / anchor_prices_list[i-1]
                    anchor_returns.append(float(ret))

            # Compute Pearson correlation
            if len(anchor_returns) == len(state.returns_buffer):
                try:
                    corr = self._pearson_correlation(list(state.returns_buffer), anchor_returns)
                    correlations.append(corr)
                except Exception:
                    pass  # Skip on error

        if correlations:
            avg_corr = statistics.mean(correlations)
            # Map from [-1, 1] to [0, 1]
            phi = (decimal.Decimal(str(avg_corr)) + decimal.Decimal("1")) / decimal.Decimal("2")
            return phi

        return self.cfg.neutral_value

    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> float:
        """Compute Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        mean_x = sum(x) / len(x)
        mean_y = sum(y) / len(y)

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(len(x)))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(len(y)))
        denominator = (sum_sq_x ** 0.5) * (sum_sq_y ** 0.5)

        if denominator > 0:
            return numerator / denominator
        return 0.0

    # =========================================================================
    # FUTURES FEATURES (FTR-05)
    # =========================================================================

    def update_funding(self, state: ColdState, funding_rate: decimal.Decimal, next_funding_ts: int = 0) -> None:
        """
        Update funding rate in ColdState.
        
        FTR-05: O(1) update - just store the value.
        
        Args:
            state: ColdState to update
            funding_rate: Current funding rate (e.g., 0.0001 = 0.01%)
            next_funding_ts: Next funding timestamp in ms (optional)
        """
        state.funding_rate = funding_rate
        if next_funding_ts > 0:
            state.next_funding_ts = next_funding_ts

    def update_open_interest(self, state: ColdState, open_interest: decimal.Decimal, ts: int = 0) -> None:
        """
        Update Open Interest in ColdState with history for delta calculation.
        
        FTR-05: O(1) update - shift current to prev, store new value.
        
        Args:
            state: ColdState to update
            open_interest: Current open interest value
            ts: Update timestamp in ms
        """
        # Shift current to prev for delta calculation
        state.prev_open_interest = state.open_interest
        state.open_interest = open_interest
        state.last_oi_update_ts = ts

    def compute_funding_normalized(self, state: ColdState) -> Optional[decimal.Decimal]:
        """
        Compute funding rate normalized to [-1, 1].
        
        FTR-05: Uses extreme_threshold from config.
        Formula: clamp(funding_rate / threshold, -1, 1)
        
        Args:
            state: ColdState with funding_rate
            
        Returns:
            Normalized funding in [-1, 1], or None if no funding data
        """
        funding = state.funding_rate
        
        # No funding data yet
        if funding == decimal.Decimal("0"):
            return None
        
        threshold = self.cfg.funding_extreme_threshold
        if threshold <= 0:
            threshold = decimal.Decimal("0.001")
        
        # Normalize: funding / threshold, clamped to [-1, 1]
        normalized = funding / threshold
        clamped = max(decimal.Decimal("-1"), min(decimal.Decimal("1"), normalized))
        
        return clamped.quantize(decimal.Decimal("0.0001"))

    def compute_oi_delta_pct(self, state: ColdState) -> Optional[decimal.Decimal]:
        """
        Compute Open Interest delta as percentage change.
        
        FTR-05: Formula: (curr - prev) / prev * 100
        
        Args:
            state: ColdState with open_interest and prev_open_interest
            
        Returns:
            Percentage change, or None if no prev data
        """
        curr = state.open_interest
        prev = state.prev_open_interest
        
        # No previous data - can't compute delta
        if prev is None or prev <= 0:
            return None
        
        # Compute percentage change
        delta_pct = ((curr - prev) / prev) * decimal.Decimal("100")
        
        return delta_pct.quantize(decimal.Decimal("0.01"))
