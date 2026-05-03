"""Decision ledger — typed decisions linked to accepted reports."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso
from .persistence import write_json_atomic

DecisionStatus = Literal["active", "deprecated", "superseded", "rejected"]


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    decision_id: str = Field(..., min_length=1)
    project_id: str = ""
    scope: str = ""
    decision: str = Field(..., min_length=1)
    status: DecisionStatus = "active"
    source_report_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    created_at: str = Field(default_factory=utc_now_iso)
    deprecated_at: Optional[str] = None
    superseded_by: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()


class DecisionLedger:
    """File-backed decision ledger.  Active decisions are loaded into context."""

    def __init__(self, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.ledger_dir = self.root_dir / ".agent_memory" / "decision_ledger"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, decision_id: str) -> Path:
        return self.ledger_dir / f"{decision_id}.dsdecision.json"

    def add_decision(
        self,
        *,
        decision: str,
        scope: str = "",
        project_id: str = "",
        source_report_ids: Optional[list[str]] = None,
        confidence: float = 1.0,
    ) -> DecisionRecord:
        rec = DecisionRecord(
            decision_id=uuid.uuid4().hex,
            project_id=project_id,
            scope=scope,
            decision=decision,
            source_report_ids=source_report_ids or [],
            confidence=confidence,
        )
        write_json_atomic(self._path(rec.decision_id), rec.model_dump())
        return rec

    def get_decision(self, decision_id: str) -> DecisionRecord:
        path = self._path(decision_id)
        if not path.exists():
            raise KeyError(f"Decision '{decision_id}' not found")
        return DecisionRecord(**json.loads(path.read_text(encoding="utf-8")))

    def deprecate(self, decision_id: str) -> DecisionRecord:
        rec = self.get_decision(decision_id)
        rec.status = "deprecated"
        rec.deprecated_at = utc_now_iso()
        write_json_atomic(self._path(decision_id), rec.model_dump())
        return rec

    def supersede(self, decision_id: str, *, new_decision_id: str) -> DecisionRecord:
        rec = self.get_decision(decision_id)
        rec.status = "superseded"
        rec.superseded_by = new_decision_id
        rec.deprecated_at = utc_now_iso()
        write_json_atomic(self._path(decision_id), rec.model_dump())
        return rec

    def list_decisions(
        self,
        *,
        status: Optional[DecisionStatus] = None,
        active_only: bool = False,
    ) -> list[DecisionRecord]:
        if active_only:
            status = "active"
        records: list[DecisionRecord] = []
        for path in self.ledger_dir.glob("*.dsdecision.json"):
            try:
                rec = DecisionRecord(
                    **json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if status and rec.status != status:
                continue
            records.append(rec)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records
