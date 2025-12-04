"""
Build Features for 1m Mean Reversion
"""
import pandas as pd
import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.new_alpha_mean_reversion.features import compute_rsi, compute_bollinger_bands
from apps.research.momentum_backtest.regime_labeling import add_regime_labels
from apps.research.momentum_backtest.config import get_processed_file_path

def build_features_1m(symbol, year, month):
    print(f"Building 1m Mean Reversion features for {symbol} {year}-{month}...")
    
    # Load 60s (1m) Golden
    input_path = get_processed_file_path(f"{symbol}-60s-golden-{year}-{month}.csv", symbol, year, month)
    if not input_path.exists():
        print(f"Error: {input_path} not found. Run resampling first.")
        return
        
    df = pd.read_csv(input_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # 0. Regime Labeling (Before renaming)
    print(f"  Computing Regime Labels...")
    df = add_regime_labels(df, trend_window_sec=300, vol_window_sec=300, bar_horizon_sec=60)
    
    # Rename columns
    df.rename(columns={
        'open_1s': 'open_60s',
        'high_1s': 'high_60s',
        'low_1s': 'low_60s',
        'close_1s': 'close_60s',
        'vol_1s': 'vol_60s'
    }, inplace=True)
    
    # 1. Bollinger Bands
    # On 1m bars, window=20 means 20 minutes
    windows = [20, 60, 120]  # 20m, 60m (1h), 120m (2h)
    for w in windows:
        print(f"  Computing Bollinger Bands {w}m...")
        upper, lower, sma = compute_bollinger_bands(df['close_60s'], window=w, num_std=2.0)
        df[f'bb_upper_{w}'] = upper
        df[f'bb_lower_{w}'] = lower
        df[f'bb_mid_{w}'] = sma
        df[f'bb_width_{w}'] = (upper - lower) / (sma + 1e-9)
        df[f'bb_pct_b_{w}'] = (df['close_60s'] - lower) / (upper - lower + 1e-9)
        df[f'dist_sma_{w}'] = (df['close_60s'] - sma) / (df['close_60s'].rolling(window=w).std() + 1e-9)

    # 2. RSI
    print(f"  Computing RSI...")
    df['rsi_14'] = compute_rsi(df['close_60s'], window=14)  # 14 minutes
    df['rsi_60'] = compute_rsi(df['close_60s'], window=60)  # 1 hour
    
    # Save
    output_path = get_processed_file_path(f"{symbol}-features-mr-1m-{year}-{month}.csv", symbol, year, month)
    print(f"Saving to {output_path}...")
    df.to_csv(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, required=True)
    parser.add_argument("--year", type=str, default="2024")
    parser.add_argument("--month", type=str, default="01")
    args = parser.parse_args()
    
    build_features_1m(args.symbol, args.year, args.month)
