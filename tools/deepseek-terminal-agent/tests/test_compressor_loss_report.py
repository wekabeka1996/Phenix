"""Tests that compressor writes LossReport and raw turns are preserved."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.compressor import ContextCompressor
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_mock_client_with_response(content: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    client.chat_completions.return_value = response
    return client


def add_turns(store: SessionStore, session_id: str, n: int) -> list[str]:
    ids = []
    for i in range(n):
        turn_id = f"turn-{i}"
        store.append_turn(
            session_id,
            ChatTurn(
                turn_id=turn_id,
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                visible_content=f"Turn {i} content — interesting data",
                model_id="deepseek-v4-pro",
            ),
        )
        ids.append(turn_id)
    return ids


def test_compressor_writes_loss_report(tmp_path):
    """Compression must write a .dsloss.json file."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)

    session = store.create_session(
        default_profile=ModelProfile(
            profile_id="p1", name="Test", model_id="deepseek-v4-pro",
            context_budget_chars=50000, memory_atom_budget=4,
            recent_turns_budget=2, tool_output_budget_chars=10000,
        )
    )
    add_turns(store, session.session_id, 20)

    mock_response = json.dumps({
        "summary": "Session compressed",
        "decisions": ["Decision A"],
        "verified_facts": ["Fact B"],
        "assumptions": [],
        "open_threads": [],
        "risks": [],
        "next_actions": [],
        "memory_atoms": [],
    })
    client = make_mock_client_with_response(mock_response)

    compressor = ContextCompressor(
        settings,
        session_store=store,
        memory_store=memory,
        client=client,
        root_dir=tmp_path,
    )

    result = compressor.compress_session(session_id=session.session_id)

    assert result["compressed"] is True
    assert "loss_report_id" in result

    # Loss report file should exist
    loss_dir = tmp_path / ".agent_memory" / "loss_reports"
    loss_files = list(loss_dir.glob("*.dsloss.json"))
    assert len(loss_files) == 1

    loss_data = json.loads(loss_files[0].read_text(encoding="utf-8"))
    assert loss_data["session_id"] == session.session_id
    assert len(loss_data["source_turn_ids"]) > 0


def test_compressor_raw_turns_preserved(tmp_path):
    """After compression, raw turns must still be on disk (is_compacted=True, not deleted)."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)

    session = store.create_session(
        default_profile=ModelProfile(
            profile_id="p1", name="Test", model_id="deepseek-v4-pro",
            context_budget_chars=50000, memory_atom_budget=4,
            recent_turns_budget=2, tool_output_budget_chars=10000,
        )
    )
    add_turns(store, session.session_id, 20)

    mock_response = json.dumps({
        "summary": "Compressed summary",
        "decisions": [], "verified_facts": [], "assumptions": [],
        "open_threads": [], "risks": [], "next_actions": [], "memory_atoms": [],
    })
    client = make_mock_client_with_response(mock_response)

    compressor = ContextCompressor(
        settings, session_store=store, memory_store=memory,
        client=client, root_dir=tmp_path,
    )
    compressor.compress_session(session_id=session.session_id)

    # ALL turns still on disk
    turns_path = tmp_path / ".agent_memory" / "sessions" / \
        session.session_id / "turns.dsctx.jsonl"
    lines = turns_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 20  # All turns preserved

    # Some turns marked as compacted
    all_turns = store.list_turns(session.session_id, include_internal=True)
    compacted = [t for t in all_turns if t.get("is_compacted")]
    assert len(compacted) > 0


def test_compressor_invalid_json_no_state_change(tmp_path):
    """If compression model returns invalid JSON, no state change."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)

    session = store.create_session(
        default_profile=ModelProfile(
            profile_id="p1", name="Test", model_id="deepseek-v4-pro",
            context_budget_chars=50000, memory_atom_budget=4,
            recent_turns_budget=2, tool_output_budget_chars=10000,
        )
    )
    add_turns(store, session.session_id, 20)

    client = make_mock_client_with_response("This is not valid JSON at all!!!")
    compressor = ContextCompressor(
        settings, session_store=store, memory_store=memory,
        client=client, root_dir=tmp_path,
    )
    result = compressor.compress_session(session_id=session.session_id)

    assert result["compressed"] is False
    assert result["reason"] == "invalid_json"

    # No loss report written
    loss_dir = tmp_path / ".agent_memory" / "loss_reports"
    if loss_dir.exists():
        assert len(list(loss_dir.glob("*.dsloss.json"))) == 0
