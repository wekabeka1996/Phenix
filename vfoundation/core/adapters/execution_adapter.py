"""
Execution Adapter (FSMP-P2-T01)

Abstract base class + mock implementation for exchange SDK integration.
Supports dry_run, paper, and live modes with retry/CB/idempotency/metrics.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional

from vfoundation.config import config
from vfoundation.core.adapters.execution_exceptions import (
    CBOpenError,
    IdempotentDuplicateError,
    RateLimitError,
    SDKError,
)
from vfoundation.core.adapters.idempotency_ledger import IdempotencyLedger

logger = logging.getLogger(__name__)


class ExecutionMode(str, enum.Enum):
    """Execution mode for adapter."""

    DRY_RUN = "dry_run"
    PAPER = "paper"
    LIVE = "live"


class CircuitBreakerState(str, enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Suppressing operations
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class OrderDTO:
    """Data transfer object for order submission."""

    symbol: str
    side: str  # "buy" | "sell"
    order_type: str  # "limit" | "market"
    qty: Decimal
    price: Optional[Decimal] = None
    reduce_only: bool = False
    time_in_force: str = "GTC"
    idempotent_key: Optional[str] = None  # User-provided key for idempotency


@dataclass
class AdapterMetrics:
    """Metrics for adapter operations."""

    sdk_submit_total: int = 0
    sdk_cancel_total: int = 0
    sdk_stream_events_total: int = 0
    sdk_retries_total: int = 0
    sdk_cb_open_total: int = 0

    # Latency tracking (in milliseconds)
    sdk_submit_latencies: List[float] = field(default_factory=list)
    sdk_cancel_latencies: List[float] = field(default_factory=list)

    def record_submit_latency(self, latency_ms: float) -> None:
        """Record submit latency (keep last 1000 samples)."""
        self.sdk_submit_latencies.append(latency_ms)
        if len(self.sdk_submit_latencies) > 1000:
            self.sdk_submit_latencies.pop(0)

    def record_cancel_latency(self, latency_ms: float) -> None:
        """Record cancel latency (keep last 1000 samples)."""
        self.sdk_cancel_latencies.append(latency_ms)
        if len(self.sdk_cancel_latencies) > 1000:
            self.sdk_cancel_latencies.pop(0)

    def get_p95_submit_latency(self) -> Optional[float]:
        """Get p95 submit latency."""
        if not self.sdk_submit_latencies:
            return None
        sorted_lat = sorted(self.sdk_submit_latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]

    def get_p95_cancel_latency(self) -> Optional[float]:
        """Get p95 cancel latency."""
        if not self.sdk_cancel_latencies:
            return None
        sorted_lat = sorted(self.sdk_cancel_latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]


class CircuitBreaker:
    """
    Circuit breaker for SDK operations.

    States: CLOSED → OPEN → HALF_OPEN → CLOSED
    """

    def __init__(
        self, open_threshold: float, cooldown_ms: int, half_open_probes: int, window_size: int = 100
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            open_threshold: Error rate threshold to open circuit (0.0-1.0)
            cooldown_ms: Cooldown period in OPEN state
            half_open_probes: Number of probes in HALF_OPEN state
            window_size: Rolling window size for error rate
        """
        self.open_threshold = open_threshold
        self.cooldown_ms = cooldown_ms
        self.half_open_probes = half_open_probes
        self.window_size = window_size

        self.state = CircuitBreakerState.CLOSED
        self.errors: List[bool] = []  # Rolling window of success/failure
        self.open_at_ms: Optional[float] = None
        self.half_open_successes = 0

    def record_success(self) -> None:
        """Record successful operation."""
        self.errors.append(False)
        if len(self.errors) > self.window_size:
            self.errors.pop(0)

        # In HALF_OPEN, track successes
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_probes:
                # Recovered - close circuit
                self.state = CircuitBreakerState.CLOSED
                self.half_open_successes = 0
                logger.info("CB: HALF_OPEN → CLOSED (recovered)")

    def record_error(self) -> None:
        """Record failed operation."""
        self.errors.append(True)
        if len(self.errors) > self.window_size:
            self.errors.pop(0)

        # In HALF_OPEN, any error reopens circuit
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.open_at_ms = time.time() * 1000
            self.half_open_successes = 0
            logger.warning("CB: HALF_OPEN → OPEN (probe failed)")
            return

        # In CLOSED, check error rate
        if self.state == CircuitBreakerState.CLOSED:
            error_rate = self._calculate_error_rate()
            if error_rate >= self.open_threshold:
                self.state = CircuitBreakerState.OPEN
                self.open_at_ms = time.time() * 1000
                logger.warning(f"CB: CLOSED → OPEN (error_rate={error_rate:.2f})")

    def _calculate_error_rate(self) -> float:
        """Calculate current error rate."""
        if not self.errors:
            return 0.0
        return sum(self.errors) / len(self.errors)

    def is_open(self) -> bool:
        """Check if circuit is open (suppressing operations)."""
        if self.state == CircuitBreakerState.CLOSED:
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            return False  # Allow probes

        # OPEN state - check cooldown
        now_ms = time.time() * 1000
        if self.open_at_ms and (now_ms - self.open_at_ms) >= self.cooldown_ms:
            # Cooldown expired - enter HALF_OPEN
            self.state = CircuitBreakerState.HALF_OPEN
            self.half_open_successes = 0
            logger.info("CB: OPEN → HALF_OPEN (cooldown expired)")
            return False

        return True


