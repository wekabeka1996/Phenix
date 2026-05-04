"""Approval queue for risky agent actions."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso
from .persistence import write_json_atomic

ApprovalRisk = Literal["medium", "high", "critical"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
ApprovalScope = Literal["once", "this_task", "this_session"]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    approval_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    requested_by: str = ""
    requested_action: str = Field(..., min_length=1)
    risk_level: ApprovalRisk = "medium"
    reason: str = ""
    expected_behavior_change: bool = True
    files_or_scopes: list[str] = Field(default_factory=list)
    rollback_plan: str = ""
    status: ApprovalStatus = "pending"
    scope: ApprovalScope = "once"
    created_at: str = Field(default_factory=utc_now_iso)
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ApprovalQueue:
    """File-backed approval queue. Requests persist to JSON files."""

    def __init__(self, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.queue_dir = self.root_dir / ".agent_memory" / "approval_queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, approval_id: str) -> Path:
        return self.queue_dir / f"{approval_id}.dsapproval.json"

    def create_request(
        self,
        *,
        session_id: str,
        requested_action: str,
        risk_level: ApprovalRisk = "medium",
        reason: str = "",
        expected_behavior_change: bool = True,
        files_or_scopes: Optional[list[str]] = None,
        rollback_plan: str = "",
        requested_by: str = "",
        scope: ApprovalScope = "once",
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            approval_id=uuid.uuid4().hex,
            session_id=session_id,
            requested_by=requested_by,
            requested_action=requested_action,
            risk_level=risk_level,
            reason=reason,
            expected_behavior_change=expected_behavior_change,
            files_or_scopes=files_or_scopes or [],
            rollback_plan=rollback_plan,
            scope=scope,
        )
        write_json_atomic(self._path(req.approval_id), req.model_dump())
        return req

    def get_request(self, approval_id: str) -> ApprovalRequest:
        path = self._path(approval_id)
        if not path.exists():
            raise KeyError(f"ApprovalRequest '{approval_id}' not found")
        return ApprovalRequest(**json.loads(path.read_text(encoding="utf-8")))

    def resolve(
        self,
        approval_id: str,
        *,
        status: Literal["approved", "rejected"],
        resolved_by: str = "user",
        note: str = "",
    ) -> ApprovalRequest:
        req = self.get_request(approval_id)
        if req.status != "pending":
            raise ValueError(f"Cannot resolve — already {req.status}")
        req.status = status
        req.resolved_at = utc_now_iso()
        req.resolved_by = resolved_by
        req.resolution_note = note or None
        write_json_atomic(self._path(approval_id), req.model_dump())
        return req

    def list_requests(
        self,
        *,
        session_id: Optional[str] = None,
        status: Optional[ApprovalStatus] = None,
    ) -> list[ApprovalRequest]:
        results: list[ApprovalRequest] = []
        for path in sorted(self.queue_dir.glob("*.dsapproval.json")):
            try:
                req = ApprovalRequest(
                    **json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if session_id and req.session_id != session_id:
                continue
            if status and req.status != status:
                continue
            results.append(req)
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def is_approved(self, approval_id: str) -> bool:
        try:
            return self.get_request(approval_id).status == "approved"
        except KeyError:
            return False
