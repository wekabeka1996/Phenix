import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.momentum_backtest.optuna_runner import run_optuna_study

def main():
    print("="*60)
    print("EXTENDED WEIGHTS SMOKE TEST (10 Trials)")
    print("="*60)
    
    # Load features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"Loading features from {features_path}...")
    
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    print(f"Loaded {len(df)} rows.")
    print(f"Columns: {list(df.columns)}")
    
    # Run study
    study = run_optuna_study(
        df_features=df,
        n_trials=10,
        storage_url="sqlite:///apps/research/momentum_backtest/data/optuna_extended_smoke.db"
    )
    
    print("\nSmoke test complete.")
    print(f"Best score: {study.best_value:.3f}")

if __name__ == "__main__":
    main()
