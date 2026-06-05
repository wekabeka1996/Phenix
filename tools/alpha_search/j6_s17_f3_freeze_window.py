#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.alpha_search.j6_s17_f1_common import (
    REPORTS_DIR,
    bool_from_any,
    discover_window_files,
    normalize_int,
    read_json,
    read_jsonl,
    utc_date_from_ts_ms,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PACKAGE_NAME = "J6-S17-F.3_FORWARD_WINDOW_FREEZE_AND_ARTIFACT_MATERIALIZATION"
COLLECTION_CONTRACT_PATH = REPORTS_DIR / "j6_s17_f_collection_contract.json"
DEFAULT_OUTCOME_RESULTS_PATH = REPORTS_DIR / \
    "j6_s17_c1_shadow_simulation_results.jsonl"
DEFAULT_AUGMENTED_DATASET_CSV = REPORTS_DIR / \
    "j6_s17_c1_augmented_policy_outcome_dataset.csv"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative_to_repo(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _canonical_key(record: dict[str, Any]) -> str | None:
    cycle_key = str(record.get("cycle_key") or "")
    tier = str(record.get("tier") or record.get("confidence_tier") or "")
    if not cycle_key or not tier:
        return None
    return f"{cycle_key}::{tier}"


def analyze_candidate_outcomes(path: Path, start_date: str, end_date: str) -> dict[str, Any]:
    rows = read_jsonl(path)
    canonical_counts: Counter[str] = Counter()
    missing_canonical_key_rows = 0
    dates: set[str] = set()

    for row in rows:
        key = _canonical_key(row)
        if key is None:
            missing_canonical_key_rows += 1
        else:
            canonical_counts[key] += 1
        plan_ts_ms = normalize_int(row.get("plan_ts_ms") or row.get("ts_ms"))
        date_value = utc_date_from_ts_ms(plan_ts_ms)
        if date_value and start_date <= date_value <= end_date:
            dates.add(date_value)

    duplicate_canonical_key_count = sum(
        1 for count in canonical_counts.values() if count > 1)
    missing_reasons: list[str] = []
    if missing_canonical_key_rows > 0:
        missing_reasons.append(
            f"missing_cycle_key_or_tier_rows={missing_canonical_key_rows}")

    return {
        "present": path.exists(),
        "path": path.as_posix(),
        "rows": len(rows),
        "schema_valid": missing_canonical_key_rows == 0,
        "usable_for_cycle_key_tier_join": missing_canonical_key_rows == 0,
        "uses_plan_id_as_canonical_key": False,
        "duplicate_canonical_key_count": duplicate_canonical_key_count,
        "missing_canonical_key_rows": missing_canonical_key_rows,
        "denominator_window": {
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        },
        "missing_reasons": missing_reasons,
    }


def analyze_augmented_dataset(path: Path, start_date: str, end_date: str) -> dict[str, Any]:
    rows = _read_csv_rows(path)
    header = list(rows[0].keys()) if rows else []
    required_headers = {
        "cycle_key",
        "tier",
        "plan_id",
        "join_match_method",
        "outcome_available",
        "plan_ts_ms",
    }
    header_valid = required_headers.issubset(set(header))
    join_method_counts: Counter[str] = Counter()
    dates: set[str] = set()

    for row in rows:
        join_method = str(row.get("join_match_method") or "")
        if join_method:
            join_method_counts[join_method] += 1
        plan_ts_ms = normalize_int(row.get("plan_ts_ms") or row.get("ts_ms"))
        date_value = utc_date_from_ts_ms(plan_ts_ms)
        if date_value and start_date <= date_value <= end_date:
            dates.add(date_value)

    disallowed_join_methods = sorted(
        method for method in join_method_counts if method != "cycle_key+tier")
    missing_reasons: list[str] = []
    if not header_valid:
        missing_reasons.append("missing_required_headers")
    if disallowed_join_methods:
        missing_reasons.append(
            f"disallowed_join_methods={','.join(disallowed_join_methods)}")

    return {
        "present": path.exists(),
        "path": path.as_posix(),
        "rows": len(rows),
        "schema_valid_or_header_valid": header_valid,
        "joined_by_cycle_key_tier": not disallowed_join_methods,
        "plan_id_diagnostics_only": "plan_id" not in join_method_counts,
        "join_method_counts": dict(sorted(join_method_counts.items())),
        "denominator_window": {
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
        },
        "missing_reasons": missing_reasons,
    }


def _marker_and_manifest_paths(start_date: str, end_date: str) -> tuple[Path, Path]:
    contract = read_json(COLLECTION_CONTRACT_PATH)
    marker = REPORTS_DIR / str(contract["freeze_marker_name_template"]).format(
        start_date=start_date,
        end_date=end_date,
    )
    manifest = REPORTS_DIR / str(contract["freeze_manifest_name_template"]).format(
        start_date=start_date,
        end_date=end_date,
    )
    return marker, manifest


def create_freeze_bundle(
    *,
    root: Path,
    start_date: str,
    end_date: str,
    daily_health_path: Path,
    readiness_path: Path,
    outcome_path: Path,
    augmented_dataset_path: Path,
    marker_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    daily_health = read_json(daily_health_path)
    readiness = read_json(readiness_path)

    window = dict(daily_health.get("window") or {})
    if window.get("start_date") != start_date or window.get("end_date") != end_date:
        raise ValueError("freeze_window_mismatch_with_daily_health")

    readiness_verdict = str(
        (readiness.get("readiness") or {}).get("verdict") or "")
    if readiness_verdict not in {"WINDOW_READY_TO_FREEZE", "WINDOW_FROZEN_READY_FOR_J6_S17_G"}:
        raise ValueError(f"freeze_readiness_not_satisfied:{readiness_verdict}")

    join_policy = dict(readiness.get("join_policy") or {})
    if bool(join_policy.get("plan_id_preferred_join_detected")):
        raise ValueError("join_integrity_regression_detected")

    candidate_outcomes = analyze_candidate_outcomes(
        outcome_path, start_date, end_date)
    if not candidate_outcomes["present"]:
        raise ValueError("candidate_outcomes_missing")
    if not candidate_outcomes["schema_valid"]:
        raise ValueError("candidate_outcomes_missing_cycle_key_tier")

    augmented_dataset = analyze_augmented_dataset(
        augmented_dataset_path, start_date, end_date)
    if not augmented_dataset["present"]:
        raise ValueError("candidate_augmented_dataset_missing")
    if not augmented_dataset["schema_valid_or_header_valid"]:
        raise ValueError("candidate_augmented_dataset_invalid_header")
    if not augmented_dataset["joined_by_cycle_key_tier"]:
        raise ValueError(
            "candidate_augmented_dataset_not_canonical_cycle_key_tier")
    if not augmented_dataset["plan_id_diagnostics_only"]:
        raise ValueError(
            "candidate_augmented_dataset_uses_plan_id_canonically")

    policy_sources = discover_window_files(
        root, "policy_cortex", start_date, end_date)
    verdict_sources = discover_window_files(
        root, "verdict", start_date, end_date)
    shadow_sources = discover_window_files(
        root, "shadow_entry_plan", start_date, end_date)

    counts = dict(daily_health.get("counts") or {})
    joins = dict(daily_health.get("joins") or {})
    schema = dict(daily_health.get("schema") or {})
    shadow_only = dict(daily_health.get("shadow_only_invariants") or {})

    source_artifacts = {
        "daily_health_artifact": _relative_to_repo(daily_health_path, root),
        "freeze_readiness_artifact": _relative_to_repo(readiness_path, root),
        "policy_cortex_sources": [_relative_to_repo(path, root) for path in policy_sources],
        "verdict_sources": [_relative_to_repo(path, root) for path in verdict_sources],
        "shadow_plan_sources": [_relative_to_repo(path, root) for path in shadow_sources],
        "candidate_outcomes": _relative_to_repo(outcome_path, root),
        "augmented_dataset": _relative_to_repo(augmented_dataset_path, root),
    }

    hash_paths = [
        daily_health_path,
        readiness_path,
        outcome_path,
        augmented_dataset_path,
        *policy_sources,
        *verdict_sources,
        *shadow_sources,
    ]
    hash_entries = [
        {
            "path": _relative_to_repo(path, root),
            "sha256": _sha256_file(path),
        }
        for path in hash_paths
    ]

    final_j6_s17_g_allowed = bool(
        (readiness.get("readiness") or {}).get("j6_s17_g_allowed"))
    manifest = {
        "freeze_window": {
            "start_date": start_date,
            "end_date": end_date,
            "forward_days": len(list((daily_health.get("coverage") or {}).get("dates") or [])),
        },
        "source_artifacts": source_artifacts,
        "row_counts": {
            "policy_rows": int(counts.get("policy_rows", 0)),
            "verdict_rows": int(counts.get("verdict_rows", 0)),
            "shadow_plan_rows": int(counts.get("shadow_plan_rows", 0)),
            "policy_cycles": int(counts.get("unique_policy_cycle_keys", 0)),
            "candidate_outcome_rows": int(candidate_outcomes["rows"]),
            "augmented_dataset_rows": int(augmented_dataset["rows"]),
        },
        "candidate_outcomes": candidate_outcomes,
        "candidate_augmented_dataset": augmented_dataset,
        "join_integrity": {
            "canonical_join": str(join_policy.get("canonical_outcome_join_key") or "cycle_key+tier"),
            "plan_id_usage": "diagnostics_only",
            "plan_id_preferred_join_detected": bool(join_policy.get("plan_id_preferred_join_detected")),
            "blocking_join_findings": list(join_policy.get("blocking_join_findings") or []),
        },
        "health": {
            "policy_to_verdict_join_rate": float(joins.get("policy_to_verdict_join_rate", 0.0)),
            "policy_to_shadow_join_rate": float(joins.get("policy_to_shadow_join_rate", 0.0)),
            "expected_three_tier_ladder_rate": float(joins.get("expected_three_tier_ladder_rate", 0.0)),
            "schema_validity": f"{int(schema.get('policy_rows_valid', 0))}_valid_{int(schema.get('policy_rows_invalid', 0))}_invalid",
            "shadow_only_invariants": "passed" if bool(shadow_only.get("passed")) else "failed",
            "duplicate_policy_cycle_keys": int(counts.get("duplicate_policy_cycle_keys", 0)),
            "duplicate_plan_id_count": int(counts.get("duplicate_plan_id_count", 0)),
        },
        "hashes": {
            "files": hash_entries,
        },
        "generated_at": _utc_now_iso(),
        "generated_by_package": PACKAGE_NAME,
        "j6_s17_g_allowed_after_rerun": final_j6_s17_g_allowed,
    }

    marker_lines = [
        f"package: {PACKAGE_NAME}",
        f"freeze_window: {start_date}..{end_date}",
        f"manifest_path: {_relative_to_repo(manifest_path, root)}",
        f"generated_at: {manifest['generated_at']}",
        f"readiness_verdict_source: {readiness_verdict}",
        f"j6_s17_g_allowed_after_rerun: {str(final_j6_s17_g_allowed).lower()}",
    ]

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("\n".join(marker_lines) + "\n", encoding="utf-8")
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create J6-S17-F.3 freeze marker and manifest for a validated forward window.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    parser.add_argument("--daily-health", type=Path, default=None)
    parser.add_argument("--freeze-readiness", type=Path, default=None)
    parser.add_argument("--candidate-outcomes", type=Path,
                        default=DEFAULT_OUTCOME_RESULTS_PATH)
    parser.add_argument("--augmented-dataset", type=Path,
                        default=DEFAULT_AUGMENTED_DATASET_CSV)
    parser.add_argument("--marker", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    default_marker, default_manifest = _marker_and_manifest_paths(
        args.start_date, args.end_date)
    daily_health_path = args.daily_health or REPORTS_DIR / \
        f"j6_s17_f1_daily_health_{args.start_date}_{args.end_date}.json"
    readiness_path = args.freeze_readiness or REPORTS_DIR / \
        f"j6_s17_f1_freeze_readiness_{args.start_date}_{args.end_date}.json"
    marker_path = args.marker or default_marker
    manifest_path = args.manifest or default_manifest

    manifest = create_freeze_bundle(
        root=args.root.resolve(),
        start_date=args.start_date,
        end_date=args.end_date,
        daily_health_path=daily_health_path,
        readiness_path=readiness_path,
        outcome_path=args.candidate_outcomes,
        augmented_dataset_path=args.augmented_dataset,
        marker_path=marker_path,
        manifest_path=manifest_path,
    )
    print(json.dumps({
        "marker_path": marker_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
        "j6_s17_g_allowed_after_rerun": manifest["j6_s17_g_allowed_after_rerun"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
