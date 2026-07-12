"""Read-only compatibility access for historical P39D memory artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Settings
from .agent_trading_memory import AgentTradingSessionMemory


class LegacyAgentMemoryReader:
    """Reads legacy memory without exposing any mutation operation."""

    MEMORY_NAME = "agent_trading_memory.json"

    def __init__(self, settings: Settings, *, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        if not self.root_dir.is_absolute():
            raise ValueError("root_dir must be absolute")
        self.sessions_root = self.root_dir / settings.sessions.root_dir

    def read_memory(
        self, *, session_id: str, agent_id: str, agent_number: int
    ) -> dict[str, Any]:
        path = self._memory_path(session_id, agent_id)
        if not path.exists():
            raise FileNotFoundError(f"legacy memory not found: {path}")
        memory = AgentTradingSessionMemory.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if memory.agent_number != agent_number:
            raise ValueError("agent_number does not match legacy memory")
        return {
            "memory": memory.model_dump(mode="json"),
            "summary": memory.compact_summary(),
            "compatibility": "read_only_legacy",
        }

    def _memory_path(self, session_id: str, agent_id: str) -> Path:
        return (
            self.sessions_root
            / self._safe_segment(session_id, "session_id")
            / "agent_trading_memory"
            / self._safe_segment(agent_id, "agent_id")
            / self.MEMORY_NAME
        )

    @staticmethod
    def _safe_segment(value: str, field: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned or any(part in cleaned for part in ("..", "/", "\\")):
            raise ValueError(f"{field} must be a safe path segment")
        return cleaned


# Import compatibility only. The aliased class has no write methods.
AgentMemoryLifecycle = LegacyAgentMemoryReader
