"""
QoSRateControl — Rate limiting, cooldowns, and exposure block logic.

Extracted from decision_making.py (Phase 14A decomposition).
Manages per-strategy, per-symbol QoS state partitions.

LOC budget: ≤500 (Constitution §3).
"""

import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from .normalized_reject_reasons import NormalizedRejectReasons

if TYPE_CHECKING:
    from apps.reference.core.time.clock import Clock


class QoSRateControl:
    """
    QoS rate-limiting for DecisionMaking domain.

    State is partitioned by strategy_id to prevent cross-strategy rate-limiting.
    Shared mutable dicts (qos_state) are passed by reference from facade.
    """

    def __init__(
        self,
        clock: "Clock",
        qos_state: dict,
        apply_to_strategies: set,
        exposure_block_cooldown_sec: int,
        max_intents_per_minute_per_symbol: int,
        get_symbol_cooldown: Callable[[str, str], int],
        logger: logging.Logger,
    ) -> None:
        self._clock = clock
        self._qos_state = qos_state
        self._apply_to_strategies = apply_to_strategies
        self.exposure_block_cooldown_sec = exposure_block_cooldown_sec
        self.max_intents_per_minute_per_symbol = max_intents_per_minute_per_symbol
        self._get_symbol_cooldown = get_symbol_cooldown
        self.logger = logger

    # ── Strategy Filter ──────────────────────────────────────────────

    def qos_enabled_for_strategy(self, strategy_id: str) -> bool:
        """Return True if QoS should be applied for this strategy_id in the strategy gateway."""
        if not self._apply_to_strategies:
            return True
        return str(strategy_id) in self._apply_to_strategies

    # ── Allow Check ──────────────────────────────────────────────────

    def qos_allow(
        self, symbol: str, strategy_id: str = "aurora", is_exposure_block: bool = False
    ) -> tuple:
        """
        Check if decision is allowed based on QoS rules (PACK EXP-4).
        Partitioned by strategy_id (v7) to prevent cross-strategy rate-limiting.

        Returns:
            Tuple of (allowed: bool, reject_reason: Optional[str])
        """
        current_time = self._clock.now_sec()
        strat_state = self._qos_state[strategy_id]  # auto-creates via defaultdict

        # Check exposure block cooldown (only for exposure-related checks)
        if is_exposure_block:
            last_exposure_block: float = float(strat_state.get("last_exposure_block", 0.0))
            time_since_last_block = current_time - last_exposure_block
            if time_since_last_block < self.exposure_block_cooldown_sec:
                remaining = self.exposure_block_cooldown_sec - time_since_last_block
                reject_reason = (
                    f"exposure_block_cooldown_active_{remaining:.1f}s_remaining"
                )
                self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
                return False, NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

        # Check symbol cooldown (prevents rapid-fire decisions for same symbol)
        symbol_cooldowns: dict[str, Any] = strat_state.get("symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        time_since_last_decision = current_time - last_decision
        symbol_cooldown_limit = self._get_symbol_cooldown(symbol, strategy_id)
        if time_since_last_decision < symbol_cooldown_limit:
            remaining = symbol_cooldown_limit - time_since_last_decision
            reject_reason = f"symbol_cooldown_active_{remaining:.1f}s_remaining_limit={symbol_cooldown_limit}s"
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        # Check rate limit (intents per minute per symbol) - separate from cooldown
        symbol_intent_counts: dict[str, Any] = strat_state.get("symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(symbol, {"count": 0, "window_start": current_time})
        window_start = intent_data.get("window_start", current_time)
        window_elapsed = current_time - window_start

        # Reset window if more than a minute has passed
        if window_elapsed >= 60:
            intent_data["count"] = 0
            intent_data["window_start"] = current_time

        if intent_data.get("count", 0) >= self.max_intents_per_minute_per_symbol:
            reject_reason = (
                f"rate_limit_exceeded_{intent_data['count']}_intents_in_window"
            )
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        return True, None

    # ── State Updates ────────────────────────────────────────────────

    def update_symbol_cooldown(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update cooldown timestamp for symbol (prevents rapid-fire decisions).

        T2B-08: Uses injected Clock for deterministic testing.
        """
        current_time = self._clock.now_sec()
        strat_state = self._qos_state[strategy_id]
        if "symbol_cooldowns" not in strat_state:
            strat_state["symbol_cooldowns"] = {}
        strat_state["symbol_cooldowns"][symbol] = current_time
        self.logger.debug(
            f"[{symbol}] QoS cooldown updated: ts={current_time} strategy={strategy_id}")

    def update_intent_count(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update intent count for rate limiting (partitioned by strategy_id)."""
        strat_state = self._qos_state[strategy_id]
        if "symbol_intent_counts" not in strat_state:
            strat_state["symbol_intent_counts"] = {}
        symbol_intent_counts = strat_state["symbol_intent_counts"]

        if symbol not in symbol_intent_counts:
            # T2B-08: Use Clock for rate-limit window start
            symbol_intent_counts[symbol] = {"count": 0, "window_start": self._clock.now_sec()}
        intent_data = symbol_intent_counts[symbol]
        intent_data["count"] = intent_data.get("count", 0) + 1
        self.logger.debug(
            f"[{symbol}] QoS intent count updated: count={intent_data['count']} strategy={strategy_id}"
        )

    def calculate_next_allowed_time(self, symbol: str, strategy_id: str = "aurora") -> int:
        """Calculate next allowed timestamp for symbol based on QoS rules.

        T2B-08: Uses injected Clock for deterministic testing.
        QOS-SPLIT-BRAIN-FIX: Now strategy-aware (reads from correct partition).
        """
        current_time = self._clock.now_sec()
        next_allowed = current_time

        # QOS-SPLIT-BRAIN-FIX: Read from strategy-specific partition
        strat_state = self._qos_state[strategy_id]

        # Check symbol cooldown (uses per-symbol resolver)
        symbol_cooldowns: dict[str, Any] = strat_state.get("symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        cooldown_duration = self._get_symbol_cooldown(symbol, strategy_id)

        cooldown_end: float = last_decision + cooldown_duration
        next_allowed = max(next_allowed, cooldown_end)

        # Check rate limit window
        symbol_intent_counts: dict[str, Any] = strat_state.get("symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(symbol, {"count": 0, "window_start": current_time})
        window_start = float(intent_data.get("window_start", current_time))
        window_end: float = window_start + 60
        intent_count: int = int(intent_data.get("count", 0))
        if intent_count >= self.max_intents_per_minute_per_symbol:
            next_allowed = max(next_allowed, window_end)

        return int(next_allowed * 1000)  # Convert to milliseconds

    def update_qos_state(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update QoS state after making a decision.

        T2B-08: Uses injected Clock for deterministic testing.
        """
        current_time = self._clock.now_sec()

        # Get strategy-partitioned state (auto-initialize if missing)
        strategy_state = self._qos_state[strategy_id]

        # Update symbol cooldown
        strategy_state["symbol_cooldowns"][symbol] = current_time

        # Update rate limit counters
        symbol_intent_counts = strategy_state["symbol_intent_counts"]
        if symbol not in symbol_intent_counts:
            symbol_intent_counts[symbol] = {"count": 0, "window_start": current_time}

        intent_data: dict[str, Any] = symbol_intent_counts[symbol]
        window_start: float = float(intent_data.get("window_start", current_time))
        window_end: float = window_start + 60

        if current_time >= window_end:
            # Reset window
            intent_data["window_start"] = current_time
            intent_data["count"] = 1
        else:
            intent_data["count"] = intent_data.get("count", 0) + 1

        self.logger.debug(
            f"[{symbol}] QoS state updated ({strategy_id}): cooldown={current_time}, intents={intent_data['count']}")

    # ── Exposure Block ───────────────────────────────────────────────

    def handle_exposure_block(self, symbol: str) -> None:
        """Handle exposure block event by updating QoS state.

        T2B-08: Uses injected Clock for deterministic testing.
        NOTE: Split-Brain bug documented — writes to flat key, not partitioned.
        """
        current_time = self._clock.now_sec()
        self._qos_state["last_exposure_block"] = current_time
        self.logger.warning(
            f"[{symbol}] Exposure block recorded at {current_time} "
            f"(WARNING: This may have no effect due to Split-Brain bug)")
