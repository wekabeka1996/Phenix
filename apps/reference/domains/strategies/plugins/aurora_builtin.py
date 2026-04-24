import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional, Protocol

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.decision_making.contracts.boundary_models import (
    ProcessStrategyBoundary,
    RegimeDetectedBoundary,
)
from apps.reference.domains.decision_making.contracts.boundary_mappers import (
    map_process_strategy_boundary_to_cmd,
    map_regime_boundary_to_event,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

logger = logging.getLogger(__name__)


class StrategyHandlerProtocol(Protocol):
    """Protocol for strategy handlers."""

    def register(self) -> None: ...


# SCORCHED-EARTH-2026-01-27: _NoopHandler DELETED
# Migration to AuroraHandler complete. legacy_tick_path_enabled was always False in config.


class _DisabledAuroraHandlerWrapper:
    """Wrapper that does NOTHING, enforcing the global disable killswitch."""

    def register(self) -> None:
        logger.warning(
            "⚠️ Aurora Strategy: Handler is GLOBALLY DISABLED. No event listeners registered.")

    def apply_runtime_analytics_restore_snapshot(self, snapshot: Any) -> None:
        pass

    def get_runtime_analytics_restore_snapshot(self, symbol: str) -> Any:
        return None


class _AuroraHandlerWrapper:
    """
    Wrapper that registers AuroraHandler event listeners.

    SCORCHED-EARTH-2026-01-27: This is now the ONLY handler (legacy path removed).
    """

    def __init__(self, handler: AuroraHandler, fsm: "FSMCore"):
        self.handler = handler
        self.fsm = fsm

    def register(self) -> None:
        """Register event listeners for Aurora handler.

        T2B-03: Primary trigger is CMD:PROCESS_STRATEGY.
        EVT:FEATURES_CALCULATED is kept for backwards compatibility (data-only, NO trigger).
        EVT:REGIME_DETECTED still updates cached regime state.
        """
        logger.info(
            "🚀 Aurora Strategy: Registering Event Listeners (CMD:PROCESS_STRATEGY, REGIME_DETECTED)")
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime)
        self.fsm.listen("EVT:SYSTEM_STRESS_STATE_UPDATED",
                        self._on_system_stress)
        # T2B-03: Keep FEATURES_CALCULATED for data-only (no warmup update), NOT as trigger
        self.fsm.listen("EVT:FEATURES_CALCULATED", self._on_features_data_only)
        # P0-3-FIX: Position state sync via canonical execution event
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_state)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED",
                        self._on_exposure_summary)
        self.fsm.listen("EVT:ORDER_STATE_CHANGED",
                        self._on_order_state_changed)
        self.fsm.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)

    def apply_runtime_analytics_restore_snapshot(self, snapshot: Any) -> None:
        apply_fn = getattr(
            self.handler, "apply_runtime_analytics_restore_snapshot", None)
        if callable(apply_fn):
            apply_fn(snapshot)

    def get_runtime_analytics_restore_snapshot(self, symbol: str) -> Any:
        getter = getattr(
            self.handler, "get_runtime_analytics_restore_snapshot", None)
        if callable(getter):
            return getter(symbol)
        return None

    def _on_process_strategy(self, event: Any) -> None:
        """T2B-03: Primary entry point.

        Parse CMD:PROCESS_STRATEGY at the earliest FSM boundary, map to
        ProcessStrategyCmd, then forward the typed model to the handler.
        Malformed payloads (missing symbol or unparseable structure) are
        logged and dropped here — no WAL record because no intent exists yet.
        """
        pld = event.pld if hasattr(event, "pld") else event
        raw = dict(pld) if isinstance(pld, dict) else {}
        try:
            boundary = ProcessStrategyBoundary.model_validate(pld)
            cmd_core = map_process_strategy_boundary_to_cmd(boundary, raw=raw)
        except ValidationError as exc:
            symbol_raw = raw.get("symbol", "unknown")
            logger.warning(
                "[%s] CMD:PROCESS_STRATEGY boundary validation failed at plugin ingress: %s",
                symbol_raw,
                exc,
            )
            return
        self.handler.on_process_strategy(cmd_core)

    def _on_regime(self, event: Any) -> None:
        """Parse EVT:REGIME_DETECTED at the FSM boundary, forward typed model.

        Malformed payloads (missing symbol or regime) are logged and dropped.
        """
        pld = event.pld if hasattr(event, "pld") else event
        raw = dict(pld) if isinstance(pld, dict) else {}
        try:
            boundary = RegimeDetectedBoundary.model_validate(pld)
            evt_core = map_regime_boundary_to_event(boundary, raw=raw)
        except ValidationError as exc:
            symbol_raw = raw.get("symbol", "unknown")
            logger.warning(
                "[%s] EVT:REGIME_DETECTED boundary validation failed at plugin ingress: %s",
                symbol_raw,
                exc,
            )
            return
        self.handler.on_regime_detected(evt_core)

    def _on_system_stress(self, event: Any) -> None:
        """Forward system stress events to handler."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_system_stress(pld)

    def _on_features_data_only(self, event: Any) -> None:
        """T2B-03: Data-only handler for FEATURES_CALCULATED (no warmup update, NO decision trigger)."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_features_data_only(pld)

    def _on_trade_executed(self, event: Any) -> None:
        """P0-3-FIX: Forward execution events to handler."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_trade_executed(pld)

    def _on_portfolio_state(self, event: Any) -> None:
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_portfolio_state(pld)

    def _on_exposure_summary(self, event: Any) -> None:
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_exposure_summary(pld)

    def _on_order_state_changed(self, event: Any) -> None:
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_order_state_changed(pld)

    def _on_trade_intent_rejected(self, event: Any) -> None:
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_trade_intent_rejected(pld)


@dataclass(frozen=True)
class AuroraBuiltinPlugin:
    """
    Plugin for the built-in Aurora strategy.

    SCORCHED-EARTH-2026-01-27: Legacy path removed. Always uses AuroraHandler.
    """

    strategy_id: str = "aurora"

    def create_handler(
        self, *, fsm: "FSMCore", config: AuroraConfig, monotonic_fn: Optional[Callable[[], float]] = None
    ) -> StrategyHandlerProtocol:
        """
        Create Aurora handler.

        Args:
            fsm: Event bus for emitting events.
            config: Aurora configuration.
            monotonic_fn: Optional monotonic clock function for deterministic backtest.
                          If None, uses get_clock().monotonic() (live or global clock).

        Returns AuroraHandler wrapper (legacy path removed).
        """
        aurora_cfg = getattr(config.strategies, "aurora", None)
        if not aurora_cfg:
            logger.error(
                "❌ Aurora Strategy: Configuration missing (config.strategies.aurora)")
            raise ValueError(
                "Aurora strategy configuration missing - cannot create handler")

        # Phase 3 Killswitch enforcement
        is_enabled = getattr(aurora_cfg, "enabled", True)
        registry = getattr(config, "strategies_registry", None)
        has_assignments = False
        if registry:
            assignments = getattr(registry, "assignments", {}) or {}
            has_assignments = any(
                self.strategy_id in strats for strats in assignments.values())

        if not is_enabled:
            if has_assignments:
                from apps.reference.config_contract import ConfigContractError
                raise ConfigContractError(
                    path="strategies.aurora.enabled",
                    why=f"Aurora Strategy is globally disabled (enabled=False) but still assigned to symbols in strategies_registry.assignments. Please remove '{self.strategy_id}' from assignments to bypass this fail-closed validation."
                )
            else:
                logger.warning(
                    "⚠️ Aurora Strategy is GLOBALLY DISABLED (enabled=False). Creating disconnected handler.")
                return _DisabledAuroraHandlerWrapper()

        # Migration complete. Always use AuroraHandler.
        logger.info("✅ Aurora Strategy: Creating AuroraHandler")

        # Create real handler
        def emit_fn(event_name: str, payload: dict) -> None:
            fsm.emit(event_name, payload, why="aurora_handler")

        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            strategy_id=self.strategy_id,
            monotonic_fn=monotonic_fn,
        )

        logger.info(f"   - Handler ID: {self.strategy_id}")
        logger.info("   - Contract: v7 (Readiness/QoS Partitioned)")

        return _AuroraHandlerWrapper(handler, fsm)
