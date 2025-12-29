"""
Typed Configuration Models for Execution Position Domain (SSOT)

RID: EP-CONFIG-SSOT-S1

Purpose:
- Single Source of Truth (SSOT) for execution_position config (aggregated_oco, trailing, close)
- Pydantic-based validation with Field constraints (gt=0, ge=0, etc.)
- Replaces raw dict access with typed models

Design Principles:
- Defaults match current behavior in manage_config.py (dataclass defaults)
- Validation catches invalid configs early (before runtime)
- Compatible with YAML config structure (config/domains/execution.yaml)
- Does NOT modify runtime code (BracketService, OrderGuardian, ExecPosRuntimeV2)

Migration Path:
- PHASE 1: Define models + resolver (this file + config_loader.py)
- PHASE 2: Integrate into ExecPosRuntimeV2 (separate task, after EP-OCO-V2-WIRING-S1)
- PHASE 3: Deprecate manage_config.py dataclasses (gradual migration)

Usage Example:
    from apps.reference.domains.execution_position.config import ExecutionPositionConfig
    from apps.reference.config import resolve_execution_position_config

    raw_cfg = yaml.safe_load(...)
    ep_cfg = resolve_execution_position_config(raw_cfg)

    # Type-safe access
    sl_pct = ep_cfg.aggregated_oco.sl_pct  # float, validated > 0
    tp_rr = ep_cfg.aggregated_oco.tp_rr    # float, validated > 0
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List


# ============================================================================
# Aggregated OCO Configuration
# ============================================================================

class AggregatedOcoWatchdogGraceConfig(BaseModel):
    """
    Grace period config for watchdog violations.

    Allows temporary violations (e.g., SL missing for 2 seconds after entry)
    before raising ALERT severity.
    """
    enabled: bool = False
    period_sec: float = Field(default=0.0, ge=0.0)
    kinds: List[str] = Field(default_factory=list)

    class Config:
        frozen = True  # Immutable


class AggregatedOcoWatchdogConfig(BaseModel):
    """
    Watchdog config for bracket set violations (MISSING_SL, ORPHAN_SL, etc.).

    Maps to YAML: config.domains.execution.manage.brackets.aggregated_oco.watchdog
    """
    enabled: bool = False
    interval_sec: int = Field(default=5, ge=1)
    auto_heal_orphans: bool = True
    grace: AggregatedOcoWatchdogGraceConfig = Field(
        default_factory=AggregatedOcoWatchdogGraceConfig
    )

    class Config:
        frozen = True


class AggregatedOcoConfig(BaseModel):
    """
    Aggregated OCO (One-Cancels-Other) configuration for bracket management.

    Maps to YAML: config.domains.execution.manage.brackets.aggregated_oco

    Key Fields:
        enabled: Master switch for aggregated OCO management
        aggregated_only_mode: Force clean entry/exit (no inline TP/SL)
        sl_pct: Stop-loss distance as % of entry price (e.g., 0.02 = 2%)
        tp_rr: Take-profit reward/risk ratio (e.g., 2.0 = 2:1)
        recalc_on_scale_in: Rebuild brackets when position grows
        recalc_on_partial_close: Rebuild brackets when position shrinks
        ttl_protect_new_bracket_ms: TTL to protect new brackets from cleanup
        allow_unprotected_position: Allow positions without SL (strict mode if False)
        max_sl_legs: Max number of SL orders per position (default 1)
        max_tp_legs: Max number of TP orders per position (default 1)
        bracket_throttle_sec: Min seconds between bracket evals per symbol (default 2.0)
        bracket_suppression_sec: Extended throttle after bracket actions (default 10.0)

    Validation:
        - sl_pct must be > 0
        - tp_rr must be > 0
        - max_sl_legs must be >= 1
        - max_tp_legs must be >= 1
        - ttl_protect_new_bracket_ms must be >= 0
        - bracket_throttle_sec must be >= 0.5
        - bracket_suppression_sec must be >= 1.0

    Defaults:
        Match current behavior in manage_config.py:
        - sl_pct: 0.02 (2%)
        - tp_rr: 2.0 (2:1)
        - recalc_on_scale_in: True
        - recalc_on_partial_close: False
        - ttl_protect_new_bracket_ms: 3000 (3 seconds)
        - allow_unprotected_position: False
        - max_sl_legs: 1
        - max_tp_legs: 1
        - bracket_throttle_sec: 2.0 (fast for scalping)
        - bracket_suppression_sec: 10.0 (anti-churn)
    """
    enabled: bool = False
    aggregated_only_mode: bool = False
    sl_pct: float = Field(
        default=0.02, gt=0.0, description="Stop-loss distance as % of entry (e.g., 0.02 = 2%)")
    tp_rr: float = Field(
        default=2.0, gt=0.0, description="Take-profit reward/risk ratio (e.g., 2.0 = 2:1)")
    sl_roi_pct: float = Field(
        default=35.0, ge=0.0, description="ROI-based SL % on margin (e.g., 35 = 35%)")
    tp_roi_pct: float = Field(
        default=50.0, ge=0.0, description="ROI-based TP % on margin (e.g., 50 = 50%)")
    roi_basis: str = Field(
        default="margin", description="ROI basis for SL/TP calculations (margin or equity)")
    leverage_source: str = Field(
        default="instrument_max", description="Source for leverage used in ROI sizing")
    recalc_on_scale_in: bool = True
    recalc_on_partial_close: bool = False
    ttl_protect_new_bracket_ms: int = Field(default=3000, ge=0)
    allow_unprotected_position: bool = False
    max_sl_legs: int = Field(default=1, ge=1)
    max_tp_legs: int = Field(default=1, ge=1)
    recreate_missing_brackets: bool = Field(
        default=True, description="Recreate SL/TP if missing during open position (fail-closed)")
    # Phase 5: Configurable throttling (faster defaults for scalping)
    bracket_throttle_sec: float = Field(
        default=2.0, ge=0.5, description="Min seconds between bracket evals per symbol")
    bracket_suppression_sec: float = Field(
        default=10.0, ge=1.0, description="Extended throttle after bracket actions (anti-churn)")
    watchdog: AggregatedOcoWatchdogConfig = Field(
        default_factory=AggregatedOcoWatchdogConfig
    )

    class Config:
        frozen = True

    @validator("sl_pct")
    def validate_sl_pct(cls, v):
        """Ensure sl_pct is reasonable (not > 100%)"""
        if v > 1.0:
            raise ValueError(
                f"sl_pct={v} is > 100%, likely a config error (use 0.02 for 2%, not 2.0)")
        return v

    @validator("tp_rr")
    def validate_tp_rr(cls, v):
        """Ensure tp_rr is reasonable (not < 0.1 or > 100)"""
        if v < 0.1:
            raise ValueError(
                f"tp_rr={v} is too small (< 0.1), likely a config error")
        if v > 100.0:
            raise ValueError(
                f"tp_rr={v} is too large (> 100), likely a config error")
        return v


# ============================================================================
# Trailing Configuration
# ============================================================================

class TrailingConfig(BaseModel):
    """
    Trailing stop configuration (move SL up/down as price advances).

    Maps to YAML: config.domains.execution.manage.trailing

    Key Fields:
        enabled: Master switch for trailing logic
        trail_distance_bps: Move SL when price advances this many bps from watermark
        activate_after_bps: Optional activation threshold (0 = immediate)
        breakeven_rr: Move SL to entry after reward/risk multiple (0 = disabled)
        hard_time_exit_sec: Force exit after this many seconds (None = disabled)

    Validation:
        - trail_distance_bps must be >= 0
        - activate_after_bps must be >= 0
        - breakeven_rr must be >= 0
        - hard_time_exit_sec must be >= 0 if set

    Defaults:
        Match current behavior in manage_config.py and shadow_execpos/trailing.py:
        - enabled: False
        - trail_distance_bps: 100.0
        - activate_after_bps: 0.0
        - breakeven_rr: 0.0
        - hard_time_exit_sec: None
    """
    enabled: bool = False
    trail_distance_bps: float = Field(
        default=100.0, ge=0.0, description="Move SL when price advances this many bps")
    activate_after_bps: float = Field(
        default=0.0, ge=0.0, description="Activation threshold (0 = immediate)")
    breakeven_rr: float = Field(
        default=0.0, ge=0.0, description="Move SL to entry after R:R multiple (0 = disabled)")
    hard_time_exit_sec: Optional[float] = Field(
        default=None, ge=0.0, description="Force exit after seconds (None = disabled)")

    # Additional fields from manage_config.py TrailingConfig
    activation_profit_atr_k: float = Field(
        default=1.0, ge=0.0, description="Activation profit multiplier (legacy)")
    cooldown_sec: float = Field(
        default=0.0, ge=0.0, description="Cooldown between trailing updates")
    step_bps: float = Field(
        default=0.0, ge=0.0, description="Step size for SL updates (0 = no step)")

    class Config:
        frozen = True

    @validator("trail_distance_bps")
    def validate_trail_distance(cls, v):
        """Warn if trail_distance is too small (< 10 bps)"""
        if v > 0 and v < 10.0:
            # Allow but warn
            pass  # Could add logging here if needed
        return v


# ============================================================================
# Snapshot Configuration
# ============================================================================

class SnapshotConfig(BaseModel):
    """
    Freshness/TTL configuration for position/order snapshots inside ExecPosRuntimeV2.

    Controls how long cached snapshots are considered valid before bracket evaluation.
    """
    orders_ttl_sec: float = Field(default=10.0, gt=0.0)
    position_ttl_sec: float = Field(default=10.0, gt=0.0)

    class Config:
        frozen = True


# ============================================================================
# Close Configuration
# ============================================================================

class CloseConfig(BaseModel):
    """
    Position close configuration (max hold time, time-based exits).

    Maps to YAML: config.domains.execution.manage.close (if exists)

    Key Fields:
        max_hold_time_sec: Force close after this many seconds (0 = disabled)
        allow_time_exit: Allow time-based exits (hard_time_exit from trailing)

    Validation:
        - max_hold_time_sec must be >= 0

    Defaults:
        - max_hold_time_sec: 0 (disabled)
        - allow_time_exit: True
    """
    max_hold_time_sec: int = Field(
        default=0, ge=0, description="Force close after seconds (0 = disabled)")
    allow_time_exit: bool = Field(
        default=True, description="Allow time-based exits")

    class Config:
        frozen = True


# ============================================================================
# Execution Position Configuration (Root)
# ============================================================================

class ExecutionPositionConfig(BaseModel):
    """
    Root configuration for execution_position domain (SSOT).

    Aggregates:
        - aggregated_oco: Bracket management config
        - trailing: Trailing stop config
        - close: Position close config
        - snapshot: Snapshot freshness/TTL config

    Usage:
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(sl_pct=0.02, tp_rr=2.0),
            trailing=TrailingConfig(trail_distance_bps=100.0),
            close=CloseConfig(max_hold_time_sec=3600),
            snapshot=SnapshotConfig(orders_ttl_sec=10, position_ttl_sec=10),
        )

        # Type-safe access
        sl_pct = ep_cfg.aggregated_oco.sl_pct  # float
        enabled = ep_cfg.trailing.enabled       # bool

    Validation:
        - All nested configs are validated (see AggregatedOcoConfig, TrailingConfig, CloseConfig)
        - Pydantic raises ValidationError on invalid values

    Immutability:
        - All configs are frozen (Config.frozen = True)
        - No runtime mutation allowed (config changes require reload)
    """
    aggregated_oco: AggregatedOcoConfig
    trailing: TrailingConfig
    close: CloseConfig
    snapshot: SnapshotConfig = Field(default_factory=SnapshotConfig)

    class Config:
        frozen = True


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    # Root config
    "ExecutionPositionConfig",

    # Aggregated OCO
    "AggregatedOcoConfig",
    "AggregatedOcoWatchdogConfig",
    "AggregatedOcoWatchdogGraceConfig",

    # Trailing
    "TrailingConfig",

    # Snapshot
    "SnapshotConfig",

    # Close
    "CloseConfig",
]
