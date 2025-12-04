"""
Aurora Phase 3 Optuna Runner: Full Spectrum Optimization
======================================================
Optimizes execution logic (Side Bias, Adaptive Thresholds/Sizing) 
and remaining feature parameters (EMA Clamp, Risk Weights).

Base parameters (Phase 1 & 2) are loaded from best_aurora_*_phase2.json or DEEP.
"""
import optuna
import pandas as pd
import numpy as np
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

# Configuration
SYMBOL = "SOLUSDT"  # Default, override with env var
TIMEFRAME = "3m"
YEAR = "2024"
MONTH = "01"
N_TRIALS = 3000

def load_base_params(symbol, timeframe):
    """Load best parameters from Phase 2 or DEEP optimization."""
    # Try DEEP first (better performance usually)
    deep_path = f"best_aurora_{symbol}_{timeframe}_DEEP.json"
    phase2_path = f"best_aurora_{symbol}_{timeframe}_phase2.json"
    
    if os.path.exists(deep_path):
        print(f"Loading base params from {deep_path}")
        with open(deep_path, 'r') as f:
            data = json.load(f)
            return data.get('params', data)
    elif os.path.exists(phase2_path):
        print(f"Loading base params from {phase2_path}")
        with open(phase2_path, 'r') as f:
            data = json.load(f)
            # Phase 2 JSON structure might be different
            return data.get('combined_params', data.get('params', data))
    else:
        print(f"⚠️  No base params found for {symbol}. Using defaults.")
        return {}

def objective_phase3(trial, df, btc_df, base_params, bar_seconds):
    # Start with base parameters (Phase 1 & 2)
    params = base_params.copy()
    
    # --- PHASE 3 PARAMETERS TO OPTIMIZE ---
    
    # 1. Side Bias (Anti-Persistency)
    params['side_bias_window_sec'] = trial.suggest_int('side_bias_window_sec', 60, 600, step=60)
    params['side_bias_penalty_factor'] = trial.suggest_float('side_bias_penalty_factor', 0.0, 1.0, step=0.1)
    
    # 2. Regime-Adaptive Thresholds
    # Multipliers for signal_threshold
    params['regime_threshold_high_vol'] = trial.suggest_float('regime_threshold_high_vol', 1.0, 2.0, step=0.1)
    params['regime_threshold_low_vol'] = trial.suggest_float('regime_threshold_low_vol', 0.5, 1.0, step=0.05)
    params['regime_threshold_trend'] = trial.suggest_float('regime_threshold_trend', 0.8, 1.2, step=0.05)
    
    # 3. Regime-Adaptive Sizing
    # Multipliers for position_size
    params['sizing_high_vol'] = trial.suggest_float('sizing_high_vol', 0.1, 1.0, step=0.1)
    params['sizing_low_vol'] = trial.suggest_float('sizing_low_vol', 1.0, 2.0, step=0.1)
    params['sizing_mean_rev'] = trial.suggest_float('sizing_mean_rev', 0.5, 1.5, step=0.1)
    
    # 4. Feature Parameters (Previously Hardcoded)
    # EMA Clamp (Trend sensitivity)
    ema_clamp = trial.suggest_float('ema_clamp_abs', 0.005, 0.05, step=0.005)
    params['ema_clamp_min'] = -ema_clamp
    params['ema_clamp_max'] = ema_clamp
    
    # Risk Score Weights
    params['risk_weight_delta'] = trial.suggest_float('risk_weight_delta', 0.1, 0.5, step=0.1)
    params['risk_weight_volume'] = trial.suggest_float('risk_weight_volume', 0.1, 0.5, step=0.1)
    params['risk_weight_volatility'] = trial.suggest_float('risk_weight_volatility', 0.1, 0.5, step=0.1)
    
    # ---------------------------------------
    
    # Rebuild features if needed (EMA clamp/Risk weights change features)
    # Note: This is expensive inside the loop, but necessary for these specific params.
    # To speed up, we could pre-calculate common variants or use a smaller subset of data for pruning.
    # For now, we run full build.
    
    try:
        df_features = build_aurora_features(df, btc_df, params, bar_seconds=bar_seconds)
        
        # Run Backtest
        engine = BacktestEngineAurora(df_features, params)
        metrics = engine.run()
        
        # Objective: Maximize PnL (with Calmar penalty)
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
    print(f"Starting Phase 3 Optimization for {symbol} ({timeframe})...")
    
    # Load Data
    template = FEATURES_DATASET_TEMPLATE_3M if timeframe == '3m' else FEATURES_DATASET_TEMPLATE_5M
    data_path = get_data_path(template, symbol, YEAR, MONTH)
    
    if not data_path.exists():
        print(f"Data not found: {data_path}")
        # Try to find golden data and build temp features
        # For simplicity, assuming features exist or can be built from golden
        # Here we assume the base features file exists (from previous phases)
        print("Please ensure feature files exist.")
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
        print("Critical: No base parameters found. Run Phase 1/2 first.")
        return

    bar_seconds = 300 if timeframe == '5m' else 180
    
    # Optuna Study
    study_name = f"aurora_phase3_{symbol}_{timeframe}"
    storage_url = f"sqlite:///{study_name}.db"
    
    # Clean up old study if exists (optional, or resume)
    # if os.path.exists(f"{study_name}.db"):
    #     os.remove(f"{study_name}.db")
        
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_url,
        direction="maximize",
        load_if_exists=True
    )
    
    print(f"Running {n_trials} trials...")
    study.optimize(
        lambda trial: objective_phase3(trial, df, btc_df, base_params, bar_seconds),
        n_trials=n_trials,
        n_jobs=1  # Sequential because feature building is CPU intensive
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
        del best_params['ema_clamp_abs'] # Remove helper param
        
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "metrics": {
            "pnl": study.best_value,
            "trials": len(study.trials)
        },
        "params": best_params
    }
    
    with open(f"best_aurora_{symbol}_{timeframe}_phase3.json", "w") as f:
        json.dump(result, f, indent=2)
        
    print(f"Saved best params to best_aurora_{symbol}_{timeframe}_phase3.json")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--timeframe", default=TIMEFRAME)
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    args = parser.parse_args()
    
    run_optimization(args.symbol, args.timeframe, args.trials)
