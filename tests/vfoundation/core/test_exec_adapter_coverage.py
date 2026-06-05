"""Coverage tests for execution_adapter.py."""
import pytest
import time
from decimal import Decimal
from typing import Dict, Any, Optional, AsyncIterator
from vfoundation.core.adapters.execution_adapter import (
    ExecutionAdapter, ExecutionMode, CircuitBreakerState, OrderDTO,
    AdapterMetrics, CircuitBreaker
)
from vfoundation.core.adapters.execution_exceptions import SDKError


# ── AdapterMetrics ──────────────────────────────────────────────
class TestAdapterMetrics:
    def test_record_submit_latency(self):
        m = AdapterMetrics()
        m.record_submit_latency(10.0)
        m.record_submit_latency(20.0)
        assert len(m.sdk_submit_latencies) == 2

    def test_record_cancel_latency(self):
        m = AdapterMetrics()
        m.record_cancel_latency(5.0)
        assert len(m.sdk_cancel_latencies) == 1

    def test_p95_submit_empty(self):
        m = AdapterMetrics()
        assert m.get_p95_submit_latency() is None

    def test_p95_submit_with_data(self):
        m = AdapterMetrics()
        for i in range(20):
            m.record_submit_latency(float(i))
        p95 = m.get_p95_submit_latency()
        assert p95 is not None
        assert p95 > 0

    def test_p95_cancel_empty(self):
        m = AdapterMetrics()
        assert m.get_p95_cancel_latency() is None

    def test_p95_cancel_with_data(self):
        m = AdapterMetrics()
        for i in range(20):
            m.record_cancel_latency(float(i))
        p95 = m.get_p95_cancel_latency()
        assert p95 is not None
        assert p95 > 0

    def test_latency_cap_at_1000(self):
        m = AdapterMetrics()
        for i in range(1100):
            m.record_submit_latency(float(i))
        assert len(m.sdk_submit_latencies) == 1000


# ── CircuitBreaker (execution_adapter variant) ──────────────────
class TestExecCircuitBreaker:
    def test_closed_state_default(self):
        cb = CircuitBreaker(open_threshold=0.5, cooldown_ms=1000, half_open_probes=3)
        assert cb.state == CircuitBreakerState.CLOSED
        assert not cb.is_open()

    def test_opens_on_high_error_rate(self):
        cb = CircuitBreaker(open_threshold=0.3, cooldown_ms=1000, half_open_probes=1, window_size=10)
        for _ in range(10):
            cb.record_error()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open()

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(open_threshold=0.3, cooldown_ms=1, half_open_probes=1, window_size=5)
        for _ in range(5):
            cb.record_error()
        time.sleep(0.01)
        assert not cb.is_open()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_success_resets_from_half_open(self):
        cb = CircuitBreaker(open_threshold=0.3, cooldown_ms=1, half_open_probes=1, window_size=5)
        for _ in range(5):
            cb.record_error()
        time.sleep(0.01)
        cb.is_open()  # HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_error_in_half_open_reopens(self):
        cb = CircuitBreaker(open_threshold=0.3, cooldown_ms=1, half_open_probes=1, window_size=5)
        for _ in range(5):
            cb.record_error()
        time.sleep(0.01)
        cb.is_open()  # HALF_OPEN
        cb.record_error()  # Should reopen
        assert cb.state == CircuitBreakerState.OPEN

    def test_error_rate_calculation(self):
        cb = CircuitBreaker(open_threshold=0.5, cooldown_ms=1000, half_open_probes=1)
        cb.record_success()
        cb.record_error()
        rate = cb._calculate_error_rate()
        assert 0 <= rate <= 1.0

    def test_error_rate_empty(self):
        cb = CircuitBreaker(open_threshold=0.5, cooldown_ms=1000, half_open_probes=1)
        assert cb._calculate_error_rate() == 0.0


