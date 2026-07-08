from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal

from .session_context_contract import SessionContextV1


class SessionContextReadModel:
    """Read-only adapter that builds a SessionContextV1 from Cockpit memory."""

    def __init__(self, memory_root: str | Path = ".agent_memory") -> None:
        self.memory_root = Path(memory_root)

    def load_context(self, session_id: str) -> SessionContextV1:
        """Loads and converts a Cockpit session into a read-only SessionContextV1 card.

        Fails closed (raises FileNotFoundError) if the memory store does not exist.
        """
        if not self.memory_root.exists():
            raise FileNotFoundError(f"Memory root directory does not exist: {self.memory_root}")

        sessions_dir = self.memory_root / "sessions"
        if not sessions_dir.exists():
            raise FileNotFoundError(f"Sessions directory does not exist: {sessions_dir}")

        session_dir = sessions_dir / session_id
        state_file = session_dir / "session.dsstate.json"
        if not state_file.exists():
            raise FileNotFoundError(f"Session state file not found: {state_file}")

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Collect references
        # 1. Pinned memory atoms
        pinned_atoms = state.get("pinned_memory_atom_ids") or []
        memory_atom_refs = [f"agent-memory://atom/{atom_id}" for atom_id in pinned_atoms]

        # Collect memory atoms from memory_store.json
        atoms_path = self.memory_root / "memory_store.json"
        if atoms_path.exists():
            try:
                with open(atoms_path, "r", encoding="utf-8") as f:
                    atoms_data = json.load(f)
                if isinstance(atoms_data, list):
                    for atom in atoms_data:
                        atom_id = atom.get("atom_id")
                        source_session_id = atom.get("source_session_id")
                        scope = atom.get("scope")
                        if atom_id and (source_session_id == session_id or atom_id in pinned_atoms or scope == "project"):
                            ref = f"agent-memory://atom/{atom_id}"
                            if ref not in memory_atom_refs:
                                memory_atom_refs.append(ref)
            except Exception:
                pass

        # 2. Subagent / artifacts refs
        attachment_refs = []
        artifacts_dir = self.memory_root / "artifacts"
        if artifacts_dir.exists():
            for item in artifacts_dir.glob(f"*{session_id}*"):
                attachment_refs.append(f"agent-memory://artifact/{item.name}")

        # 3. Pattern / playbook refs
        pattern_refs = []
        playbooks_file = self.memory_root / "playbooks.yaml"
        if playbooks_file.exists():
            pattern_refs.append("agent-memory://playbooks")

        # 4. Token budget
        active_profile = state.get("active_profile") or {}
        token_budget = active_profile.get("context_budget_chars") or 100000

        # 5. Lineage
        compression_lineage_refs = []
        current_spine_id = state.get("current_spine_id")
        if current_spine_id:
            compression_lineage_refs.append(f"agent-memory://spine/{current_spine_id}")

        # Build provenance
        provenance = {
            "title": state.get("title") or "Unnamed Session",
            "status": state.get("status") or "idle",
            "model_id": active_profile.get("model_id") or "unknown",
            "updated_at": state.get("updated_at") or "",
        }

        # Source reference list
        source = f"cockpit-session://{session_id}"

        return SessionContextV1(
            session_id=session_id,
            source=source,
            created_at=state.get("created_at") or "",
            operator_notes_refs=[],  # populated if operator notes exist
            memory_atom_refs=memory_atom_refs,
            attachment_refs=attachment_refs,
            pattern_refs=pattern_refs,
            token_budget=token_budget,
            compression_lineage_refs=compression_lineage_refs,
            approval_status="none",
            provenance=provenance,
        )
