"""Subagent tool-policy enforcement on top of the existing terminal safety layer."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

ToolPolicyName = Literal["none", "read_only",
                         "tests_only", "full_agent_safety"]

_WRITE_BLOCKERS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r">>",
        r"(^|\s)>(\s|$)",
        r"\btee\b",
        r"\bsed\s+-i\b",
        r"\bapply_patch\b",
        r"\bgit\s+commit\b",
        r"\brm\b",
        r"\bmv\b",
        r"\bcp\b",
        r"\.env\b",
    ]
]

_READ_ONLY_PREFIXES = (
    "pwd",
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "git status",
    "git diff",
    "git log",
)

_TEST_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python -m compileall",
    "ruff",
    "npm test",
)


def validate_command(policy_name: ToolPolicyName, cmd: str) -> tuple[bool, str]:
    stripped = str(cmd or "").strip()
    if not stripped:
        return False, "empty command"
    if policy_name == "none":
        return False, "tool policy blocks all commands"
    if any(pattern.search(stripped) for pattern in _WRITE_BLOCKERS):
        return False, "command violates read-only safety policy"
    if policy_name == "full_agent_safety":
        return True, ""
    if policy_name == "read_only":
        return stripped.startswith(_READ_ONLY_PREFIXES), "command is not on the read-only allowlist"
    if policy_name == "tests_only":
        return stripped.startswith(_TEST_PREFIXES), "command is not on the tests-only allowlist"
    return False, "unknown tool policy"


class PolicyEnforcedExecutor:
    def __init__(self, executor: Any, policy_name: ToolPolicyName) -> None:
        self.executor = executor
        self.policy_name = policy_name
        self.command_log: list[dict[str, Any]] = []

    def execute(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ) -> dict[str, Any]:
        allowed, reason = validate_command(self.policy_name, cmd)
        if not allowed:
            result = {
                "ok": False,
                "blocked": True,
                "cmd": cmd,
                "cwd": cwd,
                "exit_code": -1,
                "stdout": "",
                "stderr": reason,
                "timed_out": False,
                "duration_ms": 0,
                "output_truncated": False,
            }
            self.command_log.append(result)
            return result
        result = self.executor.execute(
            cmd=cmd, cwd=cwd, timeout_sec=timeout_sec)
        self.command_log.append(result)
        return result
