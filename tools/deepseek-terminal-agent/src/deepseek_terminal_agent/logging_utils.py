"""Run logging: conversation JSONL, terminal log, summary.md, secret redaction.

Every agent run creates:
  .agent_runs/<ISO-timestamp>/
    conversation.jsonl   — all messages (role/content/tool_calls/tool_results)
    terminal.log         — each terminal_exec call (JSONL)
    summary.md           — final answer written at end of run

All content is redacted before writing — API keys, tokens, secrets are replaced
with [REDACTED].
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Secret redaction patterns ────────────────────────────────────────────────
# Each pattern is (compiled_regex, replacement_template)
# Use \1 to keep a prefix (e.g. "api_key=") and replace the value only.
_REDACT_RULES: list[tuple[re.Pattern[str], str]] = [
    # sk-... style keys
    (re.compile(r'\bsk-[a-zA-Z0-9\-_]{8,}', re.IGNORECASE), "[REDACTED_KEY]"),
    # Bearer <token>
    (re.compile(
        r'(Bearer\s+)[a-zA-Z0-9\-_.]{8,}', re.IGNORECASE), r"\1[REDACTED]"),
    # key/token/secret/password = value (various formats)
    (
        re.compile(
            r'((?:api[_-]?key|token|secret|password|credential)'
            r'(?:["\s:=]+))[^\s"\'&,\]\}]{6,}',
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
]


def redact(text: str) -> str:
    """Replace recognised secrets in *text* with [REDACTED]."""
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    return text


def redact_obj(obj: Any) -> Any:
    """Recursively redact secrets from a dict/list/str structure."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    return obj


# ── RunLogger ─────────────────────────────────────────────────────────────────

class RunLogger:
    """Creates a timestamped run directory and provides log writers."""

    def __init__(self, log_dir: str = ".agent_runs") -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = Path(log_dir) / timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.conversation_path = self.run_dir / "conversation.jsonl"
        self.terminal_log_path = self.run_dir / "terminal.log"
        self.summary_path = self.run_dir / "summary.md"
        self.run_id = timestamp

    def log_message(self, message: dict[str, Any]) -> None:
        """Append one conversation turn to conversation.jsonl."""
        safe = redact_obj(message)
        with self.conversation_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def log_terminal(self, result: dict[str, Any]) -> None:
        """Append one terminal_exec result to terminal.log."""
        safe = redact_obj(result)
        with self.terminal_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def write_summary(self, content: str) -> None:
        """Write the final assistant answer to summary.md."""
        self.summary_path.write_text(redact(content), encoding="utf-8")

    def run_url(self) -> str:
        return str(self.run_dir)
