"""
Feature Engineering Domain

Signal component that transforms raw market tick data into normalized features
for downstream decision making and risk assessment.

Features computed:
- Base: OBI, TFI, delta_price, liquidity_kappa
- Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
- Phase B: Bar resampling, Bollinger Bands, ATR, RSI, regime mapping

Events:
- Input: EVT:MARKET_TICK_RECEIVED
- Output: EVT:FEATURES_CALCULATED
"""

from .feature_engineering import FeatureEngineering

# Phase B: Bar-based strategy infrastructure
from .bar_resampler import Bar, BarResampler, MultiSymbolBarResampler
from .indicators import (
    BollingerBands,
    compute_sma,
    compute_std,
    compute_bollinger_bands,
    compute_atr,
    compute_rsi,
    compute_stochastic,
    IndicatorState,
)
from .regime_mapping import (
    FlatRegime,
    FlatRegimeThresholds,
    map_to_flat_regime,
    is_flat_regime,
    get_mr_parameters,
    MRParameters,
)
from .mean_reversion_strategy import (
    MRSignalType,
    MRSignal,
    MRStrategyConfig,
    MRSymbolState,
    MeanReversion1mStrategy,
)
from .types import BarTAState

__all__ = [
    # Core
    "FeatureEngineering",
    # Bar resampling
    "Bar",
    "BarResampler",
    "MultiSymbolBarResampler",
    # Indicators
    "BollingerBands",
    "compute_sma",
    "compute_std",
    "compute_bollinger_bands",
    "compute_atr",
    "compute_rsi",
    "compute_stochastic",
    "IndicatorState",
    # TA state
    "BarTAState",
    # Regime mapping
    "FlatRegime",
    "FlatRegimeThresholds",
    "map_to_flat_regime",
    "is_flat_regime",
    "get_mr_parameters",
    "MRParameters",
    # Mean Reversion Strategy
    "MRSignalType",
    "MRSignal",
    "MRStrategyConfig",
    "MRSymbolState",
    "MeanReversion1mStrategy",
]
__version__ = "1.2.0"
