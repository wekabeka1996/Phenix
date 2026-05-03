"""Async scheduling helpers for execution-position background work.

The mixin owns loop discovery and one-way scheduling for guardian and cleanup
tasks. It does not manage task shutdown or result propagation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional

from apps.reference.utils.accessors import aget

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.async_scheduling"
)


class AsyncSchedulingMixin:
    """Mixin providing async loop discovery and fire-and-forget scheduling.

    Expects:
        self._async_loop: Optional[asyncio.AbstractEventLoop]
        self._guardian_start_scheduled: bool
        self._bg_started: bool
        self._orphan_cfg: dict
        self._guardian_unified: bool
        self._fsm_cleanup_enabled: bool
        self._fsm_cleanup_logged: bool
        self.order_guardian: (optional)
    """

    _async_loop: Optional[asyncio.AbstractEventLoop]

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the shared asyncio loop for guardian and cleanup tasks."""
        self._async_loop = loop

    def _get_async_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Resolve the loop to use for background scheduling.

        Preference order is: explicitly injected shared loop, otherwise the
        currently running loop in the calling thread.
        """
        loop = self._async_loop
        if loop and not loop.is_closed():
            return loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _submit_async(
        self,
        coro: Coroutine[Any, Any, Any],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Schedule ``coro`` on the target loop.

        The coroutine object is owned by this helper: if no usable loop is
        available it is closed immediately to avoid ``RuntimeWarning: coroutine
        was never awaited`` leaks in deferred or shutdown paths.
        """
        target_loop = loop or self._get_async_loop()
        if not target_loop:
            LOG.debug("No asyncio loop available to schedule %r", coro)
            coro.close()
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        # Use create_task only when already on the target loop; cross-thread
        # scheduling must go through run_coroutine_threadsafe.
        if running_loop is target_loop:
            target_loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, target_loop)

    def _schedule_guardian_start(self) -> None:
        """Schedule guardian start/reconcile once the async runtime is ready."""
        if self._guardian_start_scheduled:
            return
        guardian = aget(self, "order_guardian", None)
        if not guardian:
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("OrderGuardian start deferred: no event loop active")
            return

        self._submit_async(guardian.start(), loop)
        self._submit_async(self._startup_order_guardian_reconcile(), loop)
        LOG.info("OrderGuardian background tasks scheduled")
        self._guardian_start_scheduled = True

    def _schedule_fsm_cleanup_loop(self) -> None:
        """Start the FSM-side cleanup loop if this FSM still owns that duty."""
        if self._bg_started:
            return
        if not self._orphan_cfg.get("enabled"):
            return
        if not aget(self, "order_guardian", None):
            return
        if self._guardian_unified and not self._fsm_cleanup_enabled:
            # Unified guardian mode centralizes cleanup ownership outside this
            # FSM; the one-shot log avoids repeating the same startup reason.
            if not self._fsm_cleanup_logged:
                LOG.info("[FSM-CLEANUP] disabled_by_config (unified=true)")
                self._fsm_cleanup_logged = True
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("FSM cleanup start deferred: no event loop active")
            return

        self._submit_async(self._cleanup_loop(), loop)
        self._bg_started = True
