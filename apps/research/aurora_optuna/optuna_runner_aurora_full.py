"""
Aurora Phase 3+ ("Full Feature") Optuna Runner
==============================================
100% feature coverage: All production execution logic + decision params

New features vs Phase 3:
- Take-Profit (TP1 partial, TP2 full exit)
- Trailing Stop
- Cooldown between trades
- Partial exit percentage optimization

Target assets: ETH (5m), BTC (5m), XRP (3m)
"""
import optuna
import pandas as pd
import numpy as np
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

# Configuration
SYMBOL = "ETHUSDT"  # Default
TIMEFRAME = "5m"
YEAR = "2024"
MONTH = "01"
N_TRIALS = 3000

def load_base_params(symbol, timeframe):
    """Load best parameters from Phase 3 or fallback to Phase 2/DEEP."""
    for source in ['phase3', 'DEEP', 'phase2']:
        path = f"best_aurora_{symbol}_{timeframe}_{source}.json"
        if os.path.exists(path):
            print(f"Loading base params from {path}")
            with open(path, 'r') as f:
                data = json.load(f)
                return data.get('params', data)
    
    print(f"⚠️  No base params found for {symbol}. Using empty dict.")
    return {}

def objective_phase3_full(trial, df, btc_df, base_params, bar_seconds):
    """
    Objective function with 100% feature coverage.
    
    Optimizes:
    - All Phase 3 params (side-bias, regime thresholds/sizing, EMA clamp, risk weights)
    - NEW: TP ratios, trailing stop, cooldown, partial exit %
    """
    params = base_params.copy()
    
    # ============================================================================
    # PHASE 3 PARAMETERS (from previous optimization - KEEP OPTIMIZING)
    # ============================================================================
    
    # Side Bias
    params['side_bias_window_sec'] = trial.suggest_int('side_bias_window_sec', 60, 600, step=60)
    params['side_bias_penalty_factor'] = trial.suggest_float('side_bias_penalty_factor', 0.0, 1.0, step=0.1)
    
    # Regime-Adaptive Thresholds
    params['regime_threshold_high_vol'] = trial.suggest_float('regime_threshold_high_vol', 1.0, 2.0, step=0.1)
    params['regime_threshold_low_vol'] = trial.suggest_float('regime_threshold_low_vol', 0.5, 1.0, step=0.05)
    params['regime_threshold_trend'] = trial.suggest_float('regime_threshold_trend', 0.8, 1.2, step=0.05)
    
    # Regime-Adaptive Sizing
    params['sizing_high_vol'] = trial.suggest_float('sizing_high_vol', 0.1, 1.0, step=0.1)
    params['sizing_low_vol'] = trial.suggest_float('sizing_low_vol', 1.0, 2.0, step=0.1)
    params['sizing_mean_rev'] = trial.suggest_float('sizing_mean_rev', 0.5, 1.5, step=0.1)
    
    # EMA Clamp
    ema_clamp = trial.suggest_float('ema_clamp_abs', 0.005, 0.05, step=0.005)
    params['ema_clamp_min'] = -ema_clamp
    params['ema_clamp_max'] = ema_clamp
    
    # Risk Score Weights
    params['risk_weight_delta'] = trial.suggest_float('risk_weight_delta', 0.1, 0.5, step=0.1)
    params['risk_weight_volume'] = trial.suggest_float('risk_weight_volume', 0.1, 0.5, step=0.1)
    params['risk_weight_volatility'] = trial.suggest_float('risk_weight_volatility', 0.1, 0.5, step=0.1)
    
    # ============================================================================
    # PHASE 3+ PARAMETERS (NEW!)
    # ============================================================================
    
    # Take-Profit Logic
    params['tp_low_ratio'] = trial.suggest_float('tp_low_ratio', 0.3, 1.0, step=0.1)
    params['tp_high_ratio'] = trial.suggest_float('tp_high_ratio', 0.8, 2.0, step=0.2)
    params['partial_exit_pct'] = trial.suggest_float('partial_exit_pct', 0.3, 0.7, step=0.1)
    
    # Trailing Stop
    params['trailing_stop_activation_pct'] = trial.suggest_float('trailing_activation', 0.003, 0.01, step=0.001)
    params['trailing_stop_distance_pct'] = trial.suggest_float('trailing_distance', 0.002, 0.008, step=0.001)
    
    # Cooldown
    params['cooldown_sec'] = trial.suggest_int('cooldown_sec', 0, 30, step=5)
    
    # ============================================================================
    # BUILD FEATURES & RUN BACKTEST
    # ============================================================================
    
    try:
        # Rebuild features with new EMA clamp / Risk weights
        df_features = build_aurora_features(df, btc_df, params, bar_seconds=bar_seconds)
        
        # Run Backtest
        engine = BacktestEngineAurora(df_features, params)
        metrics = engine.run()
        
        # Objective: Maximize PnL with penalties
        pnl = metrics['total_pnl']
        calmar = metrics['calmar']
        trades = metrics['trades']
        
        # Penalties
        if trades < 20:  # Too few trades
            return -1000.0
            
        score = pnl
        
        # Bonus for high Calmar (risk-adjusted return)
        if calmar > 3.0:
            score *= 1.1
            
        return score
        
    except Exception as e:
        print(f"Trial failed: {e}")
        return -1000.0

