#!/usr/bin/env python3
from __future__ import annotations
from tools.alpha_search.j6_s17_f1_common import (
    DEFAULT_AUGMENTED_DATASET_CSV,
    DEFAULT_OUTCOME_RESULTS_PATH,
    POLICY_SCHEMA_PATH,
    REPORTS_DIR,
    classify_health_verdict,
    discover_window_files,
    duplicate_key_count,
    infer_default_window,
    parse_symbol_and_date,
    pct,
    read_json,
    read_jsonl,
    summarize_shadow_invariants,
    utc_date_from_ts_ms,
    validate_policy_rows,
    write_json,
)

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TEMPLATE_PATH = REPORTS_DIR / "j6_s17_f_daily_health_template.json"
HEALTH_SPEC_PATH = REPORTS_DIR / "j6_s17_f_collection_health_check_spec.json"
COLLECTION_CONTRACT_PATH = REPORTS_DIR / "j6_s17_f_collection_contract.json"


def _load_rows(paths: list[Path], prefix: str) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    rows: list[dict[str, Any]] = []
    rows_by_date: Counter[str] = Counter()
    rows_by_symbol: Counter[str] = Counter()
    for path in paths:
        fallback_symbol, date_str = parse_symbol_and_date(path, prefix)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows.append(row)
                if date_str:
                    rows_by_date[date_str] += 1
                symbol = str(row.get("symbol") or fallback_symbol or "UNKNOWN")
                rows_by_symbol[symbol] += 1
    return rows, rows_by_date, rows_by_symbol


def _shadow_join_overlap(shadow_rows: list[dict[str, Any]], outcome_rows: list[dict[str, Any]]) -> int:
    shadow_join_keys = {
        f"{row.get('cycle_key')}::{row.get('confidence_tier') or row.get('tier')}"
        for row in shadow_rows
        if row.get("cycle_key") and (row.get("confidence_tier") or row.get("tier"))
    }
    overlap = 0
    for row in outcome_rows:
        cycle_key = row.get("cycle_key")
        tier = row.get("tier") or row.get("confidence_tier")
        if cycle_key and tier and f"{cycle_key}::{tier}" in shadow_join_keys:
            overlap += 1
    return overlap


