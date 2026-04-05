from __future__ import annotations

from typing import Any, Dict

TA_FEATURE_EVENT = "EVT:TA_FEATURES_CALCULATED"
TA_WARMUP_KEY = "ta_features"
TA_FEATURE_NAMES = (
    "bb_position",
    "bb_width",
    "rsi_14",
    "price_sma_20_deviation",
    "volume_sma_ratio",
    "stoch_k",
    "stoch_d",
    "price_momentum_5m",
)


def extract_ta_feature_vector(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the TA feature subset from a flat event or merged feature dict."""
    return {
        feature_name: payload[feature_name]
        for feature_name in TA_FEATURE_NAMES
        if feature_name in payload
    }


def has_ta_feature_vector(payload: Dict[str, Any]) -> bool:
    """True when a payload already carries at least one TA feature field."""
    return any(feature_name in payload for feature_name in TA_FEATURE_NAMES)
