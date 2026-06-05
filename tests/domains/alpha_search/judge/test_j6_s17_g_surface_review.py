from __future__ import annotations

import csv
import json
from pathlib import Path

from tools.alpha_search.j6_s17_g_surface_review import (
    CANONICAL_JOIN,
    check_frozen_preflight,
    classify_surface,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_check_frozen_preflight_passes_when_manifest_and_hashes_match(tmp_path: Path) -> None:
    candidate_outcomes = tmp_path / "reports" / "alpha_search" / "j6_s17_c1_shadow_simulation_results.jsonl"
    augmented_dataset = tmp_path / "reports" / "alpha_search" / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
    marker_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f_window_frozen_2026-05-10_2026-05-17.marker"
    manifest_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f_window_manifest_2026-05-10_2026-05-17.json"
    readiness_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f1_freeze_readiness_2026-05-10_2026-05-17.json"

    _write_text(candidate_outcomes, '{"cycle_key":"x","tier":"low"}\n')
    _write_text(augmented_dataset, 'cycle_key,tier,plan_id,join_match_method,outcome_available,plan_ts_ms\nfoo,low,p1,cycle_key+tier,True,1778457600000\n')
    _write_text(marker_path, 'ok\n')
    _write_json(readiness_path, {
        "readiness": {
            "verdict": "WINDOW_FROZEN_READY_FOR_J6_S17_G",
            "j6_s17_g_allowed": True,
        },
        "join_policy": {
            "canonical_outcome_join_key": CANONICAL_JOIN,
            "plan_id_preferred_join_detected": False,
        },
    })
    _write_json(manifest_path, {
        "join_integrity": {
            "canonical_join": CANONICAL_JOIN,
            "plan_id_usage": "diagnostics_only",
        },
        "hashes": {
            "files": [
                {"path": "reports/alpha_search/j6_s17_c1_shadow_simulation_results.jsonl", "sha256": _sha256(candidate_outcomes)},
                {"path": "reports/alpha_search/j6_s17_c1_augmented_policy_outcome_dataset.csv", "sha256": _sha256(augmented_dataset)},
            ]
        },
    })

    result = check_frozen_preflight(
        root=tmp_path,
        manifest_path=manifest_path,
        marker_path=marker_path,
        readiness_path=readiness_path,
        candidate_outcomes_path=candidate_outcomes,
        augmented_dataset_path=augmented_dataset,
    )

    assert result["passed"] is True
    assert result["manifest_hashes_match_current_files"] is True
    assert result["canonical_join_confirmed"] is True
    assert result["blockers"] == []


def test_check_frozen_preflight_blocks_on_hash_mismatch(tmp_path: Path) -> None:
    candidate_outcomes = tmp_path / "reports" / "alpha_search" / "j6_s17_c1_shadow_simulation_results.jsonl"
    augmented_dataset = tmp_path / "reports" / "alpha_search" / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
    marker_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f_window_frozen_2026-05-10_2026-05-17.marker"
    manifest_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f_window_manifest_2026-05-10_2026-05-17.json"
    readiness_path = tmp_path / "reports" / "alpha_search" / "j6_s17_f1_freeze_readiness_2026-05-10_2026-05-17.json"

    _write_text(candidate_outcomes, '{"cycle_key":"x","tier":"low"}\n')
    _write_text(augmented_dataset, 'cycle_key,tier,plan_id,join_match_method,outcome_available,plan_ts_ms\nfoo,low,p1,cycle_key+tier,True,1778457600000\n')
    _write_text(marker_path, 'ok\n')
    _write_json(readiness_path, {
        "readiness": {
            "verdict": "WINDOW_FROZEN_READY_FOR_J6_S17_G",
            "j6_s17_g_allowed": True,
        },
        "join_policy": {
            "canonical_outcome_join_key": CANONICAL_JOIN,
            "plan_id_preferred_join_detected": False,
        },
    })
    _write_json(manifest_path, {
        "join_integrity": {
            "canonical_join": CANONICAL_JOIN,
            "plan_id_usage": "diagnostics_only",
        },
        "hashes": {
            "files": [
                {"path": "reports/alpha_search/j6_s17_c1_shadow_simulation_results.jsonl", "sha256": "bad"},
            ]
        },
    })

    result = check_frozen_preflight(
        root=tmp_path,
        manifest_path=manifest_path,
        marker_path=marker_path,
        readiness_path=readiness_path,
        candidate_outcomes_path=candidate_outcomes,
        augmented_dataset_path=augmented_dataset,
    )

    assert result["passed"] is False
    assert result["manifest_hashes_match_current_files"] is False
    assert "manifest_hashes_do_not_match_current_files" in result["blockers"]


def test_classify_surface_is_conservative_about_contamination_and_support() -> None:
    classification, reasons = classify_surface({
        "duplicate_contained_rows": 5,
        "metric_rows": 40,
        "support_count": 40,
        "unknown_count": 0,
        "unmatched_count": 5,
        "invalid_rows": 0,
        "avg_return": 0.4,
        "median_return": 0.3,
        "win_rate": 60.0,
    })
    assert classification == "DENOMINATOR_CONTAMINATED"
    assert reasons == ["duplicate_canonical_key_contained_rows_present"]

    classification, reasons = classify_surface({
        "duplicate_contained_rows": 0,
        "metric_rows": 120,
        "support_count": 120,
        "unknown_count": 0,
        "unmatched_count": 0,
        "invalid_rows": 0,
        "avg_return": 0.25,
        "median_return": 0.2,
        "win_rate": 62.0,
    })
    assert classification == "FORWARD_SUPPORTED"
    assert reasons == ["positive_return_and_win_rate"]

    classification, reasons = classify_surface({
        "duplicate_contained_rows": 0,
        "metric_rows": 20,
        "support_count": 20,
        "unknown_count": 0,
        "unmatched_count": 0,
        "invalid_rows": 0,
        "avg_return": 0.3,
        "median_return": 0.2,
        "win_rate": 70.0,
    })
    assert classification == "INSUFFICIENT_SUPPORT"
    assert reasons == ["support_below_30"]