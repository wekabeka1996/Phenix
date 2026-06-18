from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.config.domains.decision_making import SafetyGatesConfig
from apps.reference.config.shared.atoms import LiquidityGateConfig, StrategyIntentDecisionConfig
from apps.reference.config.shared.instruments import LeverageConfig


class MRStrategyParamsConfig(BaseModel):
    """Strategy parameters for Mean Reversion 1m.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    bb_window: int = Field(..., description='Bollinger Bands window')
    bb_num_std: float = Field(..., description='BB standard deviations')
    atr_window: int = Field(..., description='ATR window for stops')
    rsi_window: int = Field(..., description='RSI window')

    score_multiplier: float = Field(...)

    entry_threshold: float = Field(..., description='%B threshold for entry')
    rsi_oversold: float = Field(..., description='RSI oversold level')
    rsi_overbought: float = Field(..., description='RSI overbought level')

    min_bars: int = Field(..., description='Min bars before trading')
    min_bb_width: float = Field(..., description='Min BB width')
    max_bb_width: float = Field(..., description='Max BB width')

    sl_atr_mult: float = Field(..., description='SL as ATR multiplier')
    tp_to_mid: bool = Field(..., description='Target mid BB')
    cooldown_sec: int = Field(..., description='Cooldown between signals')

    confidence_base: float = Field(
        ..., ge=0.0, le=1.0,
        description='Base confidence when BB threshold touched (0.5 = 50%)'
    )
    confidence_bb_slope: float = Field(
        ..., ge=0.1, le=20.0,
        description='Slope: how fast confidence grows with |pct_b| distance from threshold'
    )
    confidence_rsi_bonus: float = Field(
        ..., ge=0.0, le=0.5,
        description='Confidence bonus when RSI confirms oversold/overbought (0.2 = +20%)'
    )


class MRRegimeThresholdsConfig(BaseModel):
    """Regime thresholds for FLAT regime classification.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    high_vol_pct: float = Field(..., description='ATR% for FLAT_HIGH')
    low_vol_pct: float = Field(..., description='ATR% for FLAT_LOW')


class MRSqueezeExpansionVetoConfig(BaseModel):
    """Per-asset squeeze-expansion veto contract for MR breakout fades."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable squeeze-expansion veto')
    squeeze_width_max: float = Field(
        ..., gt=0.0,
        description='Previous BB width must be at or below this squeeze threshold',
    )
    post_squeeze_width_max: float = Field(
        ..., gt=0.0,
        description='Current BB width must stay at or below this threshold after expansion',
    )
    expansion_ratio_min: float = Field(
        ..., gt=1.0,
        description='Current/previous BB width ratio required to veto breakout fades',
    )
    regimes: List[str] = Field(
        ..., min_length=1,
        description='Flat regimes where the squeeze-expansion veto applies',
    )
    sides: List[Literal["LONG", "SHORT"]] = Field(
        ..., min_length=1,
        description='Signal sides where the squeeze-expansion veto applies',
    )

    @model_validator(mode="after")
    def _validate_width_relationship(self) -> "MRSqueezeExpansionVetoConfig":
        if self.post_squeeze_width_max < self.squeeze_width_max:
            raise ValueError(
                "post_squeeze_width_max must be >= squeeze_width_max")
        return self


class MRMomentumSeparationVetoConfig(BaseModel):
    """Per-asset late-drift veto contract for MR counter-trend fades."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description='Enable late-drift momentum separation veto')
    lookback_bars: int = Field(
        ..., ge=1,
        description='Number of completed bars used to measure directional drift',
    )
    min_drift_pct: float = Field(
        ..., gt=0.0,
        description='Minimum cumulative drift required to veto a counter-trend fade',
    )
    min_current_bb_width: float = Field(
        ..., gt=0.0,
        description='Current BB width floor before the late-drift veto is allowed to engage',
    )
    regimes: List[str] = Field(
        ..., min_length=1,
        description='Flat regimes where the momentum-separation veto applies',
    )
    sides: List[Literal["LONG", "SHORT"]] = Field(
        ..., min_length=1,
        description='Signal sides where the momentum-separation veto applies',
    )


