"""
Executor Pool V2 - Pure Execution Layer
========================================

Multi-symbol executor pool that acts as a "mechanical hand" for order execution.
All decisions (TP/SL levels, timing, quantities) come from BracketService.

Key Changes from V1:
- REMOVED: sl_pct, tp_rr parameters - no bracket math
- REMOVED: execute_order() with auto-brackets
- ADDED: execute_entry() - entry only
- ADDED: execute_bracket() - single bracket from BracketPlan
- ADDED: execute_batch() - multiple actions in sequence

Architecture:
┌────────────────────────────────────────────────────────┐
│                   ExecutorPoolV2                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │             Global Rate Limiter                  │   │
│  │         (8 orders/sec across all)                │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│         ┌───────────────┼───────────────┐              │
│         ▼               ▼               ▼              │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│   │ BTCUSDT  │   │ ETHUSDT  │   │ SOLUSDT  │          │
│   │Executor  │   │Executor  │   │Executor  │          │
│   │   V2     │   │   V2     │   │   V2     │          │
│   └──────────┘   └──────────┘   └──────────┘          │
└────────────────────────────────────────────────────────┘

Flow (BracketService is Single Source of Truth):
1. Runtime -> ExecutorPoolV2.execute_entry() -> Entry placed
2. WebSocket -> TRADE_EXECUTED -> Runtime
3. Runtime -> BracketService.evaluate() -> BracketPlan
4. Runtime -> ExecutorPoolV2.execute_batch(plan.actions) -> SL/TP placed

Author: Copilot
Date: 2025-11-29
RID: EXECUTOR-POOL-PHASE4-BRACKETS-SINGLE-SOURCE
"""
from typing import Any, Dict, Optional, List
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from .symbol_executor import SymbolExecutorV2, OrderResult

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Non-blocking token bucket rate limiter for Binance API limits.

    Returns False immediately if rate limit exceeded - NO blocking sleep.
    Supports optional per-symbol soft limits.
    """

    def __init__(
        self,
        max_requests: int = 8,
        window_seconds: float = 1.0,
        per_symbol_limit: int = 4,  # soft limit per symbol within window
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.per_symbol_limit = per_symbol_limit
        self._lock = threading.Lock()
        self._timestamps: deque = deque()
        self._symbol_timestamps: Dict[str, deque] = {}

    def try_acquire(self, symbol: Optional[str] = None) -> bool:
        """
        Try to acquire a slot. Returns immediately (non-blocking).

        Returns:
            True if slot acquired, False if rate limited.
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds

            # Remove old timestamps outside window (global)
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            # Check global limit
            if len(self._timestamps) >= self.max_requests:
                return False

            # Check per-symbol soft limit if symbol provided
            if symbol and self.per_symbol_limit > 0:
                if symbol not in self._symbol_timestamps:
                    self._symbol_timestamps[symbol] = deque()

                sym_ts = self._symbol_timestamps[symbol]
                while sym_ts and sym_ts[0] < cutoff:
                    sym_ts.popleft()

                if len(sym_ts) >= self.per_symbol_limit:
                    return False

                sym_ts.append(now)

            # Record successful acquisition
            self._timestamps.append(now)
            return True

    def acquire(self, timeout: float = 5.0, symbol: Optional[str] = None) -> bool:
        """
        DEPRECATED: Use try_acquire() for non-blocking behavior.
        Kept for backward compatibility - returns immediately on limit.

        Args:
            timeout: Ignored (kept for API compatibility)
            symbol: Optional symbol for per-symbol limiting

        Returns:
            True if slot acquired, False if rate limited.
        """
        return self.try_acquire(symbol=symbol)

    def get_wait_time(self, symbol: Optional[str] = None) -> float:
        """Get estimated wait time until next slot available."""
        with self._lock:
            now = time.time()

            # Global wait time
            if len(self._timestamps) < self.max_requests:
                global_wait = 0.0
            else:
                oldest = self._timestamps[0]
                global_wait = max(0.0, oldest + self.window_seconds - now)

            # Per-symbol wait time
            symbol_wait = 0.0
            if symbol and symbol in self._symbol_timestamps:
                sym_ts = self._symbol_timestamps[symbol]
                if len(sym_ts) >= self.per_symbol_limit:
                    sym_oldest = sym_ts[0]
                    symbol_wait = max(0.0, sym_oldest +
                                      self.window_seconds - now)

            return max(global_wait, symbol_wait)

    def get_available_slots(self) -> int:
        """Get number of available slots in the global window."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds

            # Clean old timestamps
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            return max(0, self.max_requests - len(self._timestamps))


@dataclass
class BatchResult:
    """Result of executing a batch of actions."""
    success: bool
    results: List[Dict[str, Any]]
    errors: List[str]
    total_latency_ms: float


class ExecutorPoolV2:
    """
    Pool of SymbolExecutorV2 with shared resources.

    This is a pure execution layer - NO bracket decision logic.
    All TP/SL decisions come from BracketService via BracketPlan.
    """

    def __init__(
        self,
        adapter: Any,
        gatekeeper: Any,
        fill_timeout_sec: float = 60.0,
        max_orders_per_second: int = 8,
    ):
        """
        Initialize pool.

        NOTE: No sl_pct, tp_rr - brackets are handled by BracketService.
        """
        self.adapter = adapter
        self.gatekeeper = gatekeeper
        self.fill_timeout_sec = fill_timeout_sec

        # Executors storage
        self._lock = threading.Lock()
        self._executors: Dict[str, SymbolExecutorV2] = {}

        # Global rate limiter
        self._rate_limiter = RateLimiter(
            max_requests=max_orders_per_second,
            window_seconds=1.0,
        )

        # Metrics
        self._metrics = {
            "executors_created": 0,
            "entries_routed": 0,
            "brackets_routed": 0,
            "batches_executed": 0,
            "rate_limit_waits": 0,
            "rate_limit_timeouts": 0,
        }

        logger.info(
            f"[ExecutorPoolV2] Initialized: "
            f"max_orders/sec={max_orders_per_second}, fill_timeout={fill_timeout_sec}s"
        )

    # ─────────────────────────────────────────────────────────────
    # Public API: Executor Management
    # ─────────────────────────────────────────────────────────────

    def get_executor(self, symbol: str) -> SymbolExecutorV2:
        """Get or create executor for symbol (thread-safe lazy init)."""
        with self._lock:
            if symbol not in self._executors:
                self._executors[symbol] = SymbolExecutorV2(
                    symbol=symbol,
                    adapter=self.adapter,
                    gatekeeper=self.gatekeeper,
                    fill_timeout_sec=self.fill_timeout_sec,
                )
                self._metrics["executors_created"] += 1
                logger.info(f"[ExecutorPoolV2] Created executor for {symbol}")

            return self._executors[symbol]

    # ─────────────────────────────────────────────────────────────
    # Public API: Entry Orders
    # ─────────────────────────────────────────────────────────────

    def execute_entry(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: Optional[str],
        client_order_id: str,
        order_type: str = "LIMIT",
        rate_limit_timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Execute entry order only. NO automatic brackets.

        After this, Runtime should:
        1. Wait for TRADE_EXECUTED
        2. Call BracketService.evaluate()
        3. Call execute_batch() with BracketPlan actions
        """
        self._metrics["entries_routed"] += 1

        # Non-blocking rate limit check (per-symbol aware)
        if not self._rate_limiter.try_acquire(symbol=symbol):
            self._metrics["rate_limit_timeouts"] += 1
            wait_time = self._rate_limiter.get_wait_time(symbol=symbol)
            logger.debug(
                f"[ExecutorPoolV2] Rate limited for {symbol}, retry after {wait_time*1000:.1f}ms")
            return {
                "success": False,
                "error": "Rate limited",
                "symbol": symbol,
                "retry_after_ms": wait_time * 1000,
            }

        # Execute
        executor = self.get_executor(symbol)
        result = executor.execute_entry(
            side=side,
            quantity=quantity,
            price=price,
            client_order_id=client_order_id,
            order_type=order_type,
        )

        return {
            "success": result.success,
            "order_id": result.order_id,
            "client_order_id": result.client_order_id,
            "fill_price": result.fill_price,
            "fill_qty": result.fill_qty,
            "error": result.error,
            "latency_ms": result.latency_ms,
        }

    # ─────────────────────────────────────────────────────────────
    # Public API: Bracket Orders (from BracketPlan)
    # ─────────────────────────────────────────────────────────────

    def execute_bracket(
        self,
        symbol: str,
        action_type: str,
        side: str,
        stop_price: Optional[str] = None,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        rate_limit_timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Execute a single bracket action from BracketPlan.

        Args:
            symbol: Trading symbol
            action_type: "PLACE_SL", "PLACE_TP", or "CANCEL"
            side: Exit side (SELL for LONG, BUY for SHORT)
            stop_price: Stop price for SL/TP
            order_id: Order ID to cancel
            client_order_id: Client order ID
        """
        self._metrics["brackets_routed"] += 1

        # Non-blocking rate limit check (per-symbol aware)
        if not self._rate_limiter.try_acquire(symbol=symbol):
            self._metrics["rate_limit_timeouts"] += 1
            wait_time = self._rate_limiter.get_wait_time(symbol=symbol)
            logger.debug(
                f"[ExecutorPoolV2] Rate limited bracket for {symbol}, retry after {wait_time*1000:.1f}ms")
            return {
                "success": False,
                "error": "Rate limited",
                "symbol": symbol,
                "retry_after_ms": wait_time * 1000,
            }

        # Execute
        executor = self.get_executor(symbol)
        result = executor.execute_bracket(
            action_type=action_type,
            side=side,
            stop_price=stop_price,
            order_id=order_id,
            client_order_id=client_order_id,
        )

        return {
            "success": result.success,
            "order_id": result.order_id,
            "client_order_id": result.client_order_id,
            "error": result.error,
            "latency_ms": result.latency_ms,
        }

    def execute_batch(
        self,
        symbol: str,
        actions: List[Dict[str, Any]],
        rate_limit_timeout: float = 5.0,
    ) -> BatchResult:
        """
        Execute batch of actions from BracketPlan.

        Actions are executed sequentially (CANCEL before PLACE).

        Args:
            symbol: Trading symbol
            actions: List of dicts with action_type, side, stop_price, order_id, client_order_id

        Returns:
            BatchResult with per-action results
        """
        self._metrics["batches_executed"] += 1

        results = []
        errors = []
        start_ts = time.time()

        # Sort: CANCELs first, then PLACEs
        sorted_actions = sorted(
            actions,
            key=lambda a: 0 if a.get("action_type") == "CANCEL" else 1
        )

        for action in sorted_actions:
            result = self.execute_bracket(
                symbol=symbol,
                action_type=action.get("action_type", ""),
                side=action.get("side", ""),
                stop_price=action.get("stop_price"),
                order_id=action.get("order_id"),
                client_order_id=action.get("client_order_id"),
                rate_limit_timeout=rate_limit_timeout,
            )

            results.append(result)
            if not result.get("success"):
                errors.append(result.get("error", "Unknown error"))

        total_latency_ms = (time.time() - start_ts) * 1000

        return BatchResult(
            success=len(errors) == 0,
            results=results,
            errors=errors,
            total_latency_ms=total_latency_ms,
        )

    # ─────────────────────────────────────────────────────────────
    # Public API: Fill Routing
    # ─────────────────────────────────────────────────────────────

    def on_fill(self, symbol: str, fill_price: str, fill_qty: str, order_id: str) -> None:
        """Route fill event to correct executor."""
        with self._lock:
            executor = self._executors.get(symbol)

        if executor:
            executor.on_fill(fill_price, fill_qty, order_id)

    # ─────────────────────────────────────────────────────────────
    # Public API: Status
    # ─────────────────────────────────────────────────────────────

    def is_busy(self, symbol: str) -> bool:
        """Check if specific symbol executor is busy."""
        with self._lock:
            executor = self._executors.get(symbol)
        return executor.is_busy() if executor else False

    def any_busy(self) -> bool:
        """Check if any executor is busy."""
        with self._lock:
            return any(ex.is_busy() for ex in self._executors.values())

    def get_busy_symbols(self) -> List[str]:
        """Get list of symbols with busy executors."""
        with self._lock:
            return [symbol for symbol, ex in self._executors.items() if ex.is_busy()]

    def get_executor_state(self, symbol: str) -> str:
        """Get state of specific executor."""
        with self._lock:
            executor = self._executors.get(symbol)
        return executor.get_state() if executor else "NOT_CREATED"

    def get_metrics(self) -> Dict[str, Any]:
        """Get pool and executor metrics."""
        with self._lock:
            executor_metrics = {
                symbol: ex.get_metrics()
                for symbol, ex in self._executors.items()
            }

        return {
            "pool": {
                **self._metrics,
                "active_executors": len(self._executors),
                "busy_executors": len(self.get_busy_symbols()),
                "rate_limit_wait_time_ms": self._rate_limiter.get_wait_time() * 1000,
            },
            "executors": executor_metrics,
        }

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("[ExecutorPoolV2] Shutting down...")

        with self._lock:
            self._executors.clear()

        logger.info("[ExecutorPoolV2] Shutdown complete")
