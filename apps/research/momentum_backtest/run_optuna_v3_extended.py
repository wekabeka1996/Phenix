import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.momentum_backtest.optuna_runner import run_optuna_study

def main():
    print("="*60)
    print("OPTUNA V3 EXTENDED (400 Trials, 9 Weights)")
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
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    
    # Verify new columns exist
    required_cols = ['delta_price_phi', 'volume_spike_phi', 'volatility_state_phi', 'depth_imbalance_phi']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"ERROR: Missing columns: {missing}")
        return
    
    print(f"✅ All 9 phi-features present")
    
    # Run study
    study = run_optuna_study(
        df_features=df,
        n_trials=400,
        storage_url="sqlite:///apps/research/momentum_backtest/data/optuna_v3_extended_400.db"
    )
    
    print("\n" + "="*60)
    print("OPTIMIZATION COMPLETE")
    print("="*60)
    print(f"Best score: {study.best_value:.3f}")
    print(f"Best params: {study.best_params}")

if __name__ == "__main__":
    main()