def _resolve_window(root: Path, start_date: str | None, end_date: str | None) -> tuple[str, str, list[str]]:
    if start_date and end_date:
        all_dates = [date_str for date_str in (
            start_date, end_date) if date_str]
        return start_date, end_date, sorted(set(all_dates))
    inferred_start, inferred_end, inferred_dates = infer_default_window(root)
    if not inferred_start or not inferred_end:
        raise FileNotFoundError(
            "No common policy/verdict/shadow window found under logs/judge_experts")
    return inferred_start, inferred_end, inferred_dates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate J6-S17-F.1 daily collection health artifact.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    start_date, end_date, inferred_dates = _resolve_window(
        root, args.start_date, args.end_date)
    template = read_json(TEMPLATE_PATH)
    health_spec = read_json(HEALTH_SPEC_PATH)
    collection_contract = read_json(COLLECTION_CONTRACT_PATH)

    policy_files = discover_window_files(
        root, "policy_cortex", start_date, end_date)
    verdict_files = discover_window_files(
        root, "verdict", start_date, end_date)
    shadow_files = discover_window_files(
        root, "shadow_entry_plan", start_date, end_date)

    policy_rows, policy_rows_by_date, policy_rows_by_symbol = _load_rows(
        policy_files, "policy_cortex")
    verdict_rows, _, _ = _load_rows(verdict_files, "verdict")
    shadow_rows, _, _ = _load_rows(shadow_files, "shadow_entry_plan")

    policy_cycle_counts = Counter(str(row.get("cycle_key"))
                                  for row in policy_rows if row.get("cycle_key"))
    verdict_cycle_counts = Counter(str(row.get("cycle_key"))
                                   for row in verdict_rows if row.get("cycle_key"))
    shadow_cycle_counts = Counter(str(row.get("cycle_key"))
                                  for row in shadow_rows if row.get("cycle_key"))
    shadow_plan_id_counts = Counter(str(row.get("plan_id"))
                                    for row in shadow_rows if row.get("plan_id"))

    policy_keys = set(policy_cycle_counts)
    verdict_keys = set(verdict_cycle_counts)
    shadow_keys = set(shadow_cycle_counts)

    shadow_tiers_by_cycle: dict[str, set[str]] = defaultdict(set)
    for row in shadow_rows:
        cycle_key = str(row.get("cycle_key") or "")
        tier = str(row.get("confidence_tier") or row.get("tier") or "")
        if cycle_key and tier:
            shadow_tiers_by_cycle[cycle_key].add(tier)

    matched_verdict_cycles = len(policy_keys & verdict_keys)
    matched_shadow_cycles = len(policy_keys & shadow_keys)
    three_tier_cycles = sum(1 for cycle_key in policy_keys if len(
        shadow_tiers_by_cycle.get(cycle_key, set())) == 3)

    schema_summary = validate_policy_rows(policy_rows, Path(
        collection_contract.get("policy_schema_path") or POLICY_SCHEMA_PATH))
    shadow_only_invariants = summarize_shadow_invariants(shadow_rows)

    outcome_rows = read_jsonl(
        DEFAULT_OUTCOME_RESULTS_PATH) if DEFAULT_OUTCOME_RESULTS_PATH.exists() else []
    artifact = json.loads(json.dumps(template))
    artifact["artifact_type"] = health_spec.get("artifact_type")
    artifact["spec_version"] = health_spec.get("spec_version")
    artifact["window"] = {
        "start_date": start_date,
        "end_date": end_date,
        "source": collection_contract.get("source_root", "logs/judge_experts"),
    }
    artifact["counts"] = {
        "policy_rows": len(policy_rows),
        "verdict_rows": len(verdict_rows),
        "shadow_plan_rows": len(shadow_rows),
        "unique_policy_cycle_keys": len(policy_cycle_counts),
        "duplicate_policy_cycle_keys": duplicate_key_count(policy_cycle_counts),
        "duplicate_plan_id_count": duplicate_key_count(shadow_plan_id_counts),
    }
    artifact["schema"] = {
        "policy_rows_valid": schema_summary["valid"],
        "policy_rows_invalid": schema_summary["invalid"],
        "schema_path": schema_summary["schema_path"],
    }
    artifact["joins"] = {
        "policy_to_verdict_join_rate": pct(matched_verdict_cycles, len(policy_keys)),
        "policy_to_shadow_join_rate": pct(matched_shadow_cycles, len(policy_keys)),
        "expected_three_tier_ladder_rate": pct(three_tier_cycles, len(policy_keys)),
        "missing_verdict_cycle_keys": sorted(policy_keys - verdict_keys),
        "missing_shadow_cycle_keys": sorted(policy_keys - shadow_keys),
    }
    artifact["shadow_only_invariants"] = shadow_only_invariants
    artifact["coverage"] = {
        "dates": inferred_dates,
        "symbols": sorted(policy_rows_by_symbol.keys()),
        "rows_by_date": dict(sorted(policy_rows_by_date.items())),
        "rows_by_symbol": dict(sorted(policy_rows_by_symbol.items())),
    }
    artifact["denominator_policy"] = collection_contract.get(
        "denominator_policy", {})
    artifact["outcome_layer"] = {
        "candidate_outcomes_found": DEFAULT_OUTCOME_RESULTS_PATH.exists(),
        "candidate_augmented_dataset_found": DEFAULT_AUGMENTED_DATASET_CSV.exists(),
        "outcome_join_key": collection_contract.get("canonical_outcome_join_key", "cycle_key+tier"),
        "candidate_overlap_with_existing_simulator_results": _shadow_join_overlap(shadow_rows, outcome_rows),
    }

    health_verdict, blockers = classify_health_verdict(
        has_policy_telemetry=bool(policy_files),
        has_verdict_telemetry=bool(verdict_files),
        has_shadow_telemetry=bool(shadow_files),
        policy_rows_invalid=int(schema_summary["invalid"]),
        policy_to_verdict_join_rate=float(
            artifact["joins"]["policy_to_verdict_join_rate"]),
        policy_to_shadow_join_rate=float(
            artifact["joins"]["policy_to_shadow_join_rate"]),
        expected_three_tier_ladder_rate=float(
            artifact["joins"]["expected_three_tier_ladder_rate"]),
        shadow_invariants_passed=bool(shadow_only_invariants["passed"]),
        duplicate_policy_cycle_keys=int(
            artifact["counts"]["duplicate_policy_cycle_keys"]),
        duplicate_plan_id_count=int(
            artifact["counts"]["duplicate_plan_id_count"]),
    )
    artifact["verdict"] = {
        "health_verdict": health_verdict,
        "blockers": blockers,
    }

    output_path = args.output or REPORTS_DIR / \
        f"j6_s17_f1_daily_health_{start_date}_{end_date}.json"
    write_json(output_path, artifact)
    print(output_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
