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
    step_size: str = Field(description='Quantity precision')
    tick_size: str = Field(description='Price precision')
    min_qty: str = Field()
    min_notional: str = Field(description='Minimum notional value in USDT')
    quote: str = Field()


class InstrumentPrecisionSpec(BaseModel):
    """Canonical Aurora instrument precision (SSOT from instruments.yaml).

    TASK50: Added min_qty and min_notional for fail-closed qty normalization.
    Keep this model permissive (extra=allow) to avoid breaking exchange-specific tails.
    tick_size/step_size are enforced for active symbols via loader fail-fast checks.
    """

    model_config = ConfigDict(extra='forbid')

    symbol: Optional[str] = Field(default=None)
    tick_size: Optional[str] = Field(default=None, description='Price precision')
    step_size: Optional[str] = Field(default=None, description='Quantity precision (LOT_SIZE stepSize)')
    min_qty: Optional[str] = Field(default=None, description='Minimum quantity (LOT_SIZE minQty)')
    min_notional: Optional[str] = Field(default=None, description='Minimum notional value (MIN_NOTIONAL)')


class InstrumentExecutionConfig(BaseModel):
    """Per-instrument execution settings for leverage and margin control (TASK47c).
    
    All fields are MANDATORY for LIVE execution mode.
    Missing any field in LIVE mode → startup crash (fail-closed).
    
    GAP-LEV-01 + GAP-MAR-01: Leverage and margin mode must be part of execution contract.
    """
    model_config = ConfigDict(extra='forbid')
    
    margin_mode: Literal["isolated", "cross"] = Field(
        description='Binance margin mode. ISOLATED = per-position margin, CROSS = shared wallet margin.'
    )
    target_leverage: int = Field(
        ge=1, le=125,
        description='Target leverage for this instrument (1-125). Must match or be set on exchange.'
    )
    leverage_policy: Literal["verify_only", "set_and_verify"] = Field(
        description='verify_only = reject if mismatch. set_and_verify = set margin+leverage then verify.'
    )
    max_notional_utilization: float = Field(
        ge=0.0, le=1.0,
        description='Max notional as fraction of available capacity (0.0-1.0). Used for L1 capacity gate.'
    )



class SignalWeights(BaseModel):
    """Weights for signal calculation (OBI, TFI, etc).
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    obi: float = Field()
    tfi: float = Field()
    delta_price: float = Field()
    ema_bias: float = Field()
    volume_spike: float = Field()
    volatility_state: float = Field()
    depth_imbalance: float = Field()
    macro_sync: float = Field()


class BarGatingConfig(BaseModel):
    """Bar gating configuration for decision making."""
    model_config = ConfigDict(extra='forbid')
    enable: bool = Field()
    bar_ms: int = Field(description='Bar duration in milliseconds')


class BehaviorFsmConfig(BaseModel):
    """Behavioral FSM configuration."""
    model_config = ConfigDict(extra='forbid')
    enable: bool = Field()
    high_vol_multiplier: float = Field()
    low_vol_multiplier: float = Field()


class SignalsConfig(BaseModel):
    """Signals configuration."""
    model_config = ConfigDict(extra='forbid')
    normalize: bool = Field()
    enable_new_metrics: bool = Field()


class RegimeSizingSymbolConfig(BaseModel):
    """Per-symbol regime sizing configuration (ETAP3).
    
    Controls volatility-based position sizing multipliers for a specific symbol.
    When enabled, position size = base * multiplier(volatility_state).
    
    base_notional = per_symbol_margin_fraction * equity * effective_leverage
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable regime-based sizing for this symbol')
    low_vol_multiplier: float = Field(description='Multiplier for LOW_VOLATILITY regime (calm)')
    high_vol_multiplier: float = Field(description='Multiplier for HIGH_VOLATILITY regime (storm)')


class RiskContractV1Config(BaseModel):
    """Risk-Sizing V1 configuration contract.
    
    ETAP3: All sizing via % of equity, no fixed USD in runtime.
    
    Formulas:
    - base_notional = per_symbol_margin_fraction[symbol] * equity * effective_leverage
    - regime_target = base_notional * multiplier(volatility_state)
    - cap_notional = base_notional (same %)
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable Risk-Sizing V1')
    effective_leverage: float = Field(description='Assumed leverage for notional calculation')
    
    # Per-symbol margin fractions (% of equity → notional)
    per_symbol_margin_fraction: Dict[str, float] = Field(description='Target margin fraction per symbol (e.g., BTCUSDT: 0.04)')
    
    # Per-symbol regime sizing config (ETAP3)
    regime_sizing: Dict[str, RegimeSizingSymbolConfig] = Field(description='Per-symbol regime-based sizing config')


class SizingV2Config(BaseModel):
    """Sizing Contract V2: explicit sizing modes (no hidden fallbacks)."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["percent_equity", "fixed_notional_usd", "fixed_qty"] = Field(
        description="Sizing mode: percent_equity | fixed_notional_usd | fixed_qty"
    )
    percent_equity: Optional[float] = Field(
        default=None,
        description="Fraction of equity to allocate (0..1], required when mode=percent_equity",
    )
    fixed_notional_usd: Optional[float] = Field(
        default=None,
        description="Fixed USD notional to allocate, required when mode=fixed_notional_usd",
    )
    fixed_qty: Dict[str, float] = Field(
        default_factory=dict,
        description="Per-symbol fixed quantity (e.g., SOLUSDT: 1.0), required when mode=fixed_qty",
    )

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> "SizingV2Config":
        if self.mode == "percent_equity":
            if self.percent_equity is None:
                raise ValueError("position_sizing.sizing.percent_equity is required when mode=percent_equity")
            if not (0.0 < float(self.percent_equity) <= 1.0):
                raise ValueError("position_sizing.sizing.percent_equity must be in (0, 1]")
            return self

        if self.mode == "fixed_notional_usd":
            if self.fixed_notional_usd is None:
                raise ValueError("position_sizing.sizing.fixed_notional_usd is required when mode=fixed_notional_usd")
            if float(self.fixed_notional_usd) <= 0.0:
                raise ValueError("position_sizing.sizing.fixed_notional_usd must be > 0")
            return self

        if self.mode == "fixed_qty":
            if not self.fixed_qty:
                raise ValueError("position_sizing.sizing.fixed_qty must be non-empty when mode=fixed_qty")
            for symbol, qty in self.fixed_qty.items():
                try:
                    q = float(qty)
                except Exception as e:
                    raise ValueError(f"position_sizing.sizing.fixed_qty[{symbol!r}] must be numeric") from e
                if q <= 0.0:
                    raise ValueError(f"position_sizing.sizing.fixed_qty[{symbol!r}] must be > 0")
            return self

        return self


class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    min_position_size_usd: float = Field()
    liquidity_based_cap_usd: float = Field()
    risk_fraction_q: Optional[float] = Field()
    liquidity_kappa: float = Field()
    kappa_mode: str = Field()
    liquidity_kappa_mode: Optional[str] = Field(description='Alias for kappa_mode (legacy)')
    
    # Risk-Sizing V1 contract (ETAP1: config-only, not used in runtime)
    risk_contract_v1: Optional[RiskContractV1Config] = Field(description='Risk-Sizing V1 contract (ETAP1: disabled by default)')

    # TASK39: Sizing Contract V2 (explicit sizing modes; no legacy 10% fallback).
    sizing: Optional[SizingV2Config] = Field(
        default=None,
        description="Sizing Contract V2: percent_equity | fixed_notional_usd | fixed_qty.",
    )



