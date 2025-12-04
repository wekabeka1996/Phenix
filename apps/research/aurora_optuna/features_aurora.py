"""
Aurora Core Features (40% subset)
Implements: EMA bias, Volume spike, Macro sync, Liquidity, Risk score
"""
import pandas as pd
import numpy as np

def get_col_name(df, base_name):
    """Get column name with correct suffix (_1s, _5s, _60s, _180s, _300s)"""
    for suffix in ['_300s', '_180s', '_60s', '_1s', '_5s']:
        if f'{base_name}{suffix}' in df.columns:
            return f'{base_name}{suffix}'
    return base_name  # Fallback to no suffix

def compute_ema(series, period):
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()

def compute_ema_bias(df, period_short=3, period_long=7, clamp_min=-0.02, clamp_max=0.02):
    """
    EMA Bias = (EMA_short - EMA_long) / EMA_long
    Normalized to [0, 1]
    """
    close_col = get_col_name(df, 'close')
    
    ema_short = compute_ema(df[close_col], period_short)
    ema_long = compute_ema(df[close_col], period_long)
    
    bias_raw = (ema_short - ema_long) / (ema_long + 1e-9)
    bias_clamped = np.clip(bias_raw, clamp_min, clamp_max)
    
    # Normalize to [0, 1]: 0 = bearish, 0.5 = neutral, 1 = bullish
    ema_bias = (bias_clamped - clamp_min) / (clamp_max - clamp_min)
    return ema_bias

