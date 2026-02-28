"""
Async scheduling helpers — Phase 14.2 extraction from fsm.py.

Encapsulates asyncio loop management and background task scheduling
used by ExecPosFSM.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional, TYPE_CHECKING

from apps.reference.utils.accessors import aget

if TYPE_CHECKING:
    pass

LOG = logging.getLogger(__name__)


class AsyncSchedulingMixin:
    """
    Mixin providing async loop and background scheduling for ExecPosFSM.

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
        """Register the shared asyncio loop for guardian/adapter tasks."""
        self._async_loop = loop

    def _get_async_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Resolve the active asyncio loop for scheduling background work."""
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
        """Schedule coroutine on a target loop, thread-safe."""
        target_loop = loop or self._get_async_loop()
        if not target_loop:
            LOG.debug("No asyncio loop available to schedule %r", coro)
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is target_loop:
            target_loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, target_loop)

    def _schedule_guardian_start(self) -> None:
        """Ensure guardian poller and startup reconcile are scheduled once."""
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
        """Start FSM-side cleanup loop respecting unified guardian config."""
        if self._bg_started:
            return
        if not self._orphan_cfg.get("enabled"):
            return
        if not aget(self, "order_guardian", None):
            return
        if self._guardian_unified and not self._fsm_cleanup_enabled:
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
