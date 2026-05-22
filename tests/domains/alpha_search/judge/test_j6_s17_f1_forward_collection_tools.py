from __future__ import annotations

from pathlib import Path

from tools.alpha_search.j6_s17_f1_common import (
    build_threshold_results,
    classify_health_verdict,
    evaluate_readiness,
    normalize_int,
    scan_join_policy_script,
)


def _healthy_daily_health(*, forward_days: int, policy_cycles: int) -> dict[str, object]:
    return {
        "counts": {
            "unique_policy_cycle_keys": policy_cycles,
        },
        "schema": {
            "policy_rows_invalid": 0,
        },
        "joins": {
            "policy_to_verdict_join_rate": 100.0,
            "policy_to_shadow_join_rate": 100.0,
            "expected_three_tier_ladder_rate": 100.0,
        },
        "shadow_only_invariants": {
            "passed": True,
        },
        "coverage": {
            "dates": [f"2026-05-{index + 1:02d}" for index in range(forward_days)],
        },
        "verdict": {
            "health_verdict": "COLLECTION_HEALTHY_WITH_RESIDUALS",
        },
    }


def test_classify_health_blocks_missing_policy_telemetry() -> None:
    verdict, blockers = classify_health_verdict(
        has_policy_telemetry=False,
        has_verdict_telemetry=True,
        has_shadow_telemetry=True,
        policy_rows_invalid=0,
        policy_to_verdict_join_rate=100.0,
        policy_to_shadow_join_rate=100.0,
        expected_three_tier_ladder_rate=100.0,
        shadow_invariants_passed=True,
        duplicate_policy_cycle_keys=0,
        duplicate_plan_id_count=0,
    )
    assert verdict == "BLOCKED_BY_MISSING_POLICY_TELEMETRY"
    assert blockers == ["missing_policy_telemetry"]


def test_classify_health_keeps_duplicate_keys_as_residuals() -> None:
    verdict, blockers = classify_health_verdict(
        has_policy_telemetry=True,
        has_verdict_telemetry=True,
        has_shadow_telemetry=True,
        policy_rows_invalid=0,
        policy_to_verdict_join_rate=100.0,
        policy_to_shadow_join_rate=100.0,
        expected_three_tier_ladder_rate=100.0,
        shadow_invariants_passed=True,
        duplicate_policy_cycle_keys=3,
        duplicate_plan_id_count=5,
    )
    assert verdict == "COLLECTION_HEALTHY_WITH_RESIDUALS"
    assert blockers == [
        "duplicate_policy_cycle_keys_detected",
        "duplicate_plan_id_values_detected",
    ]


def test_normalize_int_accepts_stringified_timestamp_ms() -> None:
    assert normalize_int("1778511779999") == 1778511779999


def test_build_threshold_results_marks_failures() -> None:
    results = build_threshold_results(
        {"forward_days": 7, "policy_cycles": 30000},
        {"forward_days": 2, "policy_cycles": 2410},
    )
    assert results["forward_days"] == {
        "required_min": 7,
        "observed": 2,
        "passed": False,
    }
    assert results["policy_cycles"] == {
        "required_min": 30000,
        "observed": 2410,
        "passed": False,
    }


def test_evaluate_readiness_blocks_when_daily_health_missing() -> None:
    readiness = evaluate_readiness(
        daily_health=None,
        required_thresholds={"forward_days": 7},
        outcome_layer_metrics={},
        freeze_marker_path=None,
        manifest_path=None,
        join_policy_audit=scan_join_policy_script(""),
        comparability={
            "same_policy_cortex_contract": True,
            "same_classifier_contract": True,
            "same_verdict_semantics": True,
            "same_tier_semantics": True,
            "same_join_semantics": True,
            "same_simulator_outcome_semantics": True,
            "blockers": [],
        },
        daily_health_path=None,
    )
    assert readiness["verdict"] == "BLOCKED_BY_MISSING_ARTIFACTS"
    assert readiness["j6_s17_g_allowed"] is False


