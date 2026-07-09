"""Bounded CLI timer runner contract and iteration loop."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TimerTick(BaseModel):
    """Data model representing a single inspectable timer wakeup event."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    scheduled_at: datetime
    woke_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Literal["scheduled", "sos", "manual"]
    context_version: Optional[int] = None


def compute_sleep_seconds(
    now: datetime, next_scheduled: datetime, max_sleep_seconds: float
) -> float:
    """Computes sleep time in seconds to the next scheduled event, capped at max_sleep_seconds."""
    if max_sleep_seconds < 0:
        raise ValueError("max_sleep_seconds must be >= 0")
    
    diff = (next_scheduled - now).total_seconds()
    return max(0.0, min(diff, max_sleep_seconds))


def make_timer_tick(
    agent_id: str,
    agent_number: int,
    scheduled_at: datetime,
    woke_at: datetime,
    reason: Literal["scheduled", "sos", "manual"],
    context_version: Optional[int] = None,
) -> TimerTick:
    """Creates an inspectable TimerTick instance."""
    return TimerTick(
        agent_id=agent_id,
        agent_number=agent_number,
        scheduled_at=scheduled_at,
        woke_at=woke_at,
        reason=reason,
        context_version=context_version,
    )


def should_stop(
    started_at: datetime,
    now: datetime,
    max_runtime_seconds: Optional[float],
    max_iterations: Optional[int],
    iteration_count: int,
) -> bool:
    """Determines whether the loop should terminate based on runtime and iteration constraints."""
    if max_iterations is not None and iteration_count >= max_iterations:
        return True
    
    if max_runtime_seconds is not None:
        elapsed = (now - started_at).total_seconds()
        if elapsed >= max_runtime_seconds:
            return True
            
    return False


def run_bounded_timer_loop(
    callback: Callable[[int], Any],
    max_iterations: Optional[int] = None,
    max_runtime_seconds: Optional[float] = None,
    sleep_func: Callable[[float], None] = time.sleep,
    clock_func: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    """Runs a bounded timer loop executing the callback at each tick.

    The loop terminates safely when runtime or iteration limits are met.
    """
    started_at = clock_func()
    iteration_count = 0

    logger.info(
        "Starting bounded timer loop: max_iterations=%s, max_runtime_seconds=%s",
        max_iterations,
        max_runtime_seconds,
    )

    while True:
        now = clock_func()
        if should_stop(started_at, now, max_runtime_seconds, max_iterations, iteration_count):
            break

        # Execute step callback
        callback(iteration_count)
        iteration_count += 1

        # Check conditions again before sleeping
        now_after = clock_func()
        if should_stop(started_at, now_after, max_runtime_seconds, max_iterations, iteration_count):
            break

        # Bounded tick sleep to yield control
        sleep_func(0.01)

    logger.info("Bounded timer loop completed. Iterations run: %d", iteration_count)
    return iteration_count