class KellyConfig(BaseModel):
    """Kelly criterion configuration."""
    model_config = ConfigDict(extra='forbid')
    base_probability: float = Field()
    kelly_cap: float = Field()
    kelly_alpha: float = Field()
    payoff_ratio_r: float = Field()


class QosConfig(BaseModel):
    """Quality of Service configuration for rate limiting."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    exposure_block_cooldown_sec: int = Field()
    # Global fallback for per-symbol cooldown (aurora_instruments.<SYMBOL>.cooldown_sec takes priority)
    symbol_cooldown_sec: int = Field(description='Global fallback cooldown. Per-symbol config takes priority.')
    max_intents_per_minute_per_symbol: int = Field()
    mode: str = Field(description='defer | block')
    enforce: bool = Field()


class ROIExitConfig(BaseModel):
    """ROI Exit Strategy configuration."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field()
    target_roi_pct: float = Field()


class FailsafeConfig(BaseModel):
    """Failsafe configuration."""
    model_config = ConfigDict(extra='forbid')
    max_hold_sec: int = Field()


class MeanReversionConfig(BaseModel):
    """Configuration for Mean Reversion regime model (regime.yaml SSOT).
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema, no runtime surprises).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field()
    bb_window: int = Field()
    bb_std_dev: float = Field()
    min_vol_atr: float = Field()
    allowed_regimes: List[str] = Field()


# ============================================================================
# Mean Reversion 1m Strategy Configuration (Track B)
# ============================================================================

class MRStrategyParamsConfig(BaseModel):
    """Strategy parameters for Mean Reversion 1m.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    bb_window: int = Field(description='Bollinger Bands window')
    bb_num_std: float = Field(description='BB standard deviations')
    atr_window: int = Field(description='ATR window for stops')
    rsi_window: int = Field(description='RSI window')
    
    entry_threshold: float = Field(description='%B threshold for entry')
    rsi_oversold: float = Field(description='RSI oversold level')
    rsi_overbought: float = Field(description='RSI overbought level')
    
    min_bars: int = Field(description='Min bars before trading')
    min_bb_width: float = Field(description='Min BB width')
    max_bb_width: float = Field(description='Max BB width')
    
    sl_atr_mult: float = Field(description='SL as ATR multiplier')
    tp_to_mid: bool = Field(description='Target mid BB')
    cooldown_sec: int = Field(description='Cooldown between signals')


class MRRegimeThresholdsConfig(BaseModel):
    """Regime thresholds for FLAT regime classification.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    high_vol_pct: float = Field(description='ATR% for FLAT_HIGH')
    low_vol_pct: float = Field(description='ATR% for FLAT_LOW')


class MRStrategyOverrideConfig(BaseModel):
    """Per-asset strategy parameter overrides for MR.
    
    These override the global MRStrategyParamsConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')
    
    bb_window: Optional[int] = Field(default=None, description='BB window size')
    bb_num_std: Optional[float] = Field(default=None, description='BB std multiplier')
    min_bb_width: Optional[float] = Field(default=None, description='Min BB width filter')
    entry_threshold: Optional[float] = Field(default=None, description='Entry distance threshold')
    tp_to_mid: Optional[bool] = Field(default=None, description='TP to mid vs outer band')
    sl_atr_mult: Optional[float] = Field(default=None, description='SL ATR multiplier override')
    cooldown_sec: Optional[int] = Field(default=None, description='Cooldown between trades')
    allowed_regimes: Optional[List[str]] = Field(default=None, description='Override allowed regimes for this symbol')


class MRAssetRiskConfig(BaseModel):
    """Per-asset risk configuration for MR.
    
    Overrides global MRRiskConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')
    
    position_size_usd: Optional[float] = Field(default=None, description='Position size in USD')
    max_risk_score: Optional[float] = Field(default=None, description='Max risk score threshold')


class MRAssetConfig(BaseModel):
    """Per-asset configuration for Mean Reversion 1m.
    
    UPDATED: Now supports typed strategy/risk overrides.
    """
    model_config = ConfigDict(extra='forbid')  # CFG-LEGACY-SUNSET-11: YAML migration complete
    
    enabled: bool = Field()
    
    # NEW: Typed strategy overrides
    strategy: Optional[MRStrategyOverrideConfig] = Field(default=None, description='Strategy parameter overrides for this symbol')
    
    # NEW: Typed risk config
    risk: Optional[MRAssetRiskConfig] = Field(default=None, description='Risk configuration for this symbol')
    
    # Legacy flat fields (kept for backward compatibility, will be deprecated)
    bb_window: Optional[int] = Field()
    min_vol_atr: Optional[float] = Field()
    sl_pct: Optional[float] = Field(description='SL as percent (e.g., 0.019 = 1.9%)')
    
    allowed_regimes: List[str] = Field(description='Regimes where trading is allowed')

    position_mode: Literal["STRICT", "DYNAMIC"] = Field(description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap')


class MRRegimeSizingConfig(BaseModel):
    """Sizing/stop/target multipliers for a specific FLAT regime.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    sizing_mult: float = Field()
    stop_mult: float = Field()
    target_mult: float = Field()


