from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlphaMrS01WeightsConfig(BaseModel):
    """Weighted S01 mean-reversion component weights."""

    model_config = ConfigDict(extra="forbid")

    bb: float = Field(..., ge=0.0, le=1.0)
    rsi: float = Field(..., ge=0.0, le=1.0)
    sma: float = Field(..., ge=0.0, le=1.0)
    stoch: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_weight_mass(self) -> "AlphaMrS01WeightsConfig":
        total = self.bb + self.rsi + self.sma + self.stoch
        if abs(total - 1.0) > 1e-9:
            raise ValueError("alpha_mr_s01 weights must sum to 1.0")
        return self


class AlphaMrS01RsiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oversold: float = Field(..., ge=0.0, le=100.0)
    overbought: float = Field(..., ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> "AlphaMrS01RsiConfig":
        if self.oversold >= self.overbought:
            raise ValueError("rsi.oversold must be lower than rsi.overbought")
        return self


class AlphaMrS01SmaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deviation_normalizer: float = Field(..., gt=0.0)


class AlphaMrS01StochasticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oversold_zone: float = Field(..., ge=0.0, le=100.0)
    overbought_zone: float = Field(..., ge=0.0, le=100.0)
    signal_strength: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_ordering(self) -> "AlphaMrS01StochasticConfig":
        if self.oversold_zone >= self.overbought_zone:
            raise ValueError("stochastic.oversold_zone must be lower than stochastic.overbought_zone")
        return self


class AlphaMrS01VolumeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...)
    confirm_multiplier: float = Field(..., gt=0.0)
    contradict_multiplier: float = Field(..., gt=0.0)
    high_threshold: float = Field(..., gt=0.0)
    low_threshold: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "AlphaMrS01VolumeConfig":
        if self.low_threshold >= self.high_threshold:
            raise ValueError("volume.low_threshold must be lower than volume.high_threshold")
        return self


class AlphaMrS01BbWidthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_width: float = Field(..., ge=0.0)
    max_width: float = Field(..., gt=0.0)
    narrow_penalty_enabled: bool = Field(...)
    narrow_threshold: float = Field(..., ge=0.0)
    narrow_penalty: float = Field(..., gt=0.0)
    wide_boost_enabled: bool = Field(...)
    wide_threshold: float = Field(..., gt=0.0)
    max_multiplier: float = Field(..., ge=1.0)

    @model_validator(mode="after")
    def _validate_widths(self) -> "AlphaMrS01BbWidthConfig":
        if self.min_width > self.max_width:
            raise ValueError("bb_width.min_width must be <= bb_width.max_width")
        if self.narrow_threshold > self.max_width:
            raise ValueError("bb_width.narrow_threshold must be <= bb_width.max_width")
        return self


class AlphaMrS01SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_regimes: List[str] = Field(..., min_length=1)
    forbid_uncertain: bool = Field(...)
    cooldown_sec: int = Field(..., ge=0)
    signal_ttl_ms: int = Field(..., gt=0)
    missing_component_policy: Literal["suppress"] = Field(...)
    max_intents_per_symbol_hour: int | None = Field(default=None, ge=1)


class AlphaMrS01AssetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...)


class AlphaMrS01StrategyConfig(BaseModel):
    """Separate live-candidate strategy based on S01 weighted MR semantics."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...)
    mode: Literal["disabled", "shadow", "testnet_candidate"] = Field(...)
    source_scenario_id: str = Field(..., min_length=1)
    strategy_version: str = Field(..., min_length=1)
    timeframe_sec: int = Field(..., ge=60, le=3600)
    threshold: float = Field(..., ge=0.0, le=1.0)
    weights: AlphaMrS01WeightsConfig = Field(...)
    rsi: AlphaMrS01RsiConfig = Field(...)
    sma: AlphaMrS01SmaConfig = Field(...)
    stochastic: AlphaMrS01StochasticConfig = Field(...)
    volume: AlphaMrS01VolumeConfig = Field(...)
    bb_width: AlphaMrS01BbWidthConfig = Field(...)
    safety: AlphaMrS01SafetyConfig = Field(...)
    assets: Dict[str, AlphaMrS01AssetConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_mode_enabled(self) -> "AlphaMrS01StrategyConfig":
        if self.mode != "disabled" and not self.enabled:
            raise ValueError("alpha_mr_s01 enabled must be true when mode is not disabled")
        return self
