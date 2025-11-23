"""Test for EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md existence and completeness.

This test ensures the freeze checklist document exists and contains references
to key concepts related to V2 freeze criteria and legacy isolation.
"""

import re
from pathlib import Path


def test_freeze_checklist_doc_exists():
    """Verify that the freeze checklist document exists."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    assert doc_path.exists(), f"Freeze checklist doc not found at {doc_path}"


def test_freeze_checklist_doc_not_empty():
    """Verify that the freeze checklist document has substantial content."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Document should be substantial (at least 150 lines as specified)
    lines = content.split('\n')
    assert len(
        lines) >= 150, f"Document too short: {len(lines)} lines (expected 150+)"


def test_freeze_checklist_mentions_v2_runtime_facade():
    """Verify that the document mentions V2RuntimeFacade."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "V2RuntimeFacade" in content, \
        "Document does not mention V2RuntimeFacade"


def test_freeze_checklist_mentions_execpos_runtime_v2():
    """Verify that the document mentions ExecPosRuntimeV2."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "ExecPosRuntimeV2" in content, \
        "Document does not mention ExecPosRuntimeV2"


def test_freeze_checklist_mentions_execution_position_config():
    """Verify that the document mentions ExecutionPositionConfig."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "ExecutionPositionConfig" in content, \
        "Document does not mention ExecutionPositionConfig"


def test_freeze_checklist_mentions_runtime_mode():
    """Verify that the document mentions runtime_mode='v2'."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention runtime_mode configuration
    assert "runtime_mode" in content, \
        "Document does not mention runtime_mode"


def test_freeze_checklist_mentions_async_time_sync_rid():
    """Verify that the document references EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12" in content, \
        "Document does not reference EP-ADAPTER-BINANCE-ASYNC-TIME-SYNC-S12"


def test_freeze_checklist_mentions_latency_audit_doc():
    """Verify that the document references BINANCE_ADAPTER_LATENCY_AUDIT_S1.md."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "BINANCE_ADAPTER_LATENCY_AUDIT_S1" in content, \
        "Document does not reference BINANCE_ADAPTER_LATENCY_AUDIT_S1"


def test_freeze_checklist_mentions_legacy_subdirectory():
    """Verify that the document mentions legacy subdirectory path."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention the legacy or archive subdirectory structure
    legacy_paths = [
        "execution_position/legacy",
        "execution_position/archive",
    ]

    found = any(path in content for path in legacy_paths)
    assert found, \
        f"Document does not mention legacy subdirectory (checked: {legacy_paths})"


def test_freeze_checklist_has_required_sections():
    """Verify that the document has all required sections."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    required_sections = [
        "## Overview",
        "## Runtime Invariants",
        "## Config Invariants",
        "## Legacy Boundaries",
    ]

    for section in required_sections:
        assert section in content, f"Document missing required section: {section}"


def test_freeze_checklist_discusses_main_py():
    """Verify that the document discusses main.py isolation."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should discuss main.py not importing legacy FSM
    assert "main.py" in content, \
        "Document does not mention main.py"


def test_freeze_checklist_discusses_shadow_execpos():
    """Verify that the document discusses shadow_execpos/ isolation."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should discuss shadow_execpos directory not depending on legacy
    assert "shadow_execpos" in content, \
        "Document does not mention shadow_execpos"


def test_freeze_checklist_mentions_legacy_fsm_classes():
    """Verify that the document mentions legacy FSM class names."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should mention at least some legacy FSM classes
    legacy_classes = [
        "ExecPosFSM",
        "ManageFlowFSM",
        "CloseFlowFSM",
        "OpenFlowFSM"
    ]

    found_classes = [cls for cls in legacy_classes if cls in content]
    assert len(found_classes) >= 2, \
        f"Document should mention legacy FSM classes (found: {found_classes})"


def test_freeze_checklist_has_invariants():
    """Verify that the document defines specific invariants."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should define invariants with "Invariant" keyword
    invariant_pattern = re.compile(r"Invariant \d+:", re.IGNORECASE)
    invariants = invariant_pattern.findall(content)

    assert len(invariants) >= 5, \
        f"Document should define at least 5 invariants (found {len(invariants)})"


def test_freeze_checklist_has_steps_before_deletion():
    """Verify that the document has a section about steps before deletion."""
    doc_path = Path(__file__).parents[2] / "docs" / \
        "EXEC_POSITION_V2_FREEZE_CHECKLIST_S1.md"
    content = doc_path.read_text(encoding="utf-8")

    # Should have a section discussing deletion steps
    deletion_keywords = [
        "Before Final Deletion",
        "Before Deletion",
        "Steps Before",
        "Phase"
    ]

    found = any(keyword in content for keyword in deletion_keywords)
    assert found, \
        f"Document should discuss steps before deletion (checked: {deletion_keywords})"
