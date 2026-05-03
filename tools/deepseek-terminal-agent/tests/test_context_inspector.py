"""Tests for context inspector summaries."""
from __future__ import annotations

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.context_inspector import ContextInspector
from deepseek_terminal_agent.sessions.models import ModelProfile
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


def test_context_inspector_reports_usage_and_contributors(tmp_path):
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    session = store.create_session(default_profile=make_profile())
    builder = ContextBuilder(settings, session_store=store, root_dir=tmp_path)
    inspector = ContextInspector(builder)

    info = inspector.inspect(
        session_id=session.session_id,
        current_user_message="Inspect this context",
        selected_profile=make_profile(),
    )

    assert info["session_id"] == session.session_id
    assert info["estimated_context_usage"]["chars"] >= 0
    assert info["top_context_contributors"]
    assert "hidden reasoning" not in info["context_pack"]
