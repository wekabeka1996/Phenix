"""Project Capsule loading for the agentic dashboard transition."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings


class CapsuleProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)
    current_phase: str = Field(..., min_length=1)


class CapsuleRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: list[str] = Field(default_factory=list)
    development: list[str] = Field(default_factory=list)
    runtime: list[str] = Field(default_factory=list)


class CapsuleMemoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deep_checkpoint: bool = False
    accepted_reports_only: bool = True
    default_agent_search_mode: str = Field(..., min_length=1)


class CapsulePermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    production_changes: str = Field(..., min_length=1)
    config_changes: str = Field(..., min_length=1)
    registry_changes: str = Field(..., min_length=1)
    memory_updates: str = Field(..., min_length=1)


class CapsulePhaseState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    completed: list[str] = Field(default_factory=list)
    in_progress: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_best_step: list[str] = Field(default_factory=list)


class ProjectCapsule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: CapsuleProject
    ssot_rules: CapsuleRules
    memory: CapsuleMemoryPolicy
    permissions: CapsulePermissions
    current_phase: CapsulePhaseState

    def to_public_dict(self) -> dict:
        payload = self.model_dump()
        payload["counts"] = {
            "config_rules": len(self.ssot_rules.config),
            "development_rules": len(self.ssot_rules.development),
            "runtime_rules": len(self.ssot_rules.runtime),
            "completed_items": len(self.current_phase.completed),
            "in_progress_items": len(self.current_phase.in_progress),
            "blockers": len(self.current_phase.blockers),
            "risks": len(self.current_phase.risks),
            "next_steps": len(self.current_phase.next_best_step),
        }
        return payload


class ProjectCapsuleStore:
    """Load a machine-readable project capsule from explicit YAML."""

    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.path = self.root_dir / settings.project_capsule.path

    def load(self) -> ProjectCapsule:
        if not self.path.exists():
            raise FileNotFoundError(
                f"Project capsule file not found: {self.path}")
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("Project capsule YAML must be a mapping")
        capsule_payload = raw.get("project_capsule")
        if not isinstance(capsule_payload, dict):
            raise ValueError("project_capsule root mapping is required")
        return ProjectCapsule(**capsule_payload)
