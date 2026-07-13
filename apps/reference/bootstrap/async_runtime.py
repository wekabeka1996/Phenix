from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")


def _run_async_loop(
    loop: asyncio.AbstractEventLoop,
    ready: threading.Event,
) -> None:
    """Run an asyncio loop in a dedicated thread."""
    asyncio.set_event_loop(loop)
    loop.call_soon(ready.set)
    loop.run_forever()


class AsyncLoopRuntime:
    """Threaded asyncio runtime with thread-safe submit/run/stop APIs."""

    def __init__(self, *, name: str = "AuroraAsyncLoop") -> None:
        self._name = name
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("AsyncLoopRuntime is not started")
        return self._loop

    @property
    def thread(self) -> Optional[threading.Thread]:
        return self._thread

    def start(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None and self._loop.is_running():
            return self._loop
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        thread = threading.Thread(
            target=_run_async_loop,
            args=(loop, ready),
            name=self._name,
            daemon=True,
        )
        self._loop = loop
        self._thread = thread
        thread.start()
        if not ready.wait(timeout=5.0) or not loop.is_running():
            self.stop()
            raise RuntimeError("AsyncLoopRuntime loop failed to start")
        return loop

    def submit(self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        loop = self.loop
        if not loop.is_running():
            raise RuntimeError("AsyncLoopRuntime loop is not running")
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def run(self, coro: Coroutine[Any, Any, T], *, timeout: Optional[float] = None) -> T:
        fut = self.submit(coro)
        return fut.result(timeout=timeout)

    def stop(self, *, timeout: float = 5.0) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=timeout)
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None
            self._thread = None
