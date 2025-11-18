"""
Order Timeout Watchdog (FSMP-P2-T01)

Monitors order execution timeouts and handles expired orders with NRR-019 logging.
Provides idempotent cancellation for timed-out orders.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

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

    def __init__(
        self,
        ack_ttl_ms: int = 8000,  # 8 seconds for order acknowledgment
        fill_ttl_ms: int = 30000,  # 30 seconds for order fill
        check_interval_ms: int = 1000,  # Check every 1 second
        on_timeout_callback: Optional[Callable[[OrderDeadline], Any]] = None
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

        # 🔧 POLLING FIX: REST polling infrastructure
        self.get_order_fn = None  # Will be set via set_hooks()
        self.emit_fn = None  # Will be set via set_hooks()
        # order_id -> poll metadata
        self._poll_meta: Dict[str, Dict[str, Any]] = {}
        self._rest_polls_total = 0
        self._rest_detected_fills_total = 0
        self._rest_detected_cancels_total = 0

        # 🔧 POLLING FIX: Global RPS throttle for REST polling
        self._rps_limit = 10  # Max 10 requests per second globally
        self._rps_window_start = 0
        self._rps_request_count = 0
        self._rps_throttle_hits = 0

        # Metrics logging counter
        self._metrics_log_counter = 0

    def set_hooks(self, get_order_fn, emit_fn) -> None:
        """
        🔧 POLLING FIX: Connect REST polling hooks to adapter functions.

        Enables proactive REST polling for fill detection when WebSocket is unavailable.
        """
        self.get_order_fn = get_order_fn
        self.emit_fn = emit_fn
        LOG.info("✅ OrderTimeoutWatchdog REST polling hooks connected")

    async def _emit_via_hook(self, event_name: str, payload: Dict[str, Any], log_event: str) -> None:
        """Emit REST-detected events via ExecPosFSM hooks with structured logging."""

        payload = dict(payload or {})
        payload.setdefault("source", payload.get("source") or "rest_watchdog")

        meta = {
            "event": event_name,
            "symbol": payload.get("symbol"),
            "order_id": payload.get("orderId") or payload.get("clientOrderId"),
            "quantity": payload.get("quantity") or payload.get("qty"),
        }

        if not self.emit_fn:
            LOG.error("WATCHDOG_EMIT_MISSING", extra=meta)
            return

        try:
            await self.emit_fn(event_name, payload)
            LOG.info(log_event, extra=meta)
        except Exception:
            LOG.exception("WATCHDOG_EMIT_FAILED", extra=meta)

    def _check_rps_limit(self) -> bool:
        """
        🔧 POLLING FIX: Check global RPS limit for REST polling.

        Returns True if request is allowed, False if throttled.
        """
        current_time_ms = int(time.time() * 1000)
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

    def _start_task(self, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        """Start watchdog loop on a loop if task isn't already running."""
        if self._started or not loop:
            return
        try:
            self._watchdog_task = loop.create_task(self._watchdog_loop())
            self._started = True
            LOG.info("OrderTimeoutWatchdog running (loop=%s)", loop)
        except Exception as exc:
            LOG.warning("OrderTimeoutWatchdog failed to start: %s", exc)

    def start(self) -> None:
        """Start watchdog when a running loop already exists."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            LOG.info(
                "OrderTimeoutWatchdog deferred: no running event loop (startup/test).")
            return
        self._start_task(loop)

    def ensure_started(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Attempt to start watchdog using provided loop or current running loop."""
        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                target_loop = None
        self._start_task(target_loop)

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

                # Log metrics every 100 iterations (approximately every 10 seconds at 1000ms interval)
                self._metrics_log_counter += 1
                if self._metrics_log_counter >= 100:
                    self._log_metrics()
                    self._metrics_log_counter = 0
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

            current_time_ms = int(time.time() * 1000)

            # Poll each tracked order individually
            for order_id in tracked_order_ids:
                # Get poll metadata for this order
                meta = self._poll_meta.get(order_id, {
                    'next_poll_at': 0,
                    'attempts': 0,
                    'backoff_ms': 1000  # Start with 1 second backoff
                })

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
                        status = str(order_status.get("status", "")).upper()
                        executed_qty = float(
                            order_status.get("executedQty", 0))

                        qty_raw = order_status.get("executedQty", 0)
                        try:
                            executed_qty = Decimal(str(qty_raw))
                        except (InvalidOperation, TypeError):
                            executed_qty = Decimal("0")

                        if status == "FILLED" and executed_qty > 0:
                            # Check if already processed (idempotency)
                            if meta.get('terminal', False):
                                LOG.debug(
                                    f"🔧 POLLING SKIP: {order_id} already processed (terminal=True)")
                                continue

                            # Order was filled! Notify via event emission
                            LOG.info(
                                f"🔧 POLLING DETECTED FILL: {order_id} ({symbol}) qty={executed_qty}")
                            self._rest_detected_fills_total += 1

                            # Emit TRADE_EXECUTED event instead of direct FSM call
                            fill_payload = self._build_trade_payload(
                                symbol=symbol,
                                order_id=order_id,
                                order_status=order_status,
                                executed_qty=executed_qty,
                            )

                            await self._emit_via_hook(
                                event_name="EVT:TRADE_EXECUTED",
                                payload=fill_payload,
                                log_event="WATCHDOG_EMIT_TRADE_EXECUTED",
                            )

                            # Mark as terminal to prevent duplicate processing
                            meta['terminal'] = True
                            # Reset backoff on success
                            meta['attempts'] = 0
                            meta['backoff_ms'] = 1000

                        elif status in ("CANCELED", "REJECTED", "EXPIRED"):
                            # Check if already processed (idempotency)
                            if meta.get('terminal', False):
                                LOG.debug(
                                    f"🔧 POLLING SKIP: {order_id} already processed (terminal=True)")
                                continue

                            # Order was cancelled/expired, emit ORDER_STATE_CHANGED and remove from tracking
                            LOG.debug(
                                f"🔧 POLLING DETECTED CANCEL: {order_id} ({symbol}) status={status}")
                            self._rest_detected_cancels_total += 1

                            # Emit ORDER_STATE_CHANGED event for symmetry with TRADE_EXECUTED
                            cancel_payload = {
                                "orderId": order_id,
                                "symbol": symbol,
                                "status": status,
                                "clientOrderId": order_status.get("clientOrderId", ""),
                                "rid": None  # Will be looked up from correlation store
                            }

                            await self._emit_via_hook(
                                event_name="EVT:ORDER_STATE_CHANGED",
                                payload=cancel_payload,
                                log_event="WATCHDOG_EMIT_ORDER_STATE_CHANGED",
                            )

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
                        if not meta.get('terminal', False):
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

    def _build_trade_payload(
        self,
        *,
        symbol: str,
        order_id: str,
        order_status: Dict[str, Any],
        executed_qty: Decimal,
    ) -> Dict[str, Any]:
        """Construct canonical TRADE_EXECUTED payload for REST-detected fills."""

        payload: Dict[str, Any] = {
            "orderId": str(order_id),
            "symbol": symbol,
            "venue": order_status.get("venue") or "binance_rest_watchdog",
            "source": "rest_watchdog",
        }

        client_order_id = order_status.get("clientOrderId")
        if client_order_id:
            payload["clientOrderId"] = str(client_order_id)

        side_raw = order_status.get("side") or order_status.get("orderSide")
        if side_raw:
            payload["side"] = str(side_raw).lower()

        qty_str = str(order_status.get("executedQty") or executed_qty)
        qty_str = qty_str.strip()
        if qty_str:
            qty_str = qty_str.lstrip("+")
            if payload.get("side") == "sell":
                qty_str = qty_str.lstrip("-")
                if qty_str and not qty_str.startswith("-"):
                    qty_str = f"-{qty_str}"
            else:
                qty_str = qty_str.lstrip("-")

        payload["quantity"] = qty_str or str(executed_qty)
        payload["qty"] = payload["quantity"]

        price = order_status.get("avgPrice")
        if not price or float(price) == 0:
            # Fallback: calculate from cummulativeQuoteQty / executedQty
            cqq = float(order_status.get("cummulativeQuoteQty", 0))
            eq = float(order_status.get("executedQty", 0))
            if eq > 0:
                price = str(cqq / eq)
            else:
                price = order_status.get("price")

        if price is not None:
            payload["price"] = str(price)

        ts = order_status.get("updateTime") or order_status.get("time")
        if ts is not None:
            payload["ts"] = ts

        for key in ("type", "orderType", "reduceOnly", "closePosition"):
            if order_status.get(key) is not None:
                payload[key] = order_status.get(key)

        return payload

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

    def _log_metrics(self) -> None:
        """Log watchdog metrics periodically."""
        LOG.info(
            f"WATCHDOG_METRICS rest_polls_total={self._rest_polls_total} rest_detected_fills_total={self._rest_detected_fills_total} rps_throttle_hits={self._rps_throttle_hits}")

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
