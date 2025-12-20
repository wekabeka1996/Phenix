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
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass

from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.soft_clip import SoftClipEngine as SoftClipEngineImpl
from apps.reference.domains.execution_position.metrics_aggregator import metrics_logger
from apps.reference.domain_config import DomainConfigResolver
from apps.reference.config_contract import ConfigContractError
from apps.reference.config_models import AuroraConfig


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

    def __init__(self, fsm_core: Any, config: AuroraConfig):
        self.fsm = fsm_core
        if isinstance(config, dict):
            raise TypeError("ExposureGuard requires AuroraConfig, got dict")
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        # =====================================================================
        # PHASE 2: Use DomainConfigResolver for clean config access
        # =====================================================================
        resolver = DomainConfigResolver(config)
        eg_config = resolver.get_exposure_guard()

        # FIX: Normalize thresholds without "magic" auto-detection. 
        # Fields ending in _pct are treated as percentage (divided by 100).
        # Fields ending in _fraction are treated as ratio (0..1).
        
        def _to_dec(val: Any) -> Decimal:
            if val is None: return Decimal("0")
            return Decimal(str(val))

        self.max_equity_utilization_pct = _to_dec(eg_config.max_equity_utilization_pct) / Decimal("100")
        self.max_portfolio_fraction = _to_dec(eg_config.max_portfolio_fraction)
        self.max_long_utilization_pct = _to_dec(eg_config.max_long_utilization_pct) / Decimal("100")
        self.max_short_utilization_pct = _to_dec(eg_config.max_short_utilization_pct) / Decimal("100")
        self.max_concentration_pct = _to_dec(eg_config.max_concentration_pct) / Decimal("100")

        # Directional ratio (legacy support)
        max_directional_ratio_raw = getattr(eg_config, "max_directional_ratio", None)
        if max_directional_ratio_raw is None:
            max_directional_ratio_raw = getattr(eg_config, "directional_ratio_max", "5.0")
        self.max_directional_ratio = _to_dec(max_directional_ratio_raw)

        # TTL configurations
        self.pending_ttl_sec = eg_config.pending_ttl_sec
        self.post_fill_hold_ttl_sec = eg_config.post_fill_ttl_sec
        self.positions_stale_ttl_sec = eg_config.stale_ttl_sec

        # Flags (strict typed config; fail-closed)
        execution_cfg = self.config.trading.execution
        if execution_cfg is None or execution_cfg.exposure is None:
            raise ConfigContractError(
                path="trading.execution.exposure",
                why="Missing required exposure config (expected count_pending_orders/exclude_reduce_only/leverage_defaults).",
            )
        self.count_pending_orders = bool(execution_cfg.exposure.count_pending_orders)
        self.exclude_reduce_only = bool(execution_cfg.exposure.exclude_reduce_only)

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
            f"🆕 ExposureGuard initialized: "
            f"max_eq_util={self.max_equity_utilization_pct}, "
            f"pending_ttl={self.pending_ttl_sec}s"
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
        Reads from trading.risk.soft_limits (legacy dict block; fail-closed).
        """
        risk_cfg = self.config.trading.risk
        if not isinstance(risk_cfg, dict):
            raise ConfigContractError(path="trading.risk", why=f"Expected dict, got {type(risk_cfg)}")
        soft_limits_dict = risk_cfg.get("soft_limits")
        if not isinstance(soft_limits_dict, dict):
            raise ConfigContractError(path="trading.risk.soft_limits", why="Missing/invalid soft_limits block")

        required_keys = (
            "mode",
            "clip_min_notional_usdt",
            "directional_ratio_max",
            "side_exposure_usdt",
            "margin_exposure_usdt",
        )
        for k in required_keys:
            if k not in soft_limits_dict:
                raise ConfigContractError(path=f"trading.risk.soft_limits.{k}", why="Missing required key")

        mode = str(soft_limits_dict["mode"])
        clip_min = Decimal(str(soft_limits_dict["clip_min_notional_usdt"]))
        dir_max = Decimal(str(soft_limits_dict["directional_ratio_max"]))
        side_exp = Decimal(str(soft_limits_dict["side_exposure_usdt"]))
        margin_exp = Decimal(str(soft_limits_dict["margin_exposure_usdt"]))

        config = SoftLimitConfig(
            mode=mode,
            clip_min_notional_usdt=clip_min,
            directional_ratio_max=dir_max,
            side_exposure_usdt=side_exp,
            margin_exposure_usdt=margin_exp,
        )
        self.logger.info(
            f"SOFT_LIMIT_CONFIG loaded: mode={mode}, "
            f"clip_min={clip_min}, dir_ratio_max={dir_max}, "
            f"side_exp={side_exp}, margin_exp={margin_exp}"
        )
        return config

    def _load_fallback_config(self) -> Dict[str, Any]:
        """
        PHASE P0: Load fallback mode configuration.
        NOTE: trading.execution.fallback is currently an empty typed block; keep the historical constants here.
        """
        config = {"policy": "fail_closed", "risk_reduction_pct": Decimal("0.5"), "backoff_ms": [200, 500, 1000]}
        self.logger.info(
            f"FALLBACK_CONFIG loaded: policy={config['policy']}, risk_reduction_pct={config['risk_reduction_pct']}, backoff_ms={config['backoff_ms']}"
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
        fallback_total = self.metrics["fallback_duration_ms_total"] if "fallback_duration_ms_total" in self.metrics else 0
        self.metrics["fallback_duration_ms_total"] = fallback_total + duration_ms

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
        execution_cfg = self.config.trading.execution
        if execution_cfg is None or execution_cfg.exposure is None:
            raise ConfigContractError(
                path="trading.execution.exposure",
                why="Missing required exposure config (leverage_defaults).",
            )

        leverage_defaults = execution_cfg.exposure.leverage_defaults
        if not isinstance(leverage_defaults, dict):
            raise ConfigContractError(
                path="trading.execution.exposure.leverage_defaults",
                why=f"Expected dict, got {type(leverage_defaults)}",
            )

        default_leverage_raw = leverage_defaults["__default__"] if "__default__" in leverage_defaults else 20
        default_leverage = Decimal(str(default_leverage_raw))

        symbol_leverage_raw = leverage_defaults[symbol] if symbol in leverage_defaults else default_leverage
        symbol_leverage = Decimal(str(symbol_leverage_raw))

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
        equity_raw = portfolio_state["equity_free_usdt"] if "equity_free_usdt" in portfolio_state else "MISSING"
        margin_raw = portfolio_state["open_positions_margin_usd"] if "open_positions_margin_usd" in portfolio_state else "MISSING"
        ts_raw = portfolio_state["positions_last_ts_ms"] if "positions_last_ts_ms" in portfolio_state else "MISSING"
        self.logger.info(
            f"ON_PORTFOLIO_DEBUG: received portfolio_keys={portfolio_keys}, "
            f"equity_raw={equity_raw}, margin_raw={margin_raw}, ts_raw={ts_raw}"
        )

        # Update stored portfolio data
        self._latest_portfolio_state = portfolio_state

        # Log portfolio update for debugging
        equity_free_usdt = portfolio_state["equity_free_usdt"] if "equity_free_usdt" in portfolio_state else "0"
        open_positions_margin_usd = portfolio_state["open_positions_margin_usd"] if "open_positions_margin_usd" in portfolio_state else "0"
        positions_last_ts_ms = portfolio_state["positions_last_ts_ms"] if "positions_last_ts_ms" in portfolio_state else 0

        self.logger.debug(
            f"PORTFOLIO_UPDATE: equity={equity_free_usdt}, margin_positions={open_positions_margin_usd}, "
            f"ts={positions_last_ts_ms}"
        )

    def can_open(
        self, symbol: str, notional_usd: Decimal, portfolio_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if opening a position is allowed based on exposure limits.
        Filters by:
        1. Data staleness
        2. Equity presence
        3. Portfolio Fraction (Notional-based)
        4. Equity Utilization (Margin-based)
        5. Long/Short Utilization (Margin-based)
        6. Directional Ratio (Notional-based)
        """
        # --- 0. Fallback Mode Logic (Fail-fast) ---
        if self.is_fallback_mode_active():
            policy = self.fallback_config["policy"]
            if policy == "fail_closed":
                reason = f"FALLBACK_FAIL_CLOSED_{self.fallback_state.reason}"
                return {"allowed": False, "reason": reason}
            elif policy == "risk_reduction":
                risk_reduction_pct = Decimal(str(self.fallback_config["risk_reduction_pct"]))
                notional_usd = notional_usd * (Decimal("1") - risk_reduction_pct)
                self.logger.warning(
                    f"FALLBACK_REDUCE: {symbol} notional reduced to {notional_usd:.2f} "
                    f"(-{float(risk_reduction_pct):.1%}) due to {self.fallback_state.reason}"
                )

        # --- 1. Data Integrity & Fail-Closed ---
        def _d(v): return Decimal(str(v)) if v is not None else Decimal("0")
        
        equity_free_usdt = _d(portfolio_state.get("equity_free_usdt", "0"))
        # Check equity first to satisfy test expectations for EQUITY_UNKNOWN
        if "equity_free_usdt" not in portfolio_state or equity_free_usdt <= Decimal("0"):
            return {"allowed": False, "reason": "EQUITY_UNKNOWN", "why": "exposure_guard_no_equity"}

        stale_ttl = self.positions_stale_ttl_sec
        last_ts_ms = portfolio_state.get("positions_last_ts_ms", 0)
        stale_sec = time.time() - (last_ts_ms / 1000)
        if last_ts_ms == 0 or stale_sec > stale_ttl:
            return {"allowed": False, "reason": "PORTFOLIO_STALE", "stale_sec": float(stale_sec)}

        # --- 2. State Accumulation ---
        positions = portfolio_state.get("positions", [])
        if not isinstance(positions, list): positions = []
        
        long_notional = Decimal("0")
        short_notional = Decimal("0")
        long_margin = Decimal("0")
        short_margin = Decimal("0")
        
        ref_leverage = self.resolve_symbol_leverage(symbol)
        
        for p in positions:
            if not isinstance(p, dict): continue
            p_sym = str(p.get("symbol", ""))
            p_side = str(p.get("side", "")).upper()
            p_notion = abs(_d(p.get("notional_usd")))
            
            p_lev = self.resolve_symbol_leverage(p_sym) if p_sym else ref_leverage
            p_marg = p_notion / p_lev if p_lev else Decimal("0")
            
            if p_side in {"BUY", "LONG"}:
                long_notional += p_notion
                long_margin += p_marg
            elif p_side in {"SELL", "SHORT"}:
                short_notional += p_notion
                short_margin += p_marg

        # Include pending/postfill margin reservations
        pending_long_m = sum(item["margin"] for item in self.state.pending_exposure.values() if item.get("side") in {"BUY", "LONG"} and "margin" in item)
        pending_short_m = sum(item["margin"] for item in self.state.pending_exposure.values() if item.get("side") in {"SELL", "SHORT"} and "margin" in item)
        post_long_m = sum(item["margin"] for item in self.state.postfill_reservations.values() if item.get("side") in {"BUY", "LONG"} and time.time() < item.get("exp_ts", 0) and "margin" in item)
        post_short_m = sum(item["margin"] for item in self.state.postfill_reservations.values() if item.get("side") in {"SELL", "SHORT"} and time.time() < item.get("exp_ts", 0) and "margin" in item)

        total_pending_margin = pending_long_m + pending_short_m + post_long_m + post_short_m
        
        order_notional_abs = abs(notional_usd)
        order_margin = order_notional_abs / ref_leverage if ref_leverage else Decimal("0")
        order_side = "BUY" if notional_usd >= Decimal("0") else "SELL"

        # --- 3. Limit Enforcement ---
        
        # A) Max Portfolio Fraction (NOTIONAL-based)
        p_frac_limit = equity_free_usdt * self.max_portfolio_fraction
        if order_notional_abs > p_frac_limit:
            return {"allowed": False, "reason": "PORTFOLIO_FRACTION_BREACH", "order_notional": float(order_notional_abs), "limit": float(p_frac_limit)}

        # B) Max Equity Utilization (MARGIN-based)
        total_margin_used = (long_margin + short_margin + total_pending_margin + order_margin)
        equity_margin_limit = equity_free_usdt * self.max_equity_utilization_pct
        if total_margin_used > equity_margin_limit:
            return {"allowed": False, "reason": "EQUITY_UTILIZATION_BREACH", "actual": float(total_margin_used), "limit": float(equity_margin_limit)}

        # C) Long/Short Utilization (MARGIN-based)
        new_long_m = long_margin + pending_long_m + post_long_m + (order_margin if order_side == "BUY" else Decimal("0"))
        new_short_m = short_margin + pending_short_m + post_short_m + (order_margin if order_side == "SELL" else Decimal("0"))
        
        long_limit = equity_free_usdt * self.max_long_utilization_pct
        short_limit = equity_free_usdt * self.max_short_utilization_pct
        
        if new_long_m > long_limit:
            return {"allowed": False, "reason": "LONG_UTILIZATION_BREACH", "actual": float(new_long_m), "limit": float(long_limit)}
        if new_short_m > short_limit:
            return {"allowed": False, "reason": "SHORT_UTILIZATION_BREACH", "actual": float(new_short_m), "limit": float(short_limit)}

        # D) Directional Ratio (NOTIONAL-based)
        new_long_notion = long_notional + (order_notional_abs if order_side == "BUY" else Decimal("0"))
        new_short_notion = short_notional + (order_notional_abs if order_side == "SELL" else Decimal("0"))
        if new_short_notion > Decimal("0"):
            ratio = new_long_notion / new_short_notion
            if ratio > self.max_directional_ratio:
                 return {"allowed": False, "reason": "DIRECTIONAL_RATIO_BREACH", "ratio": float(ratio), "max": float(self.max_directional_ratio)}

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
                item["margin"] if "margin" in item else 0 for item in self.state.pending_exposure.values()
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
            item["margin"] if "margin" in item else 0 for item in self.state.pending_exposure.values()
        )
        total_postfill = len(self.state.postfill_reservations)
        total_postfill_margin = sum(
            item["margin"] if "margin" in item else 0 for item in self.state.postfill_reservations.values()
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

        if not hasattr(self.soft_limit_config, "regime_adaptation"):
            return
        regime_adaptation = self.soft_limit_config.regime_adaptation
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
                    try:
                        coro.close()
                    except Exception:
                        pass
            except RuntimeError:
                # No event loop available, skip emission
                try:
                    coro.close()
                except Exception:
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
