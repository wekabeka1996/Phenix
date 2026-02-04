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
# DET-BT-11: Import for deterministic backtest
from apps.reference.core.time import get_clock
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
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract


logger = logging.getLogger("aurora_handler")


@dataclass
class SymbolState:
    """Per-symbol state for Aurora handler."""
    def __init__(self):
        # Regime cache (from EVT:REGIME_DETECTED)
        self.regime = None
        self.regime_confidence = 0.0
        self.regime_ts_ms = 0

        # Anti-churn regime inertia (monotonic timebase)
        self.regime_raw = None
        self.regime_effective = None
        self.regime_raw_change_ts = None
        
        # DM-CRITICAL-PATCHES-02: Liveness heartbeat tracking
        self.last_regime_heartbeat_ms = None
        
        # Warmup state
        self.warmup_full_ready = False
        self.warmup_ticks_seen = 0
        
        # Side bias history (timestamps)
        self.buy_timestamps = []
        self.sell_timestamps = []
        
        # Last signal state
        self.last_signal_ts_ms = 0
        self.last_signal_side = ""
        
        # Holding period state (Anti-Churn)
        self.entry_timestamp = None
        self.position_side = ""
        
        # Re-entry cooldown state (Anti-Ping-Pong)
        self.last_exit_timestamp = None
        
        # P0-3: Cached price_motion
        self.cached_price_motion = None


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
        # DET-BT-FIX-01: Deterministic monotonic fallback via get_clock()
        self.monotonic_fn: Callable[[], float] = monotonic_fn or (lambda: get_clock().monotonic())
        self.wall_time_fn: Callable[[], float] = wall_time_fn or (lambda: get_clock().now_sec())
        
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
        self._strict_pydantic_config: bool = False
        try:
            from apps.reference.config_models import AuroraConfig
            from apps.reference.domain_config import DomainConfigResolver

            if isinstance(self.config, AuroraConfig):
                self._strict_pydantic_config = True
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
            if self._strict_pydantic_config:
                from apps.reference.config_contract import ConfigContractError

                thr_raw = getattr(decision, "signal_threshold", None)
                if thr_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.signal_threshold",
                        why="signal_threshold is required for AuroraHandler (no silent fallback).",
                    )
                self.signal_threshold = decimal.Decimal(str(thr_raw))

                # Side-bias parameters are required for kernel scoring (fail-closed).
                sb_window_raw = getattr(decision, "side_bias_window_sec", None)
                sb_target_raw = getattr(decision, "side_bias_target_ratio", None)
                sb_penalty_raw = getattr(decision, "side_bias_penalty_factor", None)
                sb_min_intents_raw = getattr(decision, "side_bias_min_intents", None)
                if sb_window_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_window_sec",
                        why="side_bias_window_sec is required (no silent fallback).",
                    )
                if sb_target_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_target_ratio",
                        why="side_bias_target_ratio is required (no silent fallback).",
                    )
                if sb_penalty_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_penalty_factor",
                        why="side_bias_penalty_factor is required (no silent fallback).",
                    )
                if sb_min_intents_raw is None:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.side_bias_min_intents",
                        why="side_bias_min_intents is required (no silent fallback).",
                    )
                self.side_bias_window_sec = float(sb_window_raw)
                self.side_bias_target_ratio = float(sb_target_raw)
                self.side_bias_penalty_factor = float(sb_penalty_raw)
                self.side_bias_min_intents = int(sb_min_intents_raw)

                regime_thr = getattr(decision, "regime_threshold_multipliers", None)
                if not isinstance(regime_thr, dict) or not regime_thr:
                    raise ConfigContractError(
                        path="strategies.aurora.decision.regime_threshold_multipliers",
                        why="regime_threshold_multipliers must be a non-empty mapping (include DEFAULT).",
                    )
                self.regime_thresholds = dict(regime_thr)
            else:
                # Legacy/non-typed config path (tests/mocks): keep backward-compatible defaults.
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

            # REGIME-KILL-SWITCH-01: Optional config-driven regime blocklist.
            # If current regime is blocked, Aurora strategy emits no signals.
            blocked = getattr(decision, "blocked_regimes", None)
            try:
                self.blocked_regimes = {str(x) for x in (blocked or []) if str(x)}
            except Exception:
                self.blocked_regimes = set()

            # Liquidity Gate (Score V2) - optional (per-symbol override supported at runtime)
            # NOTE: For non-typed configs (tests/mocks), avoid accidentally enabling this gate via MagicMock.
            self._global_liquidity_gate_cfg = (
                getattr(decision, "liquidity_gate", None) if self._strict_pydantic_config else None
            )
            
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
            # P2: FAIL-CLOSED — decision config is mandatory
            from apps.reference.config_contract import ConfigContractError
            raise ConfigContractError(
                path="strategies.aurora.decision",
                why="Aurora decision config is mandatory. Check config/aurora/strategies/aurora.yaml"
            )

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
        ts_ms = int(self.wall_time_fn() * 1000)
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "reason_code": str(reason_code),
            "reason": str(reason),
            "context": str(context),
            "ts_ms": ts_ms,
            "why_chain": list(why_chain or []),
        }
        if details:
            payload["details"] = details
        self.emit_fn("EVT:STRATEGY_DECISION_BLOCKED", payload)
        
        # P1-OBSERVABILITY: Write to WAL for audit trail (post-mortem analysis)
        try:
            write_trade_intent_rejected(
                symbol=symbol,
                tf_sec=self.timeframe_sec,
                bar_close_ts=None,
                reason_code=reason_code,
                stage="STRATEGY",
                why=f"{context}: {reason}",
                src="aurora_handler:_emit_strategy_blocked",
                ts_ms=ts_ms,
            )
        except Exception:
            pass  # Best-effort WAL write, don't fail on observability
    
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
        
        # P1-1-FIX: DO NOT update warmup from REGIME_DETECTED
        # SSOT: warmup comes from CMD:PROCESS_STRATEGY only
        
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

        Does NOT update warmup; warmup is SSOT from CMD:PROCESS_STRATEGY.
        Decision is now triggered exclusively by CMD:PROCESS_STRATEGY.
        
        P0-3: Also caches price_motion since CMD:PROCESS_STRATEGY doesn't include it.
        """
        symbol = event.get("symbol")
        if not symbol:
            return
        
        # P1-1-FIX: DO NOT update warmup from FEATURES_CALCULATED
        state = self._symbol_states[symbol]
        
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

        # === LIQUIDITY GATE (Score V2) ===
        # If enabled, block trading when liquidity_kappa is missing/not-ready/too low.
        liq_ok, liq_ctx = self._check_liquidity_gate(
            symbol=symbol,
            instr_cfg=instr_cfg,
            features=features,
            warmup_readiness=warmup_readiness,
        )
        if not liq_ok:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code=str(liq_ctx.get("reason_code") or "LIQUIDITY_GATE_FAIL"),
                reason="LIQUIDITY",
                context="aurora_handler:liquidity_gate",
                details=liq_ctx,
                why_chain=[
                    "LIQUIDITY_GATE",
                    f"kappa={liq_ctx.get('kappa')}",
                    f"min={liq_ctx.get('kappa_min')}",
                ],
            )
            return
        # === END LIQUIDITY GATE ===
        
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
        effective_regime_thresholds = self._get_regime_thresholds(symbol=symbol, instr_cfg=instr_cfg)
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
            regime_thresholds=effective_regime_thresholds,
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

        # === STRICT REGIME ALLOWLIST GATE ===
        # Contract: if a regime is not explicitly present in YAML allowed_regimes,
        # strategy must NOT emit intents in that regime.
        allowed_regimes = None
        try:
            allowed_regimes = getattr(instr_cfg, "allowed_regimes", None)
        except Exception:
            allowed_regimes = None
        if not RegimeAllowlistContract.is_regime_allowed(current_regime=str(state.regime), allowed_regimes=allowed_regimes):
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="REGIME_NOT_ALLOWLISTED",
                reason="REGIME",
                context="aurora_handler:strict_regime_allowlist",
                details={
                    "regime": state.regime,
                    "allowed_regimes": list(allowed_regimes or []),
                    "score": float(result.score),
                    "thr_buy": float(result.thr_buy),
                    "thr_sell": float(result.thr_sell),
                    "explain": RegimeAllowlistContract.explain_blocking(
                        symbol=symbol,
                        current_regime=str(state.regime),
                        allowed_regimes=list(allowed_regimes) if allowed_regimes else None,
                    ),
                },
                why_chain=["REGIME_ALLOWLIST", f"REGIME={state.regime}", "STRICT"],
            )
            return
        # === END STRICT REGIME ALLOWLIST GATE ===
        
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

        # === REGIME KILL-SWITCH (config-driven) ===
        # Block all strategy-driven intents in specified regimes (backtest hardening).
        # Note: This does NOT affect safety exits (SL/TP) managed elsewhere.
        if getattr(self, "blocked_regimes", None) and state.regime in self.blocked_regimes:
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="REGIME_KILL_SWITCH",
                reason="REGIME_BLOCKED",
                context="aurora_handler:regime_kill_switch",
                details={
                    "regime": state.regime,
                    "score": float(result.score),
                    "thr_buy": float(result.thr_buy),
                    "thr_sell": float(result.thr_sell),
                },
                why_chain=["REGIME_KILL_SWITCH", f"REGIME={state.regime}"],
            )
            return
        # === END REGIME KILL-SWITCH ===

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
        
        # P0-3-FIX: Do NOT track entry on signal emission.
        # Entry tracking is now driven by EVT:TRADE_EXECUTED only.
        
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

    def on_trade_executed(self, event: Dict[str, Any]) -> None:
        """
        P0-3-FIX: Sync position tracking with EVT:TRADE_EXECUTED.

        Entry tracking is updated ONLY on real trades, not on signal emission.
        """
        symbol = event.get("symbol")
        if not symbol:
            return

        state = self._symbol_states[symbol]

        side = str(event.get("side", "")).lower()
        if side not in ("buy", "sell"):
            return

        qty_raw = event.get("quantity")
        try:
            qty = float(qty_raw) if qty_raw is not None else 0.0
        except (TypeError, ValueError):
            qty = 0.0
        if qty == 0.0:
            return

        if state.position_side == "":
            state.entry_timestamp = float(self.monotonic_fn())
            state.position_side = side
            self.logger.info(
                f"[{symbol}] TRADE_EXECUTED: entry confirmed (side={side}, qty={qty})"
            )
            return

        if state.position_side == side:
            self.logger.debug(
                f"[{symbol}] TRADE_EXECUTED: add to position (side={side}, qty={qty})"
            )
            return

        # Opposite-side trade: treat as exit/flatten (conservative)
        prev_side = state.position_side
        state.last_exit_timestamp = float(self.monotonic_fn())
        state.entry_timestamp = None
        state.position_side = ""
        self.logger.info(
            f"[{symbol}] TRADE_EXECUTED: exit detected (prev={prev_side}, side={side}, qty={qty})"
        )

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
    
    # =========================================================================
    # END VOLATILITY-BASED ENTRY OFFSET
    # =========================================================================

    # =========================================================================
    # REGIME-BASED TP/SL (AURORA_REGIME_TP_SL_PLAN)
    # =========================================================================
    
    def _compute_regime_tpsl(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        regime: Optional[str],
        instr_cfg: Any,
        features: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute regime-based TP/SL for Aurora signal.
        
        Returns dict with:
        - stop_price: Decimal
        - target_price: Decimal
        - tpsl_ctx: dict (telemetry)
        
        Returns None if regime_tpsl is disabled or config missing.
        
        AURORA_REGIME_TP_SL_PLAN: Strategy-provided TP/SL injection point.
        """
        if instr_cfg is None:
            return None
        
        exit_cfg = getattr(instr_cfg, "exit", None)
        if exit_cfg is None:
            return None
        
        regime_tpsl_cfg = getattr(exit_cfg, "regime_tpsl", None)
        if regime_tpsl_cfg is None or not getattr(regime_tpsl_cfg, "enabled", False):
            return None
        
        tp_cfg = getattr(instr_cfg, "take_profit", None)
        
        # Resolve effective regime (prefer effective from anti-churn if enabled)
        state = self._symbol_states[symbol]
        regime_used = regime or "DEFAULT"
        if getattr(self, "anti_churn_enabled", False) and state.regime_effective:
            regime_used = state.regime_effective
        
        mode = getattr(regime_tpsl_cfg, "mode", "pct_mult")
        
        # === Calculate SL/TP based on mode ===
        if mode == "pct_mult":
            result = self._compute_tpsl_pct_mult(
                entry_price=entry_price,
                side=side,
                regime_used=regime_used,
                exit_cfg=exit_cfg,
                tp_cfg=tp_cfg,
                regime_tpsl_cfg=regime_tpsl_cfg,
            )
        elif mode == "atr":
            result = self._compute_tpsl_atr(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
                regime_used=regime_used,
                regime_tpsl_cfg=regime_tpsl_cfg,
                features=features,
            )
        else:
            self.logger.warning(f"[{symbol}] Unknown regime_tpsl mode: {mode}, skipping")
            return None
        
        if result is None:
            return None
        
        # Apply guardrails
        result = self._apply_tpsl_guardrails(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            result=result,
            regime_tpsl_cfg=regime_tpsl_cfg,
        )
        
        return result
    
    def _compute_tpsl_pct_mult(
        self,
        entry_price: decimal.Decimal,
        side: str,
        regime_used: str,
        exit_cfg: Any,
        tp_cfg: Any,
        regime_tpsl_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute TP/SL using pct_mult mode (simple multipliers).
        
        SL = entry × (1 ± sl_pct_base × sl_mult[regime])
        TP = entry × (1 ± sl_pct_eff × tp_low_ratio × tp_mult[regime])
        
        FAIL-CLOSED: Requires explicit sl_pct and tp_low_ratio in config.
        """
        # Get base values (FAIL-CLOSED: no silent defaults)
        sl_pct_raw = getattr(exit_cfg, "sl_pct", None)
        if sl_pct_raw is None:
            self.logger.error(
                f"TPSL_CONFIG_ERROR: exit.sl_pct is required for regime_tpsl pct_mult mode. "
                f"Add explicit sl_pct to instrument config."
            )
            return None
        sl_pct_base = float(sl_pct_raw)
        
        tp_low_ratio_raw = getattr(tp_cfg, "tp_low_ratio", None) if tp_cfg else None
        if tp_low_ratio_raw is None:
            self.logger.error(
                f"TPSL_CONFIG_ERROR: take_profit.tp_low_ratio is required for regime_tpsl pct_mult mode. "
                f"Add explicit tp_low_ratio to instrument config."
            )
            return None
        tp_low_ratio_base = float(tp_low_ratio_raw)
        
        # Get multipliers (FAIL-CLOSED: DEFAULT key required by model validator)
        sl_mult_map = dict(getattr(regime_tpsl_cfg, "sl_mult", None) or {})
        tp_mult_map = dict(getattr(regime_tpsl_cfg, "tp_mult", None) or {})
        
        if "DEFAULT" not in sl_mult_map or "DEFAULT" not in tp_mult_map:
            self.logger.error(
                f"TPSL_CONFIG_ERROR: sl_mult and tp_mult must have 'DEFAULT' key. "
                f"Got sl_mult keys: {list(sl_mult_map.keys())}, tp_mult keys: {list(tp_mult_map.keys())}"
            )
            return None
        
        sl_mult = float(sl_mult_map.get(regime_used, sl_mult_map["DEFAULT"]))
        tp_mult = float(tp_mult_map.get(regime_used, tp_mult_map["DEFAULT"]))
        
        # Calculate effective values
        sl_pct_eff = sl_pct_base * sl_mult
        tp_rr_eff = tp_low_ratio_base * tp_mult
        
        # Calculate prices
        sl_pct_dec = decimal.Decimal(str(sl_pct_eff))
        tp_dist_pct = sl_pct_dec * decimal.Decimal(str(tp_rr_eff))
        
        if side.upper() == "BUY":
            stop_price = entry_price * (1 - sl_pct_dec)
            target_price = entry_price * (1 + tp_dist_pct)
        elif side.upper() == "SELL":
            stop_price = entry_price * (1 + sl_pct_dec)
            target_price = entry_price * (1 - tp_dist_pct)
        else:
            return None
        
        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": {
                "mode": "pct_mult",
                "regime_used": regime_used,
                "sl_pct_base": sl_pct_base,
                "sl_mult": sl_mult,
                "sl_pct_eff": sl_pct_eff,
                "tp_low_ratio_base": tp_low_ratio_base,
                "tp_mult": tp_mult,
                "tp_rr_eff": tp_rr_eff,
            },
        }
    
    def _compute_tpsl_atr(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        regime_used: str,
        regime_tpsl_cfg: Any,
        features: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute TP/SL using ATR mode (volatility-based).
        
        SL = entry ± (atr_pct × sl_k_atr[regime])
        TP = entry ± (sl_dist × rr_by_regime[regime])
        
        FAIL-CLOSED: Requires ATR feature and explicit config maps.
        """
        # Get ATR (strict, no fallbacks)
        atr = self._get_volatility_strict(symbol, features)
        if atr is None or atr == 0:
            self.logger.warning(f"[{symbol}] ATR missing for regime_tpsl atr mode, skipping TP/SL injection")
            return None
        
        # ATR as percentage of entry price
        atr_pct = atr / entry_price
        
        # Get coefficients (FAIL-CLOSED: DEFAULT key required)
        sl_k_map = dict(getattr(regime_tpsl_cfg, "sl_k_atr", None) or {})
        rr_map = dict(getattr(regime_tpsl_cfg, "rr_by_regime", None) or {})
        
        if "DEFAULT" not in sl_k_map:
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: sl_k_atr must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(sl_k_map.keys())}"
            )
            return None
        if "DEFAULT" not in rr_map:
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: rr_by_regime must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(rr_map.keys())}"
            )
            return None
        
        sl_k = decimal.Decimal(str(sl_k_map.get(regime_used, sl_k_map["DEFAULT"])))
        rr = decimal.Decimal(str(rr_map.get(regime_used, rr_map["DEFAULT"])))
        
        # Calculate SL distance
        sl_pct_eff = atr_pct * sl_k
        
        # Calculate prices
        if side.upper() == "BUY":
            stop_price = entry_price * (1 - sl_pct_eff)
            target_price = entry_price * (1 + sl_pct_eff * rr)
        elif side.upper() == "SELL":
            stop_price = entry_price * (1 + sl_pct_eff)
            target_price = entry_price * (1 - sl_pct_eff * rr)
        else:
            return None
        
        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": {
                "mode": "atr",
                "regime_used": regime_used,
                "atr": float(atr),
                "atr_pct": float(atr_pct),
                "sl_k": float(sl_k),
                "sl_pct_eff": float(sl_pct_eff),
                "rr": float(rr),
            },
        }
    
    def _apply_tpsl_guardrails(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        result: Dict[str, Any],
        regime_tpsl_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Apply guardrails to computed TP/SL values.
        
        Validates:
        - SL/TP on correct side of entry
        - min/max SL%
        - min/max TP RR
        - min distance in bps
        """
        stop_price = result["stop_price"]
        target_price = result["target_price"]
        tpsl_ctx = result["tpsl_ctx"]
        
        # Guardrail params
        min_sl_pct = decimal.Decimal(str(getattr(regime_tpsl_cfg, "min_sl_pct", 0.003)))
        max_sl_pct = decimal.Decimal(str(getattr(regime_tpsl_cfg, "max_sl_pct", 0.06)))
        min_tp_rr = decimal.Decimal(str(getattr(regime_tpsl_cfg, "min_tp_rr", 0.3)))
        max_tp_rr = decimal.Decimal(str(getattr(regime_tpsl_cfg, "max_tp_rr", 3.0)))
        min_dist_bps = int(getattr(regime_tpsl_cfg, "min_dist_bps", 15))
        
        # Calculate actual SL distance
        if side.upper() == "BUY":
            sl_dist_pct = (entry_price - stop_price) / entry_price
            tp_dist_pct = (target_price - entry_price) / entry_price
        else:
            sl_dist_pct = (stop_price - entry_price) / entry_price
            tp_dist_pct = (entry_price - target_price) / entry_price
        
        # Validate SL on correct side
        if sl_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL on wrong side of entry "
                f"(side={side}, entry={entry_price}, sl={stop_price})"
            )
            return None
        
        # Validate TP on correct side
        if tp_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: TP on wrong side of entry "
                f"(side={side}, entry={entry_price}, tp={target_price})"
            )
            return None
        
        # Clamp SL to min/max (clamp, not fail-closed)
        if sl_dist_pct < min_sl_pct:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: SL too close ({float(sl_dist_pct):.4f} < {float(min_sl_pct):.4f}), "
                f"clamping to min_sl_pct"
            )
            sl_dist_pct = min_sl_pct
            if side.upper() == "BUY":
                stop_price = entry_price * (1 - sl_dist_pct)
            else:
                stop_price = entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "min"
        elif sl_dist_pct > max_sl_pct:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: SL too far ({float(sl_dist_pct):.4f} > {float(max_sl_pct):.4f}), "
                f"clamping to max_sl_pct"
            )
            sl_dist_pct = max_sl_pct
            if side.upper() == "BUY":
                stop_price = entry_price * (1 - sl_dist_pct)
            else:
                stop_price = entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "max"
        
        # Calculate RR (Risk:Reward ratio) = TP distance / SL distance
        current_rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else decimal.Decimal("1.0")

        # Telemetry: capture RR before RR clamp (post SL clamp).
        # This is the RR implied by the pre-guardrail TP distance at this point.
        try:
            tpsl_ctx["rr_pre"] = float(current_rr)
        except Exception:
            pass
        
        # Clamp RR to min/max (adjusts TP, not SL)
        if current_rr < min_tp_rr:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: RR too low ({float(current_rr):.2f} < {float(min_tp_rr):.2f}), "
                f"clamping to min_tp_rr"
            )
            tp_dist_pct = sl_dist_pct * min_tp_rr
            if side.upper() == "BUY":
                target_price = entry_price * (1 + tp_dist_pct)
            else:
                target_price = entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_rr_clamp"] = "min"
            current_rr = min_tp_rr
        elif current_rr > max_tp_rr:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: RR too high ({float(current_rr):.2f} > {float(max_tp_rr):.2f}), "
                f"clamping to max_tp_rr"
            )
            tp_dist_pct = sl_dist_pct * max_tp_rr
            if side.upper() == "BUY":
                target_price = entry_price * (1 + tp_dist_pct)
            else:
                target_price = entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_rr_clamp"] = "max"
            current_rr = max_tp_rr
        
        # Check min distance in bps (after all clamps)
        min_dist_dec = decimal.Decimal(str(min_dist_bps)) / decimal.Decimal("10000")
        if sl_dist_pct < min_dist_dec:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL distance {float(sl_dist_pct)*10000:.1f} bps "
                f"< min_dist_bps {min_dist_bps}"
            )
            return None
        if tp_dist_pct < min_dist_dec:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: TP distance {float(tp_dist_pct)*10000:.1f} bps "
                f"< min_dist_bps {min_dist_bps}"
            )
            return None
        
        # Update telemetry with effective (post-clamp) values
        tpsl_ctx["sl_pct_eff"] = float(sl_dist_pct)
        tpsl_ctx["tp_pct_eff"] = float(tp_dist_pct)
        tpsl_ctx["rr_eff"] = float(current_rr)

        # Convenience aliases for post-clamp observability.
        # Keep existing *_eff fields for backward compatibility.
        tpsl_ctx["sl_pct_post"] = float(sl_dist_pct)
        tpsl_ctx["rr_post"] = float(current_rr)
        
        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": tpsl_ctx,
        }
    
    # =========================================================================
    # END REGIME-BASED TP/SL
    # =========================================================================

    
    def _get_signal_weights(self, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Get signal weights for symbol."""
        weights = getattr(instr_cfg, "weights", None)
        if weights:
            return dict(weights)
        # Fallback to global
        decision = getattr(self.config.strategies.aurora, "decision", None)
        return dict(getattr(decision, "signal_weights", {})) if decision else {}

    def _get_regime_thresholds(self, *, symbol: str, instr_cfg: Any) -> Dict[str, float]:
        """Get regime threshold multipliers for symbol (per-symbol override → global fallback)."""
        thr = getattr(instr_cfg, "regime_thresholds", None)
        if isinstance(thr, dict) and thr:
            return dict(thr)
        try:
            return dict(getattr(self, "regime_thresholds", {}) or {})
        except Exception:
            return {}

    def _check_liquidity_gate(
        self,
        *,
        symbol: str,
        instr_cfg: Any,
        features: Dict[str, Any],
        warmup_readiness: Any,
    ) -> tuple[bool, Dict[str, Any]]:
        """Liquidity gate for Aurora strategy (Score V2).

        Fallback chain:
        1) strategies.aurora.assets.<SYMBOL>.liquidity_gate
        2) strategies.aurora.decision.liquidity_gate
        3) Gate disabled (pass)

        Fail-closed behavior (when enabled):
        - warmup_readiness['liquidity_kappa'] must be True
        - features['liquidity_kappa'] must exist and be parseable
        - liquidity_kappa >= kappa_min
        """
        gate_cfg = getattr(instr_cfg, "liquidity_gate", None) if instr_cfg is not None else None
        if gate_cfg is None:
            gate_cfg = getattr(self, "_global_liquidity_gate_cfg", None)

        enabled_raw = getattr(gate_cfg, "enabled", False) if gate_cfg is not None else False
        if not isinstance(enabled_raw, bool) or not enabled_raw:
            return True, {}

        kappa_min_raw = getattr(gate_cfg, "kappa_min", None)
        kappa_max_raw = getattr(gate_cfg, "kappa_max", None)
        failsafe_qty_check = bool(getattr(gate_cfg, "failsafe_qty_check", True))

        # Readiness contract: require liquidity_kappa readiness when gate is enabled.
        ready_flag = None
        if isinstance(warmup_readiness, dict):
            ready_flag = warmup_readiness.get("liquidity_kappa")
        if ready_flag is not True:
            return False, {
                "reason_code": "LIQUIDITY_NOT_READY",
                "kappa": None,
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        kappa_raw = features.get("liquidity_kappa")
        if kappa_raw is None:
            return False, {
                "reason_code": "LIQUIDITY_MISSING",
                "kappa": None,
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        try:
            kappa = decimal.Decimal(str(kappa_raw))
        except Exception:
            kappa = None
        if kappa is None or (hasattr(kappa, "is_finite") and not kappa.is_finite()):
            return False, {
                "reason_code": "LIQUIDITY_INVALID",
                "kappa": str(kappa_raw),
                "kappa_min": kappa_min_raw,
                "kappa_max": kappa_max_raw,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        # Clamp (defensive only; FE already clamps using its own config).
        try:
            if kappa_max_raw is not None:
                kappa_max = decimal.Decimal(str(kappa_max_raw))
                if kappa > kappa_max:
                    kappa = kappa_max
        except Exception:
            pass

        try:
            kappa_min = decimal.Decimal(str(kappa_min_raw)) if kappa_min_raw is not None else decimal.Decimal("0")
        except Exception:
            kappa_min = decimal.Decimal("0")

        if kappa < kappa_min:
            return False, {
                "reason_code": "LIQUIDITY_LOW",
                "kappa": str(kappa),
                "kappa_min": str(kappa_min),
                "kappa_max": str(kappa_max_raw) if kappa_max_raw is not None else None,
                "ready": ready_flag,
                "failsafe_qty_check": failsafe_qty_check,
            }

        return True, {}
    
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
        """Build SideBiasState for kernel from cached history (per-symbol overrides supported)."""
        instr_cfg = self._get_instrument_config(symbol)
        penalty_factor = self.side_bias_penalty_factor
        window_sec = self.side_bias_window_sec
        target_ratio = self.side_bias_target_ratio
        min_intents = self.side_bias_min_intents

        sb_cfg = getattr(instr_cfg, "side_bias", None) if instr_cfg is not None else None
        if sb_cfg is not None:
            try:
                pen = getattr(sb_cfg, "penalty_factor", None)
                if pen is not None:
                    penalty_factor = float(pen)
                win = getattr(sb_cfg, "window_sec", None)
                if win is not None:
                    window_sec = float(win)
                targ = getattr(sb_cfg, "target_ratio", None)
                if targ is not None:
                    target_ratio = float(targ)
            except Exception:
                # Fail-safe: keep global values if override parsing fails
                pass

        state = self._symbol_states[symbol]
        now = float(self.wall_time_fn())
        
        # Clean old entries outside window
        state.buy_timestamps = [ts for ts in state.buy_timestamps if now - ts < window_sec]
        state.sell_timestamps = [ts for ts in state.sell_timestamps if now - ts < window_sec]
        
        return SideBiasState(
            buy_count=len(state.buy_timestamps),
            sell_count=len(state.sell_timestamps),
            window_sec=window_sec,
            target_ratio=target_ratio,
            penalty_factor=penalty_factor,
            min_intents=min_intents,
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
        
        # === REGIME-BASED TP/SL (AURORA_REGIME_TP_SL_PLAN) ===
        tpsl_result = self._compute_regime_tpsl(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            regime=state.regime,
            instr_cfg=instr_cfg,
            features=features,
        )
        # === END REGIME-BASED TP/SL ===
        
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
        
        # === INJECT REGIME-BASED TP/SL INTO PAYLOAD ===
        if tpsl_result is not None:
            # Strategy Primacy: inject stop_price/target_price into price_ctx
            payload["price_ctx"]["stop_price"] = str(tpsl_result["stop_price"])
            payload["price_ctx"]["target_price"] = str(tpsl_result["target_price"])
            
            # Telemetry: tpsl_ctx for structured analysis
            payload["tpsl_ctx"] = tpsl_result["tpsl_ctx"]
            
            # Append to why_chain for human-readable log
            tpsl_ctx = tpsl_result["tpsl_ctx"]
            tpsl_why = (
                f"tpsl:regime={tpsl_ctx.get('regime_used')} "
                f"mode={tpsl_ctx.get('mode')} "
                f"sl_pct_post={tpsl_ctx.get('sl_pct_post', tpsl_ctx.get('sl_pct_eff', 0)):.4f} "
                f"tp_rr_pre={tpsl_ctx.get('rr_pre', tpsl_ctx.get('tp_rr_eff', tpsl_ctx.get('rr', 0))):.2f} "
                f"rr_post={tpsl_ctx.get('rr_post', tpsl_ctx.get('rr_eff', 0)):.2f}"
            )
            payload["why_chain"] = result.why_chain + [tpsl_why]
            
            self.logger.info(
                f"[{symbol}] REGIME_TPSL: regime={tpsl_ctx.get('regime_used')} "
                f"stop={tpsl_result['stop_price']:.6f} target={tpsl_result['target_price']:.6f}"
            )
        # === END INJECT TP/SL ===
        
        self.logger.info(
            f"[{symbol}] SIGNAL: {side.upper()} score={float(result.score):.4f} "
            f"(thr_buy={float(result.thr_buy):.4f}, thr_sell={float(result.thr_sell):.4f})"
        )
        
        self.emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)
        
        # Update state
        state.last_signal_ts_ms = now_ms
        state.last_signal_side = side
