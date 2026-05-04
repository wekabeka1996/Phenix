"""Memory atom conflict detection and effective memory resolution."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now_iso

ConflictType = Literal["contradiction", "supersession", "duplicate"]
ConflictStatus = Literal["open", "resolved", "ignored"]


class Conflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    conflict_id: str = Field(..., min_length=1)
    conflict_type: ConflictType
    atom_id_a: str
    atom_id_b: str
    reason: str = ""
    status: ConflictStatus = "open"
    winner_atom_id: Optional[str] = None
    detected_at: str = Field(default_factory=utc_now_iso)


def detect_conflicts(memory_atoms: list[dict]) -> list[Conflict]:
    """Detect contradictions and duplicates in a list of memory atom dicts."""
    import uuid

    conflicts: list[Conflict] = []
    seen_texts: dict[str, str] = {}
    for atom in memory_atoms:
        atom_id = atom.get("atom_id", "")
        text = (atom.get("text") or "").strip().lower()
        if not text:
            continue
        if text in seen_texts:
            conflicts.append(
                Conflict(
                    conflict_id=uuid.uuid4().hex,
                    conflict_type="duplicate",
                    atom_id_a=seen_texts[text],
                    atom_id_b=atom_id,
                    reason=f"Identical text: {text[:80]}",
                )
            )
        else:
            seen_texts[text] = atom_id

    # Detect simple contradictions: same scope + opposite keywords
    negation_pairs = [("enabled", "disabled"), ("active", "inactive"),
                      ("true", "false"), ("on", "off")]
    scope_atoms: dict[str, list[dict]] = {}
    for atom in memory_atoms:
        scope = atom.get("scope", "")
        scope_atoms.setdefault(scope, []).append(atom)

    for scope, atoms in scope_atoms.items():
        for i, a in enumerate(atoms):
            for b in atoms[i + 1:]:
                text_a = (a.get("text") or "").lower()
                text_b = (b.get("text") or "").lower()
                for pos, neg in negation_pairs:
                    if pos in text_a and neg in text_b:
                        conflicts.append(
                            Conflict(
                                conflict_id=uuid.uuid4().hex,
                                conflict_type="contradiction",
                                atom_id_a=a.get("atom_id", ""),
                                atom_id_b=b.get("atom_id", ""),
                                reason=f"Potential contradiction: '{pos}' vs '{neg}'",
                            )
                        )
    return conflicts


def resolve_effective_memory(
    atoms: list[dict],
    pins: list[str],
    conflicts: list[Conflict],
) -> list[dict]:
    """Return the effective (non-conflicting, non-disabled) memory atoms.

    Rules (deterministic):
    - disabled atoms excluded;
    - pinned atom wins over unpinned in a conflict;
    - earlier atom wins if neither is pinned;
    - excluded atoms removed from result.
    """
    pinned_set = set(pins)
    loser_ids: set[str] = set()

    for conflict in conflicts:
        if conflict.status == "ignored":
            continue
        a_pinned = conflict.atom_id_a in pinned_set
        b_pinned = conflict.atom_id_b in pinned_set
        if a_pinned and not b_pinned:
            loser_ids.add(conflict.atom_id_b)
        elif b_pinned and not a_pinned:
            loser_ids.add(conflict.atom_id_a)
        else:
            # Earlier (lower index) wins
            loser_ids.add(conflict.atom_id_b)

    return [
        atom for atom in atoms
        if atom.get("enabled", True)
        and atom.get("atom_id", "") not in loser_ids
    ]
