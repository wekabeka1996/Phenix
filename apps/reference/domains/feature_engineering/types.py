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
from typing import TYPE_CHECKING, Optional, Union, Deque, Tuple, List
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

    # P1-2 FIX: Spread readiness tracking
    spread_ready: bool = True
    spread_missing: bool = False

    # PRICE-MOTION-V1: Rolling price history for multi-window returns/volatility proxy.
    # Stores (ts_ms, price) in chronological order; pruned by time window in runtime logic.
    price_history: Deque[Tuple[int, decimal.Decimal]] = field(default_factory=deque)
    
    # =========================================================================
    # R1 (P1): MACRO RESID STATE — Beta-Adjusted Residual
    # =========================================================================
    # Rolling returns for beta calculation
    macro_resid_asset_returns: Deque[float] = field(default_factory=deque)
    macro_resid_anchor_returns: Deque[float] = field(default_factory=deque)
    # Residual buffer for MAD calculation
    macro_resid_buffer: Deque[float] = field(default_factory=deque)
    # Readiness
    macro_resid_ready: bool = False
    macro_resid_not_ready_reason: Optional[str] = None
    
    # =========================================================================
    # R2 (P2): ABSORPTION STATE — Experimental (Default OFF)
    # =========================================================================
    # Aggressive trade volumes for proxy calculation
    absorption_buy_vol_buffer: Deque[float] = field(default_factory=deque)
    absorption_sell_vol_buffer: Deque[float] = field(default_factory=deque)
    # TFI buffer for dedup correlation
    absorption_tfi_buffer: Deque[float] = field(default_factory=deque)
    absorption_proxy_buffer: Deque[float] = field(default_factory=deque)
    # Dedup muted status
    absorption_dedup_muted: bool = False
    absorption_dedup_corr: Optional[float] = None
    # Readiness
    absorption_ready: bool = False
    absorption_not_ready_reason: Optional[str] = None


# =============================================================================
# EP-01.1: BAR VOLATILITY STATE (per-timeframe ATR tracking)
# =============================================================================

