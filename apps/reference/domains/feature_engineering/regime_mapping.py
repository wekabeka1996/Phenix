"""
Regime Mapping for 1m Mean Reversion Strategy.

Phase B3: Maps Aurora regime_detector output to FLAT regime types
required by Mean Reversion strategy.

Aurora regime types (from regime_detector.py):
- TREND_UP, TREND_DOWN
- HIGH_VOLATILITY, LOW_VOLATILITY
- MEAN_REVERSION
- UNCERTAIN

1m MR FLAT regime types (from R&D regime_labeling.py):
- FLAT_LOW: Low volatility sideways - tight stops, smaller targets
- FLAT_NORMAL: Normal volatility sideways - standard MR parameters
- FLAT_HIGH: High volatility sideways - wider stops, larger targets

Mapping logic:
1. MEAN_REVERSION + volatility_pct → FLAT_LOW/NORMAL/HIGH
2. LOW_VOLATILITY → FLAT_LOW
3. UNCERTAIN (no clear trend) → FLAT_NORMAL (conservative)
4. TREND_UP/DOWN, HIGH_VOLATILITY → None (skip MR strategy)
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from typing import Optional


class FlatRegime(Enum):
    """FLAT regime types for 1m Mean Reversion strategy."""
    FLAT_LOW = auto()      # Low volatility - tight stops
    FLAT_NORMAL = auto()   # Normal volatility - standard MR
    FLAT_HIGH = auto()     # High volatility - wider stops


@dataclass(frozen=True)
class FlatRegimeThresholds:
    """
    Volatility thresholds for FLAT regime classification.
    
    Based on R&D regime_labeling.py:
    - ATR% > high_vol_pct → FLAT_HIGH
    - ATR% < low_vol_pct → FLAT_LOW
    - Otherwise → FLAT_NORMAL
    
    Attributes:
        high_vol_pct: Threshold for HIGH volatility (default 0.3%)
        low_vol_pct: Threshold for LOW volatility (default 0.1%)
    """
    high_vol_pct: Decimal = Decimal("0.003")  # 0.3%
    low_vol_pct: Decimal = Decimal("0.001")   # 0.1%
    
    def classify(self, atr_pct: Decimal) -> FlatRegime:
        """
        Classify ATR percentage into FLAT regime.
        
        Args:
            atr_pct: ATR as percentage of price (0.002 = 0.2%)
            
        Returns:
            FlatRegime type
        """
        if atr_pct > self.high_vol_pct:
            return FlatRegime.FLAT_HIGH
        elif atr_pct < self.low_vol_pct:
            return FlatRegime.FLAT_LOW
        else:
            return FlatRegime.FLAT_NORMAL


# Default thresholds from R&D
DEFAULT_THRESHOLDS = FlatRegimeThresholds()


def map_to_flat_regime(
    regime: str,
    atr_pct: Optional[Decimal] = None,
    thresholds: Optional[FlatRegimeThresholds] = None
) -> Optional[FlatRegime]:
    """
    Map Aurora regime + volatility to FLAT regime for 1m MR.
    
    Args:
        regime: Aurora regime string (TREND_UP, MEAN_REVERSION, etc.)
        atr_pct: ATR as percentage of price (optional, for MEAN_REVERSION)
        thresholds: Volatility thresholds (optional, uses defaults)
        
    Returns:
        FlatRegime if suitable for MR, None otherwise
        
    Examples:
        >>> map_to_flat_regime("MEAN_REVERSION", Decimal("0.002"))
        FlatRegime.FLAT_NORMAL
        
        >>> map_to_flat_regime("LOW_VOLATILITY")
        FlatRegime.FLAT_LOW
        
        >>> map_to_flat_regime("TREND_UP")
        None
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    
    # Normalize regime string
    regime_upper = regime.upper().strip() if regime else ""
    
    # Skip trending markets - not suitable for mean reversion
    if regime_upper in ("TREND_UP", "TREND_DOWN"):
        return None
    
    # Skip high volatility - too risky for MR
    if regime_upper == "HIGH_VOLATILITY":
        return None
    
    # LOW_VOLATILITY → FLAT_LOW (tight bands, small moves)
    if regime_upper == "LOW_VOLATILITY":
        return FlatRegime.FLAT_LOW
    
    # MEAN_REVERSION → classify by ATR%
    if regime_upper == "MEAN_REVERSION":
        if atr_pct is not None:
            return thresholds.classify(atr_pct)
        else:
            # No ATR data → assume normal volatility
            return FlatRegime.FLAT_NORMAL
    
    # UNCERTAIN → could be flat, conservative approach
    if regime_upper == "UNCERTAIN":
        if atr_pct is not None:
            # Use ATR to classify
            return thresholds.classify(atr_pct)
        else:
            # Default to normal
            return FlatRegime.FLAT_NORMAL
    
    # Unknown regime → skip
    return None


