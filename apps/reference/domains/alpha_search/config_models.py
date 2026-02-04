"""
Alpha Search Configuration Models

Pydantic strict models for alpha_search domain configuration.
Loaded from config/alpha_search.yaml (separate file, no core changes).

ALPHA-A4: Config schema with extra="forbid", fail-closed validation.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, model_validator


class AuroraAdapterConfig(BaseModel):
    """Configuration for Aurora scoring adapter."""
    
    scoring_version: str = Field(
        default="v2",
        description="Aurora scoring version (v1 or v2)"
    )
    essential_features: List[str] = Field(
        default=["obi", "delta_price", "macro_resid"],
        description="Features required for Aurora scoring (fail-closed if missing)"
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
            raise ValueError("Provider cannot have both 'adapter' and 'ensemble' config")
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
    exit: VirtualTraderExitConfig = Field(default_factory=VirtualTraderExitConfig)
    
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
        raise FileNotFoundError(f"Alpha search config not found: {config_path}")
    
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    
    # Support both root-level and nested 'alpha_search' key
    if "alpha_search" in raw:
        raw = raw["alpha_search"]
    
    return AlphaSearchConfig.model_validate(raw)


def get_default_config() -> AlphaSearchConfig:
    """Return default (disabled) configuration."""
    return AlphaSearchConfig(enabled=False)
