"""
Alpha Search Configuration Models

Pydantic strict models for alpha_search domain configuration.
Loaded from config/alpha_search.yaml (separate file, no core changes).

ALPHA-A4: Config schema with extra="forbid", fail-closed validation.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, model_validator


class DirectionStrengthConfig(BaseModel):
    """Aurora direction/strength scoring parameters."""

    directional_features: List[str] = Field(
        default_factory=lambda: [
            "obi",
            "tfi",
            "delta_price",
            "ema_bias",
            "depth_imbalance",
            "macro_resid",
            "macro_sync",
        ]
    )
    strength_features: List[str] = Field(
        default_factory=lambda: ["volume_spike", "volatility_state"]
    )
    strength_alpha: float = 0.5
    strength_cap: float = 1.0

    model_config = {"extra": "forbid"}


class AuroraAdapterConfig(BaseModel):
    """Configuration for Aurora scoring adapter."""

    scoring_version: str = Field(
        default="quadratic",
        description="Aurora scoring version: quadratic (Phase 9). v1/v2 are DEPRECATED."
    )
    essential_features: List[str] = Field(
        default_factory=lambda: ["obi", "delta_price", "macro_resid"],
        description="Features required for Aurora scoring (fail-closed if missing)"
    )
    base_threshold: float = Field(
        default=0.12,
        description="Base Aurora signal threshold"
    )
    delta_price_cap_pct: float = Field(
        default=0.02,
        description="Cap for delta_price normalization"
    )
    # DEPRECATED: signal_weights and feature_neutrals are parsed for backward-compat
    # but QuadraticScoringKernel ignores them. Quadratic reads pillar_sum only.
    signal_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "obi": 0.42,
            "tfi": 0.15,
            "delta_price": 0.15,
            "ema_bias": 0.15,
            "depth_imbalance": -0.15,
            "macro_resid": 0.10,
            "macro_sync": 0.0,
            "volume_spike": 0.10,
            "volatility_state": 0.10,
        },
        description="DEPRECATED: Weights parsed for compat, ignored by QuadraticScoringKernel"
    )
    feature_neutrals: Dict[str, float] = Field(
        default_factory=lambda: {
            "obi": 0.0,
            "tfi": 0.0,
            "delta_price": 0.0,
            "ema_bias": 0.5,
            "volume_spike": 0.0,
            "volatility_state": 0.0,
            "depth_imbalance": 0.5,
            "macro_sync": 0.5,
            "macro_resid": 0.0,
        },
        description="DEPRECATED: Neutrals parsed for compat, ignored by QuadraticScoringKernel"
    )
    regime_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {
            "HIGH_VOLATILITY": 1.0,
            "LOW_VOLATILITY": 0.9,
            "MEAN_REVERSION": 0.75,
            "TREND_UP": 1.0,
            "TREND_DOWN": 1.0,
            "UNCERTAIN": 1.15,
            "DEFAULT": 1.0,
        },
        description="Aurora regime-specific threshold multipliers"
    )
    direction_strength: DirectionStrengthConfig = Field(
        default_factory=DirectionStrengthConfig
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


class JudgeExpertProviderConfig(BaseModel):
    """Configuration for a judge expert provider.

    Specifies which judge expert type to instantiate. The detailed expert
    config (weights, neutrals, etc.) lives in judge.experts config block.
    """

    expert_type: str = Field(
        ...,
        description="Expert type key: 'signal_weights' or 'feature_neutrals'"
    )

    model_config = {"extra": "forbid"}


class ProviderConfig(BaseModel):
    """Configuration for a single alpha provider."""

    enabled: bool = True
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Allowed symbols (None = all)"
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
    min_tf_sec: Optional[int] = Field(
        default=None,
        ge=0,
        description="Minimum timeframe in seconds required for this provider"
    )

    # Provider-specific config (only one should be set)
    adapter: Optional[AuroraAdapterConfig] = None
    ensemble: Optional[TAEnsembleConfig] = None
    judge_expert: Optional["JudgeExpertProviderConfig"] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_provider_type(self):
        """Ensure at most one provider type is configured."""
        has_adapter = self.adapter is not None
        has_ensemble = self.ensemble is not None
        has_judge = self.judge_expert is not None
        count = sum([has_adapter, has_ensemble, has_judge])

        if count > 1:
            raise ValueError(
                "Provider must have at most one of 'adapter', 'ensemble', "
                "or 'judge_expert' config"
            )
        if count == 0:
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
    ta_feature_event: str = Field(
        default="EVT:TA_FEATURES_CALCULATED",
        description="Supplemental event that provides explicit TA features → cache"
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
    max_drawdown_exit: Optional[float] = Field(default=None, ge=0.0)
    cooldown_bars_after_close: int = Field(default=0, ge=0)

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
    flip_on_reversal: bool = False
    exit: VirtualTraderExitConfig = Field(
        default_factory=VirtualTraderExitConfig)

    model_config = {"extra": "forbid"}


class ObjectiveFeedbackConfig(BaseModel):
    """Configuration for objective-quality feedback into alpha_search models."""

    enabled: bool = False
    window_trades: Optional[int] = Field(default=None, ge=1)
    min_trades_before_reweight: Optional[int] = Field(default=None, ge=1)
    rebalance_every_closed_trades: Optional[int] = Field(default=None, ge=1)
    quality_metric_weights: Optional[Dict[str, float]] = Field(default=None)
    min_provider_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_provider_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_enabled_contract(self):
        """Require explicit parameters when objective feedback is enabled."""
        if not self.enabled:
            return self

        required_fields = {
            "window_trades": self.window_trades,
            "min_trades_before_reweight": self.min_trades_before_reweight,
            "rebalance_every_closed_trades": self.rebalance_every_closed_trades,
            "quality_metric_weights": self.quality_metric_weights,
            "min_provider_weight": self.min_provider_weight,
            "max_provider_weight": self.max_provider_weight,
        }
        missing = [name for name, value in required_fields.items()
                   if value is None]
        if missing:
            raise ValueError(
                "objective_feedback.enabled=True requires explicit fields: "
                + ",".join(sorted(missing))
            )
        if not self.quality_metric_weights:
            raise ValueError(
                "objective_feedback.quality_metric_weights must be non-empty when enabled")
        weight_mass = sum(abs(float(weight))
                          for weight in self.quality_metric_weights.values())
        if weight_mass <= 0.0:
            raise ValueError(
                "objective_feedback.quality_metric_weights must have non-zero weight mass")
        if self.min_provider_weight is not None and self.max_provider_weight is not None:
            if self.min_provider_weight > self.max_provider_weight:
                raise ValueError(
                    "objective_feedback requires min_provider_weight <= max_provider_weight")
        if self.window_trades is not None and self.min_trades_before_reweight is not None:
            if self.min_trades_before_reweight > self.window_trades:
                raise ValueError(
                    "objective_feedback.min_trades_before_reweight must be <= window_trades")
        return self


class AlphaSearchSystemConfig(BaseModel):
    """Strict top-level model for alpha_search_system.yaml."""

    momentum: Dict[str, Any] = Field(default_factory=dict)
    mean_reversion: Dict[str, Any] = Field(default_factory=dict)
    volatility: Dict[str, Any] = Field(default_factory=dict)
    ensemble: Dict[str, Any] = Field(default_factory=dict)
    plugin: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


from apps.reference.domains.alpha_search.judge.config_models import JudgeCortexConfig  # noqa: E402


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
    objective_feedback: ObjectiveFeedbackConfig = Field(
        default_factory=ObjectiveFeedbackConfig
    )

    # LLM Judge cortex config (Phase 1: contracts-only, mode='off' enforced)
    judge: Optional[JudgeCortexConfig] = Field(
        default=None,
        description="LLM Judge cortex configuration. None = judge not configured."
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


def load_system_config(config_path: str) -> AlphaSearchSystemConfig:
    """
    Load alpha_search_system configuration from YAML file.

    Args:
        config_path: Path to alpha_search_system.yaml

    Returns:
        Validated AlphaSearchSystemConfig
    """
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Alpha search system config not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if "alpha_search_system" in raw:
        raw = raw["alpha_search_system"]

    return AlphaSearchSystemConfig.model_validate(raw)


def get_default_config() -> AlphaSearchConfig:
    """Return default (disabled) configuration."""
    return AlphaSearchConfig(enabled=False)


def get_default_system_config() -> AlphaSearchSystemConfig:
    """Return default alpha_search_system configuration."""
    return AlphaSearchSystemConfig()
