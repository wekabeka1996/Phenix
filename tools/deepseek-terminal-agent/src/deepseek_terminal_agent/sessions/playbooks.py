"""Playbook registry — typed schema + YAML loader for agent playbooks."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["low", "medium", "high"]


class PlaybookApprovalPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    step: str = Field(..., min_length=1)
    reason: str = ""
    blocking: bool = True


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    playbook_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""
    trigger_button: str = ""
    hotkey: str = ""
    input_sources: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    output_schema: str = ""
    approval_points: list[PlaybookApprovalPoint] = Field(default_factory=list)
    done_criteria: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    enabled: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()


class PlaybookRegistry:
    """Load and serve playbooks from a YAML file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._playbooks: Optional[list[Playbook]] = None

    def _load(self) -> list[Playbook]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("playbooks YAML must be a mapping")
        entries = raw.get("playbooks", [])
        if not isinstance(entries, list):
            raise ValueError("playbooks.playbooks must be a list")
        return [Playbook(**entry) for entry in entries]

    def list_playbooks(self, *, enabled_only: bool = True) -> list[Playbook]:
        if self._playbooks is None:
            self._playbooks = self._load()
        if enabled_only:
            return [p for p in self._playbooks if p.enabled]
        return list(self._playbooks)

    def get_playbook(self, playbook_id: str) -> Playbook:
        for pb in self.list_playbooks(enabled_only=False):
            if pb.playbook_id == playbook_id:
                return pb
        raise KeyError(f"Playbook '{playbook_id}' not found")

    def invalidate_cache(self) -> None:
        self._playbooks = None
