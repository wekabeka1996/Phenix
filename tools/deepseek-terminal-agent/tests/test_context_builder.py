"""Tests for deterministic context assembly and budgeting."""
from __future__ import annotations

import json

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtom, MemoryAtomStore
from deepseek_terminal_agent.sessions.models import (
    ArtifactFinding,
    ArtifactRecord,
    ChatTurn,
    ModelProfile,
    SessionSpine,
)
from deepseek_terminal_agent.sessions.store import SessionStore


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_profile() -> ModelProfile:
    return ModelProfile(
        profile_id="profile-a",
        name="Profile A",
        model_id="deepseek-v4-pro",
        thinking_type="enabled",
        reasoning_effort="high",
        temperature=0.2,
        top_p=1.0,
        max_tokens=4096,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=6,
        command_timeout_sec=30,
        max_command_output_chars=1200,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=3,
        tool_output_budget_chars=1500,
    )


def write_spine(tmp_path, session_id: str, spine_id: str = "spine-1") -> None:
    path = tmp_path / ".agent_memory" / "session_spines.dsspine.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            SessionSpine(
                spine_id=spine_id,
                session_id=session_id,
                summary="Compressed session summary",
                decisions=["Keep recent turns intact"],
            ).model_dump(),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def append_turn(store: SessionStore, session_id: str, turn_id: str, role: str, text: str, *, compacted: bool = False) -> None:
    store.append_turn(
        session_id,
        ChatTurn(
            turn_id=turn_id,
            session_id=session_id,
            role=role,
            visible_content=text,
            model_id="deepseek-v4-pro",
            model_profile_snapshot=make_profile().snapshot(),
            is_compacted=compacted,
            compacted_into_spine_id="spine-1" if compacted else None,
        ),
    )


def test_stable_order_and_context_report(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    session.current_spine_id = "spine-1"
    store.update_session_profile(session.session_id, session.active_profile)
    session_path = tmp_path / ".agent_memory" / "sessions" / \
        session.session_id / "session.dsstate.json"
    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    session_payload["current_spine_id"] = "spine-1"
    session_path.write_text(json.dumps(
        session_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    write_spine(tmp_path, session.session_id)
    pinned = memory.add_atom(MemoryAtom(
        scope="session", kind="fact", text="Pinned session fact", importance=0.9))
    retrieved = memory.add_atom(MemoryAtom(scope="session", kind="todo",
                                text="Retrieve memory atoms for context builder", importance=0.7, tags=["context"]))
    session_state = store.get_session(session.session_id)
    session_state.pinned_memory_atom_ids = [pinned.atom_id]
    store._write_session_state(session_state)
    artifact = ArtifactRecord(
        artifact_id="artifact-1",
        artifact_type="evidence_pack",
        parent_session_id=session.session_id,
        child_session_id="child-1",
        role="ScoutAgent",
        task="scan repo",
        summary="Useful evidence pack",
        findings=[ArtifactFinding(claim="Workspace root is mounted", evidence_refs=[
                                  "command:pwd"], confidence=0.8)],
    )
    artifacts.write_artifact(artifact)
    session_state = store.get_session(session.session_id)
    session_state.metadata["attached_artifact_ids"] = [artifact.artifact_id]
    store._write_session_state(session_state)

    append_turn(store, session.session_id, "turn-1",
                "user", "Older user turn", compacted=True)
    append_turn(store, session.session_id, "turn-2",
                "assistant", "Recent assistant turn")
    append_turn(store, session.session_id, "turn-3",
                "user", "Recent user turn")

    builder = ContextBuilder(settings, session_store=store,
                             memory_store=memory, artifact_store=artifacts, root_dir=tmp_path)
    built = builder.build(session_id=session.session_id,
                          current_user_message="Build context with memory", selected_profile=make_profile())
    messages = built["messages"]
    report = built["context_report"]

    assert [message["role"] for message in messages[:6]] == [
        "system", "system", "system", "system", "system", "system"]
    assert report["included_sections"][:6] == [
        "system_prompt",
        "project_rules",
        "session_spine",
        "pinned_memory_atoms",
        "retrieved_memory_atoms",
        "artifacts",
    ]
    assert pinned.atom_id in report["memory_atoms_included"]
    assert retrieved.atom_id in report["memory_atoms_included"]
    assert artifact.artifact_id in report["artifacts_included"]
    assert "turn-1" not in report["recent_turns_included"]
    assert report["compacted_turns_count"] == 1


def test_budgeting_and_deterministic_output(tmp_path):
    settings = make_settings()
    settings.context.recent_turns_budget_chars = 40
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    append_turn(store, session.session_id, "turn-1", "assistant",
                "This is a very long assistant message that should be trimmed by the recent turn budget")
    append_turn(store, session.session_id, "turn-2", "user", "Short")

    builder = ContextBuilder(settings, session_store=store, root_dir=tmp_path)
    built_one = builder.build(session_id=session.session_id,
                              current_user_message="hello", selected_profile=make_profile())
    built_two = builder.build(session_id=session.session_id,
                              current_user_message="hello", selected_profile=make_profile())

    assert built_one["context_pack"] == built_two["context_pack"]
    assert built_one["context_report"]["approximate_chars"] <= settings.context.max_context_chars


def test_context_pack_excludes_hidden_reasoning(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    store.append_turn(
        session.session_id,
        ChatTurn(
            turn_id="turn-1",
            session_id=session.session_id,
            role="assistant",
            visible_content="Visible text",
            internal_reasoning_content="hidden reasoning",
            model_id="deepseek-v4-pro",
            model_profile_snapshot=make_profile().snapshot(),
        ),
    )

    builder = ContextBuilder(settings, session_store=store, root_dir=tmp_path)
    built = builder.build(session_id=session.session_id,
                          current_user_message="hello", selected_profile=make_profile())
    assert "hidden reasoning" not in built["context_pack"]


def test_persisted_tool_turns_are_replayed_as_assistant_context(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    store.append_turn(
        session.session_id,
        ChatTurn(
            turn_id="turn-1",
            session_id=session.session_id,
            role="assistant",
            visible_content="I will inspect the workspace.",
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "run_terminal_cmd", "arguments": '{"cmd":"pwd"}'},
                }
            ],
            model_id="deepseek-v4-pro",
            model_profile_snapshot=make_profile().snapshot(),
        ),
    )
    store.append_turn(
        session.session_id,
        ChatTurn(
            turn_id="turn-2",
            session_id=session.session_id,
            role="tool",
            visible_content="pwd -> /workspace/project",
            tool_results=[{"cmd": "pwd", "stdout": "/workspace/project"}],
            model_id="deepseek-v4-pro",
            model_profile_snapshot=make_profile().snapshot(),
        ),
    )

    builder = ContextBuilder(settings, session_store=store, root_dir=tmp_path)
    built = builder.build(session_id=session.session_id,
                          current_user_message="continue", selected_profile=make_profile())

    historical_messages = built["messages"][:-1]
    assert any(message["role"] == "assistant" and "Tool results:" in message["content"]
               for message in historical_messages)
    assert not any(message["role"] ==
                   "tool" for message in historical_messages)


def test_context_report_warnings_when_profile_budget_exceeded(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    append_turn(store, session.session_id, "turn-1", "assistant", "x" * 500)

    profile = make_profile()
    profile.context_budget_chars = 100
    builder = ContextBuilder(settings, session_store=store, root_dir=tmp_path)
    built = builder.build(session_id=session.session_id,
                          current_user_message="hello", selected_profile=profile)
    assert built["context_report"]["warnings"]
