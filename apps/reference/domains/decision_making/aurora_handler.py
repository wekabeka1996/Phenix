"""
AuroraHandler — Stateful Strategy Handler for Aurora.

This module wraps the pure AuroraScoringKernel with state management for:
1. Regime caching (from EVT:REGIME_DETECTED)
2. Warmup tracking
3. Side bias history

Responsibilities:
- Listen to tick/feature events
- Maintain per-symbol state
- Call scoring kernel with current state
- Emit EVT:STRATEGY_SIGNAL_PRODUCED
"""
from __future__ import annotations

import decimal
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    AuroraScoringKernel,
    ScoringResult,
    SideBiasState,
)
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.trade_intent_reject_wal import write_trade_intent_rejected


logger = logging.getLogger("aurora_handler")


@dataclass
class SymbolState:
    """Per-symbol state for Aurora handler."""
    
    # Regime cache (from EVT:REGIME_DETECTED)
    regime: Optional[str] = None
    regime_confidence: float = 0.0
    regime_ts_ms: int = 0

    # Anti-churn regime inertia (monotonic timebase)
    regime_raw: Optional[str] = None
    regime_effective: Optional[str] = None
    regime_raw_change_ts: Optional[float] = None
    
    # DM-CRITICAL-PATCHES-02: Liveness heartbeat tracking
    # Updated on EVERY EVT:REGIME_DETECTED (even if changed=False)
    last_regime_heartbeat_ms: Optional[int] = None
    
    # Warmup state
    warmup_full_ready: bool = False
    warmup_ticks_seen: int = 0
    
    # Side bias history (timestamps)
    buy_timestamps: List[float] = field(default_factory=list)
    sell_timestamps: List[float] = field(default_factory=list)
    
    # Last signal state
    last_signal_ts_ms: int = 0
    last_signal_side: str = ""
    
    # Holding period state (Anti-Churn)
    entry_timestamp: Optional[float] = None  # Time when position was opened
    position_side: str = ""                   # Current position side ("buy"/"sell")
    
    # Re-entry cooldown state (Anti-Ping-Pong)
    last_exit_timestamp: Optional[float] = None  # Time when position was closed
    
    # P0-3: Cached price_motion from EVT:FEATURES_CALCULATED
    # CMD:PROCESS_STRATEGY does not include price_motion, so we cache it here
    cached_price_motion: Optional[Dict[str, Any]] = None


