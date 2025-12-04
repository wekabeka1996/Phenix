"""
Dependency Features Module - PROD-style rolling beta and correlation

Implements relationship modeling between alt (BNB) and hub asset (BTC):
- Rolling beta (β) with winsorization
- Rolling Pearson correlation
- Vectorized implementation for 1s data
"""

import pandas as pd
import numpy as np
from typing import Optional


def winsorize(s: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    """
    Winsorize series by clipping to quantile thresholds.
    
    Args:
        s: Input series (typically returns)
        lower_q: Lower quantile (default 1%)
        upper_q: Upper quantile (default 99%)
        
    Returns:
        Winsorized series
    """
    low = s.quantile(lower_q)
    high = s.quantile(upper_q)
    return s.clip(lower=low, upper=high)


def add_dependency_features(
    df: pd.DataFrame,
    price_col_alt: str = "close_1s",
    price_col_hub: str = "btc_close_1s",
    window_secs: int = 3600,
    min_periods: int = 600,
) -> pd.DataFrame:
    """
    Add PROD-style dependency features between alt and hub asset.
    
    Calculates:
    - dep_beta_1h: Rolling beta (alt vs hub)
    - dep_corr_1h: Rolling Pearson correlation
    
    Uses 1m resampled returns to avoid zero-inflation from upsampled data.
    
    Args:
        df: DataFrame with price columns and 'ts' datetime column
        price_col_alt: Column name for alt price (e.g. BNB close_1s)
        price_col_hub: Column name for hub price (e.g. BTC close_1s)
        window_secs: Rolling window in seconds (default 3600 = 1h)
        min_periods: Minimum periods required (default 600 = 10min)
        
    Returns:
        DataFrame with added columns: dep_beta_1h, dep_corr_1h
    """
    
    # CRITICAL FIX: Use 1m resampled prices to calculate returns
    # This avoids the problem of most returns being zero due to ffill upsample
    
    # Create copy with datetime index
    df_temp = df.copy()
    if 'ts' not in df_temp.columns:
        raise ValueError("DataFrame must have 'ts' column")
    
    df_temp['ts'] = pd.to_datetime(df_temp['ts'])
    df_temp.set_index('ts', inplace=True)
    
    # Resample to 1m (60s) to get actual price changes
    alt_1m = df_temp[price_col_alt].resample('1min').last()
    hub_1m = df_temp[price_col_hub].resample('1min').last()
    
    # Calculate 1m returns
    r_alt_1m = alt_1m.pct_change()
    r_hub_1m = hub_1m.pct_change()
    
    # Winsorize 1m returns
    r_alt_wins = winsorize(r_alt_1m, lower_q=0.01, upper_q=0.99)
    r_hub_wins = winsorize(r_hub_1m, lower_q=0.01, upper_q=0.99)
    
    # Rolling calculations on 1m data
    # window_mins = window_secs // 60 (convert to minutes)
    window_mins = window_secs // 60
    min_periods_mins = max(10, min_periods // 60)  # At least 10 minutes
    
    roll_alt = r_alt_wins.rolling(window=window_mins, min_periods=min_periods_mins)
    roll_hub = r_hub_wins.rolling(window=window_mins, min_periods=min_periods_mins)
    
    # Covariance and variance
    mean_alt = roll_alt.mean()
    mean_hub = roll_hub.mean()
    mean_product = (r_alt_wins * r_hub_wins).rolling(window=window_mins, min_periods=min_periods_mins).mean()
    
    cov_alt_hub = mean_product - (mean_alt * mean_hub)
    var_hub = roll_hub.var()
    
    # Beta
    beta_1m = cov_alt_hub / (var_hub + 1e-12)
    
    # Pearson correlation
    corr_1m = r_alt_wins.rolling(window=window_mins, min_periods=min_periods_mins).corr(r_hub_wins)
    
    # Now we need to map these 1m values back to 1s DataFrame
    # Use forward-fill to broadcast 1m values to all seconds in that minute
    beta_1m_reindexed = beta_1m.reindex(df_temp.index, method='ffill')
    corr_1m_reindexed = corr_1m.reindex(df_temp.index, method='ffill')
    
    # Add to original dataframe
    df['dep_beta_1h'] = beta_1m_reindexed.values
    df['dep_corr_1h'] = corr_1m_reindexed.values
    
    # Handle NaN
    df['dep_beta_1h'] = df['dep_beta_1h'].fillna(0.0)
    df['dep_corr_1h'] = df['dep_corr_1h'].fillna(0.0)
    
    # Clip
    df['dep_corr_1h'] = df['dep_corr_1h'].clip(-1.0, 1.0)
    df['dep_beta_1h'] = df['dep_beta_1h'].clip(-3.0, 3.0)
    
    return df


def add_multi_hub_dependency(
    df: pd.DataFrame,
    hubs: list = None,
    price_col_alt: str = "close_1s",
    window_secs: int = 3600,
    min_periods: int = 600,
) -> pd.DataFrame:
    """
    Add dependency features for multiple hub assets (BTC, ETH, etc).
    
    Calculates beta and correlation for each hub, then aggregates.
    
    Args:
        df: DataFrame with price columns
        hubs: List of hub price columns (default: ['btc_close_1s', 'eth_close_1s'])
        price_col_alt: Alt asset price column
        window_secs: Rolling window
        min_periods: Minimum periods
        
    Returns:
        DataFrame with aggregated dependency features
    """
    if hubs is None:
        hubs = ['btc_close_1s']  # Default to BTC only
    
    betas = []
    corrs = []
    
    for hub_col in hubs:
        if hub_col not in df.columns:
            print(f"WARNING: {hub_col} not found, skipping")
            continue
            
        # Calculate for this hub
        df_temp = add_dependency_features(
            df.copy(),
            price_col_alt=price_col_alt,
            price_col_hub=hub_col,
            window_secs=window_secs,
            min_periods=min_periods
        )
        
        betas.append(df_temp['dep_beta_1h'])
        corrs.append(df_temp['dep_corr_1h'])
    
    # Aggregate: take mean of betas and correlations
    # (In production, might use weighted average based on hub market cap)
    if betas:
        df['dep_beta_1h'] = pd.concat(betas, axis=1).mean(axis=1)
        df['dep_corr_1h'] = pd.concat(corrs, axis=1).mean(axis=1)
    else:
        df['dep_beta_1h'] = 0.0
        df['dep_corr_1h'] = 0.0
    
    return df
