import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

from apps.research.momentum_backtest.config import (
    get_raw_file_path,
    get_processed_file_path,
    AGG_TRADES_TEMPLATE,
    BOOK_TICKER_TEMPLATE,
    FUNDING_RATE_TEMPLATE,
    KLINES_1M_TEMPLATE,
    GOLDEN_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)

def load_agg_trades(filepath: Path, chunksize: int = 1000000, nrows: Optional[int] = None) -> pd.DataFrame:
    """
    Load aggTrades CSV and resample to 1s OHLCV + Buy/Sell Volume using chunks.
    """
    print(f"Loading aggTrades from {filepath} in chunks (nrows={nrows})...")
    names = ['agg_trade_id', 'price', 'quantity', 'first_trade_id', 'last_trade_id', 'transact_time', 'is_buyer_maker']
    
    chunks = []
    
    # Check header on first chunk
    first_chunk = True
    header = None
    
    # Heuristic: Read first line.
    with open(filepath, 'r') as f:
        line = f.readline()
        if line and not line.split(',')[1].replace('.','',1).isdigit():
            header = 0
            
    try:
        reader = pd.read_csv(filepath, names=names, header=header, chunksize=chunksize, nrows=nrows)
        
        for i, df_chunk in enumerate(reader):
            if i % 10 == 0:
                print(f"Processing chunk {i}...")
                
            df_chunk['transact_time'] = pd.to_datetime(df_chunk['transact_time'], unit='ms')
            df_chunk['price'] = df_chunk['price'].astype(float)
            df_chunk['quantity'] = df_chunk['quantity'].astype(float)
            df_chunk['is_buyer_maker'] = df_chunk['is_buyer_maker'].astype(bool)
            
            df_chunk.set_index('transact_time', inplace=True)
            
            # Resample chunk
            ohlc = df_chunk['price'].resample('1s').ohlc()
            vol = df_chunk['quantity'].resample('1s').sum().rename('vol_1s')
            
            sell_vol = df_chunk[df_chunk['is_buyer_maker']]['quantity'].resample('1s').sum().rename('sell_vol_1s')
            buy_vol = df_chunk[~df_chunk['is_buyer_maker']]['quantity'].resample('1s').sum().rename('buy_vol_1s')
            
            chunk_res = pd.concat([ohlc, vol, buy_vol, sell_vol], axis=1)
            chunks.append(chunk_res)
            
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        raise

    print("Concatenating chunks...")
    if not chunks:
        return pd.DataFrame()
        
    full_res = pd.concat(chunks)
    
    print("Aggregating chunks...")
    grouped = full_res.groupby(level=0)
    
    final_res = pd.DataFrame()
    final_res['open_1s'] = grouped['open'].first()
    final_res['high_1s'] = grouped['high'].max()
    final_res['low_1s'] = grouped['low'].min()
    final_res['close_1s'] = grouped['close'].last()
    final_res['vol_1s'] = grouped['vol_1s'].sum()
    final_res['buy_vol_1s'] = grouped['buy_vol_1s'].sum()
    final_res['sell_vol_1s'] = grouped['sell_vol_1s'].sum()
    
    # Fill NaNs
    final_res['close_1s'] = final_res['close_1s'].ffill()
    final_res['open_1s'] = final_res['open_1s'].fillna(final_res['close_1s'])
    final_res['high_1s'] = final_res['high_1s'].fillna(final_res['close_1s'])
    final_res['low_1s'] = final_res['low_1s'].fillna(final_res['close_1s'])
    
    final_res['vol_1s'] = final_res['vol_1s'].fillna(0)
    final_res['buy_vol_1s'] = final_res['buy_vol_1s'].fillna(0)
    final_res['sell_vol_1s'] = final_res['sell_vol_1s'].fillna(0)
    
    return final_res