def is_flat_regime(regime: str) -> bool:
    """
    Check if regime is suitable for Mean Reversion.
    
    Args:
        regime: Aurora regime string
        
    Returns:
        True if regime can be mapped to FLAT
    """
    return map_to_flat_regime(regime) is not None


# ============================================================================
# Regime-based Multipliers (hardcoded defaults, can be overridden by config)
# ============================================================================

# Default multipliers from R&D (can be overridden via config)
_DEFAULT_SIZING_MULTIPLIERS = {
    FlatRegime.FLAT_LOW: Decimal("0.8"),
    FlatRegime.FLAT_NORMAL: Decimal("1.0"),
    FlatRegime.FLAT_HIGH: Decimal("0.7"),
}

_DEFAULT_STOP_MULTIPLIERS = {
    FlatRegime.FLAT_LOW: Decimal("0.6"),
    FlatRegime.FLAT_NORMAL: Decimal("1.0"),
    FlatRegime.FLAT_HIGH: Decimal("1.5"),
}

_DEFAULT_TARGET_MULTIPLIERS = {
    FlatRegime.FLAT_LOW: Decimal("0.8"),
    FlatRegime.FLAT_NORMAL: Decimal("1.0"),
    FlatRegime.FLAT_HIGH: Decimal("1.2"),
}


def get_mr_sizing_multiplier(
    flat_regime: FlatRegime,
    config_sizing: dict = None
) -> Decimal:
    """
    Get position sizing multiplier for FLAT regime.
    
    Based on R&D optimal parameters:
    - FLAT_LOW: 0.8x (smaller size, tighter stops)
    - FLAT_NORMAL: 1.0x (standard size)
    - FLAT_HIGH: 0.7x (smaller size, wider stops)
    
    Args:
        flat_regime: FLAT regime type
        config_sizing: Optional dict from YAML config (regime_sizing section)
        
    Returns:
        Sizing multiplier (0.7-1.0)
    """
    # Try config first
    if config_sizing:
        regime_name = flat_regime.name  # e.g., "FLAT_LOW"
        regime_cfg = config_sizing.get(regime_name, {})
        if isinstance(regime_cfg, dict) and "sizing_mult" in regime_cfg:
            return Decimal(str(regime_cfg["sizing_mult"]))
    
    # Fallback to hardcoded defaults
    return _DEFAULT_SIZING_MULTIPLIERS.get(flat_regime, Decimal("1.0"))


def get_mr_stop_multiplier(
    flat_regime: FlatRegime,
    config_sizing: dict = None
) -> Decimal:
    """
    Get stop loss multiplier for FLAT regime.
    
    Based on R&D optimal parameters:
    - FLAT_LOW: 0.6x ATR (tighter stops)
    - FLAT_NORMAL: 1.0x ATR (standard)
    - FLAT_HIGH: 1.5x ATR (wider stops)
    
    Args:
        flat_regime: FLAT regime type
        config_sizing: Optional dict from YAML config (regime_sizing section)
        
    Returns:
        Stop multiplier relative to ATR
    """
    # Try config first
    if config_sizing:
        regime_name = flat_regime.name
        regime_cfg = config_sizing.get(regime_name, {})
        if isinstance(regime_cfg, dict) and "stop_mult" in regime_cfg:
            return Decimal(str(regime_cfg["stop_mult"]))
    
    # Fallback to hardcoded defaults
    return _DEFAULT_STOP_MULTIPLIERS.get(flat_regime, Decimal("1.0"))


