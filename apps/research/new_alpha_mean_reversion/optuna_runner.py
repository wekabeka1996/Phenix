"""
Optuna Runner for Mean Reversion Strategy
"""
import optuna
import pandas as pd
import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.new_alpha_mean_reversion.config import DATA_DIR, FEATURES_DATASET_TEMPLATE, GOLDEN_DATASET_TEMPLATE
from apps.research.new_alpha_mean_reversion.backtest_engine import BacktestEngineMeanReversion
from apps.research.momentum_backtest.config import get_processed_file_path

def load_datasets(symbol, year, month):
    # Load Features
    feat_file = FEATURES_DATASET_TEMPLATE.replace("features", "features-mr") # Ensure name matches features.py output
    # Wait, features.py needs to run first. We assume data exists.
    # Actually, let's use the standard naming convention from features.py
    # In features.py we didn't specify save logic, we need a builder script.
    # For now, let's assume we run a builder script first.
    
    # Let's adjust this: The runner will assume features are built.
    feat_path = get_processed_file_path(f"{symbol}-features-mr-{year}-{month}.csv", symbol, year, month)
    golden_path = get_processed_file_path(f"{symbol}-5s-golden-{year}-{month}.csv", symbol, year, month)
    
    if not feat_path.exists():
        raise FileNotFoundError(f"Features not found: {feat_path}")
        
    df_features = pd.read_csv(feat_path)
    df_features['ts'] = pd.to_datetime(df_features['ts'])
    
    df_golden = pd.read_csv(golden_path)
    df_golden['ts'] = pd.to_datetime(df_golden['ts'])
    
    return df_features, df_golden

def objective(trial, df_features, df_golden):
    # Search Space
    bb_window = trial.suggest_categorical('bb_window', [20, 60, 120])
    # bb_entry_std: how far outside bands? 2.0 = touch, 2.5 = extreme
    bb_entry_std = trial.suggest_float('bb_entry_std', 2.0, 3.5, step=0.1)
    
    rsi_window = trial.suggest_categorical('rsi_window', [14, 60])
    rsi_threshold = trial.suggest_int('rsi_threshold', 5, 30) # Oversold < 30 (e.g. 20), Overbought > 70 (e.g. 80)
    
    sl_pct = trial.suggest_float('sl_pct', 0.002, 0.02, log=True)
    tp_pct = trial.suggest_float('tp_pct', 0.002, 0.02, log=True)
    
    # Regimes: Allow Flat Low/Normal. Maybe Flat High?
    allow_flat_high = trial.suggest_categorical('allow_flat_high', [0, 1])
    allowed_regimes = ['FLAT_LOW', 'FLAT_NORMAL']
    if allow_flat_high:
        allowed_regimes.append('FLAT_HIGH')
        
    params = {
        'bb_window': bb_window,
        'bb_entry_std': bb_entry_std,
        'rsi_window': rsi_window,
        'rsi_oversold': rsi_threshold,
        'rsi_overbought': 100 - rsi_threshold,
        'sl_pct': sl_pct,
        'tp_pct': tp_pct,
        'allowed_regimes': allowed_regimes,
        'max_holding_sec': 1800 # 30 mins max
    }
    
    engine = BacktestEngineMeanReversion(df_features, df_golden, params)
    metrics = engine.run()
    
    # Objective: Maximize PnL, but punish low trades
    total_trades = len(metrics['trades'])
    pnl = metrics['total_pnl_usd']
    
    if total_trades < 50:
        return -10000.0 # Penalty
        
    return pnl

def run_optimization(symbol, year, month, n_trials=100):
    print(f"Loading data for {symbol}...")
    try:
        df_features, df_golden = load_datasets(symbol, year, month)
    except FileNotFoundError as e:
        print(e)
        print("Please run features builder first.")
        return

    study_name = f"new_alpha_mr_{symbol}_{year}_{month}"
    storage_name = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_name,
        direction="maximize",
        load_if_exists=True
    )
    
    print(f"Starting optimization ({n_trials} trials)...")
    study.optimize(lambda t: objective(t, df_features, df_golden), n_trials=n_trials)
    
    print("Best params:", study.best_params)
    print("Best value:", study.best_value)
    
    # Save best metrics
    best_metrics = {
        'params': study.best_params,
        'value': study.best_value,
        'symbol': symbol,
        'period': f"{year}-{month}"
    }
    
    with open(f"best_metrics_mr_{symbol}.json", "w") as f:
        json.dump(best_metrics, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BNBUSDT")
    parser.add_argument("--year", type=str, default="2024")
    parser.add_argument("--month", type=str, default="03")
    parser.add_argument("--n-trials", type=int, default=100)
    args = parser.parse_args()
    
    run_optimization(args.symbol, args.year, args.month, args.n_trials)