class MRRiskConfig(BaseModel):
    """Risk management for Mean Reversion 1m.
    
    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    position_size_usd: float = Field()
    max_concurrent_positions: int = Field()
    daily_loss_limit_usd: float = Field()
    expected_pnl_multiplier: float = Field()
    fees_pct: float = Field()
    slippage_pct: float = Field()


class MeanReversion1mStrategyConfig(BaseModel):
    """
    Full configuration for Mean Reversion 1m Strategy.
    
    Config is provided via root.mean_reversion (loaded from strategy profile SSOT).
    """
    model_config = ConfigDict(extra='forbid')
    
    # Master enable flag (feature flag)
    enabled: bool = Field(description='Enable MR 1m strategy')
    
    # Timeframe
    timeframe_sec: int = Field(description='Bar timeframe in seconds')
    
    # Strategy parameters
    strategy: MRStrategyParamsConfig = Field()
    
    # Regime thresholds
    regime_thresholds: MRRegimeThresholdsConfig = Field()
    
    # Per-asset configurations (symbol → config)
    assets: Dict[str, MRAssetConfig] = Field()
    
    # Regime sizing (regime_name → multipliers)
    regime_sizing: Dict[str, MRRegimeSizingConfig] = Field()
    
    # Global allowed regimes whitelist (can be overridden per-asset in assets.X.allowed_regimes)
    allowed_regimes: List[str] = Field(description='Whitelist of Flat regimes to trade in (global default)')
    
    # Risk management
    risk: MRRiskConfig = Field()
    
    # Strict Sequential Trading Contract: MR emission mode
    # true (default) = MR emits EVT:TRADE_INTENT_PROPOSED directly (legacy behavior)
    # false = MR emits EVT:MR_SIGNAL_PRODUCED, DecisionMaking applies gates
    emit_trade_intent_directly: bool = Field(description='If true, MR emits trade intent directly (legacy). If false, emits MR_SIGNAL for DM gateway.')

# ==============================================================================
# STRATEGIES REGISTRY (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
# ==============================================================================

class StrategiesArbitrationLoggingConfig(BaseModel):
    """Logging configuration for strategy arbitration."""
    model_config = ConfigDict(extra='forbid')
    
    rejected_why_prefix: str = Field(description='Prefix for why-codes when strategy intent is rejected')
    log_level: str = Field(description='Log level for arbitration events (INFO/WARNING/ERROR)')


class StrategiesArbitrationConfig(BaseModel):
    """Configuration for strategy conflict arbitration."""
    model_config = ConfigDict(extra='forbid')
    
    mode: Literal['priority'] = Field(description="Arbitration mode: 'priority' (only supported mode, lower number = higher priority)")
    window_ms: int = Field(description="Decision window size in ms for multi-strategy arbitration (SSOT; no silent defaults).")
    priority: Dict[str, int] = Field(description='Strategy priority ranks (lower = higher priority)')
    logging: StrategiesArbitrationLoggingConfig = Field()


class StrategiesRegistryConfig(BaseModel):
    """
    Strategies Registry SSOT (config/aurora/strategies.yaml).
    
    Defines:
    1. Which strategies are active per symbol (assignments)
    2. How to arbitrate conflicts between strategies (arbitration)
    
    CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Strict validation (extra='forbid')
    """
    model_config = ConfigDict(extra='forbid')
    
    version: str = Field(description='Strategies registry config version')
    assignments: Dict[str, List[str]] = Field(description='Per-symbol strategy assignments (symbol → list[strategy_id])')
    arbitration: StrategiesArbitrationConfig = Field(description='Arbitration policy for strategy conflicts')
    
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
    model_config = ConfigDict(extra='forbid')  # Justified: dynamic merge
    
    # Common overrides (known patterns from config_loader.py L120-140)
    signal_threshold: Optional[float] = Field()
    # Other DecisionConfig fields can be overridden dynamically


class DecisionConfig(BaseModel):
    """Decision making configuration (testnet/production overrides).
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    # Mode-specific configs (typed, not Dict[str, Any])
    testnet: Optional[DecisionModeOverrideConfig] = Field()
    production: Optional[DecisionModeOverrideConfig] = Field()

    # IMPORTANT: Default exists for test compatibility, but production MUST override
    signal_threshold: float = Field(description='Signal score threshold. PRODUCTION MUST OVERRIDE in trading.yaml!')
    cooldown_sec: Optional[int] = Field(description='Global cooldown (deprecated, use per-instrument)')
    side_bias_min_score: Optional[float] = Field(description='Min score for side bias')
    side_bias_penalty_factor: Optional[float] = Field(description='Side bias penalty factor')
    side_bias_target_ratio: Optional[float] = Field(description='Side bias target ratio')
    side_bias_window_sec: Optional[int] = Field(description='Side bias window (seconds)')
    
    # Retry configuration (formerly legacy defaults)
    retry_ttl_ms: int = Field(description='Retry TTL in ms')
    retry_max_count: int = Field(description='Max retry attempts')
    retry_backoff_factor: float = Field(description='Retry backoff multiplier')

    signal_weights: SignalWeights = Field()
    signals: SignalsConfig = Field()
    position_sizing: PositionSizingConfig = Field()
    kelly: KellyConfig = Field()
    qos: QosConfig = Field()

    bar_gating: Optional[BarGatingConfig] = Field()
    behavior_fsm: Optional[BehaviorFsmConfig] = Field()
    roi_exit: Optional[ROIExitConfig] = Field()
    mean_reversion: Optional[MeanReversionConfig] = Field()

    sizing_modifiers: Dict[str, float] = Field(description='Regime-specific multipliers')
    regime_thresholds: Dict[str, float] = Field(description='Regime-specific signal thresholds')
    regime_threshold_multipliers: Dict[str, float] = Field(description='Regime threshold multipliers')
    symbols_to_track: Optional[List[str]] = Field(default=None, description='DEPRECATED: Use instruments SSOT')
    neutral_threshold: Optional[float] = Field(description='Neutral zone threshold')


class SLConfig(BaseModel):
    """Stop-loss configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(description='Fixed basis points')


class TPConfig(BaseModel):
    """Take-profit configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(description='Fixed basis points')


class BracketsConfig(BaseModel):
    """Brackets (TP/SL) configuration."""
    model_config = ConfigDict(extra='forbid')

    sl: Optional[SLConfig] = Field()
    tp: Optional[TPConfig] = Field()
    oco_emulation: bool = Field(description='Emulate OCO orders')
    stop_loss_bps: int = Field()
    offset_bps: int = Field(description='Safety offset in bps')


class EmergencyConfig(BaseModel):
    """Emergency stop-loss configuration (margin-based).
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Added wait_mode_bars (fsm_manage.py:120).
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable emergency SL')
    wait_mode_bars: int = Field(description='Wait mode bars before resuming')


class OrphanMonitorConfig(BaseModel):
    """Orphan bracket monitor configuration.
    
    CFG-DICT-ANY-BURN-13: Typed config (consumption in fsm.py L166, but keys unknown).
    extra='allow' temporary until consumption analysis complete.
    """
    model_config = ConfigDict(extra='forbid')  # TODO: Convert to forbid when keys known
    
    enabled: bool = Field(description='Enable orphan monitoring')
    # Add fields when consumption patterns are documented


class ManageConfig(BaseModel):
    """Order management configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields typed).
    """
    model_config = ConfigDict(extra='forbid')

    brackets: Optional[BracketsConfig] = Field()
    emergency: Optional[EmergencyConfig] = Field()
    auto: bool = Field()
    orphan_monitor: Optional[OrphanMonitorConfig] = Field()
    failsafe: Optional[FailsafeConfig] = Field()


class ExposureConfig(BaseModel):
    """Exposure guard configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    max_equity_utilization_pct: float = Field()
    max_portfolio_fraction: float = Field()
    max_side_utilization_pct: Dict[str, float] = Field()
    max_directional_ratio: float = Field()
    per_symbol_cap_pct: float = Field()
    pending_ttl_sec: int = Field()
    pending_reservation_ttl_sec: int = Field(description='Reservation TTL')
    post_fill_hold_ttl_sec: int = Field()
    positions_stale_ttl_sec: int = Field()
    leverage_defaults: Dict[str, int] = Field()
    count_pending_orders: bool = Field(description='Count pending orders in exposure')
    exclude_reduce_only: bool = Field(description='Exclude reduce-only from exposure')


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ack_ttl_ms: int = Field()
    fill_ttl_ms: int = Field()
    check_interval_ms: int = Field()
    rps_limit: int = Field()


class SMARegimeModelConfig(BaseModel):
    """Configuration for SMA-based trend regime detection.
    
    Detects TREND_UP, TREND_DOWN, MEAN_REVERSION based on SMA crossover.
    """
    model_config = ConfigDict(extra='forbid')
    
    sma_short_period: int = Field(ge=2, description='Short SMA period for trend detection')
    sma_long_period: int = Field(ge=5, description='Long SMA period for trend detection')
    confidence_multiplier: float = Field(ge=1.0, description='Confidence scaling factor')
    confidence_min: float = Field(ge=0.0, le=1.0, description='Minimum confidence value')
    confidence_max: float = Field(ge=0.0, le=1.0, description='Maximum confidence value')


