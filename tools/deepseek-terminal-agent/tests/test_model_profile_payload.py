"""Tests for ModelProfile payload construction rules."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.deepseek_client import build_chat_payload
from deepseek_terminal_agent.sessions.models import ModelProfile


def make_profile(**overrides) -> ModelProfile:
    payload = {
        "profile_id": "test-profile",
        "name": "Test Profile",
        "model_id": "deepseek-v4-pro",
        "thinking_type": "enabled",
        "reasoning_effort": "high",
        "temperature": 0.7,
        "top_p": 0.4,
        "max_tokens": 2048,
        "response_format": "text",
        "stream": False,
        "tool_mode": "auto",
        "max_iterations": 4,
        "command_timeout_sec": 30,
        "max_command_output_chars": 1000,
        "context_budget_chars": 20000,
        "memory_atom_budget": 4,
        "recent_turns_budget": 6,
        "tool_output_budget_chars": 4000,
    }
    payload.update(overrides)
    return ModelProfile(**payload)


def test_thinking_enabled_sends_thinking_and_reasoning_effort() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(
            thinking_type="enabled", reasoning_effort="max"),
    )

    assert payload["extra_body"]["thinking"] == {"type": "enabled"}
    assert payload["extra_body"]["reasoning_effort"] == "max"
    assert "temperature" not in payload
    assert "top_p" not in payload


def test_thinking_disabled_sends_temperature_and_top_p() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(
            thinking_type="disabled", temperature=1.2, top_p=0.9),
    )

    assert payload["extra_body"]["thinking"] == {"type": "disabled"}
    assert payload["temperature"] == pytest.approx(1.2)
    assert payload["top_p"] == pytest.approx(0.9)
    assert "reasoning_effort" not in payload["extra_body"]


def test_max_tokens_always_passed() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(max_tokens=3333),
    )

    assert payload["max_tokens"] == 3333


def test_response_format_json_object_is_sent() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "Return JSON."}],
        model_profile=make_profile(
            response_format="json_object", thinking_type="disabled"),
    )

    assert payload["response_format"] == {"type": "json_object"}


def test_tool_mode_none_omits_tools() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(tool_mode="none", thinking_type="disabled"),
        tools=[{"type": "function", "function": {"name": "terminal_exec"}}],
    )

    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_tool_mode_auto_sets_auto_tool_choice() -> None:
    tools = [{"type": "function", "function": {"name": "terminal_exec"}}]
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(tool_mode="auto", thinking_type="disabled"),
        tools=tools,
    )

    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


def test_tool_mode_required_sets_required_tool_choice() -> None:
    tools = [{"type": "function", "function": {"name": "terminal_exec"}}]
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(
            tool_mode="required", thinking_type="disabled"),
        tools=tools,
    )

    assert payload["tool_choice"] == "required"


def test_tool_mode_required_without_tools_fails() -> None:
    with pytest.raises(ValueError, match="tool_mode='required'"):
        build_chat_payload(
            messages=[{"role": "user", "content": "hello"}],
            model_profile=make_profile(
                tool_mode="required", thinking_type="disabled"),
            tools=None,
        )


def test_selected_model_id_is_preserved_without_fallback() -> None:
    payload = build_chat_payload(
        messages=[{"role": "user", "content": "hello"}],
        model_profile=make_profile(
            model_id="deepseek-v4-flash", thinking_type="disabled"),
    )

    assert payload["model"] == "deepseek-v4-flash"
