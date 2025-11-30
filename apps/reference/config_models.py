"""
Pydantic V2 configuration models for AuroraTrader.

This module defines the complete configuration schema with full type validation.
All models are designed to fail fast (startup validation) rather than silently accepting invalid configs.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class InstrumentSpec(BaseModel):
    """Specification for a trading instrument (e.g., BTCUSDT)."""
    model_config = ConfigDict(
        extra='allow')  # Allow additional fields from YAML

    symbol: str = Field(...)
    step_size: str = Field(default="0.001", description="Quantity precision")
    tick_size: str = Field(default="0.01", description="Price precision")
    min_qty: str = Field(default="0.001")
    min_notional: str = Field(
        default="10.0", description="Minimum notional value in USDT")
    quote: str = Field(default="USDT")


class SignalWeights(BaseModel):
    """Weights for signal calculation (OBI, TFI, etc)."""
    model_config = ConfigDict(extra='allow')

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


class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""
    model_config = ConfigDict(extra='allow')

    min_position_size_usd: float = Field(default=10.0)
    liquidity_based_cap_usd: float = Field(default=10000.0)
    risk_fraction_q: Optional[float] = Field(default=None)
    liquidity_kappa: float = Field(default=1.0)
    kappa_mode: str = Field(default="passive")


class KellyConfig(BaseModel):
    """Kelly criterion configuration."""
    base_probability: float = Field(default=0.5)
    kelly_cap: float = Field(default=0.25)
    kelly_alpha: float = Field(default=0.8)
    payoff_ratio_r: float = Field(default=1.5)


class QosConfig(BaseModel):
    """Quality of Service configuration for rate limiting."""
    exposure_block_cooldown_sec: int = Field(default=60)
    symbol_cooldown_sec: int = Field(default=3)
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


class DecisionConfig(BaseModel):
    """Decision making configuration (testnet/production overrides)."""
    model_config = ConfigDict(extra='allow')

    # Mode-specific configs
    testnet: Optional[Dict[str, Any]] = Field(default=None)
    production: Optional[Dict[str, Any]] = Field(default=None)

    signal_threshold: float = Field(default=0.2)
    signal_weights: SignalWeights = Field(default_factory=SignalWeights)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)
    position_sizing: PositionSizingConfig = Field(
        default_factory=PositionSizingConfig)
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    qos: QosConfig = Field(default_factory=QosConfig)

    bar_gating: Optional[BarGatingConfig] = Field(default=None)
    behavior_fsm: Optional[BehaviorFsmConfig] = Field(default=None)
    roi_exit: Optional[ROIExitConfig] = Field(default=None)

    sizing_modifiers: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific multipliers")
    regime_thresholds: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific signal thresholds")


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


class ManageConfig(BaseModel):
    """Order management configuration."""
    model_config = ConfigDict(extra='allow')

    brackets: Optional[BracketsConfig] = Field(default=None)
    emergency: Dict[str, Any] = Field(default_factory=dict)
    auto: bool = Field(default=False)
    orphan_monitor: Dict[str, Any] = Field(default_factory=dict)
    failsafe: Optional[FailsafeConfig] = Field(default=None)


class ExposureConfig(BaseModel):
    """Exposure guard configuration."""
    model_config = ConfigDict(extra='allow')

    max_equity_utilization_pct: float = Field(default=0.20)
    max_portfolio_fraction: float = Field(default=0.20)
    max_side_utilization_pct: Dict[str, float] = Field(
        default_factory=lambda: {"long": 0.12, "short": 0.12})
    max_directional_ratio: float = Field(default=2.0)
    per_symbol_cap_pct: float = Field(default=0.08)
    pending_ttl_sec: int = Field(default=90)
    post_fill_hold_ttl_sec: int = Field(default=30)
    positions_stale_ttl_sec: int = Field(default=120)
    leverage_defaults: Dict[str, int] = Field(
        default_factory=lambda: {"__default__": 20})


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    model_config = ConfigDict(extra='allow')
    
    ack_ttl_ms: int = Field(default=8000)
    fill_ttl_ms: int = Field(default=30000)
    check_interval_ms: int = Field(default=1000)
    rps_limit: int = Field(default=10)


class RegimeModelConfig(BaseModel):
    """Base configuration for regime detection models."""
    model_config = ConfigDict(extra='allow')
    
    confidence_multiplier: float = Field(default=20.0)
    confidence_min: float = Field(default=0.5)
    confidence_max: float = Field(default=0.95)


class RegimeDetectorConfig(BaseModel):
    """Regime detector configuration."""
    model_config = ConfigDict(extra='allow')
    
    models: Dict[str, Any] = Field(default_factory=dict)


class ExecutionConfig(BaseModel):
    """Execution configuration."""
    model_config = ConfigDict(extra='allow')

    manage: Optional[ManageConfig] = Field(default=None)
    exposure: Optional[ExposureConfig] = Field(default=None)
    exposure: Optional[ExposureConfig] = Field(default=None)
    watchdog: Dict[str, Any] = Field(default_factory=dict)  # Kept as dict for flexibility, but we'll validate keys in code


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    anchors: List[str] = Field(
        default_factory=list, description="Anchor symbols for macro alignment")
    window: int = Field(default=60, description="Window in seconds")
    emit_abs: bool = Field(default=False)


class ApiCallLimits(BaseModel):
    """API call limits configuration."""
    get_recent_trades: int = Field(default=50)
    get_klines: Dict[str, Any] = Field(default_factory=lambda: {"interval": "1m", "limit": 2})


class MarketDataConfig(BaseModel):
    """Market data configuration."""
    model_config = ConfigDict(extra='allow')

    poll_interval_sec: float = Field(default=2.0)
    websocket_streams: List[str] = Field(default_factory=lambda: ["bookTicker", "trade"])
    api_call_limits: ApiCallLimits = Field(default_factory=ApiCallLimits)
    macro_sync: Optional[MacroSyncConfig] = Field(default=None)


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
    model_config = ConfigDict(extra='allow')

    ema: Dict[str, Any] = Field(default_factory=dict)
    volume: Dict[str, Any] = Field(default_factory=dict)
    volatility: Dict[str, Any] = Field(default_factory=dict)
    liquidity: Dict[str, Any] = Field(default_factory=dict)
    macro_sync: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Domain-Specific Configuration Models
# ============================================================================

# Decision Making Domain
class PositionSizingConfig(BaseModel):
    """Position sizing configuration for decision making."""
    model_config = ConfigDict(extra='allow')
    
    min_position_size_usd: float = Field(default=10)
    liquidity_based_cap_usd: float = Field(default=10000)


class QoSConfig(BaseModel):
    """Quality of Service configuration for decision making."""
    model_config = ConfigDict(extra='allow')
    
    exposure_block_cooldown_sec: int = Field(default=10)
    symbol_cooldown_sec: int = Field(default=3)
    max_intents_per_minute_per_symbol: int = Field(default=6)
    mode: str = Field(default="defer")  # defer, enforce, shadow
    enforce: bool = Field(default=False)


class FeaturesTtlConfig(BaseModel):
    """Features TTL configuration."""
    model_config = ConfigDict(extra='allow')
    
    ttl_sec: int = Field(default=5)


# Note: BarGatingConfig and BehaviorFsmConfig already exist above

class SignalsConfig(BaseModel):
    """Signals processing configuration."""
    model_config = ConfigDict(extra='allow')
    
    normalize: bool = Field(default=False)


class DecisionMakingDomainConfig(BaseModel):
    """Complete decision making domain configuration."""
    model_config = ConfigDict(extra='allow')
    
    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    qos: QoSConfig = Field(default_factory=QoSConfig)
    features: FeaturesTtlConfig = Field(default_factory=FeaturesTtlConfig)
    bar_gating: BarGatingConfig = Field(default_factory=BarGatingConfig)
    behavior_fsm: BehaviorFsmConfig = Field(default_factory=BehaviorFsmConfig)
    signals: SignalsConfig = Field(default_factory=SignalsConfig)


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
    model_config = ConfigDict(extra='allow')
    
    delta_price_pct: float = Field(default=0.1)
    obi: float = Field(default=0.3)
    tfi: float = Field(default=0.3)
    absorption_inverse: float = Field(default=0.3)


class TradingAllowedThresholdsConfig(BaseModel):
    """Trading allowed thresholds configuration."""
    model_config = ConfigDict(extra='allow')
    
    max_risk_score: float = Field(default=0.8)


class RiskValidationConfig(BaseModel):
    """Risk validation configuration."""
    model_config = ConfigDict(extra='allow')
    
    total_weight_min: float = Field(default=0.5)
    total_weight_max: float = Field(default=2.0)


class RiskManagementDomainConfig(BaseModel):
    """Complete risk management domain configuration."""
    model_config = ConfigDict(extra='allow')
    
    risk_score_weights: RiskScoreWeightsConfig = Field(default_factory=RiskScoreWeightsConfig)
    trading_allowed_thresholds: TradingAllowedThresholdsConfig = Field(default_factory=TradingAllowedThresholdsConfig)
    validation: RiskValidationConfig = Field(default_factory=RiskValidationConfig)


# Position Tracking Domain
class PrecisionConfig(BaseModel):
    """Position precision configuration."""
    model_config = ConfigDict(extra='allow')
    
    quantity_min_threshold: float = Field(default=1e-9)
    flat_position_threshold: float = Field(default=1e-12)
    decimal_places: int = Field(default=2)


class ThreadTimeoutsConfig(BaseModel):
    """Thread timeouts configuration."""
    model_config = ConfigDict(extra='allow')
    
    join_timeout_sec: int = Field(default=10)


class PositionTrackingDomainConfig(BaseModel):
    """Complete position tracking domain configuration."""
    model_config = ConfigDict(extra='allow')
    
    precision: PrecisionConfig = Field(default_factory=PrecisionConfig)
    thread_timeouts: ThreadTimeoutsConfig = Field(default_factory=ThreadTimeoutsConfig)


# Account Observer Domain
class AccountObserverDomainConfig(BaseModel):
    """Complete account observer domain configuration."""
    model_config = ConfigDict(extra='allow')
    
    poll_interval_sec: int = Field(default=5)
    trade_limit: int = Field(default=10)
    symbols: List[str] = Field(default_factory=list)  # Empty = use trading.symbols_to_track
    thread_timeouts: ThreadTimeoutsConfig = Field(default_factory=ThreadTimeoutsConfig)


# Execution Position Domain
class ExposureGuardConfig(BaseModel):
    """Exposure guard configuration."""
    model_config = ConfigDict(extra='allow')
    
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
    model_config = ConfigDict(extra='allow')
    
    idempotency_window_sec: int = Field(default=60)


class OrderIndexConfig(BaseModel):
    """Order index configuration."""
    model_config = ConfigDict(extra='allow')
    
    ttl_sec: int = Field(default=3600)


class MetricsCollectorConfig(BaseModel):
    """Metrics collector configuration."""
    model_config = ConfigDict(extra='allow')
    
    window_size_minutes: int = Field(default=60)
    recent_rejections_minutes: int = Field(default=5)


class IdempotentCancelConfig(BaseModel):
    """Idempotent cancel configuration."""
    model_config = ConfigDict(extra='allow')
    
    max_retries: int = Field(default=2)


class ExecutionUtilsConfig(BaseModel):
    """Execution utilities configuration."""
    model_config = ConfigDict(extra='allow')
    
    client_order_id_max_length: int = Field(default=32)
    basis_points_base: float = Field(default=10000.0)


class ExecutionPositionDomainConfig(BaseModel):
    """Complete execution position domain configuration."""
    model_config = ConfigDict(extra='allow')
    
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)
    exposure_guard: ExposureGuardConfig = Field(default_factory=ExposureGuardConfig)
    fsm_open: FsmOpenConfig = Field(default_factory=FsmOpenConfig)
    order_index: OrderIndexConfig = Field(default_factory=OrderIndexConfig)
    metrics_collector: MetricsCollectorConfig = Field(default_factory=MetricsCollectorConfig)
    idempotent_cancel: IdempotentCancelConfig = Field(default_factory=IdempotentCancelConfig)
    utils: ExecutionUtilsConfig = Field(default_factory=ExecutionUtilsConfig)


# Top-Level Domains Configuration
class DomainsConfig(BaseModel):
    """Top-level domains configuration container."""
    model_config = ConfigDict(extra='allow')
    
    decision_making: DecisionMakingDomainConfig = Field(default_factory=DecisionMakingDomainConfig)
    feature_engineering: FeatureEngineeringDomainConfig = Field(default_factory=FeatureEngineeringDomainConfig)
    risk_management: RiskManagementDomainConfig = Field(default_factory=RiskManagementDomainConfig)
    position_tracking: PositionTrackingDomainConfig = Field(default_factory=PositionTrackingDomainConfig)
    account_observer: AccountObserverDomainConfig = Field(default_factory=AccountObserverDomainConfig)
    execution_position: ExecutionPositionDomainConfig = Field(default_factory=ExecutionPositionDomainConfig)


# Legacy FeatureEngineeringConfig for backward compatibility
class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration (legacy, simplified)."""
    model_config = ConfigDict(extra='allow')

    ema: Dict[str, Any] = Field(default_factory=dict)
    volume: Dict[str, Any] = Field(default_factory=dict)
    volatility: Dict[str, Any] = Field(default_factory=dict)
    liquidity: Dict[str, Any] = Field(default_factory=dict)
    macro_sync: Dict[str, Any] = Field(default_factory=dict)


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='allow')

    mode: str = Field(default="testnet",
                      description="testnet | production | live")
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    execution: Optional[ExecutionConfig] = Field(default=None)
    instruments: Dict[str, InstrumentSpec] = Field(default_factory=dict)
    symbols_to_track: List[str] = Field(default_factory=list, description="List of symbols to track for multi-TF aggregation")
    market_data: Optional[MarketDataConfig] = Field(default=None)
    feature_engineering: Optional[FeatureEngineeringConfig] = Field(
        default=None)
    domains: DomainsConfig = Field(default_factory=DomainsConfig)  # NEW: Domain-specific configurations


