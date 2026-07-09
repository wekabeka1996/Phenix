"""Session-bound ledger for non-executable CLI/API agent proposals."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import Settings
from ..logging_utils import redact_obj
from .models import utc_now_iso
from .persistence import write_json_atomic
from .token_budget import truncate_chars

ProposalKind = Literal[
    "analysis_note",
    "memory_refresh",
    "sos_market_change",
    "operator_question",
    "trade_intent_draft",
]
ProposalStatus = Literal["pending", "reviewed", "rejected", "accepted_for_review"]

FORBIDDEN_PROPOSAL_FIELDS = {
    "order",
    "sizing",
    "leverage",
    "quantity",
    "notional",
    "exchange_order_id",
    "client_order_id",
}


def validate_no_forbidden_proposal_fields(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip().lower()
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_PROPOSAL_FIELDS:
                raise ValueError(f"Forbidden proposal field: {child_path}")
            validate_no_forbidden_proposal_fields(child, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_forbidden_proposal_fields(item, path=f"{path}[{index}]")


class AgentProposalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    proposal_id: str = Field(default_factory=lambda: f"proposal-{uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    kind: ProposalKind
    created_at: str = Field(default_factory=utc_now_iso)
    confidence: Optional[float] = None
    rationale: str = Field(..., min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    status: ProposalStatus = "pending"
    payload: dict[str, Any] = Field(default_factory=dict)
    execution_authority: Literal[False] = False

    @field_validator("proposal_id", "session_id")
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

    @field_validator("source_refs")
    @classmethod
    def bounded_source_refs(cls, value: list[str]) -> list[str]:
        return [truncate_chars(str(item).strip(), 512) for item in value[:30] if str(item).strip()]

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within 0..1")
        return value

    @field_validator("payload")
    @classmethod
    def reject_executable_payload_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_no_forbidden_proposal_fields(value)
        return value


class AgentProposalStore:
    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.sessions_root = self.root_dir / settings.sessions.root_dir
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def create_proposal(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        kind: ProposalKind,
        rationale: str,
        source_refs: Optional[list[str]] = None,
        confidence: Optional[float] = None,
        status: ProposalStatus = "pending",
        payload: Optional[dict[str, Any]] = None,
    ) -> AgentProposalRecord:
        proposal = AgentProposalRecord(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            kind=kind,
            rationale=rationale,
            source_refs=source_refs or [],
            confidence=confidence,
            status=status,
            payload=payload or {},
        )
        self.write_proposal(proposal)
        return proposal

    def write_proposal(self, proposal: AgentProposalRecord) -> Path:
        target = self._session_proposals_root(proposal.session_id) / f"{proposal.proposal_id}.dsproposal.json"
        return write_json_atomic(target, redact_obj(proposal.model_dump()))

    def get_proposal(self, proposal_id: str) -> AgentProposalRecord:
        AgentProposalRecord.model_validate(
            {
                "proposal_id": proposal_id,
                "session_id": "validation-only",
                "agent_id": "validation-only",
                "agent_number": 0,
                "kind": "analysis_note",
                "rationale": "validation-only",
            }
        )
        for path in self.sessions_root.glob(f"*/agent_proposals/{proposal_id}.dsproposal.json"):
            return AgentProposalRecord(**json.loads(path.read_text(encoding="utf-8")))
        raise FileNotFoundError(proposal_id)

    def list_proposals(self, *, session_id: str) -> list[AgentProposalRecord]:
        proposals: list[AgentProposalRecord] = []
        root = self._session_proposals_root(session_id)
        if not root.exists():
            return []
        for path in root.glob("*.dsproposal.json"):
            proposals.append(AgentProposalRecord(**json.loads(path.read_text(encoding="utf-8"))))
        proposals.sort(key=lambda item: item.created_at, reverse=True)
        return proposals

    def _session_proposals_root(self, session_id: str) -> Path:
        normalized = str(session_id or "").strip()
        if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
            raise ValueError("session_id must be a safe single path segment")
        root = self.sessions_root / normalized / "agent_proposals"
        root.mkdir(parents=True, exist_ok=True)
        return root
