"""Runtime preflight helpers for agent instruction hot reload."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent_instruction_manifest import (
    InstructionManifest,
    build_instruction_manifest,
    changed_instruction_files,
)
from .models import SessionEvent, utc_now_iso
from .store import SessionStore

INSTRUCTIONS_REFRESHED_EVENT = "INSTRUCTIONS_REFRESHED"
INSTRUCTIONS_ACKED_EVENT = "INSTRUCTIONS_ACKED"
RECOMMENDED_MVP_CADENCE_SECONDS = 300


class AgentInstructionAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    session_id: str = Field(..., min_length=1)
    manifest_version: str = Field(..., min_length=1)
    acknowledged_at: str = Field(default_factory=utc_now_iso)

    @field_validator("agent_id", "session_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(part in cleaned for part in ("..", "/", "\\")):
            raise ValueError("identifier must be a safe local id")
        return cleaned


class InstructionPreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_number: int
    session_id: str
    manifest_version: str
    changed_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    ack_required: bool = False
    event_payload: dict
    manifest: InstructionManifest

    @field_validator("agent_id", "session_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        return AgentInstructionAck.safe_identifier(value)


class InstructionRuntimeCycleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_number: int
    session_id: str
    manifest_version: str
    changed_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    refresh_event_id: Optional[str] = None
    ack_event_id: str
    ack: AgentInstructionAck
    status: str
    recommended_cadence_seconds: int = RECOMMENDED_MVP_CADENCE_SECONDS

    @field_validator("agent_id", "session_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        return AgentInstructionAck.safe_identifier(value)


def agent_instruction_preflight(
    *,
    root_dir: str = ".",
    agent_id: str,
    agent_number: int,
    session_id: str,
    previous_manifest: Optional[InstructionManifest] = None,
) -> InstructionPreflightResult:
    current_manifest = build_instruction_manifest(root_dir=root_dir)
    changed_files = changed_instruction_files(previous_manifest, current_manifest)
    missing_files = list(current_manifest.missing_files)
    ack_required = bool(changed_files or missing_files)
    status = "missing_required_files" if missing_files else ("changed" if changed_files else "unchanged")
    event_payload = {
        "event_type": "agent_instruction_refresh",
        "agent_id": agent_id,
        "agent_number": agent_number,
        "session_id": session_id,
        "manifest_version": current_manifest.manifest_version,
        "changed_files": changed_files,
        "missing_files": missing_files,
        "ack_required": ack_required,
        "status": status,
        "created_at": utc_now_iso(),
    }
    return InstructionPreflightResult(
        agent_id=agent_id,
        agent_number=agent_number,
        session_id=session_id,
        manifest_version=current_manifest.manifest_version,
        changed_files=changed_files,
        missing_files=missing_files,
        ack_required=ack_required,
        event_payload=event_payload,
        manifest=current_manifest,
    )


def run_instruction_preflight_for_agent(
    *,
    session_store: SessionStore,
    root_dir: str = ".",
    agent_id: str,
    agent_number: int,
    session_id: str,
) -> InstructionRuntimeCycleResult:
    """Run instruction hot-reload preflight for one agent/session cycle.

    This is intentionally caller-driven. Agent loops or schedulers can invoke it
    every five minutes and immediately before a cycle when a manifest change is
    suspected; it does not start a daemon.
    """
    previous_manifest = _latest_acknowledged_manifest(session_store, session_id)
    preflight = agent_instruction_preflight(
        root_dir=root_dir,
        agent_id=agent_id,
        agent_number=agent_number,
        session_id=session_id,
        previous_manifest=previous_manifest,
    )
    changed_or_missing = bool(preflight.changed_files or preflight.missing_files)
    refresh_event_id: Optional[str] = None
    if changed_or_missing:
        refresh_event_id = uuid.uuid4().hex
        session_store.append_event(
            session_id,
            SessionEvent(
                event_id=refresh_event_id,
                session_id=session_id,
                event_type=INSTRUCTIONS_REFRESHED_EVENT,
                message="Agent instruction manifest refreshed",
                metadata={
                    **preflight.event_payload,
                    "manifest": preflight.manifest.model_dump(),
                    "recommended_cadence_seconds": RECOMMENDED_MVP_CADENCE_SECONDS,
                },
            ),
        )

    ack = acknowledge_instruction_manifest(
        agent_id=agent_id,
        agent_number=agent_number,
        session_id=session_id,
        manifest_version=preflight.manifest_version,
    )
    ack_event_id = uuid.uuid4().hex
    status = "missing_required_files" if preflight.missing_files else "acknowledged"
    session_store.append_event(
        session_id,
        SessionEvent(
            event_id=ack_event_id,
            session_id=session_id,
            event_type=INSTRUCTIONS_ACKED_EVENT,
            message="Agent acknowledged instruction manifest",
            metadata={
                "agent_id": ack.agent_id,
                "agent_number": ack.agent_number,
                "session_id": ack.session_id,
                "manifest_version": ack.manifest_version,
                "acknowledged_at": ack.acknowledged_at,
                "status": status,
                "changed_files": list(preflight.changed_files),
                "missing_files": list(preflight.missing_files),
                "manifest": preflight.manifest.model_dump(),
                "refresh_event_id": refresh_event_id,
                "recommended_cadence_seconds": RECOMMENDED_MVP_CADENCE_SECONDS,
            },
        ),
    )
    return InstructionRuntimeCycleResult(
        agent_id=agent_id,
        agent_number=agent_number,
        session_id=session_id,
        manifest_version=preflight.manifest_version,
        changed_files=preflight.changed_files,
        missing_files=preflight.missing_files,
        refresh_event_id=refresh_event_id,
        ack_event_id=ack_event_id,
        ack=ack,
        status=status,
    )


def acknowledge_instruction_manifest(
    *,
    agent_id: str,
    agent_number: int,
    session_id: str,
    manifest_version: str,
) -> AgentInstructionAck:
    return AgentInstructionAck(
        agent_id=agent_id,
        agent_number=agent_number,
        session_id=session_id,
        manifest_version=manifest_version,
    )


def _latest_acknowledged_manifest(
    session_store: SessionStore,
    session_id: str,
) -> Optional[InstructionManifest]:
    latest: Optional[InstructionManifest] = None
    for event in session_store.list_events(session_id):
        if event.get("event_type") != INSTRUCTIONS_ACKED_EVENT:
            continue
        manifest_payload = event.get("metadata", {}).get("manifest")
        if not manifest_payload:
            continue
        latest = InstructionManifest(**manifest_payload)
    return latest