@dataclass
class BarVolatilityState:
    """
    Per (symbol, tf_sec) state for bar-based volatility features.
    
    EP-01.1: Tracks True Range history for ATR calculation.
    Used to compute bar_range, bar_body, true_range, ATR_N.
    
    This is kept SEPARATE from HotState because it's timeframe-specific,
    while HotState is tick-level (tf_sec=0).
    """
    # ATR window size (configurable, default 14)
    atr_window: int = 14
    
    # Rolling buffer of True Range values
    tr_buffer: Deque[float] = field(default_factory=deque)
    
    # Previous bar's close price for True Range calculation
    prev_close: Optional[decimal.Decimal] = None
    
    # Last computed ATR (None if not enough history)
    last_atr: Optional[float] = None
    
    # Readiness flag
    atr_ready: bool = False
    
    def update_tr(self, true_range: float) -> None:
        """Add new True Range value and update ATR."""
        # Add to buffer, respecting maxlen
        if len(self.tr_buffer) >= self.atr_window:
            self.tr_buffer.popleft()
        self.tr_buffer.append(true_range)
        
        # Calculate ATR if we have enough history
        if len(self.tr_buffer) >= self.atr_window:
            self.last_atr = sum(self.tr_buffer) / len(self.tr_buffer)
            self.atr_ready = True
        else:
            self.last_atr = None
            self.atr_ready = False


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
    def enabled_timeframes_sec(self) -> List[int]:
        return self._cfg.enabled_timeframes_sec
    
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
    def depth_imbalance_use_laplace_smoothing(self) -> bool:
        return bool(self._cfg.depth_imbalance.use_laplace_smoothing)
    
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
    def volume_zscore_clip_sigma(self) -> float:
        return float(self._cfg.volume_zscore.clip_sigma)

    @property
    def large_trade_imbalance_window_ms(self) -> int:
        return int(self._cfg.large_trade_imbalance.window_ms)

    @property
    def large_trade_imbalance_enabled(self) -> bool:
        try:
            return bool(self._cfg.large_trade_imbalance.enabled)
        except Exception:
            return True

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
    
    # =========================================================================
    # P0-1: VOLATILITY HARD FLOOR (config-driven)
    # =========================================================================
    
    @property
    def volatility_tick_floor(self) -> decimal.Decimal:
        """P0-1: Tick floor to prevent division by zero (price units)."""
        try:
            return decimal.Decimal(str(self._cfg.volatility_state.tick_floor))
        except AttributeError:
            # Backward compat: default if not in config
            return decimal.Decimal("0.0001")
    
    @property
    def volatility_division_eps(self) -> decimal.Decimal:
        """P0-1: Division epsilon for safe division."""
        try:
            return decimal.Decimal(str(self._cfg.volatility_state.division_eps))
        except AttributeError:
            return decimal.Decimal("0.000000001")
    
    # =========================================================================
    # P0-0: READINESS REGISTRY (SSOT)
    # =========================================================================
    
    @property
    def readiness_registry_declared_keys(self) -> list:
        """P0-0: Declared ready keys that FE can emit in warmup.ready."""
        try:
            if self._cfg.readiness_registry:
                return list(self._cfg.readiness_registry.declared_keys)
        except AttributeError:
            pass
        # Default for backward compat
        return [
            "obi", "tfi", "delta_price", "depth_imbalance", "liquidity_kappa",
            "absorption", "ema_bias", "volume_spike", "volatility_state",
            "macro_sync", "spread_bps", "large_trade_imbalance", "volume_zscore"
        ]
    
    @property 
    def warmup_enforcement_mode(self) -> str:
        """P0-0: Warmup enforcement mode (fail_fast|warn_only|disabled)."""
        try:
            if self._cfg.warmup:
                return str(self._cfg.warmup.enforcement_mode)
        except AttributeError:
            pass
        return "fail_fast"  # Default: fail-closed
    
    @property
    def warmup_check_full_ready_invariant(self) -> bool:
        """P0-0: Check full_ready invariant (all declared keys present)."""
        try:
            if self._cfg.warmup:
                return bool(self._cfg.warmup.check_full_ready_invariant)
        except AttributeError:
            pass
        return True  # Default: enabled

    def compute_warmup_full_ready(self, ready_map: dict) -> bool:
        """
        Compute warmup.full_ready in a config-aware way.

        Contract:
        - Missing keys are treated as NOT ready (fail-closed).
        - Features that are configured OFF are excluded from the "full_ready" requirement.
          (e.g. absorption.mode=disabled should not block live readiness.)
        """
        return self.compute_warmup_full_ready_for_symbol(symbol="__default__", ready_map=ready_map)

    def compute_warmup_full_ready_for_symbol(self, *, symbol: str, ready_map: dict) -> bool:
        """
        Compute warmup.full_ready with optional required-ready overrides.

        Contract:
        - Fail-closed: missing required keys => not ready.
        - If `warmup.required_ready_keys_by_symbol[symbol]` is set => only those keys are required.
        - Else if `warmup.required_ready_keys` is set => only those keys are required.
        - Else => require all declared_keys (minus configured-off features).
        """
        if not isinstance(ready_map, dict):
            return False

        declared_keys = self.readiness_registry_declared_keys
        if not isinstance(declared_keys, list) or not declared_keys:
            return False

        override_keys: list[str] | None = None
        try:
            warmup_cfg = getattr(self._cfg, "warmup", None)
            by_symbol = getattr(warmup_cfg, "required_ready_keys_by_symbol", None) if warmup_cfg is not None else None
            if isinstance(by_symbol, dict) and symbol in by_symbol and isinstance(by_symbol[symbol], list):
                override_keys = [str(k) for k in by_symbol[symbol]]
            else:
                global_keys = getattr(warmup_cfg, "required_ready_keys", None) if warmup_cfg is not None else None
                if isinstance(global_keys, list):
                    override_keys = [str(k) for k in global_keys]
        except Exception:
            override_keys = None

        base_keys = override_keys if override_keys else [str(k) for k in declared_keys]

        required_keys: list[str] = []
        declared_set = set(str(k) for k in declared_keys)
        for key in base_keys:
            if key not in declared_set:
                return False
            if key == "absorption" and self.absorption_mode == "disabled":
                continue
            if key == "macro_resid" and (not bool(self.macro_resid_enabled)):
                continue
            if key == "macro_sync" and (not bool(self.macro_sync_enabled)):
                continue
            if key == "large_trade_imbalance" and (not bool(self.large_trade_imbalance_enabled)):
                continue
            required_keys.append(str(key))

        for key in required_keys:
            if key not in ready_map:
                return False
            if not bool(ready_map[key]):
                return False

        return True
    
    # =========================================================================
    # P0-2: SPREAD BPS HEALTH GATE
    # =========================================================================
    
    @property
    def spread_health_gate_enabled(self) -> bool:
        """P0-2: Whether spread health gate is enabled."""
        try:
            if self._cfg.spread_bps and self._cfg.spread_bps.health_gate:
                return bool(self._cfg.spread_bps.health_gate.enabled)
        except AttributeError:
            pass
        return False  # Default: off for backward compat
    
    @property
    def spread_health_max_age_sec(self) -> float:
        """P0-2: Max age before book is considered stale (seconds)."""
        try:
            if self._cfg.spread_bps and self._cfg.spread_bps.health_gate:
                return float(self._cfg.spread_bps.health_gate.max_age_sec)
        except AttributeError:
            pass
        return 5.0
    
    @property
    def spread_health_min_update_events(self) -> int:
        """P0-2: Min book update events for healthy status."""
        try:
            if self._cfg.spread_bps and self._cfg.spread_bps.health_gate:
                return int(self._cfg.spread_bps.health_gate.min_update_events)
        except AttributeError:
            pass
        return 1
    
    @property
    def spread_health_min_trades_count(self) -> int:
        """P0-2: Min trades in window for healthy status."""
        try:
            if self._cfg.spread_bps and self._cfg.spread_bps.health_gate:
                return int(self._cfg.spread_bps.health_gate.min_trades_count)
        except AttributeError:
            pass
        return 1
    
    @property
    def spread_health_window_sec(self) -> float:
        """P0-2: Lookback window for health check (seconds)."""
        try:
            if self._cfg.spread_bps and self._cfg.spread_bps.health_gate:
                return float(self._cfg.spread_bps.health_gate.window_sec)
        except AttributeError:
            pass
        return 10.0
    
    # =========================================================================
    # P0-3: FEATURE SANITY FIREWALL
    # =========================================================================
    
    @property
    def feature_sanity_enabled(self) -> bool:
        """P0-3: Whether feature sanity firewall is enabled."""
        try:
            if self._cfg.feature_sanity:
                return bool(self._cfg.feature_sanity.enabled)
        except AttributeError:
            pass
        return False  # Default: off for backward compat
    
    @property
    def feature_sanity_nan_inf_behavior(self) -> str:
        """P0-3: Behavior on NaN/Inf (neutral_and_not_ready|neutral_only|crash)."""
        try:
            if self._cfg.feature_sanity:
                return str(self._cfg.feature_sanity.nan_inf_behavior)
        except AttributeError:
            pass
        return "neutral_and_not_ready"
    
    @property
    def feature_sanity_bounds(self) -> dict:
        """P0-3: Feature bounds for validation."""
        try:
            if self._cfg.feature_sanity and self._cfg.feature_sanity.feature_bounds:
                return {
                    k: {"min": v.min, "max": v.max}
                    for k, v in self._cfg.feature_sanity.feature_bounds.items()
                }
        except AttributeError:
            pass
        return {}
    
    # =========================================================================
    # R1 (P1): MACRO RESID — Beta-Adjusted Residual
    # =========================================================================
    
    @property
    def macro_resid_enabled(self) -> bool:
        """R1: Whether macro_resid is enabled."""
        try:
            if self._cfg.macro_resid:
                return bool(self._cfg.macro_resid.enabled)
        except AttributeError:
            pass
        return False  # Default: off for backward compat
    
    @property
    def macro_resid_beta_window(self) -> int:
        """R1: Beta estimation window (samples)."""
        try:
            if self._cfg.macro_resid:
                return int(self._cfg.macro_resid.beta_window)
        except AttributeError:
            pass
        return 60
    
    @property
    def macro_resid_mad_window(self) -> int:
        """R1: MAD calculation window (samples)."""
        try:
            if self._cfg.macro_resid:
                return int(self._cfg.macro_resid.mad_window)
        except AttributeError:
            pass
        return 30
    
    @property
    def macro_resid_winsor_percentile(self) -> float:
        """R1: Winsorize percentile (e.g., 0.05 = 5%)."""
        try:
            if self._cfg.macro_resid:
                return float(self._cfg.macro_resid.winsor_percentile)
        except AttributeError:
            pass
        return 0.05
    
    @property
    def macro_resid_var_floor(self) -> float:
        """R1: Floor for var(r_btc) to prevent div-by-zero."""
        try:
            if self._cfg.macro_resid:
                return float(self._cfg.macro_resid.var_floor)
        except AttributeError:
            pass
        return 1e-7
    
    @property
    def macro_resid_scale_floor(self) -> float:
        """R1: Floor for MAD scale to prevent explosion."""
        try:
            if self._cfg.macro_resid:
                return float(self._cfg.macro_resid.scale_floor)
        except AttributeError:
            pass
        return 1e-4
    
    @property
    def macro_resid_clip(self) -> float:
        """R1: Output clip bound."""
        try:
            if self._cfg.macro_resid:
                return float(self._cfg.macro_resid.clip)
        except AttributeError:
            pass
        return 3.0
    
    @property
    def macro_resid_neutral(self) -> float:
        """R1: Neutral value (SIGNED: 0.0)."""
        try:
            if self._cfg.macro_resid:
                return float(self._cfg.macro_resid.neutral)
        except AttributeError:
            pass
        return 0.0
    
    # =========================================================================
    # R2 (P2): ABSORPTION — Experimental (Default OFF)
    # =========================================================================
    
    @property
    def absorption_mode(self) -> str:
        """R2: Absorption mode (disabled|proxy|full)."""
        try:
            if self._cfg.absorption:
                return str(self._cfg.absorption.mode)
        except AttributeError:
            pass
        return "disabled"
    
    @property
    def absorption_proxy_source(self) -> str:
        """R2: Absorption proxy source."""
        try:
            if self._cfg.absorption and self._cfg.absorption.proxy:
                return str(self._cfg.absorption.proxy.source)
        except AttributeError:
            pass
        return "aggressive_trade_imbalance"
    
    @property
    def absorption_proxy_window(self) -> int:
        """R2: Absorption proxy window (samples)."""
        try:
            if self._cfg.absorption and self._cfg.absorption.proxy:
                return int(self._cfg.absorption.proxy.window)
        except AttributeError:
            pass
        return 30
    
    @property
    def absorption_proxy_eps(self) -> float:
        """R2: Absorption proxy epsilon for division."""
        try:
            if self._cfg.absorption and self._cfg.absorption.proxy:
                return float(self._cfg.absorption.proxy.eps)
        except AttributeError:
            pass
        return 0.0001
    
    @property
    def absorption_dedup_enabled(self) -> bool:
        """R2: Whether dedup guard is enabled."""
        try:
            if self._cfg.absorption and self._cfg.absorption.dedup:
                return bool(self._cfg.absorption.dedup.enabled)
        except AttributeError:
            pass
        return True  # Default: enabled for safety
    
    @property
    def absorption_dedup_window(self) -> int:
        """R2: Dedup correlation window (samples)."""
        try:
            if self._cfg.absorption and self._cfg.absorption.dedup:
                return int(self._cfg.absorption.dedup.window)
        except AttributeError:
            pass
        return 60
    
    @property
    def absorption_dedup_threshold(self) -> float:
        """R2: Dedup threshold (|corr| > threshold → mute)."""
        try:
            if self._cfg.absorption and self._cfg.absorption.dedup:
                return float(self._cfg.absorption.dedup.threshold)
        except AttributeError:
            pass
        return 0.8
    
    @property
    def absorption_clip(self) -> float:
        """R2: Absorption output clip."""
        try:
            if self._cfg.absorption:
                return float(self._cfg.absorption.clip)
        except AttributeError:
            pass
        return 1.0
    
    @property
    def absorption_neutral(self) -> float:
        """R2: Absorption neutral value (SIGNED: 0.0)."""
        try:
            if self._cfg.absorption:
                return float(self._cfg.absorption.neutral)
        except AttributeError:
            pass
        return 0.0
    
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
    def macro_sync_max_late_ms(self) -> int:
        try:
            return int(self._cfg.macro_sync.max_late_ms)
        except Exception:
            return 0

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
