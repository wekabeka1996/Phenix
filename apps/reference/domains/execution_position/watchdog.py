"""
Order Timeout Watchdog (FSMP-P2-T01)

Monitors order execution timeouts and handles expired orders with NRR-019 logging.
Provides idempotent cancellation for timed-out orders.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any, Callable
from enum import Enum

LOG = logging.getLogger(__name__)


class OrderTimeoutType(str, Enum):
    """Types of order timeouts"""
    ACK_TIMEOUT = "ack_timeout"  # Order not acknowledged within ack_ttl_ms
    FILL_TIMEOUT = "fill_timeout"  # Order not filled within fill_ttl_ms


@dataclass
class OrderDeadline:
    """Tracks deadline information for an order"""
    order_id: str
    client_order_id: str
    symbol: str
    deadline_ms: int  # Unix timestamp in milliseconds
    timeout_type: OrderTimeoutType
    corr_id: Optional[str] = None
    rid: Optional[str] = None


class OrderTimeoutWatchdog:
    """
    Monitors order execution timeouts and handles expired orders.

    Tracks orders with deadlines and periodically checks for expirations.
    On timeout: logs NRR-019, marks order as EXPIRED, attempts idempotent cancel.
    """


class OrderTimeoutWatchdog:
    """
    Monitors order execution timeouts and handles expired orders.

    Tracks orders with deadlines and periodically checks for expirations.
    On timeout: logs NRR-019, marks order as EXPIRED, attempts idempotent cancel.
    """

    def __init__(
        self,
        ack_ttl_ms: int = 8000,  # 8 seconds for order acknowledgment
        fill_ttl_ms: int = 30000,  # 30 seconds for order fill
        check_interval_ms: int = 1000,  # Check every 1 second
        on_timeout_callback: Optional[Callable[[OrderDeadline], None]] = None
    ):
        self.ack_ttl_ms = ack_ttl_ms
        self.fill_ttl_ms = fill_ttl_ms
        self.check_interval_ms = check_interval_ms
        self.on_timeout_callback = on_timeout_callback

        # Track orders by order_id
        self.pending_orders: Dict[str, OrderDeadline] = {}
        self.acked_orders: Dict[str, OrderDeadline] = {}

        # Background task
        self._watchdog_task: Optional[asyncio.Task] = None
        self._started: bool = False

        # Metrics
        self.timeout_count = 0
        self.cancel_attempt_count = 0
        self.cancel_success_count = 0

    def start(self) -> None:
        """
        Safe start: якщо немає running loop – нічого не робимо (відкладений старт).
        Гарантія: не створюємо корутину ДО перевірки loop (щоб не було 'never awaited').
        Ідемпотентність: повторні виклики безпечні.
        """
        if self._started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Немає активного event loop (sync-контекст старту/тест)
            LOG.info(
                "OrderTimeoutWatchdog deferred: no running event loop (startup/test).")
            return

        # Тільки тут створюємо корутину і таск
        self._watchdog_task = loop.create_task(self._watchdog_loop())
        self._started = True
        LOG.info("OrderTimeoutWatchdog started on running event loop.")

    def ensure_started(self) -> None:
        """
        Легка обгортка, яку можна викликати в будь-яких async-хендлерах FSM
        (ACK/FILL/PLACE): якщо loop вже є і task ще не створений – створимо.
        """
        if self._started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # все ще нема лупа – тихо ідемо далі
            return
        self._watchdog_task = loop.create_task(self._watchdog_loop())
        self._started = True
        LOG.info("OrderTimeoutWatchdog late-started on running event loop.")

    def stop(self) -> None:
        """
        Безпечна зупинка: не кидає, не вимагає loop, ідемпотентна.
        """
        task = self._watchdog_task
        if task and not task.done():
            task.cancel()
        self._watchdog_task = None
        self._started = False
        LOG.info("OrderTimeoutWatchdog stopped.")

    def track_order_placed(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        corr_id: Optional[str] = None,
        rid: Optional[str] = None
    ):
        """Track a newly placed order for ACK timeout."""
        deadline_ms = int(time.time() * 1000) + self.ack_ttl_ms

        deadline = OrderDeadline(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            deadline_ms=deadline_ms,
            timeout_type=OrderTimeoutType.ACK_TIMEOUT,
            corr_id=corr_id,
            rid=rid
        )

        self.pending_orders[order_id] = deadline
        LOG.debug(
            f"Tracking order {order_id} for ACK timeout at {deadline_ms}")

    def on_order_ack(self, order_id: str):
        """Mark order as acknowledged, start FILL timeout tracking."""
        if order_id not in self.pending_orders:
            LOG.warning(f"ACK received for unknown order {order_id}")
            return

        deadline = self.pending_orders.pop(order_id)

        # Start FILL timeout
        fill_deadline_ms = int(time.time() * 1000) + self.fill_ttl_ms
        deadline.deadline_ms = fill_deadline_ms
        deadline.timeout_type = OrderTimeoutType.FILL_TIMEOUT

        self.acked_orders[order_id] = deadline
        LOG.debug(
            f"Order {order_id} ACKed, now tracking for FILL timeout at {fill_deadline_ms}")

    def on_order_fill(self, order_id: str):
        """Remove order from timeout tracking on successful fill."""
        if order_id in self.acked_orders:
            del self.acked_orders[order_id]
            LOG.debug(
                f"Order {order_id} filled, removed from timeout tracking")
        elif order_id in self.pending_orders:
            LOG.warning(
                f"Fill received for order {order_id} that was still pending ACK")

    def on_order_cancel(self, order_id: str):
        """Remove order from timeout tracking on cancellation."""
        self.pending_orders.pop(order_id, None)
        self.acked_orders.pop(order_id, None)
        LOG.debug(f"Order {order_id} cancelled, removed from timeout tracking")

    async def _watchdog_loop(self):
        """Main watchdog loop that checks for expired orders."""
        while self._started:
            try:
                await self._check_timeouts()
                await asyncio.sleep(self.check_interval_ms / 1000)
            except Exception as e:
                LOG.error(f"Watchdog loop error: {e}", exc_info=True)

    async def _check_timeouts(self):
        """Check all tracked orders for timeouts."""
        current_time_ms = int(time.time() * 1000)

        # Check pending orders (ACK timeout)
        expired_pending = [
            deadline for deadline in self.pending_orders.values()
            if current_time_ms >= deadline.deadline_ms
        ]

        # Check acked orders (FILL timeout)
        expired_acked = [
            deadline for deadline in self.acked_orders.values()
            if current_time_ms >= deadline.deadline_ms
        ]

        # Handle expired orders
        for deadline in expired_pending + expired_acked:
            await self._handle_timeout(deadline)

    async def _handle_timeout(self, deadline: OrderDeadline):
        """Handle a timed-out order."""
        self.timeout_count += 1

        # Remove from tracking
        self.pending_orders.pop(deadline.order_id, None)
        self.acked_orders.pop(deadline.order_id, None)

        LOG.warning(
            f"Order timeout: {deadline.order_id} ({deadline.symbol}) - {deadline.timeout_type.value}, "
            f"nrr_code=NRR-019, corr_id={deadline.corr_id}, rid={deadline.rid}"
        )

        # Call callback if provided
        if self.on_timeout_callback:
            try:
                await self.on_timeout_callback(deadline)
            except Exception as e:
                LOG.error(
                    f"Timeout callback error for order {deadline.order_id}: {e}", exc_info=True)

    def get_metrics(self) -> Dict[str, Any]:
        """Get watchdog metrics."""
        return {
            "pending_orders_count": len(self.pending_orders),
            "acked_orders_count": len(self.acked_orders),
            "total_timeouts": self.timeout_count,
            "cancel_attempts": self.cancel_attempt_count,
            "cancel_successes": self.cancel_success_count,
            "ack_ttl_ms": self.ack_ttl_ms,
            "fill_ttl_ms": self.fill_ttl_ms,
        }