# ── OrderDTO ────────────────────────────────────────────────────
class TestOrderDTO:
    def test_creation(self):
        order = OrderDTO(
            symbol="BTCUSDT", side="BUY", order_type="MARKET",
            qty=Decimal("0.01")
        )
        assert order.symbol == "BTCUSDT"
        assert order.reduce_only is False

    def test_with_optional_fields(self):
        order = OrderDTO(
            symbol="ETHUSDT", side="SELL", order_type="LIMIT",
            qty=Decimal("1.0"), price=Decimal("3500"),
            idempotent_key="idem-123"
        )
        assert order.price == Decimal("3500")
        assert order.idempotent_key == "idem-123"


# ── ExecutionAdapter (mock) ─────────────────────────────────────
class MockExecAdapter(ExecutionAdapter):
    """Concrete subclass for testing."""
    def __init__(self, mode=None, fail_submit=False, fail_cancel=False):
        super().__init__(mode=mode)
        self.fail_submit = fail_submit
        self.fail_cancel = fail_cancel

    def _submit_impl(self, order: OrderDTO, client_order_id: str) -> Dict[str, Any]:
        if self.fail_submit:
            raise SDKError("exchange unreachable")
        return {
            "op": "EVT", "verb": "ORDER_PLACED",
            "pld": {"order_id": "123", "client_order_id": client_order_id}
        }

    def _cancel_impl(self, order_id: Optional[str],
                     client_order_id: Optional[str]) -> Dict[str, Any]:
        if self.fail_cancel:
            raise SDKError("cancel failed")
        return {
            "op": "EVT", "verb": "ORDER_CANCELLED",
            "pld": {"order_id": order_id}
        }

    async def stream(self) -> AsyncIterator[Dict[str, Any]]:
        yield {"op": "EVT", "verb": "FILL", "pld": {"order_id": "123"}}


class TestExecutionAdapter:
    def test_submit_success(self):
        adapter = MockExecAdapter(mode=ExecutionMode.DRY_RUN)
        order = OrderDTO(symbol="BTC", side="BUY", order_type="MARKET", qty=Decimal("0.01"))
        result = adapter.submit(order)
        assert result["verb"] == "ORDER_PLACED"
        assert adapter.metrics.sdk_submit_total == 1

    def test_submit_retries_on_sdk_error(self):
        adapter = MockExecAdapter(mode=ExecutionMode.DRY_RUN, fail_submit=True)
        order = OrderDTO(symbol="BTC", side="BUY", order_type="MARKET", qty=Decimal("0.01"))
        with pytest.raises(SDKError):
            adapter.submit(order)
        assert adapter.metrics.sdk_retries_total > 0

    def test_cancel_success(self):
        adapter = MockExecAdapter(mode=ExecutionMode.DRY_RUN)
        result = adapter.cancel(order_id="ord1")
        assert result["verb"] == "ORDER_CANCELLED"

    def test_cancel_no_ids_raises(self):
        adapter = MockExecAdapter()
        with pytest.raises(ValueError, match="Must provide"):
            adapter.cancel()

    def test_generate_client_order_id_deterministic(self):
        adapter = MockExecAdapter()
        order = OrderDTO(symbol="BTC", side="BUY", order_type="MARKET", qty=Decimal("0.01"))
        id1 = adapter._generate_client_order_id(order)
        id2 = adapter._generate_client_order_id(order)
        assert id1 == id2

    def test_cb_blocks_submit(self):
        adapter = MockExecAdapter(mode=ExecutionMode.DRY_RUN, fail_submit=True)
        order = OrderDTO(symbol="BTC", side="BUY", order_type="MARKET", qty=Decimal("0.01"))
        # Trip CB by failing
        for _ in range(5):
            try: adapter.submit(order)
            except: pass
        # Now CB should be open
        from vfoundation.core.adapters.execution_exceptions import CBOpenError
        with pytest.raises(CBOpenError):
            adapter.submit(order)