def compute_volume_spike(df, window_sec=60, sma_length=5, cap_max=3.0, bar_seconds=60):
    """
    Volume Spike = current_volume / SMA(volume, sma_length)
    Normalized to [0, 1]
    """
    vol_col = get_col_name(df, 'vol')
    window_bars = max(1, window_sec // bar_seconds)
    
    vol_rolling = df[vol_col].rolling(window=window_bars).sum()
    vol_sma = vol_rolling.rolling(window=sma_length).mean()
    
    spike = vol_rolling / (vol_sma + 1e-9)
    spike_capped = np.clip(spike, 0, cap_max)
    
    volume_spike = spike_capped / cap_max
    return volume_spike

def compute_macro_sync(df, btc_df, window=60, min_buffer=3):
    """
    Macro Sync = correlation with BTC returns
    Normalized to [0, 1] from [-1, 1]
    """
    close_col = get_col_name(df, 'close')
    
    df = df.set_index('ts') if 'ts' in df.columns else df
    btc_df = btc_df.set_index('ts') if 'ts' in btc_df.columns else btc_df
    
    # Align BTC data
    btc_close_col = get_col_name(btc_df, 'close')
    if btc_close_col not in btc_df.columns and 'btc_close_1s' in btc_df.columns:
        btc_close_col = 'btc_close_1s'
        
    # Reindex BTC to match symbol timestamps (handles resampling alignment)
    btc_aligned = btc_df[btc_close_col].reindex(df.index, method='ffill')
    
    symbol_returns = df[close_col].pct_change()
    btc_returns = btc_aligned.pct_change()
    
    corr = symbol_returns.rolling(window).corr(btc_returns)
    macro_sync = (corr + 1.0) / 2.0
    macro_sync = macro_sync.fillna(0.5)
    
    return macro_sync.values

def compute_liquidity_kappa(df, depth_half=1000.0, kappa_min=0.3, kappa_max=1.0):
    """
    Liquidity Kappa = depth / (depth + depth_half)
    Placeholder: use volume as proxy for depth
    """
    vol_col = get_col_name(df, 'vol')
    depth_proxy = df[vol_col].rolling(12).mean()
    kappa = depth_proxy / (depth_proxy + depth_half)
    kappa = np.clip(kappa, kappa_min, kappa_max)
    
    liquidity = (kappa - kappa_min) / (kappa_max - kappa_min)
    return liquidity

def compute_risk_score(df, weights={'delta_price': 0.3, 'volume': 0.4, 'volatility': 0.3}):
    """
    Risk Score (simplified): combination of price delta, volume, volatility
    Lower score = safer to trade
    """
    close_col = get_col_name(df, 'close')
    high_col = get_col_name(df, 'high')
    low_col = get_col_name(df, 'low')
    vol_col = get_col_name(df, 'vol')
    
    delta_price = df[close_col].diff().abs() / (df[close_col] + 1e-9)
    delta_norm = np.clip(delta_price / (delta_price.quantile(0.95) + 1e-9), 0, 1)
    
    vol_norm = df[vol_col] / (df[vol_col].quantile(0.95) + 1e-9)
    vol_norm = np.clip(vol_norm, 0, 1)
    
    high_low_range = (df[high_col] - df[low_col]) / (df[close_col] + 1e-9)
    vol_range_norm = np.clip(high_low_range / (high_low_range.quantile(0.95) + 1e-9), 0, 1)
    
    risk_score = (
        weights['delta_price'] * delta_norm +
        weights['volume'] * vol_norm +
        weights['volatility'] * vol_range_norm
    )
    
    return risk_score

def compute_obi(df, window_sec=60, bar_seconds=60):
    """
    Order Book Imbalance = (BidQty - AskQty) / (BidQty + AskQty)
    Normalized to [-1, 1]
    """
    bid_col = get_col_name(df, 'tob_bid_qty')
    ask_col = get_col_name(df, 'tob_ask_qty')
    
    # Raw OBI
    obi_raw = (df[bid_col] - df[ask_col]) / (df[bid_col] + df[ask_col] + 1e-9)
    
    # Smooth it
    window_bars = max(1, window_sec // bar_seconds)
    obi_smoothed = obi_raw.rolling(window=window_bars).mean()
    
    return obi_smoothed

def compute_tfi(df, window_sec=60, bar_seconds=60):
    """
    Trade Flow Imbalance = (BuyVol - SellVol) / (BuyVol + SellVol)
    Normalized to [-1, 1]
    """
    buy_col = get_col_name(df, 'buy_vol')
    sell_col = get_col_name(df, 'sell_vol')
    
    # Raw TFI
    tfi_raw = (df[buy_col] - df[sell_col]) / (df[buy_col] + df[sell_col] + 1e-9)
    
    # Smooth it
    window_bars = max(1, window_sec // bar_seconds)
    tfi_smoothed = tfi_raw.rolling(window=window_bars).mean()
    
    return tfi_smoothed

def compute_volatility_state(df, window_sec=60, sma_length=10, cap_max=3.0, bar_seconds=60):
    """
    Volatility State = current_range / SMA(range, sma_length)
    Normalized to [0, 1]
    
    PHASE 2 FEATURE
    """
    high_col = get_col_name(df, 'high')
    low_col = get_col_name(df, 'low')
    
    # Compute price range
    df['range_temp'] = df[high_col] - df[low_col]
    
    # SMA of range
    range_sma = df['range_temp'].rolling(window=sma_length).mean()
    
    # Volatility ratio
    volatility_ratio = df['range_temp'] / (range_sma + 1e-9)
    volatility_capped = np.clip(volatility_ratio, 0, cap_max)
    
    # Normalize to [0, 1]
    volatility_state = volatility_capped / cap_max
    
    df.drop('range_temp', axis=1, inplace=True, errors='ignore')
    
    return volatility_state.fillna(0.5)

def compute_depth_imbalance(df, use_smoothing=True, depth_half=1000.0):
    """
    Depth Imbalance = (asks + depth_half) / (bids + depth_half)
    With optional Laplace smoothing
    
    PHASE 2 FEATURE
    """
    bid_col = get_col_name(df, 'tob_bid_qty')
    ask_col = get_col_name(df, 'tob_ask_qty')
    
    if use_smoothing:
        # Laplace smoothing
        imbalance = (df[ask_col] + depth_half) / (df[bid_col] + depth_half)
    else:
        # Raw ratio
        imbalance = df[ask_col] / (df[bid_col] + 1e-9)
    
    # Normalize to [0, 1]: <1.0 = bid pressure, >1.0 = ask pressure
    # Map 0.5-1.5 → 0-1
    imbalance_norm = (imbalance - 0.5).clip(-0.5, 0.5) + 0.5
    
    return imbalance_norm.fillna(0.5)

def compute_delta_price(df, spike_filter_ms=5000):
    """
    Delta Price = current_price - previous_price
    With spike filtering for reconnection artifacts
    
    PHASE 2 FEATURE
    """
    close_col = get_col_name(df, 'close')
    
    # Compute price change
    delta_price = df[close_col].diff()
    
    # Filter spikes (reconnection artifacts)
    if 'ts' in df.columns:
        ts_diff = df['ts'].diff()
        # Convert timedelta to milliseconds
        ts_diff_ms = ts_diff.dt.total_seconds() * 1000
        delta_price = delta_price.where(ts_diff_ms <= spike_filter_ms, 0)
    
    # Normalize by rolling std (optional - helps with signal strength)
    delta_std = delta_price.rolling(window=20).std()
    delta_normalized = delta_price / (delta_std + 1e-9)
    delta_normalized = np.clip(delta_normalized, -3, 3)  # Clip to ±3 sigma
    
    # Map to [0, 1]: -3 → 0, 0 → 0.5, +3 → 1
    delta_scaled = (delta_normalized + 3) / 6
    
    return delta_scaled.fillna(0.5)

def build_aurora_features(df, btc_df, params, bar_seconds=60):
    """
    Build all Aurora core features (Phase 1 + Phase 2)
    """
    df = df.copy()
    
    # ===== PHASE 1 FEATURES (40%) =====
    
    # 1. EMA Bias
    df['ema_bias'] = compute_ema_bias(
        df,
        period_short=params.get('ema_period_short', 3),
        period_long=params.get('ema_period_long', 7),
        clamp_min=params.get('ema_clamp_min', -0.02),
        clamp_max=params.get('ema_clamp_max', 0.02)
    )
    
    # 2. Volume Spike
    df['volume_spike'] = compute_volume_spike(
        df,
        window_sec=params.get('volume_window_sec', 60),
        sma_length=params.get('volume_sma_length', 5),
        cap_max=params.get('volume_cap_max', 3.0),
        bar_seconds=bar_seconds
    )
    
    # 3. Macro Sync (BTC correlation)
    if btc_df is not None:
        macro_window = params.get('macro_sync_window', 60)
        df['macro_sync'] = compute_macro_sync(df, btc_df, window=macro_window)
    else:
        df['macro_sync'] = 0.5  # Neutral
    
    # 4. Liquidity
    df['liquidity'] = compute_liquidity_kappa(
        df,
        depth_half=params.get('liquidity_depth_half', 1000.0),
        kappa_min=params.get('liquidity_kappa_min', 0.3)
    )
    
    # 5. Risk Score
    risk_weights = {
        'delta_price': params.get('risk_weight_delta', 0.3),
        'volume': params.get('risk_weight_volume', 0.4),
        'volatility': params.get('risk_weight_volatility', 0.3)
    }
    df['risk_score'] = compute_risk_score(df, weights=risk_weights)
    
    # 6. OBI (Order Book Imbalance)
    df['obi'] = compute_obi(
        df,
        window_sec=params.get('obi_window_sec', 60),
        bar_seconds=bar_seconds
    )
    
    # 7. TFI (Trade Flow Imbalance)
    df['tfi'] = compute_tfi(
        df,
        window_sec=params.get('tfi_window_sec', 60),
        bar_seconds=bar_seconds
    )
    
    # ===== PHASE 2 FEATURES (20%) =====
    
    # 8. Volatility State
    df['volatility_state'] = compute_volatility_state(
        df,
        window_sec=params.get('volatility_window_sec', 60),
        sma_length=params.get('volatility_sma_length', 10),
        cap_max=params.get('volatility_cap_max', 3.0),
        bar_seconds=bar_seconds
    )
    
    # 9. Depth Imbalance
    df['depth_imbalance'] = compute_depth_imbalance(
        df,
        use_smoothing=params.get('depth_imbalance_smoothing', True),
        depth_half=params.get('liquidity_depth_half', 1000.0)
    )
    
    # 10. Delta Price
    df['delta_price'] = compute_delta_price(
        df,
        spike_filter_ms=params.get('delta_price_spike_filter_ms', 5000)
    )
    
    # 11. REGIME LABELING (Aurora integration!)
    from apps.research.aurora_optuna.regime_labeling import add_regime_labels_aurora
    df = add_regime_labels_aurora(df, params)
    
    # Add close_5s for backtest engine (using close column as proxy if not 5s)
    close_col = get_col_name(df, 'close')
    if 'close_5s' not in df.columns:
        df['close_5s'] = df[close_col]
    
    return df.dropna()
