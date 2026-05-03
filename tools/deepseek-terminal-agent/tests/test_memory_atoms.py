"""Tests for local memory atoms and lexical retrieval."""
from __future__ import annotations

import json

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtom, MemoryAtomStore


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def test_add_search_disable_and_supersede(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    atom = store.add_atom(MemoryAtom(scope="session", kind="fact",
                          text="Model switching preserves session history", tags=["model", "session"]))

    found = store.search("model switching", top_k=5)
    assert found[0].atom_id == atom.atom_id

    disabled = store.disable_atom(atom.atom_id)
    assert disabled.enabled is False
    assert store.search("model switching", top_k=5) == []

    replacement = store.add_atom(MemoryAtom(
        scope="session", kind="decision", text="Use flash for scouts", tags=["flash", "scout"]))
    superseded = store.supersede_atom(atom.atom_id, replacement.atom_id)
    assert replacement.atom_id in superseded.contradicted_by


def test_lexical_ranking_prefers_overlap_and_pins(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    weaker = store.add_atom(MemoryAtom(scope="project", kind="fact",
                            text="General dashboard note", confidence=0.6, importance=0.5))
    stronger = store.add_atom(MemoryAtom(scope="session", kind="fact", text="Session context pack includes memory atoms",
                              confidence=0.8, importance=0.7, tags=["context", "memory"]))

    results = store.search("context memory", top_k=5)
    assert results[0].atom_id == stronger.atom_id

    pinned_results = store.search(
        "dashboard", top_k=5, pinned_atom_ids=[stronger.atom_id])
    assert pinned_results[0].atom_id == stronger.atom_id
    assert weaker.atom_id in {atom.atom_id for atom in pinned_results}


def test_one_atom_schema_validation(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    atom = store.add_atom(MemoryAtom(
        scope="session", kind="constraint", text="No raw reasoning in UI"))
    assert atom.kind == "constraint"


def test_secrets_redacted(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    atom = store.add_atom(MemoryAtom(scope="session", kind="risk",
                          text="api_key=sk-secret-value should never be shown"))
    assert atom.redacted is True
    assert "sk-secret-value" not in atom.text


def test_disabled_atoms_not_retrieved(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    atom = store.add_atom(MemoryAtom(
        scope="session", kind="todo", text="Refresh models before chat"))
    store.disable_atom(atom.atom_id)
    assert store.search("refresh models") == []


def test_corrupted_jsonl_line_is_quarantined_and_other_atoms_survive(tmp_path):
    store = MemoryAtomStore(make_settings(), root_dir=tmp_path)
    atom_path = tmp_path / ".agent_memory" / "memory_atoms.dsmem.jsonl"
    first = MemoryAtom(scope="session", kind="fact",
                       text="First atom").model_dump()
    second = MemoryAtom(scope="session", kind="fact",
                        text="Second atom").model_dump()
    atom_path.write_text(
        json.dumps(first, ensure_ascii=False) + "\n" + "not-json" +
        "\n" + json.dumps(second, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    atoms = store.list_atoms()
    quarantine_root = tmp_path / ".agent_memory" / "quarantine"

    assert [atom.text for atom in atoms] == ["Second atom", "First atom"]
    assert list(quarantine_root.glob("**/*.quarantine.jsonl"))
