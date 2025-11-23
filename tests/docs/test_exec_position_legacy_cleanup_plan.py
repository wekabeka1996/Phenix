"""Test for EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md existence and completeness.

This test ensures the cleanup plan document exists and contains references
to key legacy files that need to be tracked for removal.
"""

import re
from pathlib import Path


def test_cleanup_plan_exists():
    """Verify that the cleanup plan document exists."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    assert doc_path.exists(), f"Cleanup plan not found at {doc_path}"


def test_cleanup_plan_mentions_key_legacy_files():
    """Verify that the cleanup plan mentions key legacy FSM files."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Key legacy files that should be tracked
    key_files = [
        "fsm_open.py",
        "fsm_manage.py",
        "fsm_close.py",
    ]

    for file in key_files:
        assert file in content, f"Cleanup plan does not mention key file: {file}"


def test_cleanup_plan_has_required_sections():
    """Verify that the cleanup plan has all required sections."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    required_sections = [
        "## Overview",
        "## File Inventory",
        "## Import/Usage Map",
        "## Proposed Removal Phases",
        "## Safety Checklist",
    ]

    for section in required_sections:
        assert section in content, f"Cleanup plan missing required section: {section}"


def test_cleanup_plan_has_phase_definitions():
    """Verify that the cleanup plan defines removal phases."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention specific phases
    phases = [
        "Phase A",
        "Phase B",
        "Phase C",
    ]

    for phase in phases:
        assert phase in content, f"Cleanup plan does not define {phase}"


def test_cleanup_plan_tracks_config_adapters():
    """Verify that the cleanup plan tracks critical config adapters."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Config adapters that should be tracked as runtime-critical
    adapters = [
        "brackets_config.py",
        "manage_config.py",
    ]

    for adapter in adapters:
        assert adapter in content, f"Cleanup plan does not track adapter: {adapter}"
        # Should mention runtime-critical status
        # Find the section that mentions this file
        pattern = re.compile(
            rf"{re.escape(adapter)}.*runtime-critical", re.IGNORECASE | re.DOTALL)
        assert pattern.search(
            content), f"{adapter} not marked as runtime-critical"


def test_cleanup_plan_has_safety_checklist_items():
    """Verify that the safety checklist has actionable items."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_LEGACY_CLEANUP_PLAN_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Find Safety Checklist section start
    assert "## Safety Checklist" in content, "Safety Checklist section not found"

    # Count checkbox items in entire document after Safety Checklist
    # (This is simpler and works even if section regex is tricky)
    safety_start = content.find("## Safety Checklist")
    next_actions_start = content.find("## Next Steps", safety_start)

    if next_actions_start == -1:
        # If no next section, search until end
        checklist_section = content[safety_start:]
    else:
        checklist_section = content[safety_start:next_actions_start]

    # Count checkbox items (both checked and unchecked)
    checkboxes = [line for line in checklist_section.split(
        '\n') if '- [ ]' in line]
    assert len(
        checkboxes) >= 5, f"Safety checklist should have at least 5 items, found {len(checkboxes)}"