class MRMicrostructureVetoConfig(BaseModel):
    """Vector 1: Microstructure Veto overlay for MR handler.

    Bivariate logic: adverse TFI (+ optional OBI confirm) AND continued adverse
    price response = toxic flow -> veto. Adverse flow WITH absorption evidence
    (wick/rebound) = allowed.

    Fail-closed when required microstructure inputs are missing (configurable).
    OBI is confirm-only - never sole veto driver.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable microstructure veto overlay')

    tfi_ema_span: int = Field(
        ..., ge=2, le=50,
        description='EMA smoothing span applied to raw TFI before veto evaluation',
    )
    tfi_adverse_threshold: float = Field(
        ..., gt=0.0, le=1.0,
        description='Absolute TFI value beyond which flow is classified as adverse',
    )

    obi_confirm_enabled: bool = Field(
        ..., description='When true, adverse TFI must also be confirmed by adverse OBI',
    )
    obi_adverse_threshold: float = Field(
        ..., gt=0.0, le=1.0,
        description='Absolute OBI value beyond which book state confirms adverse flow',
    )

    price_reaction_lookback_sec: int = Field(
        ..., ge=10, le=600,
        description='Seconds of recent price action used to measure continuation vs rebound',
    )
    price_continuation_threshold: float = Field(
        ..., gt=0.0, le=0.05,
        description='Min adverse price move (as fraction) to confirm toxic continuation',
    )

    absorption_wick_ratio_min: float = Field(
        ..., ge=0.0, le=1.0,
        description='Min wick/range ratio on the current bar signaling absorption',
    )
    absorption_rebound_threshold: float = Field(
        ..., ge=0.0, le=0.05,
        description='Min favorable price move (as fraction) signaling rebound / absorption',
    )

    readiness_min_bars: int = Field(
        ..., ge=1, le=100,
        description='Min bars of TFI data before veto can engage (warmup)',
    )

    missing_policy: Literal["block"] = Field(
        ..., description=(
            'Policy when required microstructure features (tfi) are missing: '
            '"block" = fail-closed (veto trade). '
            'NOTE: "skip" was removed in R1 hardening - fail-open is not permitted '
            'in the active runtime contract.'
        ),
    )

    @model_validator(mode="after")
    def _validate_absorption_consistency(self) -> "MRMicrostructureVetoConfig":
        if self.absorption_rebound_threshold >= self.price_continuation_threshold:
            raise ValueError(
                f"absorption_rebound_threshold ({self.absorption_rebound_threshold}) "
                f"must be < price_continuation_threshold ({self.price_continuation_threshold})"
            )
        return self


class MRDirectionalBiasConfig(BaseModel):
    """Vector 2: Directional Bias Injection for MR threshold asymmetry.

    Splits the symmetric entry_threshold into base_long_threshold and
    base_short_threshold, then modulates them dynamically via funding_rate.

    Math contract:
        normalized_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
        if |normalized_funding| < funding_deadband: normalized_funding = 0

        effective_long  = clamp(base_long_threshold  - normalized_funding * funding_shift_magnitude,
                                threshold_clamp_min, threshold_clamp_max)
        effective_short = clamp(base_short_threshold + normalized_funding * funding_shift_magnitude,
                                threshold_clamp_min, threshold_clamp_max)

    Semantics:
        positive funding (longs pay shorts) -> LONG harder (threshold lowered), SHORT easier (threshold raised)
        negative funding (shorts pay longs) -> SHORT harder (threshold lowered), LONG easier (threshold raised)
        missing funding -> static split thresholds (graceful degradation, NO fail-closed)
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable directional bias modulation')

    base_long_threshold: float = Field(
        ..., gt=0.0, le=0.5,
        description='Static %B threshold for LONG entries (lower = stricter)',
    )
    base_short_threshold: float = Field(
        ..., gt=0.0, le=0.5,
        description='Static %B threshold for SHORT entries (lower = stricter)',
    )

    funding_shift_magnitude: float = Field(
        ..., ge=0.0, le=0.2,
        description='Max threshold shift per unit of normalized funding',
    )
    funding_normalization_scale: float = Field(
        ..., gt=0.0,
        description='Funding rate is divided by this before clamping to [-1,1]',
    )
    funding_deadband: float = Field(
        ..., ge=0.0, le=1.0,
        description='Normalized funding within this band is treated as zero (noise suppression)',
    )

    threshold_clamp_min: float = Field(
        ..., ge=0.0, le=0.5,
        description='Minimum legal threshold (prevents degenerate entries)',
    )
    threshold_clamp_max: float = Field(
        ..., ge=0.0, le=0.5,
        description='Maximum legal threshold (prevents unreachable entries)',
    )

    @model_validator(mode="after")
    def _validate_clamp_range(self) -> "MRDirectionalBiasConfig":
        if self.threshold_clamp_min >= self.threshold_clamp_max:
            raise ValueError(
                f"threshold_clamp_min ({self.threshold_clamp_min}) "
                f"must be < threshold_clamp_max ({self.threshold_clamp_max})"
            )
        if not (self.threshold_clamp_min <= self.base_long_threshold <= self.threshold_clamp_max):
            raise ValueError(
                f"base_long_threshold ({self.base_long_threshold}) "
                f"must be within [{self.threshold_clamp_min}, {self.threshold_clamp_max}]"
            )
        if not (self.threshold_clamp_min <= self.base_short_threshold <= self.threshold_clamp_max):
            raise ValueError(
                f"base_short_threshold ({self.base_short_threshold}) "
                f"must be within [{self.threshold_clamp_min}, {self.threshold_clamp_max}]"
            )
        return self


