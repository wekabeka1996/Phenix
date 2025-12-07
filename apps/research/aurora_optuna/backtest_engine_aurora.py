"""
Aurora Backtest Engine with Risk Management
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Trade:
    id: int
    entry_ts: pd.Timestamp
    entry_price: float
    side: str
    size: float = 1000.0  # Default position size
    exit_ts: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_net: float = 0.0
    reason: str = ""
    
    # Phase 3+: Advanced Exit Logic
    tp_low: Optional[float] = None   # TP1 (partial exit)
    tp_high: Optional[float] = None  # TP2 (full exit)
    partial_exit_done: bool = False
    trailing_stop_active: bool = False
    highest_price: float = 0.0  # For LONG trailing
    lowest_price: float = float('inf')  # For SHORT trailing
    dynamic_sl: Optional[float] = None


class BacktestEngineAurora:
    """
    Aurora Backtest Engine with FULL execution logic mirroring production.
    
    Phase 3+: Added TP, Trailing Stop, Partial Exits, Cooldown
    """
    
    def __init__(self, df_features: pd.DataFrame, params: Dict, strategy_mode='weighted_signal'):
        self.df = df_features.copy()
        self.params = params
        self.strategy_mode = strategy_mode  # 'weighted_signal' or 'mean_reversion'
        self.trades: List[Trade] = []
        self.cost_basis = 0.0006  # 0.06% per side (taker fee)
        self.last_trade_exit_ts = None  # For cooldown tracking
    
    def run(self):
        active_trade = None
        trade_id_counter = 0
        
        # Phase 3+: Cooldown parameter
        cooldown_sec = self.params.get('cooldown_sec', 0)
        
        # Pre-calculate BB columns if in mean_reversion mode
        bb_window = self.params.get('bb_window', 20)
        col_mid = f'bb_mid_{bb_window}'
        col_upper = f'bb_upper_{bb_window}'
        col_lower = f'bb_lower_{bb_window}'
        col_width = f'bb_width_{bb_window}'
        
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            
            # Manage existing trade
            if active_trade:
                self._manage_trade(active_trade, row)
                if active_trade.exit_ts:
                    self.trades.append(active_trade)
                    self.last_trade_exit_ts = active_trade.exit_ts
                    active_trade = None
                continue
            
            # NEW: Check cooldown before entry
            if cooldown_sec > 0 and self.last_trade_exit_ts:
                time_since_exit = (row['ts'] - self.last_trade_exit_ts).total_seconds()
                if time_since_exit < cooldown_sec:
                    continue  # Skip (in cooldown period)
            
            # Entry logic
            regime = row.get('regime', 'UNKNOWN')
            risk_score = row.get('risk_score', 0.0)
            
            allowed_regimes = self.params.get('allowed_regimes', [])
            max_risk = self.params.get('max_risk_score', 1.0)
            
            if allowed_regimes and regime not in allowed_regimes:
                continue
            
            if risk_score > max_risk:
                continue
            
            signal = 0.0
            
            if self.strategy_mode == 'mean_reversion':
                # Mean Reversion Logic (BB)
                price = row['close_5s']
                min_vol_atr = self.params.get('min_vol_atr', 0.001)
                
                # Check BB columns exist
                if col_lower not in row or pd.isna(row[col_lower]):
                    continue
                    
                bb_width = row.get(col_width, 0)
                if bb_width < min_vol_atr:
                    continue
                
                dist_to_mean = 0.0
                if price < row[col_lower]:
                    dist_to_mean = (row[col_mid] - price) / price
                    if dist_to_mean > (self.cost_basis * 1.5):
                        signal = 1.0 # LONG
                elif price > row[col_upper]:
                    dist_to_mean = (price - row[col_mid]) / price
                    if dist_to_mean > (self.cost_basis * 1.5):
                        signal = -1.0 # SHORT
                
                # Mean reversion doesn't use threshold multiplier logic the same way, 
                # but we can reuse the final_threshold check by setting signal to +/- 1.0
                # and ensuring threshold < 1.0
                final_threshold = 0.5 # Arbitrary low threshold since signal is binary 1/-1
                
            else:
                # Weighted Signal Logic (Original Aurora)
                signal = self._compute_signal(row)
                
                # Entry decision with Phase 3 adaptive thresholds
                threshold_multiplier = 1.0
                if regime == 'HIGH_VOLATILITY':
                    threshold_multiplier = self.params.get('regime_threshold_high_vol', 1.0)
                elif regime == 'LOW_VOLATILITY':
                    threshold_multiplier = self.params.get('regime_threshold_low_vol', 1.0)
                elif regime == 'TREND_UP' or regime == 'TREND_DOWN':
                    threshold_multiplier = self.params.get('regime_threshold_trend', 1.0)
                
                base_threshold = self.params['signal_threshold']
                adjusted_threshold = base_threshold * threshold_multiplier
                
                # Side-Bias Penalty
                side_bias_penalty = 0.0
                bias_window = self.params.get('side_bias_window_sec', 0)
                
                if bias_window > 0 and len(self.trades) > 0:
                    current_ts = row['ts']
                    window_start = current_ts - pd.Timedelta(seconds=bias_window)
                    
                    recent_trades = [t for t in self.trades if t.exit_ts and t.exit_ts > window_start]
                    if recent_trades:
                        longs = sum(1 for t in recent_trades if t.side == 'LONG')
                        shorts = sum(1 for t in recent_trades if t.side == 'SHORT')
                        total = longs + shorts
                        
                        if total > 0:
                            if signal > 0:
                                ratio = longs / total
                                if ratio > 0.6:
                                    side_bias_penalty = (ratio - 0.5) * self.params.get('side_bias_penalty_factor', 0.0)
                            elif signal < 0:
                                ratio = shorts / total
                                if ratio > 0.6:
                                    side_bias_penalty = (ratio - 0.5) * self.params.get('side_bias_penalty_factor', 0.0)
                
                final_threshold = adjusted_threshold * (1.0 + side_bias_penalty)
            
            # Regime-Adaptive Sizing
            size_multiplier = 1.0
            if regime == 'HIGH_VOLATILITY':
                size_multiplier = self.params.get('sizing_high_vol', 1.0)
            elif regime == 'LOW_VOLATILITY':
                size_multiplier = self.params.get('sizing_low_vol', 1.0)
            elif regime == 'MEAN_REVERSION':
                size_multiplier = self.params.get('sizing_mean_rev', 1.0)
            
            base_size = self.params.get('position_size', 1000.0)
            trade_size = base_size * size_multiplier
            
            # Entry Execution
            if signal > final_threshold:
                trade_id_counter += 1
                active_trade = Trade(
                    id=trade_id_counter,
                    entry_ts=row['ts'],
                    entry_price=row['close_5s'],
                    side='LONG',
                    size=trade_size
                )
            elif signal < -final_threshold:
                trade_id_counter += 1
                active_trade = Trade(
                    id=trade_id_counter,
                    entry_ts=row['ts'],
                    entry_price=row['close_5s'],
                    side='SHORT',
                    size=trade_size
                )
        
        return self._calculate_metrics()
    
    def _compute_signal(self, row):
        """
        Composite signal from features (weighted average)
        Phase 1 (40%) + Phase 2 (20%) features
        """
        # PHASE 1 WEIGHTS
        weights = {
            'ema_bias': self.params.get('weight_ema', 0.3),
            'volume_spike': self.params.get('weight_volume', 0.2),
            'macro_sync': self.params.get('weight_macro', 0.3),
            'liquidity': self.params.get('weight_liquidity', 0.2),
            'obi': self.params.get('weight_obi', 0.0),
            'tfi': self.params.get('weight_tfi', 0.0),
        }
        
        # PHASE 2 WEIGHTS (NEW!)
        weights['volatility_state'] = self.params.get('weight_volatility', 0.0)
        weights['depth_imbalance'] = self.params.get('weight_depth_imbalance', 0.0)
        weights['delta_price'] = self.params.get('weight_delta_price', 0.0)
        
        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0
        weights = {k: v/total_weight for k, v in weights.items()}
        
        # Compute weighted signal
        # Phase 1 features (normalized to [0,1] → convert to [-1, 1])
        signal = (
            weights['ema_bias'] * (row.get('ema_bias', 0.5) - 0.5) * 2 +
            weights['volume_spike'] * (row.get('volume_spike', 0.5) - 0.5) * 2 +
            weights['macro_sync'] * (row.get('macro_sync', 0.5) - 0.5) * 2 +
            weights['liquidity'] * (row.get('liquidity', 0.5) - 0.5) * 2 +
            weights['obi'] * row.get('obi', 0) +  # Already [-1, 1]
            weights['tfi'] * row.get('tfi', 0)    # Already [-1, 1]
        )
        
        # Phase 2 features (NEW!)
        signal += weights['volatility_state'] * (row.get('volatility_state', 0.5) - 0.5) * 2
        signal += weights['depth_imbalance'] * (row.get('depth_imbalance', 0.5) - 0.5) * 2
        signal += weights['delta_price'] * (row.get('delta_price', 0.5) - 0.5) * 2
        
        return signal
    
    def _manage_trade(self, trade, row):
        """
        FULL EXECUTION LOGIC: TP (partial + full), Trailing Stop, SL, Time Exit
        """
        price = row['close_5s']
        sl_pct = self.params.get('sl_pct', 0.01)
        
        # Phase 3+: TP ratios
        tp_low_ratio = self.params.get('tp_low_ratio', 0.5)
        tp_high_ratio = self.params.get('tp_high_ratio', 1.0)
        partial_exit_pct = self.params.get('partial_exit_pct', 0.5)
        
        # Phase 3+: Trailing stop parameters
        trailing_activation_pct = self.params.get('trailing_stop_activation_pct', 0.005)
        trailing_distance_pct = self.params.get('trailing_stop_distance_pct', 0.003)
        
        # Initialize TP prices on first manage call
        if trade.tp_low is None:
            if trade.side == 'LONG':
                trade.tp_low = trade.entry_price * (1 + sl_pct * tp_low_ratio)
                trade.tp_high = trade.entry_price * (1 + sl_pct * tp_high_ratio)
            else:  # SHORT
                trade.tp_low = trade.entry_price * (1 - sl_pct * tp_low_ratio)
                trade.tp_high = trade.entry_price * (1 - sl_pct * tp_high_ratio)
        
        # ========== TAKE PROFIT LOGIC ==========
        # TP1 (Partial Exit)
        if not trade.partial_exit_done:
            tp1_hit = False
            if trade.side == 'LONG' and price >= trade.tp_low:
                tp1_hit = True
            elif trade.side == 'SHORT' and price <= trade.tp_low:
                tp1_hit = True
            
            if tp1_hit:
                # Record partial PnL
                exit_size = trade.size * partial_exit_pct
                remaining_size = trade.size * (1 - partial_exit_pct)
                
                if trade.side == 'LONG':
                    partial_pnl_pct = (price - trade.entry_price) / trade.entry_price
                else:
                    partial_pnl_pct = (trade.entry_price - price) / trade.entry_price
                
                trade.pnl_net += (partial_pnl_pct - self.cost_basis) * exit_size
                trade.size = remaining_size
                trade.partial_exit_done = True
                return  # Continue with remaining position
        
        # TP2 (Full Exit) - only if TP1 already hit
        if trade.partial_exit_done:
            tp2_hit = False
            if trade.side == 'LONG' and price >= trade.tp_high:
                tp2_hit = True
            elif trade.side == 'SHORT' and price <= trade.tp_high:
                tp2_hit = True
            
            if tp2_hit:
                self._close_trade(trade, price, row['ts'], "TP_HIGH")
                return
        
        # ========== TRAILING STOP LOGIC ==========
        if trade.side == 'LONG':
            # Update highest price
            if trade.highest_price == 0.0:
                trade.highest_price = trade.entry_price
            trade.highest_price = max(trade.highest_price, price)
            
            # Check activation
            profit_pct = (price - trade.entry_price) / trade.entry_price
            if profit_pct >= trailing_activation_pct:
                trade.trailing_stop_active = True
            
            # Update and check trailing stop
            if trade.trailing_stop_active:
                trade.dynamic_sl = trade.highest_price * (1 - trailing_distance_pct)
                if price <= trade.dynamic_sl:
                    self._close_trade(trade, price, row['ts'], "TRAILING_STOP")
                    return
        
        else:  # SHORT
            # Update lowest price
            if trade.lowest_price == float('inf'):
                trade.lowest_price = trade.entry_price
            trade.lowest_price = min(trade.lowest_price, price)
            
            # Check activation
            profit_pct = (trade.entry_price - price) / trade.entry_price
            if profit_pct >= trailing_activation_pct:
                trade.trailing_stop_active = True
            
            # Update and check trailing stop
            if trade.trailing_stop_active:
                trade.dynamic_sl = trade.lowest_price * (1 + trailing_distance_pct)
                if price >= trade.dynamic_sl:
                    self._close_trade(trade, price, row['ts'], "TRAILING_STOP")
                    return
        
        # ========== STOP LOSS ==========
        if trade.side == 'LONG':
            pnl_pct = (price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - price) / trade.entry_price
        
        # Use dynamic SL if trailing is active, otherwise static SL
        if trade.trailing_stop_active and trade.dynamic_sl:
            # Already handled above
            pass
        else:
            if pnl_pct <= -sl_pct:
                self._close_trade(trade, price, row['ts'], "STOP_LOSS")
                return
        
        # ========== TIME EXIT ==========
        time_diff = (row['ts'] - trade.entry_ts).total_seconds()
        if time_diff > self.params.get('max_hold_sec', 300):
            self._close_trade(trade, price, row['ts'], "TIME_EXIT")
    
    def _close_trade(self, trade, price, ts, reason):
        trade.exit_ts = ts
        trade.exit_price = price
        trade.reason = reason
        
        # Calculate remaining PnL (if partial exit already done, size is reduced)
        if trade.side == 'LONG':
            raw = (price - trade.entry_price) / trade.entry_price
        else:
            raw = (trade.entry_price - price) / trade.entry_price
        
        # Add remaining PnL to any already realized from partial exit
        trade.pnl_net += (raw - self.cost_basis) * trade.size
    
    def _calculate_metrics(self):
        if not self.trades:
            return {'total_pnl': 0.0, 'calmar': 0.0, 'trades': 0}
        
        df = pd.DataFrame([t.__dict__ for t in self.trades])
        total_pnl = df['pnl_net'].sum()
        
        cum_pnl = df['pnl_net'].cumsum()
        peak = cum_pnl.cummax()
        dd = cum_pnl - peak
        max_dd = dd.min()
        
        if max_dd == 0:
            calmar = 0.0
        else:
            calmar = total_pnl / abs(max_dd)
        
        return {
            'total_pnl': total_pnl,
            'trades': len(self.trades),
            'win_rate': (df['pnl_net'] > 0).mean(),
            'max_dd': max_dd,
            'calmar': calmar
        }
