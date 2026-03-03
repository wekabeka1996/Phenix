import numpy as np
import pandas as pd
from tools.regime_calibration.oracle import compute_oracle_labels

def test_oracle_trend():
    df = pd.DataFrame({
        'symbol': ['BTC'] * 15,
        'open': np.linspace(100, 200, 15),
        'high': np.linspace(105, 205, 15),
        'low': np.linspace(95, 195, 15),
        'close': np.linspace(100, 200, 15),
    })
    labels = compute_oracle_labels(
        df, 
        horizon_bars=5, 
        vol_high_bps=10000, 
        vol_low_bps=0, 
        trend_ret_bps=100, 
        trend_persist=0.5, 
        flat_ret_bps=50, 
        mr_flip_rate=0.5
    )
    assert 'TREND_UP' in labels.values
    
def test_oracle_flat_mr():
    closes = [100, 101, 99, 101, 99, 101, 99, 101, 99, 101]
    df = pd.DataFrame({
        'symbol': ['BTC'] * 10,
        'open': closes,
        'high': closes,
        'low': closes,
        'close': closes,
    })
    labels = compute_oracle_labels(
        df, 
        horizon_bars=4, 
        vol_high_bps=10000, 
        vol_low_bps=0, 
        trend_ret_bps=500, 
        trend_persist=0.5, 
        flat_ret_bps=50, 
        mr_flip_rate=0.5
    )
    assert 'MEAN_REVERSION' in labels.values

def test_oracle_high_vol():
    closes = [100, 105, 95, 110, 90, 115]
    df = pd.DataFrame({
        'symbol': ['SOL'] * 6,
        'open': closes,
        'high': closes,
        'low': closes,
        'close': closes,
    })
    labels = compute_oracle_labels(
        df,
        horizon_bars=2,
        vol_high_bps=200,  # low threshold for test
        vol_low_bps=0,
        trend_ret_bps=500,
        trend_persist=0.8,
        flat_ret_bps=50,
        mr_flip_rate=0.5
    )
    assert 'HIGH_VOLATILITY' in labels.values
