"""
Aurora Holding Period Mixin.

Extracted from aurora_handler.py (Phase 14A Decomposition).

Provides:
  - Anti-churn holding period logic
  - Entry/exit tracking
  - Re-entry cooldown
  - Emergency exit override
  - Trade execution position sync
"""
from __future__ import annotations

import decimal
import logging
from typing import Any, Dict, Optional

from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult
from apps.reference.domains.decision_making.dashboard import TradeOutcome

logger = logging.getLogger("aurora_handler")


class AuroraHoldingPeriodMixin:
    """
    Mixin: holding period (anti-churn) methods for AuroraHandler.

    Self-attributes used (provided by AuroraHandler):
      - self.logger, self.monotonic_fn, self.dashboard
      - self._symbol_states
      - self.holding_period_enabled, self.holding_apply_to_flips
      - self.default_min_duration_sec, self.default_emergency_threshold
      - self.default_reentry_cooldown_sec
      - self._get_instrument_config(), self._get_time_multiplier()
      - self._emit_strategy_blocked()
    """

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
        state.mfe_price = None  # S2-TRAILING: Reset MFE
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
        if self.dashboard:
            entry_ts = state.entry_timestamp or float(self.monotonic_fn())
            exit_ts = float(self.monotonic_fn())
            duration = exit_ts - entry_ts

            self.dashboard.record_trade(TradeOutcome(
                symbol=symbol,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                pnl_percent=0.0,
                duration_sec=duration,
                is_win=False,
            ))

        state.last_exit_timestamp = float(self.monotonic_fn())
        state.entry_timestamp = None
        state.position_side = ""
        state.mfe_price = None  # S2-TRAILING: Reset MFE
        self.logger.info(
            f"[{symbol}] TRADE_EXECUTED: exit detected (prev={prev_side}, side={side}, qty={qty})"
        )

    # =========================================================================
    # END HOLDING PERIOD METHODS
    # =========================================================================
