"""Tests for TerminalExecutor.

Tests that require bash are skipped on Windows hosts without a working bash.
Run the full suite inside Docker: docker compose run --rm deepseek-agent pytest -q
"""
from __future__ import annotations

import subprocess

import pytest

from deepseek_terminal_agent.terminal_tool import TerminalExecutor


def _bash_works() -> bool:
    """Return True only if bash can actually execute a command (not just exist on PATH).

    On Windows, bash.exe may be the WSL launcher and output an installation
    prompt instead of executing commands.
    """
    try:
        r = subprocess.run(
            ["bash", "-c", "echo healthcheck"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and "healthcheck" in r.stdout
    except Exception:
        return False


# Skip marker for bash-dependent tests
needs_bash = pytest.mark.skipif(
    not _bash_works(),
    reason="bash not functional (Windows WSL launcher or bash not installed) — run inside Docker",
)


# ── Path safety ───────────────────────────────────────────────────────────────


def test_blocks_cwd_escape(tmp_path):
    """Attempt to set cwd outside workspace must be blocked."""
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("ls", cwd="../..")
    assert result["ok"] is False
    assert "error" in result


def test_blocks_cwd_absolute_escape(tmp_path):
    """Absolute cwd path outside workspace must be blocked."""
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    # Construct a path outside tmp_path
    outside = str(tmp_path.parent)
    result = executor.execute("ls", cwd=outside)
    # Absolute path outside workspace — blocked
    assert result["ok"] is False


def test_allows_cwd_inside_workspace(tmp_path):
    """A subdirectory inside workspace is allowed as cwd."""
    subdir = tmp_path / "inner"
    subdir.mkdir()
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False, dry_run=True
    )
    result = executor.execute("ls", cwd="inner")
    assert result["ok"] is True


# ── Dry run ───────────────────────────────────────────────────────────────────


def test_dry_run_does_not_execute(tmp_path):
    """In dry-run mode, commands are not executed — result shows dry_run=True."""
    executor = TerminalExecutor(
        workspace_root=str(tmp_path),
        dry_run=True,
        interactive=False,
    )
    result = executor.execute("echo should-not-run")
    assert result.get("dry_run") is True
    assert result["ok"] is True
    assert "DRY RUN" in result["stdout"]


# ── Safety blocking (non-interactive) ────────────────────────────────────────


def test_dangerous_command_blocked_non_interactive(tmp_path):
    """Dangerous command is blocked without execution in non-interactive mode."""
    executor = TerminalExecutor(
        workspace_root=str(tmp_path),
        require_approval_for_dangerous=True,
        interactive=False,
    )
    result = executor.execute("sudo ls")
    assert result["ok"] is False
    assert result.get("blocked") is True
    assert "BLOCKED" in result.get("stderr", "")


# ── Bash execution tests (skipped without bash) ───────────────────────────────


@needs_bash
def test_executes_harmless_command(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("echo hello")
    assert result["ok"] is True
    assert "hello" in result["stdout"]
    assert result["exit_code"] == 0


@needs_bash
def test_captures_stderr(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("echo err_msg >&2; exit 1")
    assert result["exit_code"] == 1
    assert "err_msg" in result["stderr"]


@needs_bash
def test_captures_both_streams(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("echo stdout_val; echo stderr_val >&2")
    assert "stdout_val" in result["stdout"]
    assert "stderr_val" in result["stderr"]


@needs_bash
def test_nonzero_exit_code_ok_false(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("exit 42")
    assert result["exit_code"] == 42
    assert result["ok"] is False


@needs_bash
def test_respects_cwd_inside_workspace(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("pwd", cwd="subdir")
    assert result["ok"] is True
    assert "subdir" in result["stdout"]


@needs_bash
def test_timeout_terminates_command(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path),
        default_timeout_sec=1,
        interactive=False,
    )
    result = executor.execute("sleep 10")
    assert result["timed_out"] is True
    assert result["ok"] is False


@needs_bash
def test_output_truncation(tmp_path):
    """stdout is truncated to max_output_chars and output_truncated is set."""
    executor = TerminalExecutor(
        workspace_root=str(tmp_path),
        max_output_chars=50,
        interactive=False,
    )
    # Generate more than 50 chars of output
    result = executor.execute("python3 -c \"print('x' * 200)\"")
    assert result["output_truncated"] is True
    assert len(result["stdout"]) <= 50


@needs_bash
def test_duration_ms_populated(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("echo hi")
    assert result["duration_ms"] >= 0


@needs_bash
def test_result_has_required_fields(tmp_path):
    executor = TerminalExecutor(
        workspace_root=str(tmp_path), interactive=False)
    result = executor.execute("echo ok")
    required = {"ok", "cmd", "cwd", "exit_code", "stdout", "stderr", "timed_out",
                "duration_ms", "output_truncated"}
    assert required.issubset(result.keys())
