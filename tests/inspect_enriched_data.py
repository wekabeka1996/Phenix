
import polars as pl
from pathlib import Path
import sys

def inspect_file(path: str):
    print(f"Inspecting: {path}")
    if not Path(path).exists():
        print(f"File not found: {path}")
        return

    df = pl.read_parquet(path)
    print(f"Shape: {df.shape}")
    print("Columns:", df.columns)

    expected_cols = ["avg_bid_qty", "avg_ask_qty", "last_bid_price", "last_ask_price", "buy_volume", "sell_volume"]
    missing = [c for c in expected_cols if c not in df.columns]
    
    if missing:
        print(f"FAIL: Missing columns: {missing}")
    else:
        print("SUCCESS: All expected columns found.")
        
        # Sample Data
        print("\nFirst 5 rows of enriched columns:")
        print(df.select(expected_cols).head(5))

        # Stats for avg_bid_qty
        print("\nStats for avg_bid_qty:")
        print(df.select("avg_bid_qty").describe())
        
        # Check non-zero
        non_zeros = df.filter(pl.col("avg_bid_qty") > 0).height
        print(f"\nRows with avg_bid_qty > 0: {non_zeros} / {df.height}")

if __name__ == "__main__":
    # Hardcoded path for the file we just generated
    target_file = "/home/wekabeka/Музыка/Phenix/data/processed/BTCUSDT/klines/5m/2023-05_enriched.parquet"
    inspect_file(target_file)
