"""
Build features for Aurora Optuna
"""
import pandas as pd
import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.config import get_data_path, GOLDEN_DATASET_TEMPLATE, FEATURES_DATASET_TEMPLATE, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

def resample_data(df, timeframe):
    """Resample 1m/60s data to target timeframe"""
    df = df.copy()
    df['ts'] = pd.to_datetime(df['ts'])
    df = df.set_index('ts')
    
    rule = '1min'
    suffix = '_60s'
    if timeframe == '3m':
        rule = '3min'
        suffix = '_180s'
    elif timeframe == '5m':
        rule = '5min'
        suffix = '_300s'
    
    # Identify columns
    agg_dict = {}
    rename_dict = {}
    
    # OHLCV
    if 'open_1s' in df.columns:
        agg_dict['open_1s'] = 'first'
        agg_dict['high_1s'] = 'max'
        agg_dict['low_1s'] = 'min'
        agg_dict['close_1s'] = 'last'
        agg_dict['vol_1s'] = 'sum'
        rename_dict = {
            'open_1s': f'open{suffix}',
            'high_1s': f'high{suffix}',
            'low_1s': f'low{suffix}',
            'close_1s': f'close{suffix}',
            'vol_1s': f'vol{suffix}'
        }
        
    # OBI / TFI Columns
    if 'buy_vol_1s' in df.columns:
        agg_dict['buy_vol_1s'] = 'sum'
        agg_dict['sell_vol_1s'] = 'sum'
        rename_dict['buy_vol_1s'] = f'buy_vol{suffix}'
        rename_dict['sell_vol_1s'] = f'sell_vol{suffix}'
        
    if 'tob_bid_qty_1s' in df.columns:
        agg_dict['tob_bid_qty_1s'] = 'mean'
        agg_dict['tob_ask_qty_1s'] = 'mean'
        rename_dict['tob_bid_qty_1s'] = f'tob_bid_qty{suffix}'
        rename_dict['tob_ask_qty_1s'] = f'tob_ask_qty{suffix}'
    
    # BTC Close
    if 'btc_close_1s' in df.columns:
        agg_dict['btc_close_1s'] = 'last'
    
    # Resample
    df_resampled = df.resample(rule).agg(agg_dict).dropna()
    df_resampled = df_resampled.rename(columns=rename_dict)
    
    return df_resampled.reset_index()

def build_features(symbol, year, month, timeframe='1m'):
    print(f"Building Aurora features for {symbol} {year}-{month} ({timeframe})...")
    
    # Load 60s Golden data (source for all timeframes)
    input_path = get_data_path(GOLDEN_DATASET_TEMPLATE, symbol, year, month)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return
    
    df = pd.read_csv(input_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Load BTC data for macro sync (if not BTC itself)
    btc_df = None
    if symbol != "BTCUSDT":
        btc_path = get_data_path(GOLDEN_DATASET_TEMPLATE, "BTCUSDT", year, month)
        if btc_path.exists():
            btc_df = pd.read_csv(btc_path)
            btc_df['ts'] = pd.to_datetime(btc_df['ts'])
            
            # Handle both golden 60s format and older 1s format
            if 'close_60s' in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df['close_60s']
            elif 'close_1s' in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df['close_1s']
            else:
                print(f"Warning: BTC close column not found in {btc_path}")
                btc_df = None
        else:
            print(f"Warning: BTC data not found at {btc_path}")
            btc_df = None
    else:
        btc_df = None
    
    # Handle Timeframe
    bar_seconds = 60
    output_template = FEATURES_DATASET_TEMPLATE
    
    if timeframe == '3m':
        print("Resampling to 3m...")
        df = resample_data(df, '3m')
        if btc_df is not None:
            btc_df = resample_data(btc_df, '3m')
        bar_seconds = 180
        output_template = FEATURES_DATASET_TEMPLATE_3M
        
    elif timeframe == '5m':
        print("Resampling to 5m...")
        df = resample_data(df, '5m')
        if btc_df is not None:
            btc_df = resample_data(btc_df, '5m')
        bar_seconds = 300
        output_template = FEATURES_DATASET_TEMPLATE_5M
    
    # Build features with default params
    default_params = {
        'ema_period_short': 3,
        'ema_period_long': 7,
        'volume_window_sec': 300,  # 5 mins
        'volume_sma_length': 5,
        'volume_cap_max': 3.0,
        'liquidity_depth_half': 1000.0,
        'liquidity_kappa_min': 0.3
    }
    
    df_features = build_aurora_features(df, btc_df, default_params, bar_seconds=bar_seconds)
    
    # Save
    output_path = get_data_path(output_template, symbol, year, month)
    print(f"Saving to {output_path}...")
    df_features.to_csv(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, required=True)
    parser.add_argument("--year", type=str, default="2024")
    parser.add_argument("--month", type=str, default="01")
    parser.add_argument("--timeframe", type=str, default="1m", choices=["1m", "3m", "5m"])
    args = parser.parse_args()
    
    build_features(args.symbol, args.year, args.month, args.timeframe)
