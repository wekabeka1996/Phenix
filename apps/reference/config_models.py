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


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
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
