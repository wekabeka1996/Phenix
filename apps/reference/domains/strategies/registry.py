from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, TYPE_CHECKING, runtime_checkable

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

    def items(self) -> list[tuple[str, StrategyPlugin]]:
        return sorted(self._plugins.items())


def _module_file(value: Any) -> str:
    if value is None:
        return ""
    module = getattr(value.__class__, "__module__", "")
    return f"{module.replace('.', '/')}.py" if module else ""


def _configured_strategy_ids(strategies_cfg: Any) -> set[str]:
    if strategies_cfg is None:
        return set()
    model_fields = getattr(strategies_cfg.__class__, "model_fields", None)
    if isinstance(model_fields, dict):
        return {
            str(strategy_id)
            for strategy_id in model_fields
            if getattr(strategies_cfg, strategy_id, None) is not None
        }
    return {
        str(strategy_id)
        for strategy_id, value in vars(strategies_cfg).items()
        if not strategy_id.startswith("_") and value is not None
    }


def build_strategy_registry_snapshot(
    *,
    config: AuroraConfig,
    registry: StrategyPluginRegistry,
    started_handlers: Dict[str, StrategyHandler],
    assigned_ids: set[str],
) -> dict[str, Any]:
    """Build non-financial startup telemetry for the configured strategy surface."""
    strategies_cfg = getattr(config, "strategies", None)
    strategies: list[dict[str, Any]] = []
    registered_plugins = dict(registry.items())
    discovered_ids = sorted(
        set(registered_plugins) | _configured_strategy_ids(strategies_cfg)
    )
    for strategy_id in discovered_ids:
        plugin = registered_plugins.get(strategy_id)
        strategy_cfg = getattr(strategies_cfg, strategy_id, None)
        configured_enabled = bool(getattr(strategy_cfg, "enabled", False))
        mode = str(getattr(strategy_cfg, "mode", "") or "").strip().lower()
        observed = strategy_id in started_handlers
        if strategy_cfg is None:
            status = "unknown"
        elif plugin is None:
            status = "historical_or_dead_code"
        elif not configured_enabled or mode == "disabled":
            status = "configured_disabled"
        elif mode == "shadow":
            status = "shadow_only"
        elif mode in {"observe", "observe_only"}:
            status = "observe_only"
        elif observed:
            status = "active_live"
        else:
            status = "configured_enabled"

        handler = started_handlers.get(strategy_id)
        notes = [f"assigned={strategy_id in assigned_ids}"]
        if mode:
            notes.append(f"mode={mode}")
        strategy_type = str(getattr(strategy_cfg, "type", "") or "").strip()
        if strategy_type:
            notes.append(f"type={strategy_type}")
        strategies.append({
            "strategy_id": strategy_id,
            "status": status,
            "plugin_file": _module_file(plugin),
            "runtime_handler": _module_file(handler) if handler is not None else "",
            "can_emit_order_intent": bool(
                plugin is not None and getattr(plugin, "can_emit_order_intent", True)
            ),
            "configured_enabled": configured_enabled,
            "observed_in_current_runtime": observed,
            "notes": "; ".join(notes),
        })

    now_ms = int(time.time() * 1000)
    return {
        "rid": f"strategy-registry-{now_ms}",
        "event_type": "STRATEGY_REGISTRY_SNAPSHOT",
        "symbol": "_SYSTEM_",
        "source_fsm": "OrderLoggerV1",
        "schema_version": "order_log_v1",
        "non_financial": True,
        "strategies": strategies,
        "metadata": {
            "financial_event": False,
            "snapshot_reason": "strategy_runtime_initialized",
        },
    }


@dataclass(frozen=True)
class StrategyRuntime:
    """Bootstraps strategy handlers for strategy_ids assigned in SSOT strategies.yaml."""

    fsm: "FSMCore"
    config: AuroraConfig
    registry: StrategyPluginRegistry
    telemetry_writer: Optional[Callable[[dict[str, Any]], None]] = None

    def _write_registry_snapshot(
        self,
        *,
        started_handlers: Dict[str, StrategyHandler],
        assigned_ids: set[str],
    ) -> None:
        if self.telemetry_writer is None:
            return
        try:
            self.telemetry_writer(build_strategy_registry_snapshot(
                config=self.config,
                registry=self.registry,
                started_handlers=started_handlers,
                assigned_ids=assigned_ids,
            ))
        except Exception:
            LOG.warning("StrategyRuntime: failed to write strategy registry snapshot", exc_info=True)

    def start(self) -> Dict[str, StrategyHandler]:
        sr = getattr(self.config, "strategies_registry", None)
        if sr is None:
            LOG.warning("StrategyRuntime: config.strategies_registry missing; no plugins started")
            self._write_registry_snapshot(started_handlers={}, assigned_ids=set())
            return {}

        assignments = getattr(sr, "assignments", None)
        if not isinstance(assignments, dict) or not assignments:
            LOG.warning("StrategyRuntime: strategies_registry.assignments missing/empty; no plugins started")
            self._write_registry_snapshot(started_handlers={}, assigned_ids=set())
            return {}

        assigned_ids: set[str] = set()
        for _, ids in assignments.items():
            if not isinstance(ids, list):
                continue
            for strategy_id in ids:
                if isinstance(strategy_id, str) and strategy_id:
                    assigned_ids.add(strategy_id)

        if not assigned_ids:
            LOG.warning("StrategyRuntime: no assigned strategy_ids; no plugins started")
            self._write_registry_snapshot(started_handlers={}, assigned_ids=set())
            return {}

        missing = sorted([sid for sid in assigned_ids if self.registry.get(sid) is None])
        if missing:
            raise ConfigContractError(
                path="strategies_registry.assignments",
                why=f"Assigned strategy_ids missing allowlisted plugins: {missing}",
            )

        started_handlers: Dict[str, StrategyHandler] = {}
        for strategy_id in sorted(assigned_ids):
            plugin = self.registry.get(strategy_id)
            if plugin is None:
                continue
            handler = plugin.create_handler(fsm=self.fsm, config=self.config)
            handler.register()
            started_handlers[strategy_id] = handler
            LOG.info("StrategyRuntime: started strategy_id=%s (handler=%s)", strategy_id, handler.__class__.__name__)
        self._write_registry_snapshot(
            started_handlers=started_handlers,
            assigned_ids=assigned_ids,
        )
        return started_handlers
