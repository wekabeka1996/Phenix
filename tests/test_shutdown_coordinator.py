"""
Tests for GracefulShutdownCoordinator.

Verifies:
  1. Stages execute in order (stage N never runs before stage N-1)
  2. A hung component (timeout) does not block the next stage
  3. required=True on a failing stage aborts remaining stages
  4. Async stop_fn is awaited correctly through the event loop
  5. coordinator.run() is idempotent — subsequent calls are no-ops
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from apps.reference.shutdown_coordinator import GracefulShutdownCoordinator, ShutdownStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_coordinator(loop: asyncio.AbstractEventLoop | None = None) -> GracefulShutdownCoordinator:
    return GracefulShutdownCoordinator(loop=loop)


# ---------------------------------------------------------------------------
# Test 1: stages execute strictly in order
# ---------------------------------------------------------------------------

def test_stages_execute_in_order():
    """Components in later stages must not run before earlier stages."""
    call_log: list[str] = []

    def make_fn(name: str):
        def fn():
            call_log.append(name)
        return fn

    coord = make_coordinator()
    coord.add_stage(ShutdownStage("first",  make_fn("first"),  timeout_sec=1.0))
    coord.add_stage(ShutdownStage("second", make_fn("second"), timeout_sec=1.0))
    coord.add_stage(ShutdownStage("third",  make_fn("third"),  timeout_sec=1.0))

    coord.run()

    assert call_log == ["first", "second", "third"], (
        f"Expected sequential execution, got: {call_log}"
    )


# ---------------------------------------------------------------------------
# Test 2: timeout does NOT block the next stage
# ---------------------------------------------------------------------------

def test_timeout_does_not_block_next_stage():
    """If a component hangs, the coordinator skips it after timeout and continues."""
    import time

    call_log: list[str] = []

    def slow_stop():
        time.sleep(10)  # will time out

    def fast_stop():
        call_log.append("fast")

    coord = make_coordinator()
    coord.add_stage(ShutdownStage("slow", slow_stop, timeout_sec=0.05))
    coord.add_stage(ShutdownStage("fast", fast_stop, timeout_sec=1.0))

    t0 = time.monotonic()
    coord.run()
    elapsed = time.monotonic() - t0

    # "fast" must have run despite "slow" timing out
    assert "fast" in call_log, "Stage after timeout must still execute"

    # Total time must be well under the 10-second sleep
    assert elapsed < 5.0, f"Shutdown should not block 10s; took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Test 3: required=True aborts remaining stages on error
# ---------------------------------------------------------------------------

def test_required_stage_aborts_on_error():
    """A required stage that raises must prevent subsequent stages from running."""
    call_log: list[str] = []

    def fail():
        raise RuntimeError("critical failure")

    def should_not_run():
        call_log.append("ran")

    coord = make_coordinator()
    coord.add_stage(ShutdownStage("fail_required", fail, timeout_sec=1.0, required=True))
    coord.add_stage(ShutdownStage("should_skip",   should_not_run, timeout_sec=1.0))

    coord.run()  # must not raise itself

    assert call_log == [], (
        f"Stages after a failed required stage must be skipped, but got: {call_log}"
    )


# ---------------------------------------------------------------------------
# Test 4: async stop_fn is awaited correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_stop_fn_is_awaited():
    """An async stop_fn should be run on the event loop and awaited."""
    called = []

    async def async_stop():
        called.append("async_stop")

    loop = asyncio.get_event_loop()
    coord = make_coordinator(loop=loop)
    coord.add_stage(ShutdownStage("async_component", async_stop, timeout_sec=2.0))

    # run_coroutine_threadsafe requires the loop to be running —
    # use a thread to call coord.run() while we await inside the loop
    import threading
    done_event = threading.Event()

    def run_in_thread():
        coord.run()
        done_event.set()

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    # Give the thread time to submit work and for the loop to process it
    for _ in range(20):
        await asyncio.sleep(0.05)
        if done_event.is_set():
            break

    thread.join(timeout=2.0)
    assert "async_stop" in called, "Async stop_fn must have been called"


# ---------------------------------------------------------------------------
# Test 5: coordinator.run() is idempotent
# ---------------------------------------------------------------------------

def test_run_is_idempotent():
    """Calling run() a second time must not re-execute any stages."""
    call_count = {"n": 0}

    def stop_fn():
        call_count["n"] += 1

    coord = make_coordinator()
    coord.add_stage(ShutdownStage("counter", stop_fn, timeout_sec=1.0))

    coord.run()
    coord.run()  # second call — must be a no-op

    assert call_count["n"] == 1, (
        f"stop_fn must be called exactly once; called {call_count['n']} times"
    )
