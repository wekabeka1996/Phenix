"""
Pydantic V2 configuration models for AuroraTrader.

This module defines the complete configuration schema with full type validation.
All models are designed to fail fast (startup validation) rather than silently accepting invalid configs.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class InstrumentSpec(BaseModel):
    """Specification for a trading instrument (e.g., BTCUSDT)."""
    model_config = ConfigDict(
        extra='forbid')

    symbol: str = Field(...)
    step_size: str = Field(default="0.001", description="Quantity precision")
    tick_size: str = Field(default="0.01", description="Price precision")
    min_qty: str = Field(default="0.001")
    min_notional: str = Field(
        default="10.0", description="Minimum notional value in USDT")
    quote: str = Field(default="USDT")


class InstrumentPrecisionSpec(BaseModel):
    """Canonical Aurora instrument precision (SSOT from instruments.yaml).

    Keep this model permissive (extra=allow) to avoid breaking exchange-specific tails.
    tick_size/step_size are enforced for active symbols via loader fail-fast checks.
    """

    model_config = ConfigDict(extra='allow')

    symbol: Optional[str] = Field(default=None)
    tick_size: Optional[float] = Field(default=None)
    step_size: Optional[float] = Field(default=None)


class SignalWeights(BaseModel):
    """Weights for signal calculation (OBI, TFI, etc).
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    obi: float = Field(default=0.2)
    tfi: float = Field(default=0.2)
    delta_price: float = Field(default=0.2)
    ema_bias: float = Field(default=0.15)
    volume_spike: float = Field(default=0.15)
    volatility_state: float = Field(default=0.05)
    depth_imbalance: float = Field(default=0.05)
    macro_sync: float = Field(default=0.05)


class BarGatingConfig(BaseModel):
    """Bar gating configuration for decision making."""
    enable: bool = Field(default=False)
    bar_ms: int = Field(default=15 * 60 * 1000,
                        description="Bar duration in milliseconds")


class BehaviorFsmConfig(BaseModel):
    """Behavioral FSM configuration."""
    enable: bool = Field(default=False)
    high_vol_multiplier: float = Field(default=2.0)
    low_vol_multiplier: float = Field(default=0.5)


class SignalsConfig(BaseModel):
    """Signals configuration."""
    normalize: bool = Field(default=True)
    enable_new_metrics: bool = Field(default=False)


class RegimeSizingSymbolConfig(BaseModel):
    """Per-symbol regime sizing configuration (ETAP3).
    
    Controls volatility-based position sizing multipliers for a specific symbol.
    When enabled, position size = base * multiplier(volatility_state).
    
    base_notional = per_symbol_margin_fraction * equity * effective_leverage
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False, description="Enable regime-based sizing for this symbol")
    low_vol_multiplier: float = Field(default=1.0, description="Multiplier for LOW_VOLATILITY regime (calm)")
    high_vol_multiplier: float = Field(default=1.0, description="Multiplier for HIGH_VOLATILITY regime (storm)")


class RiskContractV1Config(BaseModel):
    """Risk-Sizing V1 configuration contract.
    
    ETAP3: All sizing via % of equity, no fixed USD in runtime.
    
    Formulas:
    - base_notional = per_symbol_margin_fraction[symbol] * equity * effective_leverage
    - regime_target = base_notional * multiplier(volatility_state)
    - cap_notional = base_notional (same %)
    """
    model_config = ConfigDict(extra='allow')
    
    enabled: bool = Field(default=False, description="Enable Risk-Sizing V1")
    effective_leverage: float = Field(default=10.0, description="Assumed leverage for notional calculation")
    
    # Per-symbol margin fractions (% of equity → notional)
    per_symbol_margin_fraction: Dict[str, float] = Field(
        default_factory=dict,
        description="Target margin fraction per symbol (e.g., BTCUSDT: 0.04)"
    )
    
    # Per-symbol regime sizing config (ETAP3)
    regime_sizing: Dict[str, RegimeSizingSymbolConfig] = Field(
        default_factory=dict,
        description="Per-symbol regime-based sizing config"
    )



class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    min_position_size_usd: float = Field(default=10.0)
    liquidity_based_cap_usd: float = Field(default=10000.0)
    risk_fraction_q: Optional[float] = Field(default=None)
    liquidity_kappa: float = Field(default=1.0)
    kappa_mode: str = Field(default="passive")
    liquidity_kappa_mode: Optional[str] = Field(default=None, description="Alias for kappa_mode (legacy)")
    
    # Risk-Sizing V1 contract (ETAP1: config-only, not used in runtime)
    risk_contract_v1: Optional[RiskContractV1Config] = Field(
        default=None,
        description="Risk-Sizing V1 contract (ETAP1: disabled by default)"
    )



class KellyConfig(BaseModel):
    """Kelly criterion configuration."""
    base_probability: float = Field(default=0.5)
    kelly_cap: float = Field(default=0.25)
    kelly_alpha: float = Field(default=0.8)
    payoff_ratio_r: float = Field(default=1.5)


class QosConfig(BaseModel):
    """Quality of Service configuration for rate limiting."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    exposure_block_cooldown_sec: int = Field(default=60)
    # Global fallback for per-symbol cooldown (aurora_instruments.<SYMBOL>.cooldown_sec takes priority)
    symbol_cooldown_sec: int = Field(default=3, description="Global fallback cooldown. Per-symbol config takes priority.")
    max_intents_per_minute_per_symbol: int = Field(default=10)
    mode: str = Field(default="defer", description="defer | block")
    enforce: bool = Field(default=False)


class ROIExitConfig(BaseModel):
    """ROI Exit Strategy configuration."""
    enabled: bool = Field(default=True)
    target_roi_pct: float = Field(default=50.0)


class FailsafeConfig(BaseModel):
    """Failsafe configuration."""
    max_hold_sec: int = Field(default=86400)


class MeanReversionConfig(BaseModel):
    """Configuration for Mean Reversion regime model (regime.yaml SSOT).
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema, no runtime surprises).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False)
    bb_window: int = Field(default=20)
    bb_std_dev: float = Field(default=2.0)
    min_vol_atr: float = Field(default=0.001)
    allowed_regimes: List[str] = Field(default_factory=lambda: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"])


# ============================================================================
# Mean Reversion 1m Strategy Configuration (Track B)
# ============================================================================

class MRStrategyParamsConfig(BaseModel):
    """Strategy parameters for Mean Reversion 1m.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    bb_window: int = Field(default=20, description="Bollinger Bands window")
    bb_num_std: float = Field(default=2.0, description="BB standard deviations")
    atr_window: int = Field(default=14, description="ATR window for stops")
    rsi_window: int = Field(default=14, description="RSI window")
    
    entry_threshold: float = Field(default=0.05, description="%B threshold for entry")
    rsi_oversold: float = Field(default=30.0, description="RSI oversold level")
    rsi_overbought: float = Field(default=70.0, description="RSI overbought level")
    
    min_bars: int = Field(default=25, description="Min bars before trading")
    min_bb_width: float = Field(default=0.001, description="Min BB width")
    max_bb_width: float = Field(default=0.05, description="Max BB width")
    
    sl_atr_mult: float = Field(default=1.5, description="SL as ATR multiplier")
    tp_to_mid: bool = Field(default=True, description="Target mid BB")
    cooldown_sec: int = Field(default=60, description="Cooldown between signals")


class MRRegimeThresholdsConfig(BaseModel):
    """Regime thresholds for FLAT regime classification.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    high_vol_pct: float = Field(default=0.003, description="ATR% for FLAT_HIGH")
    low_vol_pct: float = Field(default=0.001, description="ATR% for FLAT_LOW")


class MRStrategyOverrideConfig(BaseModel):
    """Per-asset strategy parameter overrides for MR.
    
    These override the global MRStrategyParamsConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')
    
    bb_window: Optional[int] = Field(default=None, description="BB window size")
    bb_num_std: Optional[float] = Field(default=None, description="BB std multiplier")
    min_bb_width: Optional[float] = Field(default=None, description="Min BB width filter")
    entry_threshold: Optional[float] = Field(default=None, description="Entry distance threshold")
    tp_to_mid: Optional[bool] = Field(default=None, description="TP to mid vs outer band")
    sl_atr_mult: Optional[float] = Field(default=None, description="SL ATR multiplier override")
    cooldown_sec: Optional[int] = Field(default=None, description="Cooldown between trades")


