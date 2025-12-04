import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict, Literal

from apps.research.momentum_backtest.metrics import calculate_metrics

@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    side: Literal["long", "short"]  # Support both long and short
    size: float # USD size
    pnl: float
    exit_reason: str # 'TP', 'SL', 'TIME'


class BacktestEngine:
    def __init__(self, 
                 df: pd.DataFrame, 
                 params: Dict):
        """
        df: DataFrame with features and OHLC (1s bars).
        params: Dictionary of strategy parameters.
        """
        self.df = df
        self.params = params
        
        # Unpack parameters
        self.w_tfi = params.get('w_tfi', 0.0)
        self.w_tob = params.get('w_tob', 0.0)
        self.w_bs = params.get('w_bs', 0.0)
        self.w_bl = params.get('w_bl', 0.0)
        self.threshold = params.get('threshold', 0.1)
        self.macro_corr_weight = params.get('macro_corr_weight', 0.0)
        
        self.sl_pct = params.get('sl_pct', 0.004)
        self.sl_tp_ratio = params.get('sl_tp_ratio', 2.0)
        self.tp_pct = self.sl_pct * self.sl_tp_ratio
        
        self.max_holding_secs = params.get('max_holding_secs', 300)
        self.funding_threshold_long = params.get('funding_threshold_long', 0.0005)
        
        self.position_size = params.get('position_size', 200.0) # USD
        self.commission = params.get('commission', 0.0005) # 0.05%
        self.slippage = params.get('slippage', 0.0001) # 0.01%
        self.spread_half = params.get('spread_half', 0.0001) # 0.01%
        
    def run(self, debug: bool = False, debug_limit: int = 2000) -> Dict:
        """
        Run the backtest.
        
        Args:
            debug: If True, log detailed signal/entry information
            debug_limit: Number of initial rows to log (default 2000)
        """
        # ================================================================
        # SIGNAL SCORE (PROD PARITY)
        # ================================================================
        # Production (decision_making.py) uses:
        #   score = w_tfi * tfi_phi + w_obi * obi_phi + w_bs * ema_short_phi
        #           + w_bl * ema_long_phi + w_macro * macro_phi + ...
        # ALL features normalized to [0,1] (phi-transform)
        # ADDITIVE weighted sum, not multiplicative!
        
        # Use phi-normalized features (all in [0,1] range)
        w_tfi = self.params['w_tfi']
        w_tob = self.params['w_tob']
        w_bs = self.params['w_bs']
        w_bl = self.params['w_bl']
        w_macro = self.params.get('w_macro', 0.0)
        # NEW WEIGHTS (Tier 1 extension)
        w_delta_price = self.params.get('w_delta_price', 0.0)
        w_volume_spike = self.params.get('w_volume_spike', 0.0)
        w_volatility_state = self.params.get('w_volatility_state', 0.0)
        w_depth_imbalance = self.params.get('w_depth_imbalance', 0.0)
        
        # Build additive score from phi-features
        score = (
            w_tfi * self.df['tfi_phi'] +
            w_tob * self.df['tob_phi'] +
            w_bs * self.df['ema_bias_short_phi'] +
            w_bl * self.df['ema_bias_long_phi'] +
            w_macro * self.df['macro_phi'] +
            w_delta_price * self.df['delta_price_phi'] +
            w_volume_spike * self.df['volume_spike_phi'] +
            w_volatility_state * self.df['volatility_state_phi'] +
            w_depth_imbalance * self.df['depth_imbalance_phi']
        )
        
        # NOTE: Old R&D formula (DISCARDED):
        #   score_raw = w_tfi * tfi_1m + w_tob * tob_imb + ...
        #   score = score_raw * (1 + macro_weight * macro_corr)
        # This was mathematically different from prod!
        
        # The instruction had a syntax error here: `threshold = self.params['threshold'], else 0`
        # Assuming it meant to use the class's threshold parameter.
        signals = (score > self.threshold).astype(int)
        
        # Funding Veto
        # If funding > threshold, signal = 0
        funding_veto = self.df['funding_rate_1s'] > self.funding_threshold_long
        signals[funding_veto] = 0
        
        # Simulation Loop
        trades: List[Trade] = []
        active_position = None
        equity = 10000.0 # Starting equity
        equity_curve = []
        
        # We need to iterate.
        # To speed up, we can iterate only when we have a signal or active position.
        # But for 1s granularity checking SL/TP, we need to check every second if in position.
        
        # Convert to numpy for speed
        ts_arr = self.df['ts'].values
        open_arr = self.df['open_1s'].values
        high_arr = self.df['high_1s'].values
        low_arr = self.df['low_1s'].values
        close_arr = self.df['close_1s'].values
        signal_arr = signals.values
        
        n = len(self.df)
        
        for i in range(n):
            current_time = ts_arr[i]
            current_close = close_arr[i]
            current_high = high_arr[i]
            current_low = low_arr[i]
            
            # Update equity curve (mark to market if in position, or flat)
            if active_position:
                # Unrealized PnL
                # Long: (current_close - entry_price) * size / entry_price
                unrealized_pnl = (current_close - active_position['entry_price']) * (active_position['size'] / active_position['entry_price'])
                equity_curve.append(equity + unrealized_pnl)
            else:
                equity_curve.append(equity)
            
            # Check Exit if in position
            if active_position:
                entry_price = active_position['entry_price']
                entry_time = active_position['entry_time']
                
                # Check SL/TP
                # SL price
                sl_price = entry_price * (1 - self.sl_pct)
                tp_price = entry_price * (1 + self.tp_pct)
                
                # Check Low/High of the current bar
                # Conservative: Check SL first.
                # If Low <= SL -> SL hit
                # If High >= TP -> TP hit
                # If both -> SL hit (conservative)
                
                exit_price = None
                exit_reason = None
                
                if current_low <= sl_price:
                    exit_price = sl_price # Assume filled at SL
                    # Apply slippage on SL? Usually SL is a stop market, so yes.
                    # We apply slippage to the execution price.
                    # Here we assume we exit AT sl_price, but we should apply slippage to it.
                    # exit_price = sl_price * (1 - slippage)
                    exit_price = sl_price * (1 - self.slippage)
                    exit_reason = 'SL'
                elif current_high >= tp_price:
                    exit_price = tp_price
                    # TP is limit order usually, so maybe no slippage? Or positive slippage?
                    # Let's assume neutral or slippage. Conservative: slippage.
                    exit_price = tp_price * (1 - self.slippage) 
                    exit_reason = 'TP'
                
                # Check Time Exit
                if not exit_reason:
                    # Calculate duration
                    # ts_arr[i] is numpy datetime64.
                    duration = (current_time - entry_time) / np.timedelta64(1, 's')
                    if duration >= self.max_holding_secs:
                        exit_price = current_close * (1 - self.slippage - self.spread_half)
                        exit_reason = 'TIME'
                
                if exit_reason:
                    # Execute Exit
                    # Commission
                    comm = exit_price * (active_position['size'] / entry_price) * self.commission
                    
                    # PnL
                    # (Exit - Entry) * Qty - Comm_Entry - Comm_Exit
                    qty = active_position['size'] / entry_price
                    gross_pnl = (exit_price - entry_price) * qty
                    net_pnl = gross_pnl - active_position['comm_entry'] - comm
                    
                    equity += net_pnl
                    
                    trades.append(Trade(
                        entry_time=pd.Timestamp(entry_time),
                        exit_time=pd.Timestamp(current_time),
                        entry_price=entry_price,
                        exit_price=exit_price,
                        side='LONG',
                        size=active_position['size'],
                        pnl=net_pnl,
                        exit_reason=exit_reason
                    ))
                    
                    active_position = None
                    continue # Position closed, can't enter in same bar (simplification)
            
            # Check Entry
            if not active_position:
                if signal_arr[i] == 1:
                    # Debug logging
                    if debug and i < debug_limit:
                        print(f"  Signal {count}: i={i}, ts={current_time}")
                        print(f"  close={current_close:.2f}, score={score.iloc[i]:.4f}")
                        print(f"  funding_rate={self.df['funding_rate_1s'].iloc[i]:.6f}, threshold={self.funding_threshold_long:.6f}")
                        print(f"  funding_veto={funding_veto.iloc[i]}")
                    
                    # Enter Long
                    # Price = Close + spread + slippage
                    entry_price = current_close * (1 + self.spread_half + self.slippage)
                    
                    # Commission
                    comm_entry = self.position_size * self.commission
                    
                    active_position = {
                        'entry_time': current_time,
                        'entry_price': entry_price,
                        'size': self.position_size,
                        'comm_entry': comm_entry
                    }
                    
        # Calculate Metrics
        equity_series = pd.Series(equity_curve, index=self.df['ts'])
        metrics = calculate_metrics(trades, equity_series)
        
        return {
            "trades": trades,
            "equity_curve": equity_series,
            "metrics": metrics
        }
