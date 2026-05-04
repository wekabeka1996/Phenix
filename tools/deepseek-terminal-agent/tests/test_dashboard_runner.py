"""Tests for dashboard/runner.py."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deepseek_terminal_agent.dashboard.runner import (
    TERMINAL_STATUSES,
    DashboardRunner,
    RunResult,
    RunStatus,
    append_dashboard_run,
    load_recent_runs,
    run_agent,
)


def test_prompt_too_long_raises():
    long_prompt = "x" * 12001
    with pytest.raises(ValueError, match="Prompt too long"):
        run_agent(long_prompt, max_prompt_chars=12000)


def test_run_agent_command_does_not_contain_api_key():
    captured_args: list = []

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        m = MagicMock()
        m.returncode = 0
        m.stdout = "done"
        m.stderr = ""
        return m

    with patch("deepseek_terminal_agent.dashboard.runner.subprocess.run", side_effect=fake_run):
        run_agent("test prompt", max_prompt_chars=12000)

    assert captured_args[0] == "deepseek-agent"
    assert captured_args[1] == "run"
    assert captured_args[2] == "test prompt"
    # No extra args — API key is NOT passed on the command line
    assert len(captured_args) == 3


def _command_for_python(script: str) -> list[str]:
    return [sys.executable, "-u", "-c", script]


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _make_runner(tmp_path: Path, script: str) -> DashboardRunner:
    return DashboardRunner(
        log_dir=str(tmp_path / ".agent_runs"),
        max_output_chars=5000,
        poll_interval_sec=0.05,
        command_factory=lambda prompt: _command_for_python(script),
    )


def test_background_run_streams_stdout_before_process_exit(tmp_path):
    runner = _make_runner(
        tmp_path,
        "import time; print('first line', flush=True); time.sleep(1.0); print('done', flush=True)",
    )

    created = runner.create_run("hello")
    run_id = created["run_id"]

    assert _wait_until(
        lambda: "first line" in runner.get_output(run_id)["stdout"]
        and runner.get_status(run_id)["status"] not in TERMINAL_STATUSES,
        timeout=2.0,
    )
    assert _wait_until(
        lambda: runner.get_status(
            run_id)["status"] == RunStatus.SUCCEEDED.value,
        timeout=3.0,
    )


def test_exit_code_zero_sets_succeeded_and_records_metadata(tmp_path):
    runner = _make_runner(tmp_path, "print('ok', flush=True)")

    run_id = runner.create_run("hello")["run_id"]
    assert _wait_until(
        lambda: runner.get_status(
            run_id)["status"] == RunStatus.SUCCEEDED.value,
        timeout=2.0,
    )

    status = runner.get_status(run_id)
    assert status["exit_code"] == 0
    assert status["finished_at"] is not None
    assert status["duration_ms"] >= 0


def test_nonzero_exit_code_sets_failed(tmp_path):
    runner = _make_runner(
        tmp_path,
        "import sys; print('bad', file=sys.stderr, flush=True); sys.exit(7)",
    )

    run_id = runner.create_run("hello")["run_id"]
    assert _wait_until(
        lambda: runner.get_status(run_id)["status"] == RunStatus.FAILED.value,
        timeout=2.0,
    )

    status = runner.get_status(run_id)
    assert status["exit_code"] == 7


def test_cancel_sets_cancelled(tmp_path):
    runner = _make_runner(
        tmp_path,
        "import time; print('working', flush=True); time.sleep(10)",
    )

    run_id = runner.create_run("hello")["run_id"]
    assert _wait_until(
        lambda: runner.get_status(run_id)["status"] in {
            RunStatus.RUNNING.value,
            RunStatus.WAITING_MODEL.value,
        },
        timeout=1.0,
    )
    assert runner.cancel(run_id) is True
    assert _wait_until(
        lambda: runner.get_status(
            run_id)["status"] == RunStatus.CANCELLED.value,
        timeout=3.0,
    )


def test_events_are_ordered_redacted_and_reasoning_content_hidden(tmp_path):
    runner = _make_runner(
        tmp_path,
        "import time; print('holding', flush=True); time.sleep(1.0)",
    )
    run_id = runner.create_run("hello")["run_id"]
    assert _wait_until(
        lambda: runner.get_status(run_id)["status"] != RunStatus.QUEUED.value,
        timeout=1.0,
    )

    state = runner._runs[run_id]
    run_dir = Path(runner.log_dir) / "simulated-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    with state.lock:
        state.run_dir = str(run_dir)

    conversation_path = run_dir / "conversation.jsonl"
    terminal_log_path = run_dir / "terminal.log"
    summary_path = run_dir / "summary.md"

    conversation_record = {
        "role": "assistant",
        "content": "Visible note for the operator.",
        "reasoning_content": "hidden private chain of thought",
        "tool_calls": [
            {
                "id": "tc_1",
                "type": "function",
                "function": {
                    "name": "terminal_exec",
                    "arguments": json.dumps({"cmd": "echo api_key=sk-secret-value"}),
                },
            }
        ],
    }
    terminal_record = {
        "ok": True,
        "cmd": "echo api_key=sk-secret-value",
        "cwd": "/workspace/project",
        "exit_code": 0,
        "stdout": "api_key=sk-secret-value\nvisible output\n",
        "stderr": "",
        "timed_out": False,
        "duration_ms": 5,
        "output_truncated": False,
    }
    conversation_path.write_text(
        json.dumps(conversation_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    terminal_log_path.write_text(
        json.dumps(terminal_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        "Final answer visible to the user.", encoding="utf-8")

    runner._consume_run_logs(state, final=True)

    events = runner.get_events(run_id)
    event_types = [event["type"] for event in events]
    assert "tool_call" in event_types
    assert "command_start" in event_types
    assert "command_end" in event_types
    assert event_types.index("tool_call") < event_types.index("command_end")

    rendered_events = json.dumps(events, ensure_ascii=False)
    assert "reasoning_content" not in rendered_events
    assert "hidden private chain of thought" not in rendered_events
    assert "sk-secret-value" not in rendered_events

    output = runner.get_output(run_id)
    rendered_output = json.dumps(output, ensure_ascii=False)
    assert "sk-secret-value" not in rendered_output
    assert "[REDACTED" in rendered_output


def test_append_and_load_runs_preserve_status_and_order(tmp_path):
    log_dir = str(tmp_path)
    r1 = RunResult(
        run_id="id1",
        prompt="p1",
        stdout="out1",
        stderr="",
        exit_code=0,
        duration_ms=10,
        created_at="2026-01-01T00:00:00+00:00",
        run_dir=None,
        status=RunStatus.SUCCEEDED.value,
        finished_at="2026-01-01T00:00:10+00:00",
    )
    r2 = RunResult(
        run_id="id2",
        prompt="p2",
        stdout="out2",
        stderr="",
        exit_code=1,
        duration_ms=20,
        created_at="2026-01-02T00:00:00+00:00",
        run_dir=None,
        status=RunStatus.FAILED.value,
        finished_at="2026-01-02T00:00:20+00:00",
    )

    append_dashboard_run(log_dir, r1)
    append_dashboard_run(log_dir, r2)

    runs = load_recent_runs(log_dir, limit=10)
    assert [run["run_id"] for run in runs] == ["id2", "id1"]
    assert runs[0]["status"] == RunStatus.FAILED.value
    assert runs[1]["status"] == RunStatus.SUCCEEDED.value


def test_run_agent_captures_exit_code():
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.stdout = ""
    mock_proc.stderr = "something went wrong\n"
    with patch("deepseek_terminal_agent.dashboard.runner.subprocess.run", return_value=mock_proc):
        result = run_agent("fail test", max_prompt_chars=12000)
    assert result.exit_code == 2


def test_load_runs_empty_log_dir(tmp_path):
    runs = load_recent_runs(str(tmp_path), limit=10)
    assert runs == []


def test_load_runs_limit(tmp_path):
    log_dir = str(tmp_path)
    for i in range(5):
        r = RunResult(
            run_id=f"id{i}",
            prompt=f"p{i}",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=i,
            created_at=f"2026-01-0{i+1}T00:00:00+00:00",
            run_dir=None,
            status=RunStatus.SUCCEEDED.value,
            finished_at=f"2026-01-0{i+1}T00:00:10+00:00",
        )
        append_dashboard_run(log_dir, r)

    runs = load_recent_runs(log_dir, limit=3)
    assert len(runs) == 3


def test_append_truncates_stored_output(tmp_path):
    log_dir = str(tmp_path)
    long_out = "A" * 10000
    r = RunResult(
        run_id="id1",
        prompt="p",
        stdout=long_out,
        stderr="",
        exit_code=0,
        duration_ms=1,
        created_at="2026-01-01T00:00:00+00:00",
        run_dir=None,
        status=RunStatus.SUCCEEDED.value,
        finished_at="2026-01-01T00:00:01+00:00",
    )
    append_dashboard_run(log_dir, r)

    runs_file = Path(log_dir) / "dashboard_runs.jsonl"
    record = json.loads(runs_file.read_text().strip())
    assert len(record["stdout"]) <= 4000
