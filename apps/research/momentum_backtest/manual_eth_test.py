"""
Manual ETH Backtest
"""
import pandas as pd
import numpy as np
import sys
from pathlib import Path
import calendar

# Add project root to path
sys.path.insert(0, ".")

from apps.research.momentum_backtest.backtest_engine_multiscale import BacktestEngineMultiscale
from apps.research.momentum_backtest.config import get_processed_file_path, GOLDEN_DATASET_TEMPLATE, FEATURES_DATASET_TEMPLATE
from apps.research.momentum_backtest.optuna_runner_regime import prepare_features, load_datasets

def debug():
    symbol = "ETHUSDT"
    year = "2024"
    month = "01"
    
    print(f"Loading datasets for {symbol} {year}-{month}...")
    datasets = load_datasets(symbol, year, month)
    df_feat_raw = datasets['features_h5']
    df_golden = datasets['golden']
    
    print(f"Features raw: {len(df_feat_raw)} rows")
    print(f"Golden raw: {len(df_golden)} rows")
    
    # Filter for last week
    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    end_ts = pd.Timestamp(f"{year}-{month}-{last_day}") + pd.Timedelta(days=1)
    start_ts = end_ts - pd.Timedelta(days=7)
    
    print(f"Filtering: {start_ts} to {end_ts}")
    
    mask = (df_feat_raw['ts'] >= start_ts) & (df_feat_raw['ts'] < end_ts)
    df_test_raw = df_feat_raw[mask].copy().reset_index(drop=True)
    
    print(f"Test features: {len(df_test_raw)} rows")
    
    if len(df_test_raw) == 0:
        print("ERROR: No test data!")
        return

    # Analyze Regimes
    print("\nRegime Distribution in Test Data:")
    print(df_test_raw['regime_id'].value_counts())
    
    # Setup params (Loose)
    params = {
        'bar_horizon_sec': 5,
        'tfi_window_sec': 20,
        'depth_window_sec': 20,
        'ema_short_sec': 60,
        'ema_long_sec': 300,
        'vol_window_sec': 300,
        
        # Weights (balanced)
        'w_tfi': 0.5, 'w_tob': 0.5, 'w_bs': 0.5, 'w_bl': 0.5, 'w_macro': 0.5,
        'w_delta_price': 0.5, 'w_volume_spike': 0.5, 'w_volatility_state': 0.5, 'w_depth_imbalance': 0.5,
        
        # Threshold (very low)
        'threshold': 0.05,
        
        # Gates (very loose)
        'depth_imbalance_phi_min': 0.1,
        'tob_phi_min': 0.1,
        'ema_bias_long_phi_min': 0.1,
        'vol_state_phi_min': 0.0,
        'vol_state_phi_max': 1.0,
        
        # Risk
        'sl_pct': 0.01,
        'sl_tp_ratio': 2.0,
        'max_holding_secs': 600,
        'funding_threshold_long': 0.1, # Disable veto
        
        # Regimes (ALLOW ALL)
        'regime_allowlist': list(df_test_raw['regime_id'].unique())
    }
    
    print(f"\nRunning backtest with ALLOW ALL regimes: {params['regime_allowlist']}")
    
    # Prepare features (map columns)
    df_features = prepare_features(df_test_raw, params)
    
    engine = BacktestEngineMultiscale(df_features, df_golden, params)
    metrics = engine.run()
    
    print("\nBacktest Results:")
    print(f"Trades: {len(metrics['trades'])}")
    print(f"PnL: {metrics['total_pnl_usd']}")
    
    if len(metrics['trades']) == 0:
        print("\nDEBUGGING SIGNALS:")
        # Check why no signals
        print("Checking feature stats:")
        cols = ['tfi_phi', 'depth_imbalance_phi', 'tob_phi', 'ema_bias_short_phi', 'ema_bias_long_phi']
        print(df_features[cols].describe())

if __name__ == "__main__":
    debug()
