"""
Optuna Runner for 1m Mean Reversion
"""
import optuna
import pandas as pd
import sys
import argparse
import json

sys.path.insert(0, ".")

from apps.research.new_alpha_mean_reversion.backtest_engine_1m import BacktestEngine1m
from apps.research.momentum_backtest.config import get_processed_file_path

def load_data(symbol, year, month):
    feat_path = get_processed_file_path(f"{symbol}-features-mr-1m-{year}-{month}.csv", symbol, year, month)
    df = pd.read_csv(feat_path)
    df['ts'] = pd.to_datetime(df['ts'])
    return df

def objective(trial, df):
    bb_window = trial.suggest_categorical('bb_window', [20, 60, 120])
    min_vol_atr = trial.suggest_float('min_vol_atr', 0.001, 0.01, step=0.001)
    sl_pct = trial.suggest_float('sl_pct', 0.005, 0.02)
    
    params = {
        'bb_window': bb_window,
        'min_vol_atr': min_vol_atr,
        'sl_pct': sl_pct,
        'allowed_regimes': ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']
    }
    
    engine = BacktestEngine1m(df, params)
    metrics = engine.run()
    
    if metrics['trades'] < 30:  # Lower threshold for 1m
        return -100.0
        
    if metrics['total_pnl'] < 0:
        return metrics['total_pnl']
        
    score = metrics['calmar'] * (metrics['trades'] ** 0.5)
    return score

def run(symbol, year, month, n_trials=50):
    df = load_data(symbol, year, month)
    
    study_name = f"alpha_1m_{symbol}_{year}_{month}"
    storage = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(study_name=study_name, storage=storage, direction="maximize", load_if_exists=True)
    study.optimize(lambda t: objective(t, df), n_trials=n_trials)
    
    print("Best Params:", study.best_params)
    print("Best Value:", study.best_value)
    
    best_params = study.best_params
    best_params['allowed_regimes'] = ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']
    engine = BacktestEngine1m(df, best_params)
    metrics = engine.run(debug=True)
    
    logs = metrics['logs']
    df_logs = pd.DataFrame([l.__dict__ for l in logs])
    df_logs.to_csv(f"decision_logs_1m_{symbol}.csv", index=False)
    print(f"Saved {len(df_logs)} decision logs.")
    print(f"Final PnL: {metrics['total_pnl']:.2f}, Trades: {metrics['trades']}")
    
    with open(f"best_metrics_1m_{symbol}.json", "w") as f:
        json.dump({'params': study.best_params, 'value': study.best_value, 'metrics': {
            'pnl': metrics['total_pnl'],
            'trades': metrics['trades'],
            'win_rate': metrics['win_rate'],
            'calmar': metrics['calmar']
        }}, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=50)
    args = parser.parse_args()
    
    run(args.symbol, args.year, args.month, args.n_trials)
