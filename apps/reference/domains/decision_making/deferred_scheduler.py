"""
Deferred Intent Scheduler for QoS

Provides one-time scheduling of deferred intent retries after cooldown periods.
Prevents infinite defer loops by ensuring maximum one retry per symbol.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Callable, Union

log = logging.getLogger(__name__)


class DeferredIntentScheduler:
    """
    Schedules one-time deferred retries for QoS cooldown scenarios.

    Prevents infinite defer loops by deduplicating retries per symbol.

    Works in both async and sync contexts:
    - Async: uses asyncio loop.call_later
    - Sync: uses threading.Timer as fallback
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Union[asyncio.TimerHandle, threading.Timer]] = {}
        self._lock = threading.Lock()

    def schedule_once(self, symbol: str, when_ts_ms: int, cb: Callable[[str], None]) -> None:
        """
        Schedule one deferred retry for a symbol.

        Deduplication: maximum one active retry per symbol. If one exists - skip.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            when_ts_ms: Unix timestamp in milliseconds when to fire
            cb: Callback function that takes symbol as argument
        """
        # Calculate delay
        now_ms = int(time.time() * 1000)
        delay_sec = max(0.0, (when_ts_ms - now_ms) / 1000.0)

        with self._lock:
            # Deduplication: if already scheduled - skip
            existing = self._tasks.get(symbol)
            if existing is not None:
                # Check if timer/handle is still active
                if isinstance(existing, threading.Timer):
                    if existing.is_alive():
                        return
                elif isinstance(existing, asyncio.TimerHandle):
                    if not existing.cancelled():
                        return

            # Try async first, fallback to threading.Timer
            try:
                loop = asyncio.get_running_loop()
                self._schedule_async(symbol, delay_sec, cb, loop)
            except RuntimeError:
                # No running event loop - use threading.Timer
                self._schedule_sync(symbol, delay_sec, cb)

    def _schedule_async(self, symbol: str, delay_sec: float, cb: Callable[[str], None], loop: asyncio.AbstractEventLoop) -> None:
        """Schedule using asyncio (preferred when event loop available)."""
        def _fire():
            try:
                cb(symbol)
            finally:
                with self._lock:
                    self._tasks.pop(symbol, None)

        handle = loop.call_later(delay_sec, _fire)
        self._tasks[symbol] = handle
        log.info("Deferred retry scheduled (async) for %s in %.3fs", symbol, delay_sec)

    def _schedule_sync(self, symbol: str, delay_sec: float, cb: Callable[[str], None]) -> None:
        """Schedule using threading.Timer (fallback for sync context)."""
        def _fire():
            try:
                cb(symbol)
            finally:
                with self._lock:
                    self._tasks.pop(symbol, None)

        timer = threading.Timer(delay_sec, _fire)
        timer.daemon = True  # Don't block shutdown
        timer.start()
        self._tasks[symbol] = timer
        log.info("Deferred retry scheduled (sync/timer) for %s in %.3fs", symbol, delay_sec)

    def cancel(self, symbol: str) -> None:
        """Cancel any pending retry for the symbol."""
        with self._lock:
            task = self._tasks.pop(symbol, None)
            if task is None:
                return

            if isinstance(task, threading.Timer):
                task.cancel()
            elif isinstance(task, asyncio.TimerHandle) and not task.cancelled():
                task.cancel()

            log.debug("Cancelled deferred retry for %s", symbol)

    def get_pending_count(self) -> int:
        """Get count of currently pending retries."""
        with self._lock:
            count = 0
            for task in self._tasks.values():
                if isinstance(task, threading.Timer):
                    if task.is_alive():
                        count += 1
                elif isinstance(task, asyncio.TimerHandle):
                    if not task.cancelled():
                        count += 1
            return count

    def shutdown(self) -> None:
        """Cancel all pending timers. Call on application shutdown."""
        with self._lock:
            for symbol, task in list(self._tasks.items()):
                if isinstance(task, threading.Timer):
                    task.cancel()
                elif isinstance(task, asyncio.TimerHandle) and not task.cancelled():
                    task.cancel()
            self._tasks.clear()
            log.info("DeferredIntentScheduler shutdown complete")
