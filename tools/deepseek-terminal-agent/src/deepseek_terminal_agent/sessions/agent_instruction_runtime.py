"""Runtime preflight helpers for agent instruction hot reload."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent_instruction_manifest import (
    InstructionManifest,
    build_instruction_manifest,
    changed_instruction_files,
)
from .models import utc_now_iso


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
