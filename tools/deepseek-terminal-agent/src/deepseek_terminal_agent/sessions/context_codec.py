"""Encode turns and artifacts to ContextUnits and decode back to context packs."""
from __future__ import annotations

import uuid
from typing import Any

from .context_units import ContextUnit, SemanticRole
from .models import ArtifactRecord, ChatTurn, SessionSpine


def _classify_role(turn: ChatTurn) -> SemanticRole:
    if turn.role == "user":
        return "fact"
    if turn.tool_results:
        return "result"
    return "fact"


def encode_turns_to_units(turns: list[ChatTurn]) -> list[ContextUnit]:
    """Encode a list of chat turns to ContextUnits (non-destructive)."""
    units: list[ContextUnit] = []
    for turn in turns:
        units.append(
            ContextUnit(
                unit_id=f"turn:{turn.turn_id}",
                unit_type="turn",
                semantic_role=_classify_role(turn),
                scope=turn.session_id,
                text=turn.visible_content,
                source_refs=[f"turn:{turn.turn_id}"],
                confidence=1.0,
                importance=1.0,
                created_at=turn.created_at,
            )
        )
    return units


def encode_artifact_to_units(artifact: ArtifactRecord) -> list[ContextUnit]:
    """Encode an artifact and its findings to ContextUnits."""
    units: list[ContextUnit] = []
    units.append(
        ContextUnit(
            unit_id=f"artifact:{artifact.artifact_id}",
            unit_type="artifact",
            semantic_role="evidence",
            scope=artifact.parent_session_id,
            text=artifact.render_compact(),
            source_refs=[f"artifact:{artifact.artifact_id}"],
            confidence=1.0,
            importance=0.8,
            created_at=artifact.created_at,
        )
    )
    for finding in artifact.findings:
        units.append(
            ContextUnit(
                unit_id=f"finding:{uuid.uuid4().hex}",
                unit_type="artifact",
                semantic_role="evidence",
                scope=artifact.parent_session_id,
                text=finding.claim,
                source_refs=finding.evidence_refs,
                confidence=finding.confidence,
                importance=finding.confidence,
                created_at=artifact.created_at,
            )
        )
    return units


def encode_spine_to_units(spine: SessionSpine) -> list[ContextUnit]:
    """Encode a session spine to ContextUnits."""
    units: list[ContextUnit] = []
    if spine.summary:
        units.append(
            ContextUnit(
                unit_id=f"spine:{spine.spine_id}:summary",
                unit_type="spine",
                semantic_role="fact",
                scope=spine.session_id,
                text=spine.summary,
                source_refs=[f"spine:{spine.spine_id}"],
                confidence=0.9,
                importance=0.9,
                created_at=spine.created_at,
            )
        )
    for decision in spine.decisions:
        units.append(
            ContextUnit(
                unit_id=f"spine:{spine.spine_id}:decision:{uuid.uuid4().hex}",
                unit_type="decision",
                semantic_role="decision",
                scope=spine.session_id,
                text=decision,
                source_refs=[f"spine:{spine.spine_id}"],
                confidence=0.85,
                importance=0.9,
                created_at=spine.created_at,
            )
        )
    return units


def decode_units_to_context_pack(
    units: list[ContextUnit],
    *,
    budget_chars: int = 80000,
    label: str = "context_pack",
) -> dict[str, Any]:
    """Decode ContextUnits to a context pack string respecting a char budget.

    Returns the pack text and a list of included/excluded unit IDs.
    """
    included: list[ContextUnit] = []
    excluded: list[ContextUnit] = []
    used = 0
    for unit in sorted(units, key=lambda u: (-(u.importance + u.confidence), u.created_at)):
        if used + len(unit.text) <= budget_chars:
            included.append(unit)
            used += len(unit.text)
        else:
            excluded.append(unit)

    lines = [f"# {label}"]
    for unit in included:
        lines.append(f"\n## [{unit.unit_type}] {unit.unit_id}")
        lines.append(
            f"role={unit.semantic_role} confidence={unit.confidence:.2f}")
        lines.append(unit.text)

    return {
        "context_pack": "\n".join(lines),
        "included_unit_ids": [u.unit_id for u in included],
        "excluded_unit_ids": [u.unit_id for u in excluded],
        "used_chars": used,
    }
