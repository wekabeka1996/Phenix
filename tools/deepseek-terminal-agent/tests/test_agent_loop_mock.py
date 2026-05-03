"""Tests for AgentLoop with mocked DeepSeek client.

No real API calls are made. The tests verify:
  - Tool call dispatch and result injection
  - Multi-tool-call handling
  - max_iterations enforcement
  - Final answer extraction
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from deepseek_terminal_agent.agent_loop import AgentLoop, MaxIterationsError
from deepseek_terminal_agent.config import AgentConfig, DeepSeekConfig, Settings, TerminalConfig

# ── Fixtures / helpers ────────────────────────────────────────────────────────


def make_settings(tmp_path: Path, max_iterations: int = 10) -> Settings:
    return Settings(
        deepseek=DeepSeekConfig(api_key="sk-test", model="deepseek-v4-pro"),
        terminal=TerminalConfig(workspace_root=str(tmp_path)),
        agent=AgentConfig(
            max_iterations=max_iterations,
            system_prompt_path="nonexistent_prompt.md",  # uses inline fallback
        ),
    )


def make_tool_call(name: str, arguments: dict, call_id: str = "tc_001") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def make_response(
    content: str | None = None,
    tool_calls: list | None = None,
    finish_reason: str | None = None,
) -> MagicMock:
    if finish_reason is None:
        finish_reason = "stop" if not tool_calls else "tool_calls"
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    response = MagicMock()
    response.choices = [choice]
    return response


def make_executor_result(**kwargs) -> dict[str, Any]:
    defaults = {
        "ok": True,
        "cmd": "echo hello",
        "cwd": "/workspace",
        "exit_code": 0,
        "stdout": "hello\n",
        "stderr": "",
        "timed_out": False,
        "duration_ms": 5,
        "output_truncated": False,
    }
    defaults.update(kwargs)
    return defaults


def make_logger(tmp_path: Path) -> MagicMock:
    logger = MagicMock()
    logger.run_url.return_value = str(tmp_path)
    logger.terminal_log_path = tmp_path / "terminal.log"
    return logger


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_final_answer_returned_directly(tmp_path):
    """When the first response has no tool_calls, final answer is returned."""
    client = MagicMock()
    client.chat_completions.return_value = make_response(
        content="Hello, I found the answer.")

    executor = MagicMock()
    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    result = loop.run("What is the answer?")

    assert "Hello" in result
    executor.execute.assert_not_called()
    assert client.chat_completions.call_count == 1


def test_tool_call_dispatched_and_result_injected(tmp_path):
    """Model makes one tool call → executor runs it → final answer returned."""
    tool_call = make_tool_call("terminal_exec", {"cmd": "echo hello"})

    client = MagicMock()
    client.chat_completions.side_effect = [
        make_response(tool_calls=[tool_call]),
        make_response(content="The command output was: hello"),
    ]

    executor = MagicMock()
    executor.execute.return_value = make_executor_result(stdout="hello\n")

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    result = loop.run("Run echo hello")

    assert "hello" in result.lower() or "command" in result.lower()
    executor.execute.assert_called_once_with(
        cmd="echo hello", cwd=None, timeout_sec=None)
    assert client.chat_completions.call_count == 2


def test_tool_result_in_second_request(tmp_path):
    """The tool result is appended as a 'tool' message in the next API call."""
    tool_call = make_tool_call(
        "terminal_exec", {"cmd": "pwd"}, call_id="tc_pwd")

    client = MagicMock()
    client.chat_completions.side_effect = [
        make_response(tool_calls=[tool_call]),
        make_response(content="The current directory is /workspace."),
    ]

    executor = MagicMock()
    executor.execute.return_value = make_executor_result(
        cmd="pwd", stdout="/workspace\n")

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    loop.run("What directory am I in?")

    # Second call to chat_completions should include a 'tool' role message
    second_call_messages = client.chat_completions.call_args_list[1][1]["messages"]
    roles = [m["role"] for m in second_call_messages]
    assert "tool" in roles


def test_tool_result_is_not_double_logged(tmp_path):
    """AgentLoop does not append a second terminal log entry after executor.execute()."""
    tool_call = make_tool_call(
        "terminal_exec", {"cmd": "pwd"}, call_id="tc_log")

    client = MagicMock()
    client.chat_completions.side_effect = [
        make_response(tool_calls=[tool_call]),
        make_response(content="Done."),
    ]

    executor = MagicMock()
    executor.execute.return_value = make_executor_result(
        cmd="pwd", stdout="/workspace/project\n")

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    loop.run("Run pwd")

    logger.log_terminal.assert_not_called()


def test_multiple_tool_calls_in_one_turn(tmp_path):
    """Multiple tool calls in a single turn are all dispatched."""
    tc1 = make_tool_call("terminal_exec", {"cmd": "echo a"}, call_id="tc1")
    tc2 = make_tool_call("terminal_exec", {"cmd": "echo b"}, call_id="tc2")

    client = MagicMock()
    client.chat_completions.side_effect = [
        make_response(tool_calls=[tc1, tc2]),
        make_response(content="Done."),
    ]

    executor = MagicMock()
    executor.execute.side_effect = [
        make_executor_result(cmd="echo a", stdout="a\n"),
        make_executor_result(cmd="echo b", stdout="b\n"),
    ]

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    result = loop.run("Run two commands")

    assert executor.execute.call_count == 2
    assert result == "Done."


def test_max_iterations_raises(tmp_path):
    """Agent raises MaxIterationsError when it never produces a final answer."""
    tool_call = make_tool_call("terminal_exec", {"cmd": "echo loop"})
    infinite_response = make_response(tool_calls=[tool_call])

    client = MagicMock()
    client.chat_completions.return_value = infinite_response

    executor = MagicMock()
    executor.execute.return_value = make_executor_result()

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path, max_iterations=3)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)

    with pytest.raises(MaxIterationsError):
        loop.run("Loop forever")

    assert client.chat_completions.call_count == 3
    assert executor.execute.call_count == 3


def test_unknown_tool_returns_error(tmp_path):
    """Unknown tool name returns an error dict (does not crash the loop)."""
    unknown_tc = make_tool_call("unknown_tool", {"x": 1})

    client = MagicMock()
    client.chat_completions.side_effect = [
        make_response(tool_calls=[unknown_tc]),
        make_response(content="Handled the unknown tool error."),
    ]

    executor = MagicMock()
    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    result = loop.run("Call unknown tool")

    executor.execute.assert_not_called()
    assert result == "Handled the unknown tool error."


def test_history_updated_after_run(tmp_path):
    """After run(), history contains user + assistant messages for next turn."""
    client = MagicMock()
    client.chat_completions.return_value = make_response(
        content="First answer.")

    executor = MagicMock()
    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    loop.run("First question")

    assert len(loop.history) == 2
    assert loop.history[0]["role"] == "user"
    assert loop.history[1]["role"] == "assistant"
    assert "First answer." in loop.history[1]["content"]


def test_reasoning_content_preserved_in_tool_call_turn(tmp_path):
    """reasoning_content from assistant is included in the message sent back to API.

    DeepSeek thinking mode requires reasoning_content to be passed back in
    subsequent turns (tool call loop), otherwise the API returns 400.
    """
    tool_call = make_tool_call(
        "terminal_exec", {"cmd": "pwd"}, call_id="tc_rc")

    # First response: tool call WITH reasoning_content
    first_response = make_response(tool_calls=[tool_call])
    first_response.choices[0].message.reasoning_content = (
        "The user wants to know the directory. I should run pwd."
    )
    # Clear auto-spec tool_calls so finish_reason is set correctly
    first_response.choices[0].finish_reason = "tool_calls"

    # Second response: final answer (no reasoning needed)
    second_response = make_response(content="You are in /workspace/project.")
    second_response.choices[0].message.reasoning_content = None

    client = MagicMock()
    client.chat_completions.side_effect = [first_response, second_response]

    executor = MagicMock()
    executor.execute.return_value = make_executor_result(
        cmd="pwd", stdout="/workspace/project\n")

    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    loop.run("What directory am I in?")

    # The second API call's messages must include reasoning_content in the
    # assistant turn (to satisfy DeepSeek thinking mode API requirement)
    second_call_messages = client.chat_completions.call_args_list[1][1]["messages"]
    assistant_msgs = [
        m for m in second_call_messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].get("reasoning_content") == (
        "The user wants to know the directory. I should run pwd."
    )


def test_reasoning_content_absent_when_none(tmp_path):
    """reasoning_content is NOT added to msg_dict when it is None or absent."""
    client = MagicMock()
    response = make_response(content="Simple answer.")
    response.choices[0].message.reasoning_content = None
    client.chat_completions.return_value = response

    executor = MagicMock()
    logger = make_logger(tmp_path)
    settings = make_settings(tmp_path)

    loop = AgentLoop(settings=settings, client=client,
                     executor=executor, logger=logger)
    loop.run("Simple question")

    # No assistant message in the first call (system + user only)
    # Verify no reasoning_content key leaked into history
    assert "reasoning_content" not in loop.history[1]
