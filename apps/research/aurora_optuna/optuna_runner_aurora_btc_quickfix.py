"""
Aurora BTC-Specific Optuna Runner (Quick Fix)
==============================================
Key changes for BTC characteristics:
- Wider SL (2.5-4%)
- Longer holds (20-40 min)
- Lower signal threshold
- Include MEAN_REVERSION regime
- Larger position sizes
"""
import optuna
import pandas as pd
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE_5M

SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"
YEAR = "2024"
MONTH = "01"
N_TRIALS = 3000

def objective_btc_quick_fix(trial, df, btc_df, base_params, bar_seconds):
    """BTC-specific optimization with adjusted ranges"""
    params = base_params.copy()
    
    # BTC-SPECIFIC: Wider SL range
    params['sl_pct'] = trial.suggest_float('sl_pct', 0.025, 0.045, step=0.005)
    
    # BTC-SPECIFIC: Longer holding time
    params['max_hold_sec'] = trial.suggest_int('max_hold_sec', 1200, 2400, step=300)
    
    # BTC-SPECIFIC: Lower threshold (easier entries)
    params['signal_threshold'] = trial.suggest_float('signal_threshold', 0.12, 0.25, step=0.02)
    
    # BTC-SPECIFIC: Larger position size
    params['position_size'] = trial.suggest_float('position_size', 1200, 1800, step=100)
    
    # BTC-SPECIFIC: Include MEAN_REVERSION
    params['allowed_regimes'] = [
        'MEAN_REVERSION',  # 66% of data!
        'LOW_VOLATILITY',
        'TREND_UP',
        'TREND_DOWN'
    ]
    
    # Phase 3 params (keep optimizing)
    params['side_bias_window_sec'] = trial.suggest_int('side_bias_window_sec', 60, 600, step=60)
    params['side_bias_penalty_factor'] = trial.suggest_float('side_bias_penalty_factor', 0.0, 0.5, step=0.1)
    
    params['regime_threshold_high_vol'] = trial.suggest_float('regime_threshold_high_vol', 1.5, 2.5, step=0.1)
    params['regime_threshold_low_vol'] = trial.suggest_float('regime_threshold_low_vol', 0.5, 0.9, step=0.05)
    params['regime_threshold_trend'] = trial.suggest_float('regime_threshold_trend', 0.7, 1.1, step=0.05)
    
    # BTC-SPECIFIC: Less aggressive sizing in high vol
    params['sizing_high_vol'] = trial.suggest_float('sizing_high_vol', 0.3, 0.8, step=0.1)
    params['sizing_low_vol'] = trial.suggest_float('sizing_low_vol', 1.0, 1.6, step=0.1)
    params['sizing_mean_rev'] = trial.suggest_float('sizing_mean_rev', 0.8, 1.4, step=0.1)
    
    # EMA Clamp (BTC needs wider range)
    ema_clamp = trial.suggest_float('ema_clamp_abs', 0.01, 0.06, step=0.005)
    params['ema_clamp_min'] = -ema_clamp
    params['ema_clamp_max'] = ema_clamp
    
    # Risk weights
    params['risk_weight_delta'] = trial.suggest_float('risk_weight_delta', 0.1, 0.4, step=0.1)
    params['risk_weight_volume'] = trial.suggest_float('risk_weight_volume', 0.1, 0.4, step=0.1)
    params['risk_weight_volatility'] = trial.suggest_float('risk_weight_volatility', 0.2, 0.5, step=0.1)
    
    # Phase 3+ params
    params['tp_low_ratio'] = trial.suggest_float('tp_low_ratio', 0.4, 1.0, step=0.1)
    params['tp_high_ratio'] = trial.suggest_float('tp_high_ratio', 1.0, 2.5, step=0.2)
    params['partial_exit_pct'] = trial.suggest_float('partial_exit_pct', 0.3, 0.7, step=0.1)
    
    params['trailing_stop_activation_pct'] = trial.suggest_float('trailing_activation', 0.005, 0.015, step=0.002)
    params['trailing_stop_distance_pct'] = trial.suggest_float('trailing_distance', 0.003, 0.01, step=0.001)
    
    params['cooldown_sec'] = trial.suggest_int('cooldown_sec', 20, 60, step=10)
    
    # BTC max risk higher (less sensitive)
    params['max_risk_score'] = trial.suggest_float('max_risk_score', 0.6, 0.95, step=0.05)
    
    try:
        df_features = build_aurora_features(df, btc_df, params, bar_seconds=bar_seconds)
        engine = BacktestEngineAurora(df_features, params)
        metrics = engine.run()
        
        pnl = metrics['total_pnl']
        calmar = metrics['calmar']
        trades = metrics['trades']
        
        if trades < 15:  # Lower threshold for BTC
            return -1000.0
            
        score = pnl
        
        if calmar > 2.5:
            score *= 1.15
            
        return score
        
    except Exception as e:
        print(f"Trial failed: {e}")
        return -1000.0

def run_optimization():
    print(f"Starting BTC-Specific Optimization (Quick Fix)...")
    
    template = FEATURES_DATASET_TEMPLATE_5M
    data_path = get_data_path(template, SYMBOL, YEAR, MONTH)
    
    if not data_path.exists():
        print(f"Data not found: {data_path}")
        return

    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    btc_path = get_data_path(template, "BTCUSDT", YEAR, MONTH)
    btc_df = None
    if btc_path.exists():
        btc_df = pd.read_csv(btc_path)
        btc_df['ts'] = pd.to_datetime(btc_df['ts'])
        if 'close_1s' in btc_df.columns:
            btc_df['btc_close_1s'] = btc_df['close_1s']
    
    # Load base params (Phase 2 or whatever exists)
    base_params = {}
    for source in ['phase2', 'DEEP']:
        path = f"best_aurora_{SYMBOL}_5m_{source}.json"
        if os.path.exists(path):
            print(f"Loading base params from {path}")
            with open(path, 'r') as f:
                data = json.load(f)
                base_params = data.get('params', data)
                break
    
    bar_seconds = 300
    
    study_name = f"aurora_btc_quickfix_{SYMBOL}_{TIMEFRAME}"
    storage_url = f"sqlite:///{study_name}.db"
        
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_url,
        direction="maximize",
        load_if_exists=True
    )
    
    print(f"Running {N_TRIALS} trials with BTC-SPECIFIC params...")
    print("Changes: Wider SL (2.5-4.5%), Longer holds (20-40 min), Lower threshold")
    study.optimize(
        lambda trial: objective_btc_quick_fix(trial, df, btc_df, base_params, bar_seconds),
        n_trials=N_TRIALS,
        n_jobs=1
    )
    
    print("Best params:")
    print(json.dumps(study.best_params, indent=2))
    
    # Save results
    best_params = base_params.copy()
    best_params.update(study.best_params)
    
    if 'ema_clamp_abs' in study.best_params:
        val = study.best_params['ema_clamp_abs']
        best_params['ema_clamp_min'] = -val
        best_params['ema_clamp_max'] = val
        del best_params['ema_clamp_abs']
        
    result = {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "phase": "3+ BTC Quick Fix",
        "metrics": {
            "pnl": study.best_value,
            "trials": len(study.trials)
        },
        "params": best_params
    }
    
    with open(f"best_aurora_{SYMBOL}_{TIMEFRAME}_btc_fix.json", "w") as f:
        json.dump(result, f, indent=2)
        
    print(f"Saved to best_aurora_{SYMBOL}_{TIMEFRAME}_btc_fix.json")

if __name__ == "__main__":
    run_optimization()
