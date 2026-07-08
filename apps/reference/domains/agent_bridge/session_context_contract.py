from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    source: str
    created_at: str
    operator_notes_refs: List[str] = Field(default_factory=list)
    memory_atom_refs: List[str] = Field(default_factory=list)
    attachment_refs: List[str] = Field(default_factory=list)
    pattern_refs: List[str] = Field(default_factory=list)
    token_budget: int = Field(..., ge=0)
    compression_lineage_refs: List[str] = Field(default_factory=list)
    approval_status: Literal["pending", "approved", "rejected", "expired", "none"]
    provenance: Dict[str, Any] = Field(default_factory=dict)
