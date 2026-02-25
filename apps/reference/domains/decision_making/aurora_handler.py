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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    AuroraScoringKernel,
    ScoringResult,
    SideBiasState,
)
# NOTE: compute_direction_strength_score import removed (Plan A SSOT cleanup)
# Linear score is now sourced exclusively from FE pillar_sum.
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.domains.decision_making.shields.null_shield import NullShield
from apps.reference.domains.decision_making.shields.base import ShieldCascade
from apps.reference.domains.decision_making.aurora_tpsl import AuroraTpslMixin
from apps.reference.domains.decision_making.aurora_scoring_helpers import AuroraScoringHelpersMixin
from apps.reference.domains.decision_making.aurora_decision import AuroraDecisionMixin
from apps.reference.domains.decision_making.aurora_config_loader import AuroraConfigLoaderMixin
from apps.reference.domains.decision_making.aurora_holding_period import AuroraHoldingPeriodMixin
from apps.reference.domains.decision_making.shields.context_shield import ContextShield
from apps.reference.domains.decision_making.shields.memory_shield import MemoryShield
from apps.reference.domains.decision_making.shields.danger_zone import DangerZoneShield
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.execution_gate import ExecutionGate
from apps.reference.domains.decision_making.exit_manager import ExitManager
from apps.reference.domains.decision_making.entry_plan import EntryPlan, EntryPlanParams, EntryPlanResult, ObiMissingPolicy
from apps.reference.config_models import (
    ExitManagerConfig,
    OperationalMode,
    DashboardConfig,
)
from apps.reference.domains.decision_making.trade_intent_reject_wal import write_trade_intent_rejected
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract
from apps.reference.domains.decision_making.operational_mode import ModeManager
from apps.reference.domains.decision_making.dashboard import DashboardMetrics, TradeOutcome
from apps.reference.domains.decision_making.instrument_quantizer import (
    quantize_exposure,
    InstrumentSpec as QuantizerSpec,
)


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
        
        # S2-TRAILING: MFE (Max Favorable Excursion) tracking
        self.mfe_price = None  # Decimal: highest price for LONG, lowest for SHORT
        
        # Re-entry cooldown state (Anti-Ping-Pong)
        self.last_exit_timestamp = None
        
        # P0-3: Cached price_motion
        self.cached_price_motion = None


class AuroraHandler(AuroraTpslMixin, AuroraScoringHelpersMixin, AuroraDecisionMixin, AuroraConfigLoaderMixin, AuroraHoldingPeriodMixin):
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
        self._shield_fn = None  # Phase 9: set during _load_config if quadratic
        self._scoring_engine_cfg = None  # Phase 9: ScoringEngineConfig
        
        # Per-symbol state
        self._symbol_states: Dict[str, SymbolState] = defaultdict(SymbolState)
        
        # T2B-01: Tick-path rejection counter for observability
        self._tick_path_rejections: int = 0
        
        # Config extraction
        self._load_config()
    
    # _load_config → moved to AuroraConfigLoaderMixin (see aurora_config_loader.py)

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
    
    # _process_decision → moved to AuroraDecisionMixin (see aurora_decision.py)
    
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

    # Holding period methods → moved to AuroraHoldingPeriodMixin (see aurora_holding_period.py)

    
    # =========================================================================
    # VOL-ADJ GATES METHODS (Anti-Flat / Anti-FOMO)
    # =========================================================================
    # _get_motion_norm_sigma, _apply_vol_adj_gates, _get_signal_weights,
    # _build_shield_cascade, _get_regime_thresholds, _check_liquidity_gate,
    # _get_feature_neutrals, _get_essential_features, _get_side_bias_state,
    # _update_side_bias → moved to AuroraScoringHelpersMixin
    # (see aurora_scoring_helpers.py)
    
    # _emit_signal → moved to AuroraDecisionMixin (see aurora_decision.py)