def load_book_ticker(filepath: Path, chunksize: int = 1000000, nrows: Optional[int] = None) -> pd.DataFrame:
    """
    Load bookTicker CSV and resample to 1s (last value) using chunks.
    """
    print(f"Loading bookTicker from {filepath} in chunks (nrows={nrows})...")
    names = ['update_id', 'best_bid_price', 'best_bid_qty', 'best_ask_price', 'best_ask_qty', 'transaction_time', 'event_time']
    
    chunks = []
    
    header = None
    with open(filepath, 'r') as f:
        line = f.readline()
        if line and not line.split(',')[1].replace('.','',1).isdigit():
            header = 0
            
    reader = pd.read_csv(filepath, names=names, header=header, chunksize=chunksize, nrows=nrows)
    
    for i, df_chunk in enumerate(reader):
        if i % 10 == 0:
            print(f"Processing chunk {i}...")
            
        df_chunk['transaction_time'] = pd.to_datetime(df_chunk['transaction_time'], unit='ms')
        df_chunk['best_bid_qty'] = df_chunk['best_bid_qty'].astype(float)
        df_chunk['best_ask_qty'] = df_chunk['best_ask_qty'].astype(float)
        
        df_chunk.set_index('transaction_time', inplace=True)
        
        # Resample to 1s, taking LAST
        chunk_res = df_chunk[['best_bid_qty', 'best_ask_qty']].resample('1s').last()
        chunks.append(chunk_res)
        
    print("Concatenating chunks...")
    if not chunks:
        return pd.DataFrame()
        
    full_res = pd.concat(chunks)
    
    # Group by index and take last
    final_res = full_res.groupby(level=0).last()
    
    final_res.columns = ['tob_bid_qty_1s', 'tob_ask_qty_1s']
    
    # Forward fill
    final_res = final_res.ffill()
    
    return final_res

def load_funding_rate(filepath: Path) -> pd.DataFrame:
    """
    Load fundingRate CSV and resample to 1s (ffill).
    Expected columns: calc_time, funding_interval_hours, last_funding_rate
    """
    print(f"Loading fundingRate from {filepath}...")
    
    # Read with header to get correct column names
    df = pd.read_csv(filepath)
    
    # Expected columns from Binance Vision: calc_time, funding_interval_hours, last_funding_rate
    if 'last_funding_rate' not in df.columns:
        raise ValueError(f"Expected 'last_funding_rate' column in {filepath}, got: {df.columns.tolist()}")
         
    df['calc_time'] = pd.to_datetime(df['calc_time'], unit='ms')
    df['last_funding_rate'] = df['last_funding_rate'].astype(float)
    
    df.set_index('calc_time', inplace=True)
    
    # Return only the funding rate column, rename it
    return df[['last_funding_rate']].rename(columns={'last_funding_rate': 'funding_rate'})

def build_btc_1s_series(btc_klines_path: Path) -> pd.DataFrame:
    """
    Load BTCUSDT 1m klines and upsample to 1s with forward-fill.
    
    Expected columns: open_time, open, high, low, close, volume, etc.
    Returns DataFrame with columns: ts, btc_close_1s
    """
    print(f"Loading BTC 1m klines from {btc_klines_path}...")
    
    # Read BTC klines (has header)
    df = pd.read_csv(btc_klines_path)
    
    # Convert open_time to datetime
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close'] = df['close'].astype(float)
    
    # Set index
    df.set_index('open_time', inplace=True)
    
    # Upsample to 1s with forward-fill
    # 1m data means we have one value per minute
    # We need to create a 1s index and ffill
    print("Upsampling to 1s...")
    
    # Create 1s range from first to last timestamp
    full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq='1s')
    
    # Reindex to 1s and forward-fill
    df_1s = df[['close']].reindex(full_range, method='ffill')
    
    # Reset index and rename columns
    df_1s.reset_index(inplace=True)
    df_1s.columns = ['ts', 'btc_close_1s']
    
    print(f"BTC 1s series created: {len(df_1s):,} rows")
    
    return df_1s