class MRAssetRiskConfig(BaseModel):
    """Per-asset risk configuration for MR.
    
    Overrides global MRRiskConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')
    
    position_size_usd: Optional[float] = Field(default=None, description="Position size in USD")
    max_risk_score: Optional[float] = Field(default=None, description="Max risk score threshold")


class MRAssetConfig(BaseModel):
    """Per-asset configuration for Mean Reversion 1m.
    
    UPDATED: Now supports typed strategy/risk overrides.
    """
    model_config = ConfigDict(extra='forbid')  # CFG-LEGACY-SUNSET-11: YAML migration complete
    
    enabled: bool = Field(default=False)
    
    # NEW: Typed strategy overrides
    strategy: Optional[MRStrategyOverrideConfig] = Field(
        default=None,
        description="Strategy parameter overrides for this symbol"
    )
    
    # NEW: Typed risk config
    risk: Optional[MRAssetRiskConfig] = Field(
        default=None,
        description="Risk configuration for this symbol"
    )
    
    # Legacy flat fields (kept for backward compatibility, will be deprecated)
    bb_window: Optional[int] = Field(default=None)
    min_vol_atr: Optional[float] = Field(default=None)
    sl_pct: Optional[float] = Field(default=None, description="SL as percent (e.g., 0.019 = 1.9%)")
    
    allowed_regimes: List[str] = Field(
        default_factory=lambda: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        description="Regimes where trading is allowed"
    )

    position_mode: Literal["STRICT", "DYNAMIC"] = Field(
        default="DYNAMIC",
        description="STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap"
    )


class MRRegimeSizingConfig(BaseModel):
    """Sizing/stop/target multipliers for a specific FLAT regime.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    sizing_mult: float = Field(default=1.0)
    stop_mult: float = Field(default=1.0)
    target_mult: float = Field(default=1.0)


class MRRiskConfig(BaseModel):
    """Risk management for Mean Reversion 1m.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    position_size_usd: float = Field(default=100.0)
    max_concurrent_positions: int = Field(default=3)
    daily_loss_limit_usd: float = Field(default=50.0)
    expected_pnl_multiplier: float = Field(default=1.5)
    fees_pct: float = Field(default=0.0004)
    slippage_pct: float = Field(default=0.0002)


class MeanReversion1mStrategyConfig(BaseModel):
    """
    Full configuration for Mean Reversion 1m Strategy.
    
    Config is provided via root.mean_reversion_1m (loaded from strategy profile SSOT).
    """
    model_config = ConfigDict(extra='allow')
    
    # Master enable flag (feature flag)
    enabled: bool = Field(default=False, description="Enable MR 1m strategy")
    
    # Timeframe
    timeframe_sec: int = Field(default=60, description="Bar timeframe in seconds")
    
    # Strategy parameters
    strategy: MRStrategyParamsConfig = Field(default_factory=MRStrategyParamsConfig)
    
    # Regime thresholds
    regime_thresholds: MRRegimeThresholdsConfig = Field(default_factory=MRRegimeThresholdsConfig)
    
    # Per-asset configurations (symbol → config)
    assets: Dict[str, MRAssetConfig] = Field(default_factory=dict)
    
    # Regime sizing (regime_name → multipliers)
    regime_sizing: Dict[str, MRRegimeSizingConfig] = Field(default_factory=dict)
    
    # Global allowed regimes whitelist (can be overridden per-asset in assets.X.allowed_regimes)
    allowed_regimes: List[str] = Field(
        default_factory=lambda: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        description="Whitelist of Flat regimes to trade in (global default)"
    )
    
    # Risk management
    risk: MRRiskConfig = Field(default_factory=MRRiskConfig)
    
    # Strict Sequential Trading Contract: MR emission mode
    # true (default) = MR emits EVT:TRADE_INTENT_PROPOSED directly (legacy behavior)
    # false = MR emits EVT:MR_SIGNAL_PRODUCED, DecisionMaking applies gates
    emit_trade_intent_directly: bool = Field(
        default=True, 
        description="If true, MR emits trade intent directly (legacy). If false, emits MR_SIGNAL for DM gateway."
    )

# ==============================================================================
# STRATEGIES REGISTRY (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
# ==============================================================================

class StrategiesArbitrationLoggingConfig(BaseModel):
    """Logging configuration for strategy arbitration."""
    model_config = ConfigDict(extra='forbid')
    
    rejected_why_prefix: str = Field(
        default="ARBITRATION_REJECT",
        description="Prefix for why-codes when strategy intent is rejected"
    )
    log_level: str = Field(
        default="INFO",
        description="Log level for arbitration events (INFO/WARNING/ERROR)"
    )


class StrategiesArbitrationConfig(BaseModel):
    """Configuration for strategy conflict arbitration."""
    model_config = ConfigDict(extra='forbid')
    
    mode: Literal['priority'] = Field(
        default="priority",
        description="Arbitration mode: 'priority' (only supported mode, lower number = higher priority)"
    )
    priority: Dict[str, int] = Field(
        default_factory=dict,
        description="Strategy priority ranks (lower = higher priority)"
    )
    logging: StrategiesArbitrationLoggingConfig = Field(
        default_factory=StrategiesArbitrationLoggingConfig
    )


class StrategiesRegistryConfig(BaseModel):
    """
    Strategies Registry SSOT (config/aurora/strategies.yaml).
    
    Defines:
    1. Which strategies are active per symbol (assignments)
    2. How to arbitrate conflicts between strategies (arbitration)
    
    CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Strict validation (extra='forbid')
    """
    model_config = ConfigDict(extra='forbid')
    
    version: str = Field(
        default="1.0.0",
        description="Strategies registry config version"
    )
    assignments: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Per-symbol strategy assignments (symbol → list[strategy_id])"
    )
    arbitration: StrategiesArbitrationConfig = Field(
        default_factory=StrategiesArbitrationConfig,
        description="Arbitration policy for strategy conflicts"
    )
    
    @model_validator(mode='after')
    def validate_priorities_for_hybrid_symbols(self) -> 'StrategiesRegistryConfig':
        """Ensure all strategies in hybrid assignments have priorities defined."""
        if self.arbitration.mode == 'priority':
            priorities = self.arbitration.priority
            for symbol, strategies in self.assignments.items():
                if len(strategies) > 1:  # Hybrid symbol
                    for strategy_id in strategies:
                        if strategy_id not in priorities:
                            raise ValueError(
                                f"❌ ARBITRATION:missing_priority for '{strategy_id}' in hybrid "
                                f"symbol {symbol}. All strategies must have priorities defined."
                            )
        return self


class DecisionModeOverrideConfig(BaseModel):
    """Mode-specific decision overrides (testnet/production).
    
    CFG-DICT-ANY-BURN-13: Typed config for mode overrides.
    Allows ANY field from DecisionConfig to be overridden.
    extra='allow' justified: config_loader merges ANY override key.
    """
    model_config = ConfigDict(extra='allow')  # Justified: dynamic merge
    
    # Common overrides (known patterns from config_loader.py L120-140)
    signal_threshold: Optional[float] = Field(default=None)
    # Other DecisionConfig fields can be overridden dynamically


class DecisionConfig(BaseModel):
    """Decision making configuration (testnet/production overrides).
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    # Mode-specific configs (typed, not Dict[str, Any])
    testnet: Optional[DecisionModeOverrideConfig] = Field(default=None)
    production: Optional[DecisionModeOverrideConfig] = Field(default=None)

    # IMPORTANT: Default exists for test compatibility, but production MUST override
    signal_threshold: float = Field(default=0.2, description="Signal score threshold. PRODUCTION MUST OVERRIDE in trading.yaml!")
    cooldown_sec: Optional[int] = Field(default=None, description="Global cooldown (deprecated, use per-instrument)")
    side_bias_min_score: Optional[float] = Field(default=None, description="Min score for side bias")
    side_bias_penalty_factor: Optional[float] = Field(default=None, description="Side bias penalty factor")
    side_bias_target_ratio: Optional[float] = Field(default=None, description="Side bias target ratio")
    side_bias_window_sec: Optional[int] = Field(default=None, description="Side bias window (seconds)")
    
    # Retry configuration (formerly legacy defaults)
    retry_ttl_ms: int = Field(default=300_000, description="Retry TTL in ms")
    retry_max_count: int = Field(default=3, description="Max retry attempts")
    retry_backoff_factor: float = Field(default=2.0, description="Retry backoff multiplier")

    signal_weights: SignalWeights = Field(default_factory=SignalWeights)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)
    position_sizing: PositionSizingConfig = Field(
        default_factory=PositionSizingConfig)
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    qos: QosConfig = Field(default_factory=QosConfig)

    bar_gating: Optional[BarGatingConfig] = Field(default=None)
    behavior_fsm: Optional[BehaviorFsmConfig] = Field(default=None)
    roi_exit: Optional[ROIExitConfig] = Field(default=None)
    mean_reversion: Optional[MeanReversionConfig] = Field(default=None)

    sizing_modifiers: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific multipliers")
    regime_thresholds: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific signal thresholds")
    regime_threshold_multipliers: Dict[str, float] = Field(
        default_factory=dict, description="Regime threshold multipliers")
    symbols_to_track: Optional[List[str]] = Field(default=None, description="DEPRECATED: Use instruments SSOT")
    neutral_threshold: Optional[float] = Field(default=None, description="Neutral zone threshold")


