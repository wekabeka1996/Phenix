"""Deterministic context assembly for stateless DeepSeek chat requests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..config import Settings
from ..sessions.token_budget import estimate_tokens, truncate_chars
from .artifacts import ArtifactStore
from .memory_atoms import MemoryAtomStore
from .models import ArtifactRecord, ChatSession, ChatTurn, ContextReport, ModelProfile, SessionSpine
from .persistence import quarantine_jsonl_issue, read_jsonl_records
from .store import SessionStore


class ContextBuilder:
    def __init__(
        self,
        settings: Settings,
        *,
        session_store: SessionStore,
        memory_store: Optional[MemoryAtomStore] = None,
        artifact_store: Optional[ArtifactStore] = None,
        root_dir: str | Path = ".",
    ) -> None:
        self.settings = settings
        self.session_store = session_store
        self.memory_store = memory_store
        self.artifact_store = artifact_store
        self.root_dir = Path(root_dir)
        self.spines_path = self.root_dir / ".agent_memory" / "session_spines.dsspine.jsonl"
        self.quarantine_root = self.root_dir / ".agent_memory" / "quarantine"

    def build(
        self,
        *,
        session_id: str,
        current_user_message: str,
        selected_profile: ModelProfile,
        task_type: Optional[str] = None,
        relevant_artifact_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        session = self.session_store.get_session(session_id)
        turns = [ChatTurn(
            **payload) for payload in self.session_store.list_turns(session_id, include_internal=True)]
        spine = self._load_spine(session)
        pinned_atoms, retrieved_atoms = self._load_memory_atoms(
            session, current_user_message, selected_profile)
        artifacts = self._load_artifacts(session, relevant_artifact_ids)
        recent_turns, omitted_turns_count, compacted_turns_count = self._select_recent_turns(
            turns, selected_profile)

        sections: list[tuple[str, str, str]] = []
        sections.append(("system_prompt", "system",
                        self._load_system_prompt()))
        sections.append(("project_rules", "system",
                        self._project_rules(task_type)))
        if spine is not None:
            sections.append(("session_spine", "system",
                            self._format_spine(spine)))
        if pinned_atoms:
            sections.append(("pinned_memory_atoms", "system", self._format_atoms(
                "Pinned Memory Atoms", pinned_atoms)))
        if retrieved_atoms:
            sections.append(("retrieved_memory_atoms", "system", self._format_atoms(
                "Retrieved Memory Atoms", retrieved_atoms)))
        if artifacts:
            sections.append(
                ("artifacts", "system", self._format_artifacts(artifacts)))
        for turn in recent_turns:
            sections.append(
                (
                    f"turn:{turn.turn_id}",
                    self._message_role_for_turn(turn),
                    self._format_turn(turn, selected_profile),
                )
            )
        sections.append(("current_user_message", "user", current_user_message))

        messages = [{"role": role, "content": content}
                    for _, role, content in sections]
        section_char_totals = {label: len(content)
                               for label, _, content in sections}
        approximate_chars = sum(section_char_totals.values())
        report = ContextReport(
            included_sections=[label for label, _, _ in sections],
            approximate_chars=approximate_chars,
            approximate_tokens=estimate_tokens(
                "".join(content for _, _, content in sections),
                self.settings.context.approximate_token_ratio,
            ),
            section_char_totals=section_char_totals,
            memory_atoms_included=[
                atom.atom_id for atom in pinned_atoms + retrieved_atoms],
            artifacts_included=[
                artifact.artifact_id for artifact in artifacts],
            recent_turns_included=[turn.turn_id for turn in recent_turns],
            omitted_turns_count=omitted_turns_count,
            compacted_turns_count=compacted_turns_count,
            warnings=self._warnings(approximate_chars, selected_profile),
        )
        context_pack = self._build_context_pack(sections, report)
        return {
            "messages": messages,
            "context_pack": context_pack,
            "context_report": report.model_dump(),
        }

    def _load_system_prompt(self) -> str:
        prompt_path = self.root_dir / self.settings.agent.system_prompt_path
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        fallback_path = Path(__file__).resolve(
        ).parents[1] / "prompts" / "system.md"
        return fallback_path.read_text(encoding="utf-8")

    def _project_rules(self, task_type: Optional[str]) -> str:
        lines = [
            "Project Rules / Safety Rules",
            "- DeepSeek /chat/completions is stateless; all continuity must be assembled locally.",
            "- Never render raw reasoning_content in UI or context inspector outputs.",
            "- Never expose API keys, .env contents, or unrestricted shell endpoints.",
            f"- Workspace root is {self.settings.terminal.workspace_root}; path traversal outside it stays blocked.",
            f"- Tool outputs must stay within {self.settings.context.tool_output_budget_chars} chars before prompt assembly.",
        ]
        if task_type:
            lines.append(f"- Current task_type: {task_type}")
        return "\n".join(lines)

    def _load_spine(self, session: ChatSession) -> Optional[SessionSpine]:
        if not session.current_spine_id or not self.spines_path.exists():
            return None
        selected: Optional[SessionSpine] = None
        for line_number, record in read_jsonl_records(self.spines_path, quarantine_root=self.quarantine_root):
            try:
                candidate = SessionSpine(**record)
            except Exception as exc:
                quarantine_jsonl_issue(
                    source_path=self.spines_path,
                    quarantine_root=self.quarantine_root,
                    line_number=line_number,
                    raw_line=json.dumps(record, ensure_ascii=False),
                    error=f"invalid_session_spine: {exc}",
                )
                continue
            if candidate.spine_id == session.current_spine_id:
                selected = candidate
        return selected

    def _load_memory_atoms(
        self,
        session: ChatSession,
        current_user_message: str,
        selected_profile: ModelProfile,
    ) -> tuple[list[Any], list[Any]]:
        if self.memory_store is None or not self.settings.memory.enabled:
            return [], []
        pinned_atoms = []
        for atom_id in session.pinned_memory_atom_ids:
            try:
                atom = self.memory_store.get_atom(atom_id)
            except KeyError:
                continue
            if atom.enabled:
                pinned_atoms.append(atom)

        retrieved_atoms = self.memory_store.search(
            current_user_message,
            top_k=min(selected_profile.memory_atom_budget,
                      self.settings.memory.retrieval_top_k),
            pinned_atom_ids=session.pinned_memory_atom_ids,
            scope="session",
            exclude_atom_ids=[atom.atom_id for atom in pinned_atoms],
        )

        pinned_atoms = self._clip_atoms(
            pinned_atoms, self.settings.context.memory_budget_chars // 2)
        retrieved_atoms = self._clip_atoms(
            retrieved_atoms, self.settings.context.memory_budget_chars // 2)
        return pinned_atoms, retrieved_atoms

    def _load_artifacts(
        self,
        session: ChatSession,
        relevant_artifact_ids: Optional[list[str]],
    ) -> list[ArtifactRecord]:
        if self.artifact_store is None:
            return []
        ids = list(relevant_artifact_ids or session.metadata.get(
            "attached_artifact_ids", []))
        artifacts: list[ArtifactRecord] = []
        for artifact_id in ids:
            try:
                artifacts.append(self.artifact_store.get_artifact(artifact_id))
            except FileNotFoundError:
                continue
        clipped: list[ArtifactRecord] = []
        used = 0
        for artifact in artifacts:
            artifact_chars = len(self._format_artifact(artifact))
            if used + artifact_chars > self.settings.context.artifact_budget_chars:
                break
            clipped.append(artifact)
            used += artifact_chars
        return clipped

    def _select_recent_turns(
        self,
        turns: list[ChatTurn],
        selected_profile: ModelProfile,
    ) -> tuple[list[ChatTurn], int, int]:
        compacted_turns_count = sum(1 for turn in turns if turn.is_compacted)
        visible_turns = [turn for turn in turns if not turn.is_compacted]
        selected = visible_turns[-selected_profile.recent_turns_budget:]
        budget = self.settings.context.recent_turns_budget_chars
        while selected and sum(len(self._format_turn(turn, selected_profile)) for turn in selected) > budget:
            selected = selected[1:]
        omitted_turns_count = max(0, len(turns) - len(selected))
        return selected, omitted_turns_count, compacted_turns_count

    def _format_spine(self, spine: SessionSpine) -> str:
        lines = ["Session Spine", spine.summary]
        if spine.decisions:
            lines.append("Decisions:")
            lines.extend(f"- {item}" for item in spine.decisions)
        if spine.open_threads:
            lines.append("Open Threads:")
            lines.extend(f"- {item}" for item in spine.open_threads)
        return "\n".join(lines)

    def _format_atoms(self, title: str, atoms: list[Any]) -> str:
        lines = [title]
        for atom in atoms:
            lines.append(
                f"- [{atom.kind}] {atom.text} (confidence={atom.confidence:.2f}, importance={atom.importance:.2f})")
            for ref in atom.evidence_refs[:3]:
                lines.append(f"  evidence: {ref}")
        return "\n".join(lines)

    def _clip_atoms(self, atoms: list[Any], budget_chars: int) -> list[Any]:
        clipped: list[Any] = []
        used = 0
        for atom in atoms:
            length = len(atom.text)
            if used + length > budget_chars:
                break
            clipped.append(atom)
            used += length
        return clipped

    def _format_artifacts(self, artifacts: list[ArtifactRecord]) -> str:
        return "\n\n".join(self._format_artifact(artifact) for artifact in artifacts)

    def _format_artifact(self, artifact: ArtifactRecord) -> str:
        return artifact.render_compact(max_findings=5, max_refs=3)

    def _format_turn(self, turn: ChatTurn, selected_profile: ModelProfile) -> str:
        chunks = [turn.visible_content]
        if turn.tool_calls:
            chunks.append(
                f"Tool calls: {truncate_chars(json.dumps(turn.tool_calls, ensure_ascii=False), selected_profile.tool_output_budget_chars // 2)}")
        if turn.tool_results:
            chunks.append(
                f"Tool results: {truncate_chars(json.dumps(turn.tool_results, ensure_ascii=False), selected_profile.tool_output_budget_chars // 2)}")
        return "\n".join(chunk for chunk in chunks if chunk)

    def _message_role_for_turn(self, turn: ChatTurn) -> str:
        # Persisted tool turns are replayed as assistant context notes rather than
        # raw tool-role messages because the stateless API requires tool_call_id.
        if turn.role == "tool":
            return "assistant"
        return turn.role

    def _warnings(self, approximate_chars: int, selected_profile: ModelProfile) -> list[str]:
        warnings: list[str] = []
        if approximate_chars > selected_profile.context_budget_chars:
            warnings.append(
                "Context pack exceeds selected profile context_budget_chars.")
        if approximate_chars > self.settings.context.max_context_chars:
            warnings.append(
                "Context pack exceeds global context.max_context_chars.")
        return warnings

    def _build_context_pack(self, sections: list[tuple[str, str, str]], report: ContextReport) -> str:
        lines = ["# Context Pack"]
        for label, role, content in sections:
            lines.append(f"\n## {label}")
            lines.append(f"role: {role}")
            lines.append(content)
        lines.append("\n## Context Report")
        lines.append(json.dumps(report.model_dump(),
                     ensure_ascii=False, indent=2))
        return "\n".join(lines)
