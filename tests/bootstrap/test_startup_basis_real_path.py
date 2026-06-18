from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from apps.reference.bootstrap.runtime_analytics_restore import (
    build_startup_analytics_restore_report,
)
from apps.reference.bootstrap.startup_basis_hydrator import (
    execute_startup_basis_hydration,
)
from apps.reference.bootstrap.startup_hydration_planner import (
    build_startup_hydration_plan,
)
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.strategies.plugins.aurora_builtin import (
    AuroraBuiltinPlugin,
)
from apps.reference.domains.strategies.plugins.md_amr import MDAMRPlugin
from apps.reference.domains.strategies.plugins.mean_reversion import (
    MeanReversionPlugin,
)
from apps.reference.domains.strategies.plugins.alpha_mr_s01 import (
    AlphaMrS01Plugin,
)
from apps.reference.domains.strategies.plugins.alpha_ta_ensemble import (
    AlphaTaEnsemblePlugin,
)
from apps.reference.domains.strategies.registry import (
    StrategyPluginRegistry,
    StrategyRuntime,
)


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        pld = payload or {}
        self.emitted.append((event_name, pld))
        for handler in list(self.listeners.get(event_name, [])):
            handler(SimpleNamespace(pld=pld))


class _GuardianRuntime:
    def run(self, coro, timeout: float | None = None):
        return asyncio.run(coro)


class _TransientBackfillAdapter:
    def __init__(self) -> None:
        self.calls: dict[tuple[str, str], int] = defaultdict(int)

    async def get_klines(self, symbol: str, interval: str, limit: int):
        key = (symbol, interval)
        self.calls[key] += 1
        if self.calls[key] == 1:
            raise ConnectionError(
                f"startup transient failure for {symbol}/{interval}")
        tf_ms = {"5m": 300_000, "15m": 900_000}[interval]
        base = 1_700_000_000_000
        return [
            [base + index * tf_ms, "1", "2", "0.5", "1.5", "10"]
            for index in range(limit)
        ]


def _load_live_config():
    config = ConfigLoader(Path("config/aurora")).load_config()
    assignments = dict(config.strategies_registry.assignments)
    assignments.pop("1000PEPEUSDT", None)
    config.strategies_registry.assignments = assignments
    return config


def _build_started_handlers(config, bus: _Bus):
    plugins = StrategyPluginRegistry()
    plugins.register(AuroraBuiltinPlugin())
    plugins.register(MeanReversionPlugin())
    plugins.register(MDAMRPlugin())
    plugins.register(AlphaMrS01Plugin())
    plugins.register(AlphaTaEnsemblePlugin())
    return StrategyRuntime(fsm=bus, config=config, registry=plugins).start()


def test_live_config_hydration_plan_matches_runtime_contract() -> None:
    config = _load_live_config()
    report = build_startup_analytics_restore_report(
        config=config,
        snapshot_data={"timestamp_utc": "2026-03-15T09:09:15+00:00"},
        positions={},
        strategy_handlers={},
        snapshot_loaded=False,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_real_path",
    )
    plan = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_real_path",
    )

    assert plan.plans["aurora:BTCUSDT"].requirement.basis_required_bars == 301
    assert plan.plans["aurora:ETHUSDT"].requirement.basis_required_bars == 301
    assert "aurora:SOLUSDT" not in plan.plans
    assert plan.plans["aurora:BNBUSDT"].requirement.basis_required_bars == 301
    assert plan.plans["md_amr:XRPUSDT"].requirement.basis_required_bars == 96
    assert "aurora:DOGEUSDT" not in plan.plans
    assert "mean_reversion:DOGEUSDT" in plan.plans
    assert any(
        action.action == "SEED_HANDLER_BASIS_COUNTER"
        for action in plan.plans["aurora:BTCUSDT"].actions
    )
    assert any(
        action.action == "SEED_HANDLER_BASIS_COUNTER"
        for action in plan.plans["md_amr:XRPUSDT"].actions
    )


def test_real_runtime_path_recovers_from_transient_startup_import_failures() -> None:
    config = _load_live_config()
    bus = _Bus()
    started_handlers = _build_started_handlers(config, bus)
    assert set(started_handlers) == {
        "aurora",
        "mean_reversion",
        "md_amr",
        "alpha_mr_s01",
        "alpha_ta_ensemble",
    }
    report = build_startup_analytics_restore_report(
        config=config,
        snapshot_data={"timestamp_utc": "2026-03-15T09:09:15+00:00"},
        positions={},
        strategy_handlers=started_handlers,
        snapshot_loaded=False,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_real_path",
    )
    plan = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_real_path",
    )
    aggregator = BarAggregator(
        timeframes_sec=[180, 300, 900, 14400, 86400],
        emit_fn=bus.emit,
    )
    adapter = _TransientBackfillAdapter()

    summary = execute_startup_basis_hydration(
        hydration_plan=plan,
        restore_report=report,
        started_strategy_handlers=started_handlers,
        bar_aggregator=aggregator,
        backfill_adapter=adapter,
        guardian_runtime=_GuardianRuntime(),
    )

    aurora_handler = started_handlers["aurora"].handler
    md_amr_handler = started_handlers["md_amr"]

    assert aurora_handler._bars_seen_since_restart["BTCUSDT"] >= 301
    assert aurora_handler._bars_seen_since_restart["ETHUSDT"] >= 301
    assert aurora_handler._bars_seen_since_restart["SOLUSDT"] == 0
    assert aurora_handler._bars_seen_since_restart["BNBUSDT"] >= 301
    assert md_amr_handler._bars_seen_since_restart["XRPUSDT"] >= 96
    assert summary["imports"]["BTCUSDT:300"] >= 301
    assert summary["imports"]["BNBUSDT:300"] >= 301
    assert len(summary["seeded"]) >= 6
