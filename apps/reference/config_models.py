"""
Pydantic V2 configuration models for AuroraTrader.

This module defines the complete configuration schema with full type validation.
All models are designed to fail fast (startup validation) rather than silently accepting invalid configs.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from dataclasses import dataclass


@dataclass
class ConfigV2:
    """Config v2 structure for modular configuration."""
    core: Optional[Dict[str, Any]] = None
    symbols: Optional[Dict[str, Any]] = None
    instruments: Optional[Dict[str, Any]] = None
    domains: Dict[str, Dict[str, Any]] = None  # type: ignore[assignment]
    overrides: Optional[Dict[str, Any]] = None
    modes: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.domains is None:
            self.domains = {}


@dataclass(frozen=True)
class InstrumentProfile:
    """Unified instrument profile for all domains."""
    symbol: str
    exchange: str
    base_asset: str
    quote_asset: str

    precision_quantity: int
    precision_price: int

    min_notional: float
    min_qty: float
    min_price: float
    step_size: float
    tick_size: float

    max_position_size: float
    max_leverage: float

    default_tp_bps: Optional[float] = None
    default_sl_bps: Optional[float] = None
    min_sl_bps: Optional[float] = None
    min_tp_bps: Optional[float] = None

    regime_multipliers: Optional[Dict[str, float]] = None
    risk_max_drawdown_pct: Optional[float] = None
    risk_fraction: Optional[float] = None

    source: str = "legacy"


@dataclass
class RegimeDetectorConfig:
    """Configuration for RegimeDetector domain."""
    window_minutes: int
    min_regime_duration_min: int
    debounce_changes: bool
    # e.g., {"NORMAL": {"vol_std_bps_min": 0, ...}, ...}
    regimes: Dict[str, Dict[str, float]]
    hotreload_allowed: List[str]
    # Models configuration (sma_trend, volatility, sideways)
    models: Dict[str, Any]
    source: str = "legacy"


@dataclass
class SizingPolicy:
    """Configuration for position sizing."""
    mode: str
    max_risk_pct: float
    max_risk_usd: float
    min_notional_usd: float
    max_notional_usd: float
    liquidity_kappa: float = 1.0
    liquidity_kappa_mode: str = "static"
    kelly: Optional[Dict[str, Any]] = None
    source: str = "legacy"


@dataclass
class DecisionPolicy:
    """Configuration for decision making."""
    signal_threshold: float
    neutral_threshold: float
    max_intents_per_minute_per_symbol: int
    symbol_intent_cooldown_sec: int
    exposure_block_cooldown_sec: int
    source: str = "legacy"


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
    model_config = ConfigDict(extra='allow')

    exposure_block_cooldown_sec: int = Field(default=60)
    symbol_intent_cooldown_sec: int = Field(default=3)
    # Deprecated: kept for backward compatibility until all consumers migrate
    symbol_cooldown_sec: Optional[int] = Field(default=None)
    max_intents_per_minute_per_symbol: int = Field(default=10)
    mode: str = Field(default="defer", description="defer | block")
    enforce: bool = Field(default=False)

    @field_validator(
        "exposure_block_cooldown_sec",
        "symbol_intent_cooldown_sec",
        "max_intents_per_minute_per_symbol",
        check_fields=False,
    )
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("QoS cooldown parameters must be non-negative")
        return value


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

    sizing_modifiers: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific multipliers")
    regime_thresholds: Dict[str, float] = Field(
        default_factory=dict, description="Regime-specific signal thresholds")


@dataclass
class RiskSoftLimits:
    """Soft limit clipping configuration for exposure guard."""
    mode: str
    clip_min_notional_usdt: float
    directional_ratio_max: float
    side_exposure_usdt: float
    margin_exposure_usdt: float
    source: str = "legacy"


@dataclass
class RiskScoreWeights:
    """Weights for composite risk score calculation."""
    delta_price_pct: float
    obi: float
    tfi: float
    absorption_inverse: float
    source: str = "legacy"


@dataclass
class TradingAllowedThresholds:
    """Risk gate thresholds controlling trading permission."""
    max_risk_score: float
    overrides: Optional[Dict[str, float]] = None
    source: str = "legacy"

    def for_profile(self, profile: Optional[str]) -> float:
        """Return threshold for a specific profile, falling back to base value."""
        if profile and self.overrides and profile in self.overrides:
            return self.overrides[profile]
        return self.max_risk_score


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


class ManageConfig(BaseModel):
    """Order management configuration."""
    model_config = ConfigDict(extra='allow')

    brackets: Optional[BracketsConfig] = Field(default=None)
    emergency: Dict[str, Any] = Field(default_factory=dict)
    auto: bool = Field(default=False)
    orphan_monitor: Dict[str, Any] = Field(default_factory=dict)


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


class ExecutionConfig(BaseModel):
    """Execution configuration."""
    model_config = ConfigDict(extra='allow')

    manage: Optional[ManageConfig] = Field(default=None)
    exposure: Optional[ExposureConfig] = Field(default=None)
    watchdog: Dict[str, Any] = Field(default_factory=dict)


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    anchors: List[str] = Field(
        default_factory=list, description="Anchor symbols for macro alignment")
    window: int = Field(default=60, description="Window in seconds")
    emit_abs: bool = Field(default=False)


class MarketDataConfig(BaseModel):
    """Market data configuration."""
    model_config = ConfigDict(extra='allow')

    poll_interval_sec: int = Field(default=5)
    websocket_streams: List[str] = Field(default_factory=list)
    macro_sync: Optional[MacroSyncConfig] = Field(default=None)


@dataclass
class FeatureEngineeringConfig:
    """Configuration for FeatureEngineering domain."""
    enable_new_metrics: bool
    ema_period_short: int
    ema_period_long: int
    ema_bias_clamp: float
    volume_window_sec: int
    volume_sma_length: int
    volume_spike_cap: float
    volatility_window_sec: int
    volatility_sma_length: int
    volatility_ratio_cap: float
    liquidity_depth_half: float
    liquidity_kappa_min: float
    liquidity_kappa_max: float
    macro_sync_enabled: bool
    macro_sync_anchors: List[str]
    macro_sync_window: int
    source: str = "legacy"


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='allow')

    mode: str = Field(default="testnet",
                      description="testnet | production | live")
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    execution: Optional[ExecutionConfig] = Field(default=None)
    instruments: Dict[str, InstrumentSpec] = Field(default_factory=dict)
    market_data: Optional[MarketDataConfig] = Field(default=None)
    feature_engineering: Optional[FeatureEngineeringConfig] = Field(
        default=None)


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
    ops: OpsConfig = Field(default_factory=OpsConfig)

    # App-specific overrides
    decision: Optional[DecisionConfig] = Field(
        default=None, description="Override trading.decision if set")
    execution: Optional[ExecutionConfig] = Field(
        default=None, description="Override trading.execution if set")
    brackets: Optional[BracketsConfig] = Field(default=None)
    trailing: Dict[str, Any] = Field(default_factory=dict)

    # Config v2 support
    config_v2: Optional[ConfigV2] = Field(
        default=None, description="Config v2 structure")

    # EP-CONFIG-INJECTION-S2: Typed config for execution_position domain
    execution_position_cfg: Optional[Any] = Field(
        default=None,
        description="Typed ExecutionPositionConfig (Pydantic) built from config_v2.domains['execution']"
    )

    def has_config_v2(self) -> bool:
        """Check if any config v2 files were loaded."""
        if self.config_v2 is None:
            return False
        return (
            self.config_v2.core is not None or
            self.config_v2.symbols is not None or
            self.config_v2.instruments is not None or
            bool(self.config_v2.domains) or
            self.config_v2.overrides is not None or
            self.config_v2.modes is not None
        )

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
