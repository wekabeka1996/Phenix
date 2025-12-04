"""
Backtest Engine V2 with Inverse Symmetry Support

Supports 3 strategy modes:
- base: Current logic (long-only, standard score)
- score_flip: Inverted score (long-only, 1-phi features)
- side_flip: Standard score with inverted side (short instead of long)
"""

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
    side: Literal["long", "short"]
    size: float  # USD notional size
    pnl: float
    exit_reason: str  # 'TP', 'SL', 'TIME'


class BacktestEngineV2:
    """
    Backtest engine with support for inverse symmetry testing.
    """
    
    def __init__(self, df: pd.DataFrame, params: Dict):
        """
        Args:
            df: DataFrame with features and OHLC (1s bars)
            params: Dictionary of strategy parameters including strategy_mode
        """
        self.df = df
        self.params = params
        
        # Strategy mode
        self.strategy_mode = params.get('strategy_mode', 'base')
        if self.strategy_mode not in ('base', 'score_flip', 'side_flip'):
            raise ValueError(f"Invalid strategy_mode: {self.strategy_mode}")
        
        # Unpack parameters
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
        
        # Entry Gates
        self.depth_imbalance_phi_min = params.get('depth_imbalance_phi_min', 0.6)
        self.tob_phi_min = params.get('tob_phi_min', 0.6)
        self.ema_bias_long_phi_min = params.get('ema_bias_long_phi_min', 0.4)
        self.vol_state_phi_min = params.get('vol_state_phi_min', 0.05)
        self.vol_state_phi_max = params.get('vol_state_phi_max', 0.95)
        
        self.sl_pct = params.get('sl_pct', 0.004)
        self.sl_tp_ratio = params.get('sl_tp_ratio', 2.0)
        self.tp_pct = self.sl_pct * self.sl_tp_ratio
        
        self.max_holding_secs = params.get('max_holding_secs', 300)
        self.funding_threshold_long = params.get('funding_threshold_long', 0.0005)
        
        self.position_size = params.get('position_size', 200.0)
        self.commission = params.get('commission', 0.0005)
        self.slippage = params.get('slippage', 0.0001)
        self.spread_half = params.get('spread_half', 0.0001)
    
    def _compute_score_base(self) -> pd.Series:
        """
        Compute base score using phi-normalized features.
        Formula: score = Σ w_i * φ_i
        """
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
    
    def _compute_score_flip(self) -> pd.Series:
        """
        Compute flipped score by inverting phi features.
        Formula: score_flip = Σ w_i * (1 - φ_i)
        """
        score = (
            self.w_tfi * (1 - self.df['tfi_phi']) +
            self.w_tob * (1 - self.df['tob_phi']) +
            self.w_bs * (1 - self.df['ema_bias_short_phi']) +
            self.w_bl * (1 - self.df['ema_bias_long_phi']) +
            self.w_macro * (1 - self.df['macro_phi']) +
            self.w_delta_price * (1 - self.df['delta_price_phi']) +
            self.w_volume_spike * (1 - self.df['volume_spike_phi']) +
            self.w_volatility_state * (1 - self.df['volatility_state_phi']) +
            self.w_depth_imbalance * (1 - self.df['depth_imbalance_phi'])
        )
        return score
    
    def _calculate_entry_price(self, close: float, side: str) -> float:
        """Calculate entry price with slippage and spread."""
        if side == "long":
            return close + close * self.slippage + close * self.spread_half
        else:  # short
            return close - close * self.slippage - close * self.spread_half
    
    def _calculate_sl_tp_prices(self, entry_price: float, side: str) -> tuple:
        """Calculate SL and TP prices for given side."""
        if side == "long":
            sl_price = entry_price * (1 - self.sl_pct)
            tp_price = entry_price * (1 + self.tp_pct)
        else:  # short
            sl_price = entry_price * (1 + self.sl_pct)  # Inverted for short
            tp_price = entry_price * (1 - self.tp_pct)  # Inverted for short
        return sl_price, tp_price
    
    def _check_exit(self, active_position: Dict, bar_high: float, bar_low: float) -> tuple:
        """
        Check if position should exit via SL/TP.
        Returns: (exit_price, exit_reason) or (None, None)
        """
        entry_price = active_position['entry_price']
        side = active_position['side']
        sl_price, tp_price = self._calculate_sl_tp_prices(entry_price, side)
        
        exit_price = None
        exit_reason = None
        
        if side == "long":
            # Long: SL below entry, TP above entry
            if bar_low <= sl_price:
                exit_price = sl_price * (1 - self.slippage)
                exit_reason = 'SL'
            elif bar_high >= tp_price:
                exit_price = tp_price * (1 - self.slippage)
                exit_reason = 'TP'
        else:  # short
            # Short: SL above entry, TP below entry
            if bar_high >= sl_price:
                exit_price = sl_price * (1 + self.slippage)  # Slippage worse for short SL
                exit_reason = 'SL'
            elif bar_low <= tp_price:
                exit_price = tp_price * (1 + self.slippage)  # Slippage worse for short TP
                exit_reason = 'TP'
        
        return exit_price, exit_reason
    
    def _calculate_pnl(self, entry_price: float, exit_price: float, side: str, size: float) -> float:
        """Calculate PnL including fees."""
        if side == "long":
            gross_pnl = (exit_price - entry_price) * (size / entry_price)
        else:  # short
            gross_pnl = (entry_price - exit_price) * (size / entry_price)
        
        # Deduct commissions (entry + exit)
        fees = size * self.commission * 2
        net_pnl = gross_pnl - fees
        return net_pnl
    
    def run(self, debug: bool = False, debug_limit: int = 2000) -> Dict:
        """
        Run backtest with selected strategy mode.
        
        Returns:
            Dictionary with metrics and trade list
        """
        # Always compute base score for signal generation
        score = self._compute_score_base()
        
        # Generate entry signals from base score
        signals = (score > self.threshold).astype(int)
        
        # Apply Entry Gates (Vectorized)
        # 1. Depth Imbalance Gate
        gate_depth = self.df['depth_imbalance_phi'] >= self.depth_imbalance_phi_min
        
        # 2. ToB Gate
        gate_tob = self.df['tob_phi'] >= self.tob_phi_min
        
        # 3. EMA Context Gate
        gate_ema = self.df['ema_bias_long_phi'] >= self.ema_bias_long_phi_min
        
        # 4. Volatility Gate (Min/Max)
        gate_vol = (self.df['volatility_state_phi'] >= self.vol_state_phi_min) & \
                   (self.df['volatility_state_phi'] <= self.vol_state_phi_max)
        
        # Combine gates
        gate_mask = gate_depth & gate_tob & gate_ema & gate_vol
        
        # Apply gates to signals
        signals = signals & gate_mask.astype(int)
        
        # Funding veto for base signals only
        funding_veto = self.df['funding_rate_1s'] > self.funding_threshold_long
        if self.strategy_mode != 'score_flip':
            signals[funding_veto] = 0
        
        # For score_flip, invert the signals
        # (Do NOT apply funding veto - it's specific to long momentum bias)
        if self.strategy_mode == 'score_flip':
            signals = 1 - signals  # Invert: 0 -> 1, 1 -> 0
        
        # Determine trade side based on mode
        if self.strategy_mode == 'side_flip':
            trade_side = "short"  # Flip to short
        else:
            trade_side = "long"  # base and score_flip use long
        
        # Simulation loop
        trades: List[Trade] = []
        active_position = None
        equity = 10000.0
        equity_curve = []
        
        # Convert to numpy for speed
        ts_arr = self.df['ts'].values
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
            
            # Update equity curve
            if active_position:
                unrealized_pnl = self._calculate_unrealized_pnl(active_position, current_close)
                equity_curve.append(equity + unrealized_pnl)
            else:
                equity_curve.append(equity)
            
            # Check exit if in position
            if active_position:
                entry_time = active_position['entry_time']
                entry_price = active_position['entry_price']
                side = active_position['side']
                
                # Check SL/TP
                exit_price, exit_reason = self._check_exit(active_position, current_high, current_low)
                
                # Check time exit
                if not exit_reason:
                    duration = (current_time - entry_time) / np.timedelta64(1, 's')
                    if duration >= self.max_holding_secs:
                        exit_price = current_close
                        exit_reason = 'TIME'
                
                # Execute exit
                if exit_reason:
                    pnl = self._calculate_pnl(entry_price, exit_price, side, self.position_size)
                    
                    trade = Trade(
                        entry_time=entry_time,
                        exit_time=current_time,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        side=side,
                        size=self.position_size,
                        pnl=pnl,
                        exit_reason=exit_reason
                    )
                    trades.append(trade)
                    
                    equity += pnl
                    active_position = None
                    
                    if debug and len(trades) <= debug_limit:
                        print(f"  EXIT: {exit_reason} at {current_time}, price={exit_price:.2f}, pnl=${pnl:.2f}")
            
            # Check entry if no position
            if not active_position and signal_arr[i] == 1:
                entry_price = self._calculate_entry_price(current_close, trade_side)
                
                active_position = {
                    'entry_time': current_time,
                    'entry_price': entry_price,
                    'side': trade_side
                }
                
                if debug and len(trades) <= debug_limit:
                    print(f"  ENTRY: {trade_side.upper()} at {current_time}, price={entry_price:.2f}")
        
        # Close any remaining position at end
        if active_position:
            exit_price = close_arr[-1]
            pnl = self._calculate_pnl(active_position['entry_price'], exit_price, active_position['side'], self.position_size)
            
            trade = Trade(
                entry_time=active_position['entry_time'],
                exit_time=ts_arr[-1],
                entry_price=active_position['entry_price'],
                exit_price=exit_price,
                side=active_position['side'],
                size=self.position_size,
                pnl=pnl,
                exit_reason='END'
            )
            trades.append(trade)
            equity += pnl
        
        # Calculate metrics
        # Convert equity_curve to Series with timestamp index
        equity_series = pd.Series(equity_curve, index=self.df['ts'][:len(equity_curve)])
        metrics = calculate_metrics(trades, equity_series)
        
        # Add additional metrics
        metrics['strategy_mode'] = self.strategy_mode
        metrics['final_equity'] = equity
        metrics['total_pnl_usd'] = sum(t.pnl for t in trades) if trades else 0.0
        metrics['max_drawdown_pct'] = abs(metrics.get('max_drawdown', 0.0)) * 100
        metrics['calmar'] = metrics.get('calmar_ratio', 0.0)
        metrics['sharpe'] = metrics.get('sharpe_ratio', 0.0) if 'sharpe_ratio' in metrics else 0.0
        
        # Return raw data for walk-forward aggregation
        metrics['trades'] = trades
        metrics['equity_curve'] = equity_series
        
        return metrics
    
    def _calculate_unrealized_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate unrealized PnL for mark-to-market."""
        entry_price = position['entry_price']
        side = position['side']
        
        if side == "long":
            return (current_price - entry_price) * (self.position_size / entry_price)
        else:  # short
            return (entry_price - current_price) * (self.position_size / entry_price)