class AuroraHandler:
    """
    Stateful Aurora strategy handler.
    
    Lifecycle:
    1. Initialize with config
    2. Listen to EVT:REGIME_DETECTED, EVT:FEATURES_CALCULATED
    3. On features: call kernel, emit signal if actionable
    
    The handler is responsible for:
    - Caching regime state
    - Tracking warmup
    - Managing side bias window
    - Calling pure scoring kernel
    - Emitting signals with readiness contract
    """
    
    def __init__(
        self,
        *,
        config: Any,
        emit_fn: Callable[[str, Dict[str, Any]], None],
        strategy_id: str = "aurora",
        monotonic_fn: Callable[[], float] | None = None,
        wall_time_fn: Callable[[], float] | None = None,
    ):
        """
        Initialize Aurora handler.
        
        Args:
            config: Strategy configuration object
            emit_fn: Function to emit events (from FSM)
            strategy_id: Handler's strategy identifier
        """
        self.config = config
        self.emit_fn = emit_fn
        self.strategy_id = strategy_id
        self.logger = logging.getLogger(f"aurora_handler.{strategy_id}")

        # Timebase separation:
        # - monotonic_fn(): durations / cooldowns / holding windows
        # - wall_time_fn(): epoch-based timestamps (ts_ms)
        self.monotonic_fn: Callable[[], float] = monotonic_fn or time.monotonic
        self.wall_time_fn: Callable[[], float] = wall_time_fn or time.time
        
        # Dependency Injection / Testability
        self.scoring_kernel_cls = AuroraScoringKernel
        
        # Per-symbol state
        self._symbol_states: Dict[str, SymbolState] = defaultdict(SymbolState)
        
        # T2B-01: Tick-path rejection counter for observability
        self._tick_path_rejections: int = 0
        
        # Config extraction
        self._load_config()
    
    def _load_config(self) -> None:
        """Extract configuration parameters."""
        aurora_cfg = getattr(self.config, "strategies", None)
        aurora = getattr(aurora_cfg, "aurora", None) if aurora_cfg else None

        # FeatureEngineering warmup enforcement mode (used for readiness fail-closed behavior).
        # Default is fail_fast to preserve live safety if config can't be resolved.
        self._fe_warmup_enforcement_mode: str = "fail_fast"
        try:
            from apps.reference.config_models import AuroraConfig
            from apps.reference.domain_config import DomainConfigResolver

            if isinstance(self.config, AuroraConfig):
                fe_cfg = DomainConfigResolver(self.config).get_feature_engineering()
                warmup_cfg = getattr(fe_cfg, "warmup", None)
                if warmup_cfg is not None:
                    self._fe_warmup_enforcement_mode = str(getattr(warmup_cfg, "enforcement_mode", "fail_fast"))
        except Exception:
            self._fe_warmup_enforcement_mode = "fail_fast"
        
        # TF-SSOT-PACK-003: Get timeframe_sec from config (MANDATORY)
        # CLOSEOUT-BASELINE-001: Strict contract - no fallbacks
        if aurora is None:
            # Aurora strategy not enabled - use sentinel that will be rejected by guards
            self.timeframe_sec = 0
            self.logger.debug("AuroraHandler: aurora strategy not configured, timeframe_sec=0 (sentinel)")
        elif not hasattr(aurora, "timeframe_sec") or aurora.timeframe_sec is None:
            from apps.reference.config_contract import ConfigContractError
            raise ConfigContractError(
                path="strategies.aurora.timeframe_sec",
                why="timeframe_sec is mandatory in strategy config. Check config/aurora/strategies/aurora.yaml"
            )
        else:
            self.timeframe_sec = aurora.timeframe_sec
        
        decision = getattr(aurora, "decision", None) if aurora else None
        
        if decision:
            self.signal_threshold = decimal.Decimal(str(getattr(decision, "signal_threshold", "0.1")))
            self.side_bias_window_sec = float(getattr(decision, "side_bias_window_sec", 420))
            self.side_bias_target_ratio = float(getattr(decision, "side_bias_target_ratio", 0.72))
            self.side_bias_penalty_factor = float(getattr(decision, "side_bias_penalty_factor", 0.25))
            self.side_bias_min_intents = int(getattr(decision, "side_bias_min_intents", 18))
            self.regime_thresholds = getattr(decision, "regime_threshold_multipliers", {"DEFAULT": 1.0})
            
            # Direction strength config
            ds_cfg = getattr(decision, "direction_strength_scoring", None)
            self.direction_strength_cfg = {
                "directional_features": list(getattr(ds_cfg, "directional_features", [])) if ds_cfg else [],
                "strength_features": list(getattr(ds_cfg, "strength_features", [])) if ds_cfg else [],
                "strength_alpha": float(getattr(ds_cfg, "strength_alpha", 0.5)) if ds_cfg else 0.5,
                "strength_cap": float(getattr(ds_cfg, "strength_cap", 1.5)) if ds_cfg else 1.5,
            }
            
            # Signals config
            signals = getattr(decision, "signals", None)
            self.delta_price_cap_pct = decimal.Decimal(str(getattr(signals, "delta_price_cap_pct", "0.005"))) if signals else decimal.Decimal("0.005")
            
            # Neutral threshold for hysteresis (global default)
            nt_raw = getattr(decision, "neutral_threshold", None)
            self.neutral_threshold = decimal.Decimal(str(nt_raw)) if nt_raw is not None else decimal.Decimal("0.05")
            
            # === Holding Period Config (Anti-Churn) ===
            hp_cfg = getattr(decision, "holding_period", None)
            if hp_cfg and getattr(hp_cfg, "enabled", False):
                self.holding_period_enabled = True
                self.default_min_duration_sec = float(getattr(hp_cfg, "min_duration_sec", 30))
                self.default_emergency_threshold = float(getattr(hp_cfg, "emergency_exit_threshold", 0.7))
                self.holding_apply_to_flips = bool(getattr(hp_cfg, "apply_to_flips", True))
                self.logger.info(
                    f"Holding period enabled: min_duration={self.default_min_duration_sec}s, "
                    f"emergency_threshold={self.default_emergency_threshold}, apply_to_flips={self.holding_apply_to_flips}"
                )
            else:
                self.holding_period_enabled = False
                self.default_min_duration_sec = 30.0
                self.default_emergency_threshold = 0.7
                self.holding_apply_to_flips = True
            
            # === Re-entry Cooldown Config (Anti-Ping-Pong) ===
            rc_raw = getattr(decision, "reentry_cooldown_sec", None)
            self.default_reentry_cooldown_sec = float(rc_raw) if rc_raw is not None else 60.0
            self.logger.info(f"Re-entry cooldown: default={self.default_reentry_cooldown_sec}s")

            # === Anti-Churn: Time Multipliers + Regime Inertia ===
            ac_cfg = getattr(decision, "anti_churn", None)
            if ac_cfg and getattr(ac_cfg, "enabled", False):
                self.anti_churn_enabled = True
                self.time_multipliers = dict(getattr(ac_cfg, "time_multipliers", {}) or {})

                ri_cfg = getattr(ac_cfg, "regime_inertia", None)
                self.regime_inertia_confirm_window_sec = float(getattr(ri_cfg, "confirm_window_sec", 0.0)) if ri_cfg else 0.0
                self.regime_inertia_confirm_window_same_severity_sec = float(
                    getattr(ri_cfg, "confirm_window_same_severity_sec", 0.0)
                ) if ri_cfg else 0.0
                self.regime_inertia_immediate_risk_off = bool(getattr(ri_cfg, "immediate_risk_off", True)) if ri_cfg else True
                self.regime_severity_map = dict(getattr(ri_cfg, "severity_map", {}) or {})
            else:
                self.anti_churn_enabled = False
                self.time_multipliers = {}
                self.regime_inertia_confirm_window_sec = 0.0
                self.regime_inertia_confirm_window_same_severity_sec = 0.0
                self.regime_inertia_immediate_risk_off = True
                self.regime_severity_map = {}
            
            # === Vol-Adj Gates Config (Anti-Flat / Anti-FOMO) ===
            gates_cfg = getattr(decision, "gates", None)
            if gates_cfg and getattr(gates_cfg, "enabled", True):
                self.vol_gates_enabled = True
                self.anti_flat_sigma = float(getattr(gates_cfg, "anti_flat_sigma", 0.5))
                self.anti_fomo_sigma = float(getattr(gates_cfg, "anti_fomo_sigma", 4.0))
                self.motion_window_sec = int(getattr(gates_cfg, "motion_window_sec", 900))
                self.logger.info(
                    f"Vol-Adj Gates enabled: anti_flat_sigma={self.anti_flat_sigma}, "
                    f"anti_fomo_sigma={self.anti_fomo_sigma}, motion_window={self.motion_window_sec}s"
                )
            else:
                self.vol_gates_enabled = False
                self.anti_flat_sigma = 0.5
                self.anti_fomo_sigma = 4.0
                self.motion_window_sec = 900
        else:
            # Defaults
            self.signal_threshold = decimal.Decimal("0.1")
            self.side_bias_window_sec = 420.0
            self.side_bias_target_ratio = 0.72
            self.side_bias_penalty_factor = 0.25
            self.side_bias_min_intents = 18
            self.regime_thresholds = {"DEFAULT": 1.0}
            self.direction_strength_cfg = {}
            self.delta_price_cap_pct = decimal.Decimal("0.005")
            self.neutral_threshold = decimal.Decimal("0.05")
            # Holding period defaults (disabled)
            self.holding_period_enabled = False
            self.default_min_duration_sec = 30.0
            self.default_emergency_threshold = 0.7
            self.holding_apply_to_flips = True
            self.default_reentry_cooldown_sec = 60.0
            # Vol-Adj Gates defaults (disabled)
            self.vol_gates_enabled = False
            self.anti_flat_sigma = 0.5
            self.anti_fomo_sigma = 4.0
            self.motion_window_sec = 900

            # Anti-churn defaults (disabled)
            self.anti_churn_enabled = False
            self.time_multipliers = {}
            self.regime_inertia_confirm_window_sec = 0.0
            self.regime_inertia_confirm_window_same_severity_sec = 0.0
            self.regime_inertia_immediate_risk_off = True
            self.regime_severity_map = {}

    def _get_time_multiplier(self, regime: Optional[str]) -> float:
        if not getattr(self, "anti_churn_enabled", False):
            return 1.0
        if not regime:
            return 1.0
        try:
            return float(self.time_multipliers.get(regime, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _get_regime_severity(self, regime: Optional[str]) -> int:
        if not regime:
            return 0
        try:
            return int(self.regime_severity_map.get(regime, 0))
        except (TypeError, ValueError):
            return 0

    def _update_effective_regime(self, symbol: str, raw_regime: Optional[str]) -> None:
        """Apply regime inertia: immediate risk-off, delayed risk-on (monotonic timebase)."""
        state = self._symbol_states[symbol]
        now = float(self.monotonic_fn())

        if state.regime_raw is None and state.regime_effective is None:
            state.regime_raw = raw_regime
            state.regime_effective = raw_regime
            state.regime_raw_change_ts = now
            return

        if raw_regime != state.regime_raw:
            state.regime_raw = raw_regime
            state.regime_raw_change_ts = now

        if not getattr(self, "anti_churn_enabled", False) or self.regime_inertia_confirm_window_sec <= 0.0:
            state.regime_effective = state.regime_raw
            return

        current_eff = state.regime_effective
        raw = state.regime_raw
        if raw == current_eff:
            return

        eff_sev = self._get_regime_severity(current_eff)
        raw_sev = self._get_regime_severity(raw)

        if self.regime_inertia_immediate_risk_off and raw_sev > eff_sev:
            state.regime_effective = raw
            return

        if raw_sev == eff_sev and self.regime_inertia_confirm_window_same_severity_sec > 0.0:
            raw_change_ts = state.regime_raw_change_ts
            if raw_change_ts is None:
                state.regime_effective = raw
                return
            if (now - raw_change_ts) >= self.regime_inertia_confirm_window_same_severity_sec:
                state.regime_effective = raw
            return

        raw_change_ts = state.regime_raw_change_ts
        if raw_change_ts is None:
            state.regime_effective = raw
            return
        if (now - raw_change_ts) >= self.regime_inertia_confirm_window_sec:
            state.regime_effective = raw

    def _check_regime_liveness(
        self,
        symbol: str,
        state: SymbolState,
    ) -> Optional[Dict[str, Any]]:
        """
        DM-CRITICAL-PATCHES-02: Check if RegimeDetector is still alive (heartbeat-based).
        
        Block trading if:
        1. No heartbeat ever received (last_regime_heartbeat_ms is None)
        2. Heartbeat is stale (> basis_tf_sec * liveness_factor)
        
        Returns:
            None if liveness OK
            Dict with reason_code/why/details if blocked
        """
        # Fail-closed: no heartbeat ever → block
        if state.last_regime_heartbeat_ms is None:
            return {
                "reason_code": "NRR-REGIME-NO-HEARTBEAT",
                "why": "Regime detector heartbeat never received (fail-closed)",
                "details": {"last_regime_heartbeat_ms": None},
            }
        
        # Get liveness config from SSOT
        try:
            basis_tf_sec = int(self.config.basis_tf_sec)
            liveness_factor = int(getattr(self.config, "liveness_factor", 3))
        except (AttributeError, TypeError):
            # Config not available - use safe defaults and log
            basis_tf_sec = 300
            liveness_factor = 3
            self.logger.warning(
                f"[{symbol}] Liveness guard using fallback: basis_tf_sec={basis_tf_sec}, factor={liveness_factor}"
            )
        
        max_delay_ms = basis_tf_sec * 1000 * liveness_factor
        now_ms = int(self.monotonic_fn() * 1000)
        delta_ms = now_ms - state.last_regime_heartbeat_ms
        
        if delta_ms > max_delay_ms:
            self.logger.warning(
                f"[{symbol}] LIVENESS BLOCK: Regime heartbeat stale - "
                f"delta={delta_ms}ms > max={max_delay_ms}ms (basis={basis_tf_sec}s * factor={liveness_factor})"
            )
            return {
                "reason_code": "NRR-REGIME-DETECTOR-DEAD",
                "why": f"Regime detector heartbeat stale: {delta_ms}ms > {max_delay_ms}ms",
                "details": {
                    "last_regime_heartbeat_ms": state.last_regime_heartbeat_ms,
                    "delta_ms": delta_ms,
                    "max_delay_ms": max_delay_ms,
                    "basis_tf_sec": basis_tf_sec,
                    "liveness_factor": liveness_factor,
                },
            }
        
        return None  # Liveness OK

    def _emit_strategy_blocked(
        self,
        *,
        symbol: str,
        reason_code: str,
        reason: str,
        context: str,
        details: dict | None = None,
        why_chain: list[str] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "reason_code": str(reason_code),
            "reason": str(reason),
            "context": str(context),
            "ts_ms": int(self.wall_time_fn() * 1000),
            "why_chain": list(why_chain or []),
        }
        if details:
            payload["details"] = details
        self.emit_fn("EVT:STRATEGY_DECISION_BLOCKED", payload)
    
    def on_regime_detected(self, event: Dict[str, Any]) -> None:
        """
        Handle EVT:REGIME_DETECTED event.
        
        Updates cached regime state for symbol.
        DM-CRITICAL-PATCHES-02: Always updates heartbeat timestamp (even if changed=False).
        """
        symbol = event.get("symbol")
        if not symbol:
            return
        
        state = self._symbol_states[symbol]
        state.regime = event.get("regime")
        state.regime_confidence = float(event.get("confidence", 0.0))
        state.regime_ts_ms = int(event.get("ts_ms", int(self.wall_time_fn() * 1000)))

        # DM-CRITICAL-PATCHES-02: Update heartbeat on EVERY regime event (liveness tracking)
        # Use last_update_ts_ms from payload if available, else use monotonic clock
        heartbeat_ts = event.get("last_update_ts_ms")
        if heartbeat_ts is not None:
            state.last_regime_heartbeat_ms = int(heartbeat_ts)
        else:
            state.last_regime_heartbeat_ms = int(self.monotonic_fn() * 1000)

        if getattr(self, "anti_churn_enabled", False):
            self._update_effective_regime(symbol, state.regime)
        
        # Update warmup from regime event if present
        warmup = event.get("warmup", {})
        state.warmup_full_ready = bool(warmup.get("full_ready", False))
        state.warmup_ticks_seen = int(warmup.get("ticks_seen", 0))
        
        changed = event.get("changed", True)  # Default True for backward compat
        self.logger.debug(
            f"[{symbol}] Regime cached: {state.regime} (confidence={state.regime_confidence:.2f}, changed={changed})"
        )
    
    # =========================================================================
    # T2B-03: CMD:PROCESS_STRATEGY - Primary Entry Point
    # =========================================================================
    
    def on_process_strategy(self, cmd: Dict[str, Any]) -> None:
        """
        T2B-03: Handle CMD:PROCESS_STRATEGY command.
        
        This is the PRIMARY entry point for Aurora decision making.
        Strategies are triggered ONLY by this command (orchestrated by FE).
        
        Payload contract (from cmd_process_strategy_v1.json):
        - symbol: str
        - tf_sec: int (required, must match self.timeframe_sec)
        - bar_close_ts: int (required)
        - bar: dict (OHLCV)
        - features: dict
        - warmup: dict
        - regime: dict | None
        """
        symbol = cmd.get("symbol")
        if not symbol:
            return
        
        # T2B-03: STRICT FAIL-CLOSED TF GATE
        tf_sec = cmd.get("tf_sec")
        
        # Gate 1: Missing tf_sec → REJECT
        if tf_sec is None:
            self._tick_path_rejections += 1
            self.logger.warning(
                f"REJECTED: Aurora CMD for {symbol}: tf_sec is None (missing)"
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=None,
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY missing tf_sec (fail-closed)",
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
            )
            return
        
        # Gate 2: tf_sec=0 → REJECT (should never happen in CMD, but fail-closed)
        if tf_sec == 0:
            self._tick_path_rejections += 1
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=0,
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY tf_sec=0 forbidden (fail-closed)",
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
            )
            return
        
        # Gate 3: Wrong timeframe → REJECT
        if tf_sec != self.timeframe_sec:
            # Not our timeframe, silently skip (other strategies may handle it)
            return
        
        # Gate 4: Missing bar_close_ts → REJECT
        bar_close_ts = cmd.get("bar_close_ts")
        if not bar_close_ts:
            self._tick_path_rejections += 1
            self.logger.warning(
                f"REJECTED: Aurora CMD for {symbol}: bar_close_ts missing"
            )
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(tf_sec) if tf_sec is not None else None,
                bar_close_ts=None,
                reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                stage="STRATEGY",
                why="CMD:PROCESS_STRATEGY missing bar_close_ts (fail-closed)",
                src="aurora_handler",
                rid=cmd.get("rid"),
            )
            return
        
        # Delegate to internal processing
        self._process_decision(symbol, cmd)
    
    def on_features_data_only(self, event: Dict[str, Any]) -> None:
        """
        T2B-03: Data-only handler for EVT:FEATURES_CALCULATED.
        
        Updates warmup state cache but does NOT trigger decision.
        Decision is now triggered exclusively by CMD:PROCESS_STRATEGY.
        
        P0-3: Also caches price_motion since CMD:PROCESS_STRATEGY doesn't include it.
        """
        symbol = event.get("symbol")
        if not symbol:
            return
        
        # Only cache warmup state (no decision trigger)
        warmup = event.get("warmup", {})
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))
        state.warmup_ticks_seen = int(warmup.get("ticks_seen", 0))
        
        # P0-3: Cache price_motion for vol-adj gates
        # CMD:PROCESS_STRATEGY does not include price_motion, only EVT:FEATURES_CALCULATED
        price_motion = event.get("price_motion")
        if price_motion:
            state.cached_price_motion = price_motion
    
    def on_features_calculated(self, event: Dict[str, Any]) -> None:
        """
        DEPRECATED: Handle EVT:FEATURES_CALCULATED event.
        
        T2B-03: This method is DEPRECATED. Decision is now triggered by
        CMD:PROCESS_STRATEGY. This method is kept for backwards compatibility
        but will be removed in future versions.
        
        Use on_process_strategy() instead.
        """
        # T2B-03: Delegate to data-only handler (no decision trigger)
        self.on_features_data_only(event)
    
    def _process_decision(self, symbol: str, cmd: Dict[str, Any]) -> None:
        """
        Internal: Process decision logic after CMD:PROCESS_STRATEGY validation.
        
        This contains the core scoring kernel and signal emission logic.
        """
        # Check if symbol is enabled for Aurora
        if not self._is_symbol_enabled(symbol):
            return
        
        # Get instrument config
        instr_cfg = self._get_instrument_config(symbol)
        if not instr_cfg:
            return
        
        # Extract features and readiness from CMD payload
        features = cmd.get("features", {})
        warmup = cmd.get("warmup", {})
        warmup_readiness = warmup.get("ready", {})
        
        # Update warmup state
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))
        
        # Check warmup readiness (fail-closed)
        if not state.warmup_full_ready:
            mode = str(getattr(self, "_fe_warmup_enforcement_mode", "fail_fast"))
            if mode == "fail_fast":
                self.logger.debug(f"[{symbol}] Warmup not ready, skipping (mode=fail_fast)")
                write_trade_intent_rejected(
                    symbol=symbol,
                    tf_sec=int(cmd.get("tf_sec") or 0),
                    bar_close_ts=cmd.get("bar_close_ts"),
                    reason_code=NormalizedRejectReasons.FEATURES_NOT_READY,
                    stage="STRATEGY",
                    why="Warmup not full_ready (fail-closed; enforcement_mode=fail_fast)",
                    src="aurora_handler",
                    ts_ms=cmd.get("bar_close_ts"),
                    rid=cmd.get("rid"),
                )
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="READINESS_FE_WARMUP_NOT_READY",
                    reason="READINESS",
                    context="aurora_handler:_process_decision",
                    details={"warmup_full_ready": False, "enforcement_mode": mode},
                    why_chain=["READINESS", "warmup_full_ready:false", f"enforcement_mode:{mode}"],
                )
                return

            # warn_only / disabled: allow decision processing to proceed in degraded mode
            self.logger.debug(
                f"[{symbol}] Warmup not ready, continuing (enforcement_mode={mode})"
            )
        
        # DM-CRITICAL-PATCHES-02: Regime liveness guard
        # Block trading if RegimeDetector heartbeat is stale (detector may be dead)
        liveness_block = self._check_regime_liveness(symbol, state)
        if liveness_block is not None:
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=int(cmd.get("tf_sec") or 0),
                bar_close_ts=cmd.get("bar_close_ts"),
                reason_code=liveness_block["reason_code"],
                stage="STRATEGY",
                why=liveness_block["why"],
                src="aurora_handler",
                ts_ms=cmd.get("bar_close_ts"),
                rid=cmd.get("rid"),
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=liveness_block["reason_code"],
                reason="LIVENESS",
                context="aurora_handler:regime_liveness_guard",
                details=liveness_block.get("details", {}),
                why_chain=["LIVENESS", liveness_block["reason_code"]],
            )
            return
        
        # Get price
        price = features.get("price")
        if price is None:
            self.logger.warning(f"[{symbol}] Missing price in features")
            return
        price_dec = decimal.Decimal(str(price))
        
        # Get config for this symbol
        signal_weights = self._get_signal_weights(symbol, instr_cfg)
        feature_neutrals = self._get_feature_neutrals(symbol, instr_cfg)
        essential_features = self._get_essential_features(symbol, instr_cfg)
        
        # Build side bias state
        side_bias = self._get_side_bias_state(symbol)

        # === [SAFETY PATCH: ANCHOR SHOCK VETO (pre-check)] ===
        # We pre-load veto config and macro_resid once to avoid any crash/dup work.
        veto_cfg = None
        veto_anchor_symbol = "BTCUSDT"
        veto_threshold: float | None = None
        veto_macro_resid: float | None = None
        veto_applicable = False
        try:
            decision_cfg = getattr(self.config.strategies.aurora, "decision", None)
            veto_cfg = getattr(decision_cfg, "anchor_shock_veto", None) if decision_cfg else None
            if veto_cfg and getattr(veto_cfg, "enabled", False):
                veto_anchor_symbol = getattr(veto_cfg, "anchor_symbol", "BTCUSDT")
                veto_threshold = float(getattr(veto_cfg, "threshold", -2.0))
                veto_applicable = symbol != veto_anchor_symbol
                if veto_applicable:
                    macro_val = features.get("macro_resid")
                    if macro_val is not None:
                        veto_macro_resid = float(macro_val)
        except Exception as e:
            self.logger.warning(f"[{symbol}] Veto check warning: {e}")
            veto_cfg = None
            veto_threshold = None
            veto_macro_resid = None
            veto_applicable = False
        # =========================================
        
        # === [PATCH: PER-SYMBOL THRESHOLD SUPPORT] ===
        # 1. Start with global default
        effective_threshold = self.signal_threshold
        effective_neutral = self.neutral_threshold
        
        # 2. Check for symbol-specific override (signal_threshold)
        if instr_cfg:
            st_cfg = getattr(instr_cfg, "signal_threshold", None)
            
            if st_cfg is not None:
                if isinstance(st_cfg, (int, float)):
                    # Direct numeric value (legacy format)
                    effective_threshold = decimal.Decimal(str(st_cfg))
                    self.logger.debug(f"[{symbol}] Using per-symbol threshold (direct): {effective_threshold}")
                elif hasattr(st_cfg, "enabled") and st_cfg.enabled:
                    # Object format: {enabled: true, value: 0.12}
                    if hasattr(st_cfg, "value") and st_cfg.value is not None:
                        effective_threshold = decimal.Decimal(str(st_cfg.value))
                        self.logger.debug(f"[{symbol}] Using per-symbol threshold (enabled): {effective_threshold}")
            
            # 3. Check for symbol-specific neutral_threshold override
            nt_cfg = getattr(instr_cfg, "neutral_threshold", None)
            if nt_cfg is not None:
                if isinstance(nt_cfg, (int, float)):
                    effective_neutral = decimal.Decimal(str(nt_cfg))
                    self.logger.debug(f"[{symbol}] Using per-symbol neutral_threshold: {effective_neutral}")
                elif hasattr(nt_cfg, "value") and nt_cfg.value is not None:
                    effective_neutral = decimal.Decimal(str(nt_cfg.value))
        # === END PER-SYMBOL THRESHOLD SUPPORT ===
        
        # Get current side for hysteresis
        current_side = state.last_signal_side
        
        # Call scoring kernel
        result = self.scoring_kernel_cls.compute(
            symbol=symbol,
            features=features,
            warmup_readiness=warmup_readiness,
            price=price_dec,
            signal_weights=signal_weights,
            feature_neutrals=feature_neutrals,
            essential_features=essential_features,
            base_threshold=effective_threshold,
            regime_name=state.regime,
            regime_thresholds=self.regime_thresholds,
            side_bias_state=side_bias,
            direction_strength_cfg=self.direction_strength_cfg,
            delta_price_cap_pct=self.delta_price_cap_pct,
            neutral_threshold=effective_neutral,
            current_side=current_side,
        )
        
        # Handle result
        # CRITICAL: Update side state BEFORE any early returns.
        # This ensures hysteresis state is correct even for neutral signals.
        state.last_signal_side = result.side
        
        if result.deferred:
            self.logger.debug(f"[{symbol}] Kernel deferred: {result.defer_reason}")
            defer_reason = str(result.defer_reason or "UNKNOWN")
            reason_code = "AURORA_KERNEL_DEFERRED"
            reason = "READINESS"
            # Spread-related deferrals are common when FE cannot compute spread_bps
            # (e.g., bid/ask missing) and marks warmup.ready['spread_bps']=False.
            if (warmup_readiness.get("spread_bps") is False) or ("spread" in defer_reason.lower()):
                reason = "SPREAD"
                reason_code = "SPREAD_NOT_READY"
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=reason_code,
                reason=reason,
                context="aurora_handler:kernel_deferred",
                details={"defer_reason": defer_reason},
                why_chain=["KERNEL_DEFERRED", defer_reason],
            )
            return
        
        current_position_side = state.position_side

        # Never mutate scoring output object; use an effective side override instead.
        effective_side = result.side
        
        # === [HOLDING PERIOD CHECK: ANTI-CHURN GATE] ===
        # Ensure we check holding period for BOTH exits (neutral) and flips.
        # If suppressed, we must FORCE HOLD by overriding the signal to current side.
        
        # Determine if this signal represents an exit or flip
        # Exit: Neutral signal while in position
        # Flip: Opposite side signal while in position
        is_exit_signal = (not effective_side) and (current_position_side != "")
        is_flip_signal = (
            current_position_side != ""
            and effective_side
            and effective_side.lower() != current_position_side
        )
        
        if is_exit_signal or is_flip_signal:
            if self._should_suppress_soft_exit(symbol, result, is_flip=is_flip_signal):
                # FORCE HOLD: override *effective* signal to maintain current position.
                self.logger.info(
                    f"[{symbol}] HOLDING_PERIOD: Forcing HOLD (side={current_position_side}) "
                    f"suppressing {'flip' if is_flip_signal else 'exit'}"
                )
                effective_side = current_position_side
        
        # === END HOLDING PERIOD CHECK ===

        if not effective_side:
            # === [TRACK EXIT FOR RE-ENTRY COOLDOWN] ===
            if state.position_side:  # Was in position, now exiting
                state.last_exit_timestamp = float(self.monotonic_fn())
                state.position_side = ""
                self._clear_entry(symbol)
                self.logger.info(f"[{symbol}] Position closed (neutral). Starting re-entry cooldown.")
            # === END TRACK EXIT ===
            self.logger.debug(f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
            return

        # === [RE-ENTRY COOLDOWN: ANTI-PING-PONG GATE] ===
        # If we are flat and want to enter, check if we are in cooldown.
        if state.position_side == "" and effective_side:
            if state.last_exit_timestamp:
                reentry_cooldown = self._get_reentry_cooldown_sec(symbol)
                time_since_exit = float(self.monotonic_fn()) - state.last_exit_timestamp
                if time_since_exit < reentry_cooldown:
                    self.logger.info(
                        f"[{symbol}] REENTRY_COOLDOWN: Blocking entry {time_since_exit:.1f}s < {reentry_cooldown}s"
                    )
                    self._emit_strategy_blocked(
                        symbol=symbol,
                        reason_code="REENTRY_COOLDOWN",
                        reason="COOLDOWN",
                        context="aurora_handler:reentry_cooldown",
                        details={"time_since_exit": time_since_exit, "cooldown": reentry_cooldown},
                        why_chain=["REENTRY_COOLDOWN", f"wait:{reentry_cooldown - time_since_exit:.1f}s"],
                    )
                    return
        # === END RE-ENTRY COOLDOWN ===
        
        # === [VOL-ADJ GATES: ANTI-FLAT / ANTI-FOMO] ===
        # Block entries in dead markets (fee churn) or extreme impulses (snapback risk).
        # Config: aurora.decision.gates.{anti_flat_sigma, anti_fomo_sigma, motion_window_sec}
        # Only applies to ENTRIES (flat → position), not exits or flips.
        if self._apply_vol_adj_gates(symbol, result, state, features, effective_side=effective_side):
            return  # Entry blocked by vol-adj gate
        # === END VOL-ADJ GATES ===
        
        # === [PHASE 3 FIX: ANCHOR SHOCK VETO] ===
        # If BTC is crashing (macro_resid strongly negative), block BUY signals for non-anchor symbols.
        # Config: aurora.decision.anchor_shock_veto
        if (
            veto_cfg
            and getattr(veto_cfg, "enabled", False)
            and veto_applicable
            and veto_threshold is not None
            and veto_macro_resid is not None
            and (effective_side or "").lower() == "buy"
            and veto_macro_resid < veto_threshold
        ):
            self.logger.warning(
                f"[{symbol}] ANCHOR SHOCK VETO: Blocking BUY signal "
                f"(macro_resid={veto_macro_resid:.2f} < {veto_threshold})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="ANCHOR_SHOCK_VETO",
                reason="MACRO_VETO",
                context="aurora_handler:anchor_shock_veto",
                details={
                    "macro_resid": veto_macro_resid,
                    "threshold": veto_threshold,
                    "side": effective_side,
                    "anchor_symbol": veto_anchor_symbol,
                },
                why_chain=["MACRO_VETO", "ANCHOR_SHOCK_VETO"],
            )
            return  # Do NOT emit signal
        # === END ANCHOR SHOCK VETO ===
        
        # Emit signal
        self._emit_signal(symbol, result, features, cmd, effective_side=effective_side)
        
        # === [TRACK ENTRY FOR HOLDING PERIOD] ===
        # Track entry timestamp when side changes (new entry or flip)
        if effective_side and effective_side.lower() != current_position_side:
            self._track_entry(symbol, effective_side)
        # === END TRACK ENTRY ===
        
        # Update side bias history
        self._update_side_bias(symbol, effective_side)
    
    def _is_symbol_enabled(self, symbol: str) -> bool:
        """
        Check if symbol is enabled for Aurora strategy.
        
        P1-1: Registry SSOT takes precedence.
        1. Check strategies_registry.assignments first
        2. Fall back to aurora.assets.enabled
        """
        # P1-1: Registry check takes precedence (SSOT)
        registry = getattr(self.config, "strategies_registry", None)
        if registry:
            assignments = getattr(registry, "assignments", {}) or {}
            symbol_strategies = assignments.get(symbol, [])
            if symbol_strategies:
                # Registry has explicit assignment - use it
                return "aurora" in symbol_strategies
        
        # Fallback: legacy aurora.assets.enabled check
        aurora = getattr(self.config.strategies, "aurora", None)
        if not aurora:
            return False
        assets = getattr(aurora, "assets", {})
        if symbol not in assets:
            return False
        asset_cfg = assets[symbol]
        return bool(getattr(asset_cfg, "enabled", True))
    
    def _get_instrument_config(self, symbol: str) -> Any:
        """Get instrument config for symbol."""
        aurora = getattr(self.config.strategies, "aurora", None)
        if not aurora:
            return None
        assets = getattr(aurora, "assets", {})
        return assets.get(symbol)

    # =========================================================================
    # HOLDING PERIOD (ANTI-CHURN) METHODS
    # =========================================================================
    
    def _get_min_duration_sec(self, symbol: str) -> float:
        """
        Get min_duration_sec with per-symbol override.
        
        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.holding_period.min_duration_sec
        2. strategies.aurora.decision.holding_period.min_duration_sec
        3. self.default_min_duration_sec (30s)
        """
        base = self.default_min_duration_sec
        instr_cfg = self._get_instrument_config(symbol)
        if instr_cfg:
            hp = getattr(instr_cfg, "holding_period", None)
            if hp:
                val = getattr(hp, "min_duration_sec", None)
                if val is not None:
                    base = float(val)

        state = self._symbol_states[symbol]
        mult = self._get_time_multiplier(state.regime_effective)
        return base * mult

    def _get_emergency_threshold(self, symbol: str) -> float:
        """
        Get emergency_exit_threshold with per-symbol override.
        
        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.holding_period.emergency_exit_threshold
        2. strategies.aurora.decision.holding_period.emergency_exit_threshold
        3. self.default_emergency_threshold (0.7)
        """
        instr_cfg = self._get_instrument_config(symbol)
        if instr_cfg:
            hp = getattr(instr_cfg, "holding_period", None)
            if hp:
                val = getattr(hp, "emergency_exit_threshold", None)
                if val is not None:
                    return float(val)
        return self.default_emergency_threshold

    def _get_reentry_cooldown_sec(self, symbol: str) -> float:
        """
        Get reentry_cooldown_sec with per-symbol override.
        
        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.reentry_cooldown_sec
        2. strategies.aurora.decision.reentry_cooldown_sec
        3. self.default_reentry_cooldown_sec (60s)
        """
        base = self.default_reentry_cooldown_sec
        instr_cfg = self._get_instrument_config(symbol)
        if instr_cfg:
            val = getattr(instr_cfg, "reentry_cooldown_sec", None)
            if val is not None:
                base = float(val)

        state = self._symbol_states[symbol]
        mult = self._get_time_multiplier(state.regime_effective)
        return base * mult

    def _is_emergency_exit(self, score: decimal.Decimal, symbol: str) -> bool:
        """
        Check if score indicates emergency conditions.
        
        Returns True if |score| >= emergency_threshold, allowing exit
        even within holding period.
        """
        threshold = self._get_emergency_threshold(symbol)
        return abs(float(score)) >= threshold

    def _should_suppress_soft_exit(
        self,
        symbol: str,
        result: ScoringResult,
        is_flip: bool = False,
    ) -> bool:
        """
        Check if exit/flip signal should be suppressed due to minimum holding period.
        
        Returns True (suppress) if:
        1. Holding period feature is enabled
        2. We have an active entry timestamp
        3. Time in position < min_duration_sec
        4. This is NOT an emergency exit
        5. (for flips) holding_apply_to_flips is True
        
        Returns False (allow) otherwise.
        
        FAIL-OPEN: If entry_timestamp is None (unknown state), allow exit.
        """
        # 0. Feature disabled?
        if not self.holding_period_enabled:
            return False
        
        # 1. Skip if this is a flip and we don't apply to flips
        if is_flip and not self.holding_apply_to_flips:
            return False
        
        # 2. Get state
        state = self._symbol_states[symbol]
        entry_ts = state.entry_timestamp
        
        if entry_ts is None:
            # FAIL-OPEN: No tracked entry → allow exit
            return False
        
        # 3. Check holding period
        now = float(self.monotonic_fn())
        min_duration = self._get_min_duration_sec(symbol)
        time_in_position = now - entry_ts
        
        if time_in_position >= min_duration:
            # Holding period elapsed → allow exit
            return False
        
        # 4. Check emergency override
        if self._is_emergency_exit(result.score, symbol):
            self.logger.warning(
                f"[{symbol}] EMERGENCY_OVERRIDE: Allowing exit despite holding period "
                f"(score={float(result.score):.4f}, time_in_position={time_in_position:.1f}s, "
                f"threshold={self._get_emergency_threshold(symbol)})"
            )
            return False
        
        # 5. Suppress the exit
        self.logger.info(
            f"[{symbol}] HOLDING_PERIOD_ACTIVE: Suppressing soft {'flip' if is_flip else 'exit'} "
            f"(time_in_position={time_in_position:.1f}s < min_duration={min_duration}s, "
            f"score={float(result.score):.4f})"
        )
        
        # Emit blocked event for observability
        self._emit_strategy_blocked(
            symbol=symbol,
            reason_code="HOLDING_PERIOD_ACTIVE",
            reason="HOLDING_PERIOD",
            context="aurora_handler:holding_period_check",
            details={
                "time_in_position_sec": round(time_in_position, 2),
                "min_duration_sec": min_duration,
                "score": float(result.score),
                "signal_type": "flip" if is_flip else "exit",
            },
            why_chain=["HOLDING_PERIOD", f"time:{time_in_position:.1f}s", f"min:{min_duration}s"],
        )
        
        return True

    def _track_entry(self, symbol: str, side: str) -> None:
        """Track entry timestamp when position opens."""
        state = self._symbol_states[symbol]
        state.entry_timestamp = float(self.monotonic_fn())
        state.position_side = side.lower()
        self.logger.debug(f"[{symbol}] Entry tracked: side={side}, ts={state.entry_timestamp}")

    def _clear_entry(self, symbol: str) -> None:
        """Clear entry tracking when position closes."""
        state = self._symbol_states[symbol]
        state.entry_timestamp = None
        state.position_side = ""
        self.logger.debug(f"[{symbol}] Entry tracking cleared")

    # =========================================================================
    # END HOLDING PERIOD METHODS
    # =========================================================================
    
    # =========================================================================
    # VOL-ADJ GATES METHODS (Anti-Flat / Anti-FOMO)
    # =========================================================================
    
    def _get_motion_norm_sigma(self, symbol: str, features: Dict[str, Any]) -> Optional[float]:
        """
        Extract absolute motion norm sigma from features.
        
        Uses pm_norm_{window}s from price_motion block.
        Returns absolute value (sigma magnitude) or None if unavailable.
        
        P0-3: Falls back to cached price_motion if not in CMD features.
        """
        pm = features.get("price_motion")
        
        # P0-3: Fallback to cached price_motion from EVT:FEATURES_CALCULATED
        if not isinstance(pm, dict):
            state = self._symbol_states.get(symbol)
            if state and state.cached_price_motion:
                pm = state.cached_price_motion
        
        if not isinstance(pm, dict):
            return None
        
        window_key = f"pm_norm_{self.motion_window_sec}s"
        val = pm.get(window_key)
        
        if val is None:
            return None
        
        try:
            return abs(float(val))
        except (TypeError, ValueError):
            return None
    
    def _apply_vol_adj_gates(
        self,
        symbol: str,
        result: ScoringResult,
        state: SymbolState,
        features: Dict[str, Any],
        *,
        effective_side: str | None = None,
    ) -> bool:
        """
        Apply volatility-adjusted entry gates.
        
        Returns True if entry should be BLOCKED, False if passed.
        Only applies to ENTRY proposals (flat → position).
        """
        if not self.vol_gates_enabled:
            return False
        
        # Only apply to entries (flat → position)
        side = effective_side if effective_side is not None else result.side
        if not side or state.position_side != "":
            return False  # Not an entry, skip gates
        
        motion_norm_sigma = self._get_motion_norm_sigma(symbol, features)
        
        if motion_norm_sigma is None:
            # Readiness handles missing data, don't block here
            self.logger.debug(f"[{symbol}] VOL_GATES: motion_norm_sigma=None, skipping")
            return False
        
        # Anti-Flat gate: block entry in dead market
        if motion_norm_sigma < self.anti_flat_sigma:
            self.logger.info(
                f"[{symbol}] GATE_ANTI_FLAT_SIGMA: Blocking entry "
                f"(motion={motion_norm_sigma:.3f} < threshold={self.anti_flat_sigma})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FLAT_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_flat",
                details={
                    "motion_norm_sigma": motion_norm_sigma,
                    "threshold": self.anti_flat_sigma,
                    "window_sec": self.motion_window_sec,
                },
                why_chain=["VOL_GATE", "ANTI_FLAT", f"motion:{motion_norm_sigma:.3f}"],
            )
            return True
        
        # Anti-FOMO gate: block entry in extreme impulse
        if motion_norm_sigma > self.anti_fomo_sigma:
            self.logger.info(
                f"[{symbol}] GATE_ANTI_FOMO_SIGMA: Blocking entry "
                f"(motion={motion_norm_sigma:.3f} > threshold={self.anti_fomo_sigma})"
            )
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="GATE_ANTI_FOMO_SIGMA",
                reason="VOL_GATE",
                context="aurora_handler:anti_fomo",
                details={
                    "motion_norm_sigma": motion_norm_sigma,
                    "threshold": self.anti_fomo_sigma,
                    "window_sec": self.motion_window_sec,
                },
                why_chain=["VOL_GATE", "ANTI_FOMO", f"motion:{motion_norm_sigma:.3f}"],
            )
            return True
        
        self.logger.debug(
            f"[{symbol}] VOL_GATES: passed (motion={motion_norm_sigma:.3f} in "
            f"[{self.anti_flat_sigma}, {self.anti_fomo_sigma}])"
        )
        return False
    
    # =========================================================================
    # END VOL-ADJ GATES METHODS
    # =========================================================================
    
    # =========================================================================
    # VOLATILITY-BASED ENTRY OFFSET (Maker/GTX Compliance)
    # =========================================================================
    
    def _get_volatility_strict(
        self,
        symbol: str,
        features: Dict[str, Any],
    ) -> Optional[decimal.Decimal]:
        """
        Get ATR volatility (STRICT: no fallbacks, fail-closed).
        
        Reads from:
        1. features["volatility"]["atr_14"] (canonical FE output)
        2. features["atr"] (backward compatibility)
        
        Returns None if ATR is missing → caller MUST abort signal emission.
        This is fail-closed behavior: prefer no trade over a bad trade.
        """
        atr = None
        
        # Primary path: nested volatility.atr_14 (from FeatureEngineering)
        volatility_block = features.get("volatility")
        if isinstance(volatility_block, dict):
            atr = volatility_block.get("atr_14")
        
        # Fallback: top-level "atr" (backward compatibility / tests)
        if atr is None:
            atr = features.get("atr")
        
        if atr is None:
            self.logger.error(
                f"[{symbol}] ATR_MISSING: volatility_entry_logic requires 'volatility.atr_14' or 'atr'. "
                f"Signal ABORTED (fail-closed). Check FeatureEngineering pipeline."
            )
            return None
        
        try:
            return decimal.Decimal(str(atr))
        except (decimal.InvalidOperation, ValueError) as e:
            self.logger.error(f"[{symbol}] ATR_INVALID: Cannot convert atr={atr!r} to Decimal: {e}")
            return None
            return None
    
    # =========================================================================
    # END VOLATILITY-BASED ENTRY OFFSET
    # =========================================================================

    
    def _get_signal_weights(self, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Get signal weights for symbol."""
        weights = getattr(instr_cfg, "weights", None)
        if weights:
            return dict(weights)
        # Fallback to global
        decision = getattr(self.config.strategies.aurora, "decision", None)
        return dict(getattr(decision, "signal_weights", {})) if decision else {}
    
    def _get_feature_neutrals(self, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Get feature neutrals for symbol."""
        neutrals = getattr(instr_cfg, "feature_neutrals", None)
        if neutrals:
            return dict(neutrals)
        # Fallback to global
        decision = getattr(self.config.strategies.aurora, "decision", None)
        return dict(getattr(decision, "feature_neutrals", {})) if decision else {}
    
    def _get_essential_features(self, symbol: str, instr_cfg: Any) -> List[str]:
        """Get essential features for symbol."""
        essential = getattr(instr_cfg, "essential_features", None)
        if essential:
            return list(essential)
        # Fallback to global
        decision = getattr(self.config.strategies.aurora, "decision", None)
        return list(getattr(decision, "essential_features", [])) if decision else []
    
    def _get_side_bias_state(self, symbol: str) -> SideBiasState:
        """Build SideBiasState for kernel from cached history."""
        state = self._symbol_states[symbol]
        now = float(self.wall_time_fn())
        
        # Clean old entries outside window
        state.buy_timestamps = [ts for ts in state.buy_timestamps if now - ts < self.side_bias_window_sec]
        state.sell_timestamps = [ts for ts in state.sell_timestamps if now - ts < self.side_bias_window_sec]
        
        return SideBiasState(
            buy_count=len(state.buy_timestamps),
            sell_count=len(state.sell_timestamps),
            window_sec=self.side_bias_window_sec,
            target_ratio=self.side_bias_target_ratio,
            penalty_factor=self.side_bias_penalty_factor,
            min_intents=self.side_bias_min_intents,
        )
    
    def _update_side_bias(self, symbol: str, side: str) -> None:
        """Update side bias history after emitting signal."""
        state = self._symbol_states[symbol]
        now = float(self.wall_time_fn())
        
        if side.lower() == "buy":
            state.buy_timestamps.append(now)
        elif side.lower() == "sell":
            state.sell_timestamps.append(now)
    
    def _emit_signal(
        self,
        symbol: str,
        result: ScoringResult,
        features: Dict[str, Any],
        source_event: Dict[str, Any],
        *,
        effective_side: str | None = None,
    ) -> None:
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED with readiness contract."""
        state = self._symbol_states[symbol]
        side = effective_side if effective_side is not None else result.side
        now_ms = int(self.wall_time_fn() * 1000)
        
        # Get anchor price and default entry price
        anchor_price = decimal.Decimal(str(features.get("price", "0")))
        entry_price = anchor_price
        
        # === VOLATILITY-BASED ENTRY OFFSET (Maker/GTX Compliance) ===
        instr_cfg = self._get_instrument_config(symbol)
        vel_cfg = getattr(instr_cfg, "volatility_entry_logic", None) if instr_cfg else None
        
        if vel_cfg and getattr(vel_cfg, "enabled", False):
            # 1. Get ATR (STRICT: no fallbacks)
            volatility = self._get_volatility_strict(symbol, features)
            if volatility is None:
                # ABORT: ATR missing, fail-closed
                self._emit_strategy_blocked(
                    symbol=symbol,
                    reason_code="ATR_MISSING_FAIL_CLOSED",
                    reason="DATA_NOT_READY",
                    context="aurora_handler:volatility_entry",
                    details={"required_feature": "atr"},
                    why_chain=["VOLATILITY_ENTRY", "ATR_MISSING", "FAIL_CLOSED"],
                )
                return  # Signal aborted - prefer no trade over bad trade
            
            # 2. Get regime multiplier (fail-closed: DEFAULT required)
            regime = state.regime or "DEFAULT"
            multipliers = getattr(vel_cfg, "regime_multipliers", {})
            mult_raw = multipliers.get(regime, multipliers.get("DEFAULT"))
            if mult_raw is None:
                self.logger.error(f"[{symbol}] regime_multipliers missing DEFAULT key (fail-closed)")
                return
            mult = decimal.Decimal(str(mult_raw))
            
            # 3. Calculate offset
            offset = volatility * mult
            
            # 4. Apply offset based on side
            if side.lower() == "buy":
                entry_price = anchor_price - offset  # Bid below anchor
            elif side.lower() == "sell":
                entry_price = anchor_price + offset  # Ask above anchor
            
            self.logger.debug(
                f"[{symbol}] Limit Offset: {offset:.6f} for Regime: {regime} "
                f"(atr={volatility:.6f}, mult={mult}, entry={entry_price:.6f})"
            )
        # === END VOLATILITY OFFSET ===
        
        # Build payload per v7 contract
        payload = {
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "side": side.upper(),
            "ts_ms": now_ms,
            "rid": f"aurora_{symbol}_{now_ms}",
            "why_chain": result.why_chain,
            "readiness": {"warmup_ok": state.warmup_full_ready},
            "price_ctx": {
                "entry_price": str(entry_price),
            },
            "scoring": {
                "score": float(result.score),
                "thr_buy": float(result.thr_buy),
                "thr_sell": float(result.thr_sell),
                "regime": result.regime,
                "psi_vector": result.psi_vector,
            },
            # EP-01.2-INT: Pass volatility/liquidity snapshots for EntryPlan in DecisionMaking
            "volatility": features.get("volatility"),
            "liquidity": features.get("liquidity"),
            # EP-01.3-INT: Pass tf_sec for pending entry TTL calculation
            "tf_sec": self.timeframe_sec,
        }
        
        self.logger.info(
            f"[{symbol}] SIGNAL: {side.upper()} score={float(result.score):.4f} "
            f"(thr_buy={float(result.thr_buy):.4f}, thr_sell={float(result.thr_sell):.4f})"
        )
        
        self.emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)
        
        # Update state
        state.last_signal_ts_ms = now_ms
        state.last_signal_side = side

