"""Tests for the disk-backed SessionStore."""
from __future__ import annotations

import json

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile, SessionEvent
from deepseek_terminal_agent.sessions.store import SessionStore


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_profile(**overrides) -> ModelProfile:
    payload = {
        "profile_id": "profile-a",
        "name": "Profile A",
        "model_id": "deepseek-v4-pro",
        "thinking_type": "enabled",
        "reasoning_effort": "high",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 2048,
        "response_format": "text",
        "stream": False,
        "tool_mode": "auto",
        "max_iterations": 6,
        "command_timeout_sec": 30,
        "max_command_output_chars": 1200,
        "context_budget_chars": 20000,
        "memory_atom_budget": 4,
        "recent_turns_budget": 8,
        "tool_output_budget_chars": 3000,
    }
    payload.update(overrides)
    return ModelProfile(**payload)


def make_turn(session_id: str, turn_id: str, **overrides) -> ChatTurn:
    payload = {
        "turn_id": turn_id,
        "session_id": session_id,
        "role": "assistant",
        "visible_content": "Visible answer",
        "internal_reasoning_content": "internal hidden",
        "tool_calls": [],
        "tool_results": [],
        "model_id": "deepseek-v4-pro",
        "model_profile_snapshot": make_profile().snapshot(),
        "source_run_id": "run-1",
    }
    payload.update(overrides)
    return ChatTurn(**payload)


def test_create_list_and_load_session(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)

    session = store.create_session(title="Alpha")
    listed = store.list_sessions()
    loaded = store.get_session(session.session_id)

    assert listed[0].session_id == session.session_id
    assert loaded.title == "Alpha"


def test_append_turns_and_events(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(title="Beta")

    store.append_turn(session.session_id, make_turn(
        session.session_id, "turn-1"))
    store.append_event(
        session.session_id,
        SessionEvent(
            event_id="evt-1",
            session_id=session.session_id,
            event_type="status",
            message="running",
        ),
    )

    assert len(store.list_turns(session.session_id)) == 1
    assert len(store.list_events(session.session_id)) == 1


def test_restart_reload_reads_session_from_disk(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(title="Gamma")

    reloaded = SessionStore(
        settings, root_dir=tmp_path).load_session_after_restart(session.session_id)
    assert reloaded.session_id == session.session_id
    assert reloaded.title == "Gamma"


def test_model_switch_preserves_history(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile(
        profile_id="profile-old", name="Old"))
    original_turn = make_turn(session.session_id, "turn-1", model_profile_snapshot=make_profile(
        profile_id="profile-old", name="Old").snapshot())
    store.append_turn(session.session_id, original_turn)

    store.update_session_profile(
        session.session_id,
        make_profile(profile_id="profile-new", name="New",
                     model_id="deepseek-v4-flash"),
    )

    turns = store.list_turns(session.session_id, include_internal=True)
    assert turns[0]["model_profile_snapshot"]["profile_id"] == "profile-old"
    assert store.get_session(
        session.session_id).active_profile.profile_id == "profile-new"


def test_per_turn_model_profile_snapshot_is_retained(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session()
    snapshot = make_profile(profile_id="profile-snap",
                            name="Snapshot Profile").snapshot()
    store.append_turn(session.session_id, make_turn(
        session.session_id, "turn-1", model_profile_snapshot=snapshot))

    turns = store.list_turns(session.session_id, include_internal=True)
    assert turns[0]["model_profile_snapshot"]["profile_id"] == "profile-snap"


def test_internal_reasoning_content_hidden_from_public_serialization(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session()
    store.append_turn(session.session_id, make_turn(
        session.session_id, "turn-1"))

    public_turn = store.list_turns(session.session_id)[0]
    assert "internal_reasoning_content" not in public_turn


def test_secrets_redacted_before_disk_write(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session()
    store.append_turn(
        session.session_id,
        make_turn(
            session.session_id,
            "turn-1",
            visible_content="api_key=sk-secret-value",
            tool_results=[{"stdout": "Bearer abcdefghijklmnop"}],
        ),
    )

    turns_path = tmp_path / ".agent_memory" / "sessions" / \
        session.session_id / "turns.dsctx.jsonl"
    stored = turns_path.read_text(encoding="utf-8")
    assert "sk-secret-value" not in stored
    assert "abcdefghijklmnop" not in stored
    assert "[REDACTED" in stored


def test_export_and_import_session_round_trip(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(title="Exported")
    store.append_turn(session.session_id, make_turn(
        session.session_id, "turn-1"))

    export_path = store.export_session(session.session_id)
    imported = store.import_session(export_path)

    assert imported.title == "Exported"
    assert len(store.list_turns(imported.session_id)) == 1


def test_corrupted_turn_line_is_quarantined_and_remaining_turns_load(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(title="Quarantine")
    turns_path = tmp_path / ".agent_memory" / "sessions" / \
        session.session_id / "turns.dsctx.jsonl"
    good = make_turn(session.session_id, "turn-1").model_dump()
    second = make_turn(session.session_id, "turn-2").model_dump()
    turns_path.write_text(
        json.dumps(good, ensure_ascii=False) + "\n" +
        "{bad-json" + "\n" + json.dumps(second, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    turns = store.list_turns(session.session_id, include_internal=True)
    quarantine_root = tmp_path / ".agent_memory" / "quarantine"

    assert [turn["turn_id"] for turn in turns] == ["turn-1", "turn-2"]
    assert list(quarantine_root.glob("**/*.quarantine.jsonl"))


def test_context_pack_written_without_temp_residue(tmp_path):
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(title="Context Pack")

    context_pack_path = store.write_context_pack(
        session.session_id, "# Context Pack\nhello")
    session_state_path = tmp_path / ".agent_memory" / \
        "sessions" / session.session_id / "session.dsstate.json"

    assert context_pack_path.read_text(
        encoding="utf-8") == "# Context Pack\nhello"
    assert json.loads(session_state_path.read_text(
        encoding="utf-8"))["schema_version"] == 1
    assert not list(context_pack_path.parent.glob("*.tmp"))
