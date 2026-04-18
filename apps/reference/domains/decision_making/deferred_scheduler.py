"""Schedule one-shot deferred intent retries on the active asyncio loop.

The scheduler is intentionally narrow: it stores at most one pending retry per
symbol, fires the callback once, and then drops its own handle. It does not own
its own event loop, persist retries, or reschedule repeated defers.
"""

import asyncio
import logging
from typing import Callable, Dict

log = logging.getLogger(__name__)


class DeferredIntentScheduler:
    """Keep one pending deferred retry per symbol on the current event loop."""

    _tombstone_logged: bool = False

    def __init__(self) -> None:
        if not DeferredIntentScheduler._tombstone_logged:
            log.info(
                "TOMBSTONE_HIT module=deferred_scheduler class=DeferredIntentScheduler "
                "reason=instantiated_in_runtime — report to Package-0 audit"
            )
            DeferredIntentScheduler._tombstone_logged = True
        self._tasks: Dict[str, asyncio.TimerHandle] = {}

    def schedule_once(self, symbol: str, when_ts_ms: int, cb: Callable[[str], None]) -> None:
        """Schedule a one-shot retry for ``symbol`` at an absolute epoch-ms time.

        Contract notes:
        - ``when_ts_ms`` is an absolute Unix timestamp in milliseconds, not a
          relative cooldown duration.
        - if a non-cancelled retry is already pending for the same symbol, the
          new request is ignored.
        - if no asyncio loop is running in this thread, the retry is skipped.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.warning(
                "DeferredIntentScheduler: no running event loop, skip scheduling")
            return

        # Use the shared clock abstraction so replay/backtest paths and live
        # paths derive delay from the same timebase contract.
        from apps.reference.core.time import get_clock
        now_ms = get_clock().now_ms()

        # Heuristic: epoch-ms in modern years is ~1.6e12+. Much smaller values likely mean a wrong timebase.
        if when_ts_ms < 1_000_000_000_000:
            log.warning(
                "DeferredIntentScheduler: when_ts_ms=%s looks non-epoch-ms; delay may be wrong",
                when_ts_ms,
            )
        # Past timestamps degrade to immediate execution instead of negative delay.
        delay = max(0.0, (when_ts_ms - now_ms) / 1000.0)

        # Deduplication: if already scheduled and not cancelled - skip
        if symbol in self._tasks and not self._tasks[symbol].cancelled():
            return

        def _fire():
            try:
                cb(symbol)
            finally:
                # Cleanup must happen even if the callback raises so later defers
                # for the same symbol are not blocked forever.
                self._tasks.pop(symbol, None)

        handle = loop.call_later(delay, _fire)
        self._tasks[symbol] = handle
        log.info("Deferred retry scheduled for %s in %.3fs", symbol, delay)

    def cancel(self, symbol: str) -> None:
        """Cancel and forget any pending retry handle for ``symbol``."""
        h = self._tasks.pop(symbol, None)
        if h and not h.cancelled():
            h.cancel()
            log.debug("Cancelled deferred retry for %s", symbol)

    def get_pending_count(self) -> int:
        """Return the number of non-cancelled retry handles still tracked."""
        return len([h for h in self._tasks.values() if not h.cancelled()])