def test_evaluate_readiness_returns_window_not_ready_for_short_window() -> None:
    readiness = evaluate_readiness(
        daily_health=_healthy_daily_health(forward_days=2, policy_cycles=2410),
        required_thresholds={
            "forward_days": 7,
            "policy_cycles": 30000,
            "non_low_outcome_rows": 1,
            "track_only_outcome_rows": 1,
            "dates_with_outcomes": 1,
            "symbols_with_outcomes": 1,
            "tf_sec_values_with_outcomes": 1,
        },
        outcome_layer_metrics={
            "candidate_outcomes_found": False,
            "candidate_augmented_dataset_found": False,
            "non_low_outcome_rows": 0,
            "track_only_outcome_rows": 0,
            "dates_with_outcomes": 0,
            "symbols_with_outcomes": 0,
            "tf_sec_values_with_outcomes": 0,
        },
        freeze_marker_path=Path("missing.marker"),
        manifest_path=Path("missing.json"),
        join_policy_audit=scan_join_policy_script(""),
        comparability={
            "same_policy_cortex_contract": True,
            "same_classifier_contract": True,
            "same_verdict_semantics": True,
            "same_tier_semantics": True,
            "same_join_semantics": True,
            "same_simulator_outcome_semantics": True,
            "blockers": [],
        },
        daily_health_path=Path(
            "reports/alpha_search/j6_s17_f1_daily_health_2026-05-07_2026-05-08.json"),
    )
    assert readiness["verdict"] == "WINDOW_NOT_READY"
    assert readiness["j6_s17_g_allowed"] is False
    assert readiness["thresholds"]["forward_days"]["passed"] is False
    assert readiness["thresholds"]["policy_cycles"]["passed"] is False


def test_evaluate_readiness_ready_to_freeze_without_marker() -> None:
    readiness = evaluate_readiness(
        daily_health=_healthy_daily_health(
            forward_days=8, policy_cycles=35000),
        required_thresholds={
            "forward_days": 7,
            "policy_cycles": 30000,
            "non_low_outcome_rows": 1,
            "track_only_outcome_rows": 1,
            "dates_with_outcomes": 1,
            "symbols_with_outcomes": 1,
            "tf_sec_values_with_outcomes": 1,
        },
        outcome_layer_metrics={
            "candidate_outcomes_found": True,
            "candidate_augmented_dataset_found": True,
            "non_low_outcome_rows": 12,
            "track_only_outcome_rows": 8,
            "dates_with_outcomes": 5,
            "symbols_with_outcomes": 4,
            "tf_sec_values_with_outcomes": 2,
        },
        freeze_marker_path=Path("missing.marker"),
        manifest_path=Path("missing.json"),
        join_policy_audit=scan_join_policy_script(""),
        comparability={
            "same_policy_cortex_contract": True,
            "same_classifier_contract": True,
            "same_verdict_semantics": True,
            "same_tier_semantics": True,
            "same_join_semantics": True,
            "same_simulator_outcome_semantics": True,
            "blockers": [],
        },
        daily_health_path=Path(
            "reports/alpha_search/j6_s17_f1_daily_health_2026-05-01_2026-05-08.json"),
    )
    assert readiness["verdict"] == "WINDOW_READY_TO_FREEZE"
    assert readiness["j6_s17_g_allowed"] is False


def test_plan_id_preferred_join_blocks_when_outcomes_exist() -> None:
    readiness = evaluate_readiness(
        daily_health=_healthy_daily_health(
            forward_days=8, policy_cycles=35000),
        required_thresholds={
            "forward_days": 7,
            "policy_cycles": 30000,
            "non_low_outcome_rows": 1,
            "track_only_outcome_rows": 1,
            "dates_with_outcomes": 1,
            "symbols_with_outcomes": 1,
            "tf_sec_values_with_outcomes": 1,
        },
        outcome_layer_metrics={
            "candidate_outcomes_found": True,
            "candidate_augmented_dataset_found": True,
            "non_low_outcome_rows": 12,
            "track_only_outcome_rows": 8,
            "dates_with_outcomes": 5,
            "symbols_with_outcomes": 4,
            "tf_sec_values_with_outcomes": 2,
        },
        freeze_marker_path=Path("missing.marker"),
        manifest_path=Path("missing.json"),
        join_policy_audit=scan_join_policy_script(
            """
            # Index by plan_id (preferred)
            # Try to join outcome by plan_id
            """
        ),
        comparability={
            "same_policy_cortex_contract": True,
            "same_classifier_contract": True,
            "same_verdict_semantics": True,
            "same_tier_semantics": True,
            "same_join_semantics": True,
            "same_simulator_outcome_semantics": True,
            "blockers": [],
        },
        daily_health_path=Path(
            "reports/alpha_search/j6_s17_f1_daily_health_2026-05-01_2026-05-08.json"),
    )
    assert readiness["verdict"] == "BLOCKED_BY_JOIN_INTEGRITY"
    assert readiness["j6_s17_g_allowed"] is False
