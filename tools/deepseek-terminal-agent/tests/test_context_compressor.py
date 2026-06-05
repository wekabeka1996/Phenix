"""Tests for context compression and spine creation."""
from __future__ import annotations

import json

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.compressor import ContextCompressor
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": type(
            "Message", (), {"content": content})()})()]


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def chat_completions(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.content)


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


def append_turn(store: SessionStore, session_id: str, turn_id: str, role: str, text: str, *, tool_calls=None):
    store.append_turn(
        session_id,
        ChatTurn(
            turn_id=turn_id,
            session_id=session_id,
            role=role,
            visible_content=text,
            tool_calls=tool_calls or [],
            model_id="deepseek-v4-pro",
            model_profile_snapshot=make_profile().snapshot(),
        ),
    )


def test_mocked_valid_json_creates_spine_and_atoms(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    for index in range(15):
        append_turn(store, session.session_id,
                    f"turn-{index}", "assistant", f"turn {index}")

    client = FakeClient(json.dumps({
        "summary": "Compressed state",
        "decisions": ["Keep history"],
        "verified_facts": ["Chat is stateless upstream"],
        "assumptions": [],
        "open_threads": [],
        "risks": ["Need local persistence"],
        "next_actions": ["Continue session"],
        "memory_atoms": [
            {
                "scope": "session",
                "kind": "fact",
                "text": "Model switching preserves visible history",
                "evidence_refs": ["turn:turn-1"],
                "confidence": 0.9,
                "importance": 0.8,
                "ttl": "session",
                "tags": ["model", "history"],
            }
        ],
    }))
    compressor = ContextCompressor(
        settings, session_store=store, memory_store=memory, client=client, root_dir=tmp_path)
    result = compressor.compress_session(session_id=session.session_id)

    assert result["compressed"] is True
    assert result["memory_atom_ids"]
    assert store.get_session(
        session.session_id).current_spine_id == result["spine_id"]


def test_invalid_json_does_not_compact(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    for index in range(15):
        append_turn(store, session.session_id,
                    f"turn-{index}", "assistant", f"turn {index}")

    compressor = ContextCompressor(
        settings, session_store=store, memory_store=memory, client=FakeClient("not-json"), root_dir=tmp_path)
    result = compressor.compress_session(session_id=session.session_id)

    assert result["compressed"] is False
    assert store.get_session(session.session_id).current_spine_id is None


def test_raw_turns_preserved_and_recent_turns_kept(tmp_path):
    settings = make_settings()
    settings.compression.keep_recent_turns = 2
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    for index in range(10):
        append_turn(store, session.session_id,
                    f"turn-{index}", "assistant", f"turn {index}")

    compressor = ContextCompressor(
        settings,
        session_store=store,
        memory_store=memory,
        client=FakeClient(json.dumps({"summary": "Compressed", "decisions": [], "verified_facts": [
        ], "assumptions": [], "open_threads": [], "risks": [], "next_actions": [], "memory_atoms": []})),
        root_dir=tmp_path,
    )
    result = compressor.compress_session(session_id=session.session_id)
    turns = store.list_turns(session.session_id, include_internal=True)

    recent_turns = [turn for turn in turns if turn["turn_id"]
                    in {"turn-8", "turn-9"}]
    assert all(turn["is_compacted"] is False for turn in recent_turns)
    raw_file = (tmp_path / ".agent_memory" / "sessions" /
                session.session_id / "turns.dsctx.jsonl").read_text(encoding="utf-8")
    assert "turn 0" in raw_file
    assert result["compressed"] is True


def test_tool_call_result_pair_not_split(tmp_path):
    settings = make_settings()
    settings.compression.keep_recent_turns = 1
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    append_turn(store, session.session_id, "turn-a", "assistant",
                "Calling tool", tool_calls=[{"id": "tc-1"}])
    append_turn(store, session.session_id, "turn-b", "tool", "Tool result")
    append_turn(store, session.session_id, "turn-c",
                "assistant", "Recent keep turn")

    compressor = ContextCompressor(
        settings,
        session_store=store,
        memory_store=memory,
        client=FakeClient(json.dumps({"summary": "Compressed", "decisions": [], "verified_facts": [
        ], "assumptions": [], "open_threads": [], "risks": [], "next_actions": [], "memory_atoms": []})),
        root_dir=tmp_path,
    )
    result = compressor.compress_session(session_id=session.session_id)
    turns = {turn["turn_id"]: turn for turn in store.list_turns(
        session.session_id, include_internal=True)}

    assert turns["turn-a"]["compacted_into_spine_id"] == result["spine_id"]
    assert turns["turn-b"]["compacted_into_spine_id"] == result["spine_id"]


def test_compression_prompt_explicitly_demands_json(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    for index in range(15):
        append_turn(store, session.session_id,
                    f"turn-{index}", "assistant", f"turn {index}")

    client = FakeClient(json.dumps({"summary": "Compressed", "decisions": [], "verified_facts": [
    ], "assumptions": [], "open_threads": [], "risks": [], "next_actions": [], "memory_atoms": []}))
    compressor = ContextCompressor(
        settings, session_store=store, memory_store=memory, client=client, root_dir=tmp_path)
    messages, _, profile = compressor.build_compression_messages(
        session_id=session.session_id)

    assert profile.response_format == "json_object"
    assert "JSON object" in messages[0]["content"]
    assert "valid JSON only" in messages[1]["content"]


def test_secrets_redacted_in_created_memory_atoms(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    for index in range(15):
        append_turn(store, session.session_id,
                    f"turn-{index}", "assistant", f"turn {index}")

    compressor = ContextCompressor(
        settings,
        session_store=store,
        memory_store=memory,
        client=FakeClient(json.dumps({
            "summary": "Compressed",
            "decisions": [],
            "verified_facts": [],
            "assumptions": [],
            "open_threads": [],
            "risks": [],
            "next_actions": [],
            "memory_atoms": [{
                "scope": "session",
                "kind": "risk",
                "text": "api_key=sk-secret-value leaked in transcript",
                "evidence_refs": [],
                "confidence": 0.5,
                "importance": 0.5,
                "ttl": "session",
                "tags": [],
            }],
        })),
        root_dir=tmp_path,
    )
    result = compressor.compress_session(session_id=session.session_id)
    atom = memory.get_atom(result["memory_atom_ids"][0])

    assert atom.redacted is True
    assert "sk-secret-value" not in atom.text
