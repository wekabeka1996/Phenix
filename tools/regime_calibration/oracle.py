import numpy as np
import pandas as pd

def compute_oracle_labels(
    df: pd.DataFrame,
    horizon_bars: int,
    vol_high_bps: float = 300.0,
    vol_low_bps: float = 120.0,
    trend_ret_bps: float = 150.0,
    trend_persist: float = 0.65,
    flat_ret_bps: float = 80.0,
    mr_flip_rate: float = 0.60
) -> pd.Series:
    """
    Computes ground truth (oracle) regime labels looking forward `horizon_bars`.
    Returns a pandas Series of strings (e.g. 'HIGH_VOLATILITY', 'TREND_UP', etc.)
    aligned with df index.
    
    df must have ['symbol', 'open', 'high', 'low', 'close'] and be sorted by time per symbol.
    """
    labels = np.full(len(df), 'UNCERTAIN', dtype=object)
    
    if len(df) < horizon_bars + 1:
        return pd.Series(labels, index=df.index)
        
    for symbol, group in df.groupby('symbol'):
        idxs = group.index.to_numpy()
        close = group['close'].to_numpy(dtype=float)
        high = group['high'].to_numpy(dtype=float)
        low = group['low'].to_numpy(dtype=float)
        
        n = len(group)
        for i in range(n - horizon_bars):
            c0 = close[i]
            if c0 <= 0 or np.isnan(c0):
                continue
                
            c_horizon = close[i:i+horizon_bars]
            h_horizon = high[i:i+horizon_bars]
            l_horizon = low[i:i+horizon_bars]
            
            max_h = np.nanmax(h_horizon)
            min_l = np.nanmin(l_horizon)
            
            future_range_bps = (max_h - min_l) / c0 * 10000.0
            fwd_ret_bps = (close[i+horizon_bars] - c0) / c0 * 10000.0
            
            # Volatility check first
            if future_range_bps >= vol_high_bps:
                labels[idxs[i]] = 'HIGH_VOLATILITY'
                continue
            elif future_range_bps <= vol_low_bps:
                labels[idxs[i]] = 'LOW_VOLATILITY'
                continue
                
            # Trend check
            ret_i = np.diff(c_horizon)
            valid_ret = ret_i[~np.isnan(ret_i)]
            if len(valid_ret) > 0:
                fwd_sign = np.sign(fwd_ret_bps)
                if fwd_sign == 0:
                    fwd_sign = 1.0
                direction_persistence = np.mean(np.sign(valid_ret) == fwd_sign)
            else:
                direction_persistence = 0.0
                
            if abs(fwd_ret_bps) >= trend_ret_bps and direction_persistence >= trend_persist:
                labels[idxs[i]] = 'TREND_UP' if fwd_ret_bps > 0 else 'TREND_DOWN'
                continue
                
            # MR check
            if len(valid_ret) > 1:
                flip_rate = np.mean(np.sign(valid_ret[1:]) != np.sign(valid_ret[:-1]))
            else:
                flip_rate = 0.0
                
            if abs(fwd_ret_bps) <= flat_ret_bps and flip_rate >= mr_flip_rate:
                labels[idxs[i]] = 'MEAN_REVERSION'
                continue
                
    return pd.Series(labels, index=df.index)
