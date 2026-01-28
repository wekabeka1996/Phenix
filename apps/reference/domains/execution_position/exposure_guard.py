"""
EXP-FIX: Exposure Guard with Portfolio Notional Hard Gate.

Implements fail-closed behavior when portfolio positions are stale/unknown,
and post-fill hold mechanism to prevent race conditions.
PHASE 2: Soft-limit clipping (clip instead of reject, min notional check).
EP-01: Regime-based risk adaptation using ExecutionRegimeBucket.
"""

from __future__ import annotations

import logging
import asyncio
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING, Union
from dataclasses import dataclass

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock

from apps.reference.telemetry.order_logger import order_logger
from apps.reference.domains.execution_position.soft_clip import (
    SoftClipEngine,
    SoftLimitConfig,
    load_soft_limit_config,
)
from apps.reference.domains.execution_position.metrics_aggregator import metrics_logger
from apps.reference.domain_config import DomainConfigResolver
from apps.reference.config_contract import ConfigContractError
from apps.reference.config_models import AuroraConfig
# EP-01: Import bucket enum for type-safe regime adaptation
from apps.reference.core.types.regime_types import ExecutionRegimeBucket


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
    risk_reduction_pct: Optional[Decimal] = None


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
        
        self.max_equity_utilization_pct = self._to_dec(eg_config.max_equity_utilization_pct, path="domains.execution_position.exposure_guard.max_equity_utilization_pct") / Decimal("100")
        self.max_portfolio_fraction = self._to_dec(eg_config.max_portfolio_fraction, path="domains.execution_position.exposure_guard.max_portfolio_fraction")
        self.max_long_utilization_pct = self._to_dec(eg_config.max_long_utilization_pct, path="domains.execution_position.exposure_guard.max_long_utilization_pct") / Decimal("100")
        self.max_short_utilization_pct = self._to_dec(eg_config.max_short_utilization_pct, path="domains.execution_position.exposure_guard.max_short_utilization_pct") / Decimal("100")
        self.max_concentration_pct = self._to_dec(eg_config.max_concentration_pct, path="domains.execution_position.exposure_guard.max_concentration_pct") / Decimal("100")

        # Directional ratio (legacy support)
        # Fail-closed: ExposureGuardConfig is strict and requires this field.
        self.max_directional_ratio = self._to_dec(eg_config.max_directional_ratio, path="domains.execution_position.exposure_guard.max_directional_ratio")

        # TTL configurations
        self.pending_ttl_sec = eg_config.pending_ttl_sec
        self.post_fill_hold_ttl_sec = eg_config.post_fill_ttl_sec
        self.positions_stale_ttl_sec = eg_config.stale_ttl_sec

        # Flags (strict typed config; fail-closed)
        execution_cfg = self.config.trading.execution
        if execution_cfg is None or execution_cfg.exposure is None:
            raise ConfigContractError(
                path="trading.execution.exposure",
                why="Missing required exposure config (expected count_pending_orders/exclude_reduce_only).",
            )
        self.count_pending_orders = bool(execution_cfg.exposure.count_pending_orders)
        self.exclude_reduce_only = bool(execution_cfg.exposure.exclude_reduce_only)

        # PHASE 2: Soft-limit configuration (read from trading.risk.soft_limits)
        self.soft_limit_config = self._load_soft_limit_config()
        self.soft_clip_engine = SoftClipEngine(
            self.soft_limit_config, logger=self.logger
        )
        # EP-01: Store original base ratio for regime adaptation (immutable reference)
        self._base_directional_ratio = self.soft_limit_config.directional_ratio_max

        # PHASE P0: Fallback mode configuration and state
        self.fallback_config = self._load_fallback_config()
        self.fallback_state = FallbackState(
            risk_reduction_pct=self.fallback_config["risk_reduction_pct"]
        )

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
        try:
            cfg = load_soft_limit_config(self.config.trading.risk)
        except Exception as e:
            raise ConfigContractError(path="trading.risk.soft_limits", why=str(e)) from e

        self.logger.info(
            "SOFT_LIMIT_CONFIG loaded: "
            f"mode={cfg.mode}, clip_min={cfg.clip_min_notional_usdt}, "
            f"dir_ratio_max={cfg.directional_ratio_max}, side_exp={cfg.side_exposure_usdt}, "
            f"margin_exp={cfg.margin_exposure_usdt}, "
            f"regime_adaptation={'yes' if cfg.regime_adaptation else 'no'}"
        )
        return cfg

    def _load_fallback_config(self) -> Dict[str, Any]:
        """
        P1: Load fallback mode configuration from domains.execution_position.fallback.
        Fail-closed: raises ConfigContractError if config missing.
        """
        fallback_cfg = getattr(
            getattr(self.config.domains, "execution_position", None),
            "fallback",
            None
        )
        
        if fallback_cfg is None:
            raise ConfigContractError(
                path="domains.execution_position.fallback",
                why="Fallback config is mandatory. Add fallback section to config/aurora/domains.yaml"
            )
        
        config = {
            "policy": fallback_cfg.policy,
            "risk_reduction_pct": self._to_dec(
                fallback_cfg.risk_reduction_pct,
                path="domains.execution_position.fallback.risk_reduction_pct",
                default_on_error=Decimal("0"),
            ),
            "backoff_ms": list(fallback_cfg.backoff_ms),
        }
        self.logger.info(
            f"FALLBACK_CONFIG loaded: policy={config['policy']}, risk_reduction_pct={config['risk_reduction_pct']}, backoff_ms={config['backoff_ms']}"
        )
        return config

    def _to_dec(self, val: Any, *, path: str, default_on_error: Optional[Decimal] = None) -> Decimal:
        """Convert to Decimal with fail-closed validation."""
        if val is None:
            if default_on_error is not None:
                self.logger.error("CONFIG_DECIMAL_MISSING: %s is None; defaulting to %s", path, default_on_error)
                return default_on_error
            self.logger.error("CONFIG_DECIMAL_MISSING: %s is None", path)
            raise ConfigContractError(path=path, why="Missing required decimal value")
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError) as e:
            if default_on_error is not None:
                self.logger.error("CONFIG_DECIMAL_INVALID: %s value=%r; defaulting to %s", path, val, default_on_error)
                return default_on_error
            self.logger.error("CONFIG_DECIMAL_INVALID: %s value=%r", path, val)
            raise ConfigContractError(path=path, why=f"Invalid decimal value: {val!r}") from e

    def enter_fallback_mode(self, reason: str) -> None:
        """
        PHASE P0: Enter fallback mode with specified reason.

        Args:
            reason: Reason for entering fallback mode (e.g., "API_TIMEOUT", "EMPTY_POSITIONS")
        """
        now_ms = get_clock().now_ms()

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
        now_ms = get_clock().now_ms()
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

        SSOT: instruments.<SYM>.execution.target_leverage (instruments.yaml)

        Args:
            symbol: Trading symbol

        Returns:
            Decimal: Leverage value (>= 1)

        Raises:
            ConfigContractError: If leverage not found in instruments.yaml (no silent defaults)
        """
        symbol = str(symbol or "").strip()
        if not symbol:
            raise ValueError("symbol is required")

        # SSOT: instruments.yaml (fail-closed, no fallback)
        instruments = getattr(self.config, "instruments", None)
        if instruments is None or not isinstance(instruments, dict):
            raise ConfigContractError(
                path="instruments",
                why=f"Missing instruments config for leverage resolution (symbol={symbol})"
            )

        spec = instruments.get(symbol)
        if spec is None:
            raise ConfigContractError(
                path=f"instruments.{symbol}",
                why=f"Symbol {symbol} not found in instruments.yaml"
            )

        exec_cfg = getattr(spec, "execution", None)
        if exec_cfg is None:
            raise ConfigContractError(
                path=f"instruments.{symbol}.execution",
                why=f"Missing execution config for {symbol}"
            )

        target = getattr(exec_cfg, "target_leverage", None)
        if target is None:
            raise ConfigContractError(
                path=f"instruments.{symbol}.execution.target_leverage",
                why=f"Missing target_leverage for {symbol} in instruments.yaml (no silent defaults)"
            )

        return max(Decimal(str(target)), Decimal("1"))

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
        self, symbol: str, notional_usd: Decimal, portfolio_state: Dict[str, Any], is_flip: bool = False
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
        
        Args:
            symbol: Symbol to check
            notional_usd: Requested order size (signed)
            portfolio_state: Current portfolio snapshot
            is_flip: Whether this order flips/closes an existing position (netting logic)
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
        stale_sec = get_clock().now_sec() - (last_ts_ms / 1000)
        if last_ts_ms == 0 or stale_sec > stale_ttl:
            return {"allowed": False, "reason": "PORTFOLIO_STALE", "stale_sec": float(stale_sec)}

        # --- 2. State Accumulation (SSOT: portfolio_state_v1) ---
        positions = portfolio_state.get("positions", [])
        if not isinstance(positions, list):
            positions = []

        # Open exposure SSOT (position_tracking emits these on every snapshot).
        open_positions_usd = _d(portfolio_state.get("open_positions_usd"))
        open_positions_margin_usd = _d(portfolio_state.get("open_positions_margin_usd"))
        
        # Calculate current symbol contribution for FLIP subtraction
        current_symbol_margin = Decimal("0")
        current_symbol_notional = Decimal("0")
        current_symbol_side = ""
        
        ref_leverage = self.resolve_symbol_leverage(symbol)
        
        for p in positions:
            if not isinstance(p, dict):
                continue
            if str(p.get("symbol", "")).strip() != symbol:
                continue
            qty = _d(p.get("net_position"))
            px = _d(p.get("avg_entry_price"))
            if qty == 0 or px <= 0:
                continue
            sym_notional = abs(qty) * px
            current_symbol_notional = sym_notional
            current_symbol_margin = sym_notional / ref_leverage if ref_leverage else Decimal("0")
            current_symbol_side = "BUY" if qty > 0 else "SELL"
            break

        # If producers ever omit aggregates, fall back to conservative reconstruction.
        if open_positions_usd <= 0 and positions:
            try:
                open_positions_usd = sum(
                    abs(_d(p.get("net_position"))) * _d(p.get("avg_entry_price"))
                    for p in positions
                    if isinstance(p, dict)
                )
            except Exception:
                open_positions_usd = Decimal("0")

        # Side margin SSOT (used for directional ratio + side utilization).
        long_margin = Decimal("0")
        short_margin = Decimal("0")
        pbs = portfolio_state.get("positions_by_side")
        if isinstance(pbs, dict):
            long_margin = _d(pbs.get("long_margin"))
            short_margin = _d(pbs.get("short_margin"))
        elif positions:
            # Conservative fallback: derive margin by side from net_position * avg_entry_price, using SSOT leverage.
            for p in positions:
                if not isinstance(p, dict):
                    continue
                p_sym = str(p.get("symbol", "") or "").strip()
                qty = _d(p.get("net_position"))
                px = _d(p.get("avg_entry_price"))
                if not p_sym or qty == 0 or px <= 0:
                    continue
                p_notional = abs(qty) * px
                p_lev = self.resolve_symbol_leverage(p_sym)
                p_margin = p_notional / p_lev if p_lev else Decimal("0")
                if qty > 0:
                    long_margin += p_margin
                else:
                    short_margin += p_margin

        # Pending exposure reservations (include/exclude based on config)
        def _include_pending(item: Dict[str, Any]) -> bool:
            if not self.count_pending_orders:
                return False
            if self.exclude_reduce_only and bool(item.get("reduce_only", False)):
                return False
            return True

        pending_long_m = sum(
            _d(item.get("margin"))
            for item in self.state.pending_exposure.values()
            if isinstance(item, dict) and _include_pending(item) and item.get("side") in {"BUY", "LONG"}
        )
        pending_short_m = sum(
            _d(item.get("margin"))
            for item in self.state.pending_exposure.values()
            if isinstance(item, dict) and _include_pending(item) and item.get("side") in {"SELL", "SHORT"}
        )
        pending_notional = sum(
            abs(_d(item.get("notional")))
            for item in self.state.pending_exposure.values()
            if isinstance(item, dict) and _include_pending(item)
        )

        # Post-fill holds always count as exposure until portfolio catches up (race-safe, conservative).
        now = get_clock().now_sec()
        post_long_m = sum(
            _d(item.get("margin"))
            for item in self.state.postfill_reservations.values()
            if isinstance(item, dict) and item.get("side") in {"BUY", "LONG"} and now < float(item.get("exp_ts", 0))
        )
        post_short_m = sum(
            _d(item.get("margin"))
            for item in self.state.postfill_reservations.values()
            if isinstance(item, dict) and item.get("side") in {"SELL", "SHORT"} and now < float(item.get("exp_ts", 0))
        )
        post_notional = sum(
            abs(_d(item.get("notional")))
            for item in self.state.postfill_reservations.values()
            if isinstance(item, dict) and now < float(item.get("exp_ts", 0))
        )

        total_pending_margin = pending_long_m + pending_short_m + post_long_m + post_short_m

        requested_notional_abs = abs(notional_usd)
        order_side = "BUY" if notional_usd >= Decimal("0") else "SELL"

        # --- 3. Soft-limit clipping (trading.risk.soft_limits) ---
        order_notional_abs = requested_notional_abs
        clip_payload: Dict[str, Any] = {}
        soft_mode = str(self.soft_limit_config.mode).lower()
        if soft_mode in {"clip", "reject"}:
            clip_res = self.soft_clip_engine.calculate_clipped_size(
                notional_usd=order_notional_abs,
                symbol=symbol,
                order_side=order_side,
                long_margin=long_margin + pending_long_m + post_long_m,
                short_margin=short_margin + pending_short_m + post_short_m,
                total_margin_exposure=open_positions_margin_usd + total_pending_margin,
                symbol_leverage=ref_leverage,
            )
            if not clip_res.allowed:
                return {
                    "allowed": False,
                    "reason": f"SOFT_LIMIT_{clip_res.reason}",
                    "clip_reasons": list(clip_res.clip_reasons),
                    "requested_notional": str(requested_notional_abs),
                }
            if clip_res.clipped_notional is not None and clip_res.clipped_notional < order_notional_abs:
                if soft_mode == "reject":
                    return {
                        "allowed": False,
                        "reason": "SOFT_LIMIT_REJECT",
                        "clip_reasons": list(clip_res.clip_reasons),
                        "requested_notional": str(requested_notional_abs),
                        "max_allowed_notional": str(clip_res.clipped_notional),
                    }
                order_notional_abs = clip_res.clipped_notional
                clip_payload = {
                    "clipped": True,
                    "requested_notional_abs": str(requested_notional_abs),
                    "clipped_notional_abs": str(order_notional_abs),
                    "clip_reasons": list(clip_res.clip_reasons),
                    "original_notional": str(requested_notional_abs) # Helpful debug
                }

        # --- 4. Hard Limit Enforcement (domains.execution_position.exposure_guard) ---
        order_margin = order_notional_abs / ref_leverage if ref_leverage else Decimal("0")

        # A) Max Portfolio Fraction (NOTIONAL-based, projected)
        projected_notional = open_positions_usd + pending_notional + post_notional + order_notional_abs
        if is_flip:
            projected_notional -= current_symbol_notional # Subtract current position notional
            
        p_frac_limit = equity_free_usdt * self.max_portfolio_fraction
        if projected_notional > p_frac_limit:
            return {
                "allowed": False,
                "reason": "PORTFOLIO_FRACTION_BREACH",
                "projected_notional": float(projected_notional),
                "limit": float(p_frac_limit),
            }

        # B) Max Equity Utilization (MARGIN-based, projected)
        total_margin_used = open_positions_margin_usd + total_pending_margin + order_margin
        if is_flip:
            total_margin_used -= current_symbol_margin # Subtract current position margin
            
        equity_margin_limit = equity_free_usdt * self.max_equity_utilization_pct
        if total_margin_used > equity_margin_limit:
            return {
                "allowed": False,
                "reason": "EQUITY_UTILIZATION_BREACH",
                "actual": float(total_margin_used),
                "limit": float(equity_margin_limit),
            }

        # C) Long/Short Utilization (MARGIN-based)
        new_long_m = long_margin + pending_long_m + post_long_m + (order_margin if order_side == "BUY" else Decimal("0"))
        new_short_m = short_margin + pending_short_m + post_short_m + (order_margin if order_side == "SELL" else Decimal("0"))
        
        if is_flip:
             if current_symbol_side == "BUY":
                 new_long_m -= current_symbol_margin
             elif current_symbol_side == "SELL":
                 new_short_m -= current_symbol_margin

        long_limit = equity_free_usdt * self.max_long_utilization_pct
        short_limit = equity_free_usdt * self.max_short_utilization_pct

        if new_long_m > long_limit:
            return {"allowed": False, "reason": "LONG_UTILIZATION_BREACH", "actual": float(new_long_m), "limit": float(long_limit)}
        if new_short_m > short_limit:
            return {"allowed": False, "reason": "SHORT_UTILIZATION_BREACH", "actual": float(new_short_m), "limit": float(short_limit)}

        # D) Directional Ratio (MARGIN-based)
        min_m = min(new_long_m, new_short_m)
        if min_m > Decimal("0"):
            ratio = max(new_long_m, new_short_m) / min_m
            if ratio > self.max_directional_ratio:
                return {"allowed": False, "reason": "DIRECTIONAL_RATIO_BREACH", "ratio": float(ratio), "max": float(self.max_directional_ratio)}

        # E) Concentration (per-symbol margin cap)
        # Use simple aggregation + net logic
        symbol_margin_est = Decimal("0")
        if not is_flip and current_symbol_margin > 0:
             symbol_margin_est = current_symbol_margin
        # If is_flip is True, we essentially assume 'symbol_margin_est' becomes 0 
        # (replaced by order_margin) or we enforce the strict subtraction logic.
        # Since 'current_symbol_margin' was calculated at the top, we just don't add it here if is_flip is True
        
        # Pending symbol margin
        pending_symbol_m = sum(
            _d(item.get("margin"))
            for item in self.state.pending_exposure.values()
            if isinstance(item, dict) and _include_pending(item) and str(item.get("symbol", "")).strip() == symbol
        )
        post_symbol_m = sum(
            _d(item.get("margin"))
            for item in self.state.postfill_reservations.values()
            if isinstance(item, dict) and str(item.get("symbol", "")).strip() == symbol and now < float(item.get("exp_ts", 0))
        )

        projected_symbol_margin = symbol_margin_est + pending_symbol_m + post_symbol_m + order_margin
        concentration_limit = equity_free_usdt * self.max_concentration_pct
        if projected_symbol_margin > concentration_limit:
            return {
                "allowed": False,
                "reason": "CONCENTRATION_BREACH",
                "projected_symbol_margin": float(projected_symbol_margin),
                "limit": float(concentration_limit),
            }

        out: Dict[str, Any] = {"allowed": True}
        out.update(clip_payload)
        return out

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
        now = get_clock().now_sec()

        symbol = str(symbol or "").strip()
        if not symbol:
            raise ValueError("ExposureGuard.reserve requires non-empty symbol")

        side = str(side or "").upper()
        allowed_sides = {"BUY", "SELL", "LONG", "SHORT"}
        if side not in allowed_sides:
            raise ValueError(f"Invalid order side: '{side}'. Expected one of {allowed_sides}")

        # Idempotency: do not create duplicate reservations/log entries for same key.
        if key in self.state.pending_exposure or key in self.state.reservations:
            self.logger.debug(f"EXPOSURE_RESERVE_IDEMPOTENT: key={key} already reserved")
            return

        # Calculate reserve margin
        symbol_leverage = self.resolve_symbol_leverage(symbol)
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
            "symbol": symbol,
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
        if not symbol:
            symbol = str(self.state.pending_exposure.get(key, {}).get("symbol", "") or "").strip()
        side = str(side or self.state.pending_exposure.get(key, {}).get("side", "SELL")).upper()
        allowed_sides = {"BUY", "SELL", "LONG", "SHORT"}
        if side not in allowed_sides:
            raise ValueError(f"Invalid order side: '{side}'. Expected one of {allowed_sides}")

        if key in self.state.reservations:
            # Calculate filled margin
            symbol_leverage = self.resolve_symbol_leverage(
                symbol) if symbol else Decimal("1")
            filled_margin = notional_usd / symbol_leverage

            # Move to post-fill hold instead of releasing
            expiration_ts = get_clock().now_sec() + self.post_fill_hold_ttl_sec
            self.state.postfill_reservations[key] = {
                "notional": notional_usd,
                "margin": filled_margin,
                "leverage": symbol_leverage,
                "exp_ts": expiration_ts,
                "symbol": symbol,
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
        now = get_clock().now_sec()
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

    def on_regime_changed(self, bucket: Union[ExecutionRegimeBucket, str]) -> None:
        """
        EP-01: Regime adaptation - update directional ratio based on market regime bucket.

        Args:
            bucket: ExecutionRegimeBucket enum (preferred) or legacy string.
                    TREND_UP, TREND_DOWN → apply trend delta (more aggressive)
                    FLAT → apply flat_delta (more conservative, reduce exposure)
                    VOLATILE → apply flat_delta (tighten limits during high vol)
                    UNCERTAIN → apply flat_delta (conservative fallback)
        """
        regime_adaptation = self.soft_limit_config.regime_adaptation
        if not regime_adaptation:
            return

        # EP-01: Convert string to enum if needed (backward compatibility)
        if isinstance(bucket, str):
            try:
                bucket = ExecutionRegimeBucket(bucket)
            except ValueError:
                self.logger.warning(f"EP-01: Unknown regime bucket string '{bucket}', treating as UNCERTAIN")
                bucket = ExecutionRegimeBucket.UNCERTAIN

        # EP-01: Use immutable base ratio, not the mutable soft_limit_config value
        base_ratio = self._base_directional_ratio
        bounds = regime_adaptation.bounds if regime_adaptation.bounds else [2.0, 4.0]

        delta = Decimal("0")
        if bucket == ExecutionRegimeBucket.TREND_UP:
            delta = Decimal(str(regime_adaptation.trend_up_delta)
                            ) if regime_adaptation.trend_up_delta else Decimal("0")
        elif bucket == ExecutionRegimeBucket.TREND_DOWN:
            delta = Decimal(str(regime_adaptation.trend_down_delta)
                            ) if regime_adaptation.trend_down_delta else Decimal("0")
        elif bucket in (ExecutionRegimeBucket.FLAT, ExecutionRegimeBucket.VOLATILE, ExecutionRegimeBucket.UNCERTAIN):
            # EP-01: FLAT (mean-reversion), VOLATILE (high-vol), UNCERTAIN → all use flat_delta (conservative)
            delta = Decimal(str(regime_adaptation.flat_delta)
                            ) if regime_adaptation.flat_delta else Decimal("0")

        new_ratio = max(
            Decimal(str(bounds[0])),
            min(
                Decimal(str(bounds[1])),
                base_ratio + delta
            )
        )

        # Soft-limit directional ratio (used by SoftClipEngine).
        self.soft_limit_config.directional_ratio_max = new_ratio
        # EP-01: Also update instance attribute for direct access
        self.max_directional_ratio = new_ratio
        self.logger.info(
            f"EP-01 REGIME_ADAPTED: bucket={bucket.value} → directional_ratio_max={float(new_ratio):.2f} "
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
