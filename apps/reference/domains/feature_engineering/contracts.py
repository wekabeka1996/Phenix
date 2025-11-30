"""
Feature Engineering Contracts.

Pydantic models for type-safe validation of feature payloads.
V1: Freezes the v1 feature contract (11 features) - Task FTR-00
V2: Adds O(1) optimized features (3 new) - Task FTR-03

This module follows ADDITIVE-ONLY versioning: V2 extends V1.
"""

from decimal import Decimal
from typing import Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class FeatureSetV1(BaseModel):
    """
    Pydantic model for v1 feature set.
    
    All 11 features from EVT:FEATURES_CALCULATED payload.
    Values are stored as Decimal for precision in financial calculations.
    
    Features:
        - Base: obi, tfi, delta_price, price, absorption, liquidity_kappa
        - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
    
    Example:
        >>> features = parse_features_v1({"obi": "0.15", "tfi": "-0.23", ...})
        >>> features.obi
        Decimal('0.15')
    """
    model_config = ConfigDict(
        strict=True,
        frozen=True,  # Immutable after creation
    )
    
    # Base features (always computed)
    obi: Decimal = Field(
        ...,
        description="Order Book Imbalance: (bid - ask) / depth. Range: [-1, 1]"
    )
    tfi: Decimal = Field(
        ...,
        description="Trade Flow Imbalance: (buy - sell) / total. Range: [-1, 1]"
    )
    delta_price: Decimal = Field(
        ...,
        description="Price change from previous tick. Range: ℝ (real number)"
    )
    price: Decimal = Field(
        ...,
        description="Current price. Range: ℝ+"
    )
    absorption: Decimal = Field(
        ...,
        description="Absorption indicator. Currently placeholder (always 0.0)"
    )
    liquidity_kappa: Decimal = Field(
        ...,
        description="Liquidity measure: depth / (depth + half). Range: [kappa_min, kappa_max]"
    )
    
    # Phase 1 features (conditional on enable_new_metrics)
    ema_bias: Decimal = Field(
        ...,
        description="EMA bias: (EMA_short - EMA_long) / EMA_long, normalized. Range: [0, 1]"
    )
    volume_spike: Decimal = Field(
        ...,
        description="Volume spike: vol / SMA(vol), capped and normalized. Range: [0, 1]"
    )
    volatility_state: Decimal = Field(
        ...,
        description="Volatility state: range / SMA(range), normalized. Range: [0, 1]"
    )
    depth_imbalance: Decimal = Field(
        ...,
        description="Depth imbalance with Laplace smoothing. Range: [0, 1]"
    )
    macro_sync: Decimal = Field(
        ...,
        description="Correlation with anchor assets (BTC/ETH). Range: [0, 1]"
    )


class FeaturesCalculatedPayloadV1(BaseModel):
    """
    Full EVT:FEATURES_CALCULATED payload structure.
    
    Contains timestamp, symbol, and features dict.
    """
    model_config = ConfigDict(strict=True)
    
    ts: int = Field(..., description="Timestamp in milliseconds")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    features: Dict[str, str] = Field(..., description="Feature values as strings")


def parse_features_v1(features: Dict[str, str]) -> FeatureSetV1:
    """
    Parse raw 'features' dict from EVT:FEATURES_CALCULATED into FeatureSetV1.
    
    Converts all string values to Decimal for precision.
    Raises KeyError if any required feature is missing.
    Raises ValueError/InvalidOperation if value cannot be converted to Decimal.
    
    Args:
        features: Dict with feature names as keys and string values
        
    Returns:
        FeatureSetV1: Validated and typed feature set
        
    Raises:
        KeyError: If required feature key is missing
        ValueError: If value cannot be converted to Decimal
        ValidationError: If Pydantic validation fails
        
    Example:
        >>> raw = {"obi": "0.15", "tfi": "-0.23", "delta_price": "10.5", ...}
        >>> features = parse_features_v1(raw)
        >>> features.obi
        Decimal('0.15')
    """
    # Required v1 feature keys
    required_keys = [
        "obi", "tfi", "delta_price", "price", "absorption", "liquidity_kappa",
        "ema_bias", "volume_spike", "volatility_state", "depth_imbalance", "macro_sync"
    ]
    
    # Check all required keys exist
    missing = [k for k in required_keys if k not in features]
    if missing:
        raise KeyError(f"Missing required v1 features: {missing}")
    
    # Convert string values to Decimal
    parsed = {}
    for key in required_keys:
        try:
            parsed[key] = Decimal(features[key])
        except Exception as e:
            raise ValueError(f"Cannot convert feature '{key}' value '{features[key]}' to Decimal: {e}")
    
    return FeatureSetV1(**parsed)


def validate_features_payload_v1(payload: Dict) -> FeaturesCalculatedPayloadV1:
    """
    Validate full EVT:FEATURES_CALCULATED payload.
    
    Args:
        payload: Raw event payload dict
        
    Returns:
        FeaturesCalculatedPayloadV1: Validated payload
        
    Raises:
        ValidationError: If payload structure is invalid
    """
    return FeaturesCalculatedPayloadV1(**payload)


