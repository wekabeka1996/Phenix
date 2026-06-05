"""Tests for model-switch session continuity.

Verifies that ChatSession is source-of-truth and the model is just executor:
- Switching profiles does not erase turns
- Each turn stores a per-turn model profile snapshot
- Public turn dict does not expose raw reasoning_content
- Context builder includes all turns regardless of which model created them
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


def _make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test"))


def _make_profile(model_id: str, profile_id: str) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        name=f"Profile {profile_id}",
        model_id=model_id,
        context_budget_chars=50000,
        memory_atom_budget=4,
        recent_turns_budget=12,
        tool_output_budget_chars=10000,
    )


def _add_turn(store: SessionStore, session_id: str, role: str, content: str, model_id: str) -> ChatTurn:
    profile = _make_profile(model_id, f"p-{role}")
    turn = ChatTurn(
        turn_id=uuid.uuid4().hex,
        session_id=session_id,
        role=role,
        visible_content=content,
        model_id=model_id,
        model_profile_snapshot=profile.snapshot(),
    )
    store.append_turn(session_id, turn)
    return turn


# ── Turns survive profile switch ───────────────────────────────────────────────

def test_profile_switch_preserves_turns(tmp_path):
    """Switching session profile does not erase existing turns."""
    settings = _make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    profile_a = _make_profile("deepseek-v4-pro", "pro")
    session = store.create_session(default_profile=profile_a)

    _add_turn(store, session.session_id, "user",
              "Hello with pro model", "deepseek-v4-pro")
    _add_turn(store, session.session_id, "assistant",
              "Response from pro model", "deepseek-v4-pro")

    # Switch to flash
    profile_b = _make_profile("deepseek-v4-flash", "flash")
    store.update_session_profile(session.session_id, profile_b)

    turns = store.list_turns(session.session_id, include_internal=False)
    assert len(turns) == 2, "Profile switch must not erase turns"
    assert turns[0]["visible_content"] == "Hello with pro model"
    assert turns[1]["visible_content"] == "Response from pro model"


def test_each_turn_has_model_profile_snapshot(tmp_path):
    """Every stored turn carries its own model_profile_snapshot."""
    settings = _make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    profile = _make_profile("deepseek-v4-pro", "pro")
    session = store.create_session(default_profile=profile)

    t1 = _add_turn(store, session.session_id, "user",
                   "Turn 1", "deepseek-v4-pro")
    t2 = _add_turn(store, session.session_id, "assistant",
                   "Turn 2", "deepseek-v4-flash")

    turns = store.list_turns(session.session_id, include_internal=False)
    assert turns[0].get("model_id") == "deepseek-v4-pro"
    assert turns[1].get("model_id") == "deepseek-v4-flash"
    # snapshot should be present
    assert turns[0].get("model_profile_snapshot") is not None
    assert turns[1].get("model_profile_snapshot") is not None


def test_context_builder_includes_turns_from_both_models(tmp_path):
    """ContextBuilder includes turns from both models in the assembled context."""
    settings = _make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings,
        session_store=store,
        memory_store=memory,
        artifact_store=artifacts,
        root_dir=tmp_path,
    )
    profile = _make_profile("deepseek-v4-pro", "pro")
    session = store.create_session(default_profile=profile)

    _add_turn(store, session.session_id, "user",
              "PHRASE_A from pro model", "deepseek-v4-pro")
    _add_turn(store, session.session_id, "assistant",
              "Answer PHRASE_A", "deepseek-v4-pro")
    _add_turn(store, session.session_id, "user",
              "PHRASE_B after model switch", "deepseek-v4-flash")

    flash_profile = _make_profile("deepseek-v4-flash", "flash")
    result = builder.build(
        session_id=session.session_id,
        current_user_message="What is PHRASE_B?",
        selected_profile=flash_profile,
    )

    context_pack = result["context_pack"]
    assert "PHRASE_A" in context_pack, "Context must include turns from the pro model"
    assert "PHRASE_B" in context_pack, "Context must include turns from the flash model"


def test_session_reload_preserves_all_turns(tmp_path):
    """After reload from disk, all turns are present regardless of model."""
    settings = _make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    profile = _make_profile("deepseek-v4-pro", "pro")
    session = store.create_session(default_profile=profile)
    session_id = session.session_id

    for i in range(4):
        model = "deepseek-v4-pro" if i % 2 == 0 else "deepseek-v4-flash"
        role = "user" if i % 2 == 0 else "assistant"
        _add_turn(store, session_id, role, f"Content {i}", model)

    # Simulate restart by creating a new store from the same root_dir
    store2 = SessionStore(settings, root_dir=tmp_path)
    turns = store2.list_turns(session_id, include_internal=False)
    assert len(turns) == 4, "All turns must survive restart"
    models = [t.get("model_id") for t in turns]
    assert "deepseek-v4-pro" in models
    assert "deepseek-v4-flash" in models


def test_public_turn_dict_no_reasoning_content():
    """Per-turn public dict must never expose internal_reasoning_content."""
    turn = ChatTurn(
        turn_id="t1",
        session_id="s1",
        role="assistant",
        visible_content="Final answer",
        internal_reasoning_content="<think>Private reasoning chain</think>",
        model_id="deepseek-v4-pro",
    )
    public = turn.to_public_dict()
    import json
    public_str = json.dumps(public)
    assert "internal_reasoning_content" not in public_str
    assert "Private reasoning chain" not in public_str
    assert "<think>" not in public_str
    assert "Final answer" in public_str
