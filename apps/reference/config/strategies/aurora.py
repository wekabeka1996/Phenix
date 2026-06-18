from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.config.domains.decision_making import (
    DecisionConfig,
    HoldingPeriodConfig,
    SafetyGatesConfig,
)
from apps.reference.config.shared.atoms import LiquidityGateConfig


class AuroraSideBiasConfig(BaseModel):
    """Aurora side-bias configuration per instrument."""

    model_config = ConfigDict(extra="forbid")

    penalty_factor: Optional[float] = Field(
        ..., description="Penalty multiplier for counter-bias trades"
    )
    window_sec: Optional[int] = Field(
        ..., description="Rolling window in seconds for side bias calculation"
    )
    target_ratio: Optional[float] = Field(
        ..., description="Target long/short ratio (e.g., 0.5 = balanced)"
    )


class RegimeTpSlConfig(BaseModel):
    """Regime-aware TP/SL configuration for the Aurora strategy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        False, description="Enable regime-based TP/SL. False = legacy behavior.",
    )
    mode: Literal["pct_mult", "atr"] = Field(
        "pct_mult", description="Calculation mode: pct_mult (simple) or atr (volatility-based)",
    )
    sl_mult: Dict[str, float] = Field(
        default_factory=lambda: {"DEFAULT": 1.0},
        description="SL multiplier per regime (requires DEFAULT key)",
    )
    tp_mult: Dict[str, float] = Field(
        default_factory=lambda: {"DEFAULT": 1.0},
        description="TP RR multiplier per regime (requires DEFAULT key)",
    )
    sl_k_atr: Optional[Dict[str, float]] = Field(
        None, description="SL as k×ATR% per regime (atr mode only)",
    )
    rr_by_regime: Optional[Dict[str, float]] = Field(
        None, description="Risk-reward ratio per regime (atr mode only)",
    )
    min_sl_pct: float = Field(
        0.003, description="Min SL% (0.3%) - clamp up if below",
    )
    max_sl_pct: float = Field(
        0.06, description="Max SL% (6%) - clamp down if above",
    )
    min_tp_rr: float = Field(
        0.3, description="Min TP RR ratio - clamp up if below",
    )
    max_tp_rr: float = Field(
        3.0, description="Max TP RR ratio - clamp down if above",
    )
    min_dist_bps: int = Field(
        15, description="Min distance in bps from entry to SL/TP - FAIL-CLOSED if below (cannot clamp)",
    )

    @model_validator(mode="after")
    def validate_default_keys(self) -> "RegimeTpSlConfig":
        """Fail closed: DEFAULT key is mandatory in multiplier dictionaries."""
        if self.mode == "pct_mult":
            if "DEFAULT" not in self.sl_mult:
                raise ValueError("sl_mult must contain 'DEFAULT' key")
            if "DEFAULT" not in self.tp_mult:
                raise ValueError("tp_mult must contain 'DEFAULT' key")
        elif self.mode == "atr":
            if self.sl_k_atr is None or "DEFAULT" not in self.sl_k_atr:
                raise ValueError("sl_k_atr must contain 'DEFAULT' key")
            if self.rr_by_regime is None or "DEFAULT" not in self.rr_by_regime:
                raise ValueError("rr_by_regime must contain 'DEFAULT' key")
        return self


class AuroraExitConfig(BaseModel):
    """Aurora exit / stop-loss configuration per instrument."""

    model_config = ConfigDict(extra="forbid")

    sl_pct: Optional[float] = Field(
        ..., description="Stop-loss as percentage from entry (e.g., 0.005 = 0.5%)"
    )
    max_hold_sec: Optional[int] = Field(
        ..., description="Maximum position hold time in seconds"
    )
    regime_tpsl: Optional[RegimeTpSlConfig] = Field(
        ..., description="Regime-based TP/SL config (AURORA_REGIME_TP_SL_PLAN)",
    )


class AuroraTakeProfitConfig(BaseModel):
    """Aurora take-profit configuration per instrument."""

    model_config = ConfigDict(extra="forbid")

    tp_low_ratio: Optional[float] = Field(
        ..., description="TP1 as ratio to ATR or fixed percent"
    )
    tp_high_ratio: Optional[float] = Field(
        ..., description="TP2 as ratio to ATR or fixed percent"
    )
    partial_exit_pct: Optional[float] = Field(
        ..., description="Percentage to exit at TP1 (e.g., 0.7 = 70%)"
    )


class AuroraTrailingStopConfig(BaseModel):
    """Aurora trailing-stop configuration per instrument."""

    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(..., description="Enable trailing stop")
    activation_pct: Optional[float] = Field(
        ..., description="Activate trailing after this profit % (e.g., 0.003 = 0.3%)"
    )
    trail_pct: Optional[float] = Field(
        ..., description="Trail distance as % from high-water mark (fallback if ATR unavailable)"
    )
    trail_atr_mult: Optional[float] = Field(
        ..., description="Trail distance = ATR × this multiplier (preferred over trail_pct)",
    )
    min_update_interval_sec: Optional[int] = Field(
        ..., description="Minimum seconds between SL updates (rate limit)"
    )


class AuroraExecutionConfig(BaseModel):
    """Aurora execution-specific configuration per instrument."""

    model_config = ConfigDict(extra="forbid")

    order_type: Optional[str] = Field(...,
                                      description="Order type: LIMIT, MARKET")
    post_only: Optional[bool] = Field(
        ..., description="Use post-only orders for maker fees"
    )
    max_slippage_bps: Optional[int] = Field(
        ..., description="Max allowed slippage in basis points"
    )


class EmaClampConfig(BaseModel):
    """Per-asset EMA clamp range override."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable per-asset clamp override")
    clamp_min: Optional[float] = Field(
        ..., description="Override global ema_bias.clamp_min"
    )
    clamp_max: Optional[float] = Field(
        ..., description="Override global ema_bias.clamp_max"
    )


