"""
Feature Engineering for Mean Reversion Strategy
"""
import pandas as pd
import numpy as np
from apps.research.momentum_backtest.features_builder_multiscale import add_regime_labels

def compute_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def compute_bollinger_bands(series, window=20, num_std=2):
    sma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, lower, sma

def build_mean_reversion_features(df_golden: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Build features for Mean Reversion strategy.
    Input: Golden 1s dataframe (resampled to 5s inside or passed as 5s).
    """
    # Assuming input is already resampled to 5s if needed, or we resample here.
    # For simplicity, let's assume we work with 5s bars.
    
    df = df_golden.copy()
    
    # Ensure we have 5s bars (if input is 1s, resample)
    # But to keep it compatible with existing pipeline,    # 0. Regime Labeling (Requires close_1s, high_1s, low_1s)
    # We do this BEFORE renaming because add_regime_labels expects _1s suffixes
    print(f"  Computing Regime Labels...")
    df = add_regime_labels(df, trend_window_sec=300, vol_window_sec=300, bar_horizon_sec=5)

    # If df is 5s, we might need to map columns.
    # The 5s golden file might still have _1s suffixes.
    if 'close_1s' in df.columns and 'close_5s' not in df.columns:
        df.rename(columns={
            'open_1s': 'open_5s',
            'high_1s': 'high_5s',
            'low_1s': 'low_5s',
            'close_1s': 'close_5s',
            'vol_1s': 'vol_5s'
        }, inplace=True)
    
    # 1. Bollinger Bands (Multiple windows)
    # Window 20 (5s * 20 = 100s)
    # Window 60 (5s * 60 = 300s = 5m)
    
    windows = [20, 60, 120]
    for w in windows:
        upper, lower, sma = compute_bollinger_bands(df['close_5s'], window=w, num_std=2.0)
        df[f'bb_upper_{w}'] = upper
        df[f'bb_lower_{w}'] = lower
        df[f'bb_mid_{w}'] = sma
        df[f'bb_width_{w}'] = (upper - lower) / (sma + 1e-9)
        # %B indicator: (Price - Lower) / (Upper - Lower)
        df[f'bb_pct_b_{w}'] = (df['close_5s'] - lower) / (upper - lower + 1e-9)
        
        # Distance from SMA (z-score like)
        df[f'dist_sma_{w}'] = (df['close_5s'] - sma) / (df['close_5s'].rolling(window=w).std() + 1e-9)

    # 2. RSI
    df['rsi_14'] = compute_rsi(df['close_5s'], window=14)
    df['rsi_60'] = compute_rsi(df['close_5s'], window=60)
    
    # 3. Regime Labeling (Done at start)
    
    return df.dropna()
