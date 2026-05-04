"""Phase 9V provenance freeze guardrails for execution_position."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
LEDGER_PATH = EP_DIR / "docs" / "compatibility_stub_ledger.json"
AUDIT_PATH = EP_DIR / "docs" / "compatibility_stub_rewire_audit.json"

ROOT_ANCHORS = {
    "apps/reference/domains/execution_position/fsm.py",
    "apps/reference/domains/execution_position/contracts.py",
    "apps/reference/domains/execution_position/reasons.py",
    "apps/reference/domains/execution_position/utils.py",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_rewire_audit_is_valid_and_complete():
    ledger = _load_json(LEDGER_PATH)
    audit = _load_json(AUDIT_PATH)

    ledger_stub_paths = {entry["stub_path"] for entry in ledger["entries"]}
    audit_stub_paths = {entry["stub_path"] for entry in audit["entries"]}

    assert audit["summary"]["phase"] == "9V"
    assert audit["summary"]["stub_count"] == 64
    assert audit["summary"]["classification_counts"].get("docs_only_old_path", 0) == 0
    assert audit["summary"]["baseline_runtime_old_imports_present_before_phase_9p"] == 48
    assert audit["summary"]["runtime_old_imports_present_after_phase_9p"] == 0
    assert audit["summary"]["classification_counts"].get("runtime_old_imports_present", 0) == 0
    assert audit["summary"]["classification_counts"].get("tests_only_old_imports_present", 0) == 0
    assert audit["summary"]["classification_counts"].get("blocked_by_root_anchor_policy", 0) == 24
    assert audit["summary"]["classification_counts"].get("no_in_repo_old_references", 0) == 40
    assert audit["summary"]["stale_tests_only_old_imports_present"] == 0
    assert audit["summary"]["intentional_compatibility_guardrail_refs"] == 0
    assert audit["summary"]["intentional_root_anchor_guardrail_refs"] == 8
    assert audit["summary"]["ordinary_blocked_test_reference_count"] == 0
    assert audit["summary"]["unknown_blocked_test_reference_count"] == 0
    assert audit["summary"]["blocked_by_root_anchor_policy_after_phase_9r"] == 24
    assert audit["summary"]["removed_stub_count"] == 0
    assert audit["summary"]["candidate_for_removal_after_external_audit_count"] == 0
    assert audit["summary"]["global_doc_hygiene_reference_counts"] == {
        "historical_audit_record_keep": 24,
        "current_location_claim_update": 6,
        "migration_note_annotate": 1,
        "operator_public_api_reference_keep": 0,
        "ambiguous_requires_operator_review": 0,
    }
    assert audit["summary"]["provenance_freeze_counts"] == {
        "current_location_claim_count": 0,
        "historical_audit_record_count": 24,
        "migration_note_count": 1,
        "operator_public_api_reference_count": 0,
        "ambiguous_reference_count": 0,
    }
    assert audit["summary"]["remaining_blocker_kind_counts"] == {
        "historical_record_only": 5,
        "migration_note": 1,
        "operator_confirmation_required": 0,
        "major_version_boundary": 3,
    }
    assert audit["summary"]["remaining_current_doc_claim_count"] == 0
    assert audit_stub_paths == ledger_stub_paths


def test_root_anchors_are_excluded_and_paths_are_normalized():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        assert entry["stub_path"] not in ROOT_ANCHORS
        assert "\\" not in entry["stub_path"]
        assert "\\" not in entry["normalized_target_path"]
        assert entry["normalized_old_module"] == entry["stub_path"][:-3].replace("/", ".")
        assert entry["normalized_target_path"].endswith(".py")


def test_test_reference_classification_fields_are_present():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        assert "test_old_reference_count" in entry
        assert "intentional_compatibility_guardrail_count" in entry
        assert "intentional_root_anchor_guardrail_count" in entry
        assert "ordinary_test_reference_count" in entry
        assert "historical_comment_or_docstring_count" in entry
        assert "blocked_runtime_reference_count" in entry
        assert "fsm_reference_count" in entry
        assert "workspace_deletion_decision" in entry
        assert "stale_test_reference_count" in entry
        assert "root_anchor_guardrail_reference_count" in entry
        assert "unknown_test_reference_count" in entry
        assert "global_doc_reference_count" in entry
        assert "historical_audit_record_keep_count" in entry
        assert "current_location_claim_update_count" in entry
        assert "migration_note_annotate_count" in entry
        assert "operator_public_api_reference_keep_count" in entry
        assert "ambiguous_requires_operator_review_count" in entry
        assert "remaining_current_doc_claim_count" in entry
        assert "current_location_claim_count" in entry
        assert "historical_audit_record_count" in entry
        assert "migration_note_count" in entry
        assert "operator_public_api_reference_count" in entry
        assert "ambiguous_reference_count" in entry
        assert "remaining_blocker_kind" in entry


def test_no_entry_is_marked_immediately_removable():
    audit = _load_json(AUDIT_PATH)
    removable_now = {
        "remove_now",
        "remove_immediately",
        "candidate_for_immediate_removal",
    }
    for entry in audit["entries"]:
        assert entry["recommended_future_policy"] not in removable_now


def test_no_workspace_entry_is_marked_remove_now():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        assert entry["workspace_deletion_decision"] != "remove_now"


def test_runtime_old_reference_stubs_are_not_removal_candidates():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        if entry["runtime_old_reference_count"] <= 0:
            continue
        assert entry["recommended_future_policy"] != "candidate_for_removal_after_external_audit"


def test_root_anchor_blocked_entries_only_point_to_root_anchors():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        if entry["classification"] != "blocked_by_root_anchor_policy":
            continue
        assert entry["root_anchor_owner"] == "apps/reference/domains/execution_position/fsm.py"
        assert entry["root_anchor_reference_kind"] == "import_inside_fsm.py"
        assert entry["blocked_runtime_reference_count"] > 0
        assert entry["fsm_reference_count"] == entry["blocked_runtime_reference_count"]
        assert entry["ordinary_test_reference_count"] == 0
        assert entry["unknown_test_reference_count"] == 0
        blockers = set(entry["evidence_examples"].get("root_anchor_runtime_blockers", []))
        assert blockers
        assert blockers == {"apps/reference/domains/execution_position/fsm.py"}
        assert entry["evidence_examples"].get("runtime_old_references")


def test_zero_reference_stubs_have_external_api_assessment():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        if entry["classification"] != "no_in_repo_old_references":
            continue
        assert entry["external_api_assessment"] in {
            "external_public_api_assumed",
            "keep_until_major_version_boundary",
            "unknown_requires_operator_confirmation",
            "unknown_requires_dynamic_probe",
        }
        assert entry["next_required_proof"]


def test_former_deletion_candidates_are_now_keep_classified():
    audit = _load_json(AUDIT_PATH)
    keep_decisions = {
        "keep_until_major_version_boundary",
        "unknown_requires_operator_confirmation",
    }
    for entry in audit["entries"]:
        decision = entry.get("workspace_deletion_decision")
        if decision not in keep_decisions:
            continue
        assert entry["classification"] == "no_in_repo_old_references"
        assert entry["workspace_reference_count"] > 0
        assert entry["evidence_examples"].get("workspace_reference_examples")
        assert entry["recommended_future_policy"] in {
            "keep_until_major_version_boundary",
            "unknown_requires_dynamic_probe",
        }
        assert entry["global_doc_reference_count"] >= 0
        assert entry["remaining_current_doc_claim_count"] == 0
        assert entry["current_location_claim_count"] == 0
        assert entry["historical_audit_record_count"] >= 0
        assert entry["migration_note_count"] >= 0
        assert entry["operator_public_api_reference_count"] >= 0
        assert entry["ambiguous_reference_count"] >= 0
        assert entry["remaining_blocker_kind"] in {
            "historical_record_only",
            "migration_note",
            "major_version_boundary",
        }
        assert entry["historical_audit_record_keep_count"] >= 0
        assert entry["current_location_claim_update_count"] >= 0
        assert entry["migration_note_annotate_count"] >= 0
        assert entry["operator_public_api_reference_keep_count"] >= 0
        assert entry["ambiguous_requires_operator_review_count"] >= 0
        assert entry["evidence_examples"].get("historical_audit_record_keep") is not None
        assert entry["evidence_examples"].get("current_location_claim_update") is not None
        assert entry["evidence_examples"].get("migration_note_annotate") is not None
        assert entry["evidence_examples"].get("operator_public_api_reference_keep") is not None
        assert entry["evidence_examples"].get("ambiguous_requires_operator_review") is not None


def test_no_stale_test_only_old_ref_entries_remain():
    audit = _load_json(AUDIT_PATH)
    for entry in audit["entries"]:
        if entry["classification"] != "tests_only_old_imports_present":
            continue
        assert entry["stale_test_reference_count"] == 0
        assert entry["unknown_test_reference_count"] == 0


def test_intentional_guardrail_refs_are_separated_from_cleanup_debt():
    audit = _load_json(AUDIT_PATH)
    intentional_entries = [
        entry for entry in audit["entries"]
        if entry["intentional_compatibility_guardrail_count"] > 0
        or entry["intentional_root_anchor_guardrail_count"] > 0
    ]
    assert intentional_entries
    for entry in intentional_entries:
        assert entry["stale_test_reference_count"] == 0
        assert entry["unknown_test_reference_count"] == 0
        assert entry["ordinary_test_reference_count"] == 0
