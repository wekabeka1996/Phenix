"""Registered Cockpit agent event commands for event-first arena ingress."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import utc_now_iso
from .token_budget import truncate_chars

AgentArenaAction = Literal[
    "rationale",
    "sos",
    "testnet_order_request",
    "testnet_cancel_request",
    "testnet_close_request",
]
AgentArenaCommandStatus = Literal["recorded", "rejected", "pending_fsm"]

FORBIDDEN_ARENA_FIELDS = {
    "api_key",
    "api_secret",
    "secret",
    "signature",
    "signed_payload",
    "raw_order",
    "raw_exchange_payload",
    "exchange_request",
    "mainnet",
    "live",
}

class AgentArenaEventRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., min_length=1)
    default_status: AgentArenaCommandStatus


class AgentArenaEventRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    events: dict[AgentArenaAction, AgentArenaEventRegistration]


def load_agent_arena_event_registry() -> AgentArenaEventRegistry:
    registry_path = Path(__file__).with_name("agent_event_registry.yaml")
    if not registry_path.exists():
        raise RuntimeError(f"Agent arena event registry missing: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return AgentArenaEventRegistry(**raw)


AGENT_ARENA_EVENT_REGISTRY = load_agent_arena_event_registry()


def ensure_agent_arena_registry_available() -> None:
    required = {
        "rationale",
        "sos",
        "testnet_order_request",
        "testnet_cancel_request",
        "testnet_close_request",
    }
    missing = required.difference(AGENT_ARENA_EVENT_REGISTRY.events)
    if missing:
        raise RuntimeError(f"Agent arena event registry missing: {', '.join(sorted(missing))}")


def validate_no_forbidden_arena_fields(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip().lower()
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_ARENA_FIELDS:
                raise ValueError(f"Forbidden arena event field: {child_path}")
            validate_no_forbidden_arena_fields(child, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_forbidden_arena_fields(item, path=f"{path}[{index}]")


class AgentArenaEventCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: f"event-{uuid4().hex}")
    command_id: str = Field(default_factory=lambda: f"command-{uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    action: AgentArenaAction
    event_type: str = Field(..., min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    rationale: str = Field(..., min_length=1)
    status: AgentArenaCommandStatus
    environment: Literal["testnet"] = "testnet"
    payload: dict[str, Any] = Field(default_factory=dict)
    fsm_registered: bool = True
    exchange_submitted: Literal[False] = False

    @field_validator("event_id", "command_id", "session_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(part in cleaned for part in ("..", "/", "\\")):
            raise ValueError("identifier must be a local safe id")
        return cleaned

    @field_validator("agent_id")
    @classmethod
    def bounded_agent_id(cls, value: str) -> str:
        return truncate_chars(value.strip(), 120)

    @field_validator("rationale")
    @classmethod
    def bounded_rationale(cls, value: str) -> str:
        return truncate_chars(value.strip(), 4000)

    @field_validator("payload")
    @classmethod
    def reject_forbidden_payload_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_no_forbidden_arena_fields(value)
        if str(value.get("environment") or value.get("mode") or "").lower() in {"mainnet", "live"}:
            raise ValueError("Agent arena events are testnet-only.")
        return value


def build_agent_arena_event_command(
    *,
    session_id: str,
    action: AgentArenaAction,
    agent_id: str,
    agent_number: int,
    rationale: str,
    payload: Optional[dict[str, Any]] = None,
    event_id: Optional[str] = None,
    command_id: Optional[str] = None,
) -> AgentArenaEventCommand:
    ensure_agent_arena_registry_available()
    if action not in AGENT_ARENA_EVENT_REGISTRY.events:
        raise ValueError(f"Unknown agent arena action: {action}")
    candidate_payload = payload or {}
    validate_no_forbidden_arena_fields(candidate_payload)
    registry = AGENT_ARENA_EVENT_REGISTRY.events[action]
    return AgentArenaEventCommand(
        event_id=event_id or f"event-{uuid4().hex}",
        command_id=command_id or f"command-{uuid4().hex}",
        session_id=session_id,
        agent_id=agent_id,
        agent_number=agent_number,
        action=action,
        event_type=registry.event_type,
        rationale=rationale,
        status=registry.default_status,
        payload=candidate_payload,
    )
