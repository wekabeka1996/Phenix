"""
Backtest Engine Multiscale

Supports trading on aggregated bars (5s, 10s) while simulating exits on 1s data.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Literal

from apps.research.momentum_backtest.metrics import calculate_metrics

@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    side: Literal["long", "short"]
    size: float
    pnl: float
    exit_reason: str

class BacktestEngineMultiscale:
    def __init__(self, df_features: pd.DataFrame, df_1s: pd.DataFrame, params: Dict):
        """
        Args:
            df_features: Features DataFrame (1s, 5s, or 10s resolution)
            df_1s: Golden 1s DataFrame (for granular exit simulation)
            params: Strategy parameters
        """
        self.df = df_features
        self.df_1s = df_1s
        self.params = params
        
        # Ensure 1s data is indexed by TS for fast slicing
        if not isinstance(self.df_1s.index, pd.DatetimeIndex):
            self.df_1s = self.df_1s.set_index('ts').sort_index()
            
        # Params
        self.strategy_mode = params.get('strategy_mode', 'base') # Only 'base' (Sniper) supported really
        
        # Weights
        self.w_tfi = params.get('w_tfi', 0.0)
        self.w_tob = params.get('w_tob', 0.0)
        self.w_bs = params.get('w_bs', 0.0)
        self.w_bl = params.get('w_bl', 0.0)
        self.w_macro = params.get('w_macro', 0.0)
        self.w_delta_price = params.get('w_delta_price', 0.0)
        self.w_volume_spike = params.get('w_volume_spike', 0.0)
        self.w_volatility_state = params.get('w_volatility_state', 0.0)
        self.w_depth_imbalance = params.get('w_depth_imbalance', 0.0)
        
        self.threshold = params.get('threshold', 0.1)
        
        # Gates
        self.depth_imbalance_phi_min = params.get('depth_imbalance_phi_min', 0.0)
        self.tob_phi_min = params.get('tob_phi_min', 0.0)
        self.ema_bias_long_phi_min = params.get('ema_bias_long_phi_min', 0.0)
        self.vol_state_phi_min = params.get('vol_state_phi_min', 0.0)
        self.vol_state_phi_max = params.get('vol_state_phi_max', 1.0)
        
        # Risk
        self.sl_pct = params.get('sl_pct', 0.005)
        self.sl_tp_ratio = params.get('sl_tp_ratio', 2.0)
        self.tp_pct = self.sl_pct * self.sl_tp_ratio
        self.max_holding_secs = params.get('max_holding_secs', 300)
        
        self.position_size = params.get('position_size', 200.0)
        self.commission = params.get('commission', 0.0005)
        self.slippage = params.get('slippage', 0.0001)
        self.spread_half = params.get('spread_half', 0.0001)
        
        self.funding_threshold_long = params.get('funding_threshold_long', 0.001)
        
        # Regime Gating
        self.regime_allowlist = params.get('regime_allowlist', None)  # List of allowed regimes, e.g., ["UP_NORMAL", "FLAT_LOW"]

    def _compute_score(self) -> pd.Series:
        # Assumes columns are already renamed to standard names (tfi_phi, etc)
        score = (
            self.w_tfi * self.df['tfi_phi'] +
            self.w_tob * self.df['tob_phi'] +
            self.w_bs * self.df['ema_bias_short_phi'] +
            self.w_bl * self.df['ema_bias_long_phi'] +
            self.w_macro * self.df['macro_phi'] +
            self.w_delta_price * self.df['delta_price_phi'] +
            self.w_volume_spike * self.df['volume_spike_phi'] +
            self.w_volatility_state * self.df['volatility_state_phi'] +
            self.w_depth_imbalance * self.df['depth_imbalance_phi']
        )
        return score

    def _simulate_trade(self, entry_time: pd.Timestamp, entry_price: float, side: str) -> Trade:
        """
        Simulate trade outcome using 1s granular data.
        """
        # Define exit conditions
        if side == "long":
            sl_price = entry_price * (1 - self.sl_pct)
            tp_price = entry_price * (1 + self.tp_pct)
        else:
            sl_price = entry_price * (1 + self.sl_pct)
            tp_price = entry_price * (1 - self.tp_pct)
            
        # Slice 1s data
        end_time = entry_time + pd.Timedelta(seconds=self.max_holding_secs)
        
        # Get slice (inclusive of entry, but we should start checking from NEXT second?)
        # Realistically, if we enter at T, we check exits from T+1s.
        # But if we enter at 5s bar close, that is T. The next 1s bar is T+1.
        
        # Slicing is fast on DatetimeIndex
        # We use searchsorted to find positions? No, loc is easier but might be slower if not unique.
        # Golden data is unique ts.
        
        try:
            # We need data strictly AFTER entry_time
            # slice_df = self.df_1s.loc[entry_time : end_time] # This includes entry_time
            # Let's assume we can't exit on the same second we enter (latency).
            
            # Optimization: Use searchsorted on the index values
            # This avoids creating a sub-dataframe if we just iterate arrays
            
            # But we need High/Low.
            # Let's just use .loc for simplicity first.
            slice_df = self.df_1s[entry_time : end_time]
            
            # Skip the first row if it matches entry_time exactly (we enter at close)
            if len(slice_df) > 0 and slice_df.index[0] == entry_time:
                slice_df = slice_df.iloc[1:]
                
            if len(slice_df) == 0:
                # No data? Force time exit at entry price (neutral)
                return Trade(entry_time, entry_time, entry_price, entry_price, side, self.position_size, 0.0, "ERROR")
            
            # Vectorized check?
            # For Long:
            #   Hit SL: Low <= sl_price
            #   Hit TP: High >= tp_price
            
            highs = slice_df['high_1s'].values
            lows = slice_df['low_1s'].values
            closes = slice_df['close_1s'].values
            times = slice_df.index
            
            exit_time = end_time
            exit_price = closes[-1]
            exit_reason = "TIME"
            
            for i in range(len(highs)):
                h = highs[i]
                l = lows[i]
                ts = times[i]
                
                if side == "long":
                    # Check SL first (conservative)
                    if l <= sl_price:
                        exit_price = sl_price * (1 - self.slippage)
                        exit_reason = "SL"
                        exit_time = ts
                        break
                    if h >= tp_price:
                        exit_price = tp_price * (1 - self.slippage)
                        exit_reason = "TP"
                        exit_time = ts
                        break
                else: # Short
                    if h >= sl_price:
                        exit_price = sl_price * (1 + self.slippage)
                        exit_reason = "SL"
                        exit_time = ts
                        break
                    if l <= tp_price:
                        exit_price = tp_price * (1 + self.slippage)
                        exit_reason = "TP"
                        exit_time = ts
                        break
            
            # Calculate PnL
            if side == "long":
                gross_pnl = (exit_price - entry_price) * (self.position_size / entry_price)
            else:
                gross_pnl = (entry_price - exit_price) * (self.position_size / entry_price)
                
            fees = self.position_size * self.commission * 2
            net_pnl = gross_pnl - fees
            
            return Trade(entry_time, exit_time, entry_price, exit_price, side, self.position_size, net_pnl, exit_reason)
            
        except Exception as e:
            print(f"Simulation error: {e}")
            return Trade(entry_time, entry_time, entry_price, entry_price, side, self.position_size, 0.0, "ERROR")

    def run(self) -> Dict:
        # Compute score
        score = self._compute_score()
        signals = (score > self.threshold).astype(int)
        
        # Apply Gates
        gate_depth = self.df['depth_imbalance_phi'] >= self.depth_imbalance_phi_min
        gate_tob = self.df['tob_phi'] >= self.tob_phi_min
        gate_ema = self.df['ema_bias_long_phi'] >= self.ema_bias_long_phi_min
        gate_vol = (self.df['volatility_state_phi'] >= self.vol_state_phi_min) & \
                   (self.df['volatility_state_phi'] <= self.vol_state_phi_max)
        
        gate_mask = gate_depth & gate_tob & gate_ema & gate_vol
        signals = signals & gate_mask.astype(int)
        
        # Regime Gating
        if self.regime_allowlist is not None and 'regime_id' in self.df.columns:
            regime_mask = self.df['regime_id'].isin(self.regime_allowlist)
            signals = signals & regime_mask.astype(int)
        
        # Funding veto
        funding_veto = self.df['funding_rate_1s'] > self.funding_threshold_long
        signals[funding_veto] = 0
        
        # Simulation Loop (Fast Forward)
        trades: List[Trade] = []
        equity = 10000.0
        equity_curve = [] # We can't easily build 1s equity curve here without full simulation.
                          # We will build "trade-to-trade" equity curve for metrics.
        
        # Convert to numpy
        ts_arr = self.df['ts'].values
        close_arr = self.df['close_1s'].values
        signal_arr = signals.values
        
        i = 0
        n = len(self.df)
        
        while i < n:
            # Check signal
            if signal_arr[i] == 1:
                entry_time = ts_arr[i]
                entry_close = close_arr[i]
                
                # Entry price (Long only for Sniper)
                entry_price = entry_close * (1 + self.slippage + self.spread_half)
                
                # Simulate
                trade = self._simulate_trade(entry_time, entry_price, "long")
                trades.append(trade)
                equity += trade.pnl
                
                # Fast forward
                # Find index of bar AFTER exit_time
                # Since df is sorted, we can search.
                # But exit_time might be between bars (if 1s resolution exit).
                # We need the first bar where ts > exit_time.
                
                # Optimization: assume bars are roughly uniform.
                # Or just use searchsorted on ts_arr?
                # ts_arr is numpy array of datetime64.
                
                exit_ts = np.datetime64(trade.exit_time)
                next_i = np.searchsorted(ts_arr, exit_ts, side='right')
                
                # Ensure we advance at least 1 step
                i = max(i + 1, next_i)
                
            else:
                i += 1
        
        # Metrics
        # Construct equity series from trades
        # This is an approximation (step function), but sufficient for Calmar/DD on trade basis.
        # For accurate Time-Weighted DD, we'd need the 1s curve.
        # But `calculate_metrics` expects a Series.
        
        if trades:
            # Create a series with index = exit_time, value = cumulative equity
            trade_exits = [t.exit_time for t in trades]
            trade_pnls = [t.pnl for t in trades]
            cum_pnl = np.cumsum(trade_pnls)
            equity_values = 10000.0 + cum_pnl
            
            equity_series = pd.Series(equity_values, index=trade_exits)
            # Add start point
            equity_series = pd.concat([pd.Series([10000.0], index=[ts_arr[0]]), equity_series])
        else:
            equity_series = pd.Series([10000.0], index=[ts_arr[0]])
            
        metrics = calculate_metrics(trades, equity_series)
        
        metrics['total_pnl_usd'] = sum(t.pnl for t in trades) if trades else 0.0
        metrics['max_drawdown_pct'] = abs(metrics.get('max_drawdown', 0.0)) * 100
        metrics['calmar'] = metrics.get('calmar_ratio', 0.0)
        metrics['trades'] = trades
        metrics['equity_curve'] = equity_series
        
        return metrics
