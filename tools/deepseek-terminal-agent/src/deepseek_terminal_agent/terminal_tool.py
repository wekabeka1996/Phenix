"""Terminal tool: executes shell commands inside a sandboxed workspace.

The model calls this tool via OpenAI-compatible tool_calls. The tool:
  - Resolves cwd strictly inside workspace_root (path traversal blocked)
  - Classifies commands for danger (blocked or requires human approval)
  - Enforces a hard timeout
  - Truncates stdout/stderr to max_output_chars
  - Writes a structured log entry to terminal.log
  - Returns a JSON-serialisable result dict
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .safety import CommandRisk, SafetyResult, classify

# ── OpenAI-compatible tool schema ────────────────────────────────────────────
TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "terminal_exec",
        "description": (
            "Execute a shell command inside the configured sandbox workspace. "
            "Use this to explore the codebase, run tests, inspect files, "
            "and apply changes. All commands run via bash inside the workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory relative to workspace root.",
                },
                "timeout_sec": {
                    "type": "integer",
                    "description": "Optional timeout in seconds (overrides default).",
                },
            },
            "required": ["cmd"],
            "additionalProperties": False,
        },
    },
}


class TerminalExecutor:
    def __init__(
        self,
        workspace_root: str,
        default_timeout_sec: int = 120,
        max_output_chars: int = 20_000,
        require_approval_for_dangerous: bool = True,
        terminal_log_path: Optional[Path] = None,
        dry_run: bool = False,
        interactive: bool = True,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.default_timeout_sec = default_timeout_sec
        self.max_output_chars = max_output_chars
        self.require_approval_for_dangerous = require_approval_for_dangerous
        self.terminal_log_path = terminal_log_path
        self.dry_run = dry_run
        self.interactive = interactive

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute *cmd* inside the workspace. Returns a result dict."""
        effective_timeout = timeout_sec if timeout_sec is not None else self.default_timeout_sec

        # ── Resolve & validate cwd ──────────────────────────────────────────
        if cwd:
            target_cwd = (self.workspace_root / cwd).resolve()
        else:
            target_cwd = self.workspace_root

        try:
            target_cwd.relative_to(self.workspace_root)
        except ValueError:
            return self._record(
                self._error(cmd, str(target_cwd),
                            f"cwd '{cwd}' resolves outside workspace root "
                            f"'{self.workspace_root}'. Path traversal blocked.")
            )

        if not target_cwd.exists():
            return self._record(
                self._error(cmd, str(target_cwd),
                            f"cwd '{target_cwd}' does not exist inside workspace.")
            )

        # ── Safety classification ───────────────────────────────────────────
        safety: SafetyResult = classify(cmd)
        if safety.risk == CommandRisk.DANGEROUS:
            if self.dry_run or not self.interactive:
                return self._record(self._blocked(cmd, str(target_cwd), safety))
            elif self.require_approval_for_dangerous:
                if not self._ask_approval(cmd, safety):
                    return self._record(self._blocked(cmd, str(target_cwd), safety))

        # ── Dry-run mode ────────────────────────────────────────────────────
        if self.dry_run:
            result: dict[str, Any] = {
                "ok": True,
                "dry_run": True,
                "cmd": cmd,
                "cwd": str(target_cwd),
                "exit_code": 0,
                "stdout": f"[DRY RUN] would execute: {cmd}",
                "stderr": "",
                "timed_out": False,
                "duration_ms": 0,
                "output_truncated": False,
            }
            return self._record(result)

        # ── Bash availability ───────────────────────────────────────────────
        if not _bash_available():
            return self._record(
                self._error(cmd, str(target_cwd),
                            "bash not found on PATH. The terminal tool requires bash. "
                            "Run inside Docker: docker compose run --rm deepseek-agent")
            )

        # ── Execute ─────────────────────────────────────────────────────────
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            raw_out = exc.stdout or b""
            raw_err = exc.stderr or b""
            stdout = raw_out.decode(
                "utf-8", errors="replace") if isinstance(raw_out, bytes) else (raw_out or "")
            stderr = raw_err.decode(
                "utf-8", errors="replace") if isinstance(raw_err, bytes) else (raw_err or "")
        except Exception as exc:  # noqa: BLE001
            return self._record(self._error(cmd, str(target_cwd), f"subprocess error: {exc}"))

        duration_ms = int((time.monotonic() - start) * 1000)

        # ── Truncate output ─────────────────────────────────────────────────
        output_truncated = False
        if len(stdout) > self.max_output_chars:
            stdout = stdout[: self.max_output_chars]
            output_truncated = True
        if len(stderr) > self.max_output_chars:
            stderr = stderr[: self.max_output_chars]

        return self._record({
            "ok": not timed_out and exit_code == 0,
            "cmd": cmd,
            "cwd": str(target_cwd),
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "output_truncated": output_truncated,
        })

    # ── Internal helpers ───────────────────────────────────────────────────

    def _ask_approval(self, cmd: str, safety: SafetyResult) -> bool:
        print(
            f"\n[SAFETY] Dangerous command detected!\n"
            f"  Command : {cmd}\n"
            f"  Reason  : {safety.reason}\n"
            f"  Pattern : {safety.pattern}\n",
            file=sys.stderr,
        )
        try:
            answer = input("Approve execution? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes")

    def _error(self, cmd: str, cwd: str, error: str) -> dict[str, Any]:
        return {
            "ok": False,
            "cmd": cmd,
            "cwd": cwd,
            "exit_code": -1,
            "stdout": "",
            "stderr": error,
            "error": error,
            "timed_out": False,
            "duration_ms": 0,
            "output_truncated": False,
        }

    def _blocked(self, cmd: str, cwd: str, safety: SafetyResult) -> dict[str, Any]:
        reason = f"BLOCKED: {safety.reason} (pattern: {safety.pattern})"
        return {
            "ok": False,
            "blocked": True,
            "cmd": cmd,
            "cwd": cwd,
            "exit_code": -1,
            "stdout": "",
            "stderr": reason,
            "error": reason,
            "timed_out": False,
            "duration_ms": 0,
            "output_truncated": False,
        }

    def _record(self, result: dict[str, Any]) -> dict[str, Any]:
        """Write result to terminal.log and return it."""
        if self.terminal_log_path is not None:
            try:
                with self.terminal_log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return result


def _bash_available() -> bool:
    """Return True only if bash is on PATH AND can actually execute a command.

    On Windows, bash.exe may be the WSL launcher and output a WSL installation
    prompt instead of executing commands.  We verify real functionality here.
    """
    try:
        result = subprocess.run(
            ["bash", "-c", "echo healthcheck"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "healthcheck" in result.stdout
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
