"""
Configuration Classes for Regime Detector Domain

Provides typed configuration dataclasses for all regime detection models
with validation and backward compatibility support.

WHY: Replace manual config parsing with typed, validated dataclasses [FSMP-PORTING-T01]
"""

import warnings
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class SmaTrendConfig:
    """Configuration for SMA-based trend detection model."""
    enabled: bool = True
    fast_period: int = 5
    slow_period: int = 20
    threshold: float = 0.001
    # Confidence calculation parameters
    confidence_multiplier: float = 20.0
    confidence_min: float = 0.5
    confidence_max: float = 0.95

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.fast_period <= 0:
            raise ValueError(
                f"fast_period must be > 0, got {self.fast_period}")
        if self.slow_period <= 0:
            raise ValueError(
                f"slow_period must be > 0, got {self.slow_period}")
        if self.fast_period >= self.slow_period:
            raise ValueError(
                f"fast_period ({self.fast_period}) must be < slow_period ({self.slow_period})")
        if self.threshold <= 0:
            raise ValueError(f"threshold must be > 0, got {self.threshold}")
        if self.confidence_multiplier <= 0:
            raise ValueError(
                f"confidence_multiplier must be > 0, got {self.confidence_multiplier}")
        if self.confidence_min < 0 or self.confidence_min > 1:
            raise ValueError(
                f"confidence_min must be in [0, 1], got {self.confidence_min}")
        if self.confidence_max < 0 or self.confidence_max > 1:
            raise ValueError(
                f"confidence_max must be in [0, 1], got {self.confidence_max}")
        if self.confidence_min >= self.confidence_max:
            raise ValueError(
                f"confidence_min ({self.confidence_min}) must be < confidence_max ({self.confidence_max})")


@dataclass
class VolatilityConfig:
    """Configuration for volatility-based regime detection model."""
    enabled: bool = True
    atr_period: int = 14
    threshold_multiplier: float = 2.0
    low_vol_multiplier: float = 0.5
    atr_sma_length: int = 100
    # Confidence calculation parameters for HIGH_VOLATILITY
    high_vol_confidence_base: float = 0.5
    high_vol_confidence_multiplier: float = 2.0
    # Confidence calculation parameters for LOW_VOLATILITY
    low_vol_confidence_base: float = 0.5
    low_vol_confidence_multiplier: float = 3.0
    # Global confidence cap for all volatility regimes
    confidence_max: float = 0.95

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.atr_period <= 0:
            raise ValueError(f"atr_period must be > 0, got {self.atr_period}")
        if self.threshold_multiplier <= 1.0:
            raise ValueError(
                f"threshold_multiplier must be > 1.0, got {self.threshold_multiplier}")
        if self.low_vol_multiplier >= 1.0:
            raise ValueError(
                f"low_vol_multiplier must be < 1.0, got {self.low_vol_multiplier}")
        if self.atr_sma_length <= 0:
            raise ValueError(
                f"atr_sma_length must be > 0, got {self.atr_sma_length}")
        # Validate confidence parameters
        for attr in ['high_vol_confidence_base', 'low_vol_confidence_base']:
            val = getattr(self, attr)
            if val < 0 or val > 1:
                raise ValueError(f"{attr} must be in [0, 1], got {val}")
        for attr in ['high_vol_confidence_multiplier', 'low_vol_confidence_multiplier']:
            val = getattr(self, attr)
            if val <= 0:
                raise ValueError(f"{attr} must be > 0, got {val}")
        if self.confidence_max < 0 or self.confidence_max > 1:
            raise ValueError(
                f"confidence_max must be in [0, 1], got {self.confidence_max}")


@dataclass
class SidewaysConfig:
    """Configuration for sideways/mean-reversion detection model."""
    enabled: bool = True
    sma_period: int = 50
    deviation_threshold: float = 0.02
    # Confidence calculation parameters
    confidence_base: float = 0.5
    confidence_multiplier: float = 100.0
    # Global confidence cap for sideways regime
    confidence_max: float = 0.95

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.sma_period <= 0:
            raise ValueError(f"sma_period must be > 0, got {self.sma_period}")
        if self.deviation_threshold <= 0:
            raise ValueError(
                f"deviation_threshold must be > 0, got {self.deviation_threshold}")
        if self.confidence_base < 0 or self.confidence_base > 1:
            raise ValueError(
                f"confidence_base must be in [0, 1], got {self.confidence_base}")
        if self.confidence_multiplier <= 0:
            raise ValueError(
                f"confidence_multiplier must be > 0, got {self.confidence_multiplier}")
        if self.confidence_max < 0 or self.confidence_max > 1:
            raise ValueError(
                f"confidence_max must be in [0, 1], got {self.confidence_max}")


