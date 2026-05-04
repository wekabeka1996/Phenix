"""Memory patch flow — propose, approve, and apply atomic memory updates."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso
from .persistence import write_json_atomic

PatchRisk = Literal["low", "medium", "high"]
PatchStatus = Literal["pending", "approved", "rejected", "applied"]


class MemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    patch_id: str = Field(..., min_length=1)
    source_report_ids: list[str] = Field(default_factory=list)
    proposed_change: str = Field(..., min_length=1)
    affected_checkpoint_section: str = ""
    reason: str = ""
    risk: PatchRisk = "low"
    status: PatchStatus = "pending"
    diff: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    applied_at: Optional[str] = None
    approved_by: Optional[str] = None
    rejected_reason: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()


class MemoryPatchStore:
    """File-backed store for memory patch proposals."""

    def __init__(self, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.patch_dir = self.root_dir / ".agent_memory" / "memory_patches"
        self.patch_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, patch_id: str) -> Path:
        return self.patch_dir / f"{patch_id}.dspatch.json"

    def create_patch(
        self,
        *,
        proposed_change: str,
        affected_checkpoint_section: str = "",
        reason: str = "",
        risk: PatchRisk = "low",
        diff: str = "",
        source_report_ids: Optional[list[str]] = None,
    ) -> MemoryPatch:
        patch = MemoryPatch(
            patch_id=uuid.uuid4().hex,
            source_report_ids=source_report_ids or [],
            proposed_change=proposed_change,
            affected_checkpoint_section=affected_checkpoint_section,
            reason=reason,
            risk=risk,
            diff=diff,
        )
        write_json_atomic(self._path(patch.patch_id), patch.model_dump())
        return patch

    def get_patch(self, patch_id: str) -> MemoryPatch:
        path = self._path(patch_id)
        if not path.exists():
            raise KeyError(f"MemoryPatch '{patch_id}' not found")
        return MemoryPatch(**json.loads(path.read_text(encoding="utf-8")))

    def approve(self, patch_id: str, *, approved_by: str = "user") -> MemoryPatch:
        patch = self.get_patch(patch_id)
        if patch.status != "pending":
            raise ValueError(f"Cannot approve — already {patch.status}")
        patch.status = "approved"
        patch.approved_by = approved_by
        write_json_atomic(self._path(patch_id), patch.model_dump())
        return patch

    def reject(self, patch_id: str, *, reason: str = "") -> MemoryPatch:
        patch = self.get_patch(patch_id)
        if patch.status not in ("pending",):
            raise ValueError(f"Cannot reject — already {patch.status}")
        patch.status = "rejected"
        patch.rejected_reason = reason or None
        write_json_atomic(self._path(patch_id), patch.model_dump())
        return patch

    def mark_applied(self, patch_id: str) -> MemoryPatch:
        patch = self.get_patch(patch_id)
        if patch.status != "approved":
            raise ValueError(
                f"Cannot mark applied — not approved (status={patch.status})")
        patch.status = "applied"
        patch.applied_at = utc_now_iso()
        write_json_atomic(self._path(patch_id), patch.model_dump())
        return patch

    def list_patches(
        self,
        *,
        status: Optional[PatchStatus] = None,
    ) -> list[MemoryPatch]:
        records: list[MemoryPatch] = []
        for path in self.patch_dir.glob("*.dspatch.json"):
            try:
                rec = MemoryPatch(
                    **json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if status and rec.status != status:
                continue
            records.append(rec)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records
