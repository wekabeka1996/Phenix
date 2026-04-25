import asyncio
import json
import logging
import threading
import time
import hashlib
from typing import Any, Dict

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.core.retry_scheduler import RetryScheduler


@pytest.fixture
def fsm_mock():
    fsm = MagicMock(spec=FSMCore)
    fsm.emit = MagicMock()
    fsm.emit._emit_compat_mode = "message"
    return fsm


@pytest.fixture
def scheduler(fsm_mock):
    s = RetryScheduler(
        fsm=fsm_mock,
        default_max_attempts=3,
        min_retry_delay_ms=10,
        backoff_factor=1.0,
        jitter_ms=0
    )
    return s


@pytest.mark.asyncio
async def test_full_retry_lifecycle_success(scheduler, fsm_mock):
    """Test full cycle: register -> schedule -> execute -> emit."""
    loop = asyncio.get_running_loop()
    scheduler.bind_loop(loop)

    # original_event must have payload_min
    original_event = {
        "event_name": "EVT:TEST_OPEN",
        "payload_min": {"symbol": "BTCUSDT"},
        "rid": "rid123"
    }

    deferred_payload = {
        "retry_key": "test_key",
        "symbol": "BTCUSDT",
        "original_event": original_event,
        "next_allowed_ts": int(time.time() * 1000) + 10  # 10ms in future
    }

    # Act
    success = scheduler.register_deferred(deferred_payload)
    assert success is True
    assert scheduler.get_pending_count() == 1

    # Wait for retry to trigger
    for _ in range(20):
        if scheduler.get_pending_count() == 0:
            break
        await asyncio.sleep(0.01)

    assert scheduler.get_pending_count() == 0
    fsm_mock.emit.assert_called()
    emitted_msg = fsm_mock.emit.call_args[0][0]
    assert emitted_msg.verb == "TEST_OPEN"


@pytest.mark.asyncio
async def test_register_off_loop_threadsafe(scheduler, fsm_mock):
    """Test registration from another thread via call_soon_threadsafe."""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.is_running.return_value = True
    loop._thread_id = 1111
    scheduler._loop = loop

    with patch("threading.get_ident", return_value=9999):
        payload = {"retry_key": "thread_key", "symbol": "BTC"}
        res = scheduler.register_deferred(payload)
        assert res is True
        loop.call_soon_threadsafe.assert_called_once()


@pytest.mark.asyncio
async def test_retry_task_failure_logging(scheduler, fsm_mock, caplog):
    """Test task failure logging by simulating a failed execution."""
    loop = asyncio.get_running_loop()
    scheduler.bind_loop(loop)

    # We will patch _execute_retry to fail
    with patch.object(scheduler, "_execute_retry", side_effect=RuntimeError("Async Crash")):
        original_event = {"event_name": "EVT:E", "payload_min": {}}
        scheduler.register_deferred({
            "retry_key": "fail_key",
            "original_event": original_event,
            "next_allowed_ts": int(time.time() * 1000)
        })

        # Wait for the task to finish
        for _ in range(20):
            if not scheduler._retry_tasks:
                break
            await asyncio.sleep(0.01)

        assert "RetryScheduler: Task for fail_key failed" in caplog.text
        assert "Async Crash" in caplog.text


@pytest.mark.asyncio
async def test_registration_hash_idempotency(scheduler, fsm_mock):
    """Test that retry count is preserved for same payload, reset for different."""
    loop = asyncio.get_running_loop()
    scheduler.bind_loop(loop)

    payload1 = {
        "retry_key": "key1",
        "symbol": "BTC",
        "original_event": {"event_name": "EVT:X", "payload_min": {"a": 1}}
    }

    # First registration
    scheduler.register_deferred(payload1)
    scheduler._attempts["key1"] = 2  # Manually bump

    # Second registration with SAME payload
    scheduler.register_deferred(payload1)
    assert scheduler._attempts["key1"] == 2  # Preserved

    # Third registration with DIFFERENT payload
    payload2 = {
        "retry_key": "key1",
        "symbol": "BTC",
        # CHANGE
        "original_event": {"event_name": "EVT:X", "payload_min": {"a": 2}}
    }
    scheduler.register_deferred(payload2)
    assert scheduler._attempts["key1"] == 0  # RESET!


@pytest.mark.asyncio
async def test_execute_retry_removes_from_pending(scheduler, fsm_mock):
    """Verify _execute_retry cleans up state even if it drops intent."""
    scheduler._pending["k"] = {
        "max_attempts": 1,
        "original_event": {"event_name": "EVT:X", "payload_min": {}}
    }
    scheduler._attempts["k"] = 1  # 1+1=2 > max_attempts

    await scheduler._execute_retry("k")

    assert "k" not in scheduler._pending
    assert "k" not in scheduler._retry_tasks
    assert "k" not in scheduler._attempts  # CLEANED UP in _execute_retry after drop