class SLConfig(BaseModel):
    """Stop-loss configuration."""
    model_config = ConfigDict(extra='allow')
    fixed_bps: int = Field(default=50, description="Fixed basis points")


class TPConfig(BaseModel):
    """Take-profit configuration."""
    model_config = ConfigDict(extra='allow')
    fixed_bps: int = Field(default=100, description="Fixed basis points")


class BracketsConfig(BaseModel):
    """Brackets (TP/SL) configuration."""
    model_config = ConfigDict(extra='allow')

    sl: Optional[SLConfig] = Field(default=None)
    tp: Optional[TPConfig] = Field(default=None)
    oco_emulation: bool = Field(
        default=False, description="Emulate OCO orders")
    stop_loss_bps: int = Field(default=50)
    offset_bps: int = Field(default=5, description="Safety offset in bps")


class EmergencyConfig(BaseModel):
    """Emergency stop-loss configuration (margin-based).
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Added wait_mode_bars (fsm_manage.py:120).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False, description="Enable emergency SL")
    wait_mode_bars: int = Field(default=2, description="Wait mode bars before resuming")


class OrphanMonitorConfig(BaseModel):
    """Orphan bracket monitor configuration.
    
    CFG-DICT-ANY-BURN-13: Typed config (consumption in fsm.py L166, but keys unknown).
    extra='allow' temporary until consumption analysis complete.
    """
    model_config = ConfigDict(extra='allow')  # TODO: Convert to forbid when keys known
    
    enabled: bool = Field(default=False, description="Enable orphan monitoring")
    # Add fields when consumption patterns are documented


class ManageConfig(BaseModel):
    """Order management configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields typed).
    """
    model_config = ConfigDict(extra='forbid')

    brackets: Optional[BracketsConfig] = Field(default=None)
    emergency: Optional[EmergencyConfig] = Field(default=None)
    auto: bool = Field(default=False)
    orphan_monitor: Optional[OrphanMonitorConfig] = Field(default=None)
    failsafe: Optional[FailsafeConfig] = Field(default=None)


class ExposureConfig(BaseModel):
    """Exposure guard configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    max_equity_utilization_pct: float = Field(default=0.20)
    max_portfolio_fraction: float = Field(default=0.20)
    max_side_utilization_pct: Dict[str, float] = Field(
        default_factory=lambda: {"long": 0.12, "short": 0.12})
    max_directional_ratio: float = Field(default=2.0)
    per_symbol_cap_pct: float = Field(default=0.08)
    pending_ttl_sec: int = Field(default=90)
    pending_reservation_ttl_sec: int = Field(default=45, description="Reservation TTL")
    post_fill_hold_ttl_sec: int = Field(default=30)
    positions_stale_ttl_sec: int = Field(default=120)
    leverage_defaults: Dict[str, int] = Field(
        default_factory=lambda: {"__default__": 20})
    count_pending_orders: bool = Field(default=False, description="Count pending orders in exposure")
    exclude_reduce_only: bool = Field(default=False, description="Exclude reduce-only from exposure")


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ack_ttl_ms: int = Field(default=8000)
    fill_ttl_ms: int = Field(default=30000)
    check_interval_ms: int = Field(default=1000)
    rps_limit: int = Field(default=10)


class SMARegimeModelConfig(BaseModel):
    """Configuration for SMA-based trend regime detection.
    
    Detects TREND_UP, TREND_DOWN, MEAN_REVERSION based on SMA crossover.
    """
    model_config = ConfigDict(extra='allow')
    
    sma_short_period: int = Field(default=10, ge=2, description="Short SMA period for trend detection")
    sma_long_period: int = Field(default=50, ge=5, description="Long SMA period for trend detection")
    confidence_multiplier: float = Field(default=20.0, ge=1.0, description="Confidence scaling factor")
    confidence_min: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum confidence value")
    confidence_max: float = Field(default=0.95, ge=0.0, le=1.0, description="Maximum confidence value")


class VolatilityRegimeModelConfig(BaseModel):
    """Configuration for ATR-based volatility regime detection.
    
    Detects HIGH_VOLATILITY, LOW_VOLATILITY based on ATR vs historical average.
    """
    model_config = ConfigDict(extra='allow')
    
    enabled: bool = Field(default=True, description="Enable volatility regime detection")
    atr_period: int = Field(default=14, ge=1, description="ATR calculation period")
    atr_sma_length: int = Field(default=100, ge=10, description="ATR SMA length for baseline")
    threshold_multiplier: float = Field(default=2.0, ge=1.0, description="High vol threshold (ATR > threshold_mult * avg)")
    low_vol_multiplier: float = Field(default=0.5, ge=0.0, le=1.0, description="Low vol threshold (ATR < low_vol_mult * avg)")
    high_vol_confidence_multiplier: float = Field(default=2.0, ge=1.0, description="Confidence scaling for high vol")
    low_vol_confidence_multiplier: float = Field(default=3.0, ge=1.0, description="Confidence scaling for low vol")


class MeanReversionRegimeModelConfig(BaseModel):
    """Configuration for mean reversion regime detection.
    
    Detects MEAN_REVERSION when price is close to both SMAs.
    """
    model_config = ConfigDict(extra='allow')
    
    threshold: float = Field(default=0.005, ge=0.0, description="Max price deviation from SMAs for MR regime")
    confidence_multiplier: float = Field(default=100.0, ge=1.0, description="Confidence scaling factor")


class RegimeModelsConfig(BaseModel):
    """Container for all regime detection model configurations.
    
    Loaded from regime.yaml 'models' section.
    
    CFG-FEATURES-REGIME-SSOT-04: extra='forbid' for strict validation
    """
    model_config = ConfigDict(extra='forbid')
    
    sma_trend: SMARegimeModelConfig = Field(default_factory=SMARegimeModelConfig, description="SMA trend model")
    volatility: VolatilityRegimeModelConfig = Field(default_factory=VolatilityRegimeModelConfig, description="Volatility model")
    mean_reversion: MeanReversionRegimeModelConfig = Field(default_factory=MeanReversionRegimeModelConfig, description="Mean reversion model")


class RegimeModelConfig(BaseModel):
    """Base configuration for regime detection models."""
    model_config = ConfigDict(extra='allow')
    
    confidence_multiplier: float = Field(default=20.0)
    confidence_min: float = Field(default=0.5)
    confidence_max: float = Field(default=0.95)


class RegimeDetectorConfig(BaseModel):
    """Regime detector configuration."""
    model_config = ConfigDict(extra='allow')
    
    models: RegimeModelsConfig = Field(default_factory=RegimeModelsConfig, description="Regime detection models config")


