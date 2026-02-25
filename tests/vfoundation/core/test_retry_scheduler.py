import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable

import pytest
from unittest.mock import MagicMock, patch

from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.core.retry_scheduler import RetryScheduler


@pytest.fixture
def fsm_mock():
    fsm = MagicMock(spec=FSMCore)
    return fsm


@pytest.fixture
def logger_mock():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def on_no_loop_mock():
    return MagicMock(spec=Callable[[], None])


def test_init_valid(fsm_mock, logger_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, logger=logger_mock)
    assert scheduler.default_max_attempts == 5
    assert scheduler.min_retry_delay_ms == 500
    assert scheduler.backoff_factor == 2.0
    assert scheduler.jitter_ms == 0
    assert scheduler._pending == {}
    assert scheduler._attempts == {}
    assert scheduler._loop is None


def test_init_invalid_backoff(fsm_mock):
    with pytest.raises(ValueError, match="must be >= 1.0"):
        RetryScheduler(fsm=fsm_mock, backoff_factor=0.5)


def test_init_invalid_jitter(fsm_mock):
    with pytest.raises(ValueError, match="must be >= 0"):
        RetryScheduler(fsm=fsm_mock, jitter_ms=-10)


def test_bind_loop_not_running(fsm_mock, on_no_loop_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, on_no_loop=on_no_loop_mock)
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.is_running.return_value = False
    
    with pytest.raises(RuntimeError, match="requires a running asyncio loop"):
        scheduler.bind_loop(loop)
        
    on_no_loop_mock.assert_called_once()


def test_register_deferred_no_loop(fsm_mock, on_no_loop_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, on_no_loop=on_no_loop_mock)
    
    result = scheduler.register_deferred({"retry_key": "test"})
    assert result is False
    on_no_loop_mock.assert_called_once()


def test_register_deferred_missing_key(fsm_mock, logger_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, logger=logger_mock)
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.is_running.return_value = True
    loop._thread_id = threading.get_ident()
    scheduler._loop = loop
    
    result = scheduler.register_deferred({"symbol": "BTC"})
    assert result is False
    logger_mock.warning.assert_called_with(
        "RetryScheduler: deferred_payload missing retry_key, ignoring"
    )


def test_register_deferred_missing_original_event(fsm_mock, logger_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, logger=logger_mock)
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.is_running.return_value = True
    loop._thread_id = threading.get_ident()
    scheduler._loop = loop
    
    result = scheduler.register_deferred({"retry_key": "test1"})
    assert result is False
    logger_mock.warning.assert_called_with(
        "RetryScheduler: deferred_payload missing/invalid original_event for %s", "test1"
    )


def test_get_pending_count(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    scheduler._pending = {"k1": {}, "k2": {}}
    assert scheduler.get_pending_count() == 2


def test_get_pending_for_symbol(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    scheduler._pending = {
        "k1": {"symbol": "BTCUSDT"},
        "k2": {"symbol": "ETHUSDT"},
        "k3": {"symbol": "BTCUSDT"},
    }
    assert set(scheduler.get_pending_for_symbol("BTCUSDT")) == {"k1", "k3"}
    assert scheduler.get_pending_for_symbol("SOLUSDT") == []


def test_cancel_pending_existing(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    task_mock = MagicMock(spec=asyncio.Task)
    task_mock.done.return_value = False
    scheduler._pending = {"k1": {"symbol": "BTCUSDT"}}
    scheduler._retry_tasks = {"k1": task_mock}
    
    result = scheduler.cancel_pending("k1")
    assert result is True
    assert "k1" not in scheduler._pending
    task_mock.cancel.assert_called_once()


def test_cancel_pending_missing(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    assert scheduler.cancel_pending("missing") is False


def test_clear_all_pending(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    task1 = MagicMock(spec=asyncio.Task)
    task1.done.return_value = False
    task2 = MagicMock(spec=asyncio.Task)
    task2.done.return_value = False
    scheduler._pending = {
        "k1": {"symbol": "BTCUSDT", "retry_key": "k1", "original_event": {}},
        "k2": {"symbol": "ETHUSDT", "retry_key": "k2", "original_event": {}},
    }
    scheduler._retry_tasks = {"k1": task1, "k2": task2}
    
    count = scheduler.clear_all_pending(emit_dropped=False)
    assert count == 2
    assert scheduler._pending == {}
    assert scheduler._retry_tasks == {}
    task1.cancel.assert_called_once()
    task2.cancel.assert_called_once()

@pytest.mark.asyncio
async def test_execute_retry_success(fsm_mock):
    scheduler = RetryScheduler(fsm=fsm_mock)
    
    # Mock internal state
    scheduler._pending = {
        "k1": {
            "retry_key": "k1",
            "symbol": "BTC",
            "reason": "test",
            "original_event": {
                "event_name": "EVT:TEST",
                "payload": {"data": 123},
                "why": "why1",
                "data_ref": []
            }
        }
    }
    scheduler._attempts = {"k1": 1}
    
    # Run _execute_retry directly
    await scheduler._execute_retry("k1")
    
    # Should be removed from pending after successful execute
    assert "k1" not in scheduler._pending
    # Should emit compat
    fsm_mock.emit.assert_called_once()
    
@pytest.mark.asyncio
async def test_execute_retry_max_attempts_reached(fsm_mock, logger_mock):
    scheduler = RetryScheduler(fsm=fsm_mock, logger=logger_mock, default_max_attempts=2)
    
    scheduler._pending = {
        "k1": {
            "retry_key": "k1",
            "symbol": "BTC",
            "reason": "test",
            "max_attempts": 2,
            "original_event": {"event_name": "EVT:TEST"}
        }
    }
    scheduler._attempts = {"k1": 2}
    
    await scheduler._execute_retry("k1")
    
    assert "k1" not in scheduler._pending
    logger_mock.warning.assert_called_with("RetryScheduler: Dropping %s (reason=%s, attempts=%d/%d)", "k1", "MAX_ATTEMPTS_EXCEEDED", 3, 2)
    # Dropped intent should be emitted
    assert fsm_mock.emit.call_count == 1