class SignalThresholdConfig(BaseModel):
    """Per-asset signal-threshold override."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(...,
                          description="Enable per-asset threshold override")
    value: Optional[float] = Field(
        ..., description="Override global signal_threshold")


class MaxRiskScoreConfig(BaseModel):
    """Per-asset max-risk-score override."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Enable per-asset max_risk_score override")
    value: Optional[float] = Field(
        ..., description="Max risk score threshold for entry filtering"
    )

    @model_validator(mode="after")
    def _validate_enabled_requires_value(self) -> "MaxRiskScoreConfig":
        if self.enabled and self.value is None:
            raise ValueError(
                "max_risk_score.enabled=true requires max_risk_score.value (omit override to inherit)"
            )
        return self


class VolatilityEntryConfig(BaseModel):
    """Volatility-based limit entry pricing."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Enable volatility-based entry pricing",
    )
    regime_multipliers: Dict[str, float] = Field(
        ..., description="Regime -> multiplier. MUST include 'DEFAULT' key (fail-closed)."
    )

    @model_validator(mode="after")
    def validate_default_exists(self) -> "VolatilityEntryConfig":
        if "DEFAULT" not in self.regime_multipliers:
            raise ValueError(
                "volatility_entry_logic.regime_multipliers must contain 'DEFAULT' key (fail-closed)"
            )
        return self


class AuroraLeverageOverrideConfig(BaseModel):
    """Aurora per-symbol leverage override — only the non-SSOT field survives.

    LEV-TARGET-MODE-REMOVE-2026-05-10: leverage.target and leverage.mode removed.
    Canonical values are in instruments.yaml (instruments.execution.target_leverage /
    instruments.execution.margin_mode). Only max_notional_value is retained as an
    optional per-symbol notional cap override.
    """

    model_config = ConfigDict(extra="forbid")

    max_notional_value: Optional[Decimal] = Field(
        None,
        description=(
            "Optional per-symbol notional cap (USDT). "
            "None = 1_000_000 USDT default applied by quantizer. "
            "Separate from SSOT leverage (instruments.yaml)."
        ),
    )


CANONICAL_WEIGHT_KEYS = frozenset(
    {
        "obi",
        "tfi",
        "delta_price",
        "ema_bias",
        "volume_spike",
        "volatility_state",
        "depth_imbalance",
        "macro_sync",
        "macro_resid",
        "absorption",
    }
)


class AuroraInstrumentConfig(BaseModel):
    """Complete per-instrument configuration for the Aurora strategy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Enable Aurora strategy for this instrument (default: True for backward compat)"
    )
    weights: Optional[Dict[str, float]] = Field(
        ..., description="Per-feature signal weights from Optuna",
    )

    @field_validator("weights", mode="before")
    @classmethod
    def validate_weight_keys(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, dict):
            return value
        invalid_keys = set(value.keys()) - CANONICAL_WEIGHT_KEYS
        if invalid_keys:
            raise ValueError(
                f"Invalid weight keys: {sorted(invalid_keys)}. "
                f"Valid canonical keys: {sorted(CANONICAL_WEIGHT_KEYS)}. "
                f"(TASK54: Weight Key Mismatch Fix)"
            )
        return value

    side_bias: Optional[AuroraSideBiasConfig] = Field(
        ..., description="Side bias configuration",
    )
    position_mode: Optional[Literal["STRICT", "DYNAMIC"]] = Field(
        ..., description="STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap",
    )
    leverage: Optional[AuroraLeverageOverrideConfig] = Field(
        ..., description="Per-symbol leverage override (max_notional_value only). "
                         "Canonical leverage/margin-mode live in instruments.yaml.",
    )
    regime_thresholds: Optional[Dict[str, float]] = Field(
        ..., description="Threshold multipliers per regime (TREND, VOLATILE, FLAT)",
    )
    regime_sizing: Optional[Dict[str, float]] = Field(
        ..., description="Position size multipliers per regime",
    )
    exit: Optional[AuroraExitConfig] = Field(
        ..., description="Stop-loss and max hold time",
    )
    take_profit: Optional[AuroraTakeProfitConfig] = Field(
        ..., description="TP1/TP2 partial exit settings",
    )
    trailing_stop: Optional[AuroraTrailingStopConfig] = Field(
        ..., description="Trailing stop settings",
    )
    signal_threshold: Optional[SignalThresholdConfig] = Field(
        ..., description="Per-asset signal threshold (Phase 3+)",
    )
    max_risk_score: Optional[MaxRiskScoreConfig] = Field(
        ..., description="Per-asset max risk score (Phase 3+)",
    )
    cooldown_sec: Optional[int] = Field(
        ..., description="Per-instrument cooldown in seconds (overrides global qos.symbol_cooldown_sec)",
    )
    allowed_regimes: Optional[List[str]] = Field(
        ..., description="If set, only trade when current regime is in this list (Phase 3+ regime gating)",
    )
    scoring_version: Optional[Literal["v1", "v2"]] = Field(
        ..., description="DEPRECATED: Per-asset scoring version override (non-operational, Quadratic only)",
    )
    feature_neutrals: Optional[Dict[str, float]] = Field(
        ..., description="Override neutral offsets",
    )
    essential_features: Optional[List[str]] = Field(
        ..., description="Override essential features list",
    )
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        ..., description="Override liquidity gate",
    )
    holding_period: Optional[HoldingPeriodConfig] = Field(
        ..., description="Per-symbol holding period override (RFC: docs/RFC_min_duration_logic.md)",
    )
    reentry_cooldown_sec: Optional[int] = Field(
        ..., description="Per-symbol re-entry cooldown override (seconds)",
    )
    timeframe_sec: Optional[int] = Field(
        ..., description="Bar timeframe in seconds for this instrument. SOL=180 (3m), BTC/ETH=300 (5m)",
    )
    volatility_entry_logic: Optional[VolatilityEntryConfig] = Field(
        ..., description="Volatility-based limit entry pricing (Maker/GTX compliance)",
    )


