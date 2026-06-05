"""Tests for context codec — ContextUnit encode/decode."""
from __future__ import annotations

from deepseek_terminal_agent.sessions.context_codec import (
    decode_units_to_context_pack,
    encode_artifact_to_units,
    encode_spine_to_units,
    encode_turns_to_units,
)
from deepseek_terminal_agent.sessions.context_units import ContextUnit
from deepseek_terminal_agent.sessions.models import (
    ArtifactFinding,
    ArtifactRecord,
    ChatTurn,
    SessionSpine,
)


def make_turn(turn_id: str, role: str, content: str, session_id: str = "sess-1") -> ChatTurn:
    return ChatTurn(
        turn_id=turn_id,
        session_id=session_id,
        role=role,
        visible_content=content,
        model_id="deepseek-v4-pro",
    )


def test_encode_turns_produces_units():
    turns = [
        make_turn("t1", "user", "Hello world"),
        make_turn("t2", "assistant", "Hi there"),
    ]
    units = encode_turns_to_units(turns)
    assert len(units) == 2
    assert units[0].unit_type == "turn"
    assert units[0].text == "Hello world"
    assert units[1].text == "Hi there"
    assert units[0].unit_id == "turn:t1"


def test_encode_turns_empty():
    units = encode_turns_to_units([])
    assert units == []


def test_encode_artifact_to_units():
    artifact = ArtifactRecord(
        artifact_id="art-1",
        artifact_type="evidence_pack",
        parent_session_id="sess-1",
        child_session_id="sess-2",
        role="ScoutAgent",
        task="Analyze repo",
        summary="Found 3 critical files",
        findings=[
            ArtifactFinding(
                claim="File X has 3 issues",
                evidence_refs=["file:path/x.py#line:10"],
                confidence=0.9,
            )
        ],
    )
    units = encode_artifact_to_units(artifact)
    assert len(units) == 2  # artifact summary + finding
    assert units[0].unit_type == "artifact"
    assert units[0].semantic_role == "evidence"
    assert units[1].confidence == 0.9


def test_encode_spine_to_units():
    spine = SessionSpine(
        spine_id="sp-1",
        session_id="sess-1",
        summary="Prior context summary",
        decisions=["Use approach X", "Skip Y"],
    )
    units = encode_spine_to_units(spine)
    # summary + 2 decisions
    assert len(units) == 3
    assert units[0].unit_type == "spine"
    assert units[0].text == "Prior context summary"
    for unit in units[1:]:
        assert unit.unit_type == "decision"
        assert unit.semantic_role == "decision"


def test_decode_units_to_context_pack_within_budget():
    units = [
        ContextUnit(unit_id="u1", unit_type="turn", text="Short turn"),
        ContextUnit(unit_id="u2", unit_type="memory_atom", text="Memory fact"),
    ]
    result = decode_units_to_context_pack(units, budget_chars=10000)
    assert "u1" in result["included_unit_ids"]
    assert "u2" in result["included_unit_ids"]
    assert "context_pack" in result
    assert result["excluded_unit_ids"] == []


def test_decode_units_respects_budget():
    big_text = "x" * 5000
    units = [
        ContextUnit(unit_id="u1", unit_type="turn", text=big_text),
        ContextUnit(unit_id="u2", unit_type="turn", text=big_text),
        ContextUnit(unit_id="u3", unit_type="turn", text=big_text),
    ]
    result = decode_units_to_context_pack(units, budget_chars=8000)
    # Should not include all 3 (15000 chars total > 8000 budget)
    assert len(result["included_unit_ids"]) < 3
    assert len(result["excluded_unit_ids"]) >= 1


def test_context_unit_pydantic_validation():
    unit = ContextUnit(
        unit_id="test",
        unit_type="turn",
        semantic_role="fact",
        text="test text",
        confidence=0.8,
        importance=0.6,
    )
    assert unit.confidence == 0.8
    assert unit.schema_version == 1


def test_context_unit_invalid_confidence():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ContextUnit(unit_id="x", unit_type="turn", confidence=1.5)
