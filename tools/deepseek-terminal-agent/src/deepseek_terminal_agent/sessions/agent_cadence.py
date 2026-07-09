"""Agent memory refresh cadence and SOS trigger contract/logic."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class SOSEvent(BaseModel):
    """Event schema representing a sharp market-change trigger (SOS)."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    sos_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = Field(..., min_length=1)
    market_snapshot_ref: str = Field(..., min_length=1)
    active: bool = True


def compute_stagger_offset(agent_number: int) -> int:
    """Computes stagger offset in minutes for the given agent number.

    Stagger offset sequence:
      Agent 1: T+00
      Agent 2: T+10
      Agent 3: T+20
      Agent 4: T+30
      Agent 5: T+40
      Agent 6: T+50
    If agent_number is greater than 6, it wraps around.
    """
    if agent_number < 1:
        raise ValueError("agent_number must be >= 1")
    return ((agent_number - 1) % 6) * 10


def compute_next_refresh(
    agent_number: int, session_start: datetime, now: Optional[datetime] = None
) -> datetime:
    """Computes the next scheduled memory refresh datetime for an agent.

    Each agent refreshes every 60 minutes, staggered by their offset.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    offset = compute_stagger_offset(agent_number)
    # Find the smallest k >= 0 such that session_start + offset + k*60 > now
    # and also > session_start (since session_start is start of session, read at T+00)
    k = 0
    while True:
        candidate = session_start + timedelta(minutes=offset + k * 60)
        if candidate > now and candidate > session_start:
            return candidate
        k += 1


def should_refresh(
    now: datetime,
    last_refresh: datetime,
    sos_pending: bool,
    next_scheduled: Optional[datetime] = None,
) -> bool:
    """Determines whether an agent should refresh their shared memory.

    Refresh is forced immediately if an SOS event is pending,
    or if the current time has reached the next scheduled refresh.
    """
    if sos_pending:
        return True

    if next_scheduled is not None:
        return now >= next_scheduled

    # Fallback to simple interval-based comparison if next_scheduled is omitted
    return now >= last_refresh + timedelta(minutes=60)


def create_sos_event(
    agent_id: str,
    reason: str,
    market_snapshot_ref: str,
    timestamp: Optional[datetime] = None,
) -> dict[str, Any]:
    """Creates a dictionary representation of an SOS event."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    event = SOSEvent(
        agent_id=agent_id,
        reason=reason,
        market_snapshot_ref=market_snapshot_ref,
        timestamp=timestamp,
    )
    return event.model_dump()
