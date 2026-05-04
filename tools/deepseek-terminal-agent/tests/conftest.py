"""Shared pytest fixtures."""
from __future__ import annotations

import subprocess

import pytest


def _bash_works() -> bool:
    """Return True only if bash is available AND can execute a command.

    Filters out Windows bash.exe (WSL launcher) that exists on PATH but does
    not actually execute commands — it outputs a WSL installation prompt.
    """
    try:
        result = subprocess.run(
            ["bash", "-c", "echo healthcheck"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "healthcheck" in result.stdout
    except Exception:
        return False


@pytest.fixture
def workspace(tmp_path):
    """Temporary workspace directory for TerminalExecutor tests."""
    return tmp_path


# Skip marker for tests that require a working bash
needs_bash = pytest.mark.skipif(
    not _bash_works(),
    reason="bash not available or not functional — run tests inside Docker",
)
