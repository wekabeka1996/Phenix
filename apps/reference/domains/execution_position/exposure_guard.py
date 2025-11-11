"""
EXP-FIX: Exposure Guard with Portfolio Notional Hard Gate.

Implements fail-closed behavior when portfolio positions are stale/unknown,
and post-fill hold mechanism to prevent race conditions.
PHASE 2: Soft-limit clipping (clip instead of reject, min notional check).
"""

from __future__ import annotations

import time
import logging
import asyncio
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.soft_clip import SoftClipEngine as SoftClipEngineImpl
from apps.reference.domains.execution_position.metrics_aggregator import metrics_logger


@dataclass
class SoftLimitConfig:
    """Soft-limit clipping configuration (PHASE 2)."""
    mode: str = "clip"                      # "clip" or "reject"
    clip_min_notional_usdt: Decimal = Decimal("10")
    directional_ratio_max: Decimal = Decimal("3.0")
    side_exposure_usdt: Decimal = Decimal("600")
    margin_exposure_usdt: Decimal = Decimal("1100")


@dataclass
class ClipResult:
    """Result of soft-limit clipping logic (PHASE 2)."""
    allowed: bool
    reason: str
    clipped_notional: Optional[Decimal] = None
    original_notional: Optional[Decimal] = None
    clip_reasons: List[str] = None

    def __post_init__(self):
        if self.clip_reasons is None:
            self.clip_reasons = []


@dataclass
class ExposureState:
    """Data class for exposure state management."""

    reservations: Dict[str, Decimal]  # key -> notional_usd
    reservations_ts: Dict[str, float]  # key -> timestamp
    # key -> {notional, ts, reduce_only}
    pending_exposure: Dict[str, Dict[str, Any]]
    postfill_reservations: Dict[
        str, Dict[str, Any]
    ]  # key -> {'notional': Decimal, 'exp_ts': float}


@dataclass
class FallbackState:
    """PHASE P0: Fallback mode state management."""
    active: bool = False
    entered_at: Optional[float] = None
    reason: Optional[str] = None
    # 50% risk reduction in fallback mode
    risk_reduction_pct: Decimal = Decimal("0.5")


