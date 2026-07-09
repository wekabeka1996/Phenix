diff --git a/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py
new file mode 100644
index 00000000..8db6770f
--- /dev/null
+++ b/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py
@@ -0,0 +1,99 @@
+"""Bounded CLI timer runner contract and iteration loop."""
+from __future__ import annotations
+
+import logging
+import time
+from datetime import datetime, timezone
+from typing import Any, Callable, Literal, Optional
+from pydantic import BaseModel, ConfigDict, Field
+
+logger = logging.getLogger(__name__)
+
+
+class TimerTick(BaseModel):
+    """Data model representing a single inspectable timer wakeup event."""
+    model_config = ConfigDict(extra="forbid")
+
+    schema_version: int = 1
+    agent_id: str = Field(..., min_length=1)
+    agent_number: int = Field(..., ge=1)
+    scheduled_at: datetime
+    woke_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
+    reason: Literal["scheduled", "sos", "manual"]
+    context_version: Optional[int] = None
+
+
+def compute_sleep_seconds(
+    now: datetime, next_scheduled: datetime, max_sleep_seconds: float
+) -> float:
+    """Computes sleep time in seconds to the next scheduled event, capped at max_sleep_seconds."""
+    if max_sleep_seconds < 0:
+        raise ValueError("max_sleep_seconds must be >= 0")
+    
+    diff = (next_scheduled - now).total_seconds()
+    return max(0.0, min(diff, max_sleep_seconds))
+
+
+def make_timer_tick(
+    agent_id: str,
+    agent_number: int,
+    scheduled_at: datetime,
+    woke_at: datetime,
+    reason: Literal["scheduled", "sos", "manual"],
+    context_version: Optional[int] = None,
+) -> TimerTick:
+    """Creates an inspectable TimerTick instance."""
+    return TimerTick(
+        agent_id=agent_id,
+        agent_number=agent_number,
+        scheduled_at=scheduled_at,
+        woke_at=woke_at,
+        reason=reason,
+        context_version=context_version,
+    )
+
+
+def should_stop(
+    started_at: datetime,
+    now: datetime,
+    max_runtime_seconds: Optional[float],
+    max_iterations: Optional[int],
+    iteration_count: int,
+) -> bool:
+    """Determines whether the loop should terminate based on runtime and iteration constraints."""
+    if max_iterations is not None and iteration_count >= max_iterations:
+        return True
+    
+    if max_runtime_seconds is not None:
+        elapsed = (now - started_at).total_seconds()
+        if elapsed >= max_runtime_seconds:
+            return True
+            
+    return False
+
+
+def run_bounded_timer_loop(
+    callback: Callable[[int], Any],
+    max_iterations: Optional[int] = None,
+    max_runtime_seconds: Optional[float] = None,
+    sleep_func: Callable[[float], None] = time.sleep,
+    clock_func: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
+) -> int:
+    """Runs a bounded timer loop executing the callback at each tick.
+
+    The loop terminates safely when runtime or iteration limits are met.
+    """
+    started_at = clock_func()
+    iteration_count = 0
+
+    logger.info(
+        "Starting bounded timer loop: max_iterations=%s, max_runtime_seconds=%s",
+        max_iterations,
+        max_runtime_seconds,
+    )
+
+    while True:
+        now = clock_func()
+        if should_stop(started_at, now, max_runtime_seconds, max_iterations, iteration_count):
+            break
+
+        # Execute step callback
+        callback(iteration_count)
+        iteration_count += 1
+
+        # Check conditions again before sleeping
+        now_after = clock_func()
+        if should_stop(started_at, now_after, max_runtime_seconds, max_iterations, iteration_count):
+            break
+
+        # Bounded tick sleep to yield control
+        sleep_func(0.01)
+
+    logger.info("Bounded timer loop completed. Iterations run: %d", iteration_count)
+    return iteration_count
+diff --git a/tools/deepseek-terminal-agent/tests/test_agent_timer_runner.py b/tools/deepseek-terminal-agent/tests/test_agent_timer_runner.py
new file mode 100644
index 00000000..6ac8c8f7
--- /dev/null
+++ b/tools/deepseek-terminal-agent/tests/test_agent_timer_runner.py
@@ -0,0 +1,139 @@
+from datetime import datetime, timezone, timedelta
+import pytest
+from pydantic import ValidationError
+
+from deepseek_terminal_agent.sessions.agent_timer_runner import (
+    TimerTick,
+    compute_sleep_seconds,
+    make_timer_tick,
+    should_stop,
+    run_bounded_timer_loop,
+)
+from deepseek_terminal_agent.sessions.agent_cadence import should_refresh
+
+
+def test_timer_tick_model():
+    scheduled = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+    woke = datetime(2026, 7, 9, 12, 0, 1, tzinfo=timezone.utc)
+
+    # Valid tick creation
+    tick = make_timer_tick(
+        agent_id="agent-6",
+        agent_number=6,
+        scheduled_at=scheduled,
+        woke_at=woke,
+        reason="scheduled",
+        context_version=42,
+    )
+    assert tick.agent_id == "agent-6"
+    assert tick.agent_number == 6
+    assert tick.reason == "scheduled"
+    assert tick.context_version == 42
+
+    # Validation errors on invalid schemas
+    with pytest.raises(ValidationError):
+        TimerTick(
+            agent_id="",
+            agent_number=0,  # ge=1 constraint
+            scheduled_at=scheduled,
+            reason="scheduled",
+        )
+    with pytest.raises(ValidationError):
+        # Prohibits extra attributes
+        TimerTick(
+            agent_id="agent-6",
+            agent_number=6,
+            scheduled_at=scheduled,
+            reason="scheduled",
+            extra_field="forbidden",
+        )
+
+
+def test_compute_sleep_seconds():
+    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+
+    # Normal sleep (next is 30s away, cap is 60s -> sleep 30s)
+    next_sched = now + timedelta(seconds=30)
+    assert compute_sleep_seconds(now, next_sched, 60.0) == 30.0
+
+    # Capped sleep (next is 120s away, cap is 60s -> sleep 60s)
+    next_sched_far = now + timedelta(seconds=120)
+    assert compute_sleep_seconds(now, next_sched_far, 60.0) == 60.0
+
+    # Instant return if next is in past
+    next_sched_past = now - timedelta(seconds=10)
+    assert compute_sleep_seconds(now, next_sched_past, 60.0) == 0.0
+
+    # Error handling
+    with pytest.raises(ValueError):
+        compute_sleep_seconds(now, next_sched, -10.0)
+
+
+def test_should_stop():
+    started = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+
+    # 1. No limits -> should not stop
+    assert should_stop(started, started + timedelta(seconds=10), None, None, 5) is False
+
+    # 2. Iteration limit reached
+    assert should_stop(started, started + timedelta(seconds=10), None, 5, 5) is True
+    assert should_stop(started, started + timedelta(seconds=10), None, 5, 4) is False
+
+    # 3. Runtime limit reached
+    assert should_stop(started, started + timedelta(seconds=10), 10.0, None, 1) is True
+    assert should_stop(started, started + timedelta(seconds=9), 10.0, None, 1) is False
+
+
+def test_bounded_loop_termination():
+    call_counts = []
+    
+    def callback(iteration):
+        call_counts.append(iteration)
+
+    # Termination via max iterations
+    total_runs = run_bounded_timer_loop(
+        callback=callback,
+        max_iterations=3,
+        max_runtime_seconds=None,
+        sleep_func=lambda s: None,  # instantly run
+    )
+    assert total_runs == 3
+    assert call_counts == [0, 1, 2]
+
+    # Termination via max runtime seconds using a mocked clock
+    current_time = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+    clock_tick_calls = 0
+
+    def mock_clock():
+        nonlocal current_time, clock_tick_calls
+        # advance clock by 5 seconds on each call
+        current_time += timedelta(seconds=5)
+        clock_tick_calls += 1
+        return current_time
+
+    loop_runs = run_bounded_timer_loop(
+        callback=lambda it: None,
+        max_iterations=100,  # high count
+        max_runtime_seconds=15.0,  # terminates after clock advances past 15s
+        sleep_func=lambda s: None,
+        clock_func=mock_clock,
+    )
+    # Loop should stop once elapsed time >= 15 seconds
+    # Start: clock = 12:00:05 (first read at started_at)
+    # Iteration 0: now = 12:00:10. should_stop check: elapsed = 5s. Runs.
+    # Iteration 1: now = 12:00:20. should_stop check: elapsed = 15s >= 15s limit. Stops.
+    assert loop_runs == 1
+
+
+def test_sos_interruption_scenario():
+    # Demonstrates that should_refresh will evaluate True if SOS is pending,
+    # overriding any scheduled interval delays.
+    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
+    last = now - timedelta(minutes=5)  # refreshed 5 mins ago
+    next_sched = now + timedelta(minutes=55)  # 55 mins in future
+
+    # Scheduled refresh is not due, and no SOS -> should not refresh
+    assert should_refresh(now, last, sos_pending=False, next_scheduled=next_sched) is False
+
+    # SOS pending -> forces immediate refresh
+    assert should_refresh(now, last, sos_pending=True, next_scheduled=next_sched) is True
+