class VolatilityRegimeModelConfig(BaseModel):
    """Configuration for ATR-based volatility regime detection.
    
    Detects HIGH_VOLATILITY, LOW_VOLATILITY based on ATR vs historical average.
    """
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable volatility regime detection')
    atr_period: int = Field(ge=1, description='ATR calculation period')
    atr_sma_length: int = Field(ge=10, description='ATR SMA length for baseline')
    allow_close_to_close_atr: bool = Field(description='Allow close-to-close TR/ATR when OHLC is unavailable (explicit opt-in)')
    threshold_multiplier: float = Field(ge=1.0, description='High vol threshold (ATR > threshold_mult * avg)')
    low_vol_multiplier: float = Field(ge=0.0, le=1.0, description='Low vol threshold (ATR < low_vol_mult * avg)')
    high_vol_confidence_multiplier: float = Field(ge=1.0, description='Confidence scaling for high vol')
    low_vol_confidence_multiplier: float = Field(ge=1.0, description='Confidence scaling for low vol')


class MeanReversionRegimeModelConfig(BaseModel):
    """Configuration for mean reversion regime detection.
    
    Detects MEAN_REVERSION when price is close to both SMAs.
    """
    model_config = ConfigDict(extra='forbid')
    
    threshold: float = Field(ge=0.0, description='Max price deviation from SMAs for MR regime')
    confidence_multiplier: float = Field(ge=1.0, description='Confidence scaling factor')


class RegimeModelsConfig(BaseModel):
    """Container for all regime detection model configurations.
    
    Loaded from regime.yaml 'models' section.
    
    CFG-FEATURES-REGIME-SSOT-04: extra='forbid' for strict validation
    """
    model_config = ConfigDict(extra='forbid')
    
    sma_trend: SMARegimeModelConfig = Field(description='SMA trend model')
    volatility: VolatilityRegimeModelConfig = Field(description='Volatility model')
    mean_reversion: MeanReversionRegimeModelConfig = Field(description='Mean reversion model')


class RegimeModelConfig(BaseModel):
    """Base configuration for regime detection models."""
    model_config = ConfigDict(extra='forbid')
    
    confidence_multiplier: float = Field()
    confidence_min: float = Field()
    confidence_max: float = Field()


class RegimeDetectorConfig(BaseModel):
    """Regime detector configuration."""
    model_config = ConfigDict(extra='forbid')
    
    models: RegimeModelsConfig = Field(description='Regime detection models config')


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
    model_config = ConfigDict(extra='forbid')  # Temporary: market/cancel sub-configs unknown
    
    default_ttl_seconds: int = Field(description='Default order TTL')


class ExecutionConfig(BaseModel):
    """Execution configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    manage: Optional[ManageConfig] = Field()
    exposure: Optional[ExposureConfig] = Field()
    watchdog: Optional[WatchdogConfig] = Field()  # Typed (ack_ttl_ms, fill_ttl_ms, rps_limit)
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly typed configs
    fallback: Optional[FallbackConfig] = Field()
    limit_orders: Optional[LimitOrdersConfig] = Field()
    orders: Optional[OrdersConfig] = Field()
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Explicit runtime fields (consumption proven)
    fsm_periodic_cleanup_enabled: bool = Field(description='FSM periodic cleanup')
    anti_race_close_ms: int = Field(description='Anti-race window (ms)')
    
    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Dead fields (no consumption, keep for backward compat)
    open_order_type: Optional[str] = Field(description='DEPRECATED: No consumption found')
    order_params: Optional[Dict[str, Any]] = Field(description='DEPRECATED: No consumption found')
    preflight_backoff_ms: Optional[List[int]] = Field(description='DEPRECATED: No consumption found')
    min_post_interval_per_symbol_ms: Optional[int] = Field(description='DEPRECATED')
    allow_trade_with_guardian_tidy_only: Optional[bool] = Field(description='DEPRECATED')
    order_guardian: Optional[Dict[str, Any]] = Field(default=None, description='DEPRECATED: Guardian not config')


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(description='Enable macro sync (anchor subscription and events)')
    anchors: List[str] = Field(description='Anchor symbols for macro alignment')
    window: int = Field(description='Window in seconds')
    emit_abs: bool = Field(description='DEPRECATED: Not implemented. Planned removal: v2.0')
    
    # D4 Phase 1: Alignment mode for correlation calculation
    align_mode: str = Field(description="Alignment mode: 'strict_len' (exact match) or 'tail_min_len' (use min overlap tail)")
    min_buffer_size: int = Field(description='Min samples in buffer for correlation')
    time_diff_threshold_ms: int = Field(description='Max time diff (ms) between ticks for return calculation')
    anchor_update_from_ticks: bool = Field(description='Update anchor buffers from symbol ticks (false = EVT:ANCHOR_UPDATED only)')


class KlinesConfig(BaseModel):
    """Klines API call configuration.
    
    CFG-DICT-ANY-BURN-13: Typed config (no consumption found, default values only).
    """
    model_config = ConfigDict(extra='forbid')
    
    interval: str = Field(description='Kline interval')
    limit: int = Field(description='Max klines to fetch')


class ApiCallLimits(BaseModel):
    """API call limits configuration.
    
    CFG-DICT-ANY-BURN-13: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')
    
    get_recent_trades: int = Field()
    get_klines: KlinesConfig = Field()


class MarketDataConfig(BaseModel):
    """Market data configuration.
    
    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    poll_interval_sec: float = Field()
    use_multiprocessing: bool = Field(description='Enable multiprocessing')
    websocket_streams: List[str] = Field()
    api_call_limits: ApiCallLimits = Field()
    macro_sync: Optional[MacroSyncConfig] = Field()


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
    model_config = ConfigDict(extra='forbid')

    ema: Dict[str, Any] = Field()
    volume: Dict[str, Any] = Field()
    volatility: Dict[str, Any] = Field()
    liquidity: Dict[str, Any] = Field()
    macro_sync: Dict[str, Any] = Field()


# ============================================================================
# Domain-Specific Configuration Models
# ============================================================================

# Note: PositionSizingConfig, QosConfig, SignalsConfig are defined above
# and reused here to avoid duplication.


class RiskSkewConfig(BaseModel):
    """Risk skew guard configuration (Commit 5)."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    max_skew_sec: int = Field(description='Max age difference between features.ts and risk.ts')
    max_defer_count: int = Field(description='Max DEFERs per symbol before NO_TRADE_UNTIL_REFRESH')
    defer_cooldown_sec: int = Field(description='Cooldown between deferred retries')


class FeaturesTtlConfig(BaseModel):
    """Features TTL configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ttl_sec: int = Field()


# Note: BarGatingConfig and BehaviorFsmConfig already exist above


class ArmingConfig(BaseModel):
    """Arming/Warmup configuration for DecisionMaking."""
    model_config = ConfigDict(extra='forbid')
    
    require_regime_warmup: bool = Field()
    retry_backoff_ms: int = Field()
    max_attempts: int = Field()


class DecisionMakingDomainConfig(BaseModel):
    """Complete decision making domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    position_sizing: PositionSizingConfig = Field()
    qos: QosConfig = Field()
    features: FeaturesTtlConfig = Field()
    bar_gating: BarGatingConfig = Field()
    behavior_fsm: BehaviorFsmConfig = Field()
    signals: SignalsConfig = Field()
    risk_skew: RiskSkewConfig = Field()
    arming: ArmingConfig = Field()


# ============================================================================
# FEATURE ENGINEERING DOMAIN - Full Pydantic Validation
# ============================================================================

