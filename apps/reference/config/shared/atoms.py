from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SignalWeights(BaseModel):
    """Weights for signal calculation (OBI, TFI, etc)."""

    model_config = ConfigDict(extra="forbid")

    obi: float = Field(...)
    tfi: float = Field(...)
    delta_price: float = Field(...)
    ema_bias: float = Field(...)
    volume_spike: float = Field(...)
    volatility_state: float = Field(...)
    depth_imbalance: float = Field(...)
    macro_resid: float = Field(
        ..., description="R1: Beta-adjusted residual weight (SIGNED, neutral=0)"
    )
    macro_sync: Optional[float] = Field(
        ..., description="DEPRECATED: Use macro_resid. Kept for backward compat.",
    )
    absorption: float = Field(
        ..., description=(
            "R2: Absorption feature weight (SIGNED [-1,1], neutral=0.0). "
            "0.0 = disabled (backward compat). Set >0 after Phase 2 calibration."
        ),
    )


class BarGatingConfig(BaseModel):
    """Bar gating configuration for decision making."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = Field(...)
    bar_ms: int = Field(..., description="Bar duration in milliseconds")


class BehaviorFsmConfig(BaseModel):
    """Behavioral FSM configuration."""

    model_config = ConfigDict(extra="forbid")

    enable: bool = Field(...)
    high_vol_multiplier: float = Field(...)
    low_vol_multiplier: float = Field(...)


class SignalsConfig(BaseModel):
    """Signals configuration (strategy-level, SSOT)."""

    model_config = ConfigDict(extra="forbid")

    normalize_signals_mode: Literal["signed_v2"] = Field(
        ..., description=(
            "Signal normalization mode. Production invariant is 'signed_v2'. "
            "No other value is valid in production config. "
            "Forensic/offline passthrough: pass normalize_mode='off' directly to the scoring fn, "
            "bypassing this config. 'legacy_v1' + 'off' removed from YAML boundary."
        )
    )
    enable_new_metrics: bool = Field(...)
    delta_price_cap_pct: float = Field(
        ..., gt=0.0,
        le=1.0,
        description="Delta price cap as pct of price (e.g. 0.02 = 2%). Required (no hardcoded fallback).",
    )


class DirectionStrengthScoringConfig(BaseModel):
    """Direction/Strength split configuration (strategy-level, SSOT)."""

    model_config = ConfigDict(extra="forbid")

    directional_features: List[str] = Field(
        ..., description="Signed features that define direction (dir component)."
    )
    strength_features: List[str] = Field(
        ..., description="Magnitude/confirmation features (strength component)."
    )
    strength_alpha: float = Field(
        ..., ge=0.0,
        description="Strength influence: final = dir * (1 + strength_alpha * strength).",
    )
    strength_cap: float = Field(
        ..., ge=0.0,
        description="Clamp for strength component (>=0).",
    )

    @model_validator(mode="after")
    def _validate_directional_nonempty(self) -> "DirectionStrengthScoringConfig":
        if not self.directional_features:
            raise ValueError(
                "directional_features must be non-empty (SSOT-required)")
        return self


class LiquidityGateConfig(BaseModel):
    """Configuration for Liquidity Gate (Score V2)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable liquidity gate")
    kappa_min: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Minimum kappa required to pass gate",
    )
    kappa_max: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Max kappa (clamping)",
    )
    failsafe_qty_check: bool = Field(
        ..., description="[NOT_IMPLEMENTED] Reserved: double-check min_qty even if gate passes",
    )


class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""

    model_config = ConfigDict(extra="forbid")

    min_position_size_usd: float = Field(...)
    liquidity_based_cap_usd: float = Field(...)


class KellyConfig(BaseModel):
    """Kelly criterion configuration."""

    model_config = ConfigDict(extra="forbid")

    base_probability: float = Field(...)
    kelly_cap: float = Field(...)
    kelly_alpha: float = Field(...)
    payoff_ratio_r: float = Field(...)
    p_min: float = Field(..., description="Minimum probability clamp")
    p_max: float = Field(..., description="Maximum probability clamp")
    uplift_factor: float = Field(
        ..., description="Score-to-probability uplift multiplier",
    )


class QosConfig(BaseModel):
    """Quality of Service configuration for rate limiting."""

    model_config = ConfigDict(extra="forbid")

    exposure_block_cooldown_sec: int = Field(...)
    symbol_cooldown_sec: int = Field(
        ..., description="Global fallback cooldown. Per-symbol config takes priority."
    )
    max_intents_per_minute_per_symbol: int = Field(...)
    mode: str = Field(..., description="defer | block")
    enforce: bool = Field(...)
    apply_to_strategies: List[str] = Field(
        ..., description=(
            "Optional allowlist of strategy_id values that should have QoS applied in the strategy gateway. "
            "Empty => apply to all strategies (backward compatible)."
        ),
    )


class ROIExitConfig(BaseModel):
    """ROI Exit Strategy configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...)
    target_roi_pct: float = Field(...)


class PrecisionConfig(BaseModel):
    """Position precision configuration."""

    model_config = ConfigDict(extra="forbid")

    quantity_min_threshold: float = Field(...)
    flat_position_threshold: float = Field(...)
    decimal_places: int = Field(...)


__all__ = [
    "BarGatingConfig",
    "BehaviorFsmConfig",
    "DirectionStrengthScoringConfig",
    "KellyConfig",
    "LiquidityGateConfig",
    "PositionSizingConfig",
    "PrecisionConfig",
    "QosConfig",
    "ROIExitConfig",
    "SignalWeights",
    "SignalsConfig",
]