class MRStrategyOverrideConfig(BaseModel):
    """Per-asset strategy parameter overrides for MR.

    These override the global MRStrategyParamsConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')

    bb_window: Optional[int] = Field(
        ..., description='BB window size')
    bb_num_std: Optional[float] = Field(
        ..., description='BB std multiplier')
    min_bb_width: Optional[float] = Field(
        ..., description='Min BB width filter')
    flat_low_short_min_bb_width: Optional[float] = Field(
        ..., description='Optional stricter BB width floor for FLAT_LOW short setups only',
    )
    squeeze_expansion_veto: Optional[MRSqueezeExpansionVetoConfig] = Field(
        ..., description='Optional squeeze-expansion veto for breakout-from-squeeze fade traps',
    )
    momentum_separation_veto: Optional[MRMomentumSeparationVetoConfig] = Field(
        ..., description='Optional late-drift veto for counter-trend fade traps after expansion',
    )
    microstructure_veto: Optional[MRMicrostructureVetoConfig] = Field(
        ..., description='Optional Vector 1 microstructure veto overlay (per-asset override)',
    )
    directional_bias: Optional[MRDirectionalBiasConfig] = Field(
        ..., description='Optional Vector 2 directional bias threshold modulation (per-asset override)',
    )
    entry_threshold: Optional[float] = Field(
        ..., description='Entry distance threshold')
    tp_to_mid: Optional[bool] = Field(
        ..., description='TP to mid vs outer band')
    sl_atr_mult: Optional[float] = Field(
        ..., description='SL ATR multiplier override')
    cooldown_sec: Optional[int] = Field(
        ..., description='Cooldown between trades')
    sl_buffer_pct: Optional[float] = Field(
        ..., description='Additional SL buffer percentage (0.002 = 0.20%)')
    tp_buffer_pct: Optional[float] = Field(
        ..., description='Additional TP buffer percentage (0.002 = 0.20%)')
    allowed_regimes: Optional[List[str]] = Field(
        ..., description='Override allowed regimes for this symbol')
    confidence_base: Optional[float] = Field(
        ..., ge=0.0, le=1.0, description='Override base confidence scalar')
    confidence_bb_slope: Optional[float] = Field(
        ..., ge=0.1, le=20.0, description='Override BB slope multiplier')
    confidence_rsi_bonus: Optional[float] = Field(
        ..., ge=0.0, le=0.5, description='Override RSI confirmation bonus')


class MRAssetConfig(BaseModel):
    """Per-asset configuration for Mean Reversion 1m.

    UPDATED: Now supports typed strategy/risk overrides.
    P1: Added leverage field for Active Leverage Management.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    leverage: Optional[LeverageConfig] = Field(
        ..., description='Per-asset leverage configuration. Read by LeverageBootstrapper at startup.'
    )
    strategy: Optional[MRStrategyOverrideConfig] = Field(
        ..., description='Strategy parameter overrides for this symbol')
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        ..., description='Per-asset liquidity gate override')
    allowed_regimes: List[str] = Field(
        ..., description='Regimes where trading is allowed')
    position_mode: Literal["STRICT", "DYNAMIC"] = Field(
        ..., description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap')


class MRRegimeSizingConfig(BaseModel):
    """Sizing/stop/target multipliers for a specific FLAT regime.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    sizing_mult: float = Field(...)
    stop_mult: float = Field(...)
    target_mult: float = Field(...)


class MeanReversion1mStrategyConfig(BaseModel):
    """Full configuration for Mean Reversion 1m Strategy.

    Config is provided via config.strategies.mean_reversion (loaded from strategy profile SSOT).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable MR 1m strategy')
    mode: Literal['disabled', 'shadow', 'testnet_candidate', 'runtime'] = Field(
        ..., description='Financial authority mode for the strategy')
    timeframe_sec: int = Field(
        ..., ge=60, le=3600, description='Bar timeframe in seconds')
    strategy: MRStrategyParamsConfig = Field(...)
    regime_thresholds: MRRegimeThresholdsConfig = Field(...)
    assets: Dict[str, MRAssetConfig] = Field(...)
    regime_sizing: Dict[str, MRRegimeSizingConfig] = Field(...)
    allowed_regimes: List[str] = Field(
        ..., description='Whitelist of Flat regimes to trade in (global default)')
    allowed_sides: List[Literal['BUY', 'SELL']] = Field(
        default=['BUY', 'SELL'], min_length=1)
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        ..., description='Global liquidity gate for MR')
    execution: "StrategyExecutionConfig" = Field(
        ..., description='Execution policy (SSOT)')
    decision: Optional[StrategyIntentDecisionConfig] = Field(default=None)
    safety_gates: SafetyGatesConfig = Field(
        ..., description='Safety gates control (directional/price motion gates)'
    )
    objective: Optional["StrategyObjectiveConfig"] = Field(
        ..., description='Strategy objective configuration'
    )
    microstructure_veto: Optional[MRMicrostructureVetoConfig] = Field(
        ..., description='Global microstructure veto overlay config (can be overridden per-asset)',
    )
    directional_bias: Optional[MRDirectionalBiasConfig] = Field(
        ..., description='Global directional bias config (can be overridden per-asset)',
    )
