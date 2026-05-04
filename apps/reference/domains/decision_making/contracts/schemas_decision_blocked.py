"""Typed payload model for DecisionMaking pre-intent block events.

The authoritative public contract for this payload also exists as
apps/reference/domains/decision_making/intent/schemas/decision_blocked_v1.json. This
Python model is used to validate and serialize the event before it is written to
truth artifacts and emitted onto the FSM bus.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DecisionBlockedPayload(BaseModel):
    """Structured payload for EVT:DECISION_BLOCKED.

    This event is emitted when DecisionMaking halts before a trade intent can be
    formed, typically because a config contract or another health/readiness guard
    failed closed. Extra fields are forbidden so the Pydantic model matches the
    registered JSON schema's additionalProperties=false contract.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1)

    # Context
    symbol: str = Field(
        description="Symbol being processed when block occurred")
    stage: str = Field(
        description="Pipeline stage where block occurred (e.g. 'on_features')")
    ts_ms: int = Field(description="Timestamp of the block in ms")

    # Reason
    reason_code: str = Field(
        description="Normalized Reject Reason code (e.g. NRR-CFG-001)")
    reason: str = Field(description="Human readable reason")

    # Debug details
    path: str = Field(description="Config path or resource involved")
    why: str = Field(description="Short explanation (<80 chars)")
    rid: str | None = Field(
        default=None, description="Correlation id when available")
    span_id: str | None = Field(
        default=None, description="Tracing span id when available")
    why_chain: list[str] = Field(
        default_factory=list, description="Decision ancestry for forensics")
    details: dict[str, Any] | None = Field(
        default=None, description="Structured forensic details")