def process_golden_dataset(symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH, nrows: Optional[int] = None, include_btc: bool = True):
    """
    Main ETL function.
    
    Args:
        symbol: Trading symbol (default: BNBUSDT)
        year: Year string
        month: Month string
        nrows: Optional row limit (None = process full month)
        include_btc: If True, add btc_close_1s column
    """
    # Paths
    agg_path = get_raw_file_path(AGG_TRADES_TEMPLATE, symbol, year, month)
    bt_path = get_raw_file_path(BOOK_TICKER_TEMPLATE, symbol, year, month)
    fr_path = get_raw_file_path(FUNDING_RATE_TEMPLATE, symbol, year, month)
    
    output_path = get_processed_file_path(GOLDEN_DATASET_TEMPLATE, symbol, year, month)
    
    if output_path.exists() and nrows is None:
        print(f"Output file {output_path} already exists. Skipping.")
        print("To regenerate, delete the file first.")
        return

    # Load Data
    print(f"\n{'='*60}")
    print(f"Processing {symbol} for {year}-{month}")
    print(f"nrows limit: {nrows if nrows else 'FULL MONTH'}")
    print('='*60)
    
    df_agg = load_agg_trades(agg_path, nrows=nrows)
    df_bt = load_book_ticker(bt_path, nrows=nrows)
    df_fr = load_funding_rate(fr_path)
    
    # Align timestamps
    # Use df_agg index as the master index (1s bars)
    master_idx = df_agg.index
    
    print(f"\nMaster index (from aggTrades): {len(master_idx):,} seconds")
    print(f"  First: {master_idx.min()}")
    print(f"  Last: {master_idx.max()}")
    print(f"  Duration: {(master_idx.max() - master_idx.min()).total_seconds() / 86400:.2f} days")
    
    # Merge BookTicker
    df_bt_aligned = df_bt.reindex(master_idx, method='ffill')
    
    # Merge Funding Rate
    df_fr_aligned = df_fr.reindex(master_idx, method='ffill')
    
    # Combine all
    df_golden = pd.concat([df_agg, df_bt_aligned, df_fr_aligned], axis=1)
    
    # Rename funding column
    df_golden.rename(columns={'funding_rate': 'funding_rate_1s'}, inplace=True)
    
    # Add BTC if requested
    if include_btc:
        print("\nAdding BTC correlation data...")
        # For BNB, use BTC klines; for other symbols, adjust accordingly
        btc_symbol = "BTCUSDT"  # Could parameterize this
        btc_klines_path = get_raw_file_path(KLINES_1M_TEMPLATE, btc_symbol, year, month)
        
        if btc_klines_path.exists():
            df_btc = build_btc_1s_series(btc_klines_path)
            
            # Merge BTC by ts (after resetting index)
            df_golden.reset_index(inplace=True)
            df_golden.rename(columns={'transact_time': 'ts'}, inplace=True)
            
            # Left join on ts
            df_golden = df_golden.merge(df_btc, on='ts', how='left')
            
            # Forward-fill BTC for any gaps
            df_golden['btc_close_1s'] = df_golden['btc_close_1s'].ffill()
            
            # Backfill at start if needed
            df_golden['btc_close_1s'] = df_golden['btc_close_1s'].bfill()
            
            print(f"BTC integrated: {df_golden['btc_close_1s'].notna().sum():,} / {len(df_golden):,} rows")
        else:
            print(f"WARNING: BTC file not found at {btc_klines_path}, skipping BTC integration")
            df_golden.reset_index(inplace=True)
            df_golden.rename(columns={'transact_time': 'ts'}, inplace=True)
            df_golden['btc_close_1s'] = 0.0
    else:
        df_golden.reset_index(inplace=True)
        df_golden.rename(columns={'transact_time': 'ts'}, inplace=True)
    
    # Final cleanup
    # Fill any remaining NaNs
    df_golden = df_golden.ffill().bfill()
    df_golden = df_golden.fillna(0)
    
    # Save
    print(f"\nSaving Golden Dataset to {output_path}...")
    df_golden.to_csv(output_path, index=False)
    
    # Print final stats
    print(f"\n{'='*60}")
    print("GOLDEN DATASET CREATED")
    print('='*60)
    print(f"File: {output_path}")
    print(f"Rows: {len(df_golden):,}")
    print(f"Columns: {df_golden.columns.tolist()}")
    print(f"Date range: {df_golden['ts'].min()} to {df_golden['ts'].max()}")
    print(f"Duration: {(pd.to_datetime(df_golden['ts'].max()) - pd.to_datetime(df_golden['ts'].min())).total_seconds() / 86400:.2f} days")
    print("Done.")

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="ETL for Momentum Backtest")
    parser.add_argument("--symbol", type=str, default=DEFAULT_SYMBOL, help="Trading symbol (e.g. BTCUSDT)")
    parser.add_argument("--year", type=str, default=DEFAULT_YEAR, help="Year (YYYY)")
    parser.add_argument("--month", type=str, default=DEFAULT_MONTH, help="Month (MM)")
    parser.add_argument("--nrows", type=int, default=None, help="Number of rows to read (for testing)")
    
    args = parser.parse_args()
    
    process_golden_dataset(symbol=args.symbol, year=args.year, month=args.month, nrows=args.nrows, include_btc=True)
