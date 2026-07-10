"""Phase 14 — Security acceptance tests.

Verifies that:
- API key is never printed in public serializations
- raw reasoning_content is excluded from public turn dicts
- context_builder project rules explicitly block reasoning_content
- workspace root prevents path traversal
- tool policy enforcement cannot be bypassed
"""
from __future__ import annotations

import json

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore
from deepseek_terminal_agent.sessions.tool_policy import validate_command

# ── API key never in public output ─────────────────────────────────────────────


def test_api_key_not_in_context_report(tmp_path):
    """Context report must not contain the API key string."""
    settings = Settings(deepseek=DeepSeekConfig(
        api_key="sk-supersecret-test-key-xyz"))
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings, session_store=store,
        memory_store=memory, artifact_store=artifacts,
        root_dir=tmp_path,
    )

    profile = ModelProfile(
        profile_id="p1", name="Test", model_id="deepseek-v4-pro",
        context_budget_chars=50000, memory_atom_budget=4,
        recent_turns_budget=6, tool_output_budget_chars=10000,
    )
    session = store.create_session(default_profile=profile)

    result = builder.build(
        session_id=session.session_id,
        current_user_message="Hello",
        selected_profile=profile,
    )

    context_pack = result["context_pack"]
    context_report = json.dumps(result["context_report"])

    assert "sk-supersecret-test-key-xyz" not in context_pack
    assert "sk-supersecret-test-key-xyz" not in context_report


# ── raw reasoning_content excluded from public dict ────────────────────────────

def test_reasoning_content_excluded_from_public_dict():
    """ChatTurn.to_public_dict() must exclude internal_reasoning_content."""
    turn = ChatTurn(
        turn_id="t1",
        session_id="s1",
        role="assistant",
        visible_content="Here is my answer",
        internal_reasoning_content="<thinking>This is secret reasoning</thinking>",
        model_id="deepseek-v4-pro",
    )
    public = turn.to_public_dict()
    assert "internal_reasoning_content" not in public
    assert "<thinking>" not in json.dumps(public)
    assert "Here is my answer" in public["visible_content"]


def test_reasoning_content_preserved_internally():
    """raw reasoning content must be stored internally (append-only)."""
    turn = ChatTurn(
        turn_id="t1",
        session_id="s1",
        role="assistant",
        visible_content="Answer",
        internal_reasoning_content="<think>secret</think>",
    )
    assert turn.internal_reasoning_content == "<think>secret</think>"


# ── Context builder project rules mention reasoning_content ──────────────────

def test_project_rules_block_reasoning_content(tmp_path):
    settings = Settings(deepseek=DeepSeekConfig(api_key="sk-test"))
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings, session_store=store,
        memory_store=memory, artifact_store=artifacts,
        root_dir=tmp_path,
    )
    profile = ModelProfile(
        profile_id="p1", name="Test", model_id="deepseek-v4-pro",
        context_budget_chars=50000, memory_atom_budget=4,
        recent_turns_budget=6, tool_output_budget_chars=10000,
    )
    session = store.create_session(default_profile=profile)
    result = builder.build(
        session_id=session.session_id,
        current_user_message="test",
        selected_profile=profile,
    )
    context_pack = result["context_pack"]
    assert "reasoning_content" in context_pack  # Rule explicitly mentions it


# ── Workspace root path traversal blocked ──────────────────────────────────────

def test_workspace_path_traversal_config():
    """Config validator blocks path traversal in workspace_root relative paths."""
    from pydantic import ValidationError

    from deepseek_terminal_agent.config import AgentConfig
    # Path traversal in log_dir would be caught by validator
    with pytest.raises(ValidationError):
        AgentConfig(log_dir="../../../etc")


# ── Tool policy read_only cannot write ─────────────────────────────────────────

def test_read_only_policy_blocks_writes():
    allowed, reason = validate_command("read_only", "cat file.txt")
    assert allowed is True

    allowed, reason = validate_command("read_only", "echo hello > file.txt")
    assert allowed is False

    allowed, reason = validate_command("read_only", "git commit -m test")
    assert allowed is False


def test_tests_only_policy():
    allowed, _ = validate_command("tests_only", "pytest -q")
    assert allowed is True

    allowed, _ = validate_command("tests_only", "git commit -m test")
    assert allowed is False

    allowed, _ = validate_command("tests_only", "cat README.md")
    assert allowed is False


def test_no_policy_blocks_all():
    allowed, reason = validate_command("none", "cat file.txt")
    assert allowed is False

    allowed, reason = validate_command("none", "pytest")
    assert allowed is False

    allowed, reason = validate_command("none", "ls")
    assert allowed is False


# ── Dashboard localhost-only config ────────────────────────────────────────────

def test_dashboard_host_default_is_localhost():
    from deepseek_terminal_agent.config import DashboardConfig
    cfg = DashboardConfig()
    assert cfg.host == "127.0.0.1"


def test_dashboard_env_warning_for_public_host(monkeypatch):
    """Dashboard requires explicit private-LAN opt-in for wildcard binds."""
    from deepseek_terminal_agent.config import DashboardConfig
    with pytest.raises(ValueError, match="private_lan_enabled"):
        DashboardConfig(host="0.0.0.0")
    cfg = DashboardConfig(
        host="0.0.0.0",
        private_lan_enabled=True,
        allowed_hosts=["127.0.0.1", "localhost", "testserver", "private-lan"],
        allowed_origins=["http://127.0.0.1:8787", "private-lan"],
    )
    assert cfg.host == "0.0.0.0"

    default = DashboardConfig()
    assert default.host != "0.0.0.0"


# ── Memory atoms excluded from public turn serialization ──────────────────────

def test_memory_atom_text_not_in_turn_dict():
    """Memory atoms should not leak into raw turn dicts."""
    turn = ChatTurn(
        turn_id="t1",
        session_id="s1",
        role="user",
        visible_content="Regular user message",
    )
    public = turn.to_public_dict()
    # memory atoms are NOT stored in turns — verify no leakage
    assert "memory_atoms" not in public
