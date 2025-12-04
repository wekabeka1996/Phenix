"""
Backtest Engine for 1m Mean Reversion
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
    size: float = 1000.0
    exit_ts: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_net: float = 0.0
    reason: str = ""
    
@dataclass
class DecisionLog:
    ts: pd.Timestamp
    price: float
    signal: str
    regime: str
    volatility: float
    dist_to_mean: float
    expected_pnl_pct: float
    action: str
    comment: str

class BacktestEngine1m:
    def __init__(self, df_features: pd.DataFrame, params: Dict):
        self.df = df_features.reset_index(drop=True)
        self.params = params
        self.trades: List[Trade] = []
        self.logs: List[DecisionLog] = []
        
        # Costs
        self.maker_fee = 0.0002
        self.taker_fee = 0.0005
        self.slippage = 0.0001
        self.cost_basis = self.maker_fee + self.taker_fee + self.slippage 
        
    def run(self, debug=False):
        bb_window = self.params.get('bb_window', 20)
        min_vol_atr = self.params.get('min_vol_atr', 0.001)
        
        col_mid = f'bb_mid_{bb_window}'
        col_upper = f'bb_upper_{bb_window}'
        col_lower = f'bb_lower_{bb_window}'
        
        active_trade = None
        trade_id_counter = 0
        
        allowed_regimes = set(self.params.get('allowed_regimes', ['FLAT_LOW', 'FLAT_NORMAL']))
        
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            ts = row['ts']
            price = row['close_60s']
            regime = row['regime_id']
            bb_width = row[f'bb_width_{bb_window}']
            
            if active_trade:
                self._manage_trade(active_trade, row, col_mid)
                if active_trade.exit_ts:
                    self.trades.append(active_trade)
                    active_trade = None
                continue
                
            signal = "NONE"
            dist_to_mean = 0.0
            
            if price < row[col_lower]:
                signal = "LONG"
                dist_to_mean = (row[col_mid] - price) / price
            elif price > row[col_upper]:
                signal = "SHORT"
                dist_to_mean = (price - row[col_mid]) / price
                
            action = "WAIT"
            comment = ""
            
            if signal != "NONE":
                if regime not in allowed_regimes:
                    action = "REJECT_REGIME"
                    comment = f"Regime {regime} not allowed"
                
                elif bb_width < min_vol_atr:
                    action = "REJECT_VOL"
                    comment = f"BB Width {bb_width:.4f} < Min {min_vol_atr}"
                    
                elif dist_to_mean < (self.cost_basis * 1.5):
                    action = "REJECT_FEES"
                    comment = f"Exp PnL {dist_to_mean:.4f} < Costs {self.cost_basis*1.5:.4f}"
                    
                else:
                    action = "ENTER"
                    comment = "Valid Setup (1m)"
                    trade_id_counter += 1
                    active_trade = Trade(
                        id=trade_id_counter,
                        entry_ts=ts,
                        entry_price=price,
                        side=signal
                    )
            
            if debug or (signal != "NONE"):
                self.logs.append(DecisionLog(
                    ts=ts, price=price, signal=signal, regime=regime,
                    volatility=bb_width, dist_to_mean=dist_to_mean,
                    expected_pnl_pct=dist_to_mean, action=action, comment=comment
                ))
                
        return self._calculate_metrics()

    def _manage_trade(self, trade, row, col_mid):
        price = row['close_60s']
        mean = row[col_mid]
        
        sl_pct = self.params.get('sl_pct', 0.01)
        
        if trade.side == 'LONG':
            pnl_pct = (price - trade.entry_price) / trade.entry_price
            if price >= mean:
                self._close_trade(trade, price, row['ts'], "TAKE_PROFIT_MEAN")
                return
        else:
            pnl_pct = (trade.entry_price - price) / trade.entry_price
            if price <= mean:
                self._close_trade(trade, price, row['ts'], "TAKE_PROFIT_MEAN")
                return
                
        if pnl_pct <= -sl_pct:
            self._close_trade(trade, price, row['ts'], "STOP_LOSS")

    def _close_trade(self, trade, price, ts, reason):
        trade.exit_ts = ts
        trade.exit_price = price
        trade.reason = reason
        
        if trade.side == 'LONG':
            raw = (price - trade.entry_price) / trade.entry_price
        else:
            raw = (trade.entry_price - price) / trade.entry_price
            
        trade.pnl_net = (raw - self.cost_basis) * trade.size

    def _calculate_metrics(self):
        if not self.trades:
            return {'total_pnl': 0.0, 'calmar': 0.0, 'trades': 0, 'logs': self.logs}
            
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
            'calmar': calmar,
            'logs': self.logs
        }
