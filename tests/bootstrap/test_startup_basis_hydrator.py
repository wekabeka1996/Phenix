"""Tests for startup_basis_hydrator.hydrate_basis_bars() — STARTUP-BASIS-HYDRATION."""
import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import pytest

from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
)
from apps.reference.bootstrap.startup_basis_hydrator import (
    execute_startup_basis_hydration,
    hydrate_basis_bars,
)
from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    make_strategy_restore_snapshot,
    restored_restore_status,
)
from apps.reference.contracts.runtime_bar_identity import RuntimeBarSourceMode


@dataclass
class _FakeCandle:
    open_time_ms: int
    open: float = 40000.0
    high: float = 40500.0
    low: float = 39800.0
    close: float = 40200.0
    volume: float = 12.5


@dataclass
class _FakeBackfillResult:
    success: bool
    candles: List[_FakeCandle] = field(default_factory=list)
    error: str = ""


def _make_result(n: int, tf_sec: int = 300, success: bool = True) -> _FakeBackfillResult:
    base = 1_700_000_000_000
    tf_ms = tf_sec * 1000
    candles = [_FakeCandle(open_time_ms=base + i * tf_ms) for i in range(n)]
    return _FakeBackfillResult(success=success, candles=candles)


class _SeedSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def seed_startup_bars(self, symbol: str, count: int) -> None:
        self.calls.append((symbol, count))


class _AuroraWrapper:
    def __init__(self, handler) -> None:
        self.handler = handler


class _GuardianRuntime:
    def run(self, coro, timeout: float | None = None):
        return asyncio.run(coro)


class _BackfillAdapter:
    async def get_klines(self, symbol: str, interval: str, limit: int):
        tf_map = {"5m": 300_000, "15m": 900_000}
        tf_ms = tf_map[interval]
        base = 1_700_000_000_000
        return [
            [base + index * tf_ms, "1", "2", "0.5", "1.5", "10"]
            for index in range(limit)
        ]


class _SequentialSeedAssertAdapter:
    def __init__(self, seed_spy: "_SeedSpy") -> None:
        self.seed_spy = seed_spy
        self.calls: list[tuple[str, str, int]] = []

    async def get_klines(self, symbol: str, interval: str, limit: int):
        self.calls.append((symbol, interval, limit))
        if symbol == "ETHUSDT":
            assert self.seed_spy.calls == [
                ("BTCUSDT", 5)
            ], "BTCUSDT should be seeded before the second import starts"
        tf_map = {"5m": 300_000, "15m": 900_000}
        tf_ms = tf_map[interval]
        base = 1_700_000_000_000
        return [
            [base + index * tf_ms, "1", "2", "0.5", "1.5", "10"]
            for index in range(limit)
        ]


