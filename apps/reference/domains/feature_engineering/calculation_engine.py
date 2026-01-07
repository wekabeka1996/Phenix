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
from apps.reference.domains.feature_engineering.macro_sync_resampler import MacroSyncResampler
from typing import Dict, Deque, Optional, Any, List
from collections import deque

from apps.reference.domains.feature_engineering.large_trade_imbalance import (
    LargeTradeImbalanceCalculator,
)

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
        self._large_trade_imbalance: Optional[LargeTradeImbalanceCalculator] = None
        # P0-2: Book health tracking per symbol
        self._book_last_update_ts_ms: Dict[str, int] = {}
        self._book_update_count: Dict[str, int] = {}
        self._trade_count_in_window: Dict[str, int] = {}
        self._book_window_start_ts_ms: Dict[str, int] = {}

    # =========================================================================
    # P0-3: FEATURE SANITY FIREWALL (Central NaN/Inf/Bounds Protection)
    # =========================================================================
    
    def sanitize_feature(
        self, 
        feature_name: str, 
        raw_value: Any,
    ) -> tuple[decimal.Decimal, bool, Optional[str]]:
        """
        P0-3: Central feature sanity firewall.
        
        Checks for NaN/Inf/out-of-range and returns sanitized value.
        
        Returns:
            (value, is_ready, not_ready_reason)
            - value: Decimal value (neutral if invalid)
            - is_ready: True if value passed sanity, False if failed
            - not_ready_reason: None if ready, else reason string
        """
        if not self.cfg.feature_sanity_enabled:
            # Firewall disabled - pass through (backward compat)
            try:
                return (decimal.Decimal(str(raw_value)), True, None)
            except (ValueError, TypeError):
                return (self.cfg.neutral_value, False, "invalid_value_type")
        
        # Convert to float for NaN/Inf check
        try:
            val_float = float(raw_value)
        except (ValueError, TypeError):
            return (self.cfg.neutral_value, False, "invalid_value_type")
        
        # P0-3 STEP 1: NaN/Inf check
        if not math.isfinite(val_float):
            behavior = self.cfg.feature_sanity_nan_inf_behavior
            if behavior == "crash":
                raise ValueError(f"P0-3 SANITY FAIL: {feature_name}={raw_value} is NaN/Inf (crash mode)")
            # "neutral_and_not_ready" or "neutral_only"
            not_ready = behavior == "neutral_and_not_ready"
            return (
                self.cfg.neutral_value, 
                not not_ready,  # is_ready = False if not_ready
                f"nan_inf:{feature_name}" if not_ready else None
            )
        
        # P0-3 STEP 2: Bounds check (if configured)
        bounds = self.cfg.feature_sanity_bounds.get(feature_name)
        if bounds:
            min_val = float(bounds["min"])
            max_val = float(bounds["max"])
            if val_float < min_val or val_float > max_val:
                # Out of range - clamp and mark not_ready
                clamped = max(min_val, min(max_val, val_float))
                return (
                    decimal.Decimal(str(clamped)),
                    False,
                    f"out_of_range:{feature_name}:{val_float:.4f}"
                )
        
        # Value passed all checks
        return (decimal.Decimal(str(raw_value)), True, None)

    def sanitize_features_dict(
        self, 
        features: Dict[str, str],
    ) -> tuple[Dict[str, str], Dict[str, bool], List[str]]:
        """
        P0-3: Batch sanitize all features in dict.
        
        Returns:
            (sanitized_features, readiness_map_updates, reasons)
        """
        sanitized = {}
        readiness_updates = {}
        reasons = []
        
        for fname, fval_str in features.items():
            val, is_ready, reason = self.sanitize_feature(fname, fval_str)
            sanitized[fname] = str(val)
            readiness_updates[fname] = is_ready
            if reason:
                reasons.append(reason)
        
        return sanitized, readiness_updates, reasons

    # =========================================================================
    # P0-2: BOOK HEALTH GATE (Spread Truth Validation)
    # =========================================================================
    
    def update_book_health(
        self, 
        symbol: str, 
        ts_ms: int, 
        is_book_update: bool = False,
        is_trade: bool = False,
    ) -> None:
        """
        P0-2: Track book updates and trades for health assessment.
        
        Call this on every tick with appropriate flags.
        """
        if not self.cfg.spread_health_gate_enabled:
            return
        
        window_ms = int(self.cfg.spread_health_window_sec * 1000)
        
        # Reset window if expired
        window_start = self._book_window_start_ts_ms.get(symbol, 0)
        if ts_ms - window_start > window_ms:
            self._book_window_start_ts_ms[symbol] = ts_ms
            self._book_update_count[symbol] = 0
            self._trade_count_in_window[symbol] = 0
        
        # Track last update ts
        if is_book_update:
            self._book_last_update_ts_ms[symbol] = ts_ms
            self._book_update_count[symbol] = self._book_update_count.get(symbol, 0) + 1
        
        if is_trade:
            self._trade_count_in_window[symbol] = self._trade_count_in_window.get(symbol, 0) + 1

    def check_book_health(
        self, 
        symbol: str, 
        current_ts_ms: int,
    ) -> tuple[bool, Optional[str]]:
        """
        P0-2: Check if order book feed is healthy.
        
        3-step matrix:
        1. STEP 1: book_age < max_age_sec (hard fail if older)
        2. STEP 2: update_events >= min_update_events OR trades >= min_trades_count
        
        Returns:
            (is_healthy, not_healthy_reason)
        """
        if not self.cfg.spread_health_gate_enabled:
            return (True, None)  # Gate disabled
        
        # STEP 1: Book age check
        last_update_ts = self._book_last_update_ts_ms.get(symbol, 0)
        if last_update_ts == 0:
            # No book updates received yet
            return (False, "no_book_updates_received")
        
        max_age_ms = int(self.cfg.spread_health_max_age_sec * 1000)
        age_ms = current_ts_ms - last_update_ts
        
        if age_ms > max_age_ms:
            return (False, f"book_stale:age_ms={age_ms}")
        
        # STEP 2: Activity check (update_events OR trades)
        update_count = self._book_update_count.get(symbol, 0)
        trade_count = self._trade_count_in_window.get(symbol, 0)
        
        min_updates = self.cfg.spread_health_min_update_events
        min_trades = self.cfg.spread_health_min_trades_count
        
        # OR logic: either condition sufficient
        if update_count >= min_updates or trade_count >= min_trades:
            return (True, None)
        
        return (False, f"insufficient_activity:updates={update_count},trades={trade_count}")

    def _get_large_trade_imbalance(self) -> LargeTradeImbalanceCalculator:
        if self._large_trade_imbalance is None:
            self._large_trade_imbalance = LargeTradeImbalanceCalculator(
                window_ms=int(self.cfg.large_trade_imbalance_window_ms),
                min_trades=int(self.cfg.large_trade_imbalance_min_trades),
                eps=self.cfg.large_trade_imbalance_eps,
                neutral_value=self.cfg.neutral_value,
                use_notional=bool(self.cfg.large_trade_imbalance_use_notional),
            )
        return self._large_trade_imbalance
    
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
    # R1 (P1): MACRO RESID — Beta-Adjusted Residual
    # =========================================================================
    
    def update_macro_resid(
        self,
        state: HotState,
        asset_return: float,
        anchor_return: float,
    ) -> None:
        """
        R1: Update macro_resid buffers.
        
        Args:
            state: HotState for the symbol
            asset_return: Return of the asset (fraction)
            anchor_return: Return of the anchor (BTC) (fraction)
        """
        if not self.cfg.macro_resid_enabled:
            return
        
        beta_window = self.cfg.macro_resid_beta_window
        
        # Append to buffers
        state.macro_resid_asset_returns.append(asset_return)
        state.macro_resid_anchor_returns.append(anchor_return)
        
        # Trim to window size
        while len(state.macro_resid_asset_returns) > beta_window:
            state.macro_resid_asset_returns.popleft()
        while len(state.macro_resid_anchor_returns) > beta_window:
            state.macro_resid_anchor_returns.popleft()
    
    def compute_macro_resid(self, state: HotState) -> tuple[decimal.Decimal, bool, Optional[str]]:
        """
        R1: Compute macro_resid = clip(resid / scale, -clip, +clip).
        
        Formula:
            beta = cov(r_asset, r_btc) / var(r_btc)
            resid = r_asset[-1] - beta * r_btc[-1]
            scale = MAD(resid_buffer)
            macro_resid = clip(resid / max(scale, scale_floor), -clip, +clip)
        
        Returns:
            (value, is_ready, not_ready_reason)
        """
        neutral = decimal.Decimal(str(self.cfg.macro_resid_neutral))
        
        if not self.cfg.macro_resid_enabled:
            return (neutral, True, None)  # Feature disabled = always ready with neutral
        
        asset_rets = list(state.macro_resid_asset_returns)
        anchor_rets = list(state.macro_resid_anchor_returns)
        beta_window = self.cfg.macro_resid_beta_window
        mad_window = self.cfg.macro_resid_mad_window
        
        # Check minimum buffer size
        if len(asset_rets) < beta_window or len(anchor_rets) < beta_window:
            state.macro_resid_ready = False
            state.macro_resid_not_ready_reason = f"insufficient_samples:{len(asset_rets)}<{beta_window}"
            return (neutral, False, state.macro_resid_not_ready_reason)
        
        # Winsorize extremes
        winsor_p = self.cfg.macro_resid_winsor_percentile
        if winsor_p > 0:
            asset_rets = self._winsorize(asset_rets, winsor_p)
            anchor_rets = self._winsorize(anchor_rets, winsor_p)
        
        # Calculate beta = cov(asset, anchor) / (var(anchor) + var_floor)
        #
        # REGULARIZED BETA: Instead of if/else fallback, we use Tikhonov regularization.
        # When var(anchor) → 0 (anchor ticks slower than asset), beta → 0 gracefully.
        # This avoids early-return deadlock and provides mathematically sound degradation:
        #   - If var_anchor >> var_floor: beta ≈ cov/var_anchor (normal OLS)
        #   - If var_anchor ≈ 0: beta ≈ 0 (anchor provides no info, use asset return only)
        #
        # This is preferable to if/else because:
        #   1. No discontinuity at var_floor threshold
        #   2. Always produces a valid beta (no early return)
        #   3. Warmup completes normally, macro_resid always has a value
        var_anchor = self._variance(anchor_rets)
        var_floor = float(self.cfg.macro_resid_var_floor)
        cov = self._covariance(asset_rets, anchor_rets)
        
        # Regularized OLS: beta = cov / (var + λ) where λ = var_floor
        beta = cov / (var_anchor + var_floor)
        
        # Calculate residual for latest observation
        latest_asset_ret = asset_rets[-1]
        latest_anchor_ret = anchor_rets[-1]
        resid = latest_asset_ret - beta * latest_anchor_ret
        
        # Update residual buffer for MAD
        state.macro_resid_buffer.append(resid)
        while len(state.macro_resid_buffer) > mad_window:
            state.macro_resid_buffer.popleft()
        
        # Check MAD buffer readiness
        if len(state.macro_resid_buffer) < mad_window:
            state.macro_resid_ready = False
            state.macro_resid_not_ready_reason = f"mad_warmup:{len(state.macro_resid_buffer)}<{mad_window}"
            return (neutral, False, state.macro_resid_not_ready_reason)
        
        # Calculate MAD scale
        scale = self._mad(list(state.macro_resid_buffer))
        scale_floor = self.cfg.macro_resid_scale_floor
        scale = max(scale, scale_floor)
        
        # Normalize and clip
        clip_bound = self.cfg.macro_resid_clip
        normalized = resid / scale
        clipped = max(-clip_bound, min(clip_bound, normalized))
        
        state.macro_resid_ready = True
        state.macro_resid_not_ready_reason = None
        
        return (decimal.Decimal(str(clipped)), True, None)
    
    def _winsorize(self, data: List[float], percentile: float) -> List[float]:
        """Winsorize data at given percentile."""
        if not data or percentile <= 0:
            return data
        sorted_data = sorted(data)
        n = len(sorted_data)
        lo_idx = int(n * percentile)
        hi_idx = int(n * (1 - percentile))
        lo_val = sorted_data[lo_idx] if lo_idx < n else sorted_data[0]
        hi_val = sorted_data[hi_idx] if hi_idx < n else sorted_data[-1]
        return [max(lo_val, min(hi_val, x)) for x in data]
    
    def _variance(self, data: List[float]) -> float:
        """Calculate variance of data."""
        if len(data) < 2:
            return 0.0
        mean = sum(data) / len(data)
        return sum((x - mean) ** 2 for x in data) / len(data)
    
    def _covariance(self, x: List[float], y: List[float]) -> float:
        """Calculate covariance of x and y."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        mean_x = sum(x[:n]) / n
        mean_y = sum(y[:n]) / n
        return sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    
    def _mad(self, data: List[float]) -> float:
        """Calculate Median Absolute Deviation."""
        if not data:
            return 0.0
        median = statistics.median(data)
        return statistics.median([abs(x - median) for x in data])
    
    # =========================================================================
    # R2 (P2): ABSORPTION — Experimental (Default OFF)
    # =========================================================================
    
    def update_absorption(
        self,
        state: HotState,
        buy_vol: float,
        sell_vol: float,
        tfi: float,
    ) -> None:
        """
        R2: Update absorption buffers.
        
        Args:
            state: HotState for the symbol
            buy_vol: Aggressive buy volume
            sell_vol: Aggressive sell volume
            tfi: Trade Flow Imbalance for dedup correlation
        """
        if self.cfg.absorption_mode == "disabled":
            return
        
        window = self.cfg.absorption_proxy_window
        
        # Update volume buffers
        state.absorption_buy_vol_buffer.append(buy_vol)
        state.absorption_sell_vol_buffer.append(sell_vol)
        
        # Trim
        while len(state.absorption_buy_vol_buffer) > window:
            state.absorption_buy_vol_buffer.popleft()
        while len(state.absorption_sell_vol_buffer) > window:
            state.absorption_sell_vol_buffer.popleft()
        
        # Dedup: track TFI and proxy for correlation
        if self.cfg.absorption_dedup_enabled:
            dedup_window = self.cfg.absorption_dedup_window
            state.absorption_tfi_buffer.append(tfi)
            while len(state.absorption_tfi_buffer) > dedup_window:
                state.absorption_tfi_buffer.popleft()
    
    def compute_absorption(self, state: HotState) -> tuple[decimal.Decimal, bool, Optional[str]]:
        """
        R2: Compute absorption proxy.
        
        Formula (proxy mode):
            absorption = (sum_buy_vol - sum_sell_vol) / (sum_buy_vol + sum_sell_vol + eps)
        
        Dedup guard: mute if |corr(absorption_buffer, TFI_buffer)| > threshold
        
        Returns:
            (value, is_ready, not_ready_reason)
        """
        neutral = decimal.Decimal(str(self.cfg.absorption_neutral))
        
        if self.cfg.absorption_mode == "disabled":
            # Feature disabled = not_ready (telemetry only, excluded from scoring)
            state.absorption_ready = False
            state.absorption_not_ready_reason = "mode_disabled"
            return (neutral, False, "mode_disabled")
        
        buy_vols = list(state.absorption_buy_vol_buffer)
        sell_vols = list(state.absorption_sell_vol_buffer)
        window = self.cfg.absorption_proxy_window
        eps = self.cfg.absorption_proxy_eps
        
        # Check buffer size
        if len(buy_vols) < window or len(sell_vols) < window:
            state.absorption_ready = False
            state.absorption_not_ready_reason = f"insufficient_samples:{len(buy_vols)}<{window}"
            return (neutral, False, state.absorption_not_ready_reason)
        
        # Calculate proxy: (buy - sell) / (buy + sell + eps)
        sum_buy = sum(buy_vols)
        sum_sell = sum(sell_vols)
        denominator = sum_buy + sum_sell + eps
        
        if denominator <= eps:
            state.absorption_ready = False
            state.absorption_not_ready_reason = "zero_volume"
            return (neutral, False, "zero_volume")
        
        proxy_value = (sum_buy - sum_sell) / denominator
        
        # Update proxy buffer for dedup correlation
        state.absorption_proxy_buffer.append(proxy_value)
        while len(state.absorption_proxy_buffer) > self.cfg.absorption_dedup_window:
            state.absorption_proxy_buffer.popleft()
        
        # Dedup check
        if self.cfg.absorption_dedup_enabled:
            tfi_vals = list(state.absorption_tfi_buffer)
            proxy_vals = list(state.absorption_proxy_buffer)
            
            if len(tfi_vals) >= 10 and len(proxy_vals) >= 10:
                # Calculate correlation
                corr = self._pearson_corr(proxy_vals[-10:], tfi_vals[-10:])
                state.absorption_dedup_corr = corr
                
                threshold = self.cfg.absorption_dedup_threshold
                if abs(corr) > threshold:
                    # MUTED: absorption too correlated with TFI
                    state.absorption_dedup_muted = True
                    state.absorption_ready = False
                    state.absorption_not_ready_reason = f"dedup_muted:corr={corr:.3f}>{threshold}"
                    return (neutral, False, state.absorption_not_ready_reason)
                else:
                    state.absorption_dedup_muted = False
        
        # Clip output
        clip_bound = self.cfg.absorption_clip
        clipped = max(-clip_bound, min(clip_bound, proxy_value))
        
        state.absorption_ready = True
        state.absorption_not_ready_reason = None
        
        return (decimal.Decimal(str(clipped)), True, None)
    
    def _pearson_corr(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        mean_x = sum(x[:n]) / n
        mean_y = sum(y[:n]) / n
        
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        var_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        var_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denom = math.sqrt(var_x * var_y)
        if denom < 1e-15:
            return 0.0
        return cov / denom

    # =========================================================================
    # VOLUME SPIKE CALCULATIONS (FTR-03: O(1) Welford)
    # =========================================================================

    def update_volume_spike(
        self,
        state: HotState,
        *,
        volume: decimal.Decimal,
        time_diff_ms: int,
    ) -> None:
        """
        TASK24.C2: Update time-normalized volume rate samples (Decimal-only for spike).

        Uses `time_diff_ms` to compute an instantaneous rate:
          rate_t = volume / dt_sec

        Notes:
        - For Z-score (v2), we also keep Welford stats in float space (rate-based).
        - If dt<=0, caller should record data-quality metrics; we only mark NOT_READY here.
        """
        state.volume_spike_ready = False
        state.volume_spike_not_ready_reason = None

        if time_diff_ms <= 0:
            state.volume_spike_not_ready_reason = "bad_dt"
            return

        ms_per_sec = decimal.Decimal(str(self.cfg.ms_per_sec))
        dt_sec = decimal.Decimal(int(time_diff_ms)) / ms_per_sec
        if dt_sec <= 0:
            state.volume_spike_not_ready_reason = "bad_dt"
            return

        if volume < 0:
            state.volume_spike_not_ready_reason = "negative_volume"
            return

        rate = volume / dt_sec
        state.volume_rate_current = rate

        # Maintain Decimal SMA window
        state.volume_rate_hist.append(rate)

        # Maintain float Welford window for volume_zscore (rate-based)
        rate_f = float(rate)
        maxlen = state.vol_hist.maxlen or self.cfg.volume_sma_length
        if len(state.vol_hist) >= maxlen:
            old_val = state.vol_hist[0]
            state.vol_stats = FeatureUtils.welford_remove_tuple(state.vol_stats, old_val)
        state.vol_hist.append(rate_f)
        state.vol_stats = FeatureUtils.welford_update(state.vol_stats, rate_f)
        state.vol_window_trades = rate_f

    def compute_volume_spike(self, state: HotState) -> decimal.Decimal:
        """
        TASK24.C2: Compute time-normalized volume_spike from rate samples, normalized to [0,1].

        spike = current_rate / max(avg_rate, eps)
        phi = min(spike, cap_max) / cap_max
        """
        state.volume_spike_ready = False
        state.volume_spike_not_ready_reason = None

        current_rate = state.volume_rate_current
        if current_rate is None:
            state.volume_spike_not_ready_reason = "missing_rate"
            return self.cfg.neutral_value

        if len(state.volume_rate_hist) < 2:
            state.volume_spike_not_ready_reason = "insufficient_samples"
            return self.cfg.neutral_value

        avg_rate = sum(state.volume_rate_hist) / decimal.Decimal(len(state.volume_rate_hist))
        if avg_rate <= 0:
            state.volume_spike_not_ready_reason = "avg_rate_non_positive"
            return self.cfg.neutral_value

        denom = max(avg_rate, self.cfg.volume_spike_eps)
        spike = current_rate / denom
        spike_capped = min(spike, self.cfg.volume_spike_cap)
        phi = spike_capped / self.cfg.volume_spike_cap

        state.volume_spike_ready = True
        return phi
    
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
        
        P2-3 FIX: Expects ts in milliseconds (ts_ms convention).
        """
        if price is None or price <= 0:
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "bad_price"
            return

        # P2-3 FIX: Explicitly handle ts as milliseconds
        current_ts = current_tick.get("ts", 0)
        if current_ts <= 0:
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "bad_ts"
            return
        
        # Ensure ts is in ms (if looks like seconds, convert)
        # Heuristic: timestamps before year 2000 in ms would be < 946684800000
        # Timestamps in seconds would be around 1.7B (2023)
        if current_ts < 1_000_000_000_000:  # Likely seconds, not ms
            current_ts = current_ts * 1000
        
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
        P0-1: Hard floor to prevent division by zero / overflow (config-driven).
        """
        count, mean, _ = state.range_stats
        
        if count < 2:
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "insufficient_history"
            return self.cfg.neutral_value

        # O(1) mean access from Welford stats
        avg_range = decimal.Decimal(str(mean))
        if state.range_max is None or state.range_min is None:
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "missing_range"
            return self.cfg.neutral_value

        current_range = state.range_max - state.range_min
        if current_range < 0:
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "negative_range"
            return self.cfg.neutral_value

        # P0-1: Hard floor to prevent division by zero / overflow
        # All parameters from config - NO HARDCODED VALUES
        tick_floor = decimal.Decimal(str(self.cfg.volatility_tick_floor))
        division_eps = decimal.Decimal(str(self.cfg.volatility_division_eps))
        
        # Denominator with hard floor (config-driven)
        denom = max(avg_range, tick_floor, division_eps)
        
        ratio = current_range / denom
        
        # P0-1: NaN/Inf firewall (fail-closed)
        try:
            ratio_float = float(ratio)
            if not math.isfinite(ratio_float):
                state.volatility_state_ready = False
                state.volatility_state_not_ready_reason = "overflow_nan_inf"
                return self.cfg.neutral_value
        except (OverflowError, ValueError):
            state.volatility_state_ready = False
            state.volatility_state_not_ready_reason = "overflow_conversion"
            return self.cfg.neutral_value
        
        ratio_capped = min(ratio, self.cfg.volatility_state_cap)
        phi = ratio_capped / self.cfg.volatility_state_cap
        
        # Final sanity check on phi
        phi_clamped = max(decimal.Decimal("0"), min(decimal.Decimal("1"), phi))
        
        state.volatility_state_ready = True
        state.volatility_state_not_ready_reason = None
        return phi_clamped

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
        state: Optional[HotState] = None,
    ) -> decimal.Decimal:
        """
        Compute large trade imbalance (volume-weighted, TASK31).
        
        FTR-03: V2 feature.
        Volume-weighted imbalance (qty or notional):
            imb = (buy - sell) / (buy + sell + eps) in [-1, 1]
            phi = (imb + 1) / 2 in [0, 1]

        Returns:
            Normalized imbalance in [0, 1]. >0.5 = buy dominance, <0.5 = sell dominance.
            Fail-closed: returns neutral_value when not ready; readiness is surfaced via HotState when provided.
        """
        res = self._get_large_trade_imbalance().compute_from_tick(current_tick)
        if state is not None:
            state.large_trade_imbalance_ready = bool(res.ready)
            state.large_trade_imbalance_not_ready_reason = res.why
            state.large_trade_imbalance_trades_used = int(res.trades_used)
            state.large_trade_imbalance_dropped_out_of_order = int(res.dropped_out_of_order)
        return res.phi

    # =========================================================================
    # DEPTH IMBALANCE
    # =========================================================================

    def compute_depth_imbalance(self, bid_size: decimal.Decimal, ask_size: decimal.Decimal) -> decimal.Decimal:
        """
        Compute depth imbalance with Laplace smoothing, normalized to [0,1].
        
        P2-2 SEMANTICS DOCUMENTATION:
        - Formula: ratio = (ask + half) / (bid + half)
        - Result: phi > 0.5 means ASK > BID (more sell pressure, BEARISH)
        - Result: phi < 0.5 means BID > ASK (more buy pressure, BULLISH)
        - Result: phi = 0.5 means balanced order book
        
        This is intentional: high phi = high ask/bid ratio = more sellers.
        Downstream consumers (decision_making) should interpret accordingly.
        
        Args:
            bid_size: Total bid depth (in USD or base)
            ask_size: Total ask depth (in USD or base)
            
        Returns:
            phi in [0, 1] where >0.5 = bearish (ask dominance), <0.5 = bullish (bid dominance)
        """
        # Config wiring: depth_imbalance.use_laplace_smoothing controls whether we add depth_half.
        # Contract: must be provided by FeatureEngineeringConfig (no silent runtime fallback).
        use_smoothing = bool(self.cfg.depth_imbalance_use_laplace_smoothing)
        depth_half = self.cfg.depth_half if use_smoothing else decimal.Decimal("0")

        # Defensive: sizes are expected non-negative (USD or base). If violated, fail-closed.
        if bid_size < 0 or ask_size < 0:
            return self.cfg.neutral_value

        denominator = bid_size + depth_half
        numerator = ask_size + depth_half

        # If smoothing is disabled, we must handle denominator==0 explicitly.
        if denominator <= 0:
            if numerator <= 0:
                return self.cfg.neutral_value
            # No bids, some asks -> extreme ask dominance.
            return decimal.Decimal("1")

        ratio = numerator / denominator
        imbalance = (ratio - decimal.Decimal("1")) / (ratio + decimal.Decimal("1"))
        phi = (imbalance + decimal.Decimal("1")) / decimal.Decimal("2")
        return phi

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
        if price is None or price <= 0:
            state.prev_price = price
            return

        if (
            state.prev_price is not None
            and state.prev_price > 0
            and 0 < time_diff_ms <= self.cfg.macro_sync_time_diff_threshold_ms
        ):
            ret = (price - state.prev_price) / state.prev_price
            state.returns_buffer.append(float(ret))

        state.prev_price = price

    def compute_macro_sync(
        self, 
        state: HotState,
        anchor_prices: Dict[str, Deque],
        *,
        anchor_last_ts_ms: Dict[str, int],
        current_ts_ms: int,
    ) -> decimal.Decimal:
        """Compute macro_sync = correlation with anchor returns, normalized to [0,1]."""
        state.macro_sync_ready = False
        state.macro_sync_not_ready_reason = None

        if not self.cfg.macro_sync_enabled or not self.cfg.macro_sync_anchors:
            state.macro_sync_ready = True
            return self.cfg.neutral_value

        sym_returns = list(state.returns_buffer)
        if len(sym_returns) < self.cfg.macro_sync_min_buffer:
            state.macro_sync_not_ready_reason = "insufficient_symbol_samples"
            return self.cfg.neutral_value

        align_mode = self.cfg.macro_sync_align_mode
        ttl_ms = int(self.cfg.macro_sync_ttl_ms)

        correlations: list[float] = []
        valid_anchors = 0
        for anchor in self.cfg.macro_sync_anchors:
            last_ts = int((anchor_last_ts_ms[anchor] if anchor in anchor_last_ts_ms else 0) or 0)
            if last_ts <= 0:
                continue
            if current_ts_ms - last_ts > ttl_ms:
                continue

            prices_deque = anchor_prices.get(anchor)
            if not prices_deque:
                continue
            anchor_prices_list = list(prices_deque)
            if len(anchor_prices_list) < 3:
                continue

            anchor_returns: list[float] = []
            for i in range(1, len(anchor_prices_list)):
                prev_p = anchor_prices_list[i - 1]
                if prev_p > 0:
                    ret = (anchor_prices_list[i] - prev_p) / prev_p
                    anchor_returns.append(float(ret))

            if len(anchor_returns) < self.cfg.macro_sync_min_buffer:
                continue

            # Alignment
            if align_mode == "strict_len":
                if len(anchor_returns) != len(sym_returns):
                    continue
                n = min(len(sym_returns), self.cfg.macro_sync_window)
                x = sym_returns[-n:]
                y = anchor_returns[-n:]
            else:
                n = min(len(sym_returns), len(anchor_returns), self.cfg.macro_sync_window)
                if n < self.cfg.macro_sync_min_buffer:
                    continue
                x = sym_returns[-n:]
                y = anchor_returns[-n:]

            corr = self._pearson_correlation(x, y)
            # Treat zero-variance as NOT_READY (avoid false "neutral correlation").
            if corr == 0.0 and (statistics.pstdev(x) == 0.0 or statistics.pstdev(y) == 0.0):
                continue

            correlations.append(corr)
            valid_anchors += 1

        if not correlations:
            if valid_anchors == 0:
                state.macro_sync_not_ready_reason = "no_fresh_anchor_data"
            else:
                state.macro_sync_not_ready_reason = "no_valid_correlation"
            return self.cfg.neutral_value

        avg_corr = statistics.mean(correlations)
        phi = (decimal.Decimal(str(avg_corr)) + decimal.Decimal("1")) / decimal.Decimal("2")
        # Clamp numerical noise
        phi = max(decimal.Decimal("0"), min(decimal.Decimal("1"), phi))

        state.macro_sync_ready = True
        state.macro_sync_not_ready_reason = None
        return phi

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

    def compute_macro_sync_v2(
        self,
        state: HotState,
        resampler: MacroSyncResampler,
        *,
        symbol: str,
        anchors: list[str],
        current_ts_ms: int,
    ) -> decimal.Decimal:
        """
        TASK30-I: Macro Sync V2 — time-grid aligned correlation (Epps removed).

        Contract:
        - Uses exchange ts_ms SSOT only (no wallclock fallback).
        - On NOT_READY: sets state.macro_sync_ready=false and macro_sync_not_ready_reason, returns neutral_value.
        - On READY: sets ready=true and clears reason, returns phi in [0,1].
        """
        state.macro_sync_ready = False
        state.macro_sync_not_ready_reason = None

        if not self.cfg.macro_sync_enabled or not anchors:
            state.macro_sync_ready = True
            return self.cfg.neutral_value

        if current_ts_ms <= 0:
            state.macro_sync_not_ready_reason = "tick_ts_missing"
            return self.cfg.neutral_value

        result = resampler.compute(symbol, anchors=anchors, now_ts_ms=int(current_ts_ms))
        if not result.ready:
            state.macro_sync_not_ready_reason = result.why or "not_ready"
            return self.cfg.neutral_value

        phi = decimal.Decimal(str(result.phi))
        phi = max(decimal.Decimal("0"), min(decimal.Decimal("1"), phi))
        state.macro_sync_ready = True
        state.macro_sync_not_ready_reason = None
        return phi

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
