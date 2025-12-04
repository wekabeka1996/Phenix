"""
Optuna Runner V2: Smart Scalping Optimization
"""
import optuna
import pandas as pd
import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.new_alpha_mean_reversion.config import FEATURES_DATASET_TEMPLATE, GOLDEN_DATASET_TEMPLATE
from apps.research.new_alpha_mean_reversion.backtest_engine_v2 import BacktestEngineSmartScalping
from apps.research.momentum_backtest.config import get_processed_file_path

def load_data(symbol, year, month):
    feat_path = get_processed_file_path(f"{symbol}-features-mr-{year}-{month}.csv", symbol, year, month)
    df = pd.read_csv(feat_path)
    df['ts'] = pd.to_datetime(df['ts'])
    return df

def objective(trial, df):
    # Params
    bb_window = trial.suggest_categorical('bb_window', [20, 60, 120])
    # Min volatility (ATR/Width) required to enter. 
    # 0.0005 = 0.05% width. 0.002 = 0.2% width.
    min_vol_atr = trial.suggest_float('min_vol_atr', 0.0005, 0.003, step=0.0005)
    
    sl_pct = trial.suggest_float('sl_pct', 0.002, 0.01)
    
    params = {
        'bb_window': bb_window,
        'min_vol_atr': min_vol_atr,
        'sl_pct': sl_pct,
        'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH'] # Let's try all Flats
    }
    
    engine = BacktestEngineSmartScalping(df, params)
    metrics = engine.run()
    
    # Objective: Calmar Ratio * log(Trades)
    # We want stability AND volume.
    
    if metrics['trades'] < 50:
        return -100.0 # Penalty
        
    # If negative PnL, return PnL directly (scaled down)
    if metrics['total_pnl'] < 0:
        return metrics['total_pnl']
        
    # If positive, boost by stability
    score = metrics['calmar'] * (metrics['trades'] ** 0.5)
    return score

def run(symbol, year, month, n_trials=100):
    df = load_data(symbol, year, month)
    
    study_name = f"alpha_v2_{symbol}_{year}_{month}"
    storage = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(study_name=study_name, storage=storage, direction="maximize", load_if_exists=True)
    study.optimize(lambda t: objective(t, df), n_trials=n_trials)
    
    print("Best Params:", study.best_params)
    print("Best Value:", study.best_value)
    
    # Run best to get logs
    best_params = study.best_params
    best_params['allowed_regimes'] = ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']
    engine = BacktestEngineSmartScalping(df, best_params)
    metrics = engine.run(debug=True)
    
    # Save logs
    logs = metrics['logs']
    df_logs = pd.DataFrame([l.__dict__ for l in logs])
    df_logs.to_csv(f"decision_logs_{symbol}.csv", index=False)
    print(f"Saved {len(df_logs)} decision logs.")
    print(f"Final PnL: {metrics['total_pnl']:.2f}, Trades: {metrics['trades']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=50)
    args = parser.parse_args()
    
    run(args.symbol, args.year, args.month, args.n_trials)
