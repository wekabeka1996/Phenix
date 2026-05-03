"""Tests for conflict detection and effective memory resolution."""
from __future__ import annotations

import uuid

from deepseek_terminal_agent.sessions.context_conflicts import (
    Conflict,
    detect_conflicts,
    resolve_effective_memory,
)


def _atom(text: str, atom_id: str = "", scope: str = "session", enabled: bool = True) -> dict:
    return {
        "atom_id": atom_id or uuid.uuid4().hex,
        "text": text,
        "scope": scope,
        "enabled": enabled,
    }


def test_detect_no_conflicts():
    atoms = [_atom("The system is enabled"), _atom("Using approach X")]
    conflicts = detect_conflicts(atoms)
    assert conflicts == []


def test_detect_duplicate_conflict():
    same_text = "The ATR is ready"
    id_a = "atom-a"
    id_b = "atom-b"
    atoms = [_atom(same_text, id_a), _atom(same_text, id_b)]
    conflicts = detect_conflicts(atoms)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "duplicate"
    assert conflicts[0].atom_id_a == id_a
    assert conflicts[0].atom_id_b == id_b


def test_detect_contradiction_conflict():
    id_a = "atom-a"
    id_b = "atom-b"
    atoms = [
        _atom("The feature is enabled", id_a, scope="project"),
        _atom("The feature is disabled", id_b, scope="project"),
    ]
    conflicts = detect_conflicts(atoms)
    # Should detect at least one contradiction
    contradiction_conflicts = [
        c for c in conflicts if c.conflict_type == "contradiction"]
    assert len(contradiction_conflicts) >= 1


def test_resolve_effective_memory_excludes_disabled():
    atoms = [
        _atom("Active atom", "a1", enabled=True),
        _atom("Disabled atom", "a2", enabled=False),
    ]
    result = resolve_effective_memory(atoms, pins=[], conflicts=[])
    atom_ids = [a["atom_id"] for a in result]
    assert "a1" in atom_ids
    assert "a2" not in atom_ids


def test_resolve_effective_memory_pinned_wins():
    id_a = "atom-a"
    id_b = "atom-b"
    atoms = [_atom("Atom A", id_a), _atom("Atom B", id_b)]
    conflict = Conflict(
        conflict_id="c1",
        conflict_type="contradiction",
        atom_id_a=id_a,
        atom_id_b=id_b,
        reason="test conflict",
    )
    # Pin B — it should win
    result = resolve_effective_memory(atoms, pins=[id_b], conflicts=[conflict])
    atom_ids = [a["atom_id"] for a in result]
    assert id_b in atom_ids
    assert id_a not in atom_ids


def test_resolve_effective_memory_earlier_wins_if_neither_pinned():
    id_a = "atom-a"
    id_b = "atom-b"
    atoms = [_atom("Atom A", id_a), _atom("Atom B", id_b)]
    conflict = Conflict(
        conflict_id="c1",
        conflict_type="contradiction",
        atom_id_a=id_a,
        atom_id_b=id_b,
        reason="test conflict",
    )
    result = resolve_effective_memory(atoms, pins=[], conflicts=[conflict])
    atom_ids = [a["atom_id"] for a in result]
    # Earlier atom (a) wins
    assert id_a in atom_ids
    assert id_b not in atom_ids


def test_resolve_effective_memory_ignored_conflict_no_exclusion():
    id_a = "atom-a"
    id_b = "atom-b"
    atoms = [_atom("Atom A", id_a), _atom("Atom B", id_b)]
    conflict = Conflict(
        conflict_id="c1",
        conflict_type="contradiction",
        atom_id_a=id_a,
        atom_id_b=id_b,
        reason="test",
        status="ignored",
    )
    result = resolve_effective_memory(atoms, pins=[], conflicts=[conflict])
    atom_ids = [a["atom_id"] for a in result]
    # Both should be present since conflict is ignored
    assert id_a in atom_ids
    assert id_b in atom_ids
