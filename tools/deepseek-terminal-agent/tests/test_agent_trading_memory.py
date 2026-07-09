from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.agent_trading_memory import (
    AgentTradingSessionMemory,
    ReflectionEntry,
)


def make_memory() -> AgentTradingSessionMemory:
    return AgentTradingSessionMemory(
        session_id="session-1",
        agent_id="agent-1",
        agent_number=4,
        instruction_manifest_version="manifest-v1",
    )


def test_append_only_memory_from_runtime_event():
    memory = make_memory()

    memory.append_event_ref("event-1")
    memory.append_reflection(
        ReflectionEntry(
            reflection_id="reflection-1",
            session_id="session-1",
            agent_id="agent-1",
            kind="opening_assumptions",
            related_event_ids=["event-1"],
            content="Rationale recorded for strategic 30m review.",
        ),
        token_estimate=7,
    )

    assert memory.event_refs == ["event-1"]
    assert memory.reflection_refs == ["reflection-1"]
    assert memory.tokens_consumed_estimate == 7


def test_no_missing_agent_session_identity():
    memory = make_memory()

    with pytest.raises(ValueError, match="session_id"):
        memory.append_reflection(
            ReflectionEntry(
                reflection_id="reflection-2",
                session_id="other-session",
                agent_id="agent-1",
                kind="opening_assumptions",
                content="Wrong session should not append.",
            )
        )

    with pytest.raises(ValueError, match="agent_id"):
        memory.append_reflection(
            ReflectionEntry(
                reflection_id="reflection-3",
                session_id="session-1",
                agent_id="other-agent",
                kind="opening_assumptions",
                content="Wrong agent should not append.",
            )
        )


def test_duplicate_reflection_id_rejected():
    memory = make_memory()
    entry = ReflectionEntry(
        reflection_id="reflection-1",
        session_id="session-1",
        agent_id="agent-1",
        kind="decision_review",
        content="FSM handoff rejected for missing notional.",
    )

    memory.append_reflection(entry)

    with pytest.raises(ValueError, match="duplicate reflection_id"):
        memory.append_reflection(entry)


def test_compact_summary_and_carryover_generated():
    memory = make_memory()
    memory.append_event_ref("event-1")
    memory.append_reflection(
        ReflectionEntry(
            reflection_id="reflection-1",
            session_id="session-1",
            agent_id="agent-1",
            kind="decision_review",
            related_event_ids=["event-1"],
            related_command_ids=["command-1"],
            content="FSM rejected unsafe order payload.",
        )
    )

    summary = memory.compact_summary()
    carryover = memory.next_session_carryover_md()

    assert summary["total_reflections"] == 1
    assert summary["reflection_kind_counts"] == {"decision_review": 1}
    assert "Agent Session Carryover" in carryover
    assert "FSM rejected unsafe order payload." in carryover
