"""
Feature Engineering Types - Pure Data Structures.

FTR-04: Extracted from feature_engineering.py for Separation of Concerns.

This module contains:
- HotState: Tick-critical state (EMA, volume windows, deques)
- ColdState: Slow-changing state (funding rate, OI)
- SymbolFeatureState: Container for Hot/Cold per symbol
- FeatureEngineeringConfig: Typed configuration wrapper

NO FSM imports, NO business logic, only dataclasses and config wrapper.
"""

import decimal
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union, Deque, Tuple
from collections import deque

if TYPE_CHECKING:
    from apps.reference.config_models import (
        AuroraConfig,
        FeatureEngineeringDomainConfig,
    )
    from apps.reference.domain_config import DomainConfigResolver


# =============================================================================
# STATE DATACLASSES (Hot/Cold Pattern)
# =============================================================================

@dataclass
class HotState:
    """
    Tick-critical state for feature engineering.
    
    Updated on every market tick. Contains all data needed for
    real-time feature calculations.
    
    FTR-03: Added Welford stats tuples for O(1) mean/stddev calculation.
    The deques are still needed as FIFO queues to know which value to remove.
    """
    # EMA state
    ema_short: Optional[decimal.Decimal] = None
    ema_long: Optional[decimal.Decimal] = None
    ema_short_alpha: float = 0.0
    ema_long_alpha: float = 0.0
    
    # Volume spike state
    vol_window_start_ts: Optional[int] = None
    vol_current_ts: Optional[int] = None
    vol_window_trades: float = 0.0
    vol_hist: Deque[float] = field(default_factory=deque)
    # FTR-03: Welford stats for O(1) volume mean/stddev
    vol_stats: tuple[int, float, float] = (0, 0.0, 0.0)  # (count, mean, m2)

    # TASK24.C2: Time-normalized volume_spike (Decimal-only)
    volume_rate_hist: Deque[decimal.Decimal] = field(default_factory=deque)
    volume_rate_current: Optional[decimal.Decimal] = None
    volume_spike_ready: bool = False
    volume_spike_not_ready_reason: Optional[str] = None
    
    # Volatility state
    range_window_start_ts: Optional[int] = None
    range_min: Optional[decimal.Decimal] = None
    range_max: Optional[decimal.Decimal] = None
    range_hist: Deque[float] = field(default_factory=deque)  # Changed to float for Welford
    # FTR-03: Welford stats for O(1) range mean/stddev
    range_stats: tuple[int, float, float] = (0, 0.0, 0.0)  # (count, mean, m2)

    # TASK24.C3: Volatility readiness (explicit)
    volatility_state_ready: bool = False
    volatility_state_not_ready_reason: Optional[str] = None
    
    # Returns for macro_sync
    returns_buffer: Deque[float] = field(default_factory=deque)
    prev_price: Optional[decimal.Decimal] = None

    # TASK24.C1: Macro sync readiness (explicit)
    macro_sync_ready: bool = False
    macro_sync_not_ready_reason: Optional[str] = None

    # TASK31: Large trade imbalance readiness (explicit)
    large_trade_imbalance_ready: bool = False
    large_trade_imbalance_not_ready_reason: Optional[str] = None
    large_trade_imbalance_trades_used: int = 0
    large_trade_imbalance_dropped_out_of_order: int = 0


@dataclass
class ColdState:
    """
    Slow-changing state for feature engineering.
    
    Updated periodically (e.g., funding rate every 8h).
    FTR-05: Activated for Futures features (funding_rate, OI).
    """
    # Funding Rate (updated every 8h typically)
    funding_rate: decimal.Decimal = decimal.Decimal("0")
    next_funding_ts: int = 0
    
    # Open Interest (updated periodically)
    open_interest: decimal.Decimal = decimal.Decimal("0")
    
    # FTR-05: Fields for delta calculation
    prev_open_interest: Optional[decimal.Decimal] = None
    last_oi_update_ts: int = 0


@dataclass
class SymbolFeatureState:
    """
    Container for all feature state for a single symbol.
    
    Separates hot (tick-critical) and cold (periodic) state
    for clear ownership and future optimization.
    """
    hot: HotState
    cold: ColdState


# =============================================================================
# CONFIGURATION WRAPPER
# =============================================================================


