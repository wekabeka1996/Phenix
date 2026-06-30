from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from apps.reference.domains.agent_bridge.capabilities import (
    build_execution_capability_descriptors,
    project_execution_readiness_snapshot,
)
from apps.reference.domains.agent_bridge.execution_readiness import (
    build_execution_readiness_snapshot,
)
from apps.reference.domains.agent_bridge.publication import AgentBridgeRuntimePublisher
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer
from apps.reference.domains.execution_position.exchange_filter_cache import (
    ExchangeFilterSnapshot,
)


NOW_MS = 1_800_000_000_000


class _CloseOwner:
    async def _submit_close_order(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("close path must not execute")


class _ProtectOwner:
    async def place_brackets_parallel(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("protect path must not execute")


def _instrument(symbol: str):
    return SimpleNamespace(
        symbol=symbol,
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
    )


def _runtime(*, filters=None):
    class AdapterSecretTrap:
        def __getattribute__(self, name):  # pragma: no cover - must stay unread
            raise AssertionError(f"adapter or secret-bearing state read: {name}")

    return SimpleNamespace(
        config=SimpleNamespace(
            instruments={
                "BTCUSDT": _instrument("BTCUSDT"),
                "ETHUSDT": _instrument("ETHUSDT"),
            }
        ),
        no_order_observation_mode=True,
        shadow_mode=True,
        is_live_execution=False,
        adapter=None,
        no_order_blocked_action_count=0,
        exchange_filter_cache=(
            SimpleNamespace(_filters=filters) if filters is not None else None
        ),
        _close_exec=_CloseOwner(),
        _bracket_mgr=_ProtectOwner(),
        _idempotent_cancel_helper=object(),
        order_index=object(),
        _startup_truth_orchestrator=object(),
        manage_flows={},
        _bracket_ownership=object(),
        _symbol_brackets={},
        _symbol_bracket_truth_source={},
        correlation_store=object(),
        unused_secret_trap=AdapterSecretTrap(),
    )


def _by_key(descriptors):
    return {(item.name, item.symbol): item for item in descriptors}


def test_config_only_filters_are_degraded_but_runtime_normalizers_are_ready() -> None:
    descriptors, summaries, readiness = build_execution_capability_descriptors(
        runtime=_runtime(),
        symbols=["BTCUSDT", "ETHUSDT"],
        produced_ts_ms=NOW_MS,
    )
    indexed = _by_key(descriptors)

    for symbol in ("BTCUSDT", "ETHUSDT"):
        filter_descriptor = indexed[("exchange_filter_constraints", symbol)]
        assert filter_descriptor.status == "degraded"
        assert filter_descriptor.evidence_level == "configured_only"
        assert filter_descriptor.constraints["min_notional"] == "5"

        precision = indexed[("precision_minimum_normalization", symbol)]
        assert precision.status == "ready"
        assert precision.evidence_level == "runtime_owner"
        assert precision.constraints["unknown_symbol_fails_closed"] is True

    assert len(summaries) == 2
    assert readiness.ready == 5
    assert readiness.degraded == 2
    assert readiness.missing == 0


def test_fresh_exchange_filter_is_exchange_confirmed_ready() -> None:
    snapshot = ExchangeFilterSnapshot(
        symbol="BTCUSDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
        source="live",
        updated_at_monotonic=1.0,
        updated_at_ms=NOW_MS - 1_000,
    )
    descriptors, summaries, _ = build_execution_capability_descriptors(
        runtime=_runtime(filters={"BTCUSDT": snapshot}),
        symbols=["BTCUSDT"],
        produced_ts_ms=NOW_MS,
    )
    descriptor = _by_key(descriptors)[("exchange_filter_constraints", "BTCUSDT")]

    assert descriptor.status == "ready"
    assert descriptor.evidence_level == "exchange_confirmed"
    assert summaries[0].freshness == "fresh"


def test_stale_filter_and_unknown_symbol_never_become_ready() -> None:
    stale = ExchangeFilterSnapshot(
        symbol="BTCUSDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
        source="live",
        updated_at_monotonic=1.0,
        updated_at_ms=NOW_MS - (16 * 60 * 1_000),
    )
    descriptors, _, _ = build_execution_capability_descriptors(
        runtime=_runtime(filters={"BTCUSDT": stale}),
        symbols=["BTCUSDT", "UNKNOWNUSDT"],
        produced_ts_ms=NOW_MS,
    )
    indexed = _by_key(descriptors)

    assert indexed[("exchange_filter_constraints", "BTCUSDT")].status == "degraded"
    assert indexed[("exchange_filter_constraints", "UNKNOWNUSDT")].status == "missing"
    assert indexed[("precision_minimum_normalization", "UNKNOWNUSDT")].status == "missing"
    assert indexed[("precision_minimum_normalization", "UNKNOWNUSDT")].constraints[
        "unknown_symbol_fails_closed"
    ] is True


def test_reduce_only_descriptors_are_runtime_owned_without_calling_paths() -> None:
    snapshot = build_execution_readiness_snapshot(
        runtime=_runtime(),
        symbols=["BTCUSDT", "ETHUSDT"],
        produced_ts_ms=NOW_MS,
        trace_available=True,
    )
    indexed = _by_key(snapshot.capability_descriptors)
    invariants = {item.name: item for item in snapshot.invariants}

    for name in (
        "reduce_only_order_parameter",
        "close_path_reduce_only_enforcement",
        "protect_path_reduce_only_enforcement",
    ):
        assert indexed[(name, None)].status == "ready"
        assert indexed[(name, None)].evidence_level == "runtime_owner"
        assert indexed[(name, None)].constraints["exchange_acceptance_confirmed"] is False
    assert invariants["exchange_filter_readiness"].status == "degraded"
    assert invariants["precision_minimum_constraints"].status == "ready"
    assert invariants["reduce_only_close_protect"].status == "ready"


def test_full_runtime_snapshot_projects_to_requested_symbols() -> None:
    snapshot = build_execution_readiness_snapshot(
        runtime=_runtime(),
        symbols=["BTCUSDT", "ETHUSDT"],
        produced_ts_ms=NOW_MS,
        trace_available=True,
    )
    projected = project_execution_readiness_snapshot(snapshot, ["BTCUSDT"])

    assert projected.symbols == ["BTCUSDT"]
    assert {item.symbol for item in projected.constraint_summary} == {"BTCUSDT"}
    assert {
        item.symbol for item in projected.capability_descriptors if item.symbol is not None
    } == {"BTCUSDT"}
    assert len(projected.capability_descriptors) == 5
    assert projected.readiness_summary.ready == 4
    assert projected.readiness_summary.degraded == 1


def test_descriptor_packet_stays_bounded_without_snapshot_duplication(tmp_path: Path) -> None:
    publication_dir = tmp_path / "ops" / "agent_bridge" / "runtime"
    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=_runtime(),
        output_dir=publication_dir,
        symbols=["BTCUSDT", "ETHUSDT"],
        publisher_version="p5.v0",
    )
    for symbol, price in (("BTCUSDT", 60_000.0), ("ETHUSDT", 1_600.0)):
        publisher.ingest_mirror_record(
            {
                "ts_ms": NOW_MS - 1_000,
                "symbol": symbol,
                "tf_sec": 300,
                "bar_close_ts": NOW_MS - 1_000,
                "price": price,
                "features": {
                    "delta_price": "1",
                    "ema_bias": "0.5",
                    "obi": "0.1",
                    "volatility_state": "0.2",
                    "macro_sync": "0.8",
                },
                "regime": "UNCERTAIN",
                "regime_confidence": 0.5,
            }
        )
    publisher.publish_initial(now_ms=NOW_MS)

    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW_MS).build_packet(
        symbols=["BTCUSDT", "ETHUSDT"]
    )

    assert packet.execution_body.readiness_snapshot is None
    assert len(packet.execution_body.capability_descriptors) == 7
    assert packet.budget.estimated_tokens <= 4_400
    assert packet.budget.truncated is False


def test_descriptor_builder_has_no_secret_or_adapter_action_surface() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "reference"
        / "domains"
        / "agent_bridge"
        / "capabilities.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in (
        "api_key",
        "api_secret",
        "credentials",
        ".create_order(",
        ".place_order(",
        ".cancel_order(",
        ".modify_order(",
        ".amend_order(",
    ):
        assert forbidden not in source
