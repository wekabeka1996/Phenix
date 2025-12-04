"""
Regime Labeling for 5s Sniper

Classifies market state into:
- Trend: UP / DOWN / FLAT
- Volatility: HIGH / NORMAL / LOW
- Regime: Combined categorical (e.g., "UP_NORMAL")
"""

import pandas as pd
import numpy as np

def add_regime_labels(df: pd.DataFrame, 
                      trend_window_sec: int = 300,
                      vol_window_sec: int = 300,
                      bar_horizon_sec: int = 5) -> pd.DataFrame:
    """
    Add regime classification to features dataframe.
    
    Args:
        df: Features dataframe (must have 'close_1s')
        trend_window_sec: Window for trend detection (seconds)
        vol_window_sec: Window for volatility detection (seconds)
        bar_horizon_sec: Bar resolution (1, 5, or 10)
        
    Returns:
        DataFrame with added columns:
        - regime_trend: 'UP', 'DOWN', 'FLAT'
        - regime_vol: 'HIGH', 'NORMAL', 'LOW'
        - regime_id: Combined string (e.g., 'UP_NORMAL')
    """
    
    # Convert seconds to bars
    trend_bars = max(1, trend_window_sec // bar_horizon_sec)
    vol_bars = max(1, vol_window_sec // bar_horizon_sec)
    
    # --- Trend Detection ---
    # Use EMA slope or returns
    # Method: EMA(trend_window) slope
    ema_trend = df['close_1s'].ewm(span=trend_bars, adjust=False).mean()
    
    # Calculate slope (change over window)
    # Slope = (current - previous) / previous
    ema_slope = ema_trend.diff(periods=trend_bars) / (ema_trend.shift(trend_bars) + 1e-9)
    
    # Thresholds for UP/DOWN/FLAT
    # If slope > +0.5%, it's UP
    # If slope < -0.5%, it's DOWN
    # Otherwise FLAT
    TREND_UP_THRESHOLD = 0.005  # 0.5%
    TREND_DOWN_THRESHOLD = -0.005
    
    conditions_trend = [
        (ema_slope > TREND_UP_THRESHOLD),
        (ema_slope < TREND_DOWN_THRESHOLD)
    ]
    choices_trend = ['UP', 'DOWN']
    df['regime_trend'] = np.select(conditions_trend, choices_trend, default='FLAT')
    
    # --- Volatility Detection ---
    # Use ATR (Average True Range)
    # ATR = rolling average of (high - low)
    
    # For 5s/10s bars, high/low exist. For 1s, they might be close to close.
    if 'high_1s' in df.columns and 'low_1s' in df.columns:
        true_range = df['high_1s'] - df['low_1s']
    else:
        # Fallback: use close-to-close range
        true_range = df['close_1s'].diff().abs()
    
    atr = true_range.rolling(window=vol_bars, min_periods=1).mean()
    
    # Normalize ATR by price to get percentage volatility
    atr_pct = atr / (df['close_1s'] + 1e-9)
    
    # Thresholds for HIGH/NORMAL/LOW
    # Calculate rolling percentiles or fixed thresholds
    # Method: Use 70th and 30th percentile of ATR over a long window
    # Or use fixed thresholds
    
    # Fixed approach (simpler):
    # If ATR% > 0.3%, it's HIGH
    # If ATR% < 0.1%, it's LOW
    # Otherwise NORMAL
    
    VOL_HIGH_THRESHOLD = 0.003  # 0.3%
    VOL_LOW_THRESHOLD = 0.001   # 0.1%
    
    conditions_vol = [
        (atr_pct > VOL_HIGH_THRESHOLD),
        (atr_pct < VOL_LOW_THRESHOLD)
    ]
    choices_vol = ['HIGH', 'LOW']
    df['regime_vol'] = np.select(conditions_vol, choices_vol, default='NORMAL')
    
    # --- Combined Regime ---
    df['regime_id'] = df['regime_trend'] + '_' + df['regime_vol']
    
    return df

def get_all_regimes():
    """Return list of all possible regime combinations."""
    trends = ['UP', 'DOWN', 'FLAT']
    vols = ['HIGH', 'NORMAL', 'LOW']
    return [f"{t}_{v}" for t in trends for v in vols]

if __name__ == "__main__":
    # Test on synthetic data
    np.random.seed(42)
    ts = pd.date_range('2024-01-01', periods=1000, freq='5s')
    
    # Synthetic price with trend and noise
    trend = np.linspace(100, 110, 1000)
    noise = np.random.randn(1000) * 0.5
    price = trend + noise
    
    df_test = pd.DataFrame({
        'ts': ts,
        'close_1s': price,
        'high_1s': price + np.abs(noise) * 0.5,
        'low_1s': price - np.abs(noise) * 0.5
    })
    
    df_test = add_regime_labels(df_test, trend_window_sec=100, vol_window_sec=100, bar_horizon_sec=5)
    
    print("Regime Distribution:")
    print(df_test['regime_id'].value_counts())
    print("\nSample:")
    print(df_test[['ts', 'close_1s', 'regime_trend', 'regime_vol', 'regime_id']].tail(10))
