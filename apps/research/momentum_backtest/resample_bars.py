"""
Resample 1s Golden Dataset to 5s and 10s resolutions.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    GOLDEN_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)

def resample_dataset(symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH):
    input_path = get_processed_file_path(GOLDEN_DATASET_TEMPLATE, symbol, year, month)
    
    if not input_path.exists():
        print(f"Input file {input_path} does not exist.")
        return

    print(f"Loading 1s Golden Dataset from {input_path}...")
    df = pd.read_csv(input_path)
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    
    # Define aggregation rules
    agg_rules = {
        'open_1s': 'first',
        'high_1s': 'max',
        'low_1s': 'min',
        'close_1s': 'last',
        'vol_1s': 'sum',
        'buy_vol_1s': 'sum',
        'sell_vol_1s': 'sum',
        'tob_bid_qty_1s': 'mean',
        'tob_ask_qty_1s': 'mean',
        'funding_rate_1s': 'last'
    }
    
    # Check for BTC column
    if 'btc_close_1s' in df.columns:
        agg_rules['btc_close_1s'] = 'last'
    
    horizons = [5, 10, 60]  # Added 60s (1m)
    
    for h in horizons:
        print(f"Resampling to {h}s...")
        
        # Resample
        df_resampled = df.resample(f'{h}s').agg(agg_rules)
        
        # Drop NaNs (if any gaps)
        df_resampled.dropna(inplace=True)
        
        # Reset index to get 'ts' back
        df_resampled.reset_index(inplace=True)
        
        # Rename columns to reflect horizon? 
        # User requested "BNBUSDT-5s-golden-2024-03.csv" but didn't specify column renaming.
        # Keeping "_1s" suffix might be confusing, but consistent with code that expects "close_1s".
        # However, features_builder uses "close_1s".
        # If I rename to "close_5s", I must update features_builder.
        # User said "build features on 1s/5s/10s microbars".
        # I will KEEP the column names as `_1s` (or rename to generic `_bar`) to minimize code changes in features_builder,
        # OR I will rename them in features_builder.
        # Let's rename them to generic names in the output file? 
        # No, let's keep them as `_1s` for now to avoid breaking everything, 
        # BUT ideally they should be `open`, `high`, `low`, `close`.
        # The current system relies on `_1s` suffix.
        # I will keep the suffix but save to a new file.
        
        output_filename = GOLDEN_DATASET_TEMPLATE.replace("1s", f"{h}s")
        output_path = get_processed_file_path(output_filename, symbol, year, month)
        
        print(f"Saving to {output_path}...")
        df_resampled.to_csv(output_path, index=False)
        print(f"Saved {len(df_resampled)} rows.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Resample 1s Golden to 5s/10s")
    parser.add_argument("--symbol", type=str, default=DEFAULT_SYMBOL)
    parser.add_argument("--year", type=str, default=DEFAULT_YEAR)
    parser.add_argument("--month", type=str, default=DEFAULT_MONTH)
    args = parser.parse_args()
    
    resample_dataset(symbol=args.symbol, year=args.year, month=args.month)