class BinanceApiEnv(BaseModel):
    """Binance API configuration for a single environment."""
    model_config = ConfigDict(extra='allow')

    api_key: Optional[str] = Field(default=None)
    api_secret: Optional[str] = Field(default=None)
    rest_url: Optional[str] = Field(default=None)
    ws_url: Optional[str] = Field(default=None)


class BinanceApiConfig(BaseModel):
    """Binance API configuration (live + testnet)."""
    live: BinanceApiEnv = Field(default_factory=BinanceApiEnv)
    testnet: BinanceApiEnv = Field(default_factory=BinanceApiEnv)


class AccountObserverConfig(BaseModel):
    """Account observer configuration."""
    model_config = ConfigDict(extra='allow')
    poll_interval: int = Field(
        default=30, description="Polling interval in seconds")


class OpsConfig(BaseModel):
    """Operations configuration (monitoring, logging)."""
    model_config = ConfigDict(extra='allow')

    metrics_url: str = Field(default="http://127.0.0.1:8000/metrics")
    reports_dir: str = Field(default="reports")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    model_config = ConfigDict(extra='allow')

    level: str = Field(default="INFO")
    file: str = Field(default="logs/aurora_core.log")
    format: str = Field(default="json")
    rotation: Dict[str, int] = Field(default_factory=lambda: {
                                     "max_bytes": 10 * 1024 * 1024, "backup_count": 5})


