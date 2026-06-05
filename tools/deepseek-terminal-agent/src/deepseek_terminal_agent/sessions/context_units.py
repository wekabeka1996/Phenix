"""Typed context units for structured, reversible context assembly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import utc_now_iso

UnitType = Literal[
    "turn", "memory_atom", "artifact", "spine", "decision", "risk", "tool_result"
]
SemanticRole = Literal[
    "fact", "decision", "constraint", "evidence", "open_question", "result"
]


class ContextUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    unit_id: str = Field(..., min_length=1)
    unit_type: UnitType
    semantic_role: SemanticRole = "fact"
    scope: str = ""
    text: str = ""
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    importance: float = 0.5
    created_at: str = Field(default_factory=utc_now_iso)

    @field_validator("confidence", "importance")
    @classmethod
    def _clamp_0_1(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be within 0..1")
        return v
