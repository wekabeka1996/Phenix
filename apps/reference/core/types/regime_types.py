from enum import Enum

class RegimeLabel(str, Enum):
    """Output labels from RegimeDetector SSOT."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    MEAN_REVERSION = "MEAN_REVERSION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"

class ExecutionRegimeBucket(str, Enum):
    """Simplified buckets for Exposure Guard policy."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    FLAT = "FLAT"             # Maps MEAN_REVERSION
    UNCERTAIN = "UNCERTAIN"   # Fallback

def map_regime_to_bucket(label_str: str) -> ExecutionRegimeBucket:
    """Map Detector outputs to Execution Policy buckets."""
    try:
        label = RegimeLabel(label_str)
    except ValueError:
        return ExecutionRegimeBucket.UNCERTAIN

    if label == RegimeLabel.TREND_UP:
        return ExecutionRegimeBucket.TREND_UP
    if label == RegimeLabel.TREND_DOWN:
        return ExecutionRegimeBucket.TREND_DOWN
    if label == RegimeLabel.MEAN_REVERSION:
        return ExecutionRegimeBucket.FLAT
    if label == RegimeLabel.LOW_VOLATILITY:
        return ExecutionRegimeBucket.FLAT
        
    return ExecutionRegimeBucket.UNCERTAIN
