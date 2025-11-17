"""
Configuration classes for FeatureEngineering domain.

Handles all config loading logic with proper defaults and validation.
Separates config management from business logic.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import logging


@dataclass
class ConfigDefaults:
    """Default values for FeatureEngineering configuration."""

    # EMA defaults
    EMA_PERIOD_SHORT: int = 3
    EMA_PERIOD_LONG: int = 7

    # Volume defaults
    VOLUME_SMA_LENGTH: int = 5
    VOLUME_WINDOW_SEC: int = 60

    # Volatility defaults
    VOLATILITY_SMA_LENGTH: int = 10
    VOLATILITY_WINDOW_SEC: int = 60

    # Liquidity defaults
    LIQUIDITY_DEPTH_HALF: float = 1000.0

    # Macro sync defaults
    MACRO_SYNC_ENABLED: bool = False
    MACRO_SYNC_ANCHORS: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    MACRO_SYNC_WINDOW: int = 60

    # Feature engineering defaults
    ENABLE_NEW_METRICS: bool = True

    # Mathematical limits (previously "magic numbers")
    EMA_BIAS_CLAMP: float = 0.02  # ±2% clamp for EMA bias
    VOLUME_SPIKE_CAP: float = 3.0  # Max volume spike multiplier
    VOLATILITY_RATIO_CAP: float = 3.0  # Max volatility ratio
    LIQUIDITY_KAPPA_MIN: float = 0.3  # Min liquidity kappa
    LIQUIDITY_KAPPA_MAX: float = 1.0  # Max liquidity kappa


@dataclass
class EMAConfig:
    """EMA (Exponential Moving Average) configuration."""
    period_short: int = ConfigDefaults.EMA_PERIOD_SHORT
    period_long: int = ConfigDefaults.EMA_PERIOD_LONG
    bias_clamp: float = ConfigDefaults.EMA_BIAS_CLAMP


@dataclass
class VolumeConfig:
    """Volume spike detection configuration."""
    sma_length: int = ConfigDefaults.VOLUME_SMA_LENGTH
    window_sec: int = ConfigDefaults.VOLUME_WINDOW_SEC
    spike_cap: float = ConfigDefaults.VOLUME_SPIKE_CAP


@dataclass
class VolatilityConfig:
    """Volatility state configuration."""
    sma_length: int = ConfigDefaults.VOLATILITY_SMA_LENGTH
    window_sec: int = ConfigDefaults.VOLATILITY_WINDOW_SEC
    ratio_cap: float = ConfigDefaults.VOLATILITY_RATIO_CAP


@dataclass
class LiquidityConfig:
    """Liquidity and depth imbalance configuration."""
    depth_half: float = ConfigDefaults.LIQUIDITY_DEPTH_HALF
    kappa_min: float = ConfigDefaults.LIQUIDITY_KAPPA_MIN
    kappa_max: float = ConfigDefaults.LIQUIDITY_KAPPA_MAX


@dataclass
class MacroSyncConfig:
    """Macro synchronization (correlation) configuration."""
    enabled: bool = ConfigDefaults.MACRO_SYNC_ENABLED
    anchors: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    window: int = ConfigDefaults.MACRO_SYNC_WINDOW


class FeatureEngineeringConfig:
    """
    Configuration loader for FeatureEngineering domain.

    Handles both Pydantic models and dict-based configs with proper fallbacks.
    Extracts config loading complexity from __init__.
    """

    def __init__(self, config: Any):
        """
        Initialize configuration from raw config object.

        Args:
            config: Raw config (Pydantic model or dict)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._raw_config = config

        # Load all sub-configs
        self.enable_new_metrics = self._load_enable_new_metrics()
        self.ema = self._load_ema_config()
        self.volume = self._load_volume_config()
        self.volatility = self._load_volatility_config()
        self.liquidity = self._load_liquidity_config()
        self.macro_sync = self._load_macro_sync_config()

        self.logger.info(
            f"FeatureEngineeringConfig loaded: "
            f"new_metrics={self.enable_new_metrics}, "
            f"ema_short={self.ema.period_short}, "
            f"macro_sync={self.macro_sync.enabled}"
        )

    def _get_fe_config(self) -> Any:
        """Extract feature_engineering config section."""
        try:
            if hasattr(self._raw_config, 'trading') and hasattr(self._raw_config.trading, 'feature_engineering'):
                return self._raw_config.trading.feature_engineering
            elif isinstance(self._raw_config, dict):
                return (self._raw_config.get("trading", {}) or {}).get("feature_engineering", {})
            return {}
        except (AttributeError, TypeError) as e:
            self.logger.debug(f"Error accessing feature_engineering config: {e}")
            return {}

    def _load_enable_new_metrics(self) -> bool:
        """Load enable_new_metrics flag."""
        try:
            fe_config = self._get_fe_config()
            if hasattr(fe_config, 'enable_new_metrics'):
                return bool(fe_config.enable_new_metrics)
            elif isinstance(fe_config, dict):
                return bool(fe_config.get('enable_new_metrics', ConfigDefaults.ENABLE_NEW_METRICS))
            return ConfigDefaults.ENABLE_NEW_METRICS
        except Exception as e:
            self.logger.warning(f"Failed to load enable_new_metrics, using default: {e}")
            return ConfigDefaults.ENABLE_NEW_METRICS

    def _load_ema_config(self) -> EMAConfig:
        """Load EMA configuration."""
        try:
            fe_config = self._get_fe_config()

            if hasattr(fe_config, 'ema'):
                ema_cfg = fe_config.ema
                return EMAConfig(
                    period_short=getattr(ema_cfg, 'period_short', ConfigDefaults.EMA_PERIOD_SHORT),
                    period_long=getattr(ema_cfg, 'period_long', ConfigDefaults.EMA_PERIOD_LONG),
                    bias_clamp=getattr(ema_cfg, 'bias_clamp', ConfigDefaults.EMA_BIAS_CLAMP),
                )
            elif isinstance(fe_config, dict):
                ema_cfg = fe_config.get('ema', {})
                return EMAConfig(
                    period_short=ema_cfg.get('period_short', ConfigDefaults.EMA_PERIOD_SHORT),
                    period_long=ema_cfg.get('period_long', ConfigDefaults.EMA_PERIOD_LONG),
                    bias_clamp=ema_cfg.get('bias_clamp', ConfigDefaults.EMA_BIAS_CLAMP),
                )
            return EMAConfig()
        except Exception as e:
            self.logger.warning(f"Failed to load EMA config, using defaults: {e}")
            return EMAConfig()

    def _load_volume_config(self) -> VolumeConfig:
        """Load volume spike configuration."""
        try:
            fe_config = self._get_fe_config()

            if hasattr(fe_config, 'volume'):
                vol_cfg = fe_config.volume
                return VolumeConfig(
                    sma_length=getattr(vol_cfg, 'sma_length', ConfigDefaults.VOLUME_SMA_LENGTH),
                    window_sec=getattr(vol_cfg, 'window_sec', ConfigDefaults.VOLUME_WINDOW_SEC),
                    spike_cap=getattr(vol_cfg, 'spike_cap', ConfigDefaults.VOLUME_SPIKE_CAP),
                )
            elif isinstance(fe_config, dict):
                vol_cfg = fe_config.get('volume', {})
                return VolumeConfig(
                    sma_length=vol_cfg.get('sma_length', ConfigDefaults.VOLUME_SMA_LENGTH),
                    window_sec=vol_cfg.get('window_sec', ConfigDefaults.VOLUME_WINDOW_SEC),
                    spike_cap=vol_cfg.get('spike_cap', ConfigDefaults.VOLUME_SPIKE_CAP),
                )
            return VolumeConfig()
        except Exception as e:
            self.logger.warning(f"Failed to load volume config, using defaults: {e}")
            return VolumeConfig()

    def _load_volatility_config(self) -> VolatilityConfig:
        """Load volatility state configuration."""
        try:
            fe_config = self._get_fe_config()

            if hasattr(fe_config, 'volatility'):
                vol_cfg = fe_config.volatility
                return VolatilityConfig(
                    sma_length=getattr(vol_cfg, 'sma_length', ConfigDefaults.VOLATILITY_SMA_LENGTH),
                    window_sec=getattr(vol_cfg, 'window_sec', ConfigDefaults.VOLATILITY_WINDOW_SEC),
                    ratio_cap=getattr(vol_cfg, 'ratio_cap', ConfigDefaults.VOLATILITY_RATIO_CAP),
                )
            elif isinstance(fe_config, dict):
                vol_cfg = fe_config.get('volatility', {})
                return VolatilityConfig(
                    sma_length=vol_cfg.get('sma_length', ConfigDefaults.VOLATILITY_SMA_LENGTH),
                    window_sec=vol_cfg.get('window_sec', ConfigDefaults.VOLATILITY_WINDOW_SEC),
                    ratio_cap=vol_cfg.get('ratio_cap', ConfigDefaults.VOLATILITY_RATIO_CAP),
                )
            return VolatilityConfig()
        except Exception as e:
            self.logger.warning(f"Failed to load volatility config, using defaults: {e}")
            return VolatilityConfig()

    def _load_liquidity_config(self) -> LiquidityConfig:
        """Load liquidity and depth imbalance configuration."""
        try:
            fe_config = self._get_fe_config()

            if hasattr(fe_config, 'liquidity'):
                liq_cfg = fe_config.liquidity
                return LiquidityConfig(
                    depth_half=getattr(liq_cfg, 'depth_half', ConfigDefaults.LIQUIDITY_DEPTH_HALF),
                    kappa_min=getattr(liq_cfg, 'kappa_min', ConfigDefaults.LIQUIDITY_KAPPA_MIN),
                    kappa_max=getattr(liq_cfg, 'kappa_max', ConfigDefaults.LIQUIDITY_KAPPA_MAX),
                )
            elif isinstance(fe_config, dict):
                liq_cfg = fe_config.get('liquidity', {})
                return LiquidityConfig(
                    depth_half=liq_cfg.get('depth_half', ConfigDefaults.LIQUIDITY_DEPTH_HALF),
                    kappa_min=liq_cfg.get('kappa_min', ConfigDefaults.LIQUIDITY_KAPPA_MIN),
                    kappa_max=liq_cfg.get('kappa_max', ConfigDefaults.LIQUIDITY_KAPPA_MAX),
                )
            return LiquidityConfig()
        except Exception as e:
            self.logger.warning(f"Failed to load liquidity config, using defaults: {e}")
            return LiquidityConfig()

    def _load_macro_sync_config(self) -> MacroSyncConfig:
        """Load macro synchronization configuration."""
        try:
            # Macro sync is under trading.market_data.macro_sync
            if hasattr(self._raw_config, 'trading') and hasattr(self._raw_config.trading, 'market_data'):
                market_data = self._raw_config.trading.market_data
                if hasattr(market_data, 'macro_sync'):
                    ms_cfg = market_data.macro_sync
                    return MacroSyncConfig(
                        enabled=getattr(ms_cfg, 'enabled', ConfigDefaults.MACRO_SYNC_ENABLED),
                        anchors=list(getattr(ms_cfg, 'anchors', ConfigDefaults.MACRO_SYNC_ANCHORS)),
                        window=getattr(ms_cfg, 'window', ConfigDefaults.MACRO_SYNC_WINDOW),
                    )
            elif isinstance(self._raw_config, dict):
                ms_cfg = ((self._raw_config.get("trading", {}) or {}).get("market_data", {}) or {}).get("macro_sync", {})
                return MacroSyncConfig(
                    enabled=ms_cfg.get('enabled', ConfigDefaults.MACRO_SYNC_ENABLED),
                    anchors=ms_cfg.get('anchors', ["BTCUSDT", "ETHUSDT"]),
                    window=ms_cfg.get('window', ConfigDefaults.MACRO_SYNC_WINDOW),
                )
            return MacroSyncConfig()
        except Exception as e:
            self.logger.warning(f"Failed to load macro_sync config, using defaults: {e}")
            return MacroSyncConfig()