class EmaConfigDetailed(BaseModel):
    """EMA calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    period_short: int = Field(ge=1, le=50, description='Short EMA period (EMA3 default). Must be < period_long.')
    period_long: int = Field(ge=2, le=200, description='Long EMA period (EMA7 default). Must be > period_short.')
    
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
    
    sma_length: int = Field(ge=2, le=100, description='SMA length for volume spike calculation')
    window_sec: int = Field(ge=1, le=3600, description='Volume aggregation window in seconds')
    min_window_volume_usd: float = Field(ge=0.0, description='Minimum volume threshold for active signal (Commit 6)')


class VolatilityConfigDetailed(BaseModel):
    """Volatility metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    sma_length: int = Field(ge=2, le=100, description='SMA length for volatility state calculation')
    window_sec: int = Field(ge=1, le=3600, description='Range window for volatility calculation in seconds')


class LiquidityConfigDetailed(BaseModel):
    """Liquidity metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    depth_half: float = Field(gt=0, le=1000000, description='Half-depth parameter for liquidity kappa and depth imbalance (USD)')
    kappa_min: float = Field(ge=0.0, le=1.0, description='Minimum liquidity kappa value')
    kappa_max: float = Field(ge=0.0, le=1.0, description='Maximum liquidity kappa value')
    
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
    
    clamp_min: float = Field(ge=-1.0, le=0.0, description='Minimum clamp for EMA bias (typically -2%)')
    clamp_max: float = Field(ge=0.0, le=1.0, description='Maximum clamp for EMA bias (typically +2%)')
    
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
    
    cap_max: float = Field(gt=1.0, le=10.0, description='Maximum cap for volume spike ratio (e.g., 3.0 = 300% of average)')
    sma_len: int = Field(ge=2, le=1000, description='SMA length for time-normalized volume rate samples')
    eps: float = Field(gt=0.0, le=1.0, description='Epsilon for spike denominator (avoid divide-by-zero)')


class LargeTradeImbalanceConfig(BaseModel):
    """Large trade imbalance configuration (TASK31)."""
    model_config = ConfigDict(extra='forbid')

    window_ms: int = Field(
        ge=1000,
        le=600000,
        description="Window size in milliseconds for trade aggregation (must match market_data window for correctness)",
    )
    min_trades: int = Field(ge=1, le=100000, description="Minimum number of trades in window required to mark ready=true")
    eps: float = Field(gt=0.0, le=1.0, description="Epsilon for denominator guard (avoid divide-by-zero)")
    use_notional: bool = Field(description="If true, use notional (qty*price) instead of qty for imbalance")


class MacroSyncMetricsConfig(BaseModel):
    """Macro sync metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable macro sync correlation calculation')
    time_diff_threshold_ms: int = Field(ge=100, le=60000, description='Maximum time difference (ms) between ticks for return calculation')
    ttl_ms: int = Field(ge=100, le=600000, description='Anchor staleness TTL (ms). If anchor older than ttl_ms → macro_sync NOT_READY')
    min_buffer_size: int = Field(ge=2, le=100, description='Minimum buffer size before computing correlation')
    window: int = Field(ge=10, le=1000, description='Rolling window size for correlation calculation')
    bin_ms: int = Field(default=1000, ge=250, le=5000, description='Time-grid bin size in ms for Macro Sync V2 alignment')
    max_gap_bins: int = Field(default=2, ge=0, le=120, description='Max consecutive missing bins allowed before NOT_READY (Macro Sync V2)')
    eps: float = Field(default=1e-12, gt=0.0, le=1e-3, description='Epsilon for sigma/variance guards (Macro Sync V2)')
    anchors: List[str] = Field(min_length=1, description='Anchor symbols for correlation (market leaders)')
    
    # P0-6 FIX: Add align_mode for length mismatch handling
    align_mode: str = Field(pattern='^(strict_len|tail_min_len)$', description="Alignment mode: 'strict_len' (require exact match) or 'tail_min_len' (use shorter tail)")
    
    # P0-6 FIX: Add anchor_update_from_ticks to control double-update
    anchor_update_from_ticks: bool = Field(description='Update anchor buffers from symbol ticks (set false to avoid double-count when anchor is also trade symbol)')
    
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
    
    cap_max: float = Field(gt=1.0, le=10.0, description='Maximum cap for volatility ratio normalization')


class DepthImbalanceConfig(BaseModel):
    """Depth imbalance calculation configuration."""
    model_config = ConfigDict(extra='forbid')
    
    use_laplace_smoothing: bool = Field(description='Use Laplace smoothing (depth_half) in calculation')


class DeltaPriceConfig(BaseModel):
    """Delta price calculation configuration."""
    model_config = ConfigDict(extra='forbid')
    
    spike_filter_ms: int = Field(ge=100, le=60000, description='Time gap (ms) above which delta_price is zeroed to filter spikes')


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
    
    neutral_value: float = Field(ge=0.0, le=1.0, description='Default neutral value for all normalized features (0.5 = center of [0,1])')
    zero_value: float = Field(ge=0.0, le=1.0, description='Value for truly zero/absent features (absorption placeholder)')
    correlation_default: float = Field(ge=-1.0, le=1.0, description='Default correlation value when insufficient data')
    ms_per_sec: int = Field(ge=1000, le=1000, description='Milliseconds per second (constant for clarity)')


class FeatureEngineeringDomainConfig(BaseModel):
    """
    Complete feature engineering domain configuration.
    
    All 9 features are configured here:
    - Base: OBI, TFI, delta_price, liquidity_kappa
    - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
    """
    model_config = ConfigDict(extra='forbid')
    
    # Master switch for Phase 1 metrics
    enable_new_metrics: bool = Field(description='Enable Phase 1 metrics (ema_bias, volume_spike, etc.)')
    
    # P0-5 FIX: Volume input mode for avoiding double-counting
    volume_input_mode: str = Field(pattern='^(integrate|sample_window_total)$', description="Volume input mode: 'integrate' (sum ticks) or 'sample_window_total' (treat tick as pre-windowed sample)")
    
    # Feature calculation configs
    ema: EmaConfigDetailed = Field()
    volume: VolumeConfigDetailed = Field()
    volatility: VolatilityConfigDetailed = Field()
    liquidity: LiquidityConfigDetailed = Field()
    
    # Normalization configs
    ema_bias: EmaBiasConfig = Field()
    volume_spike: VolumeSpikeConfig = Field()
    large_trade_imbalance: LargeTradeImbalanceConfig = Field()
    volatility_state: VolatilityStateConfig = Field()
    depth_imbalance: DepthImbalanceConfig = Field()
    delta_price: DeltaPriceConfig = Field()
    
    # Macro sync config
    macro_sync: MacroSyncMetricsConfig = Field()
    
    # Default/neutral values for edge cases
    defaults: FeatureDefaultsConfig = Field()
    
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
    
    delta_price_pct: float = Field()
    obi: float = Field()
    tfi: float = Field()
    absorption_inverse: float = Field()


class TradingAllowedThresholdsConfig(BaseModel):
    """Trading allowed thresholds configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    # IMPORTANT: Default exists for test compatibility, but production MUST override
    max_risk_score: float = Field(description='Max risk score. PRODUCTION MUST OVERRIDE in domains.yaml!')


class RiskValidationConfig(BaseModel):
    """Risk validation configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    total_weight_min: float = Field()
    total_weight_max: float = Field()


