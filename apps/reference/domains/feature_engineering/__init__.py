"""
Feature Engineering Domain

Signal component that transforms raw market tick data into normalized features
for downstream decision making and risk assessment.

Features computed:
- Base: OBI, TFI, delta_price, liquidity_kappa
- Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync

Events:
- Input: EVT:MARKET_TICK_RECEIVED
- Output: EVT:FEATURES_CALCULATED
"""

from .feature_engineering import FeatureEngineering

__all__ = ["FeatureEngineering"]
__version__ = "1.1.0"
