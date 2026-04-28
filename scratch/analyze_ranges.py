import pandas as pd
import os
from pathlib import Path

def analyze_bar_ranges(symbol, tf=180):
    # Find most recent data
    date_dirs = sorted([d for d in Path("data/recorder").iterdir() if d.is_dir()], reverse=True)
    if not date_dirs:
        print("No data found.")
        return
    
    fpath = date_dirs[0] / f"{symbol}_{tf}.csv"
    if not fpath.exists():
        print(f"File {fpath} not found.")
        return
    
    df = pd.read_csv(fpath)
    df['range_pct'] = (df['high'] - df['low']) / df['low'] * 100
    
    print(f"\n--- {symbol} ({tf}s) Bar Range Analysis ---")
    print(df['range_pct'].describe())
    print(f"0.13 * Avg Range Pct: {df['range_pct'].mean() * 0.13:.4f}%")

if __name__ == "__main__":
    analyze_bar_ranges("BNBUSDT")
    analyze_bar_ranges("XRPUSDT")