class RiskManagementDomainConfig(BaseModel):
    """Complete risk management domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    risk_score_weights: RiskScoreWeightsConfig = Field()
    trading_allowed_thresholds: TradingAllowedThresholdsConfig = Field()
    validation: RiskValidationConfig = Field()
    
    # D5: Absorption deprecation flag
    # When False, absorption term is excluded from risk score calculation
    # NOTE: Other weights are NOT rescaled when absorption is disabled (per Plan v1)
    use_absorption_penalty: bool = Field(description='Whether to include absorption penalty in risk score. Set to False to disable deprecated absorption feature.')


# Position Tracking Domain
class PrecisionConfig(BaseModel):
    """Position precision configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    quantity_min_threshold: float = Field()
    flat_position_threshold: float = Field()
    decimal_places: int = Field()


class ThreadTimeoutsConfig(BaseModel):
    """Thread timeouts configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    join_timeout_sec: int = Field()


class PositionTrackingDomainConfig(BaseModel):
    """Complete position tracking domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    precision: PrecisionConfig = Field()
    thread_timeouts: ThreadTimeoutsConfig = Field()
    positions_stale_ttl_sec: int = Field(description='Portfolio freshness TTL for AuroraBridge gate')
    enable_market_tick_subscription: bool = Field(description='Enable EVT:MARKET_TICK_RECEIVED subscription for mark-price PnL (optional)')


# Account Observer Domain
class AccountObserverDomainConfig(BaseModel):
    """Complete account observer domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    poll_interval_sec: int = Field()
    trade_limit: int = Field()
    symbols: List[str] = Field()  # Empty = use trading.symbols_to_track
    thread_timeouts: ThreadTimeoutsConfig = Field()


# Execution Position Domain
class ExposureGuardConfig(BaseModel):
    """Exposure guard configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    pending_ttl_sec: int = Field()
    post_fill_ttl_sec: int = Field()
    stale_ttl_sec: int = Field()
    max_equity_utilization_pct: float = Field()
    max_portfolio_fraction: float = Field()
    max_long_utilization_pct: float = Field()
    max_short_utilization_pct: float = Field()
    max_directional_ratio: float = Field()
    max_concentration_pct: float = Field()
    pending_timeout_sec: int = Field()


class FsmOpenConfig(BaseModel):
    """FSM open configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    idempotency_window_sec: int = Field()


class OrderIndexConfig(BaseModel):
    """Order index configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    ttl_sec: int = Field()


class MetricsCollectorConfig(BaseModel):
    """Metrics collector configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    window_size_minutes: int = Field()
    recent_rejections_minutes: int = Field()


class IdempotentCancelConfig(BaseModel):
    """Idempotent cancel configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    max_retries: int = Field()


class ExecutionUtilsConfig(BaseModel):
    """Execution utilities configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    client_order_id_max_length: int = Field()
    basis_points_base: float = Field()


class ExecutionPositionDomainConfig(BaseModel):
    """Complete execution position domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation
    
    watchdog: WatchdogConfig = Field()
    exposure_guard: ExposureGuardConfig = Field()
    fsm_open: FsmOpenConfig = Field()
    order_index: OrderIndexConfig = Field()
    metrics_collector: MetricsCollectorConfig = Field()
    idempotent_cancel: IdempotentCancelConfig = Field()
    utils: ExecutionUtilsConfig = Field()

class DomainsDebugConfig(BaseModel):
    """Debug / shadow-only switches for domain gates (fail-closed in live/prod)."""
    model_config = ConfigDict(extra='forbid')

    disable_positions_stale_gate: bool = Field(
        description="DEV/SHADOW ONLY: disables position stale TTL gate (AuroraBridge portfolio freshness)."
    )
    disable_daily_loss_limit: bool = Field(
        description="DEV/SHADOW ONLY: disables daily loss/drawdown gate (RiskManagement DailyRiskState)."
    )


# Top-Level Domains Configuration
class DomainsConfig(BaseModel):
    """Top-level domains configuration container (CANONICAL)."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation, fail-fast on unknown fields
    
    debug: DomainsDebugConfig = Field()
    decision_making: DecisionMakingDomainConfig = Field()
    feature_engineering: FeatureEngineeringDomainConfig = Field()
    risk_management: RiskManagementDomainConfig = Field()
    position_tracking: PositionTrackingDomainConfig = Field()
    account_observer: AccountObserverDomainConfig = Field()
    execution_position: ExecutionPositionDomainConfig = Field()


# ============================================================================
# Aurora Per-Instrument Configuration (Phase 0)
# ============================================================================

class AuroraSideBiasConfig(BaseModel):
    """Aurora side bias configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    penalty_factor: Optional[float] = Field(description='Penalty multiplier for counter-bias trades')
    window_sec: Optional[int] = Field(description='Rolling window in seconds for side bias calculation')
    target_ratio: Optional[float] = Field(description='Target long/short ratio (e.g., 0.5 = balanced)')


class AuroraExitConfig(BaseModel):
    """Aurora exit/stop-loss configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    sl_pct: Optional[float] = Field(description='Stop-loss as percentage from entry (e.g., 0.005 = 0.5%)')
    max_hold_sec: Optional[int] = Field(description='Maximum position hold time in seconds')


class AuroraTakeProfitConfig(BaseModel):
    """Aurora take-profit configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    tp_low_ratio: Optional[float] = Field(description='TP1 as ratio to ATR or fixed percent')
    tp_high_ratio: Optional[float] = Field(description='TP2 as ratio to ATR or fixed percent')
    partial_exit_pct: Optional[float] = Field(description='Percentage to exit at TP1 (e.g., 0.7 = 70%)')


class AuroraTrailingStopConfig(BaseModel):
    """Aurora trailing stop configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    enabled: Optional[bool] = Field(description='Enable trailing stop')
    activation_pct: Optional[float] = Field(description='Activate trailing after this profit % (e.g., 0.003 = 0.3%)')
    trail_pct: Optional[float] = Field(description='Trail distance as % from high-water mark')
    min_update_interval_sec: Optional[int] = Field(description='Minimum seconds between SL updates (rate limit)')


class AuroraExecutionConfig(BaseModel):
    """Aurora execution-specific configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    order_type: Optional[str] = Field(description='Order type: LIMIT, MARKET')
    post_only: Optional[bool] = Field(description='Use post-only orders for maker fees')
    max_slippage_bps: Optional[int] = Field(description='Max allowed slippage in basis points')


# ============================================================================
# PHASE 3+ Per-Instrument Override Config Classes
# ============================================================================

class EmaClampConfig(BaseModel):
    """Per-asset EMA clamp range override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable per-asset clamp override')
    clamp_min: Optional[float] = Field(description='Override global ema_bias.clamp_min')
    clamp_max: Optional[float] = Field(description='Override global ema_bias.clamp_max')


class SignalThresholdConfig(BaseModel):
    """Per-asset signal threshold override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable per-asset threshold override')
    value: Optional[float] = Field(description='Override global signal_threshold')


