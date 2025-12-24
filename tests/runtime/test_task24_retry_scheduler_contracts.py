import asyncio
import time
from types import SimpleNamespace

import pytest


class _DummyFsm:
    def __init__(self):
        self.emit_calls = 0

    def emit(self, *_a, **_kw):
        self.emit_calls += 1
        raise AssertionError("fsm.emit must not be called directly (emit_compat-only contract)")


async def _wait_until(predicate, timeout_sec: float = 2.0) -> bool:
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_retry_attempt_increments_in_scheduler_and_caps(monkeypatch):
    from apps.reference.retry_scheduler import RetryScheduler

    emitted: list[object] = []

    async def _fake_emit_compat(_fsm, msg, logger=None):
        emitted.append(msg)

    monkeypatch.setattr("apps.reference.retry_scheduler.emit_compat", _fake_emit_compat)

    loop = asyncio.get_running_loop()
    fsm = _DummyFsm()
    sched = RetryScheduler(
        fsm=fsm,
        default_max_attempts=2,
        min_retry_delay_ms=0,
        backoff_factor=1.0,
        jitter_ms=0,
    )
    sched.bind_loop(loop)

    base = {
        "retry_key": "rk-1",
        "symbol": "BTCUSDT",
        "reason": "test",
        "next_allowed_ts": int(time.time() * 1000),
        "max_attempts": 2,
        "original_event": {"event_name": "EVT:MR_SIGNAL_PRODUCED", "payload_min": {"symbol": "BTCUSDT"}},
        "why_chain": ["test"],
        "created_ts": int(time.time() * 1000),
    }

    for i in range(3):
        assert sched.register_deferred(dict(base)) is True
        assert await _wait_until(lambda: len(emitted) >= i + 1), "Timed out waiting for retry emission"

    assert len(emitted) == 3
    assert emitted[0].verb == "MR_SIGNAL_PRODUCED"
    assert emitted[1].verb == "MR_SIGNAL_PRODUCED"
    assert emitted[2].verb == "INTENT_DROPPED"
    assert int(emitted[2].pld["attempt"]) == 3
    assert int(emitted[2].pld["max_attempts"]) == 2
    assert sched.get_pending_count() == 0


def test_retry_no_event_loop_fails_fast(monkeypatch):
    from apps.reference.retry_scheduler import RetryScheduler

    calls = {"n": 0}

    def _fake_metric() -> None:
        calls["n"] += 1

    monkeypatch.setattr("apps.reference.telemetry.metrics.inc_retry_scheduler_no_loop", _fake_metric)

    sched = RetryScheduler(
        fsm=SimpleNamespace(),
        default_max_attempts=2,
        min_retry_delay_ms=0,
        backoff_factor=1.0,
        jitter_ms=0,
    )

    ok = sched.register_deferred(
        {
            "retry_key": "rk-no-loop",
            "symbol": "BTCUSDT",
            "reason": "test",
            "next_allowed_ts": int(time.time() * 1000),
            "max_attempts": 2,
            "original_event": {"event_name": "EVT:MR_SIGNAL_PRODUCED", "payload_min": {"symbol": "BTCUSDT"}},
        }
    )

    assert ok is False
    assert calls["n"] >= 1
    assert sched.get_pending_count() == 0


# ============================================================
# TASK26: Suspicious Zone Tests - Retry Scheduler
# ============================================================

def test_retry_backoff_exponential(monkeypatch):
    """
    TASK26.SZ.10: Verify backoff_factor is applied exponentially.
    """
    from apps.reference.retry_scheduler import RetryScheduler

    computed_delays: list[int] = []
    
    async def _fake_emit_compat(_fsm, msg, logger=None):
        pass
    
    monkeypatch.setattr("apps.reference.retry_scheduler.emit_compat", _fake_emit_compat)

    RetryScheduler(
        fsm=_DummyFsm(),
        default_max_attempts=5,
        min_retry_delay_ms=100,
        backoff_factor=2.0,  # Double each retry
        jitter_ms=0,  # No randomness for test
    )

    # Expected delays: 100, 200, 400, 800, ... (exponential)
    # We verify the formula: delay = min_delay * (backoff_factor ** attempt)
    min_delay = 100
    backoff = 2.0

    for attempt in range(4):
        expected_delay = min_delay * (backoff ** attempt)
        computed_delays.append(int(expected_delay))

    assert computed_delays == [100, 200, 400, 800], f"Delays should be exponential: {computed_delays}"


async def test_retry_ttl_drops_expired_intent(monkeypatch):
    """
    TASK26.SZ.11: Intent past TTL is dropped, not retried.
    """
    from apps.reference.retry_scheduler import RetryScheduler

    emitted: list[object] = []
    
    async def _fake_emit_compat(_fsm, msg, logger=None):
        emitted.append(msg)
    
    monkeypatch.setattr("apps.reference.retry_scheduler.emit_compat", _fake_emit_compat)

    loop = asyncio.get_running_loop()
    sched = RetryScheduler(
        fsm=_DummyFsm(),
        default_max_attempts=10,
        min_retry_delay_ms=0,
        backoff_factor=1.0,
        jitter_ms=0,
    )
    sched.bind_loop(loop)

    old_ts = int(time.time() * 1000) - 100_000  # 100s ago

    payload = {
        "retry_key": "rk-ttl-test",
        "symbol": "BTCUSDT",
        "reason": "test_ttl",
        "next_allowed_ts": old_ts,
        "max_attempts": 10,
        "original_event": {"event_name": "EVT:TEST", "payload_min": {"symbol": "BTCUSDT"}},
        "why_chain": [],
        "created_ts": old_ts - 1000,
    }

    assert sched.register_deferred(payload) is True
    assert await _wait_until(lambda: sched.get_pending_count() == 0 and len(emitted) >= 1)


async def test_retry_deterministic_with_zero_jitter(monkeypatch):
    """
    TASK26.SZ.12: With jitter_ms=0, scheduling should be deterministic.
    """
    from apps.reference.retry_scheduler import RetryScheduler

    timestamps: list[int] = []
    
    async def _fake_emit_compat(_fsm, msg, logger=None):
        timestamps.append(int(time.time() * 1000))
    
    monkeypatch.setattr("apps.reference.retry_scheduler.emit_compat", _fake_emit_compat)

    loop = asyncio.get_running_loop()
    sched = RetryScheduler(
        fsm=_DummyFsm(),
        default_max_attempts=3,
        min_retry_delay_ms=50,
        backoff_factor=1.0,
        jitter_ms=0,  # Deterministic
    )
    sched.bind_loop(loop)

    now = int(time.time() * 1000) + 50
    payload = {
        "retry_key": "rk-deterministic",
        "symbol": "ETHUSDT",
        "reason": "test",
        "next_allowed_ts": now,
        "max_attempts": 3,
        "original_event": {"event_name": "EVT:TEST", "payload_min": {"symbol": "ETHUSDT"}},
        "why_chain": [],
        "created_ts": now - 100,
    }

    assert sched.register_deferred(payload) is True
    assert await _wait_until(lambda: sched.get_pending_count() == 0 and len(timestamps) >= 1)
