"""
Graceful Shutdown Contract — Phase 17.2.

Foundation-level lifecycle management per Constitution audit findings.
Provides ordered startup/shutdown with per-hook timeouts and health aggregation.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Dict, List, Optional

LOG = logging.getLogger(__name__)


class ShutdownPhase(IntEnum):
    """Ordered shutdown phases — lower values shutdown first."""

    INGRESS = 10
    PROCESSING = 20
    PERSISTENCE = 30
    BACKGROUND = 40
    NETWORKING = 50


class LifecycleHook(ABC):
    """Abstract lifecycle hook that domains implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable hook name (e.g. 'ExecPosFSM')."""
        ...

    @property
    @abstractmethod
    def shutdown_phase(self) -> ShutdownPhase:
        """Phase in which this hook should be shut down."""
        ...

    @abstractmethod
    async def shutdown(self, timeout_sec: float = 5.0) -> None:
        """Gracefully shutdown within the given timeout."""
        ...

    async def health_check(self) -> bool:
        """Return True if healthy. Defaults to True."""
        return True

    async def on_startup(self) -> None:
        """Called during startup_all(). Default no-op. Override to initialize."""
        pass


class LifecycleManager:
    """
    Manages ordered startup/shutdown of registered hooks.

    Shutdown proceeds in phase order (INGRESS first, NETWORKING last).
    Idempotent: calling shutdown_all() multiple times is safe.
    """

    def __init__(self) -> None:
        self._hooks: List[LifecycleHook] = []
        self._shutdown_complete: bool = False

    def register(self, hook: LifecycleHook) -> None:
        """Register a lifecycle hook."""
        self._hooks.append(hook)

    @property
    def hooks(self) -> List[LifecycleHook]:
        """Return registered hooks (read-only view)."""
        return list(self._hooks)

    async def shutdown_all(self, timeout_sec: float = 5.0) -> Dict[str, Optional[str]]:
        """
        Shutdown all hooks in phase order.

        Returns dict of {hook_name: None} on success or {hook_name: error_msg} on failure.
        Idempotent: second call returns cached results.
        """
        if self._shutdown_complete:
            return {}

        results: Dict[str, Optional[str]] = {}
        sorted_hooks = sorted(self._hooks, key=lambda h: h.shutdown_phase)

        for hook in sorted_hooks:
            try:
                await asyncio.wait_for(hook.shutdown(timeout_sec), timeout=timeout_sec)
                results[hook.name] = None
                LOG.info(f"Lifecycle: {hook.name} shutdown OK")
            except asyncio.TimeoutError:
                results[hook.name] = f"timeout after {timeout_sec}s"
                LOG.warning(f"Lifecycle: {hook.name} shutdown timed out")
            except Exception as e:
                results[hook.name] = str(e)
                LOG.error(f"Lifecycle: {hook.name} shutdown failed: {e}")

        self._shutdown_complete = True
        return results

    async def health_all(self) -> Dict[str, bool]:
        """Aggregate health from all registered hooks."""
        results: Dict[str, bool] = {}
        for hook in self._hooks:
            try:
                results[hook.name] = await hook.health_check()
            except Exception:
                results[hook.name] = False
        return results

    async def startup_all(self, timeout_sec: float = 5.0) -> List[str]:
        """Start all hooks in reverse shutdown order (NETWORKING first, INGRESS last).

        Blueprint 17.2: on_startup() + startup_all() for ordered startup.

        Returns:
            List of hook names that started successfully.
        """
        sorted_hooks = sorted(self._hooks, key=lambda h: h.shutdown_phase, reverse=True)
        started: List[str] = []
        for hook in sorted_hooks:
            try:
                await asyncio.wait_for(hook.on_startup(), timeout=timeout_sec)
                started.append(hook.name)
                LOG.info(f"Lifecycle: {hook.name} startup OK")
            except asyncio.TimeoutError:
                LOG.warning(f"Lifecycle: {hook.name} startup timed out")
            except Exception as e:
                LOG.error(f"Lifecycle: {hook.name} startup failed: {e}")
        return started