class FallbackConfig(BaseModel):
    """Fallback configuration for execution.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (binance_adapter.py:1160, exposure_guard.py:205).
    """
    model_config = ConfigDict(extra='forbid')
    
    # Add fields when consumption patterns documented (currently used as empty dict)


class LimitOrdersConfig(BaseModel):
    """Limit orders configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (limit_order_monitor.py:93).
    """
    model_config = ConfigDict(extra='forbid')
    
    # Add fields when consumption patterns documented


class OrdersConfig(BaseModel):
    """Orders configuration (TTL, retries, etc.).
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (fsm.py:282 default_ttl_seconds).
    """
    model_config = ConfigDict(extra='allow')  # Temporary: market/cancel sub-configs unknown
    
    default_ttl_seconds: int = Field(default=120, description="Default order TTL")


class ExecutionConfig(BaseModel):
    """Execution configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    manage: Optional[ManageConfig] = Field(default=None)
    exposure: Optional[ExposureConfig] = Field(default=None)
    watchdog: Optional[WatchdogConfig] = Field(default=None)  # Typed (ack_ttl_ms, fill_ttl_ms, rps_limit)
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly typed configs
    fallback: Optional[FallbackConfig] = Field(default=None)
    limit_orders: Optional[LimitOrdersConfig] = Field(default=None)
    orders: Optional[OrdersConfig] = Field(default=None)
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Explicit runtime fields (consumption proven)
    fsm_periodic_cleanup_enabled: bool = Field(default=True, description="FSM periodic cleanup")
    anti_race_close_ms: int = Field(default=800, description="Anti-race window (ms)")
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Dead fields (no consumption, keep for backward compat)
    open_order_type: Optional[str] = Field(default=None, description="DEPRECATED: No consumption found")
    order_params: Optional[Dict[str, Any]] = Field(default=None, description="DEPRECATED: No consumption found")
    preflight_backoff_ms: Optional[List[int]] = Field(default=None, description="DEPRECATED: No consumption found")
    min_post_interval_per_symbol_ms: Optional[int] = Field(default=None, description="DEPRECATED")
    allow_trade_with_guardian_tidy_only: Optional[bool] = Field(default=None, description="DEPRECATED")
    order_guardian: Optional[Dict[str, Any]] = Field(default=None, description="DEPRECATED: Guardian not config")


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    enabled: bool = Field(default=True, description="Enable macro sync (anchor subscription and events)")
    anchors: List[str] = Field(
        default_factory=list, description="Anchor symbols for macro alignment")
    window: int = Field(default=60, description="Window in seconds")
    emit_abs: bool = Field(default=False, description="DEPRECATED: Not implemented. Planned removal: v2.0")
    
    # D4 Phase 1: Alignment mode for correlation calculation
    align_mode: str = Field(
        default="strict_len",
        description="Alignment mode: 'strict_len' (exact match) or 'tail_min_len' (use min overlap tail)"
    )
    min_buffer_size: int = Field(default=10, description="Min samples in buffer for correlation")
    time_diff_threshold_ms: int = Field(
        default=5000, description="Max time diff (ms) between ticks for return calculation"
    )
    anchor_update_from_ticks: bool = Field(
        default=True, description="Update anchor buffers from symbol ticks (false = EVT:ANCHOR_UPDATED only)"
    )


class KlinesConfig(BaseModel):
    """Klines API call configuration.
    
    CFG-DICT-ANY-BURN-13: Typed config (no consumption found, default values only).
    """
    model_config = ConfigDict(extra='forbid')
    
    interval: str = Field(default="1m", description="Kline interval")
    limit: int = Field(default=2, description="Max klines to fetch")


class ApiCallLimits(BaseModel):
    """API call limits configuration.
    
    CFG-DICT-ANY-BURN-13: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    get_recent_trades: int = Field(default=50)
    get_klines: KlinesConfig = Field(default_factory=KlinesConfig)


class MarketDataConfig(BaseModel):
    """Market data configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    poll_interval_sec: float = Field(default=2.0)
    use_multiprocessing: bool = Field(default=False, description="Enable multiprocessing")
    websocket_streams: List[str] = Field(default_factory=lambda: ["bookTicker", "trade"])
    api_call_limits: ApiCallLimits = Field(default_factory=ApiCallLimits)
    macro_sync: Optional[MacroSyncConfig] = Field(default=None)


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
    model_config = ConfigDict(extra='forbid')

    ema: Dict[str, Any] = Field(default_factory=dict)
    volume: Dict[str, Any] = Field(default_factory=dict)
    volatility: Dict[str, Any] = Field(default_factory=dict)
    liquidity: Dict[str, Any] = Field(default_factory=dict)
    macro_sync: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Domain-Specific Configuration Models
# ============================================================================

# Note: PositionSizingConfig, QosConfig, SignalsConfig are defined above
# and reused here to avoid duplication.


class RiskSkewConfig(BaseModel):
    """Risk skew guard configuration (Commit 5)."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    max_skew_sec: int = Field(default=5, description="Max age difference between features.ts and risk.ts")
    max_defer_count: int = Field(default=3, description="Max DEFERs per symbol before NO_TRADE_UNTIL_REFRESH")
    defer_cooldown_sec: int = Field(default=2, description="Cooldown between deferred retries")


class FeaturesTtlConfig(BaseModel):
    """Features TTL configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ttl_sec: int = Field(default=5)


# Note: BarGatingConfig and BehaviorFsmConfig already exist above


class ArmingConfig(BaseModel):
    """Arming/Warmup configuration for DecisionMaking."""
    model_config = ConfigDict(extra='forbid')
    
    require_regime_warmup: bool = Field(default=False)
    retry_backoff_ms: int = Field(default=1000)
    max_attempts: int = Field(default=120)


class DecisionMakingDomainConfig(BaseModel):
    """Complete decision making domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    qos: QosConfig = Field(default_factory=QosConfig)
    features: FeaturesTtlConfig = Field(default_factory=FeaturesTtlConfig)
    bar_gating: BarGatingConfig = Field(default_factory=BarGatingConfig)
    behavior_fsm: BehaviorFsmConfig = Field(default_factory=BehaviorFsmConfig)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)
    risk_skew: RiskSkewConfig = Field(default_factory=RiskSkewConfig)
    arming: ArmingConfig = Field(default_factory=ArmingConfig)


# ============================================================================
# FEATURE ENGINEERING DOMAIN - Full Pydantic Validation
# ============================================================================

class EmaConfigDetailed(BaseModel):
    """EMA calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    period_short: int = Field(
        default=3,
        ge=1, le=50,
        description="Short EMA period (EMA3 default). Must be < period_long."
    )
    period_long: int = Field(
        default=7,
        ge=2, le=200,
        description="Long EMA period (EMA7 default). Must be > period_short."
    )
    
    @field_validator('period_long')
    @classmethod
    def validate_period_long_greater(cls, v: int, info) -> int:
        """Ensure period_long > period_short."""
        period_short = info.data.get('period_short', 3)
        if v <= period_short:
            raise ValueError(f"period_long ({v}) must be > period_short ({period_short})")
        return v


class VolumeConfigDetailed(BaseModel):
    """Volume metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    sma_length: int = Field(
        default=5,
        ge=2, le=100,
        description="SMA length for volume spike calculation"
    )
    window_sec: int = Field(
        default=60,
        ge=1, le=3600,
        description="Volume aggregation window in seconds"
    )
    min_window_volume_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum volume threshold for active signal (Commit 6)"
    )


class VolatilityConfigDetailed(BaseModel):
    """Volatility metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    sma_length: int = Field(
        default=10,
        ge=2, le=100,
        description="SMA length for volatility state calculation"
    )
    window_sec: int = Field(
        default=60,
        ge=1, le=3600,
        description="Range window for volatility calculation in seconds"
    )


class LiquidityConfigDetailed(BaseModel):
    """Liquidity metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    depth_half: float = Field(
        default=1000.0,
        gt=0, le=1_000_000,
        description="Half-depth parameter for liquidity kappa and depth imbalance (USD)"
    )
    kappa_min: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum liquidity kappa value"
    )
    kappa_max: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Maximum liquidity kappa value"
    )
    
    @field_validator('kappa_max')
    @classmethod
    def validate_kappa_max(cls, v: float, info) -> float:
        """Ensure kappa_max >= kappa_min."""
        kappa_min = info.data.get('kappa_min', 0.3)
        if v < kappa_min:
            raise ValueError(f"kappa_max ({v}) must be >= kappa_min ({kappa_min})")
        return v


