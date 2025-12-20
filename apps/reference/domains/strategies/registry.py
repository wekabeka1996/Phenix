from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, TYPE_CHECKING, runtime_checkable

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_models import AuroraConfig

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


LOG = logging.getLogger(__name__)


@runtime_checkable
class StrategyHandler(Protocol):
    """Stateful strategy handler that registers its FSM listeners."""

    def register(self) -> None: ...


@runtime_checkable
class StrategyPlugin(Protocol):
    """Allowlisted strategy plugin factory."""

    strategy_id: str

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> StrategyHandler: ...


class StrategyPluginRegistry:
    """In-process allowlist mapping `strategy_id` → plugin."""

    def __init__(self) -> None:
        self._plugins: Dict[str, StrategyPlugin] = {}

    def register(self, plugin: StrategyPlugin) -> None:
        strategy_id = getattr(plugin, "strategy_id", None)
        if not isinstance(strategy_id, str) or not strategy_id:
            raise ValueError("StrategyPlugin.strategy_id must be a non-empty str")
        if strategy_id in self._plugins:
            raise ValueError(f"Duplicate strategy_id registered: {strategy_id}")
        self._plugins[strategy_id] = plugin

    def get(self, strategy_id: str) -> Optional[StrategyPlugin]:
        return self._plugins.get(strategy_id)

    def ids(self) -> list[str]:
        return sorted(self._plugins.keys())


@dataclass(frozen=True)
class StrategyRuntime:
    """Bootstraps strategy handlers for strategy_ids assigned in SSOT strategies.yaml."""

    fsm: "FSMCore"
    config: AuroraConfig
    registry: StrategyPluginRegistry

    def start(self) -> None:
        sr = getattr(self.config, "strategies_registry", None)
        if sr is None:
            LOG.warning("StrategyRuntime: config.strategies_registry missing; no plugins started")
            return

        assignments = getattr(sr, "assignments", None)
        if not isinstance(assignments, dict) or not assignments:
            LOG.warning("StrategyRuntime: strategies_registry.assignments missing/empty; no plugins started")
            return

        assigned_ids: set[str] = set()
        for _, ids in assignments.items():
            if not isinstance(ids, list):
                continue
            for strategy_id in ids:
                if isinstance(strategy_id, str) and strategy_id:
                    assigned_ids.add(strategy_id)

        if not assigned_ids:
            LOG.warning("StrategyRuntime: no assigned strategy_ids; no plugins started")
            return

        missing = sorted([sid for sid in assigned_ids if self.registry.get(sid) is None])
        if missing:
            raise ConfigContractError(
                path="strategies_registry.assignments",
                why=f"Assigned strategy_ids missing allowlisted plugins: {missing}",
            )

        for strategy_id in sorted(assigned_ids):
            plugin = self.registry.get(strategy_id)
            if plugin is None:
                continue
            handler = plugin.create_handler(fsm=self.fsm, config=self.config)
            handler.register()
            LOG.info("StrategyRuntime: started strategy_id=%s (handler=%s)", strategy_id, handler.__class__.__name__)