# Feature metadata for documentation and testing
V1_FEATURE_METADATA = {
    "obi": {
        "group": "flow",
        "range": (-1, 1),
        "neutral": Decimal("0"),
        "monotonicity": "+1 = bullish",
    },
    "tfi": {
        "group": "flow",
        "range": (-1, 1),
        "neutral": Decimal("0"),
        "monotonicity": "+1 = bullish",
    },
    "delta_price": {
        "group": "trend",
        "range": None,  # Unbounded
        "neutral": Decimal("0"),
        "monotonicity": "+ = price up",
    },
    "price": {
        "group": "meta",
        "range": None,
        "neutral": None,
        "monotonicity": None,
    },
    "absorption": {
        "group": "flow",
        "range": None,
        "neutral": Decimal("0"),
        "monotonicity": None,  # Placeholder
    },
    "liquidity_kappa": {
        "group": "liquidity",
        "range": (Decimal("0.3"), Decimal("1.0")),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = more liquid",
    },
    "ema_bias": {
        "group": "trend",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": ">0.5 = bullish",
    },
    "volume_spike": {
        "group": "volume",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = anomaly",
    },
    "volatility_state": {
        "group": "volatility",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = volatile",
    },
    "depth_imbalance": {
        "group": "liquidity",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = sell pressure",
    },
    "macro_sync": {
        "group": "macro",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = correlated",
    },
}


# List of all v1 feature names (for iteration/validation)
V1_FEATURE_NAMES = list(V1_FEATURE_METADATA.keys())


# =============================================================================
# V2 FEATURES (FTR-03: Additive)
# =============================================================================

class FeatureSetV2(FeatureSetV1):
    """
    Pydantic model for v2 feature set.
    
    Extends V1 with 3 additional O(1) optimized features:
    - volume_zscore: Z-score normalized volume spike
    - large_trade_imbalance: Institutional flow detection
    - spread_bps: Bid-ask spread in basis points
    
    FTR-05: Added Futures features (optional, config-gated):
    - funding_rate_normalized: Funding rate normalized to [-1, 1]
    - oi_delta_pct: Open Interest percentage change
    - funding_rate: Raw funding rate for debug
    
    Task: FTR-03-WELFORD-OPTIMIZATION, FTR-05-FUTURES-INTEGRATION
    """
    model_config = ConfigDict(
        strict=True,
        frozen=True,
    )
    
    # V2 features (additive)
    volume_zscore: Decimal = Field(
        ...,
        description="Volume Z-score: (vol - mean) / stddev, normalized via tanh. Range: [0, 1]"
    )
    large_trade_imbalance: Decimal = Field(
        ...,
        description="Large trade imbalance: (avg_buy - avg_sell) / max(avg). Range: [0, 1]"
    )
    spread_bps: Decimal = Field(
        ...,
        description="Bid-ask spread in basis points: (ask - bid) / mid * 10000. Range: ℝ+"
    )
    
    # FTR-05: Futures features (optional, only present if futures.enabled)
    funding_rate_normalized: Optional[Decimal] = Field(
        default=None,
        description="Funding rate normalized: clamp(rate / threshold, -1, 1). Range: [-1, 1]"
    )
    oi_delta_pct: Optional[Decimal] = Field(
        default=None,
        description="Open Interest delta: (curr - prev) / prev * 100. Range: ℝ (percentage)"
    )
    funding_rate: Optional[Decimal] = Field(
        default=None,
        description="Raw funding rate for debugging. Range: ℝ"
    )


def parse_features_v2(features: Dict[str, str]) -> FeatureSetV2:
    """
    Parse raw 'features' dict into FeatureSetV2.
    
    Includes all V1 features plus V2 additions.
    
    Args:
        features: Dict with feature names as keys and string values
        
    Returns:
        FeatureSetV2: Validated and typed feature set
        
    Raises:
        KeyError: If required feature key is missing
        ValueError: If value cannot be converted to Decimal
    """
    # V2 required keys = V1 + 3 new
    v2_additional = ["volume_zscore", "large_trade_imbalance", "spread_bps"]
    required_keys = V1_FEATURE_NAMES + v2_additional
    
    # Check all required keys exist
    missing = [k for k in required_keys if k not in features]
    if missing:
        raise KeyError(f"Missing required v2 features: {missing}")
    
    # Convert string values to Decimal
    parsed = {}
    for key in required_keys:
        try:
            parsed[key] = Decimal(features[key])
        except Exception as e:
            raise ValueError(f"Cannot convert feature '{key}' value '{features[key]}' to Decimal: {e}")
    
    return FeatureSetV2(**parsed)


# V2 feature metadata (additive)
V2_FEATURE_METADATA = {
    **V1_FEATURE_METADATA,  # Include V1
    "volume_zscore": {
        "group": "volume",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": "higher = volume anomaly",
    },
    "large_trade_imbalance": {
        "group": "flow",
        "range": (0, 1),
        "neutral": Decimal("0.5"),
        "monotonicity": ">0.5 = larger buys",
    },
    "spread_bps": {
        "group": "liquidity",
        "range": (Decimal("0"), None),  # Unbounded positive
        "neutral": None,
        "monotonicity": "higher = less liquid",
    },
    # FTR-05: Futures features
    "funding_rate_normalized": {
        "group": "futures",
        "range": (-1, 1),
        "neutral": Decimal("0"),
        "monotonicity": ">0 = longs pay shorts (bearish pressure)",
    },
    "oi_delta_pct": {
        "group": "futures",
        "range": None,  # Unbounded percentage
        "neutral": Decimal("0"),
        "monotonicity": ">0 = increasing interest",
    },
    "funding_rate": {
        "group": "futures",
        "range": None,  # Unbounded
        "neutral": Decimal("0"),
        "monotonicity": "raw value for debug",
    },
}

V2_FEATURE_NAMES = list(V2_FEATURE_METADATA.keys())