class EmaBiasConfig(BaseModel):
    """EMA bias calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    clamp_min: float = Field(
        default=-0.02,
        ge=-1.0, le=0.0,
        description="Minimum clamp for EMA bias (typically -2%)"
    )
    clamp_max: float = Field(
        default=0.02,
        ge=0.0, le=1.0,
        description="Maximum clamp for EMA bias (typically +2%)"
    )
    
    @field_validator('clamp_max')
    @classmethod
    def validate_clamp_symmetry(cls, v: float, info) -> float:
        """Ensure clamp_max is positive opposite of clamp_min for symmetry."""
        clamp_min = info.data.get('clamp_min', -0.02)
        if abs(v + clamp_min) > 0.001:  # Allow small tolerance
            # Warning only, not an error - asymmetric is allowed
            pass
        return v


class VolumeSpikeConfig(BaseModel):
    """Volume spike calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    cap_max: float = Field(
        default=3.0,
        gt=1.0, le=10.0,
        description="Maximum cap for volume spike ratio (e.g., 3.0 = 300% of average)"
    )


class MacroSyncMetricsConfig(BaseModel):
    """Macro sync metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(
        default=True,
        description="Enable macro sync correlation calculation"
    )
    time_diff_threshold_ms: int = Field(
        default=5000,
        ge=100, le=60000,
        description="Maximum time difference (ms) between ticks for return calculation"
    )
    min_buffer_size: int = Field(
        default=3,
        ge=2, le=100,
        description="Minimum buffer size before computing correlation"
    )
    window: int = Field(
        default=60,
        ge=10, le=1000,
        description="Rolling window size for correlation calculation"
    )
    anchors: List[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT"],
        min_length=1,
        description="Anchor symbols for correlation (market leaders)"
    )
    
    # P0-6 FIX: Add align_mode for length mismatch handling
    align_mode: str = Field(
        default="strict_len",
        pattern="^(strict_len|tail_min_len)$",
        description="Alignment mode: 'strict_len' (require exact match) or 'tail_min_len' (use shorter tail)"
    )
    
    # P0-6 FIX: Add anchor_update_from_ticks to control double-update
    anchor_update_from_ticks: bool = Field(
        default=True,
        description="Update anchor buffers from symbol ticks (set false to avoid double-count when anchor is also trade symbol)"
    )
    
    @field_validator('anchors')
    @classmethod
    def validate_anchors(cls, v: List[str]) -> List[str]:
        """Ensure anchors are valid symbol format."""
        for anchor in v:
            if not anchor.endswith("USDT"):
                raise ValueError(f"Anchor '{anchor}' must end with 'USDT'")
        return v


class VolatilityStateConfig(BaseModel):
    """Volatility state normalization configuration."""
    model_config = ConfigDict(extra='forbid')
    
    cap_max: float = Field(
        default=3.0,
        gt=1.0, le=10.0,
        description="Maximum cap for volatility ratio normalization"
    )


class DepthImbalanceConfig(BaseModel):
    """Depth imbalance calculation configuration."""
    model_config = ConfigDict(extra='forbid')
    
    use_laplace_smoothing: bool = Field(
        default=True,
        description="Use Laplace smoothing (depth_half) in calculation"
    )


class DeltaPriceConfig(BaseModel):
    """Delta price calculation configuration."""
    model_config = ConfigDict(extra='forbid')
    
    spike_filter_ms: int = Field(
        default=5000,
        ge=100, le=60000,
        description="Time gap (ms) above which delta_price is zeroed to filter spikes"
    )


class FeatureDefaultsConfig(BaseModel):
    """
    Default/neutral values for features.
    
    These values are returned when:
    - Insufficient data to compute feature
    - Division by zero would occur
    - Feature is in initialization phase
    
    All features are normalized to [0, 1] range, so 0.5 = neutral.
    """
    model_config = ConfigDict(extra='forbid')
    
    neutral_value: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Default neutral value for all normalized features (0.5 = center of [0,1])"
    )
    zero_value: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Value for truly zero/absent features (absorption placeholder)"
    )
    correlation_default: float = Field(
        default=0.0,
        ge=-1.0, le=1.0,
        description="Default correlation value when insufficient data"
    )
    ms_per_sec: int = Field(
        default=1000,
        ge=1000, le=1000,
        description="Milliseconds per second (constant for clarity)"
    )


class FeatureEngineeringDomainConfig(BaseModel):
    """
    Complete feature engineering domain configuration.
    
    All 9 features are configured here:
    - Base: OBI, TFI, delta_price, liquidity_kappa
    - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
    """
    model_config = ConfigDict(extra='forbid')
    
    # Master switch for Phase 1 metrics
    enable_new_metrics: bool = Field(
        default=True,
        description="Enable Phase 1 metrics (ema_bias, volume_spike, etc.)"
    )
    
    # P0-5 FIX: Volume input mode for avoiding double-counting
    volume_input_mode: str = Field(
        default="integrate",
        pattern="^(integrate|sample_window_total)$",
        description="Volume input mode: 'integrate' (sum ticks) or 'sample_window_total' (treat tick as pre-windowed sample)"
    )
    
    # Feature calculation configs
    ema: EmaConfigDetailed = Field(default_factory=EmaConfigDetailed)
    volume: VolumeConfigDetailed = Field(default_factory=VolumeConfigDetailed)
    volatility: VolatilityConfigDetailed = Field(default_factory=VolatilityConfigDetailed)
    liquidity: LiquidityConfigDetailed = Field(default_factory=LiquidityConfigDetailed)
    
    # Normalization configs
    ema_bias: EmaBiasConfig = Field(default_factory=EmaBiasConfig)
    volume_spike: VolumeSpikeConfig = Field(default_factory=VolumeSpikeConfig)
    volatility_state: VolatilityStateConfig = Field(default_factory=VolatilityStateConfig)
    depth_imbalance: DepthImbalanceConfig = Field(default_factory=DepthImbalanceConfig)
    delta_price: DeltaPriceConfig = Field(default_factory=DeltaPriceConfig)
    
    # Macro sync config
    macro_sync: MacroSyncMetricsConfig = Field(default_factory=MacroSyncMetricsConfig)
    
    # Default/neutral values for edge cases
    defaults: FeatureDefaultsConfig = Field(default_factory=FeatureDefaultsConfig)
    
    def get_ema_alpha(self, period: str) -> float:
        """Calculate EMA alpha for given period."""
        if period == "short":
            n = self.ema.period_short
        else:
            n = self.ema.period_long
        return 2.0 / (n + 1)


# ============================================================================
# Risk Management Domain
# ============================================================================

class RiskScoreWeightsConfig(BaseModel):
    """Risk score weights configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    delta_price_pct: float = Field(default=0.1)
    obi: float = Field(default=0.3)
    tfi: float = Field(default=0.3)
    absorption_inverse: float = Field(default=0.3)


class TradingAllowedThresholdsConfig(BaseModel):
    """Trading allowed thresholds configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    # IMPORTANT: Default exists for test compatibility, but production MUST override
    max_risk_score: float = Field(default=0.8, description="Max risk score. PRODUCTION MUST OVERRIDE in domains.yaml!")


class RiskValidationConfig(BaseModel):
    """Risk validation configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    total_weight_min: float = Field(default=0.5)
    total_weight_max: float = Field(default=2.0)


class RiskManagementDomainConfig(BaseModel):
    """Complete risk management domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    risk_score_weights: RiskScoreWeightsConfig = Field(default_factory=RiskScoreWeightsConfig)
    trading_allowed_thresholds: TradingAllowedThresholdsConfig = Field(default_factory=TradingAllowedThresholdsConfig)
    validation: RiskValidationConfig = Field(default_factory=RiskValidationConfig)
    
    # D5: Absorption deprecation flag
    # When False, absorption term is excluded from risk score calculation
    # NOTE: Other weights are NOT rescaled when absorption is disabled (per Plan v1)
    use_absorption_penalty: bool = Field(
        default=True,  # Backward compatible default
        description="Whether to include absorption penalty in risk score. "
                    "Set to False to disable deprecated absorption feature."
    )


# Position Tracking Domain
class PrecisionConfig(BaseModel):
    """Position precision configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    quantity_min_threshold: float = Field(default=1e-9)
    flat_position_threshold: float = Field(default=1e-12)
    decimal_places: int = Field(default=2)


