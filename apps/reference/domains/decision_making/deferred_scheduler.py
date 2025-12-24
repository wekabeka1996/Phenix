"""
Deferred Intent Scheduler for QoS

Provides one-time scheduling of deferred intent retries after cooldown periods.
Prevents infinite defer loops by ensuring maximum one retry per symbol.
"""

import asyncio
import logging
import time
from typing import Dict, Callable

log = logging.getLogger(__name__)


class DeferredIntentScheduler:
    """
    Schedules one-time deferred retries for QoS cooldown scenarios.

    Prevents infinite defer loops by deduplicating retries per symbol.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.TimerHandle] = {}

    def schedule_once(self, symbol: str, when_ts_ms: int, cb: Callable[[str], None]) -> None:
        """
        Schedule one deferred retry for a symbol.

        Deduplication: maximum one active retry per symbol. If one exists - skip.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            when_ts_ms: Unix timestamp in milliseconds when to fire
            cb: Callback function that takes symbol as argument
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.warning(
                "DeferredIntentScheduler: no running event loop, skip scheduling")
            return

        # NOTE: `when_ts_ms` is documented as Unix epoch milliseconds.
        # Do NOT use loop.time() here (monotonic seconds); mixing time bases breaks delay calculation.
        now_ms = int(time.time() * 1000)

        # Heuristic: epoch-ms in modern years is ~1.6e12+. Much smaller values likely mean a wrong timebase.
        if when_ts_ms < 1_000_000_000_000:
            log.warning(
                "DeferredIntentScheduler: when_ts_ms=%s looks non-epoch-ms; delay may be wrong",
                when_ts_ms,
            )
        delay = max(0.0, (when_ts_ms - now_ms) / 1000.0)

        # Deduplication: if already scheduled and not cancelled - skip
        if symbol in self._tasks and not self._tasks[symbol].cancelled():
            return

        def _fire():
            try:
                cb(symbol)
            finally:
                self._tasks.pop(symbol, None)

        handle = loop.call_later(delay, _fire)
        self._tasks[symbol] = handle
        log.info("Deferred retry scheduled for %s in %.3fs", symbol, delay)

    def cancel(self, symbol: str) -> None:
        """Cancel any pending retry for the symbol."""
        h = self._tasks.pop(symbol, None)
        if h and not h.cancelled():
            h.cancel()
            log.debug("Cancelled deferred retry for %s", symbol)

    def get_pending_count(self) -> int:
        """Get count of currently pending retries."""
        return len([h for h in self._tasks.values() if not h.cancelled()])