def get_mr_target_multiplier(
    flat_regime: FlatRegime,
    config_sizing: dict = None
) -> Decimal:
    """
    Get take profit multiplier for FLAT regime.
    
    Based on R&D optimal parameters:
    - FLAT_LOW: 0.8x (smaller targets, higher win rate)
    - FLAT_NORMAL: 1.0x (standard BB band)
    - FLAT_HIGH: 1.2x (larger targets, lower win rate)
    
    Args:
        flat_regime: FLAT regime type
        config_sizing: Optional dict from YAML config (regime_sizing section)
        
    Returns:
        Target multiplier relative to BB band distance
    """
    # Try config first
    if config_sizing:
        regime_name = flat_regime.name
        regime_cfg = config_sizing.get(regime_name, {})
        if isinstance(regime_cfg, dict) and "target_mult" in regime_cfg:
            return Decimal(str(regime_cfg["target_mult"]))
    
    # Fallback to hardcoded defaults
    return _DEFAULT_TARGET_MULTIPLIERS.get(flat_regime, Decimal("1.0"))


@dataclass
class MRParameters:
    """
    Mean Reversion parameters adjusted for FLAT regime.
    
    All multipliers are relative to base strategy parameters.
    """
    flat_regime: FlatRegime
    sizing_mult: Decimal
    stop_mult: Decimal
    target_mult: Decimal
    
    @classmethod
    def from_flat_regime(
        cls,
        flat_regime: FlatRegime,
        config_sizing: dict = None
    ) -> "MRParameters":
        """
        Create MR parameters from FLAT regime.
        
        Args:
            flat_regime: The FLAT regime type
            config_sizing: Optional dict from YAML config (regime_sizing section)
                           e.g., {"FLAT_LOW": {"sizing_mult": 0.8, "stop_mult": 0.6}}
        
        Returns:
            MRParameters with multipliers from config or defaults
        """
        return cls(
            flat_regime=flat_regime,
            sizing_mult=get_mr_sizing_multiplier(flat_regime, config_sizing),
            stop_mult=get_mr_stop_multiplier(flat_regime, config_sizing),
            target_mult=get_mr_target_multiplier(flat_regime, config_sizing),
        )


def get_mr_parameters(
    regime: str,
    atr_pct: Optional[Decimal] = None,
    thresholds: Optional[FlatRegimeThresholds] = None,
    config_sizing: dict = None
) -> Optional[MRParameters]:
    """
    Get Mean Reversion parameters for current market regime.
    
    Convenience function that combines mapping and parameter lookup.
    
    Args:
        regime: Aurora regime string
        atr_pct: ATR as percentage of price
        thresholds: Volatility thresholds
        config_sizing: Optional dict from YAML config (regime_sizing section)
        
    Returns:
        MRParameters if suitable for MR, None otherwise
        
    Example:
        >>> params = get_mr_parameters("MEAN_REVERSION", Decimal("0.002"))
        >>> params.sizing_mult
        Decimal('1.0')
        
        >>> # With config override
        >>> config = {"FLAT_NORMAL": {"sizing_mult": 1.2}}
        >>> params = get_mr_parameters("MEAN_REVERSION", Decimal("0.002"), config_sizing=config)
        >>> params.sizing_mult
        Decimal('1.2')
    """
    flat_regime = map_to_flat_regime(regime, atr_pct, thresholds)
    if flat_regime is None:
        return None
    return MRParameters.from_flat_regime(flat_regime, config_sizing)