class TestHydrateBasisBars:
    def test_returns_count_of_injected_bars(self):
        """hydrate_basis_bars returns the number of bars successfully injected."""
        emit_spy = MagicMock()
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        result = _make_result(10)

        count = hydrate_basis_bars(agg, "BTCUSDT", 300, 10, result)

        assert count == 10
        assert emit_spy.call_count == 10

    def test_returns_zero_when_aggregator_none(self):
        """Returns 0 immediately when aggregator is None."""
        count = hydrate_basis_bars(None, "BTCUSDT", 300, 10, _make_result(10))
        assert count == 0

    def test_returns_zero_on_failed_fetch(self):
        """Returns 0 when fetch_result.success is False."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        agg = BarAggregator(timeframes_sec=[300], emit_fn=MagicMock())
        result = _make_result(10, success=False)

        count = hydrate_basis_bars(agg, "BTCUSDT", 300, 10, result)

        assert count == 0

    def test_constructs_correct_bar_timestamps(self):
        """Bar.end_ts_ms = candle.open_time_ms + tf_ms - 1 (close_boundary - 1)."""
        injected: list = []
        emit_spy = MagicMock()

        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)

        # Patch inject to capture bars
        original_inject = agg.inject_historical_bar
        captured = []

        def capturing_inject(bar):
            captured.append(bar)
            original_inject(bar)
        agg.inject_historical_bar = capturing_inject

        candle_ts = 1_700_000_000_000
        result = _FakeBackfillResult(
            success=True,
            candles=[_FakeCandle(open_time_ms=candle_ts)],
        )
        hydrate_basis_bars(agg, "BTCUSDT", 300, 1, result)

        assert len(captured) == 1
        bar = captured[0]
        assert bar.start_ts_ms == candle_ts
        assert bar.end_ts_ms == candle_ts + 300 * 1000 - 1
        assert bar.timeframe_sec == 300
        assert bar.symbol == "BTCUSDT"

    def test_respects_n_bars_limit(self):
        """Takes only the last n_bars from the result when result has more."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        result = _make_result(20)  # 20 available

        count = hydrate_basis_bars(
            agg, "BTCUSDT", 300, 10, result)  # want only 10

        assert count == 10
        assert emit_spy.call_count == 10

    def test_emitted_events_have_warmup_import_source_mode(self):
        """All emitted EVT:BAR_CLOSED events carry source_mode=warmup_import."""
        from apps.reference.domains.market_data.bar_aggregator import BarAggregator
        emit_spy = MagicMock()
        agg = BarAggregator(timeframes_sec=[300], emit_fn=emit_spy)
        result = _make_result(3)

        hydrate_basis_bars(agg, "BTCUSDT", 300, 3, result)

        for call in emit_spy.call_args_list:
            event_name, payload = call[0][0], call[0][1]
            assert event_name == "EVT:BAR_CLOSED"
            assert payload.get(
                "source_mode") == RuntimeBarSourceMode.WARMUP_IMPORT.value


def test_execute_startup_basis_hydration_seeds_from_replay_for_wrapper_and_direct_handler() -> None:
    from apps.reference.domains.market_data.bar_aggregator import BarAggregator

    aurora_seed = _SeedSpy()
    md_amr_seed = _SeedSpy()
    agg = BarAggregator(timeframes_sec=[300, 900], emit_fn=MagicMock())
    hydration_plan = SimpleNamespace(
        plans={
            "aurora:BTCUSDT": SimpleNamespace(
                strategy_id="aurora",
                symbol="BTCUSDT",
                requirement=SimpleNamespace(basis_tf_sec=300, basis_required_bars=5),
                actions=(
                    SimpleNamespace(action="RESTORE_OR_REPLAY_BASIS_BARS"),
                    SimpleNamespace(action="SEED_HANDLER_BASIS_COUNTER"),
                ),
            ),
            "md_amr:XRPUSDT": SimpleNamespace(
                strategy_id="md_amr",
                symbol="XRPUSDT",
                requirement=SimpleNamespace(basis_tf_sec=900, basis_required_bars=4),
                actions=(
                    SimpleNamespace(action="RESTORE_OR_REPLAY_BASIS_BARS"),
                    SimpleNamespace(action="SEED_HANDLER_BASIS_COUNTER"),
                ),
            ),
        }
    )

    summary = execute_startup_basis_hydration(
        hydration_plan=hydration_plan,
        restore_report=StartupAnalyticsRestoreReport(
            updated_at=1,
            source="tests",
            snapshots={},
        ),
        started_strategy_handlers={
            "aurora": _AuroraWrapper(aurora_seed),
            "md_amr": md_amr_seed,
        },
        bar_aggregator=agg,
        backfill_adapter=_BackfillAdapter(),
        guardian_runtime=_GuardianRuntime(),
    )

    assert aurora_seed.calls == [("BTCUSDT", 5)]
    assert md_amr_seed.calls == [("XRPUSDT", 4)]
    assert summary["imports"]["BTCUSDT:300"] == 5
    assert summary["imports"]["XRPUSDT:900"] == 4
    assert len(summary["seeded"]) == 2