class ExecutionAdapter(ABC):
    """
    Abstract base class for execution adapters.

    Implements retry, CB, idempotency, metrics. Subclasses provide SDK integration.
    """

    def __init__(self, mode: Optional[ExecutionMode] = None) -> None:
        """
        Initialize adapter.

        Args:
            mode: Execution mode (defaults to config.execution_mode)
        """
        self.mode = mode or ExecutionMode(config.execution_mode)

        # Initialize components
        self.ledger = IdempotencyLedger(
            ttl_seconds=config.idem_ttl_ms // 1000, max_entries=config.idem_max_entries
        )
        self.cb = CircuitBreaker(
            open_threshold=config.adapter_cb_open_threshold,
            cooldown_ms=config.adapter_cb_cooldown_ms,
            half_open_probes=config.adapter_cb_half_open_probes,
        )
        self.metrics = AdapterMetrics()

        logger.info(f"ExecutionAdapter initialized: mode={self.mode}")

    def _generate_client_order_id(self, order: OrderDTO) -> str:
        """
        Generate deterministic client_order_id from order parameters.

        Same inputs → same ID (idempotency key).

        Args:
            order: Order DTO

        Returns:
            Hex string hash (16 chars = 64 bits)
        """
        # Bucket timestamp to 1-second granularity
        ts_bucket = int(time.time())

        # Construct deterministic key
        components = [
            order.symbol,
            order.side,
            str(order.qty),
            order.order_type,
            str(order.price) if order.price else "market",
            "reduce" if order.reduce_only else "open",
            str(ts_bucket),
            order.idempotent_key or "",
        ]
        key_str = "|".join(components)

        # Hash to 64 bits
        digest = hashlib.sha256(key_str.encode()).hexdigest()
        return digest[:16]  # 16 hex chars = 64 bits

    def submit(self, order: OrderDTO) -> Dict[str, Any]:
        """
        Submit order with retry, CB, idempotency.

        Args:
            order: Order to submit

        Returns:
            Event dict (EVT:ORDER_PLACED or EVT:REJECTED)

        Raises:
            CBOpenError: Circuit breaker is open
            AdapterTimeoutError: Operation timed out
            IdempotentDuplicateError: Duplicate submission
        """
        # Check CB
        if self.cb.is_open():
            self.metrics.sdk_cb_open_total += 1
            raise CBOpenError("submit")

        # Generate client_order_id for idempotency
        client_order_id = self._generate_client_order_id(order)

        # Check idempotency BEFORE execution
        existing_entry = self.ledger.get(client_order_id)
        if existing_entry:
            logger.info(f"Idempotent duplicate submit: {client_order_id}")
            # Raise IdempotentDuplicateError (caller can retrieve cached event via ledger)
            raise IdempotentDuplicateError(client_order_id)

        # Execute with retry
        start_ms = time.time() * 1000
        try:
            event = self._retry_operation(
                lambda: self._submit_impl(order, client_order_id), "submit"
            )

            # Store in ledger AFTER successful execution
            self.ledger.check_and_store(
                key=client_order_id, status="ORDER_PLACED", payload=event, event=event
            )

            # Record metrics
            latency_ms = time.time() * 1000 - start_ms
            self.metrics.sdk_submit_total += 1
            self.metrics.record_submit_latency(latency_ms)
            self.cb.record_success()

            logger.info(
                f"submit OK: {order.symbol} {order.side} {order.qty} | "
                f"client_order_id={client_order_id} | lat={latency_ms:.1f}ms"
            )
            return event

        except Exception as e:
            self.cb.record_error()
            logger.error(f"submit FAIL: {e}")
            raise

    def cancel(
        self, order_id: Optional[str] = None, client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel order with retry, CB, idempotency.

        Args:
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Event dict (EVT:CANCELLED or EVT:REJECTED)

        Raises:
            CBOpenError: Circuit breaker is open
            AdapterTimeoutError: Operation timed out
            ValueError: Neither order_id nor client_order_id provided
        """
        if not order_id and not client_order_id:
            raise ValueError("Must provide order_id or client_order_id")

        # Check CB
        if self.cb.is_open():
            self.metrics.sdk_cb_open_total += 1
            raise CBOpenError("cancel")

        # Use client_order_id as idempotency key
        idem_key = client_order_id or order_id or ""

        # Check idempotency BEFORE execution
        existing_entry = self.ledger.get(f"cancel_{idem_key}")
        if existing_entry:
            logger.info(f"Idempotent duplicate cancel: {idem_key}")
            # Raise IdempotentDuplicateError (caller can retrieve cached event via ledger)
            raise IdempotentDuplicateError(idem_key)

        # Execute with retry
        start_ms = time.time() * 1000
        try:
            event = self._retry_operation(
                lambda: self._cancel_impl(order_id, client_order_id), "cancel"
            )

            # Store in ledger AFTER successful execution
            self.ledger.check_and_store(
                key=f"cancel_{idem_key}", status="CANCELLED", payload=event, event=event
            )

            # Record metrics
            latency_ms = time.time() * 1000 - start_ms
            self.metrics.sdk_cancel_total += 1
            self.metrics.record_cancel_latency(latency_ms)
            self.cb.record_success()

            logger.info(f"cancel OK: {idem_key} | lat={latency_ms:.1f}ms")
            return event

        except Exception as e:
            self.cb.record_error()
            logger.error(f"cancel FAIL: {e}")
            raise

    def _retry_operation(self, operation: Any, op_name: str) -> Dict[str, Any]:
        """
        Retry operation with exponential backoff.

        Args:
            operation: Callable to retry
            op_name: Operation name for logging

        Returns:
            Result from operation

        Raises:
            Last exception if all retries fail
        """
        max_attempts = config.adapter_retry_max_attempts
        base_ms = config.adapter_retry_base_ms
        max_ms = config.adapter_retry_max_ms

        last_exception: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                result: Dict[str, Any] = operation()
                return result
            except (RateLimitError, SDKError) as e:
                last_exception = e

                if attempt >= max_attempts:
                    break

                # Exponential backoff with jitter
                delay_ms = min(base_ms * (2 ** (attempt - 1)), max_ms)
                jitter_ms = random.uniform(0, delay_ms * 0.1)
                total_delay_ms = delay_ms + jitter_ms

                self.metrics.sdk_retries_total += 1
                logger.warning(
                    f"Retry {attempt}/{max_attempts} {op_name}: {e.why} | "
                    f"wait={total_delay_ms:.0f}ms"
                )
                time.sleep(total_delay_ms / 1000)

        # All retries failed
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{op_name} failed after {max_attempts} attempts")

    @abstractmethod
    def _submit_impl(self, order: OrderDTO, client_order_id: str) -> Dict[str, Any]:
        """
        Implement order submission (subclass responsibility).

        Args:
            order: Order to submit
            client_order_id: Generated client order ID

        Returns:
            Event dict (EVT:ORDER_PLACED or EVT:REJECTED)
        """
        ...

    @abstractmethod
    def _cancel_impl(
        self, order_id: Optional[str], client_order_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Implement order cancellation (subclass responsibility).

        Args:
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Event dict (EVT:CANCELLED or EVT:REJECTED)
        """
        ...

    @abstractmethod
    def stream(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream execution events from SDK (subclass responsibility).

        Yields:
            Event dicts (EVT:PARTIAL_FILL, EVT:FILL, EVT:EXPIRED, etc.)

        Note: Implementation should be async generator (async def ... async for).
        """
        ...


class MockExecutionAdapter(ExecutionAdapter):
    """
    DEPRECATED: Mock implementation moved to tests/vfoundation/fixtures/mock_execution_adapter.py.

    This stub remains for backward compatibility only. Import from test fixtures instead:
        from tests.vfoundation.fixtures.mock_execution_adapter import MockExecutionAdapter

    Simulates order lifecycle without real SDK calls.
    """

    def __init__(self, mode: Optional[ExecutionMode] = None) -> None:
        import warnings
        warnings.warn(
            "MockExecutionAdapter in production code is deprecated. "
            "Import from tests.vfoundation.fixtures.mock_execution_adapter instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(mode)
        self._next_exchange_order_id = 1
        self._orders: Dict[str, Dict[str, Any]] = {}

    def _submit_impl(self, order: OrderDTO, client_order_id: str) -> Dict[str, Any]:
        """
        Mock submit implementation.

        Args:
            order: Order to submit
            client_order_id: Client order ID

        Returns:
            Simulated EVT:ORDER_PLACED
        """
        # Guard: dry_run prohibits trading methods
        if self.mode == ExecutionMode.DRY_RUN:
            logger.info(f"DRY_RUN: Simulating submit {order.symbol} {order.side} {order.qty}")
            # Return simulated event
            return {
                "event_type": "ORDER_PLACED",
                "client_order_id": client_order_id,
                "exchange_order_id": None,  # No real order
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "price": float(order.price) if order.price else None,
                "qty": float(order.qty),
                "qty_remain": float(order.qty),
                "status": "SIMULATED",
            }

        # Paper mode - simulate with state
        exchange_order_id = f"MOCK_{self._next_exchange_order_id}"
        self._next_exchange_order_id += 1

        order_state = {
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "price": order.price,
            "qty": order.qty,
            "qty_remain": order.qty,
            "status": "NEW",
        }
        self._orders[exchange_order_id] = order_state

        logger.info(f"PAPER: Order placed {exchange_order_id}")

        return {
            "event_type": "ORDER_PLACED",
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "price": float(order.price) if order.price else None,
            "qty": float(order.qty),
            "qty_remain": float(order.qty),
            "status": "NEW",
        }

    def _cancel_impl(
        self, order_id: Optional[str], client_order_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Mock cancel implementation.

        Args:
            order_id: Exchange order ID
            client_order_id: Client order ID

        Returns:
            Simulated EVT:CANCELLED
        """
        # Guard: dry_run prohibits trading methods
        if self.mode == ExecutionMode.DRY_RUN:
            logger.info(f"DRY_RUN: Simulating cancel {order_id or client_order_id}")
            return {
                "event_type": "CANCELLED",
                "client_order_id": client_order_id,
                "exchange_order_id": order_id,
                "reason": "USER_CANCEL",
                "status": "SIMULATED",
            }

        # Paper mode - update state
        if order_id and order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            logger.info(f"PAPER: Order cancelled {order_id}")

        return {
            "event_type": "CANCELLED",
            "client_order_id": client_order_id,
            "exchange_order_id": order_id,
            "reason": "USER_CANCEL",
            "status": "CANCELLED",
        }

    async def stream(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Mock stream implementation (no events in mock).

        Yields:
            No events (mock adapter doesn't simulate execution flow)
        """
        # Mock adapter doesn't stream events
        # In real implementation, this would connect to WebSocket
        logger.info("Mock stream: No events (use real adapter for streaming)")
        # Return empty async generator
        if False:  # pragma: no cover
            yield {}  # Type hint only, never executed
