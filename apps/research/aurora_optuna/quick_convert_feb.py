"""
Quick converter: 1m klines → 60s golden format for Aurora
"""
import pandas as pd
from pathlib import Path
import sys

SYMBOLS = ['BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'XRPUSDT', 'DOGEUSDT']
YEAR = '2024'
MONTH = '02'

def convert_1m_to_60s(input_path, output_path):
    """Convert 1m klines to golden 60s format."""
    print(f"Converting {input_path.name}...")
    
    # Read 1m klines
    df = pd.read_csv(input_path)
    
    # Expected columns: open_time, open, high, low, close, volume, ...
    # Rename to golden format
    df_golden = pd.DataFrame({
        'ts': pd.to_datetime(df['open_time'], unit='ms'),
        'open_60s': df['open'],
        'high_60s': df['high'],
        'low_60s': df['low'],
        'close_60s': df['close'],
        'vol_60s': df['volume'],
    })
    
    # Save
    df_golden.to_csv(output_path, index=False)
    print(f"  → Saved {len(df_golden)} rows to {output_path.name}")

def main():
    data_dir = Path("/home/wekabeka/Музыка/Phenix/data/historical")
    output_dir = Path("/home/wekabeka/Музыка/Phenix/apps/research/momentum_backtest/data")
    
    for symbol in SYMBOLS:
        # Find 1m file
        pattern = f"{symbol}-1m-{YEAR}-{MONTH}.csv"
        input_files = list(data_dir.glob(f"**/{pattern}"))
        
        if not input_files:
            print(f"⚠️  {symbol}: No 1m file found")
            continue
        
        input_path = input_files[0]
        output_path = output_dir / f"{symbol}-60s-golden-{YEAR}-{MONTH}.csv"
        
        try:
            convert_1m_to_60s(input_path, output_path)
        except Exception as e:
            print(f"❌ {symbol}: Error - {e}")
            continue
    
    print("\n✅ Conversion complete!")

if __name__ == "__main__":
    main()
