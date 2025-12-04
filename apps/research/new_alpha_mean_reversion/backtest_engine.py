"""
Backtest Engine for Mean Reversion Strategy
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Trade:
    entry_ts: pd.Timestamp
    entry_price: float
    side: str  # 'LONG' or 'SHORT'
    exit_ts: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_raw: float = 0.0
    pnl_net: float = 0.0
    reason: str = ""

class BacktestEngineMeanReversion:
    def __init__(self, df_features: pd.DataFrame, df_golden_1s: pd.DataFrame, params: Dict):
        self.df = df_features.reset_index(drop=True)
        self.df_1s = df_golden_1s # For granular exits
        self.params = params
        self.trades: List[Trade] = []
        
        # Costs
        self.fee_rate = 0.0005  # 0.05% per side (taker)
        self.slippage = 0.0001  # 0.01% conservative
        
    def run(self):
        # Unpack params
        bb_window = self.params.get('bb_window', 20)
        bb_entry_std = self.params.get('bb_entry_std', 2.0) # e.g. enter at 2.0 std
        bb_exit_std = self.params.get('bb_exit_std', 0.0)   # e.g. exit at mean (0.0)
        rsi_window = self.params.get('rsi_window', 14)
        rsi_overbought = self.params.get('rsi_overbought', 70)
        rsi_oversold = self.params.get('rsi_oversold', 30)
        
        sl_pct = self.params.get('sl_pct', 0.005)
        tp_pct = self.params.get('tp_pct', 0.01)
        max_holding_sec = self.params.get('max_holding_sec', 600)
        
        # Regime Filter: ONLY trade in FLAT regimes
        # allowed_regimes = ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH'] 
        # (Maybe exclude FLAT_HIGH if toxic)
        allowed_regimes = self.params.get('allowed_regimes', ['FLAT_LOW', 'FLAT_NORMAL'])
        
        # Pre-calculate signals
        # Long: Price < Lower Band AND RSI < Oversold AND Regime is Flat
        # Short: Price > Upper Band AND RSI > Overbought AND Regime is Flat
        
        # Map dynamic column names
        col_pct_b = f'bb_pct_b_{bb_window}'
        col_rsi = f'rsi_{rsi_window}'
        
        # Entry Logic
        long_signal = (
            (self.df[col_pct_b] < (0.5 - bb_entry_std/4.0)) & # Approx mapping, or use raw price vs band
            # Better: Use pre-calculated bands if available, or re-calc?
            # Actually features.py calculates bb_pct_b. 
            # pct_b = 0 means lower band, 1 means upper band.
            # If entry_std = 2.0 (default bands), then pct_b < 0 is below lower band.
            (self.df[col_pct_b] < 0.0) & 
            (self.df[col_rsi] < rsi_oversold) &
            (self.df['regime_id'].isin(allowed_regimes))
        )
        
        short_signal = (
            (self.df[col_pct_b] > 1.0) & 
            (self.df[col_rsi] > rsi_overbought) &
            (self.df['regime_id'].isin(allowed_regimes))
        )
        
        active_trade = None
        
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            ts = row['ts']
            price = row['close_5s']
            
            # 1. Manage Active Trade
            if active_trade:
                # Check exit conditions using 1s data if possible, or 5s for speed
                # For speed in Python loop, we use 5s close. In production, use 1s.
                
                # Time Exit
                hold_time = (ts - active_trade.entry_ts).total_seconds()
                if hold_time >= max_holding_sec:
                    self._close_trade(active_trade, price, ts, "TIME_EXIT")
                    active_trade = None
                    continue
                
                # SL/TP
                if active_trade.side == 'LONG':
                    pnl_pct = (price - active_trade.entry_price) / active_trade.entry_price
                    if pnl_pct <= -sl_pct:
                        self._close_trade(active_trade, price, ts, "SL")
                        active_trade = None
                        continue
                    if pnl_pct >= tp_pct:
                        self._close_trade(active_trade, price, ts, "TP")
                        active_trade = None
                        continue
                    # Mean Reversion Exit: Crossed Mean?
                    # If pct_b > 0.5 (Mean), exit
                    if row[col_pct_b] >= 0.5:
                         self._close_trade(active_trade, price, ts, "MEAN_REVERSION")
                         active_trade = None
                         continue
                         
                elif active_trade.side == 'SHORT':
                    pnl_pct = (active_trade.entry_price - price) / active_trade.entry_price
                    if pnl_pct <= -sl_pct:
                        self._close_trade(active_trade, price, ts, "SL")
                        active_trade = None
                        continue
                    if pnl_pct >= tp_pct:
                        self._close_trade(active_trade, price, ts, "TP")
                        active_trade = None
                        continue
                    # Mean Reversion Exit
                    if row[col_pct_b] <= 0.5:
                         self._close_trade(active_trade, price, ts, "MEAN_REVERSION")
                         active_trade = None
                         continue
            
            # 2. Entry Logic (if no active trade)
            if active_trade is None:
                if long_signal.iloc[i]:
                    active_trade = Trade(entry_ts=ts, entry_price=price, side='LONG')
                elif short_signal.iloc[i]:
                    active_trade = Trade(entry_ts=ts, entry_price=price, side='SHORT')
                    
        return self._calculate_metrics()

    def _close_trade(self, trade, price, ts, reason):
        trade.exit_ts = ts
        trade.exit_price = price
        trade.reason = reason
        
        if trade.side == 'LONG':
            raw_pnl_pct = (price - trade.entry_price) / trade.entry_price
        else:
            raw_pnl_pct = (trade.entry_price - price) / trade.entry_price
            
        # Net PnL = Raw - 2 * (Fee + Slippage)
        # Assuming 1000 USD bet size for simplicity in metrics
        trade.pnl_raw = raw_pnl_pct * 1000.0
        
        costs = 2 * (self.fee_rate + self.slippage)
        trade.pnl_net = (raw_pnl_pct - costs) * 1000.0
        
        self.trades.append(trade)

    def _calculate_metrics(self):
        if not self.trades:
            return {
                'total_pnl_usd': 0.0,
                'trades': [],
                'win_rate': 0.0,
                'max_drawdown_pct': 0.0,
                'calmar': 0.0
            }
            
        df_trades = pd.DataFrame([t.__dict__ for t in self.trades])
        total_pnl = df_trades['pnl_net'].sum()
        win_rate = (df_trades['pnl_net'] > 0).mean()
        
        # Max DD
        df_trades['cum_pnl'] = df_trades['pnl_net'].cumsum()
        df_trades['peak'] = df_trades['cum_pnl'].cummax()
        df_trades['dd'] = df_trades['cum_pnl'] - df_trades['peak']
        max_dd = df_trades['dd'].min()
        
        # Calmar (Annualized Return / MaxDD)
        # Approx: PnL / abs(MaxDD)
        if max_dd == 0:
            calmar = 0.0
        else:
            calmar = total_pnl / abs(max_dd)
            
        return {
            'total_pnl_usd': total_pnl,
            'trades': self.trades,
            'win_rate': win_rate,
            'max_drawdown_pct': max_dd, # In USD terms here
            'calmar': calmar
        }