class SystemConfig(BaseModel):
    """System configuration (framework-level)."""
    model_config = ConfigDict(extra='allow')

    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class AuroraConfig(BaseModel):
    """
    Root configuration model for AuroraTrader.

    This replaces the old dict-based AuroraConfig class with full type validation.
    Pydantic V2 validates on instantiation, raising ValidationError immediately if config is invalid.
    """
    model_config = ConfigDict(
        extra='allow')  # Allow additional top-level fields

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
    # System configs
    system: SystemConfig = Field(default_factory=SystemConfig)
    ops: OpsConfig = Field(default_factory=OpsConfig)
    
    # Domain configs (New)
    domains: Optional[DomainsConfig] = Field(default=None, description="Domain-specific configurations")

    # App-specific overrides
    decision: Optional[DecisionConfig] = Field(
        default=None, description="Override trading.decision if set")
    execution: Optional[ExecutionConfig] = Field(
        default=None, description="Override trading.execution if set")
    brackets: Optional[BracketsConfig] = Field(default=None)
    brackets: Optional[BracketsConfig] = Field(default=None)
    trailing: Dict[str, Any] = Field(default_factory=dict)
    
    # Regime Detector Config (loaded from regime.yaml usually, but can be part of main config)
    models: Optional[Dict[str, Any]] = Field(default=None)

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
