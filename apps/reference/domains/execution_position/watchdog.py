"""
Order Timeout Watchdog (FSMP-P2-T01)

Monitors order execution timeouts and handles expired orders with NRR-019 logging.
Provides idempotent cancellation for timed-out orders.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any, Callable
from enum import Enum

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.terminal_order_contracts import (
    normalize_order_state_changed_payload,
)

from apps.reference.utils.accessors import dget

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
    # EP-01.3-INT: Per-order fill TTL override (ms). If set, used instead of global fill_ttl_ms.
    fill_ttl_override_ms: Optional[int] = None


class OrderTimeoutWatchdog:
    """
    Monitors order execution timeouts and handles expired orders.

    Tracks orders with deadlines and periodically checks for expirations.
    On timeout: logs NRR-019, marks order as EXPIRED, attempts idempotent cancel.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        ack_ttl_ms: int = 8000,  # 8 seconds for order acknowledgment
        fill_ttl_ms: int = 30000,  # 30 seconds for order fill
        check_interval_ms: int = 1000,  # Check every 1 second
        on_timeout_callback: Optional[Callable[[OrderDeadline], Any]] = None
    ):
        self.config = config or {}
        # Load from config if available, else use defaults
        self.ack_ttl_ms = self.config["ack_ttl_ms"] if "ack_ttl_ms" in self.config else ack_ttl_ms
        self.fill_ttl_ms = self.config["fill_ttl_ms"] if "fill_ttl_ms" in self.config else fill_ttl_ms
        self.check_interval_ms = self.config["check_interval_ms"] if "check_interval_ms" in self.config else check_interval_ms
        self.on_timeout_callback = on_timeout_callback

        # Track orders by order_id
        self.pending_orders: Dict[str, OrderDeadline] = {}
        self.acked_orders: Dict[str, OrderDeadline] = {}

        # Background task
        self._watchdog_task: Optional[asyncio.Task] = None
        self._started: bool = False
        # DET-BT-09: Allow disabling for deterministic backtest
        self._enabled: bool = True

        # Metrics
        self.timeout_count = 0
        self.cancel_attempt_count = 0
        self.cancel_success_count = 0

        # 🔧 POLLING FIX: REST polling infrastructure
        self.get_order_fn = None  # Will be set via set_hooks()
        self.emit_fn = None  # Will be set via set_hooks()
        # order_id -> poll metadata
        self._poll_meta: Dict[str, Dict[str, Any]] = {}
        self._rest_polls_total = 0
        self._rest_detected_fills_total = 0
        self._rest_detected_cancels_total = 0

        # 🔧 POLLING FIX: Global RPS throttle for REST polling
        self._rps_limit = self.config["rps_limit"] if "rps_limit" in self.config else 10  # Max 10 requests per second globally
        self._rps_window_start = 0
        self._rps_request_count = 0
        self._rps_throttle_hits = 0

    def set_hooks(self, get_order_fn, emit_fn) -> None:
        """
        🔧 POLLING FIX: Connect REST polling hooks to adapter functions.

        Enables proactive REST polling for fill detection when WebSocket is unavailable.
        """
        self.get_order_fn = get_order_fn
        self.emit_fn = emit_fn
        LOG.info("✅ OrderTimeoutWatchdog REST polling hooks connected")

    def _check_rps_limit(self) -> bool:
        """
        🔧 POLLING FIX: Check global RPS limit for REST polling.

        Returns True if request is allowed, False if throttled.
        """
        current_time_ms = get_clock().now_ms()
        window_start = current_time_ms // 1000 * 1000  # Current second window

        # Reset counter if we're in a new second
        if window_start != self._rps_window_start:
            self._rps_window_start = window_start
            self._rps_request_count = 0

        # Check if we're under the limit
        if self._rps_request_count < self._rps_limit:
            self._rps_request_count += 1
            return True
        else:
            self._rps_throttle_hits += 1
            return False

    def start(self) -> None:
        """
        Safe start: якщо немає running loop – нічого не робимо (відкладений старт).
        Гарантія: не створюємо корутину ДО перевірки loop (щоб не було 'never awaited').
        Ідемпотентність: повторні виклики безпечні.
        """
        if self._started:
            return
        # DET-BT-09: Skip if disabled (backtest mode)
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Немає активного event loop (sync-контекст старту/тест)
            LOG.info(
                "OrderTimeoutWatchdog deferred: no running event loop (startup/test).")
            return

        # Тільки тут створюємо корутину і таск
        task = loop.create_task(self._watchdog_loop(), name="watchdog_loop")
        task.add_done_callback(
            lambda t: LOG.error(
                "[Watchdog] Task died unexpectedly: %s", t.exception()
            ) if not t.cancelled() and t.exception() else None
        )
        self._watchdog_task = task
        self._started = True
        LOG.info("OrderTimeoutWatchdog started on running event loop.")

    def ensure_started(self) -> None:
        """
        Легка обгортка, яку можна викликати в будь-яких async-хендлерах FSM
        (ACK/FILL/PLACE): якщо loop вже є і task ще не створений – створимо.
        """
        if self._started:
            return
        # DET-BT-09: Skip if disabled (backtest mode)
        if not self._enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # все ще нема лупа – тихо ідемо далі
            return
        task = loop.create_task(self._watchdog_loop(), name="watchdog_loop")
        task.add_done_callback(
            lambda t: LOG.error(
                "[Watchdog] Task died unexpectedly: %s", t.exception()
            ) if not t.cancelled() and t.exception() else None
        )
        self._watchdog_task = task
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

    def disable(self) -> None:
        """
        DET-BT-09: Disable watchdog permanently (for backtest mode).
        
        Once disabled, start() and ensure_started() become no-ops.
        Use this in backtest to prevent race conditions.
        """
        self._enabled = False
        self.stop()
        LOG.info("OrderTimeoutWatchdog DISABLED for deterministic backtest.")

    def track_order_placed(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        corr_id: Optional[str] = None,
        rid: Optional[str] = None,
        # EP-01.3-INT: Per-order fill TTL override (ms)
        fill_ttl_override_ms: Optional[int] = None,
    ):
        """Track a newly placed order for ACK timeout.
        
        Args:
            fill_ttl_override_ms: If provided, overrides global fill_ttl_ms for this order.
                                  Used for pending entry TTL based on timeframe.
        """
        deadline_ms = get_clock().now_ms() + self.ack_ttl_ms

        deadline = OrderDeadline(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            deadline_ms=deadline_ms,
            timeout_type=OrderTimeoutType.ACK_TIMEOUT,
            corr_id=corr_id,
            rid=rid,
            fill_ttl_override_ms=fill_ttl_override_ms,  # EP-01.3-INT
        )

        self.pending_orders[order_id] = deadline
        ttl_info = f", fill_ttl_override={fill_ttl_override_ms}ms" if fill_ttl_override_ms else ""
        LOG.debug(
            f"Tracking order {order_id} for ACK timeout at {deadline_ms}{ttl_info}")

    def on_order_ack(self, order_id: str):
        """Mark order as acknowledged, start FILL timeout tracking."""
        # WD-001: Idempotency - already acked orders are skipped silently
        if order_id in self.acked_orders:
            LOG.debug(f"Order {order_id} already ACKed, skipping duplicate")
            return
        
        if order_id not in self.pending_orders:
            # WD-001: Demote to DEBUG - SL/TP orders are not tracked, this is expected
            LOG.debug(f"ACK received for untracked order {order_id} (SL/TP or external)")
            return

        deadline = self.pending_orders.pop(order_id)

        # EP-01.3-INT: Use per-order fill TTL if provided, else global
        fill_ttl = deadline.fill_ttl_override_ms if deadline.fill_ttl_override_ms else self.fill_ttl_ms
        fill_deadline_ms = get_clock().now_ms() + fill_ttl
        deadline.deadline_ms = fill_deadline_ms
        deadline.timeout_type = OrderTimeoutType.FILL_TIMEOUT

        self.acked_orders[order_id] = deadline
        ttl_source = "override" if deadline.fill_ttl_override_ms else "global"
        LOG.debug(
            f"Order {order_id} ACKed, now tracking for FILL timeout at {fill_deadline_ms} ({ttl_source}: {fill_ttl}ms)")

    def on_order_fill(self, order_id: str):
        """Remove order from timeout tracking on successful fill."""
        if order_id in self.acked_orders:
            del self.acked_orders[order_id]
            LOG.debug(
                f"Order {order_id} filled, removed from timeout tracking")
        elif order_id in self.pending_orders:
            # BUG FIX: Also remove from pending_orders if fill arrives before ACK
            del self.pending_orders[order_id]
            LOG.warning(
                f"Fill received for order {order_id} that was still pending ACK (removed)")
        # BUG FIX: Clean up poll metadata to prevent memory leak
        self._poll_meta.pop(order_id, None)

    def on_order_cancel(self, order_id: str):
        """Remove order from timeout tracking on cancellation."""
        self.pending_orders.pop(order_id, None)
        self.acked_orders.pop(order_id, None)
        # BUG FIX: Clean up poll metadata to prevent memory leak
        self._poll_meta.pop(order_id, None)
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
        current_time_ms = get_clock().now_ms()

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

        # 🔧 POLLING FIX: Proactive REST polling for fill detection
        # Poll orders based on their individual backoff schedules
        if self.get_order_fn:
            await self._poll_order_statuses()

        # Handle expired orders
        for deadline in expired_pending + expired_acked:
            await self._handle_timeout(deadline)

    async def _poll_order_statuses(self) -> None:
        """
        🔧 POLLING FIX: Proactive REST polling for fill detection.

        Polls order status via REST API to detect fills that WebSocket might have missed.
        Reduces false ORDER_TIMEOUT by providing secondary fill detection.
        """
        if not self.get_order_fn:
            return

        try:
            # Get all tracked order IDs
            tracked_order_ids = set(self.pending_orders.keys()) | set(
                self.acked_orders.keys())
            if not tracked_order_ids:
                return

            current_time_ms = get_clock().now_ms()

            # Poll each tracked order individually
            for order_id in tracked_order_ids:
                # Get poll metadata for this order
                meta = (
                    self._poll_meta[order_id]
                    if order_id in self._poll_meta
                    else {
                        "next_poll_at": 0,
                        "attempts": 0,
                        "backoff_ms": 1000,  # Start with 1 second backoff
                    }
                )

                # Check if we should poll this order (respect backoff)
                if current_time_ms < meta['next_poll_at']:
                    continue

                # Get symbol for this order
                symbol = None
                if order_id in self.pending_orders:
                    symbol = self.pending_orders[order_id].symbol
                elif order_id in self.acked_orders:
                    symbol = self.acked_orders[order_id].symbol

                if not symbol:
                    continue

                try:
                    # Check global RPS limit before making request
                    if not self._check_rps_limit():
                        LOG.debug(
                            f"🔧 POLLING THROTTLED: RPS limit hit for {order_id}")
                        continue

                    self._rest_polls_total += 1
                    order_status = await self.get_order_fn(symbol, order_id)

                    if order_status:
                        status = str(dget(order_status, "status", "")).upper()
                        executed_qty = float(
                            dget(order_status, "executedQty", 0))

                        if status == "FILLED" and executed_qty > 0:
                            # Check if already processed (idempotency)
                            if bool(dget(meta, "terminal", False)):
                                LOG.debug(
                                    f"🔧 POLLING SKIP: {order_id} already processed (terminal=True)")
                                continue

                            # Order was filled! Notify via event emission
                            LOG.info(
                                f"🔧 POLLING DETECTED FILL: {order_id} ({symbol}) qty={executed_qty}")
                            self._rest_detected_fills_total += 1

                            # Emit TRADE_EXECUTED event instead of direct FSM call
                            deadline = None
                            if order_id in self.pending_orders:
                                deadline = self.pending_orders.get(order_id)
                            elif order_id in self.acked_orders:
                                deadline = self.acked_orders.get(order_id)
                            fill_payload = {
                                "orderId": order_id,
                                "symbol": symbol,
                                "quantity": executed_qty,
                                "qty": executed_qty,
                                "price": float(dget(order_status, "avgPrice", 0)),
                                "clientOrderId": (
                                    dget(order_status, "clientOrderId", "")
                                    or getattr(deadline, "client_order_id", "")
                                ),
                                "client_order_id": (
                                    dget(order_status, "clientOrderId", "")
                                    or getattr(deadline, "client_order_id", "")
                                ),
                                "rid": getattr(deadline, "rid", None),
                                "ts_ms": current_time_ms,
                            }

                            if self.emit_fn:
                                await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)

                            # BUG FIX: Stop timeout tracking immediately!
                            self.on_order_fill(order_id)

                            # Mark as terminal to prevent duplicate processing
                            meta['terminal'] = True
                            # Reset backoff on success
                            meta['attempts'] = 0
                            meta['backoff_ms'] = 1000

                        elif status in ("CANCELED", "REJECTED", "EXPIRED"):
                            # Check if already processed (idempotency)
                            if bool(dget(meta, "terminal", False)):
                                LOG.debug(
                                    f"🔧 POLLING SKIP: {order_id} already processed (terminal=True)")
                                continue

                            # Order was cancelled/expired, emit ORDER_STATE_CHANGED and remove from tracking
                            LOG.debug(
                                f"🔧 POLLING DETECTED CANCEL: {order_id} ({symbol}) status={status}")
                            self._rest_detected_cancels_total += 1

                            # Emit ORDER_STATE_CHANGED event for symmetry with TRADE_EXECUTED
                            cancel_payload = normalize_order_state_changed_payload({
                                "orderId": order_id,
                                "symbol": symbol,
                                "status": status,
                                "client_order_id": dget(order_status, "clientOrderId", ""),
                                "rid": None  # Will be looked up from correlation store
                            }, fallback_ts_ms=get_clock().now_ms())

                            if self.emit_fn:
                                await self.emit_fn("EVT:ORDER_STATE_CHANGED", cancel_payload)

                            self.on_order_cancel(order_id)

                            # Mark as terminal to prevent duplicate processing
                            meta['terminal'] = True
                            # Reset backoff
                            meta['attempts'] = 0
                            meta['backoff_ms'] = 1000

                        else:
                            # Order still pending, increase backoff
                            meta['attempts'] += 1
                            # Exponential backoff, max 30s
                            meta['backoff_ms'] = min(
                                meta['backoff_ms'] * 2, 30000)

                    else:
                        # Order not found, might be cancelled
                        LOG.debug(f"🔧 POLLING: Order {order_id} not found")
                        # Check if already processed (idempotency)
                        if not bool(dget(meta, "terminal", False)):
                            self.on_order_cancel(order_id)
                            meta['terminal'] = True
                        # Reset backoff
                        meta['attempts'] = 0
                        meta['backoff_ms'] = 1000

                    # Update next poll time
                    meta['next_poll_at'] = current_time_ms + meta['backoff_ms']
                    self._poll_meta[order_id] = meta

                except Exception as e:
                    LOG.debug(
                        f"Error polling order {order_id} for {symbol}: {e}")
                    # On error, increase backoff
                    meta['attempts'] += 1
                    meta['backoff_ms'] = min(meta['backoff_ms'] * 2, 30000)
                    meta['next_poll_at'] = current_time_ms + meta['backoff_ms']
                    self._poll_meta[order_id] = meta

        except Exception as e:
            LOG.debug(f"Error in REST polling: {e}")

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
                result = self.on_timeout_callback(deadline)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
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
            # 🔧 POLLING FIX: REST polling metrics
            "rest_polls_total": self._rest_polls_total,
            "rest_detected_fills_total": self._rest_detected_fills_total,
            "rest_detected_cancels_total": self._rest_detected_cancels_total,
            "rps_throttle_hits": self._rps_throttle_hits,
            "rps_limit": self._rps_limit,
        }
