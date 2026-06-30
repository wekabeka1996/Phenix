"""Tests for empty-fetch recovery in execute_startup_basis_hydration.

Reproduces the live failure pattern: Binance returns success=True but candles=[]
(or success=False with error="empty_response") and verifies that the top-level
retry loop re-attempts the fetch and eventually seeds the handler correctly.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
from apps.reference.domains.strategies.plugins.alpha_mr_s01 import (
    AlphaMrS01Plugin,
)
from apps.reference.domains.strategies.plugins.alpha_ta_ensemble import (
    AlphaTaEnsemblePlugin,
)
from apps.reference.domains.strategies.plugins.md_amr import MDAMRPlugin
from apps.reference.domains.strategies.plugins.mean_reversion import (
    MeanReversionPlugin,
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


class _EmptyThenSuccessBackfillAdapter:
    """Simulates the live failure: first N calls return success but empty candles.

    fetch_candles() has an internal 3-attempt retry.  To trigger the OUTER
    retry in execute_startup_basis_hydration(), the adapter must return empty
    for at least 3 consecutive calls (exhausting the inner retry), then
    succeed on the next call (triggered by the outer retry).

    fail_count = total empty responses per (symbol, interval) key.
    With fail_count=3 the inner retry is exhausted → fetch_candles returns
    success=False → hydrate_basis_bars returns 0 → outer retry fires.
    """

    def __init__(self, *, fail_count: int = 3) -> None:
        self.calls: dict[tuple[str, str], int] = defaultdict(int)
        self._fail_count = fail_count

    async def get_klines(self, symbol: str, interval: str, limit: int):
        key = (symbol, interval)
        self.calls[key] += 1
        if self.calls[key] <= self._fail_count:
            # Return empty — simulates Binance maintenance/rate limit
            return []
        tf_ms = {"5m": 300_000, "15m": 900_000}[interval]
        base = 1_700_000_000_000
        return [
            [base + index * tf_ms, "1", "2", "0.5", "1.5", "10"]
            for index in range(limit)
        ]


class _PermanentlyEmptyBackfillAdapter:
    """Simulates permanent Binance failure: always returns empty candles."""

    async def get_klines(self, symbol: str, interval: str, limit: int):
        return []


def _load_live_config():
    config = ConfigLoader(Path("config/aurora")).load_config()
    assignments = dict(config.strategies_registry.assignments)
    assignments.pop("1000PEPEUSDT", None)
    config.strategies_registry.assignments = assignments
    return config


def _build_started_handlers(config, bus: _Bus):
    plugins = StrategyPluginRegistry()
    plugins.register(AuroraBuiltinPlugin())
    plugins.register(AlphaMrS01Plugin())
    plugins.register(AlphaTaEnsemblePlugin())
    plugins.register(MeanReversionPlugin())
    plugins.register(MDAMRPlugin())
    return StrategyRuntime(fsm=bus, config=config, registry=plugins).start()


def _build_plan_and_report(config, bus: _Bus):
    started_handlers = _build_started_handlers(config, bus)
    report = build_startup_analytics_restore_report(
        config=config,
        snapshot_data={"timestamp_utc": "2026-03-15T09:09:15+00:00"},
        positions={},
        strategy_handlers=started_handlers,
        snapshot_loaded=False,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_empty_fetch",
    )
    plan = build_startup_hydration_plan(
        config=config,
        analytics_restore_report=report,
        updated_at=1_773_565_755_000,
        source="tests:startup_basis_empty_fetch",
    )
    return started_handlers, report, plan


@patch("apps.reference.bootstrap.startup_basis_hydrator.time.sleep")
def test_empty_fetch_retries_and_recovers(mock_sleep) -> None:
    """Inner fetch_candles retry exhausted (3 empties) → outer retry fires → 4th call succeeds."""
    config = _load_live_config()
    bus = _Bus()
    started_handlers, report, plan = _build_plan_and_report(config, bus)
    aggregator = BarAggregator(
        timeframes_sec=[180, 300, 900, 14400, 86400],
        emit_fn=bus.emit,
    )
    # fail_count=3: inner retry (3 attempts) is exhausted, then outer retry kicks in
    adapter = _EmptyThenSuccessBackfillAdapter(fail_count=3)

    summary = execute_startup_basis_hydration(
        hydration_plan=plan,
        restore_report=report,
        started_strategy_handlers=started_handlers,
        bar_aggregator=aggregator,
        backfill_adapter=adapter,
        guardian_runtime=_GuardianRuntime(),
    )

    # md_amr handler must be seeded after outer retry recovery
    md_amr_handler = started_handlers["md_amr"]
    assert md_amr_handler._bars_seen_since_restart["XRPUSDT"] >= 96

    # Aurora should also be seeded
    aurora_handler = started_handlers["aurora"].handler
    assert aurora_handler._bars_seen_since_restart["BTCUSDT"] >= 301
    assert aurora_handler._bars_seen_since_restart["BNBUSDT"] >= 301

    # Outer retry loop fired → sleep was called at least once
    assert mock_sleep.call_count > 0, "Expected outer retry delays after inner retry exhaustion"

    # No "exhausted" entries in skipped (recovery succeeded on outer retry)
    assert not any("exhausted" in s for s in summary.get("skipped", []))

    # Seeded records must exist
    assert len(summary["seeded"]) >= 6


@patch("apps.reference.bootstrap.startup_basis_hydrator.time.sleep")
def test_permanent_empty_fetch_produces_exhausted_status(mock_sleep) -> None:
    """When ALL fetches return empty, seeded_bars=0 and EXHAUSTED is reported."""
    config = _load_live_config()
    bus = _Bus()
    started_handlers, report, plan = _build_plan_and_report(config, bus)
    aggregator = BarAggregator(
        timeframes_sec=[180, 300, 900, 14400, 86400],
        emit_fn=bus.emit,
    )
    adapter = _PermanentlyEmptyBackfillAdapter()

    summary = execute_startup_basis_hydration(
        hydration_plan=plan,
        restore_report=report,
        started_strategy_handlers=started_handlers,
        bar_aggregator=aggregator,
        backfill_adapter=adapter,
        guardian_runtime=_GuardianRuntime(),
    )

    # Handler should NOT be seeded (0 bars imported)
    md_amr_handler = started_handlers["md_amr"]
    assert md_amr_handler._bars_seen_since_restart.get("XRPUSDT", 0) == 0

    # "exhausted" entries must exist in skipped
    exhausted = [s for s in summary.get("skipped", []) if "exhausted" in s]
    assert len(exhausted) > 0, "Expected EXHAUSTED entries in skipped"

    # Seeded records should be empty or partial
    # (only strategies with restore_snapshot_bars fallback could be seeded)


@patch("apps.reference.bootstrap.startup_basis_hydrator.time.sleep")
def test_retry_recovery_on_first_attempt_does_not_sleep(mock_sleep) -> None:
    """When first fetch succeeds, no retry delays should occur for that symbol."""
    config = _load_live_config()
    bus = _Bus()
    started_handlers, report, plan = _build_plan_and_report(config, bus)
    aggregator = BarAggregator(
        timeframes_sec=[180, 300, 900, 14400, 86400],
        emit_fn=bus.emit,
    )
    # Adapter that succeeds on first call
    adapter = _EmptyThenSuccessBackfillAdapter(fail_count=0)

    summary = execute_startup_basis_hydration(
        hydration_plan=plan,
        restore_report=report,
        started_strategy_handlers=started_handlers,
        bar_aggregator=aggregator,
        backfill_adapter=adapter,
        guardian_runtime=_GuardianRuntime(),
    )

    # No retries needed — no sleep calls
    assert mock_sleep.call_count == 0, "No retries should occur on first success"

    # All handlers should be seeded
    md_amr_handler = started_handlers["md_amr"]
    assert md_amr_handler._bars_seen_since_restart["XRPUSDT"] >= 96
    assert len(summary["seeded"]) >= 6
