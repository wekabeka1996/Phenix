"""Tests for agent instruction hot reload runtime helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.agent_instruction_manifest import (
    INSTRUCTION_ROOT,
    REQUIRED_INSTRUCTION_FILES,
    build_instruction_manifest,
)
from deepseek_terminal_agent.sessions.agent_instruction_runtime import (
    INSTRUCTIONS_ACKED_EVENT,
    INSTRUCTIONS_REFRESHED_EVENT,
    acknowledge_instruction_manifest,
    agent_instruction_preflight,
    run_instruction_preflight_for_agent,
)
from deepseek_terminal_agent.sessions.models import ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


def write_required_instructions(root: Path) -> None:
    instruction_root = root / INSTRUCTION_ROOT
    instruction_root.mkdir(parents=True)
    for filename, _, _ in REQUIRED_INSTRUCTION_FILES:
        (instruction_root / filename).write_text(
            f"# {filename}\n\nRuntime test instruction body.\n",
            encoding="utf-8",
        )


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


def make_store_and_session(tmp_path: Path) -> tuple[SessionStore, str]:
    store = SessionStore(make_settings(), root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    return store, session.session_id


def test_preflight_returns_changed_files_and_refresh_payload(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    previous = build_instruction_manifest(root_dir=tmp_path)
    (tmp_path / INSTRUCTION_ROOT / "FEATURE_TRUST_GUIDE.md").write_text(
        "# FEATURE_TRUST_GUIDE.md\n\nTrust only runtime-proven features.\n",
        encoding="utf-8",
    )

    result = agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
        previous_manifest=previous,
    )

    changed = (INSTRUCTION_ROOT / "FEATURE_TRUST_GUIDE.md").as_posix()
    assert result.changed_files == [changed]
    assert result.missing_files == []
    assert result.ack_required is True
    assert result.event_payload["event_type"] == "agent_instruction_refresh"
    assert result.event_payload["status"] == "changed"
    assert result.event_payload["changed_files"] == [changed]
    assert result.event_payload["manifest_version"] == result.manifest_version


def test_preflight_reports_missing_required_file(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    (tmp_path / INSTRUCTION_ROOT / "AGENT_ARENA_RULES.md").unlink()

    result = agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
    )

    missing = (INSTRUCTION_ROOT / "AGENT_ARENA_RULES.md").as_posix()
    assert missing in result.missing_files
    assert result.ack_required is True
    assert result.event_payload["status"] == "missing_required_files"


def test_acknowledge_instruction_manifest_produces_ack(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    manifest = build_instruction_manifest(root_dir=tmp_path)

    ack = acknowledge_instruction_manifest(
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
        manifest_version=manifest.manifest_version,
    )

    assert ack.agent_id == "agent-3"
    assert ack.agent_number == 3
    assert ack.session_id == "session-1"
    assert ack.manifest_version == manifest.manifest_version
    assert ack.acknowledged_at


def test_ack_rejects_path_traversal_identifiers() -> None:
    with pytest.raises(ValueError):
        acknowledge_instruction_manifest(
            agent_id="../agent",
            agent_number=3,
            session_id="session-1",
            manifest_version="abc123",
        )


def test_preflight_does_not_mutate_trading_config(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "aurora_business.yaml"
    original = b"risk:\n  live: false\n"
    config_file.write_bytes(original)

    agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
    )

    assert config_file.read_bytes() == original


def test_runtime_first_cycle_writes_refresh_and_ack(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    store, session_id = make_store_and_session(tmp_path)

    result = run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    events = store.list_events(session_id)
    assert result.ack_event_id
    assert result.refresh_event_id
    assert len(result.changed_files) == len(REQUIRED_INSTRUCTION_FILES)
    assert [event["event_type"] for event in events] == [
        INSTRUCTIONS_REFRESHED_EVENT,
        INSTRUCTIONS_ACKED_EVENT,
    ]
    ack_event = events[-1]
    assert ack_event["metadata"]["agent_id"] == "agent-3"
    assert ack_event["metadata"]["agent_number"] == 3
    assert ack_event["metadata"]["session_id"] == session_id
    assert ack_event["metadata"]["manifest_version"] == result.manifest_version


def test_runtime_changed_file_produces_refresh_event(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    store, session_id = make_store_and_session(tmp_path)
    run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    changed_path = tmp_path / INSTRUCTION_ROOT / "AGENT_TRADING_STYLE.md"
    changed_path.write_text("# AGENT_TRADING_STYLE.md\n\nUpdated for P39.\n", encoding="utf-8")
    result = run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    assert result.changed_files == [(INSTRUCTION_ROOT / "AGENT_TRADING_STYLE.md").as_posix()]
    events = store.list_events(session_id)
    refresh_events = [event for event in events if event["event_type"] == INSTRUCTIONS_REFRESHED_EVENT]
    assert len(refresh_events) == 2
    assert refresh_events[-1]["metadata"]["changed_files"] == result.changed_files


def test_runtime_unchanged_cycle_does_not_duplicate_refresh_event(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    store, session_id = make_store_and_session(tmp_path)
    run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    result = run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    events = store.list_events(session_id)
    refresh_events = [event for event in events if event["event_type"] == INSTRUCTIONS_REFRESHED_EVENT]
    ack_events = [event for event in events if event["event_type"] == INSTRUCTIONS_ACKED_EVENT]
    assert result.changed_files == []
    assert result.refresh_event_id is None
    assert len(refresh_events) == 1
    assert len(ack_events) == 2


def test_runtime_missing_file_marks_missing_state(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    (tmp_path / INSTRUCTION_ROOT / "SUBAGENT_RULES.md").unlink()
    store, session_id = make_store_and_session(tmp_path)

    result = run_instruction_preflight_for_agent(
        session_store=store,
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id=session_id,
    )

    missing = (INSTRUCTION_ROOT / "SUBAGENT_RULES.md").as_posix()
    assert missing in result.missing_files
    assert result.status == "missing_required_files"
    events = store.list_events(session_id)
    assert events[0]["metadata"]["status"] == "missing_required_files"
    assert events[-1]["metadata"]["missing_files"] == [missing]


def test_runtime_rejects_path_traversal_identity(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    store, session_id = make_store_and_session(tmp_path)

    with pytest.raises(ValueError):
        run_instruction_preflight_for_agent(
            session_store=store,
            root_dir=str(tmp_path),
            agent_id="../agent",
            agent_number=3,
            session_id=session_id,
        )