class FeatureEngineeringConfig:
    """
    Configuration wrapper that provides clean access to feature engineering settings.
    
    Eliminates hasattr/isinstance checks by providing typed access to all config values.
    Works with both DomainConfigResolver (preferred) and raw AuroraConfig.
    """
    __slots__ = ('_cfg',)
    
    def __init__(self, config: Union["DomainConfigResolver", "AuroraConfig"]):
        """
        Initialize with config source.
        
        Args:
            config: DomainConfigResolver or AuroraConfig
        """
        self._cfg = self._resolve_config(config)
    
    def _resolve_config(self, config) -> "FeatureEngineeringDomainConfig":
        """Resolve config to FeatureEngineeringDomainConfig."""
        # Import here to avoid circular imports
        from apps.reference.config_models import (
            FeatureEngineeringDomainConfig,
            AuroraConfig,
        )
        from apps.reference.domain_config import DomainConfigResolver
        
        # If already a resolver, use it
        if isinstance(config, DomainConfigResolver):
            return config.get_feature_engineering()
        
        # If AuroraConfig, create resolver
        if isinstance(config, AuroraConfig):
            resolver = DomainConfigResolver(config)
            return resolver.get_feature_engineering()
        
        # Strict object config: no dict support (TASK25).
        if isinstance(config, dict):
            raise TypeError("FeatureEngineeringConfig requires AuroraConfig or DomainConfigResolver, got dict")
        
        raise TypeError(f"Invalid config type for FeatureEngineering: {type(config)}")
    
    # =========================================================================
    # TYPED ACCESSORS - No more hasattr/try-except!
    # =========================================================================
    
    @property
    def enable_new_metrics(self) -> bool:
        return self._cfg.enable_new_metrics
    
    @property
    def ema_period_short(self) -> int:
        return self._cfg.ema.period_short
    
    @property
    def ema_period_long(self) -> int:
        return self._cfg.ema.period_long
    
    @property
    def ema_short_alpha(self) -> float:
        return 2.0 / (self._cfg.ema.period_short + 1)
    
    @property
    def ema_long_alpha(self) -> float:
        return 2.0 / (self._cfg.ema.period_long + 1)
    
    @property
    def volume_sma_length(self) -> int:
        return self._cfg.volume.sma_length
    
    @property
    def volume_window_sec(self) -> int:
        return self._cfg.volume.window_sec
    
    @property
    def volume_window_ms(self) -> int:
        return self._cfg.volume.window_sec * 1000
    
    @property
    def volatility_sma_length(self) -> int:
        return self._cfg.volatility.sma_length
    
    @property
    def volatility_window_sec(self) -> int:
        return self._cfg.volatility.window_sec
    
    @property
    def volatility_window_ms(self) -> int:
        return self._cfg.volatility.window_sec * 1000
    
    @property
    def depth_half(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.liquidity.depth_half))
    
    @property
    def kappa_min(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.liquidity.kappa_min))
    
    @property
    def kappa_max(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.liquidity.kappa_max))
    
    @property
    def ema_bias_clamp_min(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.ema_bias.clamp_min))
    
    @property
    def ema_bias_clamp_max(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.ema_bias.clamp_max))
    
    @property
    def volume_spike_cap(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.volume_spike.cap_max))

    @property
    def volume_spike_sma_len(self) -> int:
        return int(self._cfg.volume_spike.sma_len)

    @property
    def volume_spike_eps(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.volume_spike.eps))

    @property
    def large_trade_imbalance_window_ms(self) -> int:
        return int(self._cfg.large_trade_imbalance.window_ms)

    @property
    def large_trade_imbalance_min_trades(self) -> int:
        return int(self._cfg.large_trade_imbalance.min_trades)

    @property
    def large_trade_imbalance_eps(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.large_trade_imbalance.eps))

    @property
    def large_trade_imbalance_use_notional(self) -> bool:
        return bool(self._cfg.large_trade_imbalance.use_notional)
    
    @property
    def volatility_state_cap(self) -> decimal.Decimal:
        return decimal.Decimal(str(self._cfg.volatility_state.cap_max))
    
    @property
    def macro_sync_enabled(self) -> bool:
        return self._cfg.macro_sync.enabled

    @property
    def macro_sync_time_diff_threshold_ms(self) -> int:
        return int(self._cfg.macro_sync.time_diff_threshold_ms)

    @property
    def macro_sync_ttl_ms(self) -> int:
        return int(self._cfg.macro_sync.ttl_ms)

    @property
    def macro_sync_anchors(self) -> list:
        return self._cfg.macro_sync.anchors

    @property
    def macro_sync_align_mode(self) -> str:
        return str(self._cfg.macro_sync.align_mode)

    @property
    def macro_sync_anchor_update_from_ticks(self) -> bool:
        return bool(self._cfg.macro_sync.anchor_update_from_ticks)
    
    @property
    def macro_sync_window(self) -> int:
        return self._cfg.macro_sync.window

    @property
    def macro_sync_bin_ms(self) -> int:
        return int(self._cfg.macro_sync.bin_ms)

    @property
    def macro_sync_max_gap_bins(self) -> int:
        return int(self._cfg.macro_sync.max_gap_bins)

    @property
    def macro_sync_eps(self) -> float:
        return float(self._cfg.macro_sync.eps)
    
    @property
    def macro_sync_min_buffer(self) -> int:
        return self._cfg.macro_sync.min_buffer_size
    
    @property
    def delta_price_spike_filter_ms(self) -> int:
        return self._cfg.delta_price.spike_filter_ms

    @property
    def ms_per_sec(self) -> int:
        return int(self._cfg.defaults.ms_per_sec)
    
    # =========================================================================
    # DEFAULT VALUES - No more magic numbers!
    # =========================================================================
    
    @property
    def neutral_value(self) -> decimal.Decimal:
        """Default neutral value for normalized features [0,1]. 0.5 = center."""
        return decimal.Decimal(str(self._cfg.defaults.neutral_value))
    
    @property
    def zero_value(self) -> decimal.Decimal:
        """Zero value for absent features (e.g., absorption placeholder)."""
        return decimal.Decimal(str(self._cfg.defaults.zero_value))
    
    @property
    def correlation_default(self) -> float:
        """Default correlation value when insufficient data."""
        return self._cfg.defaults.correlation_default
    
    @property
    def ms_per_sec(self) -> int:
        """Conversion constant: milliseconds per second."""
        return self._cfg.defaults.ms_per_sec

    # =========================================================================
    # FUTURES CONFIG (FTR-05)
    # =========================================================================
    
    @property
    def futures_enabled(self) -> bool:
        """Whether Futures features (funding_rate, OI) are enabled."""
        try:
            futures_cfg = self._cfg.futures
        except AttributeError:
            return False
        return futures_cfg is not None and futures_cfg.enabled
    
    @property
    def funding_extreme_threshold(self) -> decimal.Decimal:
        """Threshold for extreme funding rate normalization (default 0.001 = 0.1%)."""
        try:
            return decimal.Decimal(str(self._cfg.futures.funding.extreme_threshold))
        except AttributeError:
            return decimal.Decimal("0.001")
