"""Manifest contract for dynamic agent arena instruction files."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import utc_now_iso

INSTRUCTION_ROOT = Path("docs") / "agent_arena_instructions"

REQUIRED_INSTRUCTION_FILES: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("AGENT_ARENA_RULES.md", 10, ("all",)),
    ("AGENT_SKILLS.md", 20, ("all",)),
    ("AGENT_TRADING_STYLE.md", 30, ("decision_agent", "operator_agent")),
    ("FEATURE_TRUST_GUIDE.md", 40, ("decision_agent", "analyst_agent")),
    ("SESSION_OBJECTIVE.md", 50, ("all",)),
    ("SUBAGENT_RULES.md", 60, ("subagent", "coordinator")),
)


def _utc_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _safe_instruction_path(value: str) -> str:
    path = Path(str(value or "").strip())
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError("instruction path must be a safe relative path")
    return path.as_posix()


class InstructionManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1)
    sha256: str = ""
    version: str = "missing"
    updated_at: str = ""
    priority: int = Field(..., ge=0)
    target_agents: list[str] = Field(default_factory=list)
    missing: bool = False

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return _safe_instruction_path(value)

    @field_validator("target_agents")
    @classmethod
    def target_agents_required(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("target_agents must not be empty")
        return cleaned


class InstructionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    manifest_version: str
    generated_at: str = Field(default_factory=utc_now_iso)
    instruction_root: str
    instructions: list[InstructionManifestEntry] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)

    @field_validator("instruction_root")
    @classmethod
    def safe_root(cls, value: str) -> str:
        return _safe_instruction_path(value)


def build_instruction_entry(
    *,
    root_dir: str | Path,
    filename: str,
    priority: int,
    target_agents: tuple[str, ...],
) -> InstructionManifestEntry:
    relative_path = (INSTRUCTION_ROOT / filename).as_posix()
    _safe_instruction_path(relative_path)
    absolute_path = Path(root_dir) / relative_path
    if not absolute_path.exists():
        return InstructionManifestEntry(
            path=relative_path,
            priority=priority,
            target_agents=list(target_agents),
            missing=True,
        )
    if not absolute_path.is_file():
        raise ValueError(f"instruction path is not a file: {relative_path}")
    raw = absolute_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    return InstructionManifestEntry(
        path=relative_path,
        sha256=digest,
        version=digest[:16],
        updated_at=_utc_from_mtime(absolute_path),
        priority=priority,
        target_agents=list(target_agents),
        missing=False,
    )


def build_instruction_manifest(root_dir: str | Path = ".") -> InstructionManifest:
    entries = [
        build_instruction_entry(
            root_dir=root_dir,
            filename=filename,
            priority=priority,
            target_agents=target_agents,
        )
        for filename, priority, target_agents in REQUIRED_INSTRUCTION_FILES
    ]
    entries.sort(key=lambda item: (item.priority, item.path))
    missing_files = [entry.path for entry in entries if entry.missing]
    version_source = "|".join(
        f"{entry.path}:{entry.sha256}:{entry.version}:{entry.missing}" for entry in entries
    )
    manifest_version = hashlib.sha256(version_source.encode("utf-8")).hexdigest()[:16]
    return InstructionManifest(
        manifest_version=manifest_version,
        instruction_root=INSTRUCTION_ROOT.as_posix(),
        instructions=entries,
        missing_files=missing_files,
    )


def changed_instruction_files(
    previous_manifest: Optional[InstructionManifest],
    current_manifest: InstructionManifest,
) -> list[str]:
    if previous_manifest is None:
        return [entry.path for entry in current_manifest.instructions if not entry.missing]
    previous = {entry.path: entry.sha256 for entry in previous_manifest.instructions}
    changed = []
    for entry in current_manifest.instructions:
        if entry.missing:
            continue
        if previous.get(entry.path) != entry.sha256:
            changed.append(entry.path)
    return changed
