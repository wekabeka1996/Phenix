"""Context compression that writes session spines without deleting raw turns."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from ..config import Settings
from ..deepseek_client import DeepSeekClient
from .context_loss import generate_loss_report
from .memory_atoms import MemoryAtom, MemoryAtomStore
from .models import ChatTurn, ModelProfile, SessionSpine
from .persistence import append_jsonl_record, write_json_atomic
from .store import SessionStore


class ContextCompressor:
    def __init__(
        self,
        settings: Settings,
        *,
        session_store: SessionStore,
        memory_store: MemoryAtomStore,
        client: Optional[DeepSeekClient] = None,
        root_dir: str | Path = ".",
    ) -> None:
        self.settings = settings
        self.session_store = session_store
        self.memory_store = memory_store
        self.client = client or DeepSeekClient(settings.deepseek)
        self.root_dir = Path(root_dir)
        self.spines_path = self.root_dir / ".agent_memory" / "session_spines.dsspine.jsonl"
        self.spines_path.parent.mkdir(parents=True, exist_ok=True)
        self.loss_reports_dir = self.root_dir / ".agent_memory" / "loss_reports"
        self.loss_reports_dir.mkdir(parents=True, exist_ok=True)

    def build_compression_messages(
        self,
        *,
        session_id: str,
        selected_profile: Optional[ModelProfile] = None,
    ) -> tuple[list[dict[str, str]], list[ChatTurn], ModelProfile]:
        profile = selected_profile or self._compression_profile()
        turns = [ChatTurn(
            **payload) for payload in self.session_store.list_turns(session_id, include_internal=True)]
        source_turns = self._select_source_turns(turns)
        transcript = "\n\n".join(
            f"[{turn.role}] {turn.visible_content}" for turn in source_turns
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You compress prior chat history into strict JSON. "
                    "Return only a JSON object matching the requested schema with keys: "
                    "summary, decisions, verified_facts, assumptions, open_threads, risks, next_actions, memory_atoms."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Summarize the following transcript into valid JSON only. "
                    "Preserve factual claims, decisions, risks, and compact memory atoms.\n\n"
                    f"Transcript:\n{transcript}"
                ),
            },
        ]
        return messages, source_turns, profile

    def compress_session(
        self,
        *,
        session_id: str,
        selected_profile: Optional[ModelProfile] = None,
    ) -> dict[str, Any]:
        messages, source_turns, profile = self.build_compression_messages(
            session_id=session_id,
            selected_profile=selected_profile,
        )
        if not source_turns:
            return {"compressed": False, "reason": "nothing_to_compact"}

        response = self.client.chat_completions(
            messages=messages, model_profile=profile)
        raw_content = response.choices[0].message.content or ""
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            return {"compressed": False, "reason": "invalid_json"}

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            return {"compressed": False, "reason": "empty_summary"}

        spine_id = uuid.uuid4().hex
        spine = SessionSpine(
            spine_id=spine_id,
            session_id=session_id,
            summary=summary,
            decisions=[str(item) for item in payload.get("decisions", [])],
            verified_facts=[str(item)
                            for item in payload.get("verified_facts", [])],
            assumptions=[str(item) for item in payload.get("assumptions", [])],
            open_threads=[str(item)
                          for item in payload.get("open_threads", [])],
            risks=[str(item) for item in payload.get("risks", [])],
            next_actions=[str(item)
                          for item in payload.get("next_actions", [])],
            source_turn_ids=[turn.turn_id for turn in source_turns],
        )
        append_jsonl_record(self.spines_path, spine.model_dump())

        created_atoms: list[str] = []
        for item in payload.get("memory_atoms", []):
            atom = self.memory_store.add_atom(
                MemoryAtom(
                    scope=str(item.get("scope") or "session"),
                    kind=item.get("kind") or "fact",
                    text=str(item.get("text") or "").strip(),
                    evidence_refs=[str(ref)
                                   for ref in item.get("evidence_refs", [])],
                    confidence=float(item.get("confidence", 0.5)),
                    importance=float(item.get("importance", 0.5)),
                    ttl=item.get("ttl") or "session",
                    source_session_id=session_id,
                    source_turn_ids=[turn.turn_id for turn in source_turns],
                    tags=[str(tag) for tag in item.get("tags", [])],
                )
            )
            created_atoms.append(atom.atom_id)

        for turn in source_turns:
            self.session_store.update_turn(
                session_id,
                turn.turn_id,
                is_compacted=True,
                compacted_into_spine_id=spine_id,
            )

        session = self.session_store.get_session(session_id)
        session.current_spine_id = spine_id
        self.session_store.save_session(session)

        # Write LossReport — raw turns preserved, this documents what was compressed
        source_chars = sum(len(turn.visible_content) for turn in source_turns)
        compressed_chars = len(summary)
        loss_report = generate_loss_report(
            session_id=session_id,
            source_turn_ids=[turn.turn_id for turn in source_turns],
            spine_summary=summary,
            omitted_items=[turn.visible_content[:120]
                           for turn in source_turns],
            preserved_facts=[str(item)
                             for item in payload.get("verified_facts", [])],
            source_chars=source_chars,
            compressed_chars=compressed_chars,
        )
        loss_report_path = self.loss_reports_dir / \
            f"{loss_report.loss_report_id}.dsloss.json"
        write_json_atomic(loss_report_path, loss_report.model_dump())

        return {
            "compressed": True,
            "spine_id": spine_id,
            "source_turn_ids": [turn.turn_id for turn in source_turns],
            "memory_atom_ids": created_atoms,
            "loss_report_id": loss_report.loss_report_id,
        }

    def _compression_profile(self) -> ModelProfile:
        return ModelProfile(
            profile_id="json-compressor",
            name="JSON Compressor",
            model_id=self.settings.compression.model_id,
            thinking_type=self.settings.compression.thinking_type,
            reasoning_effort="high",
            temperature=0.0,
            top_p=1.0,
            max_tokens=4096,
            response_format="json_object",
            stream=False,
            tool_mode="none",
            max_iterations=4,
            command_timeout_sec=60,
            max_command_output_chars=4000,
            context_budget_chars=self.settings.compression.target_chars,
            memory_atom_budget=self.settings.memory.retrieval_top_k,
            recent_turns_budget=self.settings.compression.keep_recent_turns,
            tool_output_budget_chars=8000,
        )

    def _select_source_turns(self, turns: list[ChatTurn]) -> list[ChatTurn]:
        uncompacted = [turn for turn in turns if not turn.is_compacted]
        if len(uncompacted) <= self.settings.compression.keep_recent_turns:
            return []
        candidates = uncompacted[: -
                                 self.settings.compression.keep_recent_turns]
        if len(candidates) > self.settings.compression.max_source_turns:
            candidates = candidates[-self.settings.compression.max_source_turns:]
        return self._preserve_tool_pairs(candidates, turns)

    def _preserve_tool_pairs(self, selected: list[ChatTurn], all_turns: list[ChatTurn]) -> list[ChatTurn]:
        selected_ids = {turn.turn_id for turn in selected}
        by_id = {turn.turn_id: idx for idx, turn in enumerate(all_turns)}
        for turn in list(selected):
            if turn.role == "assistant" and turn.tool_calls:
                index = by_id[turn.turn_id]
                if index + 1 < len(all_turns) and all_turns[index + 1].role == "tool":
                    selected_ids.add(all_turns[index + 1].turn_id)
            if turn.role == "tool":
                index = by_id[turn.turn_id]
                if index - 1 >= 0 and all_turns[index - 1].role == "assistant" and all_turns[index - 1].tool_calls:
                    selected_ids.add(all_turns[index - 1].turn_id)
        return [turn for turn in all_turns if turn.turn_id in selected_ids and not turn.is_compacted]