class ThreadTimeoutsConfig(BaseModel):
    """Thread timeouts configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    join_timeout_sec: int = Field(default=10)


class PositionTrackingDomainConfig(BaseModel):
    """Complete position tracking domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    precision: PrecisionConfig = Field(default_factory=PrecisionConfig)
    thread_timeouts: ThreadTimeoutsConfig = Field(default_factory=ThreadTimeoutsConfig)
    positions_stale_ttl_sec: int = Field(default=15, description="Portfolio freshness TTL for AuroraBridge gate")
    enable_market_tick_subscription: bool = Field(
        default=False,
        description="Enable EVT:MARKET_TICK_RECEIVED subscription for mark-price PnL (optional)",
    )


# Account Observer Domain
class AccountObserverDomainConfig(BaseModel):
    """Complete account observer domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    poll_interval_sec: int = Field(default=5)
    trade_limit: int = Field(default=10)
    symbols: List[str] = Field(default_factory=list)  # Empty = use trading.symbols_to_track
    thread_timeouts: ThreadTimeoutsConfig = Field(default_factory=ThreadTimeoutsConfig)


# Execution Position Domain
class ExposureGuardConfig(BaseModel):
    """Exposure guard configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    pending_ttl_sec: int = Field(default=90)
    post_fill_ttl_sec: int = Field(default=5)
    stale_ttl_sec: int = Field(default=5)
    max_equity_utilization_pct: float = Field(default=0.20)
    max_portfolio_fraction: float = Field(default=0.20)
    max_long_utilization_pct: float = Field(default=0.20)
    max_short_utilization_pct: float = Field(default=0.20)
    max_directional_ratio: float = Field(default=2.0)
    max_concentration_pct: float = Field(default=0.10)
    pending_timeout_sec: int = Field(default=5)


class FsmOpenConfig(BaseModel):
    """FSM open configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    idempotency_window_sec: int = Field(default=60)


class OrderIndexConfig(BaseModel):
    """Order index configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ttl_sec: int = Field(default=3600)


class MetricsCollectorConfig(BaseModel):
    """Metrics collector configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    window_size_minutes: int = Field(default=60)
    recent_rejections_minutes: int = Field(default=5)


class IdempotentCancelConfig(BaseModel):
    """Idempotent cancel configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    max_retries: int = Field(default=2)


class ExecutionUtilsConfig(BaseModel):
    """Execution utilities configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    client_order_id_max_length: int = Field(default=32)
    basis_points_base: float = Field(default=10000.0)


class ExecutionPositionDomainConfig(BaseModel):
    """Complete execution position domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)
    exposure_guard: ExposureGuardConfig = Field(default_factory=ExposureGuardConfig)
    fsm_open: FsmOpenConfig = Field(default_factory=FsmOpenConfig)
    order_index: OrderIndexConfig = Field(default_factory=OrderIndexConfig)
    metrics_collector: MetricsCollectorConfig = Field(default_factory=MetricsCollectorConfig)
    idempotent_cancel: IdempotentCancelConfig = Field(default_factory=IdempotentCancelConfig)
    utils: ExecutionUtilsConfig = Field(default_factory=ExecutionUtilsConfig)


# Top-Level Domains Configuration
class DomainsConfig(BaseModel):
    """Top-level domains configuration container (CANONICAL)."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation, fail-fast on unknown fields
    
    decision_making: DecisionMakingDomainConfig = Field(default_factory=DecisionMakingDomainConfig)
    feature_engineering: FeatureEngineeringDomainConfig = Field(default_factory=FeatureEngineeringDomainConfig)
    risk_management: RiskManagementDomainConfig = Field(default_factory=RiskManagementDomainConfig)
    position_tracking: PositionTrackingDomainConfig = Field(default_factory=PositionTrackingDomainConfig)
    account_observer: AccountObserverDomainConfig = Field(default_factory=AccountObserverDomainConfig)
    execution_position: ExecutionPositionDomainConfig = Field(default_factory=ExecutionPositionDomainConfig)


# ============================================================================
# Aurora Per-Instrument Configuration (Phase 0)
# ============================================================================

class AuroraSideBiasConfig(BaseModel):
    """Aurora side bias configuration per instrument."""
    model_config = ConfigDict(extra='allow')

    penalty_factor: Optional[float] = Field(
        default=None,
        description="Penalty multiplier for counter-bias trades"
    )
    window_sec: Optional[int] = Field(
        default=None,
        description="Rolling window in seconds for side bias calculation"
    )
    target_ratio: Optional[float] = Field(
        default=None,
        description="Target long/short ratio (e.g., 0.5 = balanced)"
    )


class AuroraExitConfig(BaseModel):
    """Aurora exit/stop-loss configuration per instrument."""
    model_config = ConfigDict(extra='allow')

    sl_pct: Optional[float] = Field(
        default=None,
        description="Stop-loss as percentage from entry (e.g., 0.005 = 0.5%)"
    )
    max_hold_sec: Optional[int] = Field(
        default=None,
        description="Maximum position hold time in seconds"
    )


class AuroraTakeProfitConfig(BaseModel):
    """Aurora take-profit configuration per instrument."""
    model_config = ConfigDict(extra='allow')

    tp_low_ratio: Optional[float] = Field(
        default=None,
        description="TP1 as ratio to ATR or fixed percent"
    )
    tp_high_ratio: Optional[float] = Field(
        default=None,
        description="TP2 as ratio to ATR or fixed percent"
    )
    partial_exit_pct: Optional[float] = Field(
        default=None,
        description="Percentage to exit at TP1 (e.g., 0.7 = 70%)"
    )


class AuroraTrailingStopConfig(BaseModel):
    """Aurora trailing stop configuration per instrument."""
    model_config = ConfigDict(extra='allow')

    enabled: Optional[bool] = Field(
        default=None,
        description="Enable trailing stop"
    )
    activation_pct: Optional[float] = Field(
        default=None,
        description="Activate trailing after this profit % (e.g., 0.003 = 0.3%)"
    )
    trail_pct: Optional[float] = Field(
        default=None,
        description="Trail distance as % from high-water mark"
    )
    min_update_interval_sec: Optional[int] = Field(
        default=5,
        description="Minimum seconds between SL updates (rate limit)"
    )


class AuroraExecutionConfig(BaseModel):
    """Aurora execution-specific configuration per instrument."""
    model_config = ConfigDict(extra='allow')

    order_type: Optional[str] = Field(
        default=None,
        description="Order type: LIMIT, MARKET"
    )
    post_only: Optional[bool] = Field(
        default=None,
        description="Use post-only orders for maker fees"
    )
    max_slippage_bps: Optional[int] = Field(
        default=None,
        description="Max allowed slippage in basis points"
    )


# ============================================================================
# PHASE 3+ Per-Instrument Override Config Classes
# ============================================================================

class EmaClampConfig(BaseModel):
    """Per-asset EMA clamp range override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False, description="Enable per-asset clamp override")
    clamp_min: Optional[float] = Field(default=None, description="Override global ema_bias.clamp_min")
    clamp_max: Optional[float] = Field(default=None, description="Override global ema_bias.clamp_max")


class SignalThresholdConfig(BaseModel):
    """Per-asset signal threshold override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False, description="Enable per-asset threshold override")
    value: Optional[float] = Field(default=None, description="Override global signal_threshold")


class MaxRiskScoreConfig(BaseModel):
    """Per-asset max risk score override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(default=False, description="Enable per-asset max_risk_score override")
    value: Optional[float] = Field(default=None, description="Max risk score threshold for entry filtering")


