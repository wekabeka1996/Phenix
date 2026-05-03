"""Safety classification for terminal commands.

Dangerous commands are BLOCKED outright (non-interactive) or require explicit
human approval (interactive + require_approval_for_dangerous=true).

The classifier uses regex patterns. It is conservative — it blocks obviously
destructive, privilege-escalating, or secret-exfiltrating commands, while
allowing normal dev operations (ls, git, pytest, pip, cat project files, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CommandRisk(Enum):
    SAFE = "safe"
    DANGEROUS = "dangerous"


# Each entry: (regex_pattern, human_readable_reason)
_DANGEROUS_SPEC: list[tuple[str, str]] = [
    # ── Destructive filesystem ──────────────────────────────────────────────
    (r"rm\s+.*-[a-zA-Z]*r[a-zA-Z]*\s+/",
     "recursive delete at filesystem root"),
    (r"rm\s+-[a-zA-Z]*f[a-zA-Z]*\s+[/~]", "force delete at / or ~"),
    (r"\brm\s+-rf\b", "recursive force remove"),
    (r"\brm\s+-fr\b", "recursive force remove"),
    # ── Disk / filesystem format ─────────────────────────────────────────────
    (r"\bmkfs\b", "filesystem format command"),
    (r"\bdd\s+if=", "low-level disk copy (dd)"),
    # ── System control ────────────────────────────────────────────────────────
    (r"\bshutdown\b", "system shutdown"),
    (r"\breboot\b", "system reboot"),
    (r"\bhalt\b", "system halt"),
    (r"\bpoweroff\b", "system poweroff"),
    # ── Fork bomb ─────────────────────────────────────────────────────────────
    (r":\s*\(\s*\)\s*\{", "fork bomb pattern"),
    # ── Privilege escalation ──────────────────────────────────────────────────
    (r"\bsudo\b", "sudo privilege escalation"),
    (r"\bsu\s+[-]", "su with login flag (su -, su -l, su -c)"),
    (r"\bsu\s+root\b", "su root explicit"),
    # ── Permission bombs ──────────────────────────────────────────────────────
    (r"chmod\s+.*-R\s+777\s+/", "recursive chmod 777 /"),
    (r"chmod\s+-R\s+777\s+/", "recursive chmod 777 /"),
    (r"chown\s+.*-R\s+\S+\s+/", "recursive chown /"),
    # ── Remote code execution via pipe to shell ───────────────────────────────
    (r"curl\s+\S+.*\|\s*(?:ba)?sh", "curl pipe to shell"),
    (r"wget\s+\S+.*\|\s*(?:ba)?sh", "wget pipe to shell"),
    (r"curl\s+\S+.*\|\s*bash\b", "curl pipe to bash"),
    (r"curl\s+\S+.*\|\s*sh\b", "curl pipe to sh"),
    # ── Docker daemon access ──────────────────────────────────────────────────
    (r"docker\.sock", "docker socket access (host escape)"),
    (r"/var/run/docker", "docker daemon socket path"),
    # ── Credential exfiltration ───────────────────────────────────────────────
    (r"cat\s+\.env\b", "read .env secrets"),
    (r"cat\s+.*\.env\b", "read .env-style file"),
    (r"~[/\\]\.ssh\b", "SSH credentials access"),
    (r"~[/\\]\.aws\b", "AWS credentials access"),
    (r"~[/\\]\.config\b", "system config credentials"),
    (r"\bprintenv\b", "full environment variable dump"),
    (r"(?:^|\s)env\s*$", "bare env dump (all env vars)"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE | re.MULTILINE), reason)
    for p, reason in _DANGEROUS_SPEC
]


@dataclass
class SafetyResult:
    risk: CommandRisk
    reason: str = ""
    pattern: str = ""


def classify(cmd: str) -> SafetyResult:
    """Classify a command as SAFE or DANGEROUS.

    Returns the first matching dangerous pattern if any, otherwise SAFE.
    """
    stripped = cmd.strip()
    for compiled, reason in _COMPILED:
        if compiled.search(stripped):
            return SafetyResult(
                risk=CommandRisk.DANGEROUS,
                reason=reason,
                pattern=compiled.pattern,
            )
    return SafetyResult(risk=CommandRisk.SAFE)


def is_dangerous(cmd: str) -> bool:
    """Convenience wrapper — returns True if the command is dangerous."""
    return classify(cmd).risk == CommandRisk.DANGEROUS
