"""
EP-01 — Regime Types SSOT.

Defines the canonical labels emitted by RegimeDetector (RegimeLabel)
and the simplified buckets consumed by ExposureGuard policy (ExecutionRegimeBucket).
"""
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
    """
    Simplified buckets for Exposure Guard policy.
    
    EP-01: ExposureGuard switches on these buckets, NOT raw RegimeLabel strings.
    """
    TREND_UP = "TREND_UP"       # Aggressive long bias allowed
    TREND_DOWN = "TREND_DOWN"   # Aggressive short bias allowed
    FLAT = "FLAT"               # Mean-reversion / low-vol → reduce directional exposure
    VOLATILE = "VOLATILE"       # High volatility → tighten limits
    UNCERTAIN = "UNCERTAIN"     # Fallback / unknown → conservative


def map_regime_to_bucket(label_str: str) -> ExecutionRegimeBucket:
    """
    Map Detector outputs (RegimeLabel) to Execution Policy buckets.
    
    EP-01: This is the ONLY place where label→bucket translation happens.
    ExposureGuard must use ExecutionRegimeBucket, never raw strings.
    """
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
    if label == RegimeLabel.HIGH_VOLATILITY:
        return ExecutionRegimeBucket.VOLATILE

    return ExecutionRegimeBucket.UNCERTAIN
