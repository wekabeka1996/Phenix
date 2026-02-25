"""Tests for vfoundation.core.adapters.execution_adapter — CB, metrics, mock adapter."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from vfoundation.core.adapters.execution_adapter import (
    AdapterMetrics,
    CircuitBreaker,
    CircuitBreakerState,
    ExecutionMode,
    OrderDTO,
)
from vfoundation.core.adapters.execution_exceptions import (
    CBOpenError,
    IdempotentDuplicateError,
)
# Phase 9.3: MockExecutionAdapter moved to test fixtures
from tests.vfoundation.fixtures.mock_execution_adapter import MockExecutionAdapter


# ── OrderDTO ──────────────────────────────────────────────────────────────


class TestOrderDTO:
    def test_minimal(self) -> None:
        o = OrderDTO(symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.1"))
        assert o.symbol == "BTCUSDT"
        assert o.reduce_only is False
        assert o.time_in_force == "GTC"

    def test_limit_order(self) -> None:
        o = OrderDTO(
            symbol="BTCUSDT", side="sell", order_type="limit",
            qty=Decimal("1"), price=Decimal("50000"),
        )
        assert o.price == Decimal("50000")

    def test_with_idempotent_key(self) -> None:
        o = OrderDTO(
            symbol="ETHUSDT", side="buy", order_type="market",
            qty=Decimal("5"), idempotent_key="ik-1",
        )
        assert o.idempotent_key == "ik-1"


# ── AdapterMetrics ────────────────────────────────────────────────────────


class TestAdapterMetrics:
    def test_initial_counters(self) -> None:
        m = AdapterMetrics()
        assert m.sdk_submit_total == 0
        assert m.sdk_cancel_total == 0

    def test_record_submit_latency(self) -> None:
        m = AdapterMetrics()
        m.record_submit_latency(5.0)
        m.record_submit_latency(10.0)
        assert len(m.sdk_submit_latencies) == 2

    def test_latency_cap_at_1000(self) -> None:
        m = AdapterMetrics()
        for i in range(1050):
            m.record_submit_latency(float(i))
        assert len(m.sdk_submit_latencies) == 1000

    def test_p95_submit(self) -> None:
        m = AdapterMetrics()
        for i in range(100):
            m.record_submit_latency(float(i))
        p95 = m.get_p95_submit_latency()
        assert p95 is not None
        assert 90 <= p95 <= 99

    def test_p95_cancel(self) -> None:
        m = AdapterMetrics()
        for i in range(100):
            m.record_cancel_latency(float(i))
        p95 = m.get_p95_cancel_latency()
        assert p95 is not None

    def test_p95_empty_none(self) -> None:
        m = AdapterMetrics()
        assert m.get_p95_submit_latency() is None
        assert m.get_p95_cancel_latency() is None


# ── CircuitBreaker ────────────────────────────────────────────────────────


class TestCircuitBreaker:
    def _make_cb(self, **kw: Any) -> CircuitBreaker:
        defaults: Dict[str, Any] = dict(
            open_threshold=0.5, cooldown_ms=1000,
            half_open_probes=2, window_size=10,
        )
        defaults.update(kw)
        return CircuitBreaker(**defaults)

    def test_starts_closed(self) -> None:
        cb = self._make_cb()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.is_open() is False

    def test_success_keeps_closed(self) -> None:
        cb = self._make_cb()
        for _ in range(10):
            cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_opens_on_threshold(self) -> None:
        cb = self._make_cb(open_threshold=0.5, window_size=4)
        cb.record_success()
        cb.record_error()
        # 1 err / 2 total = 0.5 → opens
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open() is True

    def test_error_rate_below_threshold_stays_closed(self) -> None:
        cb = self._make_cb(open_threshold=0.5, window_size=10)
        cb.record_success()
        cb.record_success()
        cb.record_success()
        cb.record_error()
        # error_rate = 1/4 = 0.25 < 0.5
        assert cb.state == CircuitBreakerState.CLOSED

    def test_open_to_half_open_after_cooldown(self) -> None:
        cb = self._make_cb(cooldown_ms=1)
        # Force open
        cb.state = CircuitBreakerState.OPEN
        cb.open_at_ms = time.time() * 1000 - 100
        # Cooldown expired → half_open
        assert cb.is_open() is False
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        cb = self._make_cb(half_open_probes=2)
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.half_open_successes = 0
        cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_error_reopens(self) -> None:
        cb = self._make_cb()
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.record_error()
        assert cb.state == CircuitBreakerState.OPEN

    def test_half_open_allows_probes(self) -> None:
        cb = self._make_cb()
        cb.state = CircuitBreakerState.HALF_OPEN
        assert cb.is_open() is False  # probes allowed

    def test_error_rate_calculation(self) -> None:
        cb = self._make_cb()
        assert cb._calculate_error_rate() == 0.0
        cb.record_success()
        cb.record_success()
        assert cb._calculate_error_rate() == 0.0
        cb.errors.append(True)
        assert cb._calculate_error_rate() == pytest.approx(1 / 3)


# ── MockExecutionAdapter ─────────────────────────────────────────────────


class TestMockExecutionAdapter:
    """Tests for MockExecutionAdapter (test fixture implementation)."""

    @pytest.fixture()
    def adapter(self) -> MockExecutionAdapter:
        return MockExecutionAdapter(mode=ExecutionMode.DRY_RUN)

    def test_no_deprecation_warning(self) -> None:
        """Fixture MockExecutionAdapter must NOT raise DeprecationWarning."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            MockExecutionAdapter(mode=ExecutionMode.DRY_RUN)  # should not raise

    def test_submit_dry_run(self, adapter: MockExecutionAdapter) -> None:
        order = OrderDTO(
            symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.01"),
        )
        event = adapter.submit(order)
        assert event["event_type"] == "ORDER_PLACED"
        assert event["status"] == "SIMULATED"
        assert event["exchange_order_id"] is None

    def test_submit_paper_mode(self) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            adapter = MockExecutionAdapter(mode=ExecutionMode.PAPER)
        order = OrderDTO(
            symbol="ETHUSDT", side="sell", order_type="limit",
            qty=Decimal("1"), price=Decimal("3000"),
        )
        event = adapter.submit(order)
        assert event["event_type"] == "ORDER_PLACED"
        assert event["exchange_order_id"].startswith("MOCK_")
        assert event["status"] == "NEW"

    def test_cancel_dry_run(self, adapter: MockExecutionAdapter) -> None:
        event = adapter.cancel(order_id="ord-1", client_order_id="coid-1")
        assert event["event_type"] == "CANCELLED"
        assert event["status"] == "SIMULATED"

    def test_cancel_paper_mode(self) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            adapter = MockExecutionAdapter(mode=ExecutionMode.PAPER)
        # First submit
        order = OrderDTO(symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.1"))
        ev = adapter.submit(order)
        oid = ev["exchange_order_id"]
        # Then cancel
        cancel_ev = adapter.cancel(order_id=oid)
        assert cancel_ev["event_type"] == "CANCELLED"

    def test_cancel_requires_id(self, adapter: MockExecutionAdapter) -> None:
        with pytest.raises(ValueError, match="Must provide"):
            adapter.cancel()

    def test_submit_idempotent_duplicate(self, adapter: MockExecutionAdapter) -> None:
        order = OrderDTO(
            symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.01"),
        )
        adapter.submit(order)
        # Same order within same second → duplicate
        with pytest.raises(IdempotentDuplicateError):
            adapter.submit(order)

    def test_cb_open_raises(self, adapter: MockExecutionAdapter) -> None:
        adapter.cb.state = CircuitBreakerState.OPEN
        adapter.cb.open_at_ms = time.time() * 1000 + 60000  # far future
        order = OrderDTO(symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.01"))
        with pytest.raises(CBOpenError):
            adapter.submit(order)

    def test_metrics_recorded_after_submit(self, adapter: MockExecutionAdapter) -> None:
        order = OrderDTO(symbol="BTCUSDT", side="buy", order_type="market", qty=Decimal("0.01"))
        adapter.submit(order)
        assert adapter.metrics.sdk_submit_total == 1
        assert len(adapter.metrics.sdk_submit_latencies) == 1

    def test_generate_client_order_id_deterministic(self, adapter: MockExecutionAdapter) -> None:
        order = OrderDTO(
            symbol="BTCUSDT", side="buy", order_type="market",
            qty=Decimal("0.01"), idempotent_key="test-key",
        )
        id1 = adapter._generate_client_order_id(order)
        id2 = adapter._generate_client_order_id(order)
        assert id1 == id2
        assert len(id1) == 16
