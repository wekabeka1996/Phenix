from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from apps.reference.domains.agent_bridge.execution_readiness import (
    build_execution_readiness_snapshot,
)


NOW_MS = 1_800_000_000_000


def _by_name(snapshot):
    return {item.name: item for item in snapshot.invariants}


def test_missing_runtime_is_explicit_and_secret_values_are_not_needed() -> None:
    snapshot = build_execution_readiness_snapshot(
        runtime=None,
        symbols=["BTCUSDT"],
        produced_ts_ms=NOW_MS,
        trace_available=False,
    )

    invariants = _by_name(snapshot)
    assert snapshot.runtime_available is False
    assert invariants["exchange_filter_readiness"].status == "missing"
    assert invariants["lifecycle_reconciliation"].status == "missing"
    assert invariants["secret_isolation"].status == "ready"
    assert "does not read" in invariants["secret_isolation"].detail


def test_runtime_owned_snapshot_reduces_unknowns_without_execution_calls() -> None:
    filter_snapshot = SimpleNamespace(
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
    )

    class Runtime:
        shadow_mode = True
        is_live_execution = False
        adapter = object()
        exchange_filter_cache = SimpleNamespace(_filters={"BTCUSDT": filter_snapshot})
        _close_exec = object()
        _idempotent_cancel_helper = object()
        order_index = object()
        fsm = None
        _startup_truth_orchestrator = object()
        manage_flows = {}
        _bracket_ownership = object()
        _symbol_brackets = {}
        _symbol_bracket_truth_source = {}
        correlation_store = object()

        def submit_order(self, *_args, **_kwargs):  # pragma: no cover
            raise AssertionError("execution submit must not be called")

        def __getattribute__(self, name):
            if name in {"api_key", "api_secret", "secret", "credentials"}:
                raise AssertionError(f"secret-bearing attribute read: {name}")
            return object.__getattribute__(self, name)

    snapshot = build_execution_readiness_snapshot(
        runtime=Runtime(),
        symbols=["BTCUSDT"],
        produced_ts_ms=NOW_MS,
        trace_available=True,
    )

    invariants = _by_name(snapshot)
    assert snapshot.runtime_available is True
    assert invariants["testnet_only_or_mode"].status == "ready"
    assert invariants["exchange_filter_readiness"].status == "degraded"
    assert invariants["precision_minimum_constraints"].status == "degraded"
    assert invariants["reduce_only_close_protect"].status == "degraded"
    assert invariants["duplicate_idempotency_protection"].status == "ready"
    assert invariants["lifecycle_reconciliation"].status == "ready"
    assert invariants["bracket_ownership"].status == "ready"
    assert invariants["trace_correlation_identity"].status == "ready"
    assert all(item.evidence_source for item in snapshot.invariants)
    assert all(item.raw_ref for item in snapshot.invariants)
