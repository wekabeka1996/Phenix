"""Data contract for CLI agent session loops, actions, and state transitions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CLIAgentSessionState(BaseModel):
    """Safe state representation of a bounded CLI agent session."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    last_memory_refresh_at: Optional[datetime] = None
    next_refresh_at: Optional[datetime] = None
    context_version: Optional[int] = None
    sos_pending: bool = False
    max_runtime_seconds: float = Field(..., gt=0.0)
    max_iterations: int = Field(..., gt=0)


class CLIAgentActionEnvelope(BaseModel):
    """Non-executable session wrapper for actions emitted by the CLI agent."""
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    action_kind: Literal["memory_refresh", "sos_emit", "proposal_submit", "heartbeat"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = Field(..., min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    proposal_ref: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def reject_executable_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Strict validation enforcing that no executable trading fields are present."""
        from .agent_proposals import validate_no_forbidden_proposal_fields
        validate_no_forbidden_proposal_fields(value)
        return value


def build_memory_refresh_action(reason: str, source_refs: list[str]) -> CLIAgentActionEnvelope:
    """Builds a non-executable action envelope for refreshing shared memory."""
    return CLIAgentActionEnvelope(
        action_kind="memory_refresh",
        reason=reason,
        source_refs=source_refs,
    )


def build_sos_emit_action(reason: str, market_snapshot_ref: str) -> CLIAgentActionEnvelope:
    """Builds a non-executable action envelope to emit an SOS trigger."""
    return CLIAgentActionEnvelope(
        action_kind="sos_emit",
        reason=reason,
        payload={"market_snapshot_ref": market_snapshot_ref},
    )


def build_proposal_submit_action(
    proposal_ref: str, reason: str, payload: dict[str, Any]
) -> CLIAgentActionEnvelope:
    """Builds a non-executable action envelope to submit a trading or analysis proposal."""
    return CLIAgentActionEnvelope(
        action_kind="proposal_submit",
        proposal_ref=proposal_ref,
        reason=reason,
        payload=payload,
    )


def should_agent_session_continue(
    started_at: datetime, now: datetime, state: CLIAgentSessionState, iteration_count: int
) -> bool:
    """Evaluates the loop boundary conditions to decide if the session should continue."""
    if iteration_count >= state.max_iterations:
        return False
    
    elapsed = (now - started_at).total_seconds()
    if elapsed >= state.max_runtime_seconds:
        return False
        
    return True


def apply_timer_tick_to_session_state(
    state: CLIAgentSessionState,
    tick_time: datetime,
    next_refresh: datetime,
    sos_active: bool,
) -> CLIAgentSessionState:
    """Applies a timer tick event to transition the session state."""
    new_state = state.model_copy(deep=True)
    
    # If SOS is active or scheduled refresh is due
    is_refresh_due = (
        state.next_refresh_at is not None 
        and tick_time >= state.next_refresh_at
    )
    
    if sos_active or is_refresh_due:
        new_state.last_memory_refresh_at = tick_time
        new_state.next_refresh_at = next_refresh
        new_state.sos_pending = False
        if new_state.context_version is not None:
            new_state.context_version += 1
        else:
            new_state.context_version = 1
            
    return new_state
