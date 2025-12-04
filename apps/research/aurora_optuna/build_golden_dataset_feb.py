"""
Robust Golden Dataset Builder - February 2024
=============================================
Aggregates Klines, AggTrades, and BookTicker into Aurora 60s format.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import gc

SYMBOLS = ['BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'XRPUSDT', 'DOGEUSDT']
YEAR = '2024'
MONTH = '02'
DATA_DIR = Path("/home/wekabeka/Музыка/Phenix/data/historical")
OUTPUT_DIR = Path("/home/wekabeka/Музыка/Phenix/apps/research/momentum_backtest/data")

def process_symbol(symbol):
    print(f"\nProcessing {symbol}...")
    
    # 1. Load Klines (Base)
    kline_files = list(DATA_DIR.glob(f"**/{symbol}-1m-{YEAR}-{MONTH}.csv"))
    if not kline_files:
        print(f"❌ {symbol}: No kline file found")
        return
    
    print(f"  Loading Klines from {kline_files[0].name}...")
    df_kline = pd.read_csv(kline_files[0])
    df_kline['ts'] = pd.to_datetime(df_kline['open_time'], unit='ms')
    df_kline = df_kline.set_index('ts').sort_index()
    
    # Rename to golden format (using _1s suffix to match January data)
    df_golden = pd.DataFrame({
        'open_1s': df_kline['open'],
        'high_1s': df_kline['high'],
        'low_1s': df_kline['low'],
        'close_1s': df_kline['close'],
        'vol_1s': df_kline['volume'],
    })
    
    del df_kline
    gc.collect()
    
    # 2. Process AggTrades (Buy/Sell Vol)
    trade_files = list(DATA_DIR.glob(f"**/{symbol}-aggTrades-{YEAR}-{MONTH}.csv"))
    if trade_files:
        print(f"  Processing AggTrades from {trade_files[0].name}...")
        
        # Process in chunks to save memory
        chunk_size = 1_000_000
        buy_vols = []
        sell_vols = []
        
        # Columns: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
        # (7 columns found in file)
        names = ['id', 'price', 'qty', 'f_id', 'l_id', 'time', 'is_buyer_maker']
        
        try:
            # Check if header exists
            first_line = pd.read_csv(trade_files[0], nrows=1)
            has_header = 'agg_trade_id' in first_line.columns
            header = 0 if has_header else None
            
            for chunk in pd.read_csv(trade_files[0], chunksize=chunk_size, names=names, header=header):
                
                chunk['ts'] = pd.to_datetime(chunk['time'], unit='ms').dt.floor('1min')
                
                # Buyer Maker = Sell Order (Taker Sell)
                # !Buyer Maker = Buy Order (Taker Buy)
                
                # Buy Vol (Taker Buy)
                buy_chunk = chunk[~chunk['is_buyer_maker']].groupby('ts')['qty'].sum()
                buy_vols.append(buy_chunk)
                
                # Sell Vol (Taker Sell)
                sell_chunk = chunk[chunk['is_buyer_maker']].groupby('ts')['qty'].sum()
                sell_vols.append(sell_chunk)
            
            # Aggregate all chunks
            total_buy_vol = pd.concat(buy_vols).groupby(level=0).sum()
            total_sell_vol = pd.concat(sell_vols).groupby(level=0).sum()
            
            # Merge into golden
            df_golden['buy_vol_1s'] = total_buy_vol
            df_golden['sell_vol_1s'] = total_sell_vol
            
            # Fill NaN with 0 (no trades in that minute)
            df_golden['buy_vol_1s'] = df_golden['buy_vol_1s'].fillna(0)
            df_golden['sell_vol_1s'] = df_golden['sell_vol_1s'].fillna(0)
            
        except Exception as e:
            print(f"⚠️  Error processing trades: {e}")
            df_golden['buy_vol_1s'] = df_golden['vol_1s'] / 2  # Fallback
            df_golden['sell_vol_1s'] = df_golden['vol_1s'] / 2
    else:
        print("⚠️  No AggTrades found, using fallback")
        df_golden['buy_vol_1s'] = df_golden['vol_1s'] / 2
        df_golden['sell_vol_1s'] = df_golden['vol_1s'] / 2
        
    gc.collect()
    
    # 3. Process BookTicker (TOB Liquidity)
    ticker_files = list(DATA_DIR.glob(f"**/{symbol}-bookTicker-{YEAR}-{MONTH}.csv"))
    if ticker_files:
        print(f"  Processing BookTicker from {ticker_files[0].name}...")
        
        # Columns: update_id, best_bid_price, best_bid_qty, best_ask_price, best_ask_qty, transaction_time, event_time
        # (7 columns found in file)
        
        chunk_size = 1_000_000
        bid_qtys = []
        ask_qtys = []
        
        try:
            # Check header
            first_line = pd.read_csv(ticker_files[0], nrows=1)
            has_header = 'best_bid_qty' in first_line.columns
            
            names = ['id', 'bid_p', 'bid_q', 'ask_p', 'ask_q', 'time', 'evt_time']
            header = 0 if has_header else None
            
            for chunk in pd.read_csv(ticker_files[0], chunksize=chunk_size, names=names, header=header):
                # Normalize columns
                if 'time' not in chunk.columns and 'transaction_time' in chunk.columns:
                    chunk['time'] = chunk['transaction_time']
                if 'bid_q' not in chunk.columns and 'best_bid_qty' in chunk.columns:
                    chunk['bid_q'] = chunk['best_bid_qty']
                if 'ask_q' not in chunk.columns and 'best_ask_qty' in chunk.columns:
                    chunk['ask_q'] = chunk['best_ask_qty']
                
                chunk['ts'] = pd.to_datetime(chunk['time'], unit='ms').dt.floor('1min')
                
                # Mean liquidity per minute
                bid_chunk = chunk.groupby('ts')['bid_q'].mean()
                bid_qtys.append(bid_chunk)
                
                ask_chunk = chunk.groupby('ts')['ask_q'].mean()
                ask_qtys.append(ask_chunk)
            
            # Aggregate chunks
            total_bid_qty = pd.concat(bid_qtys).groupby(level=0).mean()
            total_ask_qty = pd.concat(ask_qtys).groupby(level=0).mean()
            
            df_golden['tob_bid_qty_1s'] = total_bid_qty
            df_golden['tob_ask_qty_1s'] = total_ask_qty
            
            # Fill missing
            df_golden['tob_bid_qty_1s'] = df_golden['tob_bid_qty_1s'].fillna(method='ffill').fillna(0)
            df_golden['tob_ask_qty_1s'] = df_golden['tob_ask_qty_1s'].fillna(method='ffill').fillna(0)
            
        except Exception as e:
            print(f"⚠️  Error processing ticker: {e}")
            df_golden['tob_bid_qty_1s'] = 0
            df_golden['tob_ask_qty_1s'] = 0
    else:
        print("⚠️  No BookTicker found")
        df_golden['tob_bid_qty_1s'] = 0
        df_golden['tob_ask_qty_1s'] = 0
        
    # 4. Save
    output_path = OUTPUT_DIR / f"{symbol}-60s-golden-{YEAR}-{MONTH}.csv"
    df_golden.reset_index().to_csv(output_path, index=False)
    print(f"✅ Saved {len(df_golden)} rows to {output_path.name}")
    
    gc.collect()

import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", help="Process specific symbol")
    args = parser.parse_args()
    
    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = SYMBOLS
        
    for symbol in symbols:
        try:
            process_symbol(symbol)
        except Exception as e:
            print(f"❌ Critical error for {symbol}: {e}")

if __name__ == "__main__":
    main()
