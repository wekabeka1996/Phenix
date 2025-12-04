"""
Run Optuna Optimization for Depth Mode Entry/Exit (RND-DEPTH-MODE-ENTRY-EXIT-V1)

Optimizes:
- Signal weights (9 features)
- Entry Gates (Depth, ToB, EMA, Volatility)
- Exit Parameters (SL, TP, Time Stop)

Target: BNBUSDT March 2024
"""

import optuna
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.momentum_backtest.optuna_runner import objective, _df_features_global
import apps.research.momentum_backtest.optuna_runner as runner_module

def run_optimization():
    print("="*80)
    print("OPTUNA OPTIMIZATION: DEPTH MODE ENTRY/EXIT")
    print("="*80)
    
    # Load features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"Loading features from {features_path}...")
    
    if not Path(features_path).exists():
        print(f"ERROR: Features file not found at {features_path}")
        return
    
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Set global features for worker
    runner_module._df_features_global = df
    
    print(f"Loaded {len(df)} rows")
    
    # Create study
    study_name = "depth_mode_entry_exit_v1"
    storage_name = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_name,
        direction="minimize",  # Minimize objective (negative Calmar/PnL)
        load_if_exists=True
    )
    
    print(f"Starting optimization (200 trials)...")
    
    try:
        study.optimize(objective, n_trials=200)
    except KeyboardInterrupt:
        print("\nOptimization interrupted by user.")
    
    print(f"\n{'='*80}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'='*80}")
    
    print(f"Best Trial #{study.best_trial.number}")
    print(f"Value: {study.best_value:.4f}")
    print("Params:")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")
    
    # Save best params
    best_params_df = pd.DataFrame([study.best_params])
    best_params_df.to_json("depth_mode_best_params.json", orient="records", lines=True)
    print(f"\nSaved best params to depth_mode_best_params.json")

if __name__ == "__main__":
    run_optimization()
