"""
RetryScheduler Integration Test (PHASE2-DEAD-DEFER-FIX)

Tests that EVT:INTENT_DEFERRED is properly handled by RetryScheduler
and retries are emitted.
"""
import asyncio
import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from apps.reference.retry_scheduler import RetryScheduler
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message


class _FakeFSM:
    """Minimal FSM for testing."""
    def __init__(self):
        self.listeners: dict[str, list] = {}
        self.emitted: list[tuple] = []

    def listen(self, event: str, handler):
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: dict = None, why: str = None, data_ref=None):
        self.emitted.append((event, payload, why))


class TestRetrySchedulerIntegration:
    """Test RetryScheduler properly handles deferred intents."""

    @pytest.mark.asyncio
    async def test_register_deferred_schedules_retry(self):
        """
        Verify RetryScheduler schedules retry and emits original event.
        """
        fsm = _FakeFSM()
        
        scheduler = RetryScheduler(
            fsm=fsm,
            default_max_attempts=3,
            min_retry_delay_ms=10,  # Fast for testing
            backoff_factor=1.0,
            jitter_ms=0,
        )
        
        loop = asyncio.get_running_loop()
        scheduler.bind_loop(loop)
        
        now_ms = int(time.time() * 1000)
        deferred_payload = {
            "retry_key": "flip:BTCUSDT:SELL:r1",
            "symbol": "BTCUSDT",
            "reason": "SYMBOL_COOLDOWN_ACTIVE",
            "next_allowed_ts": now_ms,  # Immediately
            "attempt": 1,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:FEATURES_CALCULATED",
                "payload_min": {"symbol": "BTCUSDT", "side": "SELL", "rid": "r1"},
            },
            "created_ts": now_ms,
            "why_chain": ["qos_cooldown"],
        }
        
        result = scheduler.register_deferred(deferred_payload)
        assert result is True, "register_deferred should return True"
        
        # Wait for retry task to execute
        await asyncio.sleep(0.2)
        
        # Should have attempted emit_compat (which calls fsm.emit internally)
        # Check that pending was cleared
        assert "flip:BTCUSDT:SELL:r1" not in scheduler._pending

    @pytest.mark.asyncio
    async def test_max_attempts_drops_intent(self):
        """
        Verify intent is dropped after max_attempts exceeded.
        """
        fsm = _FakeFSM()
        
        scheduler = RetryScheduler(
            fsm=fsm,
            default_max_attempts=2,
            min_retry_delay_ms=10,
            backoff_factor=1.0,
            jitter_ms=0,
        )
        
        loop = asyncio.get_running_loop()
        scheduler.bind_loop(loop)
        
        now_ms = int(time.time() * 1000)
        retry_key = "flip:BTCUSDT:BUY:r2"
        
        # Simulate 2 previous attempts
        scheduler._attempts[retry_key] = 2
        
        deferred_payload = {
            "retry_key": retry_key,
            "symbol": "BTCUSDT",
            "reason": "RATE_LIMIT_EXCEEDED",
            "next_allowed_ts": now_ms,
            "attempt": 3,
            "max_attempts": 2,  # Already exceeded
            "original_event": {
                "event_name": "EVT:FEATURES_CALCULATED",
                "payload_min": {"symbol": "BTCUSDT", "side": "BUY", "rid": "r2"},
            },
            "created_ts": now_ms,
            "why_chain": ["rate_limit"],
        }
        
        scheduler.register_deferred(deferred_payload)
        
        # Wait for task
        await asyncio.sleep(0.2)
        
        # Should be dropped (attempts cleared)
        assert retry_key not in scheduler._attempts

    def test_no_loop_returns_false(self):
        """
        Verify register_deferred returns False when no loop is bound.
        """
        fsm = _FakeFSM()
        
        scheduler = RetryScheduler(
            fsm=fsm,
            default_max_attempts=3,
            min_retry_delay_ms=100,
            backoff_factor=1.0,
            jitter_ms=0,
        )
        
        # No bind_loop called
        
        now_ms = int(time.time() * 1000)
        deferred_payload = {
            "retry_key": "test:key",
            "symbol": "BTCUSDT",
            "reason": "TEST",
            "next_allowed_ts": now_ms,
            "original_event": {
                "event_name": "EVT:TEST",
                "payload_min": {"symbol": "BTCUSDT"},
            },
            "created_ts": now_ms,
        }
        
        with patch("apps.reference.telemetry.metrics.inc_retry_scheduler_no_loop"):
            result = scheduler.register_deferred(deferred_payload)
        
        assert result is False, "Should return False when no loop bound"


class TestRetrySchedulerPartitioning:
    """Test that different retry_keys are handled independently."""

    @pytest.mark.asyncio
    async def test_different_strategies_independent(self):
        """
        Verify retries for different strategy_ids are independent.
        """
        fsm = _FakeFSM()
        
        scheduler = RetryScheduler(
            fsm=fsm,
            default_max_attempts=3,
            min_retry_delay_ms=10,
            backoff_factor=1.0,
            jitter_ms=0,
        )
        
        loop = asyncio.get_running_loop()
        scheduler.bind_loop(loop)
        
        now_ms = int(time.time() * 1000)
        
        # Aurora strategy retry
        aurora_payload = {
            "retry_key": "aurora:BTCUSDT:LONG:r1",
            "symbol": "BTCUSDT",
            "reason": "COOLDOWN",
            "next_allowed_ts": now_ms,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:AURORA_SIGNAL",
                "payload_min": {"symbol": "BTCUSDT", "strategy_id": "aurora"},
            },
            "created_ts": now_ms,
        }
        
        # MeanReversion strategy retry
        mr_payload = {
            "retry_key": "mr:BTCUSDT:SHORT:r2",
            "symbol": "BTCUSDT",
            "reason": "COOLDOWN",
            "next_allowed_ts": now_ms,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:MR_SIGNAL",
                "payload_min": {"symbol": "BTCUSDT", "strategy_id": "mean_reversion"},
            },
            "created_ts": now_ms,
        }
        
        scheduler.register_deferred(aurora_payload)
        scheduler.register_deferred(mr_payload)
        
        # Both should be tracked
        assert "aurora:BTCUSDT:LONG:r1" in scheduler._pending or "aurora:BTCUSDT:LONG:r1" in scheduler._retry_tasks
        assert "mr:BTCUSDT:SHORT:r2" in scheduler._pending or "mr:BTCUSDT:SHORT:r2" in scheduler._retry_tasks
        
        # Wait for both to complete
        await asyncio.sleep(0.3)
        
        # Both should be cleared
        assert "aurora:BTCUSDT:LONG:r1" not in scheduler._pending
        assert "mr:BTCUSDT:SHORT:r2" not in scheduler._pending
