from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionContextV1(BaseModel):
    """Read-only shared trading session memory context contract.

    POLICY SAFETY RULE:
    - This contract prohibits any order, sizing, leverage, or execution authority fields.
    - FSM components or MemoryPatch processes MUST NOT mutate YAML or system configurations.
    """
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

    @field_validator("source")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        if not value.startswith("cockpit-session://"):
            raise ValueError("source reference must start with 'cockpit-session://'")
        return value

    @field_validator("provenance")
    @classmethod
    def validate_provenance_keys(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        required_keys = {"title", "status"}
        missing_keys = required_keys - value.keys()
        if missing_keys:
            raise ValueError(f"provenance must contain keys: {missing_keys}")
        return value