def test_execute_startup_basis_hydration_seeds_from_restored_bars_without_replay() -> None:
    seed_spy = _SeedSpy()
    restored = restored_restore_status(
        why=["bars_restored"],
        updated_at=1,
        source="tests",
        evidence_ref="bars:test",
    )
    scopes = {
        scope.value: restored_restore_status(
            why=["restored"],
            updated_at=1,
            source="tests",
            evidence_ref=f"{scope.value}:test",
        )
        for scope in RuntimeAnalyticsRestoreScope
    }
    scopes[RuntimeAnalyticsRestoreScope.BARS.value] = restored

    report = StartupAnalyticsRestoreReport(
        updated_at=1,
        source="tests",
        snapshots={
            "aurora:BTCUSDT": make_strategy_restore_snapshot(
                strategy_id="aurora",
                symbol="BTCUSDT",
                updated_at=1,
                scopes=scopes,
                source="tests",
                has_open_position=False,
            ),
        },
    )
    hydration_plan = SimpleNamespace(
        plans={
            "aurora:BTCUSDT": SimpleNamespace(
                strategy_id="aurora",
                symbol="BTCUSDT",
                requirement=SimpleNamespace(basis_tf_sec=300, basis_required_bars=301),
                actions=(SimpleNamespace(action="SEED_HANDLER_BASIS_COUNTER"),),
            )
        }
    )

    summary = execute_startup_basis_hydration(
        hydration_plan=hydration_plan,
        restore_report=report,
        started_strategy_handlers={"aurora": _AuroraWrapper(seed_spy)},
        bar_aggregator=None,
        backfill_adapter=None,
        guardian_runtime=_GuardianRuntime(),
    )

    assert seed_spy.calls == [("BTCUSDT", 301)]
    assert summary["imports"] == {}
    assert summary["seeded"][0]["source"] == "restore_snapshot_bars"


def test_execute_startup_basis_hydration_seeds_each_symbol_before_next_import() -> None:
    from apps.reference.domains.market_data.bar_aggregator import BarAggregator

    aurora_seed = _SeedSpy()
    agg = BarAggregator(timeframes_sec=[300], emit_fn=MagicMock())
    hydration_plan = SimpleNamespace(
        plans={
            "aurora:BTCUSDT": SimpleNamespace(
                strategy_id="aurora",
                symbol="BTCUSDT",
                requirement=SimpleNamespace(basis_tf_sec=300, basis_required_bars=5),
                actions=(
                    SimpleNamespace(action="RESTORE_OR_REPLAY_BASIS_BARS"),
                    SimpleNamespace(action="SEED_HANDLER_BASIS_COUNTER"),
                ),
            ),
            "aurora:ETHUSDT": SimpleNamespace(
                strategy_id="aurora",
                symbol="ETHUSDT",
                requirement=SimpleNamespace(basis_tf_sec=300, basis_required_bars=5),
                actions=(
                    SimpleNamespace(action="RESTORE_OR_REPLAY_BASIS_BARS"),
                    SimpleNamespace(action="SEED_HANDLER_BASIS_COUNTER"),
                ),
            ),
        }
    )

    summary = execute_startup_basis_hydration(
        hydration_plan=hydration_plan,
        restore_report=StartupAnalyticsRestoreReport(
            updated_at=1,
            source="tests",
            snapshots={},
        ),
        started_strategy_handlers={"aurora": _AuroraWrapper(aurora_seed)},
        bar_aggregator=agg,
        backfill_adapter=_SequentialSeedAssertAdapter(aurora_seed),
        guardian_runtime=_GuardianRuntime(),
    )

    assert aurora_seed.calls == [("BTCUSDT", 5), ("ETHUSDT", 5)]
    assert summary["imports"]["BTCUSDT:300"] == 5
    assert summary["imports"]["ETHUSDT:300"] == 5
