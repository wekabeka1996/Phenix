"""Tests for vfoundation.core.idempotency.store — enums, DTOs, metrics, abstract store."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import pytest

from vfoundation.core.idempotency.store import (
    ConfirmResult,
    ConfirmStatus,
    DistributedIdempotencyStore,
    GetStatus,
    IdempotencyMetrics,
    ReleaseResult,
    ReleaseStatus,
    ReserveResult,
    ReserveStatus,
    StatusResult,
    _LatencyMeasurer,
)


# ── Enums ─────────────────────────────────────────────────────────────────


class TestEnums:
    def test_reserve_status_values(self) -> None:
        assert ReserveStatus.NEW.value == "NEW"
        assert ReserveStatus.DUPLICATE_SAME.value == "DUPLICATE_SAME"
        assert ReserveStatus.DUPLICATE_CONFLICT.value == "DUPLICATE_CONFLICT"
        assert ReserveStatus.EXTERN_OWNER.value == "EXTERN_OWNER"
        assert ReserveStatus.ERROR.value == "ERROR"

    def test_confirm_status_values(self) -> None:
        assert ConfirmStatus.CONFIRMED.value == "CONFIRMED"
        assert ConfirmStatus.MISSING.value == "MISSING"
        assert ConfirmStatus.ERROR.value == "ERROR"

    def test_get_status_values(self) -> None:
        assert GetStatus.EMPTY.value == "EMPTY"
        assert GetStatus.HELD.value == "HELD"
        assert GetStatus.CONFIRMED.value == "CONFIRMED"

    def test_release_status_values(self) -> None:
        assert ReleaseStatus.RELEASED.value == "RELEASED"
        assert ReleaseStatus.MISSING.value == "MISSING"
        assert ReleaseStatus.ERROR.value == "ERROR"


# ── DTOs ──────────────────────────────────────────────────────────────────


class TestDTOs:
    def test_reserve_result_defaults(self) -> None:
        r = ReserveResult(status=ReserveStatus.NEW)
        assert r.lease_ms is None
        assert r.owner is None
        assert r.error is None

    def test_reserve_result_with_lease(self) -> None:
        r = ReserveResult(status=ReserveStatus.NEW, lease_ms=60000)
        assert r.lease_ms == 60000

    def test_confirm_result_defaults(self) -> None:
        r = ConfirmResult(status=ConfirmStatus.CONFIRMED)
        assert r.error is None

    def test_status_result_full(self) -> None:
        r = StatusResult(
            status=GetStatus.CONFIRMED,
            owner="w1",
            payload_digest="abc",
            ts_ns=123456,
            meta={"key": "val"},
        )
        assert r.owner == "w1"
        assert r.meta == {"key": "val"}

    def test_release_result_with_error(self) -> None:
        r = ReleaseResult(status=ReleaseStatus.ERROR, error="timeout")
        assert r.error == "timeout"


# ── IdempotencyMetrics ────────────────────────────────────────────────────


class TestIdempotencyMetrics:
    def test_initial_counters_empty(self) -> None:
        m = IdempotencyMetrics()
        assert m.idemp_reserve_total == {}
        assert m.idemp_conflict_total == 0
        assert m.reserve_latencies == []

    def test_record_reserve_latency(self) -> None:
        m = IdempotencyMetrics()
        m.record_reserve_latency(1.5)
        m.record_reserve_latency(2.5)
        assert len(m.reserve_latencies) == 2

    def test_record_confirm_latency(self) -> None:
        m = IdempotencyMetrics()
        m.record_confirm_latency(3.0)
        assert len(m.confirm_latencies) == 1

    def test_p95_reserve_latency(self) -> None:
        m = IdempotencyMetrics()
        for i in range(100):
            m.record_reserve_latency(float(i))
        p95 = m.get_p95_reserve_latency()
        assert p95 is not None
        assert 90 <= p95 <= 99

    def test_p95_confirm_latency(self) -> None:
        m = IdempotencyMetrics()
        for i in range(100):
            m.record_confirm_latency(float(i))
        p95 = m.get_p95_confirm_latency()
        assert p95 is not None
        assert 90 <= p95 <= 99

    def test_p95_empty_returns_none(self) -> None:
        m = IdempotencyMetrics()
        assert m.get_p95_reserve_latency() is None
        assert m.get_p95_confirm_latency() is None

    def test_latency_cap_at_1000(self) -> None:
        m = IdempotencyMetrics()
        for i in range(1050):
            m.record_reserve_latency(float(i))
        assert len(m.reserve_latencies) == 1000


# ── Abstract store contract ───────────────────────────────────────────────


class _FakeStore(DistributedIdempotencyStore):
    """Minimal concrete implementation for testing the ABC."""

    def reserve(self, key: str, payload_digest: str, ttl_ms: int, owner: str) -> ReserveResult:
        return ReserveResult(status=ReserveStatus.NEW, lease_ms=ttl_ms)

    def confirm(
        self, key: str, final_status: str, meta: Optional[Dict[str, Any]] = None
    ) -> ConfirmResult:
        return ConfirmResult(status=ConfirmStatus.CONFIRMED)

    def get_status(self, key: str) -> StatusResult:
        return StatusResult(status=GetStatus.EMPTY)

    def release(self, key: str, owner: str) -> ReleaseResult:
        return ReleaseResult(status=ReleaseStatus.RELEASED)


class TestAbstractStore:
    def test_concrete_instantiation(self) -> None:
        store = _FakeStore()
        assert store.metrics is not None

    def test_reserve_returns_result(self) -> None:
        store = _FakeStore()
        r = store.reserve("k1", "digest", 60000, "w1")
        assert r.status == ReserveStatus.NEW

    def test_confirm_returns_result(self) -> None:
        store = _FakeStore()
        r = store.confirm("k1", "ORDER_PLACED")
        assert r.status == ConfirmStatus.CONFIRMED

    def test_get_status_returns_result(self) -> None:
        store = _FakeStore()
        r = store.get_status("k1")
        assert r.status == GetStatus.EMPTY

    def test_release_returns_result(self) -> None:
        store = _FakeStore()
        r = store.release("k1", "w1")
        assert r.status == ReleaseStatus.RELEASED


# ── _LatencyMeasurer ──────────────────────────────────────────────────────


class TestLatencyMeasurer:
    def test_reserve_latency_recorded(self) -> None:
        store = _FakeStore()
        with store._measure_latency("reserve"):
            pass  # instant
        assert len(store.metrics.reserve_latencies) == 1

    def test_confirm_latency_recorded(self) -> None:
        store = _FakeStore()
        with store._measure_latency("confirm"):
            pass
        assert len(store.metrics.confirm_latencies) == 1

    def test_unknown_operation_no_crash(self) -> None:
        store = _FakeStore()
        with store._measure_latency("unknown"):
            pass
        # Should not raise, just not recorded
        assert len(store.metrics.reserve_latencies) == 0
        assert len(store.metrics.confirm_latencies) == 0
