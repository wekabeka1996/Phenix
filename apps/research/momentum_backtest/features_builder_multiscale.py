"""
Multi-scale Feature Builder

Generates features for 1s, 5s, 10s bar horizons with multiple window variations.
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    GOLDEN_DATASET_TEMPLATE,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)
from apps.research.momentum_backtest.regime_labeling import add_regime_labels

def build_multiscale_features(symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH):
    horizons = [1, 5, 10]
    
    # Define window variations (in seconds)
    tfi_windows = [20, 60, 120]
    depth_spans = [5, 20, 60]
    ema_short_windows = [60, 180]
    ema_long_windows = [300, 900]
    vol_windows = [60, 300]
    
    for h in horizons:
        print(f"\n{'='*60}")
        print(f"Processing Horizon: {h}s")
        print(f"{'='*60}")
        
        output_filename = FEATURES_DATASET_TEMPLATE.replace("features", f"features-h{h}")
        output_path = get_processed_file_path(output_filename, symbol, year, month)
        
        if output_path.exists():
            print(f"Output file {output_path} already exists. Skipping.")
            continue
            
        # Load Golden Data
        input_filename = GOLDEN_DATASET_TEMPLATE.replace("1s", f"{h}s")
        input_path = get_processed_file_path(input_filename, symbol, year, month)
        
        if not input_path.exists():
            print(f"Input file {input_path} not found. Skipping.")
            continue
            
        print(f"Loading {input_path}...")
        df = pd.read_csv(input_path)
        df['ts'] = pd.to_datetime(df['ts'])
        
        # Helper to convert seconds to bars
        def sec_to_bars(sec):
            return max(1, int(sec // h))
        
        epsilon = 1e-9
        
        # --- 1. TFI ---
        for w_sec in tfi_windows:
            w_bars = sec_to_bars(w_sec)
            print(f"  Computing TFI {w_sec}s ({w_bars} bars)...")
            
            buy_vol = df['buy_vol_1s'].rolling(window=w_bars, min_periods=1).sum()
            sell_vol = df['sell_vol_1s'].rolling(window=w_bars, min_periods=1).sum()
            tfi_raw = (buy_vol - sell_vol) / (buy_vol + sell_vol + epsilon)
            
            # Phi normalize
            col_name = f'tfi_phi_{w_sec}s'
            df[col_name] = (tfi_raw.clip(-1, 1) + 1) / 2
            
        # --- 2. ToB Imbalance (Depth Proxy) ---
        # Note: 'depth_imbalance' in previous task was actually ToB imbalance
        # User config asks for 'depth_window_sec'.
        # In V1 builder: 
        #   tob_imbalance = (bid-ask)/(bid+ask) smoothed by span=10
        #   depth_imbalance = (bid-ask)/(bid+ask) raw
        # Let's standardize.
        # We will compute 'depth_imbalance' using ToB qty, smoothed by 'depth_window_sec'.
        
        tob_imb_raw = (df['tob_bid_qty_1s'] - df['tob_ask_qty_1s']) / (df['tob_bid_qty_1s'] + df['tob_ask_qty_1s'] + epsilon)
        
        for w_sec in depth_spans:
            w_bars = sec_to_bars(w_sec)
            print(f"  Computing Depth Imbalance {w_sec}s (span={w_bars})...")
            
            # Use EWM for smoothing
            depth_smooth = tob_imb_raw.ewm(span=w_bars, adjust=False).mean()
            
            # Phi normalize
            col_name = f'depth_imbalance_phi_{w_sec}s'
            df[col_name] = (depth_smooth.clip(-1, 1) + 1) / 2
            
            # Also compute ToB phi (using same windows or fixed?)
            # User config separates 'depth_window_sec'.
            # But 'tob_phi' in V1 was span=10.
            # Let's generate 'tob_phi' variations too, using same windows?
            # Or just use the same feature for both if they are redundant.
            # In V1, 'tob_imbalance' (span 10) and 'depth_imbalance' (raw) were distinct.
            # Let's create 'tob_phi_{w_sec}s' as well.
            col_name_tob = f'tob_phi_{w_sec}s'
            df[col_name_tob] = df[col_name] # Same logic for now
            
        # --- 3. EMA Bias ---
        # We need pairs of (short, long).
        # Optuna will pick one short and one long.
        # We should pre-compute ALL EMAs, then compute bias pairs?
        # Or compute specific bias pairs?
        # User wants to optimize ema_short_sec and ema_long_sec independently.
        # So we should compute 'ema_bias_short_phi_{w}s' for w in [60, 180]
        # And 'ema_bias_long_phi_{w}s' for w in [300, 900]
        # Wait, bias is (price - ema) / ema?
        # In V1 builder:
        #   ema_bias_short = (ema_short - ema_long) / ema_long  <-- PROD formula
        #   ema_bias_long = (ema_long - ema_very_long) / ema_very_long
        # This dependency chain is complex for independent optimization.
        # If we want to optimize `ema_short_sec`, does it mean the "Short" component of the "Short Bias"?
        # Or does it mean the "Short Bias" feature itself uses `ema_short_sec` as its primary EMA?
        
        # Let's simplify:
        # ema_bias_short_phi_{w}s = (price - EMA(w)) / EMA(w) normalized?
        # NO, V1 used (EMA3 - EMA7) / EMA7.
        # If user selects ema_short_sec=60, does it mean EMA(60)?
        # Let's assume user wants:
        #   ema_bias_short = (Price - EMA_short) / EMA_short
        #   ema_bias_long = (Price - EMA_long) / EMA_long
        # This is the standard "Trend Bias" definition.
        # V1 builder had complex "Prod Parity" logic.
        # Let's stick to simple Price vs EMA for this R&D task to allow flexible windows.
        
        for w_sec in ema_short_windows:
            w_bars = sec_to_bars(w_sec)
            print(f"  Computing EMA Short {w_sec}s...")
            ema = df['close_1s'].ewm(span=w_bars, adjust=False).mean()
            bias = (df['close_1s'] - ema) / ema
            
            # Normalize: assume bias is within ±0.05 (5%)
            col_name = f'ema_bias_short_phi_{w_sec}s'
            df[col_name] = ((bias / 0.005).clip(-1, 1) + 1) / 2 # 0.5% deviation scale
            
        for w_sec in ema_long_windows:
            w_bars = sec_to_bars(w_sec)
            print(f"  Computing EMA Long {w_sec}s...")
            ema = df['close_1s'].ewm(span=w_bars, adjust=False).mean()
            bias = (df['close_1s'] - ema) / ema
            
            col_name = f'ema_bias_long_phi_{w_sec}s'
            df[col_name] = ((bias / 0.01).clip(-1, 1) + 1) / 2 # 1.0% deviation scale
            
        # --- 4. Volatility State ---
        # Range / SMA(Range)
        for w_sec in vol_windows:
            w_bars = sec_to_bars(w_sec)
            print(f"  Computing Volatility {w_sec}s...")
            
            rolling_high = df['high_1s'].rolling(window=w_bars, min_periods=1).max()
            rolling_low = df['low_1s'].rolling(window=w_bars, min_periods=1).min()
            price_range = rolling_high - rolling_low
            
            # Baseline: 10x window? Or fixed?
            # V1 used window=60, baseline=10 (bars? no, sma_length=10).
            # Let's use baseline = 10 * w_bars
            baseline_window = w_bars * 10
            range_sma = price_range.rolling(window=baseline_window, min_periods=1).mean()
            
            vol_state = price_range / (range_sma + epsilon)
            
            col_name = f'volatility_state_phi_{w_sec}s'
            df[col_name] = (vol_state.clip(0, 3.0) / 3.0)
            
            # Also compute volume_spike (Volume / SMA(Volume))
            vol_sum = df['vol_1s'].rolling(window=w_bars, min_periods=1).sum()
            vol_sma = vol_sum.rolling(window=baseline_window, min_periods=1).mean()
            vol_spike = vol_sum / (vol_sma + epsilon)
            
            col_name_vol = f'volume_spike_phi_{w_sec}s'
            df[col_name_vol] = (vol_spike.clip(0, 3.0) / 3.0)

        # --- 5. Macro / Delta Price (Fixed for now or default) ---
        # Delta Price (1 bar)
        delta_pct = df['close_1s'].diff() / (df['close_1s'].shift(1) + epsilon)
        df['delta_price_phi'] = ((delta_pct / 0.001).clip(-1, 1) + 1) / 2 # 0.1% scale
        
        # Macro (placeholder 0.5 if missing)
        df['macro_phi'] = 0.5 
        
        # Funding
        df['funding_rate_1s'] = df['funding_rate_1s'] # Keep raw for veto
        
        # --- 6. Regime Labeling ---
        print(f"  Computing Regime Labels...")
        df = add_regime_labels(df, trend_window_sec=300, vol_window_sec=300, bar_horizon_sec=h)
        
        # Save
        output_filename = FEATURES_DATASET_TEMPLATE.replace("features", f"features-h{h}")
        output_path = get_processed_file_path(output_filename, symbol, year, month)
        
        print(f"Saving to {output_path}...")
        df.to_csv(output_path, index=False)
        print("Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Feature Builder for Momentum Backtest")
    parser.add_argument("--symbol", type=str, default=DEFAULT_SYMBOL)
    parser.add_argument("--year", type=str, default=DEFAULT_YEAR)
    parser.add_argument("--month", type=str, default=DEFAULT_MONTH)
    args = parser.parse_args()
    
    build_multiscale_features(symbol=args.symbol, year=args.year, month=args.month)