class StrategyExecutionConfig(BaseModel):
    """Execution policy for strategies (ORDER-POLICY-01)."""

    model_config = ConfigDict(extra="forbid")

    entry_order_type: Literal["LIMIT", "MARKET"] = Field(...)
    entry_tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        ..., description="Time-in-force for LIMIT orders. Required for LIMIT, None for MARKET.",
    )
    exit_order_type: Optional[Literal["LIMIT", "MARKET"]] = Field(...)
    exit_tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        ...)
    exit_limit_ttl_ms: Optional[int] = Field(..., ge=1)
    gtx_retry_max: int = Field(..., ge=0, le=10)
    gtx_retry_offset_bps: float = Field(..., ge=0.0)


class AuroraStrategyConfig(BaseModel):
    """Aurora strategy SSOT config."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable Aurora strategy globally")
    mode: Literal["disabled", "shadow", "testnet_candidate", "runtime"] = Field(
        ...,
        description="Financial authority mode for the strategy.",
    )
    type: str = Field(...,
                      description="Strategy type identifier (informational)")
    description: str = Field(
        ..., description="Human description of the strategy profile"
    )
    timeframe_sec: int = Field(
        ..., ge=60,
        le=3600,
        description="Bar timeframe in seconds",
    )
    allowed_sides: List[Literal["BUY", "SELL"]] = Field(
        default=["BUY", "SELL"], min_length=1)
    execution: StrategyExecutionConfig = Field(
        ..., description="Execution policy (SSOT)")
    safety_gates: SafetyGatesConfig = Field(
        ..., description="Safety gates control (directional/price motion gates)"
    )
    shadow_mode_enabled: bool = Field(
        ..., description="Enable shadow mode: compare legacy scoring with kernel and log divergences",
    )
    objective: Optional["StrategyObjectiveConfig"] = Field(
        ..., description="Strategy objective configuration",
    )
    decision: DecisionConfig = Field(
        ..., description="Aurora decision policy (global defaults)"
    )
    assets: Dict[str, AuroraInstrumentConfig] = Field(
        ..., description="Per-symbol Aurora overrides (symbol -> config)"
    )
