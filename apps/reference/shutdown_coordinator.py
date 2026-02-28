"""
GracefulShutdownCoordinator — centralized ordered shutdown for Aurora Core.

Ensures components stop in the correct dependency order so that:
  - No new signals enter the system during shutdown
  - In-flight orders are drained before Guardian is stopped
  - The async event loop closes last, after all components have released it
  - Every stage runs with an explicit timeout; a hung component never blocks the rest

Usage::

    coordinator = GracefulShutdownCoordinator(loop=guardian_loop)
    coordinator.add_stage(
        ShutdownStage("decision_making", decision_making.stop, timeout_sec=3.0),
    ).add_stage(
        ShutdownStage("execution_position", execution_position.stop, timeout_sec=5.0),
    ).add_stage(
        ShutdownStage("guardian_runtime", lambda: guardian_runtime.stop(5.0), timeout_sec=6.0),
    )
    coordinator.run()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

LOG = logging.getLogger(__name__)


@dataclass
class ShutdownStage:
    """Describes a single component's shutdown action.

    Args:
        name:        Human-readable name used in log output.
        stop_fn:     Zero-arg callable that returns None or a coroutine.
                     Both sync and async functions are supported.
        timeout_sec: How long to wait before declaring the stop a timeout.
        required:    If True and the stop_fn raises, subsequent stages are
                     skipped (fail-fast). Use for truly critical teardown.
    """

    name: str
    stop_fn: Callable[[], Any]
    timeout_sec: float = 5.0
    required: bool = False


class GracefulShutdownCoordinator:
    """Runs registered shutdown stages sequentially, components within a
    stage in declaration order. Each stage runs with its own timeout.

    Thread-safety: designed to be called from the main thread while the
    async event loop runs in a background thread (the typical Aurora setup).
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop
        # Each element is a list of ShutdownStage — all run before moving on
        self._stages: list[list[ShutdownStage]] = []
        self._done = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_stage(self, *stages: ShutdownStage) -> "GracefulShutdownCoordinator":
        """Append one group of components as a single shutdown stage.

        All stages in the group are executed in order before the coordinator
        moves to the next stage. Returns self for fluent chaining.
        """
        self._stages.append(list(stages))
        return self

    def run(self) -> None:
        """Execute all registered stages in order.

        Idempotent: subsequent calls after the first are no-ops.
        """
        if self._done:
            LOG.debug("[Shutdown] coordinator.run() called again — skipping (already done)")
            return
        self._done = True

        total = len(self._stages)
        LOG.info("[Shutdown] ══ Starting coordinated shutdown (%d stage(s)) ══", total)
        t0 = time.monotonic()

        for i, stage_group in enumerate(self._stages, start=1):
            names = ", ".join(s.name for s in stage_group)
            LOG.info("[Shutdown] Stage %d/%d → %s", i, total, names)
            try:
                self._run_stage(stage_group)
            except _RequiredStageError as exc:
                LOG.critical(
                    "[Shutdown] Required stage failed — aborting remaining stages. "
                    "Reason: %s", exc
                )
                break

        LOG.info(
            "[Shutdown] ══ All stages complete (%.2fs total) ══",
            time.monotonic() - t0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_stage(self, stage_group: list[ShutdownStage]) -> None:
        for stage in stage_group:
            self._run_one(stage)

    def _run_one(self, stage: ShutdownStage) -> None:
        """Execute one ShutdownStage with a wall-clock timeout.

        The stop_fn is always dispatched to a daemon thread so that
        a blocking sync call cannot stall the coordinator beyond timeout_sec.
        Async coroutines are additionally forwarded to the background event loop.
        """
        import threading

        t0 = time.monotonic()
        label = stage.name
        exc_holder: list[BaseException] = []

        def run_sync():
            try:
                result = stage.stop_fn()
                if asyncio.iscoroutine(result):
                    if self._loop and self._loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(result, self._loop)
                        future.result(timeout=stage.timeout_sec)
                    else:
                        LOG.warning(
                            "[Shutdown] %-35s: coroutine but no running loop — asyncio.run() fallback",
                            label,
                        )
                        asyncio.run(result)
            except Exception as exc:
                exc_holder.append(exc)

        thread = threading.Thread(target=run_sync, daemon=True, name=f"shutdown-{label}")
        thread.start()
        thread.join(timeout=stage.timeout_sec)

        if thread.is_alive():
            LOG.warning(
                "[Shutdown] %-35s TIMEOUT after %.1fs — continuing anyway",
                label, stage.timeout_sec,
            )
            return

        if exc_holder:
            exc = exc_holder[0]
            LOG.error(
                "[Shutdown] %-35s ERROR (%.2fs): %s",
                label, time.monotonic() - t0, exc,
            )
            if stage.required:
                raise _RequiredStageError(f"{label}: {exc}") from exc
            return

        LOG.info("[Shutdown] %-35s OK   (%.2fs)", label, time.monotonic() - t0)



class _RequiredStageError(Exception):
    """Raised internally when a required ShutdownStage fails."""
