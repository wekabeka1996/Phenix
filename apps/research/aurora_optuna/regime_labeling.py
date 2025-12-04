"""
Regime Labeling for Aurora Backtest
Based on apps/reference/domains/regime_detector/regime_detector.py
"""
import pandas as pd
import numpy as np
from decimal import Decimal

def get_col_name(df, base_name):
    """Get column name with correct suffix (_1s, _5s, _60s, _180s, _300s)"""
    for suffix in ['_300s', '_180s', '_60s', '_1s', '_5s']:
        if f'{base_name}{suffix}' in df.columns:
            return f'{base_name}{suffix}'
    return base_name  # Fallback to no suffix

def compute_sma(series, period):
    """Simple Moving Average"""
    return series.rolling(window=period).mean()

def compute_atr(df, period=14):
    """Average True Range"""
    high_col = get_col_name(df, 'high')
    low_col = get_col_name(df, 'low')
    close_col = get_col_name(df, 'close')
    
    # True Range: max(high-low, abs(high-prev_close), abs(low-prev_close))
    tr1 = df[high_col] - df[low_col]
    tr2 = (df[high_col] - df[close_col].shift()).abs()
    tr3 = (df[low_col] - df[close_col].shift()).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr

def label_regime(df, config):
    """
    Label market regime based on Aurora regime_detector logic
    
    Priority:
    1. HIGH_VOLATILITY / LOW_VOLATILITY (if enabled)
    2. MEAN_REVERSION
    3. TREND_UP / TREND_DOWN
    4. UNCERTAIN (default)
    """
    close_col = get_col_name(df, 'close')
    
    # Parameters
    sma_short_period = config.get('sma_short_period', 10)
    sma_long_period = config.get('sma_long_period', 50)
    
    volatility_enabled = config.get('volatility_enabled', True)
    atr_period = config.get('atr_period', 14)
    atr_sma_length = config.get('atr_sma_length', 100)
    high_vol_threshold = config.get('high_vol_threshold', 2.0)
    low_vol_threshold = config.get('low_vol_threshold', 0.5)
    
    mean_rev_threshold = config.get('mean_rev_threshold', 0.005)
    
    # Compute indicators
    price = df[close_col]
    sma_short = compute_sma(price, sma_short_period)
    sma_long = compute_sma(price, sma_long_period)
    
    # ATR for volatility detection
    if volatility_enabled:
        atr = compute_atr(df, atr_period)
        atr_sma = atr.rolling(window=atr_sma_length).mean()
        volatility_ratio = atr / (atr_sma + 1e-9)
    else:
        volatility_ratio = pd.Series(1.0, index=df.index)
    
    # Initialize regime column
    regime = pd.Series('UNCERTAIN', index=df.index)
    
    # Priority 1: Volatility Regimes
    if volatility_enabled:
        regime = regime.where(~(volatility_ratio > high_vol_threshold), 'HIGH_VOLATILITY')
        regime = regime.where(~(volatility_ratio < low_vol_threshold), 'LOW_VOLATILITY')
    
    # Priority 2: Mean Reversion
    sma_spread = (sma_short - sma_long).abs() / (sma_long + 1e-9)
    price_dev_short = (price - sma_short).abs() / (sma_short + 1e-9)
    price_dev_long = (price - sma_long).abs() / (sma_long + 1e-9)
    
    mean_rev_mask = (
        (regime == 'UNCERTAIN') &
        (sma_spread < mean_rev_threshold) &
        (price_dev_short < mean_rev_threshold) &
        (price_dev_long < mean_rev_threshold)
    )
    regime = regime.where(~mean_rev_mask, 'MEAN_REVERSION')
    
    # Priority 3: Trend Detection
    trend_up_mask = (
        (regime == 'UNCERTAIN') &
        (sma_short > sma_long) &
        (price > sma_short)
    )
    regime = regime.where(~trend_up_mask, 'TREND_UP')
    
    trend_down_mask = (
        (regime == 'UNCERTAIN') &
        (sma_short < sma_long) &
        (price < sma_short)
    )
    regime = regime.where(~trend_down_mask, 'TREND_DOWN')
    
    return regime

def add_regime_labels_aurora(df, config=None):
    """Add regime labels to dataframe"""
    if config is None:
        config = {
            'sma_short_period': 10,
            'sma_long_period': 50,
            'volatility_enabled': True,
            'atr_period': 14,
            'atr_sma_length': 100,
            'high_vol_threshold': 2.0,
            'low_vol_threshold': 0.5,
            'mean_rev_threshold': 0.005
        }
    
    df['regime'] = label_regime(df, config)
    return df
