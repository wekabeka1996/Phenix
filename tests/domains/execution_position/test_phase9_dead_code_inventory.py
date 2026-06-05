"""Phase 9F dead/dormant surface inventory guardrails for execution_position."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
LEDGER_PATH = EP_DIR / "docs" / "dead_code_inventory.json"
STUB_LEDGER_PATH = EP_DIR / "docs" / "compatibility_stub_ledger.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_dead_code_inventory_is_valid_json():
    ledger = _load_json(LEDGER_PATH)
    assert ledger["phase"] == "9G"
    assert ledger["created_in_phase"] == "9F"
    assert ledger["package"] == "execution_position"
    assert isinstance(ledger["entries"], list)
    assert isinstance(ledger["removable_candidates"], list)
    assert isinstance(ledger["phase_9g_focus_surfaces"], list)


def test_inventory_paths_and_stub_ledger_exist():
    ledger = _load_json(LEDGER_PATH)
    assert STUB_LEDGER_PATH.exists()
    assert ledger["compatibility_stubs"]["ledger_path"] == (
        "apps/reference/domains/execution_position/docs/compatibility_stub_ledger.json"
    )
    for entry in ledger["entries"]:
        target = PROJECT_ROOT / entry["path"]
        assert target.exists(), f"Missing inventory path: {entry['path']}"


def test_compatibility_stubs_are_protected_and_count_matches():
    ledger = _load_json(LEDGER_PATH)
    stub_ledger = _load_json(STUB_LEDGER_PATH)
    assert ledger["compatibility_stubs"]["protected_in_phase_9f"] is True
    assert ledger["compatibility_stubs"]["count"] == len(stub_ledger["entries"]) == 64
    assert not ledger["removable_candidates"], (
        "Phase 9F must not mark compatibility stubs or other EP surfaces removable "
        "without a separate import-rewire or external-import audit."
    )


def test_root_anchors_are_excluded_from_removal():
    ledger = _load_json(LEDGER_PATH)
    root_anchors = set(ledger["root_anchor_exclusions"])
    removable_paths = {item["path"] for item in ledger["removable_candidates"]}
    assert root_anchors.isdisjoint(removable_paths)
    assert root_anchors == {
        "apps/reference/domains/execution_position/fsm.py",
        "apps/reference/domains/execution_position/contracts.py",
        "apps/reference/domains/execution_position/reasons.py",
        "apps/reference/domains/execution_position/utils.py",
    }


def test_phase_9g_focus_surfaces_have_upgraded_evidence_fields():
    ledger = _load_json(LEDGER_PATH)
    focus = set(ledger["phase_9g_focus_surfaces"])
    matched = 0
    for entry in ledger["entries"]:
        exact_match = entry["surface"] in focus
        file_surface_match = entry["path"] in focus and entry["surface"] == entry["path"]
        if not exact_match and not file_surface_match:
            continue
        matched += 1
        assert isinstance(entry["import_site_count"], int)
        assert isinstance(entry["patch_target_count"], int)
        assert isinstance(entry["test_reference_count"], int)
        assert isinstance(entry["docs_reference_count"], int)
        assert isinstance(entry["runtime_wiring_reference_count"], int)
        assert isinstance(entry["recommended_next_action"], str)
        assert "runtime_wiring_references" in entry["proof"]
    assert matched == 5


def test_retained_surface_classifications_are_frozen():
    ledger = _load_json(LEDGER_PATH)
    expected = {
        "apps/reference/domains/execution_position/telemetry/metrics_aggregator.py": "dormant_but_intentional",
        "apps/reference/domains/execution_position/telemetry/drift_monitor.py": "shadow_runtime",
        "apps/reference/domains/execution_position/guardian/idempotent_cancel.py::IdempotentCancelHelper.generate_deterministic_clientOrderId": "active_test_only",
        "apps/reference/domains/execution_position/flows/close/fsm_close.py::CloseFlowFSM._check_close_conditions": "dormant_but_intentional",
        "apps/reference/domains/execution_position/orchestration/event_handlers.py::DEAD-CODE(PHASE 4) marker near reservation_id write": "dormant_but_intentional",
    }
    got = {entry["surface"]: entry["classification"] for entry in ledger["entries"]}
    for surface, classification in expected.items():
        assert got[surface] == classification


def test_retained_surface_intent_proof_survives():
    metrics_text = (EP_DIR / "telemetry" / "metrics_aggregator.py").read_text(encoding="utf-8")
    drift_text = (EP_DIR / "telemetry" / "drift_monitor.py").read_text(encoding="utf-8")
    close_text = (EP_DIR / "flows" / "close" / "fsm_close.py").read_text(encoding="utf-8")

    assert "Structured JSON event logging for monitoring and compliance." in metrics_text
    assert "Shadow-Mode Validation" in drift_text
    assert "Off-path computation" in drift_text
    assert "This domain only executes CMD:CLOSE." in close_text
