"""Tests for agent instruction hot reload runtime helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from deepseek_terminal_agent.sessions.agent_instruction_manifest import (
    INSTRUCTION_ROOT,
    REQUIRED_INSTRUCTION_FILES,
    build_instruction_manifest,
)
from deepseek_terminal_agent.sessions.agent_instruction_runtime import (
    acknowledge_instruction_manifest,
    agent_instruction_preflight,
)


def write_required_instructions(root: Path) -> None:
    instruction_root = root / INSTRUCTION_ROOT
    instruction_root.mkdir(parents=True)
    for filename, _, _ in REQUIRED_INSTRUCTION_FILES:
        (instruction_root / filename).write_text(
            f"# {filename}\n\nRuntime test instruction body.\n",
            encoding="utf-8",
        )


def test_preflight_returns_changed_files_and_refresh_payload(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    previous = build_instruction_manifest(root_dir=tmp_path)
    (tmp_path / INSTRUCTION_ROOT / "FEATURE_TRUST_GUIDE.md").write_text(
        "# FEATURE_TRUST_GUIDE.md\n\nTrust only runtime-proven features.\n",
        encoding="utf-8",
    )

    result = agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
        previous_manifest=previous,
    )

    changed = (INSTRUCTION_ROOT / "FEATURE_TRUST_GUIDE.md").as_posix()
    assert result.changed_files == [changed]
    assert result.missing_files == []
    assert result.ack_required is True
    assert result.event_payload["event_type"] == "agent_instruction_refresh"
    assert result.event_payload["status"] == "changed"
    assert result.event_payload["changed_files"] == [changed]
    assert result.event_payload["manifest_version"] == result.manifest_version


def test_preflight_reports_missing_required_file(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    (tmp_path / INSTRUCTION_ROOT / "AGENT_ARENA_RULES.md").unlink()

    result = agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
    )

    missing = (INSTRUCTION_ROOT / "AGENT_ARENA_RULES.md").as_posix()
    assert missing in result.missing_files
    assert result.ack_required is True
    assert result.event_payload["status"] == "missing_required_files"


def test_acknowledge_instruction_manifest_produces_ack(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    manifest = build_instruction_manifest(root_dir=tmp_path)

    ack = acknowledge_instruction_manifest(
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
        manifest_version=manifest.manifest_version,
    )

    assert ack.agent_id == "agent-3"
    assert ack.agent_number == 3
    assert ack.session_id == "session-1"
    assert ack.manifest_version == manifest.manifest_version
    assert ack.acknowledged_at


def test_ack_rejects_path_traversal_identifiers() -> None:
    with pytest.raises(ValueError):
        acknowledge_instruction_manifest(
            agent_id="../agent",
            agent_number=3,
            session_id="session-1",
            manifest_version="abc123",
        )


def test_preflight_does_not_mutate_trading_config(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "aurora_business.yaml"
    original = b"risk:\n  live: false\n"
    config_file.write_bytes(original)

    agent_instruction_preflight(
        root_dir=str(tmp_path),
        agent_id="agent-3",
        agent_number=3,
        session_id="session-1",
    )

    assert config_file.read_bytes() == original