def run_optimization(symbol, timeframe, n_trials=N_TRIALS):
    print(f"Starting Phase 3+ FULL FEATURE Optimization for {symbol} ({timeframe})...")
    
    # Load Data
    template = FEATURES_DATASET_TEMPLATE_3M if timeframe == '3m' else FEATURES_DATASET_TEMPLATE_5M
    data_path = get_data_path(template, symbol, YEAR, MONTH)
    
    if not data_path.exists():
        print(f"Data not found: {data_path}")
        return

    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Load BTC for macro sync
    btc_path = get_data_path(template, "BTCUSDT", YEAR, MONTH)
    btc_df = None
    if btc_path.exists():
        btc_df = pd.read_csv(btc_path)
        btc_df['ts'] = pd.to_datetime(btc_df['ts'])
        if 'close_1s' in btc_df.columns:
            btc_df['btc_close_1s'] = btc_df['close_1s']
    
    # Load Base Params
    base_params = load_base_params(symbol, timeframe)
    if not base_params:
        print("Warning: No base parameters. Starting from scratch.")

    bar_seconds = 300 if timeframe == '5m' else 180
    
    # Optuna Study
    study_name = f"aurora_full_{symbol}_{timeframe}"
    storage_url = f"sqlite:///{study_name}.db"
        
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_url,
        direction="maximize",
        load_if_exists=True
    )
    
    print(f"Running {n_trials} trials with FULL FEATURE SET...")
    print("Features: TP (partial+full), Trailing Stop, Cooldown, + All Phase 3")
    study.optimize(
        lambda trial: objective_phase3_full(trial, df, btc_df, base_params, bar_seconds),
        n_trials=n_trials,
        n_jobs=1  # Sequential (feature building is CPU intensive)
    )
    
    print("Best params:")
    print(json.dumps(study.best_params, indent=2))
    
    # Save results
    best_params = base_params.copy()
    best_params.update(study.best_params)
    
    # Add derived params
    if 'ema_clamp_abs' in study.best_params:
        val = study.best_params['ema_clamp_abs']
        best_params['ema_clamp_min'] = -val
        best_params['ema_clamp_max'] = val
        del best_params['ema_clamp_abs']
        
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "phase": "3+ (Full Feature)",
        "metrics": {
            "pnl": study.best_value,
            "trials": len(study.trials)
        },
        "params": best_params
    }
    
    with open(f"best_aurora_{symbol}_{timeframe}_full.json", "w") as f:
        json.dump(result, f, indent=2)
        
    print(f"Saved best params to best_aurora_{symbol}_{timeframe}_full.json")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--timeframe", default=TIMEFRAME)
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    args = parser.parse_args()
    
    run_optimization(args.symbol, args.timeframe, args.trials)
