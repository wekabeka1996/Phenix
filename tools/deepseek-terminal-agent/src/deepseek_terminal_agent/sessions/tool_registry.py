"""Tool registry — typed schema + YAML loader for agent tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

ToolRiskLevel = Literal["low", "medium", "high", "critical"]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    tool_id: str = Field(..., min_length=1)
    description: str = ""
    risk_level: ToolRiskLevel = "low"
    allowed_agents: list[str] = Field(default_factory=list)
    approval_required: bool = False
    audit_logging: bool = True
    rollback_expectation: str = ""
    enabled: bool = True
    manual_only: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def requires_approval(self, agent_role: str = "") -> bool:
        if self.manual_only:
            return True
        if self.approval_required:
            return True
        if self.risk_level in ("high", "critical"):
            return True
        return False


class ToolRegistry:
    """Load and serve tool definitions from a YAML file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._tools: Optional[dict[str, ToolDefinition]] = None

    def _load(self) -> dict[str, ToolDefinition]:
        if not self.path.exists():
            return {}
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("tool_registry YAML must be a mapping")
        entries = raw.get("tools", [])
        if not isinstance(entries, list):
            raise ValueError("tools must be a list")
        return {t.tool_id: t for entry in entries for t in [ToolDefinition(**entry)]}

    def _ensure_loaded(self) -> dict[str, ToolDefinition]:
        if self._tools is None:
            self._tools = self._load()
        return self._tools

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._ensure_loaded().values())

    def get_tool(self, tool_id: str) -> ToolDefinition:
        tools = self._ensure_loaded()
        if tool_id not in tools:
            raise KeyError(f"Tool '{tool_id}' not found")
        return tools[tool_id]

    def is_allowed(self, tool_id: str, agent_role: str = "") -> bool:
        try:
            tool = self.get_tool(tool_id)
        except KeyError:
            return False
        if not tool.enabled:
            return False
        if tool.manual_only:
            return False
        if tool.allowed_agents and agent_role and agent_role not in tool.allowed_agents:
            return False
        return True

    def invalidate_cache(self) -> None:
        self._tools = None
