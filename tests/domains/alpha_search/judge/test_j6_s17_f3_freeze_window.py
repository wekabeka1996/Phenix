from __future__ import annotations

import csv
import json
from pathlib import Path

from tools.alpha_search.j6_s17_f3_freeze_window import create_freeze_bundle


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_window_logs(root: Path, start_date: str) -> None:
    logs_dir = root / "logs" / "judge_experts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    sample = {"cycle_key": "ENTRY:BTCUSDT:300:1778457600000",
              "confidence_tier": "low"}
    for prefix in ("policy_cortex", "verdict", "shadow_entry_plan"):
        _write_jsonl(
            logs_dir / f"{prefix}_BTCUSDT_{start_date}.jsonl", [sample])


def _base_daily_health(start_date: str, end_date: str) -> dict[str, object]:
    return {
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "source": "logs/judge_experts",
        },
        "counts": {
            "policy_rows": 1,
            "verdict_rows": 1,
            "shadow_plan_rows": 3,
            "unique_policy_cycle_keys": 1,
            "duplicate_policy_cycle_keys": 0,
            "duplicate_plan_id_count": 0,
        },
        "schema": {
            "policy_rows_valid": 1,
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
            "dates": [
                "2026-05-10",
                "2026-05-11",
                "2026-05-12",
                "2026-05-13",
                "2026-05-14",
                "2026-05-15",
                "2026-05-16",
                "2026-05-17",
            ],
        },
        "verdict": {
            "health_verdict": "COLLECTION_HEALTHY_WITH_RESIDUALS",
        },
    }


def _base_readiness() -> dict[str, object]:
    return {
        "readiness": {
            "verdict": "WINDOW_READY_TO_FREEZE",
            "j6_s17_g_allowed": False,
        },
        "join_policy": {
            "canonical_outcome_join_key": "cycle_key+tier",
            "plan_id_preferred_join_detected": False,
            "blocking_join_findings": [],
        },
    }


def test_create_freeze_bundle_writes_marker_and_manifest(tmp_path: Path) -> None:
    start_date = "2026-05-10"
    end_date = "2026-05-17"
    reports_dir = tmp_path / "reports" / "alpha_search"
    _write_window_logs(tmp_path, start_date)

    daily_health_path = reports_dir / \
        f"j6_s17_f1_daily_health_{start_date}_{end_date}.json"
    readiness_path = reports_dir / \
        f"j6_s17_f1_freeze_readiness_{start_date}_{end_date}.json"
    outcome_path = reports_dir / "j6_s17_c1_shadow_simulation_results.jsonl"
    dataset_path = reports_dir / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
    marker_path = reports_dir / \
        f"j6_s17_f_window_frozen_{start_date}_{end_date}.marker"
    manifest_path = reports_dir / \
        f"j6_s17_f_window_manifest_{start_date}_{end_date}.json"

    _write_json(reports_dir / "j6_s17_f_collection_contract.json", {
        "freeze_marker_name_template": "j6_s17_f_window_frozen_{start_date}_{end_date}.marker",
        "freeze_manifest_name_template": "j6_s17_f_window_manifest_{start_date}_{end_date}.json",
    })
    _write_json(daily_health_path, _base_daily_health(start_date, end_date))
    _write_json(readiness_path, _base_readiness())
    _write_jsonl(outcome_path, [{
        "cycle_key": "ENTRY:BTCUSDT:300:1778457600000",
        "tier": "medium",
        "plan_id": "sep_medium_BTCUSDT_1778457600000",
        "plan_ts_ms": 1778457600000,
        "outcome_available": True,
        "simulation_status": "success",
    }])
    _write_csv(dataset_path, [{
        "cycle_key": "ENTRY:BTCUSDT:300:1778457600000",
        "tier": "medium",
        "plan_id": "sep_medium_BTCUSDT_1778457600000",
        "join_match_method": "cycle_key+tier",
        "outcome_available": "True",
        "plan_ts_ms": "1778457600000",
    }])

    manifest = create_freeze_bundle(
        root=tmp_path,
        start_date=start_date,
        end_date=end_date,
        daily_health_path=daily_health_path,
        readiness_path=readiness_path,
        outcome_path=outcome_path,
        augmented_dataset_path=dataset_path,
        marker_path=marker_path,
        manifest_path=manifest_path,
    )

    assert marker_path.is_file()
    assert manifest_path.is_file()
    assert manifest["freeze_window"]["start_date"] == start_date
    assert manifest["source_artifacts"]["candidate_outcomes"].endswith(
        "j6_s17_c1_shadow_simulation_results.jsonl")
    assert manifest["candidate_augmented_dataset"]["joined_by_cycle_key_tier"] is True
    assert manifest["join_integrity"]["canonical_join"] == "cycle_key+tier"
    assert manifest["hashes"]["files"]


def test_create_freeze_bundle_rejects_plan_id_join_usage(tmp_path: Path) -> None:
    start_date = "2026-05-10"
    end_date = "2026-05-17"
    reports_dir = tmp_path / "reports" / "alpha_search"
    _write_window_logs(tmp_path, start_date)

    daily_health_path = reports_dir / \
        f"j6_s17_f1_daily_health_{start_date}_{end_date}.json"
    readiness_path = reports_dir / \
        f"j6_s17_f1_freeze_readiness_{start_date}_{end_date}.json"
    outcome_path = reports_dir / "j6_s17_c1_shadow_simulation_results.jsonl"
    dataset_path = reports_dir / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
    marker_path = reports_dir / \
        f"j6_s17_f_window_frozen_{start_date}_{end_date}.marker"
    manifest_path = reports_dir / \
        f"j6_s17_f_window_manifest_{start_date}_{end_date}.json"

    _write_json(reports_dir / "j6_s17_f_collection_contract.json", {
        "freeze_marker_name_template": "j6_s17_f_window_frozen_{start_date}_{end_date}.marker",
        "freeze_manifest_name_template": "j6_s17_f_window_manifest_{start_date}_{end_date}.json",
    })
    _write_json(daily_health_path, _base_daily_health(start_date, end_date))
    _write_json(readiness_path, _base_readiness())
    _write_jsonl(outcome_path, [{
        "cycle_key": "ENTRY:BTCUSDT:300:1778457600000",
        "tier": "medium",
        "plan_id": "sep_medium_BTCUSDT_1778457600000",
        "plan_ts_ms": 1778457600000,
        "outcome_available": True,
        "simulation_status": "success",
    }])
    _write_csv(dataset_path, [{
        "cycle_key": "ENTRY:BTCUSDT:300:1778457600000",
        "tier": "medium",
        "plan_id": "sep_medium_BTCUSDT_1778457600000",
        "join_match_method": "plan_id",
        "outcome_available": "True",
        "plan_ts_ms": "1778457600000",
    }])

    try:
        create_freeze_bundle(
            root=tmp_path,
            start_date=start_date,
            end_date=end_date,
            daily_health_path=daily_health_path,
            readiness_path=readiness_path,
            outcome_path=outcome_path,
            augmented_dataset_path=dataset_path,
            marker_path=marker_path,
            manifest_path=manifest_path,
        )
    except ValueError as exc:
        assert str(
            exc) == "candidate_augmented_dataset_not_canonical_cycle_key_tier"
    else:
        raise AssertionError("expected canonical join validation failure")