class AuroraInstrumentConfig(BaseModel):
    """
    Complete per-instrument configuration for Aurora strategy.

    Fallback chain:
    1. aurora_instruments.<SYMBOL>.<param> (this config)
    2. trading.decision.<param> (global fallback)
    """
    model_config = ConfigDict(extra='forbid')  # Strict validation (CFG-AURORA-INSTRUMENTS-SSOT-01)

    # Strategy enable/disable flag
    enabled: bool = Field(
        default=True,
        description="Enable Aurora strategy for this instrument (default: True for backward compat)"
    )

    # Signal weights (Phase 3+ Optuna results)
    weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Per-feature signal weights from Optuna"
    )

    # Side bias
    side_bias: Optional[AuroraSideBiasConfig] = Field(
        default=None,
        description="Side bias configuration"
    )

    position_mode: Literal["STRICT", "DYNAMIC"] = Field(
        default="DYNAMIC",
        description="STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap"
    )

    # Regime-based thresholds
    regime_thresholds: Optional[Dict[str, float]] = Field(
        default=None,
        description="Threshold multipliers per regime (TREND, VOLATILE, FLAT)"
    )

    # Regime-based position sizing
    regime_sizing: Optional[Dict[str, float]] = Field(
        default=None,
        description="Position size multipliers per regime"
    )

    # Exit configuration
    exit: Optional[AuroraExitConfig] = Field(
        default=None,
        description="Stop-loss and max hold time"
    )

    # Take profit configuration
    take_profit: Optional[AuroraTakeProfitConfig] = Field(
        default=None,
        description="TP1/TP2 partial exit settings"
    )

    # Trailing stop configuration
    trailing_stop: Optional[AuroraTrailingStopConfig] = Field(
        default=None,
        description="Trailing stop settings"
    )

    # Execution configuration
    execution: Optional[AuroraExecutionConfig] = Field(
        default=None,
        description="Order execution settings"
    )

    # Phase 3+ per-asset overrides
    ema_clamp: Optional[EmaClampConfig] = Field(
        default=None,
        description="Per-asset EMA clamp range (Phase 3+)"
    )
    signal_threshold: Optional[SignalThresholdConfig] = Field(
        default=None,
        description="Per-asset signal threshold (Phase 3+)"
    )
    max_risk_score: Optional[MaxRiskScoreConfig] = Field(
        default=None,
        description="Per-asset max risk score (Phase 3+)"
    )

    cooldown_sec: Optional[int] = Field(
        default=None,
        description="Per-instrument cooldown in seconds (overrides global qos.symbol_cooldown_sec)"
    )

    # Phase 3+ Recovery: Regime gating
    allowed_regimes: Optional[List[str]] = Field(
        default=None,
        description="If set, only trade when current regime is in this list (Phase 3+ regime gating)"
    )

    # Phase 1.5 Recovery: Per-instrument timeframe
    timeframe_sec: Optional[int] = Field(
        default=None,
        description="Bar timeframe in seconds for this instrument. SOL=180 (3m), BTC/ETH=300 (5m)"
    )

    # Position Control (Anti-pyramiding)
    position_mode: Optional[str] = Field(
        default="ONE_SIDE",
        description="Position constraint mode: 'STRICT' (1 pos total), 'ONE_SIDE' (1 pos per side/allow reduce), 'HEDGE' (allow all)"
    )


class OpsConfig(BaseModel):
    """Operations configuration (killswitch, quiet hours, monitoring)."""
    model_config = ConfigDict(extra='allow')

    # Emergency controls (A-01 fix)
    panic_killswitch: bool = Field(
        default=False, 
        description="Emergency kill switch - blocks all new CMD:OPEN when True"
    )
    panic_ttl_sec: Optional[int] = Field(
        default=None,
        description="Optional TTL in seconds for panic_killswitch; if set, killswitch auto-expires after this many seconds"
    )
    quiet_hours_utc: List[str] = Field(
        default_factory=list,
        description="Time windows in UTC when trading is blocked (e.g., ['22:00-06:00'])"
    )
    allowlist_symbols: List[str] = Field(
        default_factory=list,
        description="If non-empty, only these symbols can trade. Empty = no restrictions"
    )
    
    # Monitoring
    metrics_url: str = Field(default="http://127.0.0.1:8000/metrics")
    reports_dir: str = Field(default="reports")


# ==============================================================================
# DOMAIN CONFIGURATION (Hybrid Mode: live data → testnet execution)
# ==============================================================================
class DomainModeConfig(BaseModel):
    """Configuration for a single domain's trading mode."""
    model_config = ConfigDict(extra='allow')
    
    trading_mode: Literal["live", "testnet"] = Field(
        ...,  # REQUIRED - no default!
        description="Trading mode for this domain: 'live' or 'testnet'"
    )


class DomainConfigurationConfig(BaseModel):
    """
    Domain-level mode configuration for hybrid trading.
    
    Hybrid mode allows:
    - Data domains (market_data, feature_engineering, decision_making) → LIVE
    - Execution domains (execution_position, risk_management) → TESTNET
    
    CRITICAL: For production, explicitly set each domain's mode!
    Default is all-testnet for safety in tests.
    """
    model_config = ConfigDict(extra='allow')
    
    market_data: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Market data source mode (should be 'live' for real prices)"
    )
    feature_engineering: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Feature engineering mode (should match market_data)"
    )
    decision_making: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Decision making mode (should match market_data)"
    )
    risk_management: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Risk management mode (testnet for safety)"
    )
    execution_position: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Execution mode (MUST be 'testnet' for testing!)"
    )
    audit_trail: DomainModeConfig = Field(
        default_factory=lambda: DomainModeConfig(trading_mode="testnet"),
        description="Audit trail mode (usually 'live' for logging)"
    )


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='forbid')

    mode: str = Field(default="testnet",
                      description="testnet | production | live")
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    execution: Optional[ExecutionConfig] = Field(default=None)
    instruments: Dict[str, InstrumentSpec] = Field(default_factory=dict)
    aurora_instruments: Dict[str, AuroraInstrumentConfig] = Field(
        default_factory=dict,
        description="Per-instrument Aurora strategy configuration (Optuna results)"
    )
    symbols_to_track: List[str] = Field(default_factory=list, description="List of symbols to track for multi-TF aggregation")
    market_data: Optional[MarketDataConfig] = Field(default=None)
    feature_engineering: Optional[FeatureEngineeringConfig] = Field(
        default=None)
    domains: DomainsConfig = Field(default_factory=DomainsConfig)  # NEW: Domain-specific configurations
    
    # Legacy risk config (still used by DailyRiskState etc)
    risk: Dict[str, Any] = Field(default_factory=dict, description="Legacy risk configuration (daily gate, etc)")
    
    # TCA and Risk Budgets (Dicts for now but typed access via field)
    tca_prefs: Dict[str, Any] = Field(default_factory=dict, description="TCA Preferences")
    risk_budgets: Dict[str, Any] = Field(default_factory=dict, description="Risk Budgeting Configuration")

    # Risk management data sources (used for hybrid/live/testnet wiring)
    risk_management: "TradingRiskManagementConfig" = Field(...)
    
    # Ops configuration (killswitch, quiet hours)
    ops: Optional[OpsConfig] = Field(
        default=None,
        description="Operations config (panic killswitch, quiet hours, allowlist)"
    )
    
    # CRITICAL: Domain-level mode configuration (Hybrid Mode)
    # Default is all-testnet for safety. Production MUST explicitly set live modes!
    domain_configuration: DomainConfigurationConfig = Field(
        default_factory=DomainConfigurationConfig,
        description="Domain-level trading mode configuration for hybrid mode (live data + testnet execution)"
    )


class BinanceApiEnv(BaseModel):
    """Binance API configuration for a single environment."""
    model_config = ConfigDict(extra='forbid')

    api_key: Optional[str] = Field(default=None)
    api_secret: Optional[str] = Field(default=None)
    rest_url: Optional[str] = Field(default=None)
    ws_url: Optional[str] = Field(default=None)


class BinanceApiConfig(BaseModel):
    """Binance API configuration (live + testnet)."""
    model_config = ConfigDict(extra='forbid')
    live: BinanceApiEnv = Field(default_factory=BinanceApiEnv)
    testnet: BinanceApiEnv = Field(default_factory=BinanceApiEnv)


