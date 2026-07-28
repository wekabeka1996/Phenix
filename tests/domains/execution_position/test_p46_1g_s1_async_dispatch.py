from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future

import pytest

from apps.reference.bootstrap.async_runtime import AsyncLoopRuntime
from apps.reference.domains.execution_position.adapters.async_scheduling import (
    AsyncDispatchUnavailableError,
    AsyncSchedulingMixin,
)


class SchedulingProbe(AsyncSchedulingMixin):
    def __init__(self) -> None:
        self._async_loop = None


async def _record_call(calls: list[str], called: threading.Event) -> None:
    calls.append(threading.current_thread().name)
    called.set()


async def _add_numbers(a: int, b: int) -> int:
    return a + b


async def _raising_coro() -> None:
    raise ValueError("dispatch_failed_deliberately")


def test_1_canonical_runtime_starts_and_exposes_running_loop() -> None:
    runtime = AsyncLoopRuntime(name="P46S1CanonicalLoop")
    loop = runtime.start()
    try:
        assert loop.is_running() is True
        assert runtime.loop is loop
        assert runtime.thread is not None
        assert runtime.thread.name == "P46S1CanonicalLoop"
        assert runtime.thread.is_alive() is True
    finally:
        runtime.stop()


def test_2_production_fsm_receives_exact_canonical_loop() -> None:
    runtime = AsyncLoopRuntime(name="P46S1CanonicalLoop")
    loop = runtime.start()
    probe = SchedulingProbe()
    probe.set_async_loop(loop)
    try:
        assert probe._get_async_loop() is loop
    finally:
        runtime.stop()


def test_3_worker_thread_dispatch_uses_one_canonical_loop() -> None:
    runtime = AsyncLoopRuntime(name="P46S1CanonicalLoop")
    loop = runtime.start()
    probe = SchedulingProbe()
    probe.set_async_loop(loop)
    calls: list[str] = []
    called = threading.Event()

    try:
        future = probe._submit_async(_record_call(calls, called))
        assert isinstance(future, Future)
        assert future.result(timeout=2.0) is None
        assert called.is_set() is True
        assert calls == ["P46S1CanonicalLoop"]
        assert probe._get_async_loop() is loop
    finally:
        runtime.stop()


@pytest.mark.asyncio
async def test_4_dispatch_from_canonical_loop_creates_one_task() -> None:
    probe = SchedulingProbe()
    loop = asyncio.get_running_loop()
    probe.set_async_loop(loop)
    calls: list[str] = []
    called = threading.Event()

    task = probe._submit_async(_record_call(calls, called))
    assert isinstance(task, asyncio.Task)
    await task

    assert called.is_set() is True
    assert len(calls) == 1


def test_5_result_and_exception_are_observable() -> None:
    runtime = AsyncLoopRuntime(name="P46S1ObservableLoop")
    loop = runtime.start()
    probe = SchedulingProbe()
    probe.set_async_loop(loop)

    try:
        fut1 = probe._submit_async(_add_numbers(10, 32))
        assert isinstance(fut1, Future)
        assert fut1.result(timeout=2.0) == 42

        fut2 = probe._submit_async(_raising_coro())
        assert isinstance(fut2, Future)
        with pytest.raises(ValueError, match="dispatch_failed_deliberately"):
            fut2.result(timeout=2.0)
    finally:
        runtime.stop()


def test_6_missing_loop_raises_typed_fail_closed_error() -> None:
    probe = SchedulingProbe()
    calls: list[str] = []
    called = threading.Event()

    with pytest.raises(
        AsyncDispatchUnavailableError,
        match="canonical async loop is unavailable",
    ):
        probe._submit_async(_record_call(calls, called))

    assert calls == []
    assert not called.is_set()


def test_7_unready_and_stopped_loop_registration_fails_closed() -> None:
    runtime = AsyncLoopRuntime(name="P46S1StoppedLoop")
    loop = runtime.start()
    runtime.stop()
    probe = SchedulingProbe()

    with pytest.raises(
        AsyncDispatchUnavailableError,
        match="canonical async loop must be running before registration",
    ):
        probe.set_async_loop(loop)

    assert probe._get_async_loop() is None


def test_8_stopped_and_closed_loop_dispatch_fails_closed() -> None:
    runtime = AsyncLoopRuntime(name="P46S1DispatchClosedLoop")
    loop = runtime.start()
    probe = SchedulingProbe()
    probe._async_loop = loop
    runtime.stop()

    calls: list[str] = []
    called = threading.Event()

    with pytest.raises(
        AsyncDispatchUnavailableError,
        match="canonical async loop is unavailable",
    ):
        probe._submit_async(_record_call(calls, called))

    assert calls == []
    assert not called.is_set()


def test_9_coroutine_is_not_silently_dropped() -> None:
    probe = SchedulingProbe()
    calls: list[str] = []
    called = threading.Event()

    raised = False
    try:
        probe._submit_async(_record_call(calls, called))
    except AsyncDispatchUnavailableError:
        raised = True

    assert raised is True
    assert len(calls) == 0
    assert not called.is_set()


def test_10_shutdown_leaves_no_thread_running() -> None:
    runtime = AsyncLoopRuntime(name="P46S1ShutdownLoop")
    loop = runtime.start()
    thread = runtime.thread
    assert thread is not None
    assert thread.is_alive() is True

    runtime.stop()
    assert thread.is_alive() is False
    assert runtime._loop is None
    assert runtime._thread is None
