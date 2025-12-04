"""
Build Features for Mean Reversion
"""
import pandas as pd
import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.new_alpha_mean_reversion.features import build_mean_reversion_features
from apps.research.momentum_backtest.config import get_processed_file_path

def build(symbol, year, month):
    print(f"Building Mean Reversion features for {symbol} {year}-{month}...")
    
    # Load 5s Golden
    input_path = get_processed_file_path(f"{symbol}-5s-golden-{year}-{month}.csv", symbol, year, month)
    if not input_path.exists():
        print(f"Error: {input_path} not found. Run resampling first.")
        return
        
    df_golden = pd.read_csv(input_path)
    df_golden['ts'] = pd.to_datetime(df_golden['ts'])
    
    # Build Features
    df_features = build_mean_reversion_features(df_golden, symbol)
    
    # Save
    output_path = get_processed_file_path(f"{symbol}-features-mr-{year}-{month}.csv", symbol, year, month)
    print(f"Saving to {output_path}...")
    df_features.to_csv(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, required=True)
    parser.add_argument("--year", type=str, default="2024")
    parser.add_argument("--month", type=str, default="03")
    args = parser.parse_args()
    
    build(args.symbol, args.year, args.month)
