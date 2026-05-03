"""User-facing context inspection helpers built on top of ContextBuilder."""
from __future__ import annotations

from typing import Any, Optional

from .context_builder import ContextBuilder
from .models import ModelProfile


class ContextInspector:
    def __init__(self, builder: ContextBuilder) -> None:
        self.builder = builder

    def inspect(
        self,
        *,
        session_id: str,
        current_user_message: str,
        selected_profile: ModelProfile,
        relevant_artifact_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        built = self.builder.build(
            session_id=session_id,
            current_user_message=current_user_message,
            selected_profile=selected_profile,
            relevant_artifact_ids=relevant_artifact_ids,
        )
        report = built["context_report"]
        section_totals = report.get("section_char_totals", {})
        contributors = [
            {"section": section, "chars": chars}
            for section, chars in sorted(section_totals.items(), key=lambda item: item[1], reverse=True)
        ]
        return {
            "session_id": session_id,
            "active_profile": selected_profile.snapshot(),
            "estimated_context_usage": {
                "chars": report["approximate_chars"],
                "tokens": report["approximate_tokens"],
            },
            "system_project_rules_size": section_totals.get("system_prompt", 0) + section_totals.get("project_rules", 0),
            "session_spine_size": section_totals.get("session_spine", 0),
            "memory_atoms_included": report.get("memory_atoms_included", []),
            "artifacts_included": report.get("artifacts_included", []),
            "recent_turns_included": report.get("recent_turns_included", []),
            "top_context_contributors": contributors[:5],
            "warnings": report.get("warnings", []),
            "context_pack": built["context_pack"],
            "context_report": report,
        }
