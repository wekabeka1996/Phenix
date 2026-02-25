"""
DMConfigResolver — Configuration resolution and strategy arbitration.

Extracted from decision_making.py (Phase 14A decomposition).
Pure config lookups + strategy arbitration logic. No FSM side effects.

LOC budget: ≤500 (Constitution §3).
"""

import decimal
import logging
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from apps.reference.utils.accessors import aget

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig, AuroraInstrumentConfig


class DMConfigResolver:
    """
    All config resolution and strategy arbitration for DecisionMaking domain.

    Extracts per-instrument overrides, global fallbacks, and multi-strategy
    arbitration from AuroraConfig (strict Pydantic model).

    State: Only reads config + maintains arb_signal_buffer/arb_window_winner
    (mutable dicts shared with facade).
    """

    def __init__(
        self,
        config: "AuroraConfig",
        strategies_registry: Any,
        arb_signal_buffer: Dict[str, Tuple],
        arb_window_winner: Dict[str, Tuple],
        flip_global_enabled: bool,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.strategies_registry = strategies_registry
        self._arb_signal_buffer = arb_signal_buffer
        self._arb_window_winner = arb_window_winner
        self.flip_global_enabled = flip_global_enabled
        self.logger = logger

    # ── Strategy Assignment ─────────────────────────────────────────

    def is_strategy_assigned(self, symbol: str, strategy_id: str) -> bool:
        """
        Check if a specific strategy is assigned to a symbol in strategies_registry.

        STRATEGY-AWARE-GATES-FIX: This is the SSOT for strategy activation.
        """
        if not self.strategies_registry:
            return strategy_id == "aurora"

        assignments = self.strategies_registry.assignments.get(symbol, [])
        return strategy_id in assignments

    # ── Strategy Arbitration ────────────────────────────────────────

    def check_strategy_arbitration(
        self,
        symbol: str,
        strategy_id: str,
        *,
        ts_ms: int | None = None,
        commit: bool = False,
    ) -> Dict[str, Any]:
        """
        Check if strategy is allowed to generate intent for symbol based on arbitration rules.

        CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Implements deterministic arbitration.
        DM-CRITICAL-PATCHES-02: Uses dedicated signal buffer with priority ranks.

        Returns:
            Dict with keys: allowed (bool), reason (str)
        """
        if not self.strategies_registry:
            return {"allowed": True, "reason": ""}

        assignments = (
            self.strategies_registry.assignments[symbol]
            if symbol in self.strategies_registry.assignments
            else []
        )

        if not assignments:
            self.logger.warning(
                f"[{symbol}] ARBITRATION: symbol not in registry. "
                f"Assignments: {list(self.strategies_registry.assignments.keys())}"
            )
            return {
                "allowed": False,
                "reason": "ARBITRATION_REJECT:symbol_not_in_registry",
            }

        if strategy_id not in assignments:
            self.logger.warning(
                f"[{symbol}] ARBITRATION: strategy {strategy_id!r} not in assignments {assignments!r}"
            )
            return {
                "allowed": False,
                "reason": "ARBITRATION_REJECT:strategy_not_assigned_to_symbol",
            }

        if len(assignments) == 1:
            return {"allowed": True, "reason": ""}

        # Multi-strategy case: priority arbitration with dedicated buffer
        arb = self.strategies_registry.arbitration

        if arb.mode != "priority":
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:unknown_mode_{arb.mode}"[:80],
            }

        rank = arb.priority.get(strategy_id)
        if rank is None:
            self.logger.error(
                f"[{symbol}] ARBITRATION: strategy {strategy_id!r} missing priority rank (fail-closed DROP)"
            )
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:missing_priority:{strategy_id}"[:80],
            }

        for strat in assignments:
            if strat not in arb.priority:
                return {
                    "allowed": False,
                    "reason": f"ARBITRATION_REJECT:missing_priority:{strat}"[:80],
                }

        if ts_ms is None:
            return {"allowed": True, "reason": ""}

        try:
            window_ms = int(arb.window_ms)
        except Exception:
            return {"allowed": False, "reason": "ARBITRATION_REJECT:invalid_window_ms"[:80]}
        if window_ms <= 0:
            return {"allowed": False, "reason": "ARBITRATION_REJECT:invalid_window_ms"[:80]}

        now_ms = int(ts_ms)
        existing = self._arb_signal_buffer.get(symbol)

        if existing is not None:
            last_ts, last_sid, last_rank = existing
            delta_ms = now_ms - last_ts

            if delta_ms <= window_ms:
                if rank < last_rank:
                    self.logger.info(
                        f"[{symbol}] ARBITRATION: {strategy_id}(rank={rank}) overrides "
                        f"{last_sid}(rank={last_rank}) delta={delta_ms}ms window={window_ms}ms"
                    )
                    if commit:
                        self._arb_signal_buffer[symbol] = (now_ms, strategy_id, rank)
                        self._arb_window_winner[symbol] = (now_ms // window_ms, strategy_id)
                    return {"allowed": True, "reason": ""}
                elif rank >= last_rank:
                    self.logger.info(
                        f"[{symbol}] ARBITRATION: dropped {strategy_id}(rank={rank}) - "
                        f"window claimed by {last_sid}(rank={last_rank}) delta={delta_ms}ms"
                    )
                    return {
                        "allowed": False,
                        "reason": f"{arb.logging.rejected_why_prefix}:lower_priority_vs_{last_sid}"[:80],
                    }

        if commit:
            self._arb_signal_buffer[symbol] = (now_ms, strategy_id, rank)
            self._arb_window_winner[symbol] = (now_ms // window_ms, strategy_id)
        return {"allowed": True, "reason": ""}

    # ── Per-Instrument Config Lookups ───────────────────────────────

    def get_aurora_instrument_cfg(self, symbol: str) -> "Optional[AuroraInstrumentConfig]":
        """
        Get per-instrument Aurora configuration for a symbol.

        Fallback chain:
        1. config.strategies.aurora.assets[SYMBOL]
        2. None (caller falls back to global)
        """
        if not self.config:
            return None

        aurora = getattr(self.config.strategies, "aurora", None)
        if aurora is None:
            return None

        return aurora.assets.get(symbol)

    def get_position_sizing_config(self):
        """Get position sizing configuration from domains.yaml. SSOT."""
        if hasattr(self.config, "domains") and hasattr(self.config.domains, "decision_making"):
            dm_cfg = self.config.domains.decision_making
            if hasattr(dm_cfg, "position_sizing") and dm_cfg.position_sizing is not None:
                return dm_cfg.position_sizing

        return self.config.domains.decision_making.position_sizing

    def get_symbol_cooldown(self, symbol: str, strategy_id: str = "aurora") -> int:
        """
        Get per-symbol cooldown in seconds (partitioned by strategy_id).

        Fallback: strategies.<strategy_id>.assets.<SYMBOL>.cooldown_sec → default 3s.
        """
        if strategy_id == "aurora":
            instr_cfg = self.get_aurora_instrument_cfg(symbol)
            if instr_cfg is not None:
                cooldown = aget(instr_cfg, "cooldown_sec", None)
                if cooldown is not None:
                    return int(cooldown)

        return self._default_symbol_cooldown_sec

    @property
    def _default_symbol_cooldown_sec(self) -> int:
        """Resolve default cooldown from config."""
        try:
            dm_cfg = self.config.domains.decision_making
            qos = getattr(dm_cfg, "qos", None)
            if qos:
                val = getattr(qos, "symbol_cooldown_sec", None)
                if val is not None:
                    return int(val)
        except AttributeError:
            pass
        return 3  # Safe default

    def get_param(self, symbol: str, param: str, default: Any) -> Any:
        """
        Get configuration parameter with per-instrument override support.

        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.<param>
        2. strategies.aurora.decision.<param>
        3. default value
        """
        instr_cfg = self.get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            value = aget(instr_cfg, param, None)
            if value is not None:
                return value

        global_value = aget(self.config.strategies.aurora.decision, param, default)
        return global_value if global_value is not None else default

    def get_side_bias_params(self, symbol: str) -> tuple:
        """
        Get side_bias parameters with per-instrument override.

        Returns:
            (penalty_factor, window_sec, target_ratio, min_intents)

        Raises:
            ValueError: If required params missing (fail-closed).
        """
        dm = self.config.strategies.aurora.decision
        instr_cfg = self.get_aurora_instrument_cfg(symbol)
        sb = aget(instr_cfg, "side_bias", None)

        def get_val(item_key, global_attr, default=None):
            val = aget(sb, item_key, None) if sb else None
            if val is not None:
                return val
            glob = getattr(dm, global_attr, None)
            return glob if glob is not None else default

        penalty = get_val("penalty_factor", "side_bias_penalty_factor")
        window = get_val("window_sec", "side_bias_window_sec")
        target = get_val("target_ratio", "side_bias_target_ratio")
        min_intents = get_val("min_intents", "side_bias_min_intents")

        if penalty is None:
            raise ValueError(f"side_bias_penalty_factor is required for {symbol}")
        if window is None:
            raise ValueError(f"side_bias_window_sec is required for {symbol}")
        if target is None:
            raise ValueError(f"side_bias_target_ratio is required for {symbol}")
        if min_intents is None:
            raise ValueError(f"side_bias_min_intents is required for {symbol}")

        return (penalty, window, target, min_intents)

    def get_regime_thresholds(self, symbol: str) -> dict:
        """
        Get regime threshold multipliers with per-instrument override.

        Fallback: per-instrument → global → empty dict.
        """
        instr_cfg = self.get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            thresholds = aget(instr_cfg, "regime_thresholds", None)
            if thresholds is not None:
                return thresholds

        dm = self.config.strategies.aurora.decision
        global_thresholds = (
            dm.regime_threshold_multipliers
            if dm.regime_threshold_multipliers is not None
            else {}
        )
        return global_thresholds

    def get_signal_threshold(self, symbol: str) -> decimal.Decimal:
        """
        Get signal threshold with per-instrument override (Phase 3+).

        Raises:
            AttributeError: If global config missing (fail-closed).
        """
        instr_cfg = self.get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            st_cfg = aget(instr_cfg, "signal_threshold", None)
            if st_cfg is not None and st_cfg.enabled:
                if st_cfg.value is not None:
                    return decimal.Decimal(str(st_cfg.value))

        decision_config = self.config.strategies.aurora.decision
        return decimal.Decimal(str(decision_config.signal_threshold))

    def get_flip_config(self, symbol: str) -> Tuple[bool, float]:
        """Get flip orchestration config for symbol (STRICT - no defaults).

        Returns:
            Tuple of (flip_enabled: bool, hysteresis_mult: float)

        Raises:
            ConfigContractError: if per-symbol flip config is missing.
        """
        if not self.flip_global_enabled:
            return (False, 1.0)

        instr = self.config.instruments.get(symbol)
        if not instr:
            raise ConfigContractError(
                path=f"instruments.{symbol}",
                why=f"Missing instruments config for active symbol {symbol}",
            )

        if not instr.flip:
            raise ConfigContractError(
                path=f"instruments.{symbol}.flip",
                why=f"Missing REQUIRED flip config for symbol {symbol}. "
                f"Add flip.enabled + flip.hysteresis_mult.",
            )

        return (
            bool(instr.flip.enabled),
            max(1.0, float(instr.flip.hysteresis_mult)),
        )

    def get_precision(self, symbol: str) -> Tuple[float, float]:
        """Return (tick_size, step_size) from canonical config.instruments; fail-closed.

        CFG-INSTRUMENTS-STEP-02-DM-PRECISION

        Raises:
            ValueError: If symbol missing or precision fields not set.
        """
        instruments = self.config.instruments
        if not instruments or symbol not in instruments:
            raise ValueError(
                f"Missing instrument config for {symbol} in config.instruments (SSOT)"
            )

        spec = instruments[symbol]
        tick_size = aget(spec, "tick_size", None)
        step_size = aget(spec, "step_size", None)

        if tick_size is None or step_size is None:
            raise ValueError(
                f"Missing precision for {symbol}: tick_size={tick_size}, step_size={step_size}"
            )

        return float(tick_size), float(step_size)