class MaxRiskScoreConfig(BaseModel):
    """Per-asset max risk score override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = Field(description='Enable per-asset max_risk_score override')
    value: Optional[float] = Field(description='Max risk score threshold for entry filtering')


class AuroraInstrumentConfig(BaseModel):
    """
    Complete per-instrument configuration for Aurora strategy.

    Fallback chain:
    1. aurora_instruments.<SYMBOL>.<param> (this config)
    2. trading.decision.<param> (global fallback)
    """
    model_config = ConfigDict(extra='forbid')  # Strict validation (CFG-AURORA-INSTRUMENTS-SSOT-01)

    # Strategy enable/disable flag
    enabled: bool = Field(description='Enable Aurora strategy for this instrument (default: True for backward compat)')

    # Signal weights (Phase 3+ Optuna results)
    weights: Optional[Dict[str, float]] = Field(description='Per-feature signal weights from Optuna')

    # Side bias
    side_bias: Optional[AuroraSideBiasConfig] = Field(description='Side bias configuration')

    position_mode: Literal["STRICT", "DYNAMIC"] = Field(description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap')

    # Regime-based thresholds
    regime_thresholds: Optional[Dict[str, float]] = Field(description='Threshold multipliers per regime (TREND, VOLATILE, FLAT)')

    # Regime-based position sizing
    regime_sizing: Optional[Dict[str, float]] = Field(description='Position size multipliers per regime')

    # Exit configuration
    exit: Optional[AuroraExitConfig] = Field(description='Stop-loss and max hold time')

    # Take profit configuration
    take_profit: Optional[AuroraTakeProfitConfig] = Field(description='TP1/TP2 partial exit settings')

    # Trailing stop configuration
    trailing_stop: Optional[AuroraTrailingStopConfig] = Field(description='Trailing stop settings')

    # Execution configuration
    execution: Optional[AuroraExecutionConfig] = Field(description='Order execution settings')

    # Phase 3+ per-asset overrides
    ema_clamp: Optional[EmaClampConfig] = Field(description='Per-asset EMA clamp range (Phase 3+)')
    signal_threshold: Optional[SignalThresholdConfig] = Field(description='Per-asset signal threshold (Phase 3+)')
    max_risk_score: Optional[MaxRiskScoreConfig] = Field(description='Per-asset max risk score (Phase 3+)')

    cooldown_sec: Optional[int] = Field(description='Per-instrument cooldown in seconds (overrides global qos.symbol_cooldown_sec)')

    # Phase 3+ Recovery: Regime gating
    allowed_regimes: Optional[List[str]] = Field(description='If set, only trade when current regime is in this list (Phase 3+ regime gating)')

    # Phase 1.5 Recovery: Per-instrument timeframe
    timeframe_sec: Optional[int] = Field(description='Bar timeframe in seconds for this instrument. SOL=180 (3m), BTC/ETH=300 (5m)')

    # NOTE: Position control is expressed via `position_mode` above.


class OpsConfig(BaseModel):
    """Operations configuration (killswitch, quiet hours, monitoring)."""
    model_config = ConfigDict(extra='forbid')

    # Emergency controls (A-01 fix)
    panic_killswitch: bool = Field(description='Emergency kill switch - blocks all new CMD:OPEN when True')
    panic_ttl_sec: Optional[int] = Field(description='Optional TTL in seconds for panic_killswitch; if set, killswitch auto-expires after this many seconds')
    quiet_hours_utc: List[str] = Field(description="Time windows in UTC when trading is blocked (e.g., ['22:00-06:00'])")
    allowlist_symbols: List[str] = Field(description='If non-empty, only these symbols can trade. Empty = no restrictions')
    
    # Monitoring
    metrics_url: str = Field()
    reports_dir: str = Field()


# ==============================================================================
# DOMAIN CONFIGURATION (Hybrid Mode: live data → testnet execution)
# ==============================================================================
class DomainModeConfig(BaseModel):
    """Configuration for a single domain's trading mode."""
    model_config = ConfigDict(extra='forbid')
    
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
    model_config = ConfigDict(extra='forbid')
    
    market_data: DomainModeConfig = Field(description="Market data source mode (should be 'live' for real prices)")
    feature_engineering: DomainModeConfig = Field(description='Feature engineering mode (should match market_data)')
    decision_making: DomainModeConfig = Field(description='Decision making mode (should match market_data)')
    risk_management: DomainModeConfig = Field(description='Risk management mode (testnet for safety)')
    execution_position: DomainModeConfig = Field(description="Execution mode (MUST be 'testnet' for testing!)")
    audit_trail: DomainModeConfig = Field(description="Audit trail mode (usually 'live' for logging)")


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='forbid')

    mode: str = Field(description='testnet | production | live')
    decision: DecisionConfig = Field()
    execution: Optional[ExecutionConfig] = Field()
    symbols_to_track: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of symbols to track for multi-TF aggregation. "
            "If omitted, it is derived deterministically from trading.decision.symbols_to_track."
        ),
    )
    market_data: Optional[MarketDataConfig] = Field()
    
    # NOTE (TASK23.FIX.B): Forbidden SSOT mirrors are intentionally NOT part of TradingConfig.
    # - instruments SSOT: root.instruments (config/aurora/instruments.yaml)
    # - aurora_instruments SSOT: root.aurora_instruments (config/aurora/aurora_instruments.yaml)
    # - domains SSOT: root.domains (config/aurora/domains.yaml)
    # - feature_engineering SSOT: domains.yaml (domain config), not trading.yaml
    
    # Legacy risk config (still used by DailyRiskState etc)
    risk: Dict[str, Any] = Field(description='Legacy risk configuration (daily gate, etc)')
    
    # TCA and Risk Budgets (Dicts for now but typed access via field)
    tca_prefs: Dict[str, Any] = Field(description='TCA Preferences')
    risk_budgets: Dict[str, Any] = Field(description='Risk Budgeting Configuration')

    # Risk management data sources (used for hybrid/live/testnet wiring)
    risk_management: "TradingRiskManagementConfig" = Field(...)
    
    # Ops configuration (killswitch, quiet hours)
    ops: Optional[OpsConfig] = Field(description='Operations config (panic killswitch, quiet hours, allowlist)')
    
    # CRITICAL: Domain-level mode configuration (Hybrid Mode)
    # Default is all-testnet for safety. Production MUST explicitly set live modes!
    domain_configuration: DomainConfigurationConfig = Field(description='Domain-level trading mode configuration for hybrid mode (live data + testnet execution)')

    @model_validator(mode='after')
    def _derive_symbols_to_track(self) -> "TradingConfig":
        """Derive symbols_to_track deterministically (no loader hydration).

        Policy (TASK28):
        - Preferred source: trading.symbols_to_track (explicit)
        - Fallback source: trading.decision.symbols_to_track (legacy)
        - If both missing/empty: fail-closed
        """

        if self.symbols_to_track is None:
            decision_symbols = getattr(self.decision, "symbols_to_track", None)
            if isinstance(decision_symbols, list) and decision_symbols:
                self.symbols_to_track = [str(s) for s in decision_symbols]

        if not isinstance(self.symbols_to_track, list) or not self.symbols_to_track:
            raise ValueError(
                "Missing trading.symbols_to_track (and no fallback trading.decision.symbols_to_track)."
            )

        # Normalize to strings for stability
        self.symbols_to_track = [str(s) for s in self.symbols_to_track]
        return self


class BinanceApiEnv(BaseModel):
    """Binance API configuration for a single environment."""
    model_config = ConfigDict(extra='forbid')

    api_key: Optional[str] = Field()
    api_secret: Optional[str] = Field()
    rest_url: Optional[str] = Field()
    ws_url: Optional[str] = Field()


