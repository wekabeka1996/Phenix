import pandas as pd
import numpy as np
from pathlib import Path

from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    GOLDEN_DATASET_TEMPLATE,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)

def build_features(symbol: str = DEFAULT_SYMBOL, year: str = DEFAULT_YEAR, month: str = DEFAULT_MONTH):
    """
    Load Golden Dataset and compute features.
    """
    input_path = get_processed_file_path(GOLDEN_DATASET_TEMPLATE, symbol, year, month)
    output_path = get_processed_file_path(FEATURES_DATASET_TEMPLATE, symbol, year, month)
    
    if not input_path.exists():
        print(f"Input file {input_path} does not exist. Run ETL first.")
        return

    print(f"Loading Golden Dataset from {input_path}...")
    df = pd.read_csv(input_path)
    
    # Ensure sorted by ts
    df.sort_values('ts', inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    print("Computing features...")
    
    # 1. TFI (1m)
    # Rolling 60s Buy/Sell Volume
    # Since data is 1s bars, window=60
    buy_vol_60s = df['buy_vol_1s'].rolling(window=60, min_periods=1).sum()
    sell_vol_60s = df['sell_vol_1s'].rolling(window=60, min_periods=1).sum()
    
    epsilon = 1e-9
    df['tfi_1m'] = (buy_vol_60s - sell_vol_60s) / (buy_vol_60s + sell_vol_60s + epsilon)
    
    # 2. ToB Imbalance
    # Raw: (Bid - Ask) / (Bid + Ask)
    tob_imb_raw = (df['tob_bid_qty_1s'] - df['tob_ask_qty_1s']) / (df['tob_bid_qty_1s'] + df['tob_ask_qty_1s'] + epsilon)
    # Smoothed EMA 10-15s. Let's use span=10.
    df['tob_imbalance'] = tob_imb_raw.ewm(span=10, adjust=False).mean().clip(-1, 1)
    
    # 3. EMA Bias
    # Short: 1m = 60s
    # Long: 7m = 420s
    ema_1m = df['close_1s'].ewm(span=60, adjust=False).mean()
    ema_7m = df['close_1s'].ewm(span=420, adjust=False).mean()
    
    df['ema_bias_short'] = (df['close_1s'] - ema_1m) / ema_1m
    df['ema_bias_long'] = (df['close_1s'] - ema_7m) / ema_7m
    
    # 4. Volatility State
    # vol_60s / SMA(vol_60s, 3600)
    # Vol here refers to Volume or Price Volatility?
    # Context says "vol_60s / SMA(vol_60s, 3600)". Usually means Volume.
    # But for scalping, price volatility (ATR) is also useful.
    # Let's stick to the prompt: "vol_60s" likely means Volume 60s sum.
    vol_60s = df['vol_1s'].rolling(window=60, min_periods=1).sum()
    vol_baseline = vol_60s.rolling(window=3600, min_periods=1).mean()
    df['vol_state'] = vol_60s / (vol_baseline + epsilon)
    
    # 5. Dependency Features (BNB vs BTC) - PROD-style
    # Import dependency module
    from apps.research.momentum_backtest.dependency_features import add_dependency_features
    
    if 'btc_close_1s' in df.columns and df['btc_close_1s'].notna().sum() > 0:
        print("  Computing dependency features (BNB vs BTC)...")
        print("    - Rolling beta (1h window, winsorized returns)")
        print("    - Rolling Pearson correlation")
        
        # Add dep_beta_1h and dep_corr_1h columns
        df = add_dependency_features(
            df,
            price_col_alt='close_1s',
            price_col_hub='btc_close_1s',
            window_secs=3600,
            min_periods=600
        )
        
        # Use correlation as macro_corr_1h (primary dependency metric)
        df['macro_corr_1h'] = df['dep_corr_1h']
        
        print(f"    ✅ dep_beta_1h: mean={df['dep_beta_1h'].mean():.3f}, "
              f"std={df['dep_beta_1h'].std():.3f}, "
              f"range=[{df['dep_beta_1h'].min():.3f}, {df['dep_beta_1h'].max():.3f}]")
        print(f"    ✅ dep_corr_1h: mean={df['dep_corr_1h'].mean():.3f}, "
              f"std={df['dep_corr_1h'].std():.3f}, "
              f"range=[{df['dep_corr_1h'].min():.3f}, {df['dep_corr_1h'].max():.3f}]")
    else:
        print("  WARNING: btc_close_1s not found or empty, using fallback")
        df['dep_beta_1h'] = 0.0
        df['dep_corr_1h'] = 0.0
        df['macro_corr_1h'] = 0.0
    
    # ================================================================
    # PHI-NORMALIZATION (PROD PARITY)
    # ================================================================
    # Production (decision_making.py) normalizes ALL features to [0,1]
    # before computing signal score. We replicate this here.
    # Keep raw features for reference, add _phi versions for scoring.
    
    print("  Applying PROD-style phi-normalization...")
    
    # TFI: [-1, 1] → [0, 1]
    # tfi_phi = (tfi_raw + 1) / 2
    df['tfi_phi'] = (df['tfi_1m'].clip(-1, 1) + 1) / 2
    
    # ToB/OBI: [-1, 1] → [0, 1]
    # obi_phi = (obi_raw + 1) / 2
    df['tob_phi'] = (df['tob_imbalance'].clip(-1, 1) + 1) / 2
    
    # EMA Bias Short/Long: already computing as percentage deviation
    # Prod normalizes (ema_short - ema_long) / ema_long → [0,1]
    # Our current ema_bias is (price - ema) / ema which can be >1 or <0
    # Need to match prod's exact formula from feature_engineering.py
    
    # From prod: ema_bias = (ema_short - ema_long) / ema_long, normalized to [0,1]
    # calculation_engine.py shows: bias = (short - long) / long, then clipped
    # Let's recalculate to match prod exactly
    
    # Recalculate EMA bias to match prod (EMA3 vs EMA7 for short)
    ema_3m = df['close_1s'].ewm(span=180, adjust=False).mean()  # 3min = 180s
    ema_7m = df['close_1s'].ewm(span=420, adjust=False).mean()  # 7min = 420s
    ema_15m = df['close_1s'].ewm(span=900, adjust=False).mean()  # 15min
    ema_60m = df['close_1s'].ewm(span=3600, adjust=False).mean()  # 60min
    
    # Prod formula: (short - long) / long
    ema_bias_short_raw = (ema_3m - ema_7m) / (ema_7m + epsilon)
    ema_bias_long_raw = (ema_15m - ema_60m) / (ema_60m + epsilon)
    
    # Normalize to [0, 1] via sigmoid-like transform
    # Prod uses: tanh-style or direct clipping after scaling
    # From calculation_engine.py: clips to [-0.05, 0.05] then maps to [0,1]
    # Formula: clamp( (bias / 0.05 + 1) / 2, 0, 1)
    
    df['ema_bias_short_phi'] = ((ema_bias_short_raw / 0.05).clip(-1, 1) + 1) / 2
    df['ema_bias_long_phi'] = ((ema_bias_long_raw / 0.05).clip(-1, 1) + 1) / 2
    
    # Update old columns to match (for backward compatibility if needed)
    df['ema_bias_short'] = df['ema_bias_short_phi']
    df['ema_bias_long'] = df['ema_bias_long_phi']
    
    # Vol State: already ratio-based, normalize to [0,1]
    # Prod caps at 3x and normalizes
    # vol_state_phi = min(vol_current / vol_baseline, 3.0) / 3.0
    df['vol_state_phi'] = (df['vol_state'].clip(0, 3.0) / 3.0)
    
    # Macro Corr: [-1, 1] → [0, 1]
    # macro_phi = (macro_corr + 1) / 2
    df['macro_phi'] = (df['macro_corr_1h'].clip(-1, 1) + 1) / 2
    
    print(f"    ✅ Phi-features created:")
    print(f"       tfi_phi: [{df['tfi_phi'].min():.3f}, {df['tfi_phi'].max():.3f}]")
    print(f"       tob_phi: [{df['tob_phi'].min():.3f}, {df['tob_phi'].max():.3f}]")
    print(f"       ema_bias_short_phi: [{df['ema_bias_short_phi'].min():.3f}, {df['ema_bias_short_phi'].max():.3f}]")
    print(f"       ema_bias_long_phi: [{df['ema_bias_long_phi'].min():.3f}, {df['ema_bias_long_phi'].max():.3f}]")
    print(f"       vol_state_phi: [{df['vol_state_phi'].min():.3f}, {df['vol_state_phi'].max():.3f}]")
    print(f"       macro_phi: [{df['macro_phi'].min():.3f}, {df['macro_phi'].max():.3f}]")

    
    # 6. Delta Price (price momentum)
    # Production: delta_price = current_price - previous_price
    # Normalized later as percentage change
    df['delta_price'] = df['close_1s'].diff()
    
    # 7. Volume Spike
    # Formula: volume_spike = current_volume / SMA(volume, window)
    # Production config: window_sec: 60, sma_length: 5
    vol_current = df['vol_1s'].rolling(window=60, min_periods=1).sum()
    vol_sma = vol_current.rolling(window=5, min_periods=1).mean()
    df['volume_spike'] = vol_current / (vol_sma + epsilon)
    
    # 8. Volatility State (price volatility, not volume)
    # Production: current_range / SMA(historical_ranges)
    # window_sec: 60, sma_length: 10
    # Range = high - low over rolling window
    rolling_high = df['high_1s'].rolling(window=60, min_periods=1).max()
    rolling_low = df['low_1s'].rolling(window=60, min_periods=1).min()
    price_range = rolling_high - rolling_low
    range_sma = price_range.rolling(window=10, min_periods=1).mean()
    df['volatility_state'] = price_range / (range_sma + epsilon)
    
    # 9. Depth Imbalance
    # Production uses depth_half smoothing: (asks + depth_half) / (bids + depth_half)
    # Then normalize. We don't have L2 depth in 1s data, so use orderbook imbalance as proxy
    # Use tob_bid_qty vs tob_ask_qty as depth proxy
    depth_half = 1000.0  # Production config value
    # Ratio formula from production: (asks + depth_half) / (bids + depth_half)
    # This gives ratio > 1 if more asks, < 1 if more bids
    # Convert to imbalance: (bids - asks) / (bids + asks)
    df['depth_imbalance'] = (df['tob_bid_qty_1s'] - df['tob_ask_qty_1s']) / \
                            (df['tob_bid_qty_1s'] + df['tob_ask_qty_1s'] + epsilon)
    
    # 10. Funding Norm
    # z-score or deviation.
    # Let's use simple deviation from mean of last 24h (86400s)?
    # Or just raw funding rate if it's already small.
    # Prompt says "z-score or deviation".
    # Let's do z-score over a long window, e.g. 3 days? Or just 1 day.
    # Funding rate changes every 8h usually, but here it's 1s series.
    # Let's use a rolling window of 24h (86400s).
    fr_mean = df['funding_rate_1s'].rolling(window=86400, min_periods=1).mean()
    fr_std = df['funding_rate_1s'].rolling(window=86400, min_periods=1).std()
    df['funding_norm'] = (df['funding_rate_1s'] - fr_mean) / (fr_std + epsilon)
    
    # ================================================================
    # PHI-NORMALIZATION (PROD PARITY)
    # ================================================================
    # Production (decision_making.py) normalizes ALL features to [0,1]
    # before computing signal score. We replicate this here.
    # Keep raw features for reference, add _phi versions for scoring.
    
    print("  Applying PROD-style phi-normalization...")
    
    # TFI: [-1, 1] → [0, 1]
    # tfi_phi = (tfi_raw + 1) / 2
    df['tfi_phi'] = (df['tfi_1m'].clip(-1, 1) + 1) / 2
    
    # ToB/OBI: [-1, 1] → [0, 1]
    # obi_phi = (obi_raw + 1) / 2
    df['tob_phi'] = (df['tob_imbalance'].clip(-1, 1) + 1) / 2
    
    # EMA Bias Short/Long: already computing as percentage deviation
    # Prod normalizes (ema_short - ema_long) / ema_long → [0,1]
    # Our current ema_bias is (price - ema) / ema which can be >1 or <0
    # Need to match prod's exact formula from feature_engineering.py
    
    # From prod: ema_bias = (ema_short - ema_long) / ema_long, normalized to [0,1]
    # calculation_engine.py shows: bias = (short - long) / long, then clipped
    # Let's recalculate to match prod exactly
    
    # Recalculate EMA bias to match prod (EMA3 vs EMA7 for short)
    ema_3m = df['close_1s'].ewm(span=180, adjust=False).mean()  # 3min = 180s
    ema_7m = df['close_1s'].ewm(span=420, adjust=False).mean()  # 7min = 420s
    ema_15m = df['close_1s'].ewm(span=900, adjust=False).mean()  # 15min
    ema_60m = df['close_1s'].ewm(span=3600, adjust=False).mean()  # 60min
    
    # Prod formula: (short - long) / long
    ema_bias_short_raw = (ema_3m - ema_7m) / (ema_7m + epsilon)
    ema_bias_long_raw = (ema_15m - ema_60m) / (ema_60m + epsilon)
    
    # Normalize to [0, 1] via sigmoid-like transform
    # Prod uses: tanh-style or direct clipping after scaling
    # From calculation_engine.py: clips to [-0.05, 0.05] then maps to [0,1]
    # Formula: clamp( (bias / 0.05 + 1) / 2, 0, 1)
    
    df['ema_bias_short_phi'] = ((ema_bias_short_raw / 0.05).clip(-1, 1) + 1) / 2
    df['ema_bias_long_phi'] = ((ema_bias_long_raw / 0.05).clip(-1, 1) + 1) / 2
    
    # Update old columns to match (for backward compatibility if needed)
    df['ema_bias_short'] = df['ema_bias_short_phi']
    df['ema_bias_long'] = df['ema_bias_long_phi']
    
    # Vol State: already ratio-based, normalize to [0,1]
    # Prod caps at 3x and normalizes
    # vol_state_phi = min(vol_current / vol_baseline, 3.0) / 3.0
    df['vol_state_phi'] = (df['vol_state'].clip(0, 3.0) / 3.0)
    
    # Macro Corr: [-1, 1] → [0, 1]
    # macro_phi = (macro_corr + 1) / 2
    df['macro_phi'] = (df['macro_corr_1h'].clip(-1, 1) + 1) / 2
    
    # === NEW PHI FEATURES ===
    
    # Delta Price: normalize as percentage change, clip to ±2%, map to [0,1]
    # Production likely uses similar approach
    delta_pct = df['delta_price'] / (df['close_1s'].shift(1) + epsilon)
    df['delta_price_phi'] = ((delta_pct / 0.02).clip(-1, 1) + 1) / 2
    
    # Volume Spike: cap at 3.0, normalize to [0,1]
    # Production config: cap_max: 3.0
    df['volume_spike_phi'] = (df['volume_spike'].clip(0, 3.0) / 3.0)
    
    # Volatility State: cap at 3.0, normalize to [0,1]
    # Production config: cap_max: 3.0
    df['volatility_state_phi'] = (df['volatility_state'].clip(0, 3.0) / 3.0)
    
    # Depth Imbalance: [-1, 1] → [0, 1]
    df['depth_imbalance_phi'] = (df['depth_imbalance'].clip(-1, 1) + 1) / 2
    
    print(f"    ✅ Phi-features created:")
    print(f"       tfi_phi: [{df['tfi_phi'].min():.3f}, {df['tfi_phi'].max():.3f}]")
    print(f"       tob_phi: [{df['tob_phi'].min():.3f}, {df['tob_phi'].max():.3f}]")
    print(f"       ema_bias_short_phi: [{df['ema_bias_short_phi'].min():.3f}, {df['ema_bias_short_phi'].max():.3f}]")
    print(f"       ema_bias_long_phi: [{df['ema_bias_long_phi'].min():.3f}, {df['ema_bias_long_phi'].max():.3f}]")
    print(f"       vol_state_phi: [{df['vol_state_phi'].min():.3f}, {df['vol_state_phi'].max():.3f}]")
    print(f"       macro_phi: [{df['macro_phi'].min():.3f}, {df['macro_phi'].max():.3f}]")
    print(f"       delta_price_phi: [{df['delta_price_phi'].min():.3f}, {df['delta_price_phi'].max():.3f}]")
    print(f"       volume_spike_phi: [{df['volume_spike_phi'].min():.3f}, {df['volume_spike_phi'].max():.3f}]")
    print(f"       volatility_state_phi: [{df['volatility_state_phi'].min():.3f}, {df['volatility_state_phi'].max():.3f}]")
    print(f"       depth_imbalance_phi: [{df['depth_imbalance_phi'].min():.3f}, {df['depth_imbalance_phi'].max():.3f}]")

    
    # Select columns
    # Include both raw and phi-normalized features
    cols = [
        'ts', 'open_1s', 'high_1s', 'low_1s', 'close_1s',  # OHLC for backtest
        # Raw features (for reference/analysis)
        'tfi_1m', 'tob_imbalance', 'ema_bias_short', 'ema_bias_long',
        'vol_state', 'macro_corr_1h', 'funding_rate_1s', 'funding_norm',
        'dep_beta_1h', 'dep_corr_1h',
        'delta_price', 'volume_spike', 'volatility_state', 'depth_imbalance',
        # Phi-normalized features (PROD parity, for scoring)
        'tfi_phi', 'tob_phi', 'ema_bias_short_phi', 'ema_bias_long_phi',
        'vol_state_phi', 'macro_phi',
        'delta_price_phi', 'volume_spike_phi', 'volatility_state_phi', 'depth_imbalance_phi'
    ]
    
    # Save
    print(f"Saving Features Dataset to {output_path}...")
    df[cols].to_csv(output_path, index=False)
    print("Done.")

if __name__ == "__main__":
    build_features()
