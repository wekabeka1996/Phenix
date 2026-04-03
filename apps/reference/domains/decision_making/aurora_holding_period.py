"""Holding-period and re-entry timing helpers for AuroraHandler.

This mixin owns the local timer logic that can suppress soft exits or flips,
tracks position timing state off executed trades, and exposes cooldown helpers
used by the decision path. It does not decide whether a signal is valid on its
own; AuroraDecisionMixin calls into these methods after scoring and exit logic.
"""
from __future__ import annotations

import decimal
from typing import Any, Dict

from apps.reference.domains.decision_making.quadratic_scoring_kernel import ScoringResult
from apps.reference.domains.decision_making.dashboard import TradeOutcome


class AuroraHoldingPeriodMixin:
    # Host contract:
    # - self._symbol_states stores the per-symbol timing state owned by AuroraHandler;
    # - self.monotonic_fn is the only timebase used for hold/cooldown math;
    # - self.default_* values are already hydrated by AuroraConfigLoaderMixin;
    # - self._emit_strategy_blocked() is available for blocked-event telemetry.

    # =========================================================================
    # HOLDING PERIOD (ANTI-CHURN) METHODS
    # =========================================================================

    def _get_min_duration_sec(self, symbol: str) -> float:
        """Resolve the active minimum hold duration for a symbol.

        This method only reads the per-symbol override directly. The global
        decision-level value has already been folded into self.default_min_duration_sec
        by the config loader.
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
        # Use the inertia-adjusted regime so timer scaling matches the same
        # effective regime seen by the decision path.
        mult = self._get_time_multiplier(state.regime_effective)
        return base * mult

    def _get_emergency_threshold(self, symbol: str) -> float:
        """Resolve the score magnitude that bypasses the holding-period gate.

        As with the minimum duration, the global decision-level default is
        already materialized into self.default_emergency_threshold.
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
        """Resolve the cooldown applied after a local exit is recorded.

        The loader precomputes the global fallback into
        self.default_reentry_cooldown_sec; this method only layers a per-symbol
        override on top and then applies the effective-regime time multiplier.
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
        """Return True when absolute score reaches the bypass threshold."""
        threshold = self._get_emergency_threshold(symbol)
        return abs(float(score)) >= threshold

    def _should_suppress_soft_exit(
        self,
        symbol: str,
        result: ScoringResult,
        is_flip: bool = False,
    ) -> bool:
        """Return True when a soft exit/flip must be held by anti-churn policy.

        Hard exits from the exit manager bypass this method. Unknown entry time
        fails open so the handler does not deadlock a position after restart or
        state loss.
        """
        # 0. Feature disabled?
        if not self.holding_period_enabled:
            return False

        # 1. Skip if this is a flip and we don't apply to flips
        if is_flip and not self.holding_apply_to_flips:
            return False

        # 2. Read the current local position timing state.
        state = self._symbol_states[symbol]
        entry_ts = state.entry_timestamp

        if entry_ts is None:
            # FAIL-OPEN: No tracked entry → allow exit
            return False

        # 3. Compare elapsed monotonic time against the scaled min duration.
        now = float(self.monotonic_fn())
        min_duration = self._get_min_duration_sec(symbol)
        time_in_position = now - entry_ts

        if time_in_position >= min_duration:
            # Holding period elapsed → allow exit
            return False

        # 4. Emergency override is score-driven and intentionally ignores the
        # remaining hold time.
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

        # Emit a blocked event because the caller will otherwise only observe a
        # forced HOLD outcome, not the reason the soft exit/flip was denied.
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
            why_chain=["HOLDING_PERIOD",
                       f"time:{time_in_position:.1f}s", f"min:{min_duration}s"],
        )

        return True

    def _track_entry(self, symbol: str, side: str) -> None:
        """Stamp a local entry using the handler monotonic clock.

        This helper updates only local timer state. Production position truth is
        normally established by on_trade_executed(), not by signal emission.
        """
        state = self._symbol_states[symbol]
        state.entry_timestamp = float(self.monotonic_fn())
        state.position_side = side.lower()
        self.logger.debug(
            f"[{symbol}] Entry tracked: side={side}, ts={state.entry_timestamp}")

    def _clear_entry(self, symbol: str) -> None:
        """Clear local timing markers for a closed position.

        This does not stamp last_exit_timestamp; callers that start a cooldown
        must record the exit time separately before clearing the entry state.
        """
        state = self._symbol_states[symbol]
        state.entry_timestamp = None
        state.position_side = ""
        state.mfe_price = None  # S2-TRAILING: Reset MFE
        self.logger.debug(f"[{symbol}] Entry tracking cleared")

    def on_trade_executed(self, event: Dict[str, Any]) -> None:
        """Sync local position timing state from an executed-trade event.

        Only quantity-bearing buy/sell executions mutate state here. This mixin
        uses the handler monotonic clock rather than event wall-clock timestamps
        so holding-period and cooldown calculations stay on one timebase.
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
            # A fresh entry starts the hold timer; if we had a prior local exit,
            # also feed the objective-engine reentry counter.
            state.entry_timestamp = float(self.monotonic_fn())
            state.position_side = side
            if state.last_exit_timestamp is not None:
                state.objective_reentry_ts_ms.append(
                    int(self.monotonic_fn() * 1000))
            self.logger.info(
                f"[{symbol}] TRADE_EXECUTED: entry confirmed (side={side}, qty={qty})"
            )
            return

        if state.position_side == side:
            self.logger.debug(
                f"[{symbol}] TRADE_EXECUTED: add to position (side={side}, qty={qty})"
            )
            return

        # Without execution-side position reconciliation in this mixin, an
        # opposite fill is treated conservatively as a close/flatten event
        # rather than assuming an immediate reversal is fully established.
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