class RetrySchedulerConfig(BaseModel):
    """AuroraBridge retry scheduler configuration."""
    model_config = ConfigDict(extra='forbid')

    max_attempts: int = Field(..., description="Max retry attempts for deferred intents")
    min_retry_delay_ms: int = Field(..., description="Minimum retry delay (ms)")


class BridgeConfig(BaseModel):
    """AuroraBridge configuration (strict object config)."""
    model_config = ConfigDict(extra='forbid')

    retry_scheduler: RetrySchedulerConfig = Field(...)


class RiskManagementDataSourcesConfig(BaseModel):
    """Runtime data source selection for risk management."""
    model_config = ConfigDict(extra='forbid')

    market_data: Literal["live", "testnet"] = Field(...)
    portfolio_state: Literal["live", "testnet", "follow_execution"] = Field(...)


class TradingRiskManagementConfig(BaseModel):
    """Trading-level risk management config (legacy location in trading.yaml)."""
    model_config = ConfigDict(extra='forbid')

    data_sources: RiskManagementDataSourcesConfig = Field(...)


class AccountObserverConfig(BaseModel):
    """Account observer configuration."""
    model_config = ConfigDict(extra='allow')
    poll_interval: int = Field(
        default=30, description="Polling interval in seconds")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    model_config = ConfigDict(extra='allow')

    level: str = Field(default="INFO")
    file: str = Field(default="logs/aurora_core.log")
    format: str = Field(default="json")
    rotation: Dict[str, int] = Field(default_factory=lambda: {
                                     "max_bytes": 10 * 1024 * 1024, "backup_count": 5})
    
    
class SystemMarketDataConfig(BaseModel):
    """System-level Market Data configuration."""
    model_config = ConfigDict(extra='allow')
    
    queue_maxsize: int = Field(..., description="Max size of IPC queue (worker → proxy)")
    local_queue_maxsize: int = Field(..., description="Max size of local queue (proxy internal)")
    emit_workers: int = Field(..., description="Thread pool size for non-blocking FSM.emit()")
    tick_ttl_ms: int = Field(..., description="Max age of tick data in ms — older ticks are DROPPED")


class SystemConfig(BaseModel):
    """System configuration (framework-level)."""
    model_config = ConfigDict(extra='allow')

    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    market_data: Optional[SystemMarketDataConfig] = Field(default=None, description="Market data system settings")


class SystemRuntimeMeta(BaseModel):
    """Runtime metadata captured during config load."""

    model_config = ConfigDict(extra='forbid')

    config_name: Optional[str] = Field(default=None, description="Identifier of the loaded config profile")
    config_dir: Optional[str] = Field(default=None, description="Filesystem path of the config directory in use")


class SystemMetaConfig(BaseModel):
    """Service/runtime metadata preserved under a dedicated namespace."""

    model_config = ConfigDict(extra='forbid')

    system_config_version: Optional[str] = Field(default=None)
    regime_config_version: Optional[str] = Field(default=None)
    sequential_tests: Dict[str, Any] = Field(default_factory=dict)
    risk_core: Dict[str, Any] = Field(default_factory=dict)
    kelly: Dict[str, Any] = Field(default_factory=dict)
    calibrator: Dict[str, Any] = Field(default_factory=dict)
    hawkes: Dict[str, Any] = Field(default_factory=dict)
    hotreload_whitelist: List[Any] = Field(default_factory=list)
    hardening: Dict[str, Any] = Field(default_factory=dict)
    position_tracking: Dict[str, Any] = Field(default_factory=dict)
    runtime: SystemRuntimeMeta = Field(default_factory=SystemRuntimeMeta)


class AuroraConfig(BaseModel):
    """
    Root configuration model for AuroraTrader.

    This replaces the old dict-based AuroraConfig class with full type validation.
    Pydantic V2 validates on instantiation, raising ValidationError immediately if config is invalid.
    """
    model_config = ConfigDict(extra='forbid')

    # Core app configs
    trading_mode: str = Field(
        default="testnet", description="Trading mode: testnet | production | live")
    trading: TradingConfig = Field(default_factory=TradingConfig)

    # Exchange/account/market configs
    binance_api: BinanceApiConfig = Field(default_factory=BinanceApiConfig)
    account_observer: AccountObserverConfig = Field(
        default_factory=AccountObserverConfig)

    # System configs
    system: SystemConfig = Field(default_factory=SystemConfig)
    system_meta: SystemMetaConfig = Field(default_factory=SystemMetaConfig)
    ops: OpsConfig = Field(default_factory=OpsConfig)

    # Bridge config (AuroraBridge retry scheduler)
    bridge: BridgeConfig = Field(...)
    
    # Domain configs (New)
    domains: Optional[DomainsConfig] = Field(default=None, description="Domain-specific configurations")

    # Canonical instruments SSOT (config/aurora/instruments.yaml)
    instruments: Dict[str, InstrumentPrecisionSpec] = Field(
        default_factory=dict,
        description="Canonical instrument precision map (symbol -> tick_size/step_size)"
    )
    
    # Canonical aurora_instruments SSOT (config/aurora/aurora_instruments.yaml)
    aurora_instruments: Dict[str, AuroraInstrumentConfig] = Field(
        default_factory=dict,
        description="Per-symbol Aurora strategy overrides (weights, side_bias, exit, etc.)"
    )
    
    # Strategies registry SSOT (config/aurora/strategies.yaml)
    # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION
    strategies_registry: Optional[StrategiesRegistryConfig] = Field(
        default=None,
        description="Strategy assignments + arbitration config (from strategies.yaml)"
    )
    
    # Strategy configs (Track B, optional root-level overrides)
    mean_reversion_1m: Optional[MeanReversion1mStrategyConfig] = Field(
        default=None, 
        description="Mean Reversion 1m strategy config (loaded from strategy profile SSOT)"
    )

    # App-specific overrides
    decision: Optional[DecisionConfig] = Field(
        default=None, description="Override trading.decision if set")
    execution: Optional[ExecutionConfig] = Field(
        default=None, description="Override trading.execution if set")
    brackets: Optional[BracketsConfig] = Field(default=None)
    trailing: Dict[str, Any] = Field(default_factory=dict)
    
    # Regime Detector Config (loaded from regime.yaml, Pydantic-validated)
    models: Optional[RegimeModelsConfig] = Field(default=None, description="Regime detection models from regime.yaml")

    # Legacy root-level configs (to be migrated to system_meta)
    logging: Optional[Dict[str, Any]] = Field(default=None, description="Logging configuration")
    hmm: Optional[Dict[str, Any]] = Field(default=None, description="HMM regime detector config")
    features: Optional[Dict[str, Any]] = Field(default=None, description="Feature engineering config")
    hotreload_whitelist: Optional[List[str]] = Field(default=None, description="Hot-reload allowlist")
    aurora: Optional[Dict[str, Any]] = Field(default=None, description="Aurora strategy global config")
    runtime: Optional[Dict[str, Any]] = Field(default=None, description="Runtime configuration")

    @field_validator('trading_mode')
    @classmethod
    def validate_trading_mode(cls, v: str) -> str:
        """Ensure trading_mode is one of the valid values."""
        allowed_modes = ("testnet", "production", "live",
                         "hybrid_live_data_testnet_exec")
        if v not in allowed_modes:
            raise ValueError(
                f"trading_mode must be one of: {', '.join(allowed_modes)}. Got: {v}")
        return v

    @field_validator('trading')
    @classmethod
    def validate_trading_mode_consistency(cls, v: TradingConfig, info) -> TradingConfig:
        """Ensure trading.mode and trading_mode are consistent."""
        # Note: In Pydantic V2, we can check info.data for other fields
        if 'trading_mode' in info.data:
            if v.mode != info.data['trading_mode']:
                # Optionally sync them or raise an error
                v.mode = info.data['trading_mode']
        return v


# Convenience function for creating config from dict
def create_aurora_config(config_dict: Dict[str, Any]) -> AuroraConfig:
    """Create a validated AuroraConfig from a dictionary.

    Raises pydantic.ValidationError on invalid config.
    """
    return AuroraConfig(**config_dict)


# Backward-compat imports for tests/legacy modules
AuroraTradingConfig = TradingConfig
AuroraExposureConfig = ExposureConfig