@dataclass
class RegimeModels:
    """Container for all regime detection models."""
    sma_trend: SmaTrendConfig = field(default_factory=SmaTrendConfig)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)
    sideways: SidewaysConfig = field(default_factory=SidewaysConfig)


@dataclass
class RegimeDetectorConfig:
    """Main configuration class for RegimeDetector domain."""
    models: RegimeModels = field(default_factory=RegimeModels)
    max_period: int = 100

    def __post_init__(self):
        """Validate and normalize configuration after initialization."""
        if self.max_period <= 0:
            raise ValueError(f"max_period must be > 0, got {self.max_period}")

        # Ensure all required models are present (they are by default with dataclass)
        pass

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RegimeDetectorConfig':
        """
        Create configuration from dictionary with backward compatibility.

        Handles deprecated parameter names and provides warnings.
        """
        config = cls()

        # Extract models section
        models_dict = config_dict.get("models", {})

        # Handle SMA Trend config with backward compatibility
        sma_config = models_dict.get("sma_trend", {})
        if not sma_config:
            # Try legacy names
            if "sma_trend" in models_dict:
                sma_config = models_dict["sma_trend"]
            else:
                # Check for deprecated parameter names
                legacy_fast = config_dict.get(
                    "sma_short_period") or config_dict.get("short_period")
                legacy_slow = config_dict.get(
                    "sma_long_period") or config_dict.get("long_period")
                if legacy_fast or legacy_slow:
                    warnings.warn(
                        "Using deprecated config parameters 'sma_short_period'/'short_period' and "
                        "'sma_long_period'/'long_period'. Use 'models.sma_trend.fast_period' and "
                        "'models.sma_trend.slow_period' instead.",
                        DeprecationWarning,
                        stacklevel=2
                    )
                    sma_config = {
                        "fast_period": legacy_fast or 5,
                        "slow_period": legacy_slow or 20
                    }

        if sma_config:
            config.models.sma_trend = SmaTrendConfig(**sma_config)

        # Handle Volatility config
        vol_config = models_dict.get("volatility", {})
        if vol_config:
            config.models.volatility = VolatilityConfig(**vol_config)

        # Handle Sideways config with backward compatibility
        sideways_config = models_dict.get("sideways", {})
        if not sideways_config:
            # Try legacy mean_reversion config
            mr_config = models_dict.get("mean_reversion", {})
            if mr_config:
                warnings.warn(
                    "Using deprecated config section 'mean_reversion'. Use 'sideways' instead.",
                    DeprecationWarning,
                    stacklevel=2
                )
                # Map old parameters to new ones
                sideways_config = {
                    "sma_period": mr_config.get("sma_period", 50),
                    "deviation_threshold": mr_config.get("threshold", 0.02)
                }

        if sideways_config:
            config.models.sideways = SidewaysConfig(**sideways_config)

        # Handle max_period
        if "max_period" in config_dict:
            config.max_period = config_dict["max_period"]

        return config

    @classmethod
    def from_object(cls, config_obj: Any) -> 'RegimeDetectorConfig':
        """
        Create configuration from object with attribute access.
        """
        config = cls()

        if hasattr(config_obj, 'models'):
            if hasattr(config_obj.models, 'sma_trend'):
                config.models.sma_trend = SmaTrendConfig(
                    **vars(config_obj.models.sma_trend))
            if hasattr(config_obj.models, 'volatility'):
                config.models.volatility = VolatilityConfig(
                    **vars(config_obj.models.volatility))
            if hasattr(config_obj.models, 'sideways'):
                config.models.sideways = SidewaysConfig(
                    **vars(config_obj.models.sideways))
            # Handle legacy mean_reversion
            if hasattr(config_obj.models, 'mean_reversion'):
                warnings.warn(
                    "Using deprecated config section 'mean_reversion'. Use 'sideways' instead.",
                    DeprecationWarning,
                    stacklevel=2
                )
                mr_config = vars(config_obj.models.mean_reversion)
                config.models.sideways = SidewaysConfig(
                    sma_period=mr_config.get("sma_period", 50),
                    deviation_threshold=mr_config.get("threshold", 0.02)
                )

        if hasattr(config_obj, 'max_period'):
            config.max_period = config_obj.max_period

        # Handle legacy top-level parameters
        if hasattr(config_obj, 'sma_short_period') or hasattr(config_obj, 'short_period'):
            warnings.warn(
                "Using deprecated config parameters. Use 'models.sma_trend' section instead.",
                DeprecationWarning,
                stacklevel=2
            )

        return config
