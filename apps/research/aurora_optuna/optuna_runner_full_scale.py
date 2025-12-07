import optuna
import pandas as pd
import numpy as np
import argparse
import os
import json
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, ".")

from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

# Asset-Specific Search Spaces (derived from new_alpha analysis)
SEARCH_SPACES = {
    "BTCUSDT": {
        "bb_window": [20, 40],
        "min_vol_atr": (0.005, 0.015),
        "sl_pct": (0.005, 0.015),
    },
    "ETHUSDT": {
        "bb_window": [60, 120, 180],
        "min_vol_atr": (0.015, 0.040),
        "sl_pct": (0.020, 0.050),
    },
    "XRPUSDT": {
        "bb_window": [20, 40],
        "min_vol_atr": (0.005, 0.020),
        "sl_pct": (0.010, 0.025),
    },
    "SOLUSDT": {
        "bb_window": [40, 60, 120],
        "min_vol_atr": (0.015, 0.030),
        "sl_pct": (0.010, 0.030),
    },
    "DOGEUSDT": {
        "bb_window": [20, 40],
        "min_vol_atr": (0.005, 0.020),
        "sl_pct": (0.010, 0.030),
    }
}

def load_data(symbol, year, month, timeframe='1m'):
    """Load data from disk using config paths"""
    template = FEATURES_DATASET_TEMPLATE
    if timeframe == '3m':
        template = FEATURES_DATASET_TEMPLATE_3M
    elif timeframe == '5m':
        template = FEATURES_DATASET_TEMPLATE_5M
        
    feat_path = get_data_path(template, symbol, year, month)
    print(f"Loading data from {feat_path}...")
    
    if not os.path.exists(feat_path):
        raise FileNotFoundError(f"Could not find data file: {feat_path}")
        
    df = pd.read_csv(feat_path)
    df['ts'] = pd.to_datetime(df['ts'])

    # Load BTC data for macro features (optional, but good for correlation)
    btc_df = None
    if symbol != "BTCUSDT":
        btc_path = get_data_path(template, "BTCUSDT", year, month)
        if os.path.exists(btc_path):
            btc_df = pd.read_csv(btc_path)
            btc_df['ts'] = pd.to_datetime(btc_df['ts'])
            
            # Ensure column naming
            col_name = 'close_1s'
            if timeframe == '3m': col_name = 'close_180s'
            if timeframe == '5m': col_name = 'close_300s'
            
            if col_name in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df[col_name]
    elif symbol == "BTCUSDT":
        btc_df = df.copy()
        col_name = 'close_1s'
        if timeframe == '3m': col_name = 'close_180s'
        if timeframe == '5m': col_name = 'close_300s'
        if col_name in btc_df.columns:
            btc_df['btc_close_1s'] = btc_df[col_name]
    
    return df, btc_df

