from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from apps.reference.config_contract import ConfigContractError
from apps.reference.domains.strategies.registry import StrategyPluginRegistry, StrategyRuntime


class _FSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)


@dataclass(frozen=True)
class _Handler:
    fsm: _FSM
    registered: list[str]
    strategy_id: str

    def register(self) -> None:
        self.registered.append(self.strategy_id)
        self.fsm.listen(f"EVT:HANDLER_REGISTERED:{self.strategy_id}", object())


@dataclass(frozen=True)
class _Plugin:
    strategy_id: str
    registered: list[str]

    def create_handler(self, *, fsm: _FSM, config: object) -> _Handler:
        return _Handler(fsm=fsm, registered=self.registered, strategy_id=self.strategy_id)


def test_task32_registry_starts_assigned_plugins() -> None:
    fsm = _FSM()
    registry = StrategyPluginRegistry()
    registered: list[str] = []

    registry.register(_Plugin(strategy_id="s1", registered=registered))
    registry.register(_Plugin(strategy_id="s2", registered=registered))

    strategies_registry = SimpleNamespace(assignments={"BTCUSDT": ["s1", "s2"]})
    cfg = SimpleNamespace(strategies_registry=strategies_registry)

    StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    assert registered == ["s1", "s2"]


def test_task32_registry_fails_closed_on_missing_plugin() -> None:
    fsm = _FSM()
    registry = StrategyPluginRegistry()
    registry.register(_Plugin(strategy_id="s1", registered=[]))

    strategies_registry = SimpleNamespace(assignments={"BTCUSDT": ["s1", "missing"]})
    cfg = SimpleNamespace(strategies_registry=strategies_registry)

    with pytest.raises(ConfigContractError) as exc:
        StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    assert "missing allowlisted plugins" in exc.value.why


class _TypedFinancialProfile(BaseModel):
    enabled: bool = True
    mode: str = "runtime"
    execution: object | None = None
    decision: object | None = None
    objective: object | None = None
    allowed_sides: list[str] = ["BUY", "SELL"]


def test_runtime_fails_before_handlers_for_incomplete_active_financial_contract() -> None:
    fsm = _FSM()
    registry = StrategyPluginRegistry()
    registered: list[str] = []
    registry.register(_Plugin(strategy_id="s1", registered=registered))
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={"BTCUSDT": ["s1"]}),
        strategies=SimpleNamespace(s1=_TypedFinancialProfile()),
    )

    with pytest.raises(ConfigContractError) as exc:
        StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    assert "DECISION_KELLY_MISSING" in exc.value.why
    assert "EXECUTION_POLICY_MISSING" in exc.value.why
    assert registered == []


def test_shadow_profile_can_start_without_financial_contract() -> None:
    fsm = _FSM()
    registry = StrategyPluginRegistry()
    registered: list[str] = []
    registry.register(_Plugin(strategy_id="s1", registered=registered))
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={"BTCUSDT": ["s1"]}),
        strategies=SimpleNamespace(s1=_TypedFinancialProfile(mode="shadow")),
    )

    StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    assert registered == ["s1"]


def test_runtime_fails_when_active_financial_profile_has_no_assignment() -> None:
    fsm = _FSM()
    registry = StrategyPluginRegistry()
    registered: list[str] = []
    registry.register(_Plugin(strategy_id="s1", registered=registered))
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={"BTCUSDT": []}),
        strategies=SimpleNamespace(s1=_TypedFinancialProfile()),
    )

    with pytest.raises(ConfigContractError) as exc:
        StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    assert "not assigned" in exc.value.why
    assert registered == []
