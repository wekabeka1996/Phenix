"""Append-friendly local memory atoms with lexical retrieval and redaction."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import Settings
from ..logging_utils import redact_obj
from .models import utc_now_iso
from .persistence import append_jsonl_record, quarantine_jsonl_issue, read_jsonl_records

MemoryKind = Literal["fact", "decision", "invariant",
                     "preference", "risk", "result", "todo", "constraint"]
MemoryTTL = Literal["short", "session", "project", "long"]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", str(text or "").lower()))


class MemoryAtom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    atom_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    scope: str = Field(..., min_length=1)
    kind: MemoryKind
    text: str = Field(..., min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    ttl: MemoryTTL = "session"
    source_session_id: Optional[str] = None
    source_turn_ids: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    contradicted_by: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    redacted: bool = False

    @field_validator("confidence", "importance")
    @classmethod
    def score_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("must be within 0..1")
        return value


class MemoryAtomStore:
    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.path = self.root_dir / settings.memory.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.quarantine_root = self.root_dir / ".agent_memory" / "quarantine"

    def add_atom(self, atom: MemoryAtom) -> MemoryAtom:
        if len(atom.text) > self.settings.memory.max_atom_chars:
            raise ValueError("atom.text exceeds memory.max_atom_chars")
        sanitized = self._sanitize(atom)
        self._append_atom(sanitized)
        return sanitized

    def list_atoms(self, *, include_disabled: bool = True) -> list[MemoryAtom]:
        atoms = list(self._load_latest().values())
        atoms.sort(key=lambda item: (
            item.updated_at, item.atom_id), reverse=True)
        if include_disabled:
            return atoms
        return [atom for atom in atoms if atom.enabled]

    def get_atom(self, atom_id: str) -> MemoryAtom:
        atoms = self._load_latest()
        return atoms[atom_id]

    def update_atom(self, atom_id: str, **updates: Any) -> MemoryAtom:
        atom = self.get_atom(atom_id)
        payload = atom.model_dump()
        payload.update(updates)
        payload["updated_at"] = utc_now_iso()
        updated = MemoryAtom(**payload)
        sanitized = self._sanitize(updated)
        self._append_atom(sanitized)
        return sanitized

    def disable_atom(self, atom_id: str) -> MemoryAtom:
        return self.update_atom(atom_id, enabled=False)

    def supersede_atom(self, atom_id: str, successor_atom_id: str) -> MemoryAtom:
        atom = self.get_atom(atom_id)
        contradicted_by = list(atom.contradicted_by)
        if successor_atom_id not in contradicted_by:
            contradicted_by.append(successor_atom_id)
        return self.update_atom(atom_id, contradicted_by=contradicted_by, enabled=False)

    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        pinned_atom_ids: Optional[list[str]] = None,
        scope: Optional[str] = None,
        exclude_atom_ids: Optional[list[str]] = None,
    ) -> list[MemoryAtom]:
        query_tokens = _tokenize(query)
        pinned = set(pinned_atom_ids or [])
        excluded = set(exclude_atom_ids or [])
        candidates: list[tuple[float, MemoryAtom]] = []
        for atom in self.list_atoms(include_disabled=False):
            if atom.atom_id in excluded:
                continue
            candidates.append(
                (self._score_atom(atom, query_tokens, pinned, scope), atom))
        candidates.sort(key=lambda item: (-item[0], item[1].atom_id))
        limit = top_k or self.settings.memory.retrieval_top_k
        return [atom for score, atom in candidates if score > 0][:limit]

    def _score_atom(
        self,
        atom: MemoryAtom,
        query_tokens: set[str],
        pinned_atom_ids: set[str],
        scope: Optional[str],
    ) -> float:
        atom_tokens = _tokenize(atom.text) | set(
            token.lower() for token in atom.tags)
        overlap = len(query_tokens & atom_tokens)
        score = float(overlap * 5)
        if scope and atom.scope == scope:
            score += 3.0
        if atom.atom_id in pinned_atom_ids:
            score += 10.0
        score += atom.importance * 3.0
        score += atom.confidence * 2.0
        if atom.scope == "project":
            score += 0.5
        return score

    def _sanitize(self, atom: MemoryAtom) -> MemoryAtom:
        original = atom.model_dump()
        redacted = redact_obj(original)
        redacted["redacted"] = redacted != original or original.get(
            "redacted", False)
        return MemoryAtom(**redacted)

    def _append_atom(self, atom: MemoryAtom) -> None:
        append_jsonl_record(self.path, atom.model_dump())

    def _load_latest(self) -> dict[str, MemoryAtom]:
        latest: dict[str, MemoryAtom] = {}
        for line_number, record in read_jsonl_records(self.path, quarantine_root=self.quarantine_root):
            try:
                atom = MemoryAtom(**record)
            except Exception as exc:
                quarantine_jsonl_issue(
                    source_path=self.path,
                    quarantine_root=self.quarantine_root,
                    line_number=line_number,
                    raw_line=json.dumps(record, ensure_ascii=False),
                    error=f"invalid_memory_atom: {exc}",
                )
                continue
            latest[atom.atom_id] = atom
        return latest