def objective(trial, df_features, btc_df, symbol, bar_seconds=60):
    # Get asset-specific ranges
    ranges = SEARCH_SPACES.get(symbol, SEARCH_SPACES["BTCUSDT"]) # Default to BTC if unknown
    
    # --- Mean Reversion Params ---
    bb_window = trial.suggest_categorical('bb_window', ranges['bb_window'])
    bb_std_dev = trial.suggest_float('bb_std_dev', 1.5, 3.0, step=0.1)
    min_vol_atr = trial.suggest_float('min_vol_atr', ranges['min_vol_atr'][0], ranges['min_vol_atr'][1])
    
    # --- Risk Params ---
    sl_pct = trial.suggest_float('sl_pct', ranges['sl_pct'][0], ranges['sl_pct'][1])
    max_hold_sec = trial.suggest_int('max_hold_sec', 60, 7200, step=60) # Up to 2 hours
    
    # --- Phase 3+ Execution Params ---
    tp_low_ratio = trial.suggest_float('tp_low_ratio', 0.3, 0.8)
    tp_high_ratio = trial.suggest_float('tp_high_ratio', 0.8, 2.5) # Extended upper range
    partial_exit_pct = trial.suggest_float('partial_exit_pct', 0.3, 0.8)
    
    trailing_stop_activation_pct = trial.suggest_float('trailing_stop_activation_pct', 0.005, 0.05)
    trailing_stop_distance_pct = trial.suggest_float('trailing_stop_distance_pct', 0.002, 0.02)
    
    cooldown_sec = trial.suggest_int('cooldown_sec', 0, 300, step=15)
    
    # Regime Selection - Use ACTUAL regime values from data, not the FLAT_* ones
    # Data has: MEAN_REVERSION (most common), HIGH_VOLATILITY, TREND_UP, TREND_DOWN, LOW_VOLATILITY, UNCERTAIN
    allowed_regimes = ['MEAN_REVERSION', 'LOW_VOLATILITY', 'UNCERTAIN']  # Best for mean reversion strategy
    
    params = {
        'bb_window': bb_window,
        'bb_std_dev': bb_std_dev,
        'min_vol_atr': min_vol_atr,
        'sl_pct': sl_pct,
        'max_hold_sec': max_hold_sec,
        'tp_low_ratio': tp_low_ratio,
        'tp_high_ratio': tp_high_ratio,
        'partial_exit_pct': partial_exit_pct,
        'trailing_stop_activation_pct': trailing_stop_activation_pct,
        'trailing_stop_distance_pct': trailing_stop_distance_pct,
        'cooldown_sec': cooldown_sec,
        'allowed_regimes': allowed_regimes
    }
    
    # Rebuild features with new params (BB depends on window)
    # Note: We pass params to build_aurora_features, which now handles BB calc
    df_trial = build_aurora_features(df_features, btc_df, params, bar_seconds=bar_seconds)
    
    # Run Backtest
    engine = BacktestEngineAurora(df_trial, params, strategy_mode='mean_reversion')
    metrics = engine.run()
    
    # Objective: Maximize Total PnL
    # Penalty for too few trades to avoid overfitting to noise
    if metrics['trades'] < 30:
        return -1000.0
        
    return metrics['total_pnl']

def run_optimization(symbol, year, month, n_trials=3000, timeframe='1m'):
    print(f"Starting optimization for {symbol}...")
    
    # Load Data
    try:
        df, btc_df = load_data(symbol, year, month, timeframe)
    except Exception as e:
        print(f"Error loading data for {symbol}: {e}")
        return

    bar_seconds = 60
    if timeframe == '3m':
        bar_seconds = 180
    elif timeframe == '5m':
        bar_seconds = 300
        
    # Create Study
    study_name = f"aurora_full_{symbol}_{year}_{month}"
    storage = f"sqlite:///aurora_full_optimization.db"
    
    study = optuna.create_study(
        study_name=study_name, 
        storage=storage, 
        direction="maximize", 
        load_if_exists=True
    )
    
    print(f"Running {n_trials} trials for {symbol}...")
    study.optimize(
        lambda t: objective(t, df, btc_df, symbol, bar_seconds), 
        n_trials=n_trials,
        n_jobs=1 # Sequential to avoid DB locks, or use >1 if using proper DB
    )
    
    print(f"Best Params for {symbol}:", study.best_params)
    print(f"Best Value: {study.best_value}")
    
    # Save Results
    best_params = study.best_params
    # Use CORRECT regime values (same as in objective function)
    best_params['allowed_regimes'] = ['MEAN_REVERSION', 'LOW_VOLATILITY', 'UNCERTAIN']
    
    # Re-run to get full metrics
    df_final = build_aurora_features(df, btc_df, best_params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_final, best_params, strategy_mode='mean_reversion')
    metrics = engine.run()
    
    result_file = f"best_aurora_full_{symbol}.json"
    with open(result_file, "w") as f:
        json.dump({
            'symbol': symbol,
            'params': best_params, 
            'value': study.best_value, 
            'metrics': metrics
        }, f, indent=2)
        
    print(f"Saved results to {result_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT"])
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=3000)
    parser.add_argument("--timeframe", type=str, default="1m")
    
    args = parser.parse_args()
    
    for symbol in args.symbols:
        run_optimization(symbol, args.year, args.month, args.n_trials, args.timeframe)
