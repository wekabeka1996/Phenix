"""Tests for agent arena instruction manifests."""
from __future__ import annotations

from pathlib import Path

import pytest

from deepseek_terminal_agent.sessions.agent_instruction_manifest import (
    INSTRUCTION_ROOT,
    REQUIRED_INSTRUCTION_FILES,
    InstructionManifestEntry,
    build_instruction_entry,
    build_instruction_manifest,
    changed_instruction_files,
)


def write_required_instructions(root: Path) -> None:
    instruction_root = root / INSTRUCTION_ROOT
    instruction_root.mkdir(parents=True)
    for filename, _, _ in REQUIRED_INSTRUCTION_FILES:
        (instruction_root / filename).write_text(
            f"# {filename}\n\nTest instruction body for {filename}.\n",
            encoding="utf-8",
        )


def test_manifest_preserves_priority_ordering(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)

    manifest = build_instruction_manifest(root_dir=tmp_path)

    priorities = [entry.priority for entry in manifest.instructions]
    assert priorities == sorted(priorities)
    assert manifest.missing_files == []
    assert all(entry.sha256 for entry in manifest.instructions)
    assert all(entry.version == entry.sha256[:16] for entry in manifest.instructions)


def test_manifest_detects_file_change(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    previous = build_instruction_manifest(root_dir=tmp_path)

    target = tmp_path / INSTRUCTION_ROOT / "AGENT_SKILLS.md"
    target.write_text("# AGENT_SKILLS.md\n\nUpdated behavior contract.\n", encoding="utf-8")
    current = build_instruction_manifest(root_dir=tmp_path)

    assert changed_instruction_files(previous, current) == [
        (INSTRUCTION_ROOT / "AGENT_SKILLS.md").as_posix()
    ]
    assert current.manifest_version != previous.manifest_version


def test_manifest_reports_missing_required_file(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    missing = tmp_path / INSTRUCTION_ROOT / "SESSION_OBJECTIVE.md"
    missing.unlink()

    manifest = build_instruction_manifest(root_dir=tmp_path)

    assert (INSTRUCTION_ROOT / "SESSION_OBJECTIVE.md").as_posix() in manifest.missing_files
    missing_entries = [entry for entry in manifest.instructions if entry.missing]
    assert len(missing_entries) == 1
    assert missing_entries[0].sha256 == ""
    assert missing_entries[0].version == "missing"


def test_instruction_path_traversal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        InstructionManifestEntry(path="../outside.md", priority=1, target_agents=["all"])

    with pytest.raises(ValueError):
        build_instruction_entry(
            root_dir=tmp_path,
            filename="../outside.md",
            priority=1,
            target_agents=("all",),
        )


def test_manifest_does_not_mutate_trading_config(tmp_path: Path) -> None:
    write_required_instructions(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "aurora_business.yaml"
    original = b"trading:\n  mode: testnet\n"
    config_file.write_bytes(original)

    build_instruction_manifest(root_dir=tmp_path)

    assert config_file.read_bytes() == original
