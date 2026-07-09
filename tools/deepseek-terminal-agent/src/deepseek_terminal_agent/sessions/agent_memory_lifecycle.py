"""Runtime lifecycle adapter for trading-session memory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import Settings
from .agent_trading_memory import AgentTradingSessionMemory, ReflectionEntry
from .persistence import write_json_atomic, write_text_atomic


class AgentMemoryLifecycle:
    """Persist and update one append-only memory document per session/agent."""

    MEMORY_NAME = "agent_trading_memory.json"
    SUMMARY_NAME = "agent_trading_memory.summary.json"
    CARRYOVER_NAME = "agent_trading_session_carryover.md"

    def __init__(self, settings: Settings, *, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.sessions_root = self.root_dir / settings.sessions.root_dir

    def attach_identity(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        instruction_manifest_version: str = "p39d-runtime-v1",
    ) -> AgentTradingSessionMemory:
        memory = self.load_or_create(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            instruction_manifest_version=instruction_manifest_version,
        )
        self._write_memory(memory)
        return memory

    def load_or_create(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        instruction_manifest_version: str = "p39d-runtime-v1",
    ) -> AgentTradingSessionMemory:
        path = self._memory_path(session_id, agent_id)
        if path.exists():
            memory = AgentTradingSessionMemory(**json.loads(path.read_text(encoding="utf-8")))
            if memory.agent_number != agent_number:
                raise ValueError("agent_number does not match existing memory")
            return memory
        return AgentTradingSessionMemory(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            instruction_manifest_version=instruction_manifest_version,
        )

    def append_instruction_ack(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        instruction_manifest_version: str,
    ) -> AgentTradingSessionMemory:
        memory = self.load_or_create(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
            instruction_manifest_version=instruction_manifest_version,
        )
        memory.append_event_ref(event_id)
        memory.append_context_ref(f"instruction_manifest:{instruction_manifest_version}")
        self._write_memory(memory)
        return memory

    def append_rationale_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        command_id: str,
        rationale: str,
        reflection_id: str | None = None,
    ) -> AgentTradingSessionMemory:
        memory = self.load_or_create(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )
        memory.append_event_ref(event_id)
        memory.append_reflection(
            ReflectionEntry(
                reflection_id=reflection_id or f"reflection-{uuid4().hex}",
                session_id=session_id,
                agent_id=agent_id,
                kind="opening_assumptions",
                related_event_ids=[event_id],
                related_command_ids=[command_id],
                content=rationale,
            ),
            token_estimate=max(1, len(rationale.split())),
        )
        self._write_memory(memory)
        return memory

    def append_fsm_decision(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
        event_id: str,
        command_id: str,
        accepted: bool,
        reason: str,
        reflection_id: str | None = None,
    ) -> AgentTradingSessionMemory:
        memory = self.load_or_create(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )
        memory.append_event_ref(event_id)
        memory.append_reflection(
            ReflectionEntry(
                reflection_id=reflection_id or f"decision-review-{uuid4().hex}",
                session_id=session_id,
                agent_id=agent_id,
                kind="decision_review",
                related_event_ids=[event_id],
                related_command_ids=[command_id],
                content=f"FSM handoff {'accepted' if accepted else 'rejected'}: {reason}",
            ),
            token_estimate=max(1, len(reason.split()) + 4),
        )
        self._write_memory(memory)
        return memory

    def finalize_session(
        self,
        *,
        session_id: str,
        agent_id: str,
        agent_number: int,
    ) -> dict[str, Any]:
        memory = self.load_or_create(
            session_id=session_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )
        summary = memory.compact_summary()
        carryover_md = memory.next_session_carryover_md()
        session_dir = self._agent_dir(session_id, agent_id)
        write_json_atomic(session_dir / self.SUMMARY_NAME, summary)
        write_text_atomic(session_dir / self.CARRYOVER_NAME, carryover_md)
        return {"memory": memory.model_dump(mode="json"), "summary": summary, "carryover_md": carryover_md}

    def read_memory(self, *, session_id: str, agent_id: str, agent_number: int) -> dict[str, Any]:
        memory = self.load_or_create(session_id=session_id, agent_id=agent_id, agent_number=agent_number)
        return {"memory": memory.model_dump(mode="json"), "summary": memory.compact_summary()}

    def _write_memory(self, memory: AgentTradingSessionMemory) -> Path:
        return write_json_atomic(
            self._memory_path(memory.session_id, memory.agent_id),
            memory.model_dump(mode="json"),
        )

    def _memory_path(self, session_id: str, agent_id: str) -> Path:
        return self._agent_dir(session_id, agent_id) / self.MEMORY_NAME

    def _agent_dir(self, session_id: str, agent_id: str) -> Path:
        safe_session = self._safe_segment(session_id, "session_id")
        safe_agent = self._safe_segment(agent_id, "agent_id")
        return self.sessions_root / safe_session / "agent_trading_memory" / safe_agent

    @staticmethod
    def _safe_segment(value: str, field: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned or any(part in cleaned for part in ("..", "/", "\\")):
            raise ValueError(f"{field} must be a safe path segment")
        return cleaned
