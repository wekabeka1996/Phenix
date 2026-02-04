"""
Backtest Feature Augmenter
==========================

Vectorized TA-Lib-style indicator calculations for backtest enrichment.
Calculates MACD, Stochastic, Momentum, and other features missing from main FE.

Design principles:
- Polars-native for maximum performance on 1-year data
- Zero dependency on live system (backtest isolation)
- All calculations are vectorized (no Python loops over rows)
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import polars as pl

LOG = logging.getLogger(__name__)


def _ema(series: pl.Series, span: int) -> pl.Series:
    """
    Exponential Moving Average using Polars.
    
    Formula: EMA = α * price + (1 - α) * EMA_prev
    where α = 2 / (span + 1)
    """
    alpha = 2.0 / (span + 1)
    return series.ewm_mean(span=span, adjust=False)


def compute_macd(
    df: pl.DataFrame,
    close_col: str = "close",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pl.DataFrame:
    """
    Compute MACD (Moving Average Convergence Divergence).
    
    Returns DataFrame with columns:
    - macd_line: Fast EMA - Slow EMA
    - macd_signal: Signal line (EMA of MACD line)
    - macd_histogram: MACD line - Signal line
    
    Args:
        df: DataFrame with close prices
        close_col: Name of close price column
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)
    """
    close = df[close_col].cast(pl.Float64)
    
    # Calculate EMAs
    ema_fast = close.ewm_mean(span=fast, adjust=False)
    ema_slow = close.ewm_mean(span=slow, adjust=False)
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line (EMA of MACD line)
    macd_signal = macd_line.ewm_mean(span=signal, adjust=False)
    
    # Histogram
    macd_histogram = macd_line - macd_signal
    
    return df.with_columns([
        macd_line.alias("macd_line"),
        macd_signal.alias("macd_signal"),
        macd_histogram.alias("macd_histogram"),
    ])


def compute_stochastic(
    df: pl.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    k_period: int = 14,
    d_period: int = 3,
) -> pl.DataFrame:
    """
    Compute Stochastic Oscillator (%K and %D).
    
    Formula:
    %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
    %D = SMA(%K, d_period)
    
    Args:
        df: DataFrame with OHLC data
        k_period: Lookback period for %K (default 14)
        d_period: SMA period for %D (default 3)
    """
    high = df[high_col].cast(pl.Float64)
    low = df[low_col].cast(pl.Float64)
    close = df[close_col].cast(pl.Float64)
    
    # Rolling highest high and lowest low
    highest_high = high.rolling_max(window_size=k_period)
    lowest_low = low.rolling_min(window_size=k_period)
    
    # %K calculation (avoid division by zero)
    range_hl = highest_high - lowest_low
    stoch_k = pl.when(range_hl > 0).then(
        100.0 * (close - lowest_low) / range_hl
    ).otherwise(50.0)  # Neutral if no range
    
    # %D is SMA of %K
    stoch_d = stoch_k.rolling_mean(window_size=d_period)
    
    return df.with_columns([
        stoch_k.alias("stochastic_k"),
        stoch_d.alias("stochastic_d"),
    ])


def compute_momentum(
    df: pl.DataFrame,
    close_col: str = "close",
    windows: Optional[List[int]] = None,
) -> pl.DataFrame:
    """
    Compute price momentum (percentage change) over multiple windows.
    
    Momentum = (Close - Close_n) / Close_n * 100
    
    Default windows: [5, 60, 1440] (5m, 1h, 1d in 1-minute bars)
    
    Args:
        df: DataFrame with close prices
        windows: List of lookback periods in bars
    """
    if windows is None:
        windows = [5, 60, 1440]  # 5min, 1h, 1d for 1m timeframe
    
    close = df[close_col].cast(pl.Float64)
    
    new_cols = []
    for w in windows:
        # Percentage change over window
        prev_close = close.shift(w)
        momentum = pl.when(prev_close > 0).then(
            (close - prev_close) / prev_close
        ).otherwise(0.0)
        
        # Name based on window size
        if w <= 5:
            name = "price_momentum_5m"
        elif w <= 60:
            name = "price_momentum_1h"
        else:
            name = "price_momentum_1d"
        
        new_cols.append(momentum.alias(name))
    
    return df.with_columns(new_cols)


def compute_volume_momentum(
    df: pl.DataFrame,
    volume_col: str = "volume",
    window: int = 5,
) -> pl.DataFrame:
    """
    Compute volume momentum (percentage change in volume).
    
    Args:
        df: DataFrame with volume data
        window: Lookback period in bars
    """
    volume = df[volume_col].cast(pl.Float64)
    
    prev_volume = volume.shift(window)
    vol_momentum = pl.when(prev_volume > 0).then(
        (volume - prev_volume) / prev_volume
    ).otherwise(0.0)
    
    return df.with_columns([
        vol_momentum.alias("volume_momentum_5m"),
    ])


def compute_rsi(
    df: pl.DataFrame,
    close_col: str = "close",
    period: int = 14,
) -> pl.DataFrame:
    """
    Compute Relative Strength Index (RSI).
    
    Uses exponential smoothing for RS calculation.
    
    Args:
        df: DataFrame with close prices
        period: RSI period (default 14)
    """
    close = df[close_col].cast(pl.Float64)
    
    # Price changes
    delta = close.diff()
    
    # Separate gains and losses
    gains = pl.when(delta > 0).then(delta).otherwise(0.0)
    losses = pl.when(delta < 0).then(-delta).otherwise(0.0)
    
    # Exponential averages
    avg_gain = gains.ewm_mean(span=period, adjust=False)
    avg_loss = losses.ewm_mean(span=period, adjust=False)
    
    # RSI calculation
    rs = pl.when(avg_loss > 0).then(avg_gain / avg_loss).otherwise(100.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    return df.with_columns([
        rsi.alias("rsi_14"),
    ])


class BacktestFeatureAugmenter:
    """
    Main class for augmenting backtest data with TA indicators.
    
    Usage:
        augmenter = BacktestFeatureAugmenter(df, config=alpha_search_cfg)
        enriched_df = augmenter.augment()
    """
    
    # Default config values (fallback if no config provided)
    DEFAULT_CONFIG = {
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "stochastic": {"k_period": 14, "d_period": 3},
        "rsi": {"period": 14},
        "momentum": {"windows_bars": [5, 60, 1440]},
        "volume_momentum": {"window": 5},
    }
    
    def __init__(
        self, 
        df: pl.DataFrame, 
        symbol_col: str = "symbol",
        config: Optional[Dict] = None
    ):
        """
        Initialize augmenter with raw OHLCV DataFrame.
        
        Args:
            df: Polars DataFrame with columns: ts, symbol, open, high, low, close, volume
            symbol_col: Name of symbol column for grouping
            config: Optional dict with indicator params (from alpha_search.yaml)
        """
        self.df = df
        self.symbol_col = symbol_col
        self.config = config or self.DEFAULT_CONFIG
        self._validate_columns()
    
    def _get_cfg(self, key: str, subkey: str, default):
        """Safely get config value with fallback."""
        try:
            return self.config.get(key, {}).get(subkey, default)
        except (AttributeError, TypeError):
            return default
    
    def _validate_columns(self) -> None:
        """Validate required columns exist."""
        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in self.df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
    
    def augment(self) -> pl.DataFrame:
        """
        Apply all indicator calculations per symbol.
        
        Returns DataFrame with all new feature columns added.
        """
        LOG.info(f"Augmenting {len(self.df)} rows with TA indicators...")
        
        # Extract config values
        macd_fast = self._get_cfg("macd", "fast", 12)
        macd_slow = self._get_cfg("macd", "slow", 26)
        macd_signal = self._get_cfg("macd", "signal", 9)
        stoch_k = self._get_cfg("stochastic", "k_period", 14)
        stoch_d = self._get_cfg("stochastic", "d_period", 3)
        rsi_period = self._get_cfg("rsi", "period", 14)
        mom_windows = self._get_cfg("momentum", "windows_bars", [5, 60, 1440])
        vol_mom_window = self._get_cfg("volume_momentum", "window", 5)
        
        LOG.debug(f"Augmenter config: MACD({macd_fast},{macd_slow},{macd_signal}), "
                  f"RSI({rsi_period}), Momentum({mom_windows})")
        
        # Group by symbol and apply indicators
        result_dfs = []
        
        for symbol in self.df[self.symbol_col].unique().to_list():
            symbol_df = self.df.filter(pl.col(self.symbol_col) == symbol)
            
            # Apply all indicators with config params
            symbol_df = compute_macd(symbol_df, fast=macd_fast, slow=macd_slow, signal=macd_signal)
            symbol_df = compute_stochastic(symbol_df, k_period=stoch_k, d_period=stoch_d)
            symbol_df = compute_momentum(symbol_df, windows=mom_windows)
            symbol_df = compute_volume_momentum(symbol_df, window=vol_mom_window)
            symbol_df = compute_rsi(symbol_df, period=rsi_period)
            
            result_dfs.append(symbol_df)
        
        # Combine all symbols back
        if result_dfs:
            result = pl.concat(result_dfs)
        else:
            result = self.df
        
        # Sort by timestamp to maintain order
        if "ts" in result.columns:
            result = result.sort("ts")
        
        LOG.info(f"Augmentation complete. Added columns: "
                 f"macd_line, macd_signal, macd_histogram, "
                 f"stochastic_k, stochastic_d, "
                 f"price_momentum_5m/1h/1d, volume_momentum_5m, rsi_14")
        
        return result

    
    def get_feature_names(self) -> List[str]:
        """Return list of feature names this augmenter produces."""
        return [
            "macd_line",
            "macd_signal", 
            "macd_histogram",
            "stochastic_k",
            "stochastic_d",
            "price_momentum_5m",
            "price_momentum_1h",
            "price_momentum_1d",
            "volume_momentum_5m",
            "rsi_14",
        ]
