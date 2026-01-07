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


logger = logging.getLogger("aurora_handler")


@dataclass
class SymbolState:
    """Per-symbol state for Aurora handler."""
    
    # Regime cache (from EVT:REGIME_DETECTED)
    regime: Optional[str] = None
    regime_confidence: float = 0.0
    regime_ts_ms: int = 0
    
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
        
        # Dependency Injection / Testability
        self.scoring_kernel_cls = AuroraScoringKernel
        
        # Per-symbol state
        self._symbol_states: Dict[str, SymbolState] = defaultdict(SymbolState)
        
        # Config extraction
        self._load_config()
    
    def _load_config(self) -> None:
        """Extract configuration parameters."""
        aurora_cfg = getattr(self.config, "strategies", None)
        aurora = getattr(aurora_cfg, "aurora", None) if aurora_cfg else None
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
            "ts_ms": int(time.time() * 1000),
            "why_chain": list(why_chain or []),
        }
        if details:
            payload["details"] = details
        self.emit_fn("EVT:STRATEGY_DECISION_BLOCKED", payload)
    
    def on_regime_detected(self, event: Dict[str, Any]) -> None:
        """
        Handle EVT:REGIME_DETECTED event.
        
        Updates cached regime state for symbol.
        """
        symbol = event.get("symbol")
        if not symbol:
            return
        
        state = self._symbol_states[symbol]
        state.regime = event.get("regime")
        state.regime_confidence = float(event.get("confidence", 0.0))
        state.regime_ts_ms = int(event.get("ts_ms", int(time.time() * 1000)))
        
        # Update warmup from regime event if present
        warmup = event.get("warmup", {})
        state.warmup_full_ready = bool(warmup.get("full_ready", False))
        state.warmup_ticks_seen = int(warmup.get("ticks_seen", 0))
        
        self.logger.debug(
            f"[{symbol}] Regime cached: {state.regime} (confidence={state.regime_confidence:.2f})"
        )
    
    def on_features_calculated(self, event: Dict[str, Any]) -> None:
        """
        Handle EVT:FEATURES_CALCULATED event.
        
        Triggers scoring kernel if symbol is enabled.
        """
        symbol = event.get("symbol")
        if not symbol:
            return
        
        # Check if symbol is enabled for Aurora
        if not self._is_symbol_enabled(symbol):
            return
        
        # Get instrument config
        instr_cfg = self._get_instrument_config(symbol)
        if not instr_cfg:
            return
        
        # Extract features and readiness
        features = event.get("features", {})
        warmup = event.get("warmup", {})
        warmup_readiness = warmup.get("ready", {})
        
        # Update warmup state
        state = self._symbol_states[symbol]
        state.warmup_full_ready = bool(warmup.get("full_ready", False))
        
        # Check warmup readiness (fail-closed)
        if not state.warmup_full_ready:
            self.logger.debug(f"[{symbol}] Warmup not ready, skipping")
            self._emit_strategy_blocked(
                symbol=symbol,
                reason_code="READINESS_FE_WARMUP_NOT_READY",
                reason="READINESS",
                context="aurora_handler:on_features_calculated",
                details={"warmup_full_ready": False},
                why_chain=["READINESS", "warmup_full_ready:false"],
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
        
        # === [HOLDING PERIOD CHECK: ANTI-CHURN GATE] ===
        # Ensure we check holding period for BOTH exits (neutral) and flips.
        # If suppressed, we must FORCE HOLD by overriding the signal to current side.
        
        # Determine if this signal represents an exit or flip
        # Exit: Neutral signal while in position
        # Flip: Opposite side signal while in position
        is_exit_signal = (not result.side) and (current_position_side != "")
        is_flip_signal = (
            current_position_side != ""
            and result.side
            and result.side.lower() != current_position_side
        )
        
        if is_exit_signal or is_flip_signal:
             if self._should_suppress_soft_exit(symbol, result, is_flip=is_flip_signal):
                 # FORCE HOLD: Override result to maintain current position
                 self.logger.info(
                     f"[{symbol}] HOLDING_PERIOD: Forcing HOLD (side={current_position_side}) "
                     f"suppressing {'flip' if is_flip_signal else 'exit'}"
                 )
                 result.side = current_position_side
                 # Ensure score is sufficient to hold (if needed, but side is primary)
                 
                 # IMPORTANT: If we forced hold, it's no longer a flip or exit.
                 # It becomes a "continue" signal.
        
        # === END HOLDING PERIOD CHECK ===

        if not result.side:
            # === [TRACK EXIT FOR RE-ENTRY COOLDOWN] ===
            if state.position_side:  # Was in position, now exiting
                 state.last_exit_timestamp = __import__("time").time()
                 state.position_side = ""
                 self._clear_entry(symbol)
                 self.logger.info(f"[{symbol}] Position closed (neutral). Starting re-entry cooldown.")
            # === END TRACK EXIT ===
            self.logger.debug(f"[{symbol}] Neutral signal (score={float(result.score):.4f})")
            return

        # === [RE-ENTRY COOLDOWN: ANTI-PING-PONG GATE] ===
        # If we are flat and want to enter, check if we are in cooldown.
        if state.position_side == "" and result.side:
            if state.last_exit_timestamp:
                reentry_cooldown = self._get_reentry_cooldown_sec(symbol)
                time_since_exit = __import__("time").time() - state.last_exit_timestamp
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
        if self._apply_vol_adj_gates(symbol, result, state, features):
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
            and result.side.lower() == "buy"
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
                    "side": result.side,
                    "anchor_symbol": veto_anchor_symbol,
                },
                why_chain=["MACRO_VETO", "ANCHOR_SHOCK_VETO"],
            )
            return  # Do NOT emit signal
        # === END ANCHOR SHOCK VETO ===
        
        # Emit signal
        self._emit_signal(symbol, result, features, event)
        
        # === [TRACK ENTRY FOR HOLDING PERIOD] ===
        # Track entry timestamp when side changes (new entry or flip)
        if result.side and result.side.lower() != current_position_side:
            self._track_entry(symbol, result.side)
        # === END TRACK ENTRY ===
        
        # Update side bias history
        self._update_side_bias(symbol, result.side)
    
    def _is_symbol_enabled(self, symbol: str) -> bool:
        """Check if symbol is enabled for Aurora strategy."""
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
        instr_cfg = self._get_instrument_config(symbol)
        if instr_cfg:
            hp = getattr(instr_cfg, "holding_period", None)
            if hp:
                val = getattr(hp, "min_duration_sec", None)
                if val is not None:
                    return float(val)
        return self.default_min_duration_sec

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
        instr_cfg = self._get_instrument_config(symbol)
        if instr_cfg:
            val = getattr(instr_cfg, "reentry_cooldown_sec", None)
            if val is not None:
                return float(val)
        return self.default_reentry_cooldown_sec

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
        now = time.time()
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
        state.entry_timestamp = time.time()
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
        """
        pm = features.get("price_motion")
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
        self, symbol: str, result: ScoringResult, 
        state: SymbolState, features: Dict[str, Any]
    ) -> bool:
        """
        Apply volatility-adjusted entry gates.
        
        Returns True if entry should be BLOCKED, False if passed.
        Only applies to ENTRY proposals (flat → position).
        """
        if not self.vol_gates_enabled:
            return False
        
        # Only apply to entries (flat → position)
        if not result.side or state.position_side != "":
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
        now = time.time()
        
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
        now = time.time()
        
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
    ) -> None:
        """Emit EVT:STRATEGY_SIGNAL_PRODUCED with readiness contract."""
        state = self._symbol_states[symbol]
        now_ms = int(time.time() * 1000)
        
        # Build payload per v7 contract
        payload = {
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "side": result.side.upper(),
            "ts_ms": now_ms,
            "rid": f"aurora_{symbol}_{now_ms}",
            "why_chain": result.why_chain,
            "readiness": {"warmup_ok": state.warmup_full_ready},
            "price_ctx": {
                "entry_price": str(features.get("price", "0")),
            },
            "scoring": {
                "score": float(result.score),
                "thr_buy": float(result.thr_buy),
                "thr_sell": float(result.thr_sell),
                "regime": result.regime,
                "psi_vector": result.psi_vector,
            },
        }
        
        self.logger.info(
            f"[{symbol}] SIGNAL: {result.side.upper()} score={float(result.score):.4f} "
            f"(thr_buy={float(result.thr_buy):.4f}, thr_sell={float(result.thr_sell):.4f})"
        )
        
        self.emit_fn("EVT:STRATEGY_SIGNAL_PRODUCED", payload)
        
        # Update state
        state.last_signal_ts_ms = now_ms
        state.last_signal_side = result.side
