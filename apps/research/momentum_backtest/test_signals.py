import pandas as pd
import numpy as np
from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)

def main():
    # Load Data
    path = get_processed_file_path(FEATURES_DATASET_TEMPLATE, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
    print(f"Loading features from {path}...")
    df = pd.read_csv(path)
    
    # Convert ts to datetime
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Simulate signal generation
    w_tfi = 1.0
    threshold = 0.0
    
    score_raw = w_tfi * df['tfi_1m']
    
    print(f"\nScore stats:")
    print(score_raw.describe())
    
    signals = (score_raw > threshold).astype(int)
    
    print(f"\nSignal stats:")
    print(f"Total signals: {signals.sum()}")
    print(f"Signal rate: {signals.mean():.2%}")
    
    # Check for NaN issues
    print(f"\nNaN check:")
    print(f"tfi_1m NaNs: {df['tfi_1m'].isna().sum()}")
    print(f"score NaNs: {score_raw.isna().sum()}")
    print(f"signal NaNs: {signals.isna().sum()}")
    
    # Show first few signals
    print(f"\nFirst 20 rows with signal=1:")
    signal_rows = df[signals == 1].head(20)
    print(signal_rows[['ts', 'tfi_1m', 'close_1s']])

if __name__ == "__main__":
    main()