class ExposureGuard:
    """
    Exposure Guard with hard portfolio notional gate.

    Features:
    - Fail-closed when positions are stale/unknown
    - Post-fill hold to prevent FILL→portfolio race conditions
    - Shadow notional validation for safety
    """

    def __init__(self, config: Dict[str, Any], fsm: Optional[Any] = None):
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        self.fsm = fsm  # Store FSM reference for event emission

        # Configuration: Pydantic-first with fallback for backward compatibility
        try:
            if hasattr(config, 'trading') and config.trading and hasattr(config.trading, 'execution') and config.trading.execution and hasattr(config.trading.execution, 'exposure') and config.trading.execution.exposure:
                exposure_config = config.trading.execution.exposure
            elif isinstance(config, dict):
                exposure_config = config.get("trading", {}).get(
                    "execution", {}).get("exposure", {})
            else:
                exposure_config = {}
        except (AttributeError, TypeError):
            exposure_config = {}

        # EXP-LEVERAGE-001: New margin-based limit (backward compatible)
        try:
            if hasattr(exposure_config, 'max_equity_utilization_pct'):
                max_eq_util = exposure_config.max_equity_utilization_pct or "0.20"
            else:
                max_eq_util = getattr(
                    exposure_config, "max_equity_utilization_pct", "0.20")
        except (AttributeError, TypeError):
            max_eq_util = "0.20"
        self.max_equity_utilization_pct = Decimal(str(max_eq_util))

        # Legacy field for backward compatibility
        try:
            if hasattr(exposure_config, 'max_portfolio_fraction'):
                max_port_frac = exposure_config.max_portfolio_fraction or "0.20"
            elif isinstance(exposure_config, dict):
                max_port_frac = exposure_config.get(
                    'max_portfolio_fraction', "0.20")
            else:
                max_port_frac = "0.20"
        except (AttributeError, TypeError):
            max_port_frac = "0.20"
        self.max_portfolio_fraction = Decimal(str(max_port_frac))

        # EXP-DIRECTION: Per-side utilization limits
        try:
            if hasattr(exposure_config, 'max_side_utilization_pct'):
                side_config = exposure_config.max_side_utilization_pct or {}
            elif isinstance(exposure_config, dict):
                side_config = exposure_config.get(
                    'max_side_utilization_pct', {})
            else:
                side_config = {}
        except (AttributeError, TypeError):
            side_config = {}

        try:
            if isinstance(side_config, dict):
                long_pct = side_config.get('long', "0.12")
            elif hasattr(side_config, 'long'):
                long_pct = side_config.long or "0.12"
            else:
                long_pct = "0.12"
        except (AttributeError, TypeError):
            long_pct = "0.12"
        self.max_long_utilization_pct = Decimal(str(long_pct))

        try:
            if isinstance(side_config, dict):
                short_pct = side_config.get('short', "0.12")
            elif hasattr(side_config, 'short'):
                short_pct = side_config.short or "0.12"
            else:
                short_pct = "0.12"
        except (AttributeError, TypeError):
            short_pct = "0.12"
        self.max_short_utilization_pct = Decimal(str(short_pct))

        # EXP-DIRECTION: Directional imbalance control
        try:
            if hasattr(exposure_config, 'max_directional_ratio'):
                max_dir_ratio = exposure_config.max_directional_ratio or "2.0"
            elif isinstance(exposure_config, dict):
                max_dir_ratio = exposure_config.get(
                    'max_directional_ratio', "2.0")
            else:
                max_dir_ratio = "2.0"
        except (AttributeError, TypeError):
            max_dir_ratio = "2.0"
        self.max_directional_ratio = Decimal(str(max_dir_ratio))

        # EXP-CONCENTRATION: Per-symbol cap
        try:
            if hasattr(exposure_config, 'per_symbol_cap_pct'):
                per_sym_cap = exposure_config.per_symbol_cap_pct or "0.08"
            elif isinstance(exposure_config, dict):
                per_sym_cap = self.config.trading.exposure.per_symbol_cap_pct
            else:
                per_sym_cap = "0.08"
        except (AttributeError, TypeError):
            per_sym_cap = "0.08"
        self.per_symbol_cap_pct = Decimal(str(per_sym_cap))

        # TTL configurations
        try:
            if hasattr(exposure_config, 'pending_ttl_sec'):
                pending_ttl = exposure_config.pending_ttl_sec or 90
            elif isinstance(exposure_config, dict):
                pending_ttl = self.config.trading.exposure.pending_ttl_sec
            else:
                pending_ttl = 90
        except (AttributeError, TypeError):
            pending_ttl = 90
        self.pending_ttl_sec = pending_ttl

        try:
            if hasattr(exposure_config, 'post_fill_hold_ttl_sec'):
                post_fill_ttl = exposure_config.post_fill_hold_ttl_sec or 5
            elif isinstance(exposure_config, dict):
                post_fill_ttl = exposure_config.get(
                    'post_fill_hold_ttl_sec', 5)
            else:
                post_fill_ttl = 5
        except (AttributeError, TypeError):
            post_fill_ttl = 5
        self.post_fill_hold_ttl_sec = int(post_fill_ttl)

        try:
            if hasattr(exposure_config, 'positions_stale_ttl_sec'):
                stale_ttl = exposure_config.positions_stale_ttl_sec or 5
            elif isinstance(exposure_config, dict):
                stale_ttl = self.config.trading.exposure.positions_stale_ttl_sec
            else:
                stale_ttl = 5
        except (AttributeError, TypeError):
            stale_ttl = 5
        self.positions_stale_ttl_sec = stale_ttl

        # count_pending_orders flag
        try:
            if hasattr(exposure_config, 'count_pending_orders'):
                count_pending = exposure_config.count_pending_orders
            elif isinstance(exposure_config, dict):
                count_pending = exposure_config.get(
                    'count_pending_orders', True)
            else:
                count_pending = True
        except (AttributeError, TypeError):
            count_pending = True
        self.count_pending_orders = count_pending

        # exclude_reduce_only flag
        try:
            if hasattr(exposure_config, 'exclude_reduce_only'):
                exclude_ro = exposure_config.exclude_reduce_only
            elif isinstance(exposure_config, dict):
                exclude_ro = exposure_config.get('exclude_reduce_only', True)
            else:
                exclude_ro = True
        except (AttributeError, TypeError):
            exclude_ro = True
        self.exclude_reduce_only = exclude_ro

        # PHASE 2: Soft-limit configuration (read from trading.risk.soft_limits)
        self.soft_limit_config = self._load_soft_limit_config()
        self.soft_clip_engine = SoftClipEngineImpl(
            self.soft_limit_config, logger=self.logger
        )

        # PHASE P0: Fallback mode configuration and state
        self.fallback_config = self._load_fallback_config()
        self.fallback_state = FallbackState()

        # State
        self.state = ExposureState(
            reservations={},
            reservations_ts={},
            pending_exposure={},
            postfill_reservations={},
        )

        # 🧹 STARTUP: Log initial state (for debugging)
        self.logger.info(
            f"🆕 ExposureGuard initialized: pending_exposure=empty, postfill=empty"
        )

        # Metrics
        self.metrics: Dict[str, Any] = {
            "exposure_fail_closed_total": {},
            "postfill_hold_active": 0,
            "postfill_hold_expired_total": 0,
            "exposure_mismatch_total": 0,
            "clip_total": 0,  # PHASE 2
            "clip_notional_total": Decimal("0"),  # PHASE 2
            # PHASE P0: Fallback mode metrics
            "fallback_mode_entries_total": 0,
            "fallback_blocks_total": 0,
            "fallback_duration_ms_total": 0,
        }

    def _load_soft_limit_config(self) -> SoftLimitConfig:
        """
        Load soft-limit clipping configuration (PHASE 2).
        Reads from trading.risk.soft_limits with fallbacks.
        """
        try:
            if hasattr(self.config, 'trading') and hasattr(self.config.trading, 'risk') and hasattr(self.config.trading.risk, 'soft_limits'):
                soft_limits_dict = self.config.trading.risk.soft_limits or {}
            elif isinstance(self.config, dict):
                soft_limits_dict = self.config.get("trading", {}).get(
                    "risk", {}).get("soft_limits", {})
            else:
                soft_limits_dict = {}
        except (AttributeError, TypeError):
            soft_limits_dict = {}

        # Parse values with defaults
        mode = soft_limits_dict.get("mode", "clip") if isinstance(
            soft_limits_dict, dict) else getattr(soft_limits_dict, "mode", "clip")
        clip_min = Decimal(str(soft_limits_dict.get("clip_min_notional_usdt", "10") if isinstance(
            soft_limits_dict, dict) else getattr(soft_limits_dict, "clip_min_notional_usdt", "10")))
        dir_ratio = Decimal(str(soft_limits_dict.get("directional_ratio_max", "3.0") if isinstance(
            soft_limits_dict, dict) else getattr(soft_limits_dict, "directional_ratio_max", "3.0")))
        side_exp = Decimal(str(soft_limits_dict.get("side_exposure_usdt", "600") if isinstance(
            soft_limits_dict, dict) else getattr(soft_limits_dict, "side_exposure_usdt", "600")))
        margin_exp = Decimal(str(soft_limits_dict.get("margin_exposure_usdt", "1100") if isinstance(
            soft_limits_dict, dict) else getattr(soft_limits_dict, "margin_exposure_usdt", "1100")))

        config = SoftLimitConfig(
            mode=mode,
            clip_min_notional_usdt=clip_min,
            directional_ratio_max=dir_ratio,
            side_exposure_usdt=side_exp,
            margin_exposure_usdt=margin_exp,
        )
        self.logger.info(
            f"SOFT_LIMIT_CONFIG loaded: mode={mode}, "
            f"clip_min={clip_min}, dir_ratio_max={dir_ratio}, "
            f"side_exp={side_exp}, margin_exp={margin_exp}"
        )
        return config

    def _load_fallback_config(self) -> Dict[str, Any]:
        """
        PHASE P0: Load fallback mode configuration.
        Reads from trading.execution.fallback with fallbacks.
        """
        try:
            if hasattr(self.config, 'trading') and hasattr(self.config.trading, 'execution') and hasattr(self.config.trading.execution, 'fallback'):
                fallback_config = self.config.trading.execution.fallback or {}
            elif isinstance(self.config, dict):
                fallback_config = self.config.get("trading", {}).get(
                    "execution", {}).get("fallback", {})
            else:
                fallback_config = {}
        except (AttributeError, TypeError):
            fallback_config = {}

        # Parse configuration with defaults
        policy = fallback_config.get("policy", "fail_closed") if isinstance(
            fallback_config, dict) else getattr(fallback_config, "policy", "fail_closed")
        risk_reduction_pct = Decimal(str(fallback_config.get("risk_reduction_pct", "0.5") if isinstance(
            fallback_config, dict) else getattr(fallback_config, "risk_reduction_pct", "0.5")))
        backoff_ms = fallback_config.get("backoff_ms", [200, 500, 1000]) if isinstance(
            fallback_config, dict) else getattr(fallback_config, "backoff_ms", [200, 500, 1000])

        config = {
            "policy": policy,
            "risk_reduction_pct": risk_reduction_pct,
            "backoff_ms": backoff_ms,
        }
        self.logger.info(
            f"FALLBACK_CONFIG loaded: policy={policy}, risk_reduction_pct={risk_reduction_pct}, backoff_ms={backoff_ms}"
        )
        return config

    def enter_fallback_mode(self, reason: str) -> None:
        """
        PHASE P0: Enter fallback mode with specified reason.

        Args:
            reason: Reason for entering fallback mode (e.g., "API_TIMEOUT", "EMPTY_POSITIONS")
        """
        now_ms = int(time.time() * 1000)

        if self.fallback_state.active:
            self.logger.warning(
                f"FALLBACK_MODE_ALREADY_ACTIVE: reason={reason}, current_reason={self.fallback_state.reason}"
            )
            return

        # Enter fallback mode
        self.fallback_state.active = True
        self.fallback_state.reason = reason
        self.fallback_state.entered_at = now_ms

        # Increment metrics
        self._increment_metric("fallback_mode_entries_total", reason)

        self.logger.warning(
            f"FALLBACK_MODE_ENTERED: reason={reason}, policy={self.fallback_config['policy']}, "
            f"risk_reduction_pct={self.fallback_config['risk_reduction_pct']}"
        )

        # Emit alert event
        if self.fsm:
            from vfoundation.core.protocol import Message
            from vfoundation.core.fsm_emit_compat import emit_compat
            import asyncio

            msg = Message(
                op="EVT",
                verb="FALLBACK_MODE_ENTERED",
                src="execution_position",
                dst="*",
                pld={
                    "reason": reason,
                    "policy": self.fallback_config["policy"],
                    "risk_reduction_pct": float(self.fallback_config["risk_reduction_pct"]),
                    "entered_at_ms": now_ms
                },
                why="fallback_mode_entered",
            )
            self._safe_create_task(emit_compat(
                self.fsm, msg, logger=self.logger))

        # Alert manager notification
        try:
            from vfoundation.core.alert_manager import AlertManager
            alert_mgr = AlertManager.get_instance()
            alert_mgr.alert(
                level="WARNING",
                title="Fallback Mode Activated",
                message=f"ExposureGuard entered fallback mode: {reason}",
                source="ExposureGuard",
                metadata={
                    "reason": reason,
                    "policy": self.fallback_config["policy"],
                    "risk_reduction_pct": float(self.fallback_config["risk_reduction_pct"])
                }
            )
        except Exception as e:
            self.logger.error(
                f"ALERT_MANAGER_ERROR: Failed to send fallback alert - {e}")

    def exit_fallback_mode(self) -> None:
        """
        PHASE P0: Exit fallback mode and resume normal operation.
        """
        if not self.fallback_state.active:
            self.logger.debug("FALLBACK_MODE_NOT_ACTIVE: No action needed")
            return

        # Calculate duration
        now_ms = int(time.time() * 1000)
        duration_ms = now_ms - self.fallback_state.entered_at

        # Update metrics
        self.metrics["fallback_duration_ms_total"] = self.metrics.get(
            "fallback_duration_ms_total", 0) + duration_ms

        reason = self.fallback_state.reason

        # Exit fallback mode
        self.fallback_state.active = False
        self.fallback_state.reason = ""
        self.fallback_state.entered_at = 0

        self.logger.info(
            f"FALLBACK_MODE_EXITED: reason={reason}, duration_ms={duration_ms}"
        )

        # Emit alert event
        if self.fsm:
            from vfoundation.core.protocol import Message
            from vfoundation.core.fsm_emit_compat import emit_compat
            import asyncio

            msg = Message(
                op="EVT",
                verb="FALLBACK_MODE_EXITED",
                src="execution_position",
                dst="*",
                pld={
                    "previous_reason": reason,
                    "duration_ms": duration_ms,
                    "exited_at_ms": now_ms
                },
                why="fallback_mode_exited",
            )
            self._safe_create_task(emit_compat(
                self.fsm, msg, logger=self.logger))

        # Alert manager notification
        try:
            from vfoundation.core.alert_manager import AlertManager
            alert_mgr = AlertManager.get_instance()
            alert_mgr.alert(
                level="INFO",
                title="Fallback Mode Deactivated",
                message=f"ExposureGuard exited fallback mode after {duration_ms}ms",
                source="ExposureGuard",
                metadata={
                    "previous_reason": reason,
                    "duration_ms": duration_ms
                }
            )
        except Exception as e:
            self.logger.error(
                f"ALERT_MANAGER_ERROR: Failed to send exit alert - {e}")

    def is_fallback_mode_active(self) -> bool:
        """
        PHASE P0: Check if fallback mode is currently active.

        Returns:
            bool: True if fallback mode is active
        """
        return self.fallback_state.active

    def resolve_symbol_leverage(self, symbol: str) -> Decimal:
        """
        Resolve leverage for a symbol.

        EXP-LEVERAGE-001: Get leverage from config with fallbacks.

        Args:
            symbol: Trading symbol

        Returns:
            Decimal: Leverage value (>= 1)
        """
        try:
            if hasattr(self.config, 'trading') and self.config.trading:
                exposure_config = self.config.trading.execution.exposure if self.config.trading.execution and self.config.trading.execution else None
            elif isinstance(self.config, dict):
                exposure_config = (
                    self.config.trading.get(
                        "execution", {}).get("exposure", {})
                )
            else:
                exposure_config = None
        except (AttributeError, TypeError):
            exposure_config = None

        if exposure_config is None:
            exposure_config = {}

        # Get leverage defaults with Pydantic-first + fallback
        try:
            if hasattr(exposure_config, 'leverage_defaults'):
                leverage_defaults = exposure_config.leverage_defaults or {}
            elif isinstance(exposure_config, dict):
                leverage_defaults = getattr(
                    self.config.trading.execution.exposure, 'leverage_defaults', {})
            else:
                leverage_defaults = {}
        except (AttributeError, TypeError):
            leverage_defaults = {}

        # Get default leverage with type checking
        try:
            if isinstance(leverage_defaults, dict):
                default_leverage_str = leverage_defaults.get(
                    "__default__", "20")
            elif hasattr(leverage_defaults, '__default__'):
                default_leverage_str = str(
                    leverage_defaults.__default__ or "20")
            else:
                default_leverage_str = "20"
        except (AttributeError, TypeError):
            default_leverage_str = "20"
        default_leverage = Decimal(str(default_leverage_str))

        # Get leverage for this symbol, fallback to default
        try:
            if isinstance(leverage_defaults, dict):
                symbol_leverage_str = leverage_defaults.get(
                    symbol, default_leverage)
            elif hasattr(leverage_defaults, symbol):
                symbol_leverage_str = getattr(
                    leverage_defaults, symbol, default_leverage)
            else:
                symbol_leverage_str = default_leverage
        except (AttributeError, TypeError):
            symbol_leverage_str = default_leverage
        symbol_leverage = Decimal(str(symbol_leverage_str))

        # Ensure leverage >= 1
        return max(symbol_leverage, Decimal("1"))

    def on_portfolio(self, portfolio_state: Dict[str, Any]) -> None:
        """
        Update exposure guard with latest portfolio state.

        EXP-LEVERAGE-001: Store portfolio equity and margin data for exposure checks.

        Args:
            portfolio_state: Latest portfolio state from EVT:PORTFOLIO_STATE_UPDATED
        """
        # DEBUG: Log portfolio state keys and values
        portfolio_keys = list(portfolio_state.keys())
        equity_raw = portfolio_state.get("equity_free_usdt", "MISSING")
        margin_raw = portfolio_state.get(
            "open_positions_margin_usd", "MISSING")
        ts_raw = portfolio_state.get("positions_last_ts_ms", "MISSING")
        self.logger.info(
            f"ON_PORTFOLIO_DEBUG: received portfolio_keys={portfolio_keys}, "
            f"equity_raw={equity_raw}, margin_raw={margin_raw}, ts_raw={ts_raw}"
        )

        # Update stored portfolio data
        self._latest_portfolio_state = portfolio_state

        # Log portfolio update for debugging
        equity_free_usdt = portfolio_state.get("equity_free_usdt", "0")
        open_positions_margin_usd = portfolio_state.get(
            "open_positions_margin_usd", "0")
        positions_last_ts_ms = portfolio_state.get("positions_last_ts_ms", 0)

        self.logger.debug(
            f"PORTFOLIO_UPDATE: equity={equity_free_usdt}, margin_positions={open_positions_margin_usd}, "
            f"ts={positions_last_ts_ms}"
        )

    def can_open(
        self, symbol: str, notional_usd: Decimal, portfolio_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if opening a position is allowed based on exposure limits.

        EXP-FIX: Fail-closed if positions are stale/unknown.

        Args:
            symbol: Trading symbol
            notional_usd: Position notional value in USD
            portfolio_state: Latest portfolio state from EVT:PORTFOLIO_STATE_UPDATED

        Returns:
            Dict with 'allowed': bool and 'reason' if rejected
        """
        now_ms = int(time.time() * 1000)

        # 🧹 CLEANUP: Remove expired postfill_reservations
        now_ts = time.time()
        expired_keys = [
            key for key, item in self.state.postfill_reservations.items()
            if now_ts >= item.get("exp_ts", now_ts)
        ]
        if expired_keys:
            self.logger.warning(
                f"🧹 CLEANUP_POSTFILL: Removing {len(expired_keys)} expired reservations: {expired_keys}"
            )
            for key in expired_keys:
                del self.state.postfill_reservations[key]

        # 🧹 CLEANUP: Remove stale pending_exposure orders (>5s without fill/cancel)
        # Most orders execute/cancel within 1-2s; 5s is generous timeout
        pending_timeout_sec = 5
        stale_pending = []
        for key, item in self.state.pending_exposure.items():
            age_sec = now_ts - item.get("ts", now_ts)
            if age_sec > pending_timeout_sec:
                stale_pending.append((key, age_sec))

        if stale_pending:
            self.logger.error(
                f"🧹 CLEANUP_PENDING: Removing {len(stale_pending)} stale orders (>5s): "
                f"{[(k, f'{a:.1f}s') for k, a in stale_pending]}"
            )
            for key, _ in stale_pending:
                del self.state.pending_exposure[key]

        # DEBUG: Log portfolio state keys and values
        portfolio_keys = list(portfolio_state.keys())
        equity_raw = portfolio_state.get("equity_free_usdt", "MISSING")
        margin_raw = portfolio_state.get(
            "open_positions_margin_usd", "MISSING")
        ts_raw = portfolio_state.get("positions_last_ts_ms", "MISSING")
        self.logger.info(
            f"CAN_OPEN_DEBUG: symbol={symbol}, notional={notional_usd}, "
            f"portfolio_keys={portfolio_keys}, equity_raw={equity_raw}, "
            f"margin_raw={margin_raw}, ts_raw={ts_raw}"
        )

        # Extract portfolio data
        try:
            equity_free_usdt_str = portfolio_state.get("equity_free_usdt", "0")
            open_positions_margin_usd_str = portfolio_state.get(
                "open_positions_margin_usd", "0")
            positions_last_ts_ms = portfolio_state.get(
                "positions_last_ts_ms", 0)

            equity_free_usdt = (
                Decimal(str(equity_free_usdt_str))
                if equity_free_usdt_str
                else Decimal("0")
            )
            open_positions_margin_usd = (
                Decimal(str(open_positions_margin_usd_str))
                if open_positions_margin_usd_str
                else Decimal("0")
            )
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.error(
                f"EXPOSURE_DATA_ERROR: Invalid portfolio data - {e}")
            return {"allowed": False, "reason": "PORTFOLIO_DATA_INVALID"}

        # EXP-FIX: Fail-closed if equity is unknown/zero (timing issue protection)
        if equity_free_usdt == Decimal("0"):
            reason = "EQUITY_UNKNOWN"
            self._increment_metric("exposure_fail_closed_total", reason)
            self.logger.warning(
                f"EXPOSURE_FAIL_CLOSED: {reason} - equity not available yet"
            )
            # Emit event for bridge to monitor
            if self.fsm:
                from vfoundation.core.protocol import Message
                from vfoundation.core.fsm_emit_compat import emit_compat
                import asyncio

                msg = Message(
                    op="EVT",
                    verb="EXPOSURE_FAIL_CLOSED",
                    src="execution_position",
                    dst="*",
                    pld={"reason": reason},
                    why="exposure_fail_closed",
                )
                self._safe_create_task(emit_compat(
                    self.fsm, msg, logger=self.logger))
            return {"allowed": False, "reason": reason}

        # EXP-FIX: Fail-closed if positions are stale or unknown
        if open_positions_margin_usd is None or positions_last_ts_ms == 0:
            reason = "PORTFOLIO_UNKNOWN"
            self._increment_metric("exposure_fail_closed_total", reason)
            self.logger.warning(
                f"EXPOSURE_FAIL_CLOSED: {reason} - no position data available"
            )
            # Emit event for bridge to monitor
            if self.fsm:
                from vfoundation.core.protocol import Message
                from vfoundation.core.fsm_emit_compat import emit_compat
                import asyncio

                msg = Message(
                    op="EVT",
                    verb="EXPOSURE_FAIL_CLOSED",
                    src="execution_position",
                    dst="*",
                    pld={"reason": reason},
                    why="exposure_fail_closed",
                )
                self._safe_create_task(emit_compat(
                    self.fsm, msg, logger=self.logger))
            return {"allowed": False, "reason": reason}

        stale_sec = (now_ms - positions_last_ts_ms) / 1000.0
        if stale_sec > self.positions_stale_ttl_sec:
            reason = "PORTFOLIO_STALE"
            self._increment_metric("exposure_fail_closed_total", reason)
            self.logger.warning(
                f"EXPOSURE_FAIL_CLOSED: {reason} - stale {stale_sec:.1f}s > {self.positions_stale_ttl_sec}s"
            )
            # Emit event for bridge to monitor
            if self.fsm:
                from vfoundation.core.protocol import Message
                from vfoundation.core.fsm_emit_compat import emit_compat
                import asyncio

                msg = Message(
                    op="EVT",
                    verb="EXPOSURE_FAIL_CLOSED",
                    src="execution_position",
                    dst="*",
                    pld={"reason": reason, "stale_sec": stale_sec},
                    why="exposure_fail_closed",
                )
                self._safe_create_task(emit_compat(
                    self.fsm, msg, logger=self.logger))
            return {"allowed": False, "reason": reason, "stale_sec": stale_sec}

        # PHASE P0: Apply fallback mode policy if active
        if self.is_fallback_mode_active():
            policy = self.fallback_config["policy"]
            if policy == "fail_closed":
                reason = f"FALLBACK_FAIL_CLOSED_{self.fallback_state.reason}"
                self._increment_metric("fallback_blocks_total", reason)
                self.logger.warning(
                    f"FALLBACK_BLOCK: {reason} - blocking trade during fallback mode"
                )
                # Emit event for monitoring
                if self.fsm:
                    from vfoundation.core.protocol import Message
                    from vfoundation.core.fsm_emit_compat import emit_compat
                    import asyncio

                    msg = Message(
                        op="EVT",
                        verb="FALLBACK_BLOCK",
                        src="execution_position",
                        dst="*",
                        pld={
                            "reason": reason,
                            "fallback_reason": self.fallback_state.reason,
                            "policy": policy
                        },
                        why="fallback_mode_block",
                    )
                    self._safe_create_task(emit_compat(
                        self.fsm, msg, logger=self.logger))
                return {"allowed": False, "reason": reason}
            elif policy == "risk_reduction":
                # Apply risk reduction by scaling down the notional
                risk_reduction_pct = self.fallback_config["risk_reduction_pct"]
                reduced_notional = notional_usd * \
                    (Decimal("1") - risk_reduction_pct)
                self.logger.warning(
                    f"FALLBACK_RISK_REDUCTION: {symbol} notional {notional_usd:.2f} → {reduced_notional:.2f} "
                    f"({risk_reduction_pct:.1%} reduction) due to {self.fallback_state.reason}"
                )
                # Update notional for subsequent checks
                notional_usd = reduced_notional
                # Emit event for monitoring
                if self.fsm:
                    from vfoundation.core.protocol import Message
                    from vfoundation.core.fsm_emit_compat import emit_compat
                    import asyncio

                    msg = Message(
                        op="EVT",
                        verb="FALLBACK_RISK_REDUCTION",
                        src="execution_position",
                        dst="*",
                        pld={
                            "symbol": symbol,
                            "original_notional": float(notional_usd / (Decimal("1") - risk_reduction_pct)),
                            "reduced_notional": float(reduced_notional),
                            "reduction_pct": float(risk_reduction_pct),
                            "fallback_reason": self.fallback_state.reason
                        },
                        why="fallback_risk_reduction",
                    )
                    self._safe_create_task(emit_compat(
                        self.fsm, msg, logger=self.logger))

        # EXP-LEVERAGE-001: Calculate margin-based exposure
        # Calculate reserve margin for this order
        symbol_leverage = self.resolve_symbol_leverage(symbol)
        reserve_margin = notional_usd / symbol_leverage

        # Calculate current margin exposure
        current_pending_margin = sum(
            item["margin"] for item in self.state.pending_exposure.values()
            if "margin" in item
        )
        current_postfill_margin = sum(
            item["margin"]
            for item in self.state.postfill_reservations.values()
            if time.time() < item["exp_ts"] and "margin" in item
        )
        total_margin_exposure = open_positions_margin_usd + \
            current_pending_margin + current_postfill_margin

        # 🔍 DIAGNOSTIC: Show pending/postfill breakdown
        self.logger.info(
            f"💧 MARGIN_BREAKDOWN for {symbol}: "
            f"open_positions={open_positions_margin_usd:.2f} + "
            f"pending={current_pending_margin:.2f} + "
            f"postfill={current_postfill_margin:.2f} = "
            f"total={total_margin_exposure:.2f}, "
            f"new_reserve={reserve_margin:.2f}"
        )

        # 🔍 DIAGNOSTIC: Show pending_exposure details
        if self.state.pending_exposure:
            self.logger.warning(
                f"⚠️ PENDING_EXPOSURE ({len(self.state.pending_exposure)} items):"
            )
            for key, item in self.state.pending_exposure.items():
                self.logger.warning(
                    f"   {key}: margin={item.get('margin', 0):.2f}, "
                    f"side={item.get('side', '?')}, ts={item.get('ts', 0)}"
                )

        # 🔍 DIAGNOSTIC: Show postfill_reservations details
        if self.state.postfill_reservations:
            self.logger.warning(
                f"⚠️ POSTFILL_RESERVATIONS ({len(self.state.postfill_reservations)} items):"
            )
            now = time.time()
            for key, item in self.state.postfill_reservations.items():
                exp_ts = item.get("exp_ts", 0)
                age_sec = now - exp_ts
                self.logger.warning(
                    f"   {key}: margin={item.get('margin', 0):.2f}, "
                    f"side={item.get('side', '?')}, "
                    f"exp_in={age_sec:.1f}s"
                )

        # Calculate margin limit
        margin_limit = equity_free_usdt * self.max_equity_utilization_pct
        new_total_margin_exposure = total_margin_exposure + reserve_margin

        # EXP-DIRECTION: Extract long/short margin from portfolio_state
        positions_by_side = portfolio_state.get("positions_by_side", {})
        long_margin_usd = Decimal(
            str(positions_by_side.get("long_margin", "0")))
        short_margin_usd = Decimal(
            str(positions_by_side.get("short_margin", "0")))

        # Also include pending exposure by side (if available)
        pending_long = sum(
            item.get("margin", 0) for item in self.state.pending_exposure.values()
            if item.get("side") == "BUY" and "margin" in item
        )
        pending_short = sum(
            item.get("margin", 0) for item in self.state.pending_exposure.values()
            if item.get("side") == "SELL" and "margin" in item
        )
        postfill_long = sum(
            item.get("margin", 0) for item in self.state.postfill_reservations.values()
            if item.get("side") == "BUY" and time.time() < item["exp_ts"]
        )
        postfill_short = sum(
            item.get("margin", 0) for item in self.state.postfill_reservations.values()
            if item.get("side") == "SELL" and time.time() < item["exp_ts"]
        )

        total_long_margin = long_margin_usd + pending_long + postfill_long
        total_short_margin = short_margin_usd + pending_short + postfill_short

        # Determine which side this order is on
        # (side would come from trade_intent - for now assume we need to infer from notional_usd context)
        # We'll add side parameter later; for now, extract from pending_exposure if available
        order_side = "SELL"  # Default, will be overridden by caller
        for item in self.state.pending_exposure.values():
            if abs(item.get("margin", 0) - reserve_margin) < Decimal("0.01"):
                order_side = item.get("side", "SELL")
                break

        # Calculate new margins after this order
        if order_side == "BUY":
            new_long_margin = total_long_margin + reserve_margin
            new_short_margin = total_short_margin
        else:
            new_long_margin = total_long_margin
            new_short_margin = total_short_margin + reserve_margin

        # Log exposure breakdown with margin details
        utilization_pct = (
            (new_total_margin_exposure / equity_free_usdt *
             100) if equity_free_usdt > 0 else 0
        )
        util_long_pct = (
            (new_long_margin / equity_free_usdt *
             100) if equity_free_usdt > 0 else 0
        )
        util_short_pct = (
            (new_short_margin / equity_free_usdt *
             100) if equity_free_usdt > 0 else 0
        )

        # Calculate directional ratio
        if min(new_long_margin, new_short_margin) > 0:
            directional_ratio = max(new_long_margin, new_short_margin) / min(
                new_long_margin, new_short_margin)
        else:
            directional_ratio = Decimal("1.0")

        self.logger.info(
            f"EXPOSURE_BREAKDOWN margin_used={new_total_margin_exposure:.2f} "
            f"limit={margin_limit:.2f} reserve_margin={reserve_margin:.2f} "
            f"equity={equity_free_usdt:.2f} lev={symbol_leverage} "
            f"util_total={utilization_pct:.1f}% util_long={util_long_pct:.1f}% "
            f"util_short={util_short_pct:.1f}% ratio={directional_ratio:.2f} "
            f"why=margin_check"
        )

        # EXP-DIRECTION: Check 1 - Total margin cap (PHASE 3: with soft-clip)
        if new_total_margin_exposure > margin_limit:
            allowed_extra = margin_limit - total_margin_exposure

            if allowed_extra > Decimal("0"):
                # Shrink-to-fit: reduce order size to fit within limit
                shrink_notional = allowed_extra * symbol_leverage
                self.logger.info(
                    f"EXPOSURE_SHRINK_TO_FIT: {symbol} notional {notional_usd:.2f} → {shrink_notional:.2f} "
                    f"(allowed_extra={allowed_extra:.2f})"
                )
                return {
                    "allowed": True,
                    "reason": "SHRUNK_TO_FIT",
                    "shrink_notional": shrink_notional
                }
            else:
                # PHASE 3: Try soft-clip before rejecting
                if self.soft_limit_config.mode == "clip":
                    clip_result = self.soft_clip_engine.calculate_clipped_size(
                        notional_usd=notional_usd,
                        symbol=symbol,
                        order_side=order_side,
                        long_margin=new_long_margin,
                        short_margin=new_short_margin,
                        total_margin_exposure=total_margin_exposure,
                        symbol_leverage=symbol_leverage,
                        margin_limit=margin_limit,
                    )
                    if clip_result.allowed:
                        self.logger.info(
                            f"CLIPPED_MARGIN: {symbol} {order_side} "
                            f"{notional_usd:.2f} → {clip_result.clipped_notional:.2f} "
                            f"reasons={clip_result.clip_reasons}"
                        )
                        # Phase 5: Metrics aggregation
                        metrics_logger.log_clip_event(
                            symbol=symbol,
                            original_notional=notional_usd,
                            clipped_notional=clip_result.clipped_notional,
                            clip_reason=clip_result.clip_reasons[0] if clip_result.clip_reasons else "unknown",
                            rid=f"clip_margin_{symbol}_{now_ms}",
                        )
                        self.metrics["clip_total"] = self.metrics.get(
                            "clip_total", 0) + 1
                        self.metrics["clip_notional_total"] = self.metrics.get(
                            "clip_notional_total", Decimal("0")) + (notional_usd - clip_result.clipped_notional)
                        order_logger.write({
                            "rid": f"clip_margin_{symbol}_{now_ms}",
                            "event_type": "ORDER_CLIPPED",
                            "symbol": symbol,
                            "side": order_side,
                            "original_notional": float(notional_usd),
                            "clipped_notional": float(clip_result.clipped_notional),
                            "reason": "MARGIN_LIMIT",
                            "clip_reasons": clip_result.clip_reasons,
                        })
                        # Emit EVT:ORDER_CLIPPED event for margin clipping
                        if self.fsm:
                            from vfoundation.core.protocol import Message
                            from vfoundation.core.fsm_emit_compat import emit_compat
                            import asyncio

                            msg = Message(
                                op="EVT",
                                verb="ORDER_CLIPPED",
                                src="execution_position",
                                dst="*",
                                pld={
                                    "symbol": symbol,
                                    "side": order_side,
                                    "original_notional": float(notional_usd),
                                    "clipped_notional": float(clip_result.clipped_notional),
                                    "reason": "MARGIN_LIMIT",
                                    "clip_reasons": clip_result.clip_reasons,
                                    "reduction_amount": float(notional_usd - clip_result.clipped_notional)
                                },
                                why="order_clipped_margin_limit",
                            )
                            self._safe_create_task(emit_compat(
                                self.fsm, msg, logger=self.logger))
                        return {
                            "allowed": True,
                            "reason": "CLIPPED_MARGIN",
                            "shrink_notional": clip_result.clipped_notional,
                        }

                reason = "EXPOSURE_LIMIT_EXCEEDED"
                self.logger.warning(
                    f"EXPOSURE_REJECT: {reason} - would exceed {margin_limit:.2f} USD margin limit"
                )
                # Metrics: rejection event (NRR-011)
                try:
                    metrics_logger.log_reject_event(
                        symbol=symbol,
                        reason="NRR-011",
                        notional=notional_usd,
                        side=order_side,
                        rid=f"exposure_check_{symbol}_{now_ms}",
                    )
                except Exception:
                    pass
                order_logger.write({
                    "rid": f"exposure_check_{symbol}_{now_ms}",
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": "NONE",
                    "quantity": float(notional_usd),
                    "nrr_code": "NRR-011",
                    "why": f"Margin exposure limit exceeded: {new_total_margin_exposure:.2f} > {margin_limit:.2f}",
                    "source_fsm": "ExposureGuard",
                    "metadata": {
                        "exposure_check": True,
                        "margin_limit": float(margin_limit),
                        "new_total_margin": float(new_total_margin_exposure),
                        "reserve_margin": float(reserve_margin),
                        "leverage": float(symbol_leverage)
                    }
                })
                # Emit EVT:ORDER_REJECTED event for exposure limit
                if self.fsm:
                    from vfoundation.core.protocol import Message
                    from vfoundation.core.fsm_emit_compat import emit_compat
                    import asyncio

                    msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="*",
                        pld={
                            "symbol": symbol,
                            "side": "NONE",
                            "quantity": float(notional_usd),
                            "nrr_code": "NRR-011",
                            "reason": reason,
                            "why": f"Margin exposure limit exceeded: {new_total_margin_exposure:.2f} > {margin_limit:.2f}",
                            "margin_limit": float(margin_limit),
                            "new_total_margin": float(new_total_margin_exposure),
                            "reserve_margin": float(reserve_margin),
                            "leverage": float(symbol_leverage)
                        },
                        why="exposure_limit_exceeded",
                    )
                    self._safe_create_task(emit_compat(
                        self.fsm, msg, logger=self.logger))
                return {"allowed": False, "reason": reason}

        # EXP-DIRECTION: Check 2 - Per-side cap (PHASE 3: with soft-clip)
        side_limit = equity_free_usdt * (
            self.max_long_utilization_pct if order_side == "BUY"
            else self.max_short_utilization_pct
        )
        current_side_margin = new_long_margin if order_side == "BUY" else new_short_margin

        if current_side_margin > side_limit:
            allowed_extra_side = side_limit - (
                total_long_margin if order_side == "BUY" else total_short_margin
            )

            if allowed_extra_side > Decimal("0"):
                shrink_notional = allowed_extra_side * symbol_leverage
                self.logger.info(
                    f"EXPOSURE_SIDE_SHRINK: {symbol} {order_side} notional {notional_usd:.2f} → {shrink_notional:.2f} "
                    f"(side_limit={side_limit:.2f}, current={current_side_margin:.2f})"
                )
                return {
                    "allowed": True,
                    "reason": "SHRUNK_TO_FIT_SIDE",
                    "shrink_notional": shrink_notional
                }
            else:
                # PHASE 3: Try soft-clip before rejecting
                if self.soft_limit_config.mode == "clip":
                    clip_result = self.soft_clip_engine.calculate_clipped_size(
                        notional_usd=notional_usd,
                        symbol=symbol,
                        order_side=order_side,
                        long_margin=new_long_margin,
                        short_margin=new_short_margin,
                        total_margin_exposure=total_margin_exposure,
                        symbol_leverage=symbol_leverage,
                        side_limit=side_limit,
                    )
                    if clip_result.allowed:
                        self.logger.info(
                            f"CLIPPED_SIDE: {symbol} {order_side} "
                            f"{notional_usd:.2f} → {clip_result.clipped_notional:.2f} "
                            f"reasons={clip_result.clip_reasons}"
                        )
                        self.metrics["clip_total"] = self.metrics.get(
                            "clip_total", 0) + 1
                        self.metrics["clip_notional_total"] = self.metrics.get(
                            "clip_notional_total", Decimal("0")) + (notional_usd - clip_result.clipped_notional)
                        order_logger.write({
                            "rid": f"clip_side_{symbol}_{now_ms}",
                            "event_type": "ORDER_CLIPPED",
                            "symbol": symbol,
                            "side": order_side,
                            "original_notional": float(notional_usd),
                            "clipped_notional": float(clip_result.clipped_notional),
                            "reason": "SIDE_LIMIT",
                            "clip_reasons": clip_result.clip_reasons,
                        })
                        # Emit EVT:ORDER_CLIPPED event for side clipping
                        if self.fsm:
                            from vfoundation.core.protocol import Message
                            from vfoundation.core.fsm_emit_compat import emit_compat
                            import asyncio

                            msg = Message(
                                op="EVT",
                                verb="ORDER_CLIPPED",
                                src="execution_position",
                                dst="*",
                                pld={
                                    "symbol": symbol,
                                    "side": order_side,
                                    "original_notional": float(notional_usd),
                                    "clipped_notional": float(clip_result.clipped_notional),
                                    "reason": "SIDE_LIMIT",
                                    "clip_reasons": clip_result.clip_reasons,
                                    "reduction_amount": float(notional_usd - clip_result.clipped_notional)
                                },
                                why="order_clipped_side_limit",
                            )
                            self._safe_create_task(emit_compat(
                                self.fsm, msg, logger=self.logger))
                        return {
                            "allowed": True,
                            "reason": "CLIPPED_SIDE",
                            "shrink_notional": clip_result.clipped_notional,
                        }

                reason = "SIDE_EXPOSURE_EXCEEDED"
                self.logger.warning(
                    f"EXPOSURE_REJECT: {reason} - {order_side} would exceed {side_limit:.2f} USD limit"
                )
                # Metrics: rejection event (NRR-012)
                try:
                    metrics_logger.log_reject_event(
                        symbol=symbol,
                        reason="NRR-012",
                        notional=notional_usd,
                        side=order_side,
                        rid=f"exposure_check_{symbol}_{now_ms}",
                    )
                except Exception:
                    pass
                order_logger.write({
                    "rid": f"exposure_check_{symbol}_{now_ms}",
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": order_side,
                    "quantity": float(notional_usd),
                    "nrr_code": "NRR-012",
                    "why": f"Side exposure limit exceeded: {current_side_margin:.2f} > {side_limit:.2f}",
                    "source_fsm": "ExposureGuard",
                    "metadata": {
                        "side_limit": float(side_limit),
                        "current_side_margin": float(current_side_margin)
                    }
                })
                # Emit EVT:ORDER_REJECTED event for side exposure limit
                if self.fsm:
                    from vfoundation.core.protocol import Message
                    from vfoundation.core.fsm_emit_compat import emit_compat
                    import asyncio

                    msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="*",
                        pld={
                            "symbol": symbol,
                            "side": order_side,
                            "quantity": float(notional_usd),
                            "nrr_code": "NRR-012",
                            "reason": reason,
                            "why": f"Side exposure limit exceeded: {current_side_margin:.2f} > {side_limit:.2f}",
                            "side_limit": float(side_limit),
                            "current_side_margin": float(current_side_margin)
                        },
                        why="side_exposure_limit_exceeded",
                    )
                    self._safe_create_task(emit_compat(
                        self.fsm, msg, logger=self.logger))
                return {"allowed": False, "reason": reason}

        # EXP-DIRECTION: Check 3 - Directional ratio cap (PHASE 3: with soft-clip)
        if directional_ratio > self.max_directional_ratio and min(new_long_margin, new_short_margin) > 0:
            # PHASE 3: Try soft-clip before rejecting
            if self.soft_limit_config.mode == "clip":
                clip_result = self.soft_clip_engine.calculate_clipped_size(
                    notional_usd=notional_usd,
                    symbol=symbol,
                    order_side=order_side,
                    long_margin=new_long_margin,
                    short_margin=new_short_margin,
                    total_margin_exposure=total_margin_exposure,
                    symbol_leverage=symbol_leverage,
                    directional_ratio_max=self.max_directional_ratio,
                )
                if clip_result.allowed:
                    self.logger.info(
                        f"CLIPPED_DIRECTIONAL: {symbol} {order_side} "
                        f"{notional_usd:.2f} → {clip_result.clipped_notional:.2f} "
                        f"reasons={clip_result.clip_reasons}"
                    )
                    self.metrics["clip_total"] = self.metrics.get(
                        "clip_total", 0) + 1
                    self.metrics["clip_notional_total"] = self.metrics.get(
                        "clip_notional_total", Decimal("0")) + (notional_usd - clip_result.clipped_notional)
                    order_logger.write({
                        "rid": f"clip_directional_{symbol}_{now_ms}",
                        "event_type": "ORDER_CLIPPED",
                        "symbol": symbol,
                        "side": order_side,
                        "original_notional": float(notional_usd),
                        "clipped_notional": float(clip_result.clipped_notional),
                        "reason": "DIRECTIONAL_RATIO",
                        "clip_reasons": clip_result.clip_reasons,
                    })
                    # Emit EVT:ORDER_CLIPPED event for directional clipping
                    if self.fsm:
                        from vfoundation.core.protocol import Message
                        from vfoundation.core.fsm_emit_compat import emit_compat
                        import asyncio

                        msg = Message(
                            op="EVT",
                            verb="ORDER_CLIPPED",
                            src="execution_position",
                            dst="*",
                            pld={
                                "symbol": symbol,
                                "side": order_side,
                                "original_notional": float(notional_usd),
                                "clipped_notional": float(clip_result.clipped_notional),
                                "reason": "DIRECTIONAL_RATIO",
                                "clip_reasons": clip_result.clip_reasons,
                                "reduction_amount": float(notional_usd - clip_result.clipped_notional)
                            },
                            why="order_clipped_directional_ratio",
                        )
                        self._safe_create_task(emit_compat(
                            self.fsm, msg, logger=self.logger))
                    return {
                        "allowed": True,
                        "reason": "CLIPPED_DIRECTIONAL",
                        "shrink_notional": clip_result.clipped_notional,
                    }

            reason = "DIRECTIONAL_RATIO_EXCEEDED"
            self.logger.warning(
                f"EXPOSURE_REJECT: {reason} - ratio {directional_ratio:.2f} > {self.max_directional_ratio}"
            )
            # Metrics: rejection event (NRR-013)
            try:
                metrics_logger.log_reject_event(
                    symbol=symbol,
                    reason="NRR-013",
                    notional=notional_usd,
                    side=order_side,
                    rid=f"exposure_check_{symbol}_{now_ms}",
                )
            except Exception:
                pass
            order_logger.write({
                "rid": f"exposure_check_{symbol}_{now_ms}",
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": order_side,
                "quantity": float(notional_usd),
                "nrr_code": "NRR-013",
                "why": f"Directional ratio limit exceeded: {directional_ratio:.2f} > {self.max_directional_ratio}",
                "source_fsm": "ExposureGuard",
                "metadata": {
                    "directional_ratio": float(directional_ratio),
                    "max_ratio": float(self.max_directional_ratio),
                    "long_margin": float(new_long_margin),
                    "short_margin": float(new_short_margin)
                }
            })
            # Emit EVT:ORDER_REJECTED event for directional ratio limit
            if self.fsm:
                from vfoundation.core.protocol import Message
                from vfoundation.core.fsm_emit_compat import emit_compat
                import asyncio

                msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="*",
                    pld={
                        "symbol": symbol,
                        "side": order_side,
                        "quantity": float(notional_usd),
                        "nrr_code": "NRR-013",
                        "reason": reason,
                        "why": f"Directional ratio limit exceeded: {directional_ratio:.2f} > {self.max_directional_ratio}",
                        "directional_ratio": float(directional_ratio),
                        "max_ratio": float(self.max_directional_ratio),
                        "long_margin": float(new_long_margin),
                        "short_margin": float(new_short_margin)
                    },
                    why="directional_ratio_limit_exceeded",
                )
                self._safe_create_task(emit_compat(
                    self.fsm, msg, logger=self.logger))
            return {"allowed": False, "reason": reason}

        return {"allowed": True}

    def reserve(
        self, key: str, notional_usd: Decimal, reduce_only: bool = False, symbol: str = "", side: str = "SELL"
    ) -> None:
        """
        Reserve exposure for a pending order.

        EXP-LEVERAGE-001: Calculate and reserve margin instead of notional.
        EXP-DIRECTION: Track side for directional ratio calculations.

        Args:
            key: Reservation key (idempotent_key or rid)
            notional_usd: Position notional value in USD
            reduce_only: Whether this is a reduce-only order
            symbol: Trading symbol for leverage calculation
            side: Order side (BUY or SELL)
        """
        now = time.time()

        # Calculate reserve margin
        symbol_leverage = self.resolve_symbol_leverage(
            symbol) if symbol else Decimal("1")
        reserve_margin = notional_usd / symbol_leverage

        # Store reservation data
        # Keep notional for backward compatibility
        self.state.reservations[key] = notional_usd
        self.state.reservations_ts[key] = now

        # Store in pending_exposure with margin info and side
        self.state.pending_exposure[key] = {
            "notional": notional_usd,
            "margin": reserve_margin,
            "leverage": symbol_leverage,
            "ts": now,
            "reduce_only": reduce_only,
            "side": side,
        }

        self.logger.debug(
            f"EXPOSURE_RESERVE: key={key}, notional={notional_usd}, margin={reserve_margin}, lev={symbol_leverage}, side={side}"
        )

        # Log to OrderLoggerV1
        order_logger.write({
            "rid": f"reserve_{key}",
            "event_type": "ORDER_INTENT",
            "symbol": symbol,
            "side": side,
            "quantity": float(reserve_margin),  # Log margin amount
            "source_fsm": "ExposureGuard",
            "reservation_id": key,
            "metadata": {
                "reservation_created": True,
                "reduce_only": reduce_only,
                "reserve_margin": float(reserve_margin),
                "leverage": float(symbol_leverage),
                "side": side
            }
        })

    def release(self, key: str) -> None:
        """
        Release exposure reservation.

        Args:
            key: Reservation key to release
        """
        if key in self.state.reservations:
            released_usd = self.state.reservations.pop(key)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)
            self.logger.debug(
                f"EXPOSURE_RELEASE: key={key}, usd={released_usd}")

    def cleanup_all_pending(self) -> None:
        """
        🧹 EMERGENCY CLEANUP: Clear ALL pending_exposure reservations.

        This should be called during startup/sync to clear stale orders
        that were not properly released (e.g., after restart).
        """
        if self.state.pending_exposure:
            count = len(self.state.pending_exposure)
            total_margin = sum(
                item.get("margin", 0) for item in self.state.pending_exposure.values()
            )
            self.logger.critical(
                f"🧹 CLEANUP_ALL_PENDING: Clearing {count} stale orders, "
                f"total_margin={total_margin:.2f} USD"
            )
            self.state.pending_exposure.clear()
            self.state.reservations.clear()
            self.state.reservations_ts.clear()
        else:
            self.logger.info(
                f"✅ CLEANUP_ALL_PENDING: No pending orders to clear"
            )

    def on_fill(self, key: str, notional_usd: Decimal, symbol: str = "", side: str = "SELL") -> None:
        """
        Handle order fill - move to post-fill hold instead of immediate release.

        EXP-FIX: Prevents race condition where FILL is processed before portfolio update.
        EXP-LEVERAGE-001: Store margin in postfill reservations.
        EXP-DIRECTION: Track side for directional ratio calculations.

        Args:
            key: Reservation key
            notional_usd: Filled notional value
            symbol: Trading symbol for leverage calculation
            side: Order side (BUY or SELL)
        """
        if key in self.state.reservations:
            # Calculate filled margin
            symbol_leverage = self.resolve_symbol_leverage(
                symbol) if symbol else Decimal("1")
            filled_margin = notional_usd / symbol_leverage

            # Move to post-fill hold instead of releasing
            expiration_ts = time.time() + self.post_fill_hold_ttl_sec
            self.state.postfill_reservations[key] = {
                "notional": notional_usd,
                "margin": filled_margin,
                "leverage": symbol_leverage,
                "exp_ts": expiration_ts,
                "side": side,
            }
            self.state.reservations.pop(key, None)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)

            self.metrics["postfill_hold_active"] = len(
                self.state.postfill_reservations)
            self.logger.debug(
                f"POSTFILL_HOLD: key={key}, notional={notional_usd}, margin={filled_margin}, lev={symbol_leverage}, side={side}, expires={expiration_ts}"
            )

    def expire_stale(self) -> List[str]:
        """
        Clean up stale reservations and expired post-fill holds.

        Returns:
            List of expired reservation keys
        """
        now = time.time()
        expired = []

        # Clean up stale reservations
        stale_reservations = [
            key
            for key, ts in self.state.reservations_ts.items()
            if now - ts > self.pending_ttl_sec
        ]
        for key in stale_reservations:
            expired.append(key)
            self.state.reservations.pop(key, None)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)

        # Clean up expired post-fill holds
        expired_postfill = [
            key
            for key, item in self.state.postfill_reservations.items()
            if now >= item["exp_ts"]
        ]
        for key in expired_postfill:
            self.state.postfill_reservations.pop(key, None)
            self.metrics["postfill_hold_expired_total"] += 1
            expired.append(key)  # Add to expired list

        self.metrics["postfill_hold_active"] = len(
            self.state.postfill_reservations)

        if expired:
            self.logger.info(
                f"EXPOSURE_CLEANUP: expired {len(expired)} reservations, {len(expired_postfill)} postfill holds"
            )

        return expired

    def get_exposure_summary(self) -> Dict[str, Any]:
        """Get current exposure summary for metrics."""
        total_pending = sum(self.state.reservations.values())
        total_pending_margin = sum(
            item.get("margin", 0) for item in self.state.pending_exposure.values()
        )
        total_postfill = len(self.state.postfill_reservations)
        total_postfill_margin = sum(
            item.get("margin", 0) for item in self.state.postfill_reservations.values()
        )

        return {
            "reservations_count": len(self.state.reservations),
            "reservations_usd": float(total_pending),
            "reservations_margin_usd": float(total_pending_margin),
            "postfill_hold_count": total_postfill,
            "postfill_hold_margin_usd": float(total_postfill_margin),
            "pending_ttl_sec": self.pending_ttl_sec,
            "postfill_hold_ttl_sec": self.post_fill_hold_ttl_sec,
        }

    def on_regime_changed(self, regime_type: str) -> None:
        """
        PHASE 3: Regime adaptation - update directional ratio based on market regime.

        regime_type: "TREND_UP", "TREND_DOWN", "FLAT", "UNCERTAIN"
        """
        if not self.soft_limit_config:
            return

        regime_adaptation = getattr(
            self.soft_limit_config, "regime_adaptation", None)
        if not regime_adaptation:
            return

        base_ratio = self.soft_limit_config.directional_ratio_max
        bounds = regime_adaptation.bounds if regime_adaptation.bounds else [
            2.0, 4.0]

        delta = Decimal("0")
        if regime_type == "TREND_UP":
            delta = Decimal(str(regime_adaptation.trend_up_delta)
                            ) if regime_adaptation.trend_up_delta else Decimal("0")
        elif regime_type == "TREND_DOWN":
            delta = Decimal(str(regime_adaptation.trend_down_delta)
                            ) if regime_adaptation.trend_down_delta else Decimal("0")
        elif regime_type in ["FLAT", "UNCERTAIN"]:
            delta = Decimal(str(regime_adaptation.flat_delta)
                            ) if regime_adaptation.flat_delta else Decimal("0")

        new_ratio = max(
            Decimal(str(bounds[0])),
            min(
                Decimal(str(bounds[1])),
                base_ratio + delta
            )
        )

        self.max_directional_ratio = new_ratio
        self.logger.info(
            f"REGIME_ADAPTED: {regime_type} → directional_ratio_max={float(new_ratio):.2f} "
            f"(base={float(base_ratio):.2f}, delta={float(delta):.2f})"
        )

    def _safe_create_task(self, coro) -> None:
        """
        Safely create an asyncio task, checking for running event loop.

        This prevents RuntimeError when called from synchronous test contexts.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            # No running event loop, try to get existing loop
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.create_task(coro)
                else:
                    # Loop is closed, skip emission
                    pass
            except RuntimeError:
                # No event loop available, skip emission
                pass

    def _increment_metric(self, metric_name: str, reason: str) -> None:
        """
        Increment a metric counter by reason.

        Args:
            metric_name: Name of the metric (e.g., "exposure_fail_closed_total")
            reason: Reason for the increment (e.g., "EQUITY_UNKNOWN")
        """
        if metric_name not in self.metrics:
            self.metrics[metric_name] = {}

        current_value = self.metrics[metric_name]

        if not isinstance(current_value, dict):
            legacy_total = current_value
            self.metrics[metric_name] = {}
            if isinstance(legacy_total, (int, float, Decimal)) and legacy_total:
                # Preserve any pre-existing aggregate count under a legacy bucket.
                self.metrics[metric_name]["__legacy_total"] = legacy_total

        if reason not in self.metrics[metric_name]:
            self.metrics[metric_name][reason] = 0

        self.metrics[metric_name][reason] += 1
