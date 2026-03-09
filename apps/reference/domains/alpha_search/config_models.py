"""
Alpha Search Configuration Models

Pydantic strict models for alpha_search domain configuration.
Loaded from config/alpha_search.yaml (separate file, no core changes).

ALPHA-A4: Config schema with extra="forbid", fail-closed validation.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, model_validator


class DirectionStrengthConfig(BaseModel):
    """Direction/strength scoring split configuration for Aurora adapter."""

    directional_features: List[str] = Field(
        default=["obi", "tfi", "delta_price", "ema_bias",
                 "depth_imbalance", "macro_resid", "macro_sync"],
        description="Features that contribute to directional score"
    )
    strength_features: List[str] = Field(
        default=["volume_spike", "volatility_state"],
        description="Features that contribute to signal strength"
    )
    strength_alpha: float = Field(
        default=0.5,
        description="Weight of strength signal in final score"
    )
    strength_cap: float = Field(
        default=1.0,
        description="Max strength multiplier"
    )

    model_config = {"extra": "forbid"}


class AuroraAdapterConfig(BaseModel):
    """
    Configuration for Aurora scoring adapter.

    All scoring parameters are defined here — no hardcoded defaults in code.
    alpha_search.yaml is the SSOT for this adapter's behaviour.
    """

    scoring_version: str = Field(
        default="v2",
        description="Aurora scoring version (v1 or v2)"
    )
    essential_features: List[str] = Field(
        default=["obi", "delta_price", "macro_resid"],
        description="Features required for Aurora scoring (fail-closed if missing)"
    )
    base_threshold: float = Field(
        default=0.12,
        ge=0.0,
        le=1.0,
        description="Base signal threshold before regime multiplier"
    )
    delta_price_cap_pct: float = Field(
        default=0.02,
        ge=0.0,
        description="Delta price normalization cap (as fraction, e.g. 0.02 = 2%)"
    )
    signal_weights: Dict[str, float] = Field(
        description="Feature weights for directional scoring."
    )
    feature_neutrals: Dict[str, float] = Field(
        description="Neutral/center values per feature."
    )
    regime_thresholds: Dict[str, float] = Field(
        description="Regime-based threshold multipliers."
    )
    direction_strength: DirectionStrengthConfig = Field(
        default_factory=DirectionStrengthConfig,
        description="Direction/strength scoring split config"
    )

    model_config = {"extra": "forbid"}


class EnsembleModelConfig(BaseModel):
    """Configuration for individual TA model in ensemble."""

    enabled: bool = True
    weight: Optional[float] = None  # None = equal weights

    model_config = {"extra": "forbid"}


class TAEnsembleConfig(BaseModel):
    """Configuration for TA ensemble provider."""

    rebalance_frequency_days: int = Field(default=7, ge=1)
    performance_window_days: int = Field(default=30, ge=1)
    risk_adjustment: bool = True
    models: Dict[str, EnsembleModelConfig] = Field(
        default_factory=lambda: {
            "mean_reversion_v1": EnsembleModelConfig(enabled=True),
            "momentum_v1": EnsembleModelConfig(enabled=True),
            "volatility_v1": EnsembleModelConfig(enabled=True),
        }
    )

    model_config = {"extra": "forbid"}


class ProviderConfig(BaseModel):
    """Configuration for a single alpha provider."""

    enabled: bool = True
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Allowed symbols (None = all)"
    )
    min_tf_sec: Optional[int] = Field(
        default=None,
        ge=1,
        description="Minimum bar timeframe (seconds) this provider will process. "
                    "EVT:FEATURES_CALCULATED with tf_sec < min_tf_sec are silently skipped. "
                    "Use for ta_ensemble (needs 5m TA features) to avoid spam on 3m symbols."
    )
    threshold: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Signal threshold for this provider"
    )
    fail_closed: bool = Field(
        default=True,
        description="If True, missing features → score=0 + why. If False, skip."
    )

    # Provider-specific config (only one should be set)
    adapter: Optional[AuroraAdapterConfig] = None
    ensemble: Optional[TAEnsembleConfig] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_provider_type(self):
        """Ensure exactly one provider type is configured."""
        has_adapter = self.adapter is not None
        has_ensemble = self.ensemble is not None

        if has_adapter and has_ensemble:
            raise ValueError(
                "Provider cannot have both 'adapter' and 'ensemble' config")
        if not has_adapter and not has_ensemble:
            # Default to ensemble if neither specified (for backwards compat)
            pass  # OK, will use default ensemble
        return self


class CacheConfig(BaseModel):
    """Configuration for features cache (bridge between events)."""

    max_per_symbol: int = Field(
        default=4,
        ge=1,
        description="Max feature snapshots to keep per symbol"
    )
    require_same_bar_close_ts: bool = Field(
        default=True,
        description="Require exact bar_close_ts match for cache hit"
    )

    model_config = {"extra": "forbid"}


class TriggersConfig(BaseModel):
    """Event names for the two-phase bridge."""

    feature_event: str = Field(
        default="EVT:FEATURES_CALCULATED",
        description="Event that provides features → cache"
    )
    decision_event: str = Field(
        default="CMD:PROCESS_STRATEGY",
        description="Event that triggers scoring → read cache"
    )
    emit_event: str = Field(
        default="EVT:ALPHA_SCORE_CALCULATED",
        description="Event emitted with alpha scores"
    )

    model_config = {"extra": "forbid"}


class VirtualTraderExitConfig(BaseModel):
    """Exit rules for virtual trader."""

    max_bars: int = Field(default=12, ge=1)
    max_hold_sec: int = Field(default=3600, ge=60)
    max_drawdown_exit: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Per-trade adverse move stop in percent (e.g. 1.2 = 1.2%)"
    )
    cooldown_bars_after_close: int = Field(
        default=0,
        ge=0,
        description="After any virtual position closes, block new entries for this many bars "
                    "(per provider+symbol pair). Addresses 90%+ reversal-exit rate by preventing "
                    "immediate re-entry on noisy signal flips."
    )

    model_config = {"extra": "forbid"}


class VirtualTraderConfig(BaseModel):
    """Configuration for virtual trader (shadow PnL tracking)."""

    enabled: bool = True
    per_provider: bool = Field(
        default=True,
        description="Track PnL separately per provider for clean feedback"
    )
    max_positions_per_symbol: int = Field(default=1, ge=1)
    notional_size: float = Field(
        default=1000.0,
        description="Notional size for virtual trades (for PnL calc)"
    )
    flip_on_reversal: bool = Field(
        default=False,
        description="If True: on opposite signal close current position AND immediately open in new direction. "
                    "If False: close on reversal then wait for next independent entry bar."
    )
    exit: VirtualTraderExitConfig = Field(
        default_factory=VirtualTraderExitConfig)

    model_config = {"extra": "forbid"}


class AlphaSearchConfig(BaseModel):
    """
    Root configuration for alpha_search domain.

    Loaded from config/alpha_search.yaml.
    Pydantic strict mode with extra="forbid".

    IMPORTANT: Legacy fields (augmenter, signals, models, ensemble) must be
    placed under the 'legacy' key to pass validation.
    """

    enabled: bool = Field(
        default=False,
        description="Master switch for alpha_search"
    )
    shadow_mode: bool = Field(
        default=True,
        description="If True, signals are logged but not traded"
    )

    triggers: TriggersConfig = Field(default_factory=TriggersConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)

    providers: Dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="Provider configurations keyed by provider_id"
    )

    virtual_trader: VirtualTraderConfig = Field(
        default_factory=VirtualTraderConfig
    )

    # Explicit legacy bucket — allows old fields without breaking strict validation.
    # Migration: move augmenter/signals/models/ensemble here, then remove them.
    legacy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Container for legacy config fields (augmenter, signals, models, ensemble)"
    )

    # STRICT: extra="forbid" — typos/unknown fields will raise ValidationError
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_at_least_one_provider_if_enabled(self):
        """If enabled, at least one provider must be enabled."""
        if self.enabled:
            enabled_providers = [
                name for name, cfg in self.providers.items()
                if cfg.enabled
            ]
            if not enabled_providers:
                raise ValueError(
                    "alpha_search.enabled=True but no providers are enabled"
                )
        return self


# ==============================================================================
# System Config Models — Model Tuning Parameters
# Loaded from config/alpha_search_system.yaml
# ==============================================================================


class MomentumWeightsConfig(BaseModel):
    """Momentum timeframe weights."""
    short: float = Field(default=0.3, description="5m momentum weight")
    medium: float = Field(default=0.4, description="1h momentum weight")
    long: float = Field(default=0.3, description="1d momentum weight")
    model_config = {"extra": "forbid"}


class MomentumVolumeConfig(BaseModel):
    """Momentum volume multipliers."""
    confirm_multiplier: float = Field(
        default=1.2, description="Volume confirms direction")
    contradict_multiplier: float = Field(
        default=0.8, description="Volume contradicts direction")
    model_config = {"extra": "forbid"}


class MomentumRsiConfig(BaseModel):
    """Momentum RSI thresholds."""
    overbought: float = Field(default=70)
    oversold: float = Field(default=30)
    confidence_penalty: float = Field(default=0.7)
    model_config = {"extra": "forbid"}


class MomentumMacdConfig(BaseModel):
    """Momentum MACD factors."""
    confirm_boost: float = Field(default=1.1)
    contradict_penalty: float = Field(default=0.9)
    model_config = {"extra": "forbid"}


class MomentumConfidenceConfig(BaseModel):
    """Momentum confidence parameters."""
    base: float = Field(default=0.8)
    consistency_min: float = Field(
        default=0.7, description="Min consistency multiplier")
    consistency_range: float = Field(
        default=0.6, description="Range added at 100% agreement")
    model_config = {"extra": "forbid"}


class MomentumSystemConfig(BaseModel):
    """All momentum model tuning parameters."""
    weights: MomentumWeightsConfig = Field(
        default_factory=MomentumWeightsConfig)
    volume: MomentumVolumeConfig = Field(default_factory=MomentumVolumeConfig)
    rsi: MomentumRsiConfig = Field(default_factory=MomentumRsiConfig)
    macd: MomentumMacdConfig = Field(default_factory=MomentumMacdConfig)
    confidence: MomentumConfidenceConfig = Field(
        default_factory=MomentumConfidenceConfig)
    model_config = {"extra": "forbid"}


class MeanRevWeightsConfig(BaseModel):
    """Mean reversion signal weights."""
    bb: float = Field(default=0.4)
    rsi: float = Field(default=0.3)
    sma: float = Field(default=0.2)
    stoch: float = Field(default=0.1)
    model_config = {"extra": "forbid"}


class MeanRevRsiConfig(BaseModel):
    """Mean reversion RSI thresholds."""
    oversold: float = Field(default=30)
    overbought: float = Field(default=70)
    model_config = {"extra": "forbid"}


class MeanRevSmaConfig(BaseModel):
    """Mean reversion SMA parameters."""
    deviation_normalizer: float = Field(default=0.05)
    model_config = {"extra": "forbid"}


class MeanRevStochConfig(BaseModel):
    """Mean reversion stochastic parameters."""
    oversold_zone: float = Field(default=20)
    overbought_zone: float = Field(default=80)
    signal_strength: float = Field(default=0.3)
    model_config = {"extra": "forbid"}


class MeanRevVolumeConfig(BaseModel):
    """Mean reversion volume parameters."""
    confirm_multiplier: float = Field(default=1.2)
    contradict_multiplier: float = Field(default=0.8)
    high_threshold: float = Field(default=1.5)
    low_threshold: float = Field(default=0.7)
    model_config = {"extra": "forbid"}


class MeanRevBbWidthConfig(BaseModel):
    """Mean reversion Bollinger Band width parameters."""
    wide_threshold: float = Field(default=0.05)
    narrow_threshold: float = Field(default=0.02)
    max_multiplier: float = Field(default=1.5)
    narrow_penalty: float = Field(default=0.7)
    model_config = {"extra": "forbid"}


class MeanRevConfidenceConfig(BaseModel):
    """Mean reversion confidence parameters."""
    base: float = Field(default=0.5)
    agreement_factor: float = Field(default=0.4)
    strength_base: float = Field(default=0.8)
    signal_threshold: float = Field(default=0.1)
    model_config = {"extra": "forbid"}


class MeanReversionSystemConfig(BaseModel):
    """All mean reversion model tuning parameters."""
    weights: MeanRevWeightsConfig = Field(default_factory=MeanRevWeightsConfig)
    rsi: MeanRevRsiConfig = Field(default_factory=MeanRevRsiConfig)
    sma: MeanRevSmaConfig = Field(default_factory=MeanRevSmaConfig)
    stochastic: MeanRevStochConfig = Field(default_factory=MeanRevStochConfig)
    volume: MeanRevVolumeConfig = Field(default_factory=MeanRevVolumeConfig)
    bb_width: MeanRevBbWidthConfig = Field(
        default_factory=MeanRevBbWidthConfig)
    confidence: MeanRevConfidenceConfig = Field(
        default_factory=MeanRevConfidenceConfig)
    model_config = {"extra": "forbid"}


class VolWeightsConfig(BaseModel):
    """Volatility signal weights."""
    atr: float = Field(default=0.4)
    bb: float = Field(default=0.25)
    rv: float = Field(default=0.2)
    range: float = Field(default=0.1)
    vol_corr: float = Field(default=0.05)
    model_config = {"extra": "forbid"}


class VolBbConfig(BaseModel):
    """Volatility BB amplifier."""
    amplifier: float = Field(default=10)
    model_config = {"extra": "forbid"}


class VolSignalClampConfig(BaseModel):
    """Volatility signal clamp bounds."""
    atr: float = Field(default=2.0)
    rv: float = Field(default=2.0)
    model_config = {"extra": "forbid"}


class VolVolumeVolConfig(BaseModel):
    """Volatility volume-volatility correlation parameters."""
    high_threshold: float = Field(default=1.2)
    low_threshold: float = Field(default=0.8)
    signal_strength: float = Field(default=0.2)
    model_config = {"extra": "forbid"}


class VolLevelConfig(BaseModel):
    """Volatility level filter parameters."""
    low_level: float = Field(default=0.5)
    low_penalty: float = Field(default=0.5)
    high_level: float = Field(default=2.0)
    high_boost: float = Field(default=1.2)
    model_config = {"extra": "forbid"}


class VolConfidenceConfig(BaseModel):
    """Volatility confidence parameters."""
    base: float = Field(default=0.6)
    agreement_factor: float = Field(default=0.3)
    strength_base: float = Field(default=0.7)
    no_signal: float = Field(default=0.4)
    model_config = {"extra": "forbid"}


class VolatilitySystemConfig(BaseModel):
    """All volatility model tuning parameters."""
    weights: VolWeightsConfig = Field(default_factory=VolWeightsConfig)
    bb: VolBbConfig = Field(default_factory=VolBbConfig)
    signal_clamp: VolSignalClampConfig = Field(
        default_factory=VolSignalClampConfig)
    volume_vol: VolVolumeVolConfig = Field(default_factory=VolVolumeVolConfig)
    vol_level: VolLevelConfig = Field(default_factory=VolLevelConfig)
    confidence: VolConfidenceConfig = Field(
        default_factory=VolConfidenceConfig)
    model_config = {"extra": "forbid"}


class EnsembleSystemConfig(BaseModel):
    """Ensemble model tuning parameters."""
    max_history: int = Field(default=100, ge=1)
    confidence_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    pnl_normalizer: float = Field(default=100.0, gt=0)
    min_performance_score: float = Field(default=0.1, ge=0.0)
    variance_cap: float = Field(default=0.5, ge=0.0, le=1.0)
    model_config = {"extra": "forbid"}


class PluginSystemConfig(BaseModel):
    """Backtest plugin tuning parameters."""
    default_tf_sec: int = Field(default=300, ge=1)
    why_chain_limit: int = Field(default=5, ge=1)
    model_config = {"extra": "forbid"}


class AlphaSearchSystemConfig(BaseModel):
    """
    Root system configuration for alpha_search model tuning.

    Loaded from config/alpha_search_system.yaml.
    All defaults match the previously hardcoded values.
    """
    momentum: MomentumSystemConfig = Field(
        default_factory=MomentumSystemConfig)
    mean_reversion: MeanReversionSystemConfig = Field(
        default_factory=MeanReversionSystemConfig)
    volatility: VolatilitySystemConfig = Field(
        default_factory=VolatilitySystemConfig)
    ensemble: EnsembleSystemConfig = Field(
        default_factory=EnsembleSystemConfig)
    plugin: PluginSystemConfig = Field(default_factory=PluginSystemConfig)
    model_config = {"extra": "forbid"}


def load_system_config(config_path: str) -> AlphaSearchSystemConfig:
    """
    Load system config from YAML file.

    Falls back to defaults if file not found.
    """
    import yaml
    from pathlib import Path
    import logging

    LOG = logging.getLogger(__name__)
    path = Path(config_path)
    if not path.exists():
        LOG.info(f"System config not found at {config_path}, using defaults")
        return AlphaSearchSystemConfig()

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if "alpha_search_system" in raw:
        raw = raw["alpha_search_system"]

    return AlphaSearchSystemConfig.model_validate(raw)


def get_default_system_config() -> AlphaSearchSystemConfig:
    """Return default system configuration (matches previously hardcoded values)."""
    return AlphaSearchSystemConfig()


def load_alpha_search_config(config_path: str) -> AlphaSearchConfig:
    """
    Load alpha_search configuration from YAML file.

    Args:
        config_path: Path to alpha_search.yaml

    Returns:
        Validated AlphaSearchConfig

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If config is invalid
    """
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Alpha search config not found: {config_path}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    # Support both root-level and nested 'alpha_search' key
    if "alpha_search" in raw:
        raw = raw["alpha_search"]

    return AlphaSearchConfig.model_validate(raw)


def get_default_config() -> AlphaSearchConfig:
    """Return default (disabled) configuration."""
    return AlphaSearchConfig(enabled=False)
