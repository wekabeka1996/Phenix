import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional, Protocol

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

logger = logging.getLogger(__name__)


class StrategyHandlerProtocol(Protocol):
    """Protocol for strategy handlers."""
    def register(self) -> None: ...


@dataclass(frozen=True)
class _NoopHandler:
    """Noop handler when legacy path is active."""
    def register(self) -> None:
        logger.warning("⚠️ Aurora Strategy: NOOP Handler Registered (Legacy Path Active)")
        return


class _AuroraHandlerWrapper:
    """
    Wrapper that registers AuroraHandler event listeners.
    
    Only active when legacy_tick_path_enabled is False.
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
        logger.info("🚀 Aurora Strategy: Registering Event Listeners (CMD:PROCESS_STRATEGY, REGIME_DETECTED)")
        self.fsm.listen("CMD:PROCESS_STRATEGY", self._on_process_strategy)
        self.fsm.listen("EVT:REGIME_DETECTED", self._on_regime)
        # T2B-03: Keep FEATURES_CALCULATED for data-only (no warmup update), NOT as trigger
        self.fsm.listen("EVT:FEATURES_CALCULATED", self._on_features_data_only)
        # P0-3-FIX: Position state sync via canonical execution event
        self.fsm.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
    
    def _on_process_strategy(self, event: Any) -> None:
        """T2B-03: Primary entry point - forward CMD:PROCESS_STRATEGY to handler."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_process_strategy(pld)
    
    def _on_regime(self, event: Any) -> None:
        """Forward regime events to handler."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_regime_detected(pld)
    
    def _on_features_data_only(self, event: Any) -> None:
        """T2B-03: Data-only handler for FEATURES_CALCULATED (no warmup update, NO decision trigger)."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_features_data_only(pld)

    def _on_trade_executed(self, event: Any) -> None:
        """P0-3-FIX: Forward execution events to handler."""
        pld = event.pld if hasattr(event, "pld") else event
        self.handler.on_trade_executed(pld)


@dataclass(frozen=True)
class AuroraBuiltinPlugin:
    """
    Plugin for the built-in Aurora strategy.
    
    Phase 4: Routes to either:
    - _NoopHandler when legacy_tick_path_enabled=True (DM-driven)
    - _AuroraHandlerWrapper when legacy_tick_path_enabled=False (Handler-driven)
    """

    strategy_id: str = "aurora"

    def create_handler(
        self, *, fsm: "FSMCore", config: AuroraConfig, monotonic_fn: Optional[Callable[[], float]] = None
    ) -> StrategyHandlerProtocol:
        """
        Create Aurora handler based on config.
        
        Args:
            fsm: Event bus for emitting events.
            config: Aurora configuration.
            monotonic_fn: Optional monotonic clock function for deterministic backtest.
                          If None, uses get_clock().monotonic() (live or global clock).
        
        Returns NoopHandler if legacy path is enabled (default),
        or real AuroraHandler wrapper if legacy path is disabled.
        """
        aurora_cfg = getattr(config.strategies, "aurora", None)
        if not aurora_cfg:
            logger.error("❌ Aurora Strategy: Configuration missing (config.strategies.aurora)")
            return _NoopHandler()
        
        # Check kill-switch
        legacy_enabled = getattr(aurora_cfg, "legacy_tick_path_enabled", True)
        if legacy_enabled:
            logger.warning("⚠️ Aurora Strategy: LEGACY PATH ENABLED. AuroraHandler is SILENT (Noop).")
            logger.warning("   Please set 'legacy_tick_path_enabled: false' in config to activate new architecture.")
            return _NoopHandler()
        
        logger.info("✅ Aurora Strategy: ACTIVATING New Architecture (AuroraHandler)")
        
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
