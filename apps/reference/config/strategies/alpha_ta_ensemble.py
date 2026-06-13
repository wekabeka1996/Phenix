from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==============================================================================
# Momentum Model Config
# ==============================================================================
class MomentumWeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    short: float = Field(..., ge=0.0, le=1.0)
    medium: float = Field(..., ge=0.0, le=1.0)
    long: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_weights(self) -> MomentumWeightsConfig:
        total = self.short + self.medium + self.long
        if abs(total - 1.0) > 1e-9:
            raise ValueError("momentum weights must sum to 1.0")
        return self


class MomentumVolumeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_multiplier: float = Field(..., gt=0.0)
    contradict_multiplier: float = Field(..., gt=0.0)


class MomentumRsiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overbought: float = Field(..., ge=0.0, le=100.0)
    oversold: float = Field(..., ge=0.0, le=100.0)
    confidence_penalty: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> MomentumRsiConfig:
        if self.oversold >= self.overbought:
            raise ValueError("momentum.rsi.oversold must be lower than overbought")
        return self


class MomentumMacdConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_boost: float = Field(..., ge=1.0)
    contradict_penalty: float = Field(..., ge=0.0, le=1.0)


class MomentumConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: float = Field(..., ge=0.0, le=1.0)
    consistency_min: float = Field(..., ge=0.0)
    consistency_range: float = Field(..., ge=0.0)


class MomentumModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: MomentumWeightsConfig = Field(...)
    volume: MomentumVolumeConfig = Field(...)
    rsi: MomentumRsiConfig = Field(...)
    macd: MomentumMacdConfig = Field(...)
    confidence: MomentumConfidenceConfig = Field(...)


# ==============================================================================
# Mean Reversion Model Config
# ==============================================================================
class MeanReversionWeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bb: float = Field(..., ge=0.0, le=1.0)
    rsi: float = Field(..., ge=0.0, le=1.0)
    sma: float = Field(..., ge=0.0, le=1.0)
    stoch: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_weights(self) -> MeanReversionWeightsConfig:
        total = self.bb + self.rsi + self.sma + self.stoch
        if abs(total - 1.0) > 1e-9:
            raise ValueError("mean_reversion weights must sum to 1.0")
        return self


class MeanReversionRsiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    oversold: float = Field(..., ge=0.0, le=100.0)
    overbought: float = Field(..., ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> MeanReversionRsiConfig:
        if self.oversold >= self.overbought:
            raise ValueError("mean_reversion.rsi.oversold must be lower than overbought")
        return self


class MeanReversionSmaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviation_normalizer: float = Field(..., gt=0.0)


class MeanReversionStochasticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    oversold_zone: float = Field(..., ge=0.0, le=100.0)
    overbought_zone: float = Field(..., ge=0.0, le=100.0)
    signal_strength: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> MeanReversionStochasticConfig:
        if self.oversold_zone >= self.overbought_zone:
            raise ValueError("mean_reversion.stochastic.oversold_zone must be lower than overbought_zone")
        return self


class MeanReversionVolumeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_multiplier: float = Field(..., gt=0.0)
    contradict_multiplier: float = Field(..., gt=0.0)
    high_threshold: float = Field(..., gt=0.0)
    low_threshold: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MeanReversionVolumeConfig:
        if self.low_threshold >= self.high_threshold:
            raise ValueError("mean_reversion.volume.low_threshold must be lower than high_threshold")
        return self


class MeanReversionBbWidthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wide_threshold: float = Field(..., gt=0.0)
    narrow_threshold: float = Field(..., ge=0.0)
    max_multiplier: float = Field(..., ge=1.0)
    narrow_penalty: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MeanReversionBbWidthConfig:
        if self.narrow_threshold >= self.wide_threshold:
            raise ValueError("mean_reversion.bb_width.narrow_threshold must be lower than wide_threshold")
        return self


class MeanReversionConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: float = Field(..., ge=0.0, le=1.0)
    agreement_factor: float = Field(..., ge=0.0)
    strength_base: float = Field(..., ge=0.0)
    signal_threshold: float = Field(..., ge=0.0)


class MeanReversionModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: MeanReversionWeightsConfig = Field(...)
    rsi: MeanReversionRsiConfig = Field(...)
    sma: MeanReversionSmaConfig = Field(...)
    stochastic: MeanReversionStochasticConfig = Field(...)
    volume: MeanReversionVolumeConfig = Field(...)
    bb_width: MeanReversionBbWidthConfig = Field(...)
    confidence: MeanReversionConfidenceConfig = Field(...)


# ==============================================================================
# Volatility Model Config
# ==============================================================================
class VolatilityWeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atr: float = Field(..., ge=0.0, le=1.0)
    bb: float = Field(..., ge=0.0, le=1.0)
    rv: float = Field(..., ge=0.0, le=1.0)
    range: float = Field(..., ge=0.0, le=1.0)
    vol_corr: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_weights(self) -> VolatilityWeightsConfig:
        total = self.atr + self.bb + self.rv + self.range + self.vol_corr
        if abs(total - 1.0) > 1e-9:
            raise ValueError("volatility weights must sum to 1.0")
        return self


class VolatilityBbConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amplifier: float = Field(..., gt=0.0)


class VolatilitySignalClampConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atr: float = Field(..., gt=0.0)
    rv: float = Field(..., gt=0.0)


class VolatilityVolumeVolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    high_threshold: float = Field(..., gt=0.0)
    low_threshold: float = Field(..., ge=0.0)
    signal_strength: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> VolatilityVolumeVolConfig:
        if self.low_threshold >= self.high_threshold:
            raise ValueError("volatility.volume_vol.low_threshold must be lower than high_threshold")
        return self


class VolatilityVolLevelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    low_level: float = Field(..., ge=0.0)
    low_penalty: float = Field(..., ge=0.0, le=1.0)
    high_level: float = Field(..., gt=0.0)
    high_boost: float = Field(..., ge=1.0)

    @model_validator(mode="after")
    def _validate_levels(self) -> VolatilityVolLevelConfig:
        if self.low_level >= self.high_level:
            raise ValueError("volatility.vol_level.low_level must be lower than high_level")
        return self


class VolatilityConfidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: float = Field(..., ge=0.0, le=1.0)
    agreement_factor: float = Field(..., ge=0.0)
    strength_base: float = Field(..., ge=0.0)
    no_signal: float = Field(..., ge=0.0, le=1.0)


class VolatilityModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: VolatilityWeightsConfig = Field(...)
    bb: VolatilityBbConfig = Field(...)
    signal_clamp: VolatilitySignalClampConfig = Field(...)
    volume_vol: VolatilityVolumeVolConfig = Field(...)
    vol_level: VolatilityVolLevelConfig = Field(...)
    confidence: VolatilityConfidenceConfig = Field(...)


# ==============================================================================
# Ensemble Model Config
# ==============================================================================
class EnsembleSubModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(...)
    weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class EnsembleSettingsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rebalance_frequency_days: int = Field(..., ge=1)
    performance_window_days: int = Field(..., ge=1)
    risk_adjustment: bool = Field(...)
    models: Dict[str, EnsembleSubModelConfig] = Field(...)


# ==============================================================================
# Profiles, Safety & Assets Config
# ==============================================================================
class AlphaTaEnsembleProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    entry_threshold: float = Field(..., ge=0.0, le=1.0)
    allowed_regimes: List[str] = Field(..., min_length=1)
    allowed_sides: List[Literal["BUY", "SELL"]] = Field(..., min_length=1)
    score_overrides: Dict[str, float] = Field(default_factory=dict)


class AlphaTaEnsembleSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_regimes: List[str] = Field(..., min_length=1)
    forbid_uncertain: bool = Field(...)
    cooldown_sec: int = Field(..., ge=0)
    signal_ttl_ms: int = Field(..., gt=0)
    min_feature_freshness_sec: int = Field(..., ge=0)
    max_intents_per_symbol_hour: Optional[int] = Field(default=None, ge=1)


class AlphaTaEnsembleAssetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(...)
    profile_id: str = Field(..., min_length=1)


# ==============================================================================
# Main Strategy Config Model
# ==============================================================================
class AlphaTaEnsembleStrategyConfig(BaseModel):
    """Configuration model for alpha_ta_ensemble strategy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...)
    mode: Literal["disabled", "shadow", "testnet_candidate"] = Field(...)
    strategy_version: str = Field(..., min_length=1)
    timeframe_sec: int = Field(..., ge=60, le=3600)
    threshold: float = Field(..., ge=0.0, le=1.0)

    momentum: MomentumModelConfig = Field(...)
    mean_reversion: MeanReversionModelConfig = Field(...)
    volatility: VolatilityModelConfig = Field(...)
    ensemble: EnsembleSettingsConfig = Field(...)

    profiles: Dict[str, AlphaTaEnsembleProfileConfig] = Field(..., min_length=1)
    safety: AlphaTaEnsembleSafetyConfig = Field(...)
    assets: Dict[str, AlphaTaEnsembleAssetConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_mode_enabled(self) -> AlphaTaEnsembleStrategyConfig:
        if self.mode != "disabled" and not self.enabled:
            raise ValueError("alpha_ta_ensemble enabled must be true when mode is not disabled")
        return self

    @model_validator(mode="after")
    def _validate_asset_profiles_exist(self) -> AlphaTaEnsembleStrategyConfig:
        for symbol, asset in self.assets.items():
            if asset.enabled and asset.profile_id not in self.profiles:
                raise ValueError(
                    f"Asset {symbol} references profile_id '{asset.profile_id}' "
                    f"which is not defined in profiles registry"
                )
        return self