class BinanceApiConfig(BaseModel):
    """Binance API configuration (live + testnet)."""
    model_config = ConfigDict(extra='forbid')
    live: BinanceApiEnv = Field()
    testnet: BinanceApiEnv = Field()


class RetrySchedulerConfig(BaseModel):
    """AuroraBridge retry scheduler configuration."""
    model_config = ConfigDict(extra='forbid')

    max_attempts: int = Field(..., description="Max retry attempts for deferred intents")
    min_retry_delay_ms: int = Field(..., description="Minimum retry delay (ms)")
    backoff_factor: float = Field(..., description="Retry backoff factor (>=1.0)")
    jitter_ms: int = Field(..., description="Optional jitter added to delay (ms, >=0)")


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
    model_config = ConfigDict(extra='forbid')
    poll_interval: int = Field(description='Polling interval in seconds')


class LoggingConfig(BaseModel):
    """Logging configuration."""
    model_config = ConfigDict(extra='forbid')

    level: str = Field()
    file: str = Field()
    format: str = Field()
    rotation: Dict[str, int] = Field()
    
    
class SystemMarketDataConfig(BaseModel):
    """System-level Market Data configuration."""
    model_config = ConfigDict(extra='forbid')
    
    queue_maxsize: int = Field(..., description="Max size of IPC queue (worker → proxy)")
    local_queue_maxsize: int = Field(..., description="Max size of local queue (proxy internal)")
    emit_workers: int = Field(..., description="Thread pool size for non-blocking FSM.emit()")
    tick_ttl_ms: int = Field(..., description="Max age of tick data in ms — older ticks are DROPPED")
    ws_heartbeat_sec: float = Field(..., description="aiohttp WS heartbeat interval (sec) to keep connection alive")
    ws_receive_timeout_sec: float = Field(..., description="Max time without WS messages (sec) before reconnect")
    proxy_batch_size: int = Field(..., description="Proxy consumer: max items processed per batch")
    proxy_queue_get_timeout_sec: float = Field(..., description="Proxy consumer: blocking get() timeout (sec)")
    proxy_idle_sleep_sec: float = Field(..., description="Proxy consumer: sleep when queue is empty (sec)")


class SystemConfig(BaseModel):
    """System configuration (framework-level)."""
    model_config = ConfigDict(extra='forbid')

    logging: LoggingConfig = Field()
    market_data: Optional[SystemMarketDataConfig] = Field(default=None, description='Market data system settings')


class SystemRuntimeMeta(BaseModel):
    """Runtime metadata captured during config load."""

    model_config = ConfigDict(extra='forbid')

    config_name: Optional[str] = Field(default=None, description='Identifier of the loaded config profile')
    config_dir: Optional[str] = Field(default=None, description='Filesystem path of the config directory in use')


class SystemMetaConfig(BaseModel):
    """Service/runtime metadata preserved under a dedicated namespace."""

    model_config = ConfigDict(extra='forbid')

    system_config_version: Optional[str] = Field(default=None)
    regime_config_version: Optional[str] = Field(default=None)
    sequential_tests: Dict[str, Any] = Field()
    risk_core: Dict[str, Any] = Field()
    kelly: Dict[str, Any] = Field()
    calibrator: Dict[str, Any] = Field()
    hawkes: Dict[str, Any] = Field()
    hotreload_whitelist: List[Any] = Field()
    hardening: Dict[str, Any] = Field()
    position_tracking: Dict[str, Any] = Field()
    runtime: Optional[SystemRuntimeMeta] = Field(default=None)


class AuroraConfig(BaseModel):
    """
    Root configuration model for AuroraTrader.

    This replaces the old dict-based AuroraConfig class with full type validation.
    Pydantic V2 validates on instantiation, raising ValidationError immediately if config is invalid.
    """
    model_config = ConfigDict(extra='forbid')

    # Core app configs
    trading_mode: str = Field(description='Trading mode: testnet | production | live')
    trading: TradingConfig = Field()

    # Exchange/account/market configs
    binance_api: BinanceApiConfig = Field()
    account_observer: AccountObserverConfig = Field()

    # System configs
    system: SystemConfig = Field()
    system_meta: SystemMetaConfig = Field()
    ops: OpsConfig = Field()

    # Bridge config (AuroraBridge retry scheduler)
    bridge: BridgeConfig = Field(...)
    
    # Domain configs (New)
    domains: DomainsConfig = Field(description='Domain-specific configurations')

    # Canonical instruments SSOT (config/aurora/instruments.yaml)
    instruments: Dict[str, InstrumentPrecisionSpec] = Field(description='Canonical instrument precision map (symbol -> tick_size/step_size)')
    
    # Canonical aurora_instruments SSOT (config/aurora/aurora_instruments.yaml)
    aurora_instruments: Dict[str, AuroraInstrumentConfig] = Field(description='Per-symbol Aurora strategy overrides (weights, side_bias, exit, etc.)')
    
    # Strategies registry SSOT (config/aurora/strategies.yaml)
    # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION
    strategies_registry: Optional[StrategiesRegistryConfig] = Field(default=None, description='Strategy assignments + arbitration config (from strategies.yaml)')
    
    # Strategy configs (Track B, optional root-level overrides)
    mean_reversion: Optional[MeanReversion1mStrategyConfig] = Field(default=None, description='Mean Reversion 1m strategy config (loaded from strategy profile SSOT)')

    # App-specific overrides
    # TASK23.FIX.B: Legacy root aliases must NOT be required.
    # If provided explicitly, they act as overrides; otherwise they should not block startup.
    decision: Optional[DecisionConfig] = Field(default=None, description='Override trading.decision if set')
    execution: Optional[ExecutionConfig] = Field(default=None, description='Override trading.execution if set')
    brackets: Optional[BracketsConfig] = Field(default=None)
    trailing: Dict[str, Any] = Field(default_factory=dict)
    
    # Regime Detector Config (loaded from regime.yaml, Pydantic-validated)
    models: Optional[RegimeModelsConfig] = Field(default=None, description='Regime detection models from regime.yaml')

    # regime.yaml SSOT (top-level keys)
    hmm: Dict[str, Any] = Field(description='HMM regime detector config (from regime.yaml)')
    features: Dict[str, Any] = Field(description='Regime features config (from regime.yaml)')
    hotreload_whitelist: List[str] = Field(description='Hot-reload allowlist (from regime.yaml)')

    # Strategy profile SSOT (loaded registry-driven; may be null if not assigned)
    aurora: Optional[Dict[str, Any]] = Field(default=None, description='Aurora strategy global config (from strategies/aurora.yaml)')

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

    @model_validator(mode='after')
    def _backcompat_root_execution_alias(self) -> "AuroraConfig":
        """Back-compat: expose trading.execution at root execution if root is unset.

        This is a deterministic aliasing rule and must not be implemented via loader dict mutation.
        """
        if self.execution is None and getattr(self.trading, "execution", None) is not None:
            self.execution = self.trading.execution
        return self


# Convenience function for creating config from dict
def create_aurora_config(config_dict: Dict[str, Any]) -> AuroraConfig:
    """Create a validated AuroraConfig from a dictionary.

    Raises pydantic.ValidationError on invalid config.
    """
    return AuroraConfig(**config_dict)


# Backward-compat imports for tests/legacy modules
AuroraTradingConfig = TradingConfig
AuroraExposureConfig = ExposureConfig
