"""
LimitOrderMonitor - Autonomous LIMIT Order Lifecycle Manager

Canonical location: execution_position domain.

Responsibilities:
- Monitor all active LIMIT orders across symbols
- Track order placement timestamps
- Cancel orders that exceed configured timeout
- Emit observability events for monitoring
- Integrate with OrderGuardian for coordination

Design Pattern: Observer + Per-Order Timer
- Event-driven registration (ORDER_PLACED events)
- Per-order asyncio timer tasks (exact-expiry, no polling jitter)
- Cleanup on ORDER_FILLED/ORDER_CANCELLED events via unregister_order()

Configuration (via AuroraConfig):
```yaml
trading:
  execution:
    limit_orders:
      enable_monitoring: true
      default_timeout_sec: 30
      poll_interval_sec: 5  # legacy, kept for config compat
      auto_cancel_expired: true
      max_limit_orders_per_symbol: 3
```
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Set, Any
from decimal import Decimal
from dataclasses import dataclass, field

LOG = logging.getLogger(__name__)


@dataclass
class LimitOrderState:
    """State tracking for a single LIMIT order"""
    order_id: str
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    client_order_id: str
    placed_ts: float
    timeout_sec: int
    corr_id: Optional[str] = None
    rid: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float) -> bool:
        """Check if order has exceeded timeout"""
        return (now - self.placed_ts) > self.timeout_sec

    def age_seconds(self, now: float) -> float:
        """Get order age in seconds"""
        return now - self.placed_ts


class LimitOrderMonitor:
    """
    Autonomous LIMIT Order Monitor using per-order timer tasks.

    Each registered order gets its own asyncio task that fires exactly at
    expiry. unregister_order() cancels the task immediately — no polling.
    """

    def __init__(
        self,
        adapter: Optional[Any],
        config: Optional[Any] = None,
        bus: Optional[Any] = None,
    ):
        self.adapter = adapter
        self.config = config
        self.bus = bus

        # Tracked LIMIT orders: {order_id: LimitOrderState}
        self._active_orders: Dict[str, LimitOrderState] = {}

        # Per-order timer tasks: {order_id: asyncio.Task}
        self._timer_tasks: Dict[str, asyncio.Task] = {}

        # Per-symbol order count: {symbol: count}
        self._symbol_counts: Dict[str, int] = {}

        # Configuration
        self._enabled = True
        self._default_timeout_sec = 30
        self._auto_cancel = True
        self._max_per_symbol = 3

        if config and hasattr(config, 'trading'):
            try:
                limit_cfg = config.trading.execution.limit_orders if \
                    config.trading.execution and \
                    hasattr(config.trading.execution, 'limit_orders') else None

                if limit_cfg:
                    self._enabled = getattr(
                        limit_cfg, 'enable_monitoring', True)
                    self._default_timeout_sec = getattr(
                        limit_cfg, 'default_timeout_sec', 30)
                    self._auto_cancel = getattr(
                        limit_cfg, 'auto_cancel_expired', True)
                    self._max_per_symbol = getattr(
                        limit_cfg, 'max_limit_orders_per_symbol', 3)
            except AttributeError:
                pass

        self._running = False

        LOG.info(
            "TOMBSTONE_HIT module=limit_order_monitor class=LimitOrderMonitor "
            "reason=instantiated_in_runtime — report to Package-0 audit"
        )

        # Metrics
        self._metrics = {
            'orders_tracked': 0,
            'orders_cancelled_timeout': 0,
            'orders_cancelled_limit': 0,
            'errors': 0,
        }

        LOG.info(
            f"LimitOrderMonitor initialized: enabled={self._enabled}, "
            f"timeout={self._default_timeout_sec}s, "
            f"auto_cancel={self._auto_cancel}, max_per_symbol={self._max_per_symbol}"
        )

    async def start(self):
        """Start the monitor (no-op — timers are per-order, started on registration)"""
        if not self._enabled:
            LOG.info("LimitOrderMonitor disabled in config")
            return
        self._running = True
        LOG.info("LimitOrderMonitor started (per-order timer mode)")

    async def stop(self):
        """Stop monitoring — cancel all pending timer tasks"""
        self._running = False
        for order_id, task in list(self._timer_tasks.items()):
            if not task.done():
                task.cancel()
        self._timer_tasks.clear()
        LOG.info("LimitOrderMonitor stopped")

    def register_limit_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        client_order_id: str,
        timeout_sec: Optional[int] = None,
        corr_id: Optional[str] = None,
        rid: Optional[str] = None,
        **metadata
    ):
        """
        Register a LIMIT order for monitoring.

        Starts a per-order timer task that fires exactly at timeout_sec.
        Call this immediately after successful LIMIT order placement.
        """
        if not self._enabled:
            return

        # Check per-symbol limit
        current_count = self._symbol_counts.get(symbol, 0)
        if current_count >= self._max_per_symbol:
            LOG.warning(
                f"Symbol {symbol} has {current_count} LIMIT orders "
                f"(max={self._max_per_symbol}), not tracking new order"
            )
            self._metrics['orders_cancelled_limit'] += 1
            return

        timeout = timeout_sec if timeout_sec is not None else self._default_timeout_sec

        state = LimitOrderState(
            order_id=order_id,
            symbol=symbol,
            side=side,
            price=Decimal(str(price)),
            qty=Decimal(str(qty)),
            client_order_id=client_order_id,
            placed_ts=time.time(),
            timeout_sec=timeout,
            corr_id=corr_id,
            rid=rid,
            metadata=metadata
        )

        self._active_orders[order_id] = state
        self._symbol_counts[symbol] = self._symbol_counts.get(symbol, 0) + 1
        self._metrics['orders_tracked'] += 1

        # Start per-order timer task
        if self._running or not self._timer_tasks:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    task = asyncio.create_task(
                        self._expire_after(order_id, timeout))
                    self._timer_tasks[order_id] = task
            except RuntimeError:
                # No event loop running (e.g. sync context / testing) — timer not created
                pass

        LOG.info(
            f"Tracking LIMIT order: {symbol} {side} {order_id} "
            f"(timeout={timeout}s, count={self._symbol_counts[symbol]})"
        )

    def unregister_order(self, order_id: str, reason: str = "filled_or_cancelled"):
        """
        Remove order from tracking (called when filled or manually cancelled).
        Cancels the associated timer task immediately.
        """
        if order_id not in self._active_orders:
            return

        # Cancel timer task to prevent spurious cancellation
        task = self._timer_tasks.pop(order_id, None)
        if task and not task.done():
            task.cancel()

        state = self._active_orders.pop(order_id)
        self._symbol_counts[state.symbol] = max(
            0, self._symbol_counts.get(state.symbol, 0) - 1)

        LOG.info(
            f"Untracked LIMIT order: {state.symbol} {order_id} ({reason})")

    async def _expire_after(self, order_id: str, timeout_sec: int):
        """Per-order timer: sleep exactly timeout_sec, then cancel if still active."""
        try:
            await asyncio.sleep(timeout_sec)
        except asyncio.CancelledError:
            return  # Order was filled/cancelled before expiry

        state = self._active_orders.get(order_id)
        if state and self._auto_cancel and self.adapter:
            await self._cancel_expired_order(order_id, state, time.time())
        elif state:
            age = state.age_seconds(time.time())
            LOG.warning(
                f"LIMIT order {state.symbol} {order_id} expired "
                f"(age={age:.1f}s, timeout={state.timeout_sec}s) - auto_cancel disabled"
            )
            self.unregister_order(order_id, "timeout_no_cancel")

    async def _cancel_expired_order(self, order_id: str, state: LimitOrderState, now: float):
        """Cancel an expired LIMIT order"""
        age = state.age_seconds(now)

        LOG.warning(
            f"Cancelling expired LIMIT order: {state.symbol} {order_id} "
            f"(age={age:.1f}s, timeout={state.timeout_sec}s)"
        )

        try:
            await self.adapter.cancel_order(state.symbol, order_id)
            LOG.info(f"Cancelled expired LIMIT: {state.symbol} {order_id}")
            self._metrics['orders_cancelled_timeout'] += 1

            # Emit event for observability
            if self.bus:
                from vfoundation.core.protocol import Message
                event = Message(
                    op="EVT",
                    verb="LIMIT_ORDER_TIMEOUT",
                    src="limit_order_monitor",
                    dst="execution_position",
                    rid=state.rid or "",
                    why=f"timeout_{age:.1f}s",
                    pld={
                        "symbol": state.symbol,
                        "order_id": order_id,
                        "age_sec": age,
                        "timeout_sec": state.timeout_sec,
                    }
                )
                if hasattr(self.bus, 'emit'):
                    self.bus.emit(event)

        except Exception as e:
            LOG.error(f"Failed to cancel expired LIMIT {order_id}: {e}")
            self._metrics['errors'] += 1
        finally:
            self.unregister_order(order_id, "timeout_cancelled")

    def get_active_orders(self, symbol: Optional[str] = None) -> Dict[str, LimitOrderState]:
        """Get all active LIMIT orders, optionally filtered by symbol"""
        if symbol:
            return {oid: state for oid, state in self._active_orders.items()
                    if state.symbol == symbol}
        return self._active_orders.copy()

    def get_symbol_count(self, symbol: str) -> int:
        """Get number of active LIMIT orders for a symbol"""
        return self._symbol_counts.get(symbol, 0)

    def can_place_limit_order(self, symbol: str) -> bool:
        """Check if a new LIMIT order can be placed for symbol"""
        return self.get_symbol_count(symbol) < self._max_per_symbol

    def get_metrics(self) -> Dict[str, int]:
        """Get monitoring metrics"""
        return {
            **self._metrics,
            'active_orders': len(self._active_orders),
            'tracked_symbols': len([c for c in self._symbol_counts.values() if c > 0])
        }
