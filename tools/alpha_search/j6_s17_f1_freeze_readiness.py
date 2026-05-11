#!/usr/bin/env python3
from __future__ import annotations
from tools.alpha_search.j6_s17_f1_common import (
    DEFAULT_AUGMENTED_DATASET_CSV,
    DEFAULT_OUTCOME_RESULTS_PATH,
    REPORTS_DIR,
    bool_from_any,
    evaluate_readiness,
    infer_default_window,
    normalize_int,
    read_csv_rows,
    read_json,
    scan_join_policy_script,
    utc_date_from_ts_ms,
    write_json,
)

import argparse
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REQUIREMENTS_PATH = REPORTS_DIR / "j6_s17_f_forward_window_requirements.json"
CHECKLIST_PATH = REPORTS_DIR / "j6_s17_f_collection_freeze_checklist.md"
COMPARABILITY_PATH = REPORTS_DIR / "j6_s17_f_old_vs_new_comparability_plan.json"
COLLECTION_CONTRACT_PATH = REPORTS_DIR / "j6_s17_f_collection_contract.json"
LEGACY_JOIN_SCRIPT_PATHS = [
    REPO_ROOT / "tools" / "alpha_search" / "j6_s17_b_forward_outcome_join.py",
    REPO_ROOT / "tools" / "alpha_search" / "j6_s17_c1_shadow_outcomes.py",
]


def _resolve_window(root: Path, start_date: str | None, end_date: str | None) -> tuple[str, str]:
    if start_date and end_date:
        return start_date, end_date
    inferred_start, inferred_end, _ = infer_default_window(root)
    if not inferred_start or not inferred_end:
        raise FileNotFoundError(
            "No common policy/verdict/shadow window found under logs/judge_experts")
    return inferred_start, inferred_end


def _default_daily_health_path(start_date: str, end_date: str) -> Path:
    return REPORTS_DIR / f"j6_s17_f1_daily_health_{start_date}_{end_date}.json"


def _freeze_paths(collection_contract: dict[str, Any], start_date: str, end_date: str) -> tuple[Path, Path]:
    marker = REPORTS_DIR / str(collection_contract["freeze_marker_name_template"]).format(
        start_date=start_date,
        end_date=end_date,
    )
    manifest = REPORTS_DIR / str(collection_contract["freeze_manifest_name_template"]).format(
        start_date=start_date,
        end_date=end_date,
    )
    return marker, manifest


def _load_outcome_layer_metrics(start_date: str, end_date: str) -> dict[str, Any]:
    metrics = {
        "candidate_outcomes_found": DEFAULT_OUTCOME_RESULTS_PATH.exists(),
        "candidate_augmented_dataset_found": DEFAULT_AUGMENTED_DATASET_CSV.exists(),
        "non_low_outcome_rows": 0,
        "track_only_outcome_rows": 0,
        "dates_with_outcomes": 0,
        "symbols_with_outcomes": 0,
        "tf_sec_values_with_outcomes": 0,
    }
    if not DEFAULT_AUGMENTED_DATASET_CSV.exists():
        return metrics

    rows = read_csv_rows(DEFAULT_AUGMENTED_DATASET_CSV)
    dates: set[str] = set()
    symbols: set[str] = set()
    tf_secs: set[str] = set()

    for row in rows:
        if not bool_from_any(row.get("outcome_available")):
            continue
        plan_ts = normalize_int(row.get("plan_ts_ms") or row.get("ts_ms"))
        date_value = utc_date_from_ts_ms(plan_ts)
        if date_value and (date_value < start_date or date_value > end_date):
            continue
        tier = str(row.get("tier") or row.get("confidence_tier") or "")
        classifier_output = str(row.get("classifier_output") or "")
        if tier.lower() != "low":
            metrics["non_low_outcome_rows"] += 1
        if classifier_output == "TRACK_ONLY":
            metrics["track_only_outcome_rows"] += 1
        if date_value:
            dates.add(date_value)
        symbol = str(row.get("symbol") or "")
        if symbol:
            symbols.add(symbol)
        tf_sec = str(row.get("tf_sec") or "")
        if tf_sec:
            tf_secs.add(tf_sec)

    metrics["dates_with_outcomes"] = len(dates)
    metrics["symbols_with_outcomes"] = len(symbols)
    metrics["tf_sec_values_with_outcomes"] = len(tf_secs)
    return metrics


def _join_policy_audit(collection_contract: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    plan_id_preferred = False
    for path in LEGACY_JOIN_SCRIPT_PATHS:
        audit = scan_join_policy_script(path.read_text(encoding="utf-8"))
        if audit["plan_id_preferred_join_detected"]:
            plan_id_preferred = True
            findings.extend(
                f"{path.name}:{item}" for item in audit["blocking_join_findings"])
    return {
        "canonical_outcome_join_key": collection_contract.get("canonical_outcome_join_key", "cycle_key+tier"),
        "plan_id_alone_forbidden": bool(collection_contract.get("plan_id_alone_forbidden", True)),
        "plan_id_preferred_join_detected": plan_id_preferred,
        "blocking_join_findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate J6-S17-F.1 freeze readiness artifact.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--daily-health", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    start_date, end_date = _resolve_window(
        root, args.start_date, args.end_date)
    requirements = read_json(REQUIREMENTS_PATH)
    collection_contract = read_json(COLLECTION_CONTRACT_PATH)
    comparability = read_json(COMPARABILITY_PATH)
    _ = CHECKLIST_PATH.read_text(encoding="utf-8")

    daily_health_path = args.daily_health or _default_daily_health_path(
        start_date, end_date)
    daily_health = read_json(
        daily_health_path) if daily_health_path.exists() else None

    freeze_marker_path, manifest_path = _freeze_paths(
        collection_contract, start_date, end_date)
    outcome_layer_metrics = _load_outcome_layer_metrics(start_date, end_date)
    join_policy = _join_policy_audit(collection_contract)
    readiness_eval = evaluate_readiness(
        daily_health=daily_health,
        required_thresholds=requirements["thresholds"],
        outcome_layer_metrics=outcome_layer_metrics,
        freeze_marker_path=freeze_marker_path,
        manifest_path=manifest_path,
        join_policy_audit=join_policy,
        comparability=comparability,
        daily_health_path=daily_health_path,
    )

    artifact = {
        "readiness": {
            "verdict": readiness_eval["verdict"],
            "j6_s17_g_allowed": readiness_eval["j6_s17_g_allowed"],
            "frozen_window_found": bool(readiness_eval["freeze_marker_found"] and readiness_eval["manifest_found"]),
            "freeze_marker_path": freeze_marker_path.as_posix(),
            "manifest_path": manifest_path.as_posix(),
        },
        "thresholds": readiness_eval["thresholds"],
        "health_inputs": readiness_eval["health_inputs"],
        "comparability": {
            "same_policy_cortex_contract": comparability["same_policy_cortex_contract"],
            "same_classifier_contract": comparability["same_classifier_contract"],
            "same_verdict_semantics": comparability["same_verdict_semantics"],
            "same_tier_semantics": comparability["same_tier_semantics"],
            "same_join_semantics": comparability["same_join_semantics"],
            "same_simulator_outcome_semantics": comparability["same_simulator_outcome_semantics"],
            "blockers": list(comparability.get("blockers") or []),
        },
        "join_policy": join_policy,
        "blockers": readiness_eval["blockers"],
        "next_action": readiness_eval["next_action"],
    }

    output_path = args.output or REPORTS_DIR / \
        f"j6_s17_f1_freeze_readiness_{start_date}_{end_date}.json"
    write_json(output_path, artifact)
    print(output_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
