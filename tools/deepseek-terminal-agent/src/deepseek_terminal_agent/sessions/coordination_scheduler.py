"""Caller-driven scheduler for P41X agent coordination cycles."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .collective_memory import CollectiveMemoryStore
from .coordination_config import CoordinationConfig


SchedulerTask = Literal[
    "market_refresh",
    "agent_heartbeat",
    "collective_sync",
    "tactical_analysis",
    "decision_review",
    "portfolio_reconciliation",
    "reflection",
    "memory_checkpoint",
    "instruction_manifest_refresh",
]


class SchedulerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: SchedulerTask
    due: bool
    reason: Literal["cadence", "event", "not_due"]
    evaluated_at: str
    next_due_at: str


class CoordinationScheduler:
    """Computes deterministic due work; callers own the actual runtime loop."""

    def __init__(self, config: CoordinationConfig, store: CollectiveMemoryStore) -> None:
        self.config = config
        self.store = store

    def due_tasks(
        self,
        *,
        last_run_at: dict[str, str],
        now: Optional[datetime] = None,
        event_wakeup: Optional[str] = None,
    ) -> list[SchedulerDecision]:
        resolved = self._as_utc(now)
        wake_tasks = set(self.config.timers.event_wakeups.get(event_wakeup or "", []))
        decisions: list[SchedulerDecision] = []
        for task, cadence in self._cadences().items():
            previous_raw = last_run_at.get(task)
            previous = self._parse(previous_raw) if previous_raw else None
            next_due = (previous + timedelta(seconds=cadence)) if previous else resolved
            event_due = task in wake_tasks
            cadence_due = previous is None or resolved >= next_due
            reason = "event" if event_due else ("cadence" if cadence_due else "not_due")
            decisions.append(
                SchedulerDecision(
                    task=task,
                    due=event_due or cadence_due,
                    reason=reason,
                    evaluated_at=resolved.isoformat(),
                    next_due_at=(resolved if event_due else next_due).isoformat(),
                )
            )
        return decisions

    def record_wakeup(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        task: SchedulerTask,
        reason: Literal["cadence", "event"],
        idempotency_key: str,
        created_at: Optional[datetime] = None,
    ):
        resolved = self._as_utc(created_at)
        return self.store.append_evidence(
            session_id=session_id,
            event_type="SCHEDULER_WAKEUP",
            category="scheduler",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=idempotency_key,
            created_at=resolved.isoformat(),
            payload={"task": task, "reason": reason, "woke_at": resolved.isoformat()},
        )

    def _cadences(self) -> dict[SchedulerTask, int]:
        timers = self.config.timers
        return {
            "market_refresh": timers.market_refresh_seconds,
            "agent_heartbeat": timers.agent_heartbeat_seconds,
            "collective_sync": timers.collective_sync_seconds,
            "tactical_analysis": timers.tactical_analysis_seconds,
            "decision_review": timers.decision_review_seconds,
            "portfolio_reconciliation": timers.portfolio_reconciliation_seconds,
            "reflection": timers.reflection_seconds,
            "memory_checkpoint": timers.memory_checkpoint_seconds,
            "instruction_manifest_refresh": timers.instruction_manifest_refresh_seconds,
        }

    @staticmethod
    def _parse(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> datetime:
        resolved = value or datetime.now(timezone.utc)
        return resolved if resolved.tzinfo is not None else resolved.replace(tzinfo=timezone.utc)
