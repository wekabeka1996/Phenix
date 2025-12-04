import pandas as pd
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from apps.research.momentum_backtest.optuna_runner import run_optuna_study

def main():
    print("="*60)
    print("OPTUNA V2 SMOKE TEST (5 Trials)")
    print("="*60)
    
    # Load features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"Loading features from {features_path}...")
    
    if not Path(features_path).exists():
        print(f"Error: Features file not found at {features_path}")
        return
        
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    print(f"Loaded {len(df)} rows.")
    
    # Run study
    study = run_optuna_study(
        df_features=df,
        n_trials=50,
        storage_url="sqlite:///apps/research/momentum_backtest/data/optuna_smoke_50.db"
    )
    
    print("\nSmoke test complete.")
    print(f"Best score: {study.best_value:.3f}")
    print(f"Best params: {study.best_params}")

if __name__ == "__main__":
    main()
