"""
Async Manager for Shadow ExecPos
================================

Provides event loop resolution for the ExecPos domain.
This is a minimal utility class - runtime manages its own tasks directly.
"""
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ExecPosAsyncManager:
    """
    Minimal async loop manager for ExecPos domain.

    Responsibility:
    - Holding and resolving the reference to the active event loop.

    Note: Task tracking and lifecycle management is handled by the runtime itself,
    not by this manager. This keeps the design simple and avoids duplication.
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the shared asyncio loop."""
        self._loop = loop

    def get_async_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Resolve the active asyncio loop.

        Resolution order:
        1. Explicitly set loop (if not closed)
        2. Currently running loop
        3. Default event loop (for test environments)

        Returns:
            The active event loop, or None if unavailable.
        """
        if self._loop and not self._loop.is_closed():
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # Fallback for test environments or thread-based loops
            try:
                return asyncio.get_event_loop()
            except Exception:
                return None

    def clear(self) -> None:
        """Clear the stored loop reference."""
        self._loop = None
