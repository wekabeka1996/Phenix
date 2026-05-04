from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LlmMicrostructureSentinelHandler:
    """Sentinel handler: llm_microstructure is bridge-driven via shadow_telemetry.

    No FSM listeners are registered here — the actual intent injection is
    performed by ``apps.reference.domains.shadow_telemetry.main_bridge``.
    This handler exists solely to satisfy the StrategyRuntime``.register()`` contract.
    """

    def register(self) -> None:
        LOG.info(
            "LlmMicrostructurePlugin: bridge-driven strategy; "
            "FSM listeners managed by shadow_telemetry.main_bridge"
        )


@dataclass(frozen=True)
class LlmMicrostructurePlugin:
    """Allowlist sentinel plugin for the ``llm_microstructure`` strategy.

    The strategy behaviour is externally driven by the shadow_telemetry bridge
    (``apps/reference/domains/shadow_telemetry/main_bridge.py``).
    This plugin is registered solely to pass the StrategyRuntime allowlist check
    for symbols that have ``llm_microstructure`` in their
    ``strategies_registry.assignments`` (e.g. BNBUSDT).
    """

    strategy_id: str = "llm_microstructure"

    def create_handler(
        self,
        *,
        fsm: "FSMCore",
        config: AuroraConfig,
    ) -> _LlmMicrostructureSentinelHandler:
        return _LlmMicrostructureSentinelHandler()
