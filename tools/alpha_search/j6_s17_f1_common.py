from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "alpha_search"
LOGS_DIR = REPO_ROOT / "logs" / "judge_experts"
DEFAULT_OUTCOME_RESULTS_PATH = REPORTS_DIR / \
    "j6_s17_c1_shadow_simulation_results.jsonl"
DEFAULT_AUGMENTED_DATASET_CSV = REPORTS_DIR / \
    "j6_s17_c1_augmented_policy_outcome_dataset.csv"
DEFAULT_OUTCOME_JOIN_SUMMARY_PATH = REPORTS_DIR / \
    "j6_s17_c1_outcome_join_summary.json"
POLICY_SCHEMA_PATH = (
    REPO_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "alpha_search"
    / "judge"
    / "policy_cortex"
    / "schemas"
    / "policy_cortex_annotation_v1.json"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    ensure_ascii=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def bool_from_any(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def normalize_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None


def utc_date_from_ts_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 4)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def duplicate_key_count(counts: Mapping[str, int]) -> int:
    return sum(1 for count in counts.values() if count > 1)


def parse_symbol_and_date(path: Path, prefix: str) -> tuple[str | None, str | None]:
    stem = path.stem
    marker = f"{prefix}_"
    if not stem.startswith(marker):
        return None, None
    tail = stem[len(marker):]
    try:
        symbol, date_str = tail.rsplit("_", 1)
    except ValueError:
        return None, None
    return symbol or None, date_str or None


def discover_window_files(
    root: Path,
    prefix: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[Path]:
    files = sorted((root / "logs" / "judge_experts").glob(f"{prefix}_*.jsonl"))
    if start_date is None and end_date is None:
        return files

    selected: list[Path] = []
    for path in files:
        _, date_str = parse_symbol_and_date(path, prefix)
        if date_str is None:
            continue
        if start_date is not None and date_str < start_date:
            continue
        if end_date is not None and date_str > end_date:
            continue
        selected.append(path)
    return selected


def infer_default_window(root: Path) -> tuple[str | None, str | None, list[str]]:
    date_sets: list[set[str]] = []
    for prefix in ("policy_cortex", "verdict", "shadow_entry_plan"):
        prefix_dates = {
            date_str
            for _, date_str in (
                parse_symbol_and_date(path, prefix)
                for path in discover_window_files(root, prefix)
            )
            if date_str is not None
        }
        date_sets.append(prefix_dates)

    if not date_sets:
        return None, None, []

    common_dates = sorted(set.intersection(*date_sets)
                          ) if all(date_sets) else []
    if not common_dates:
        return None, None, []
    return common_dates[0], common_dates[-1], common_dates


def validate_policy_rows(
    rows: list[dict[str, Any]], schema_path: Path = POLICY_SCHEMA_PATH
) -> dict[str, Any]:
    schema = read_json(schema_path)
    valid_count = 0
    invalid_count = 0
    invalid_examples: list[str] = []

    validator = None
    try:
        from jsonschema import Draft7Validator  # type: ignore

        validator = Draft7Validator(schema)
    except Exception:
        validator = None

    required_keys = set(schema.get("required", []))
    allow_extra = bool(schema.get("additionalProperties", True))

    for row in rows:
        errors: list[str] = []
        if validator is not None:
            errors = [error.message for error in validator.iter_errors(row)]
        else:
            missing = sorted(required_keys - set(row.keys()))
            if missing:
                errors.append(f"missing_required:{','.join(missing)}")
            if not allow_extra:
                extras = sorted(set(row.keys()) -
                                set(schema.get("properties", {}).keys()))
                if extras:
                    errors.append(f"unexpected_keys:{','.join(extras)}")

        if errors:
            invalid_count += 1
            if len(invalid_examples) < 5:
                invalid_examples.append(errors[0])
        else:
            valid_count += 1

    return {
        "valid": valid_count,
        "invalid": invalid_count,
        "examples": invalid_examples,
        "schema_path": schema_path.as_posix(),
    }


def summarize_shadow_invariants(shadow_rows: list[dict[str, Any]]) -> dict[str, Any]:
    checked = [
        "authority_mode=shadow",
        "applied=false",
        "shadow_only=true",
        "cycle_key_present",
        "confidence_tier_present",
    ]
    violation_counts = Counter()
    for row in shadow_rows:
        if str(row.get("authority_mode") or "") != "shadow":
            violation_counts["authority_mode_not_shadow"] += 1
        if bool_from_any(row.get("applied")):
            violation_counts["applied_true"] += 1
        if not bool_from_any(row.get("shadow_only")):
            violation_counts["shadow_only_false"] += 1
        if not str(row.get("cycle_key") or ""):
            violation_counts["missing_cycle_key"] += 1
        if not str(row.get("confidence_tier") or row.get("tier") or ""):
            violation_counts["missing_confidence_tier"] += 1

    violations = [
        {"code": code, "count": count}
        for code, count in sorted(violation_counts.items())
        if count > 0
    ]
    return {
        "checked": checked,
        "passed": not violations,
        "violations": violations,
    }


def scan_join_policy_script(script_text: str) -> dict[str, Any]:
    normalized = script_text.lower()
    findings: list[str] = []
    if "index by plan_id (preferred)" in normalized or "plan_id (preferred)" in normalized:
        findings.append("legacy_outcome_index_prefers_plan_id")
    if "try to join outcome by plan_id" in normalized:
        findings.append("legacy_join_attempts_plan_id_before_canonical_key")
    if "keyed by cycle_key + plan_id or plan_id" in normalized:
        findings.append("legacy_join_declares_plan_id_as_primary_outcome_key")
    return {
        "canonical_outcome_join_key": "cycle_key+tier",
        "plan_id_alone_forbidden": True,
        "plan_id_preferred_join_detected": bool(findings),
        "blocking_join_findings": findings,
    }


def classify_health_verdict(
    *,
    has_policy_telemetry: bool,
    has_verdict_telemetry: bool,
    has_shadow_telemetry: bool,
    policy_rows_invalid: int,
    policy_to_verdict_join_rate: float,
    policy_to_shadow_join_rate: float,
    expected_three_tier_ladder_rate: float,
    shadow_invariants_passed: bool,
    duplicate_policy_cycle_keys: int,
    duplicate_plan_id_count: int,
) -> tuple[str, list[str]]:
    if not has_policy_telemetry:
        return "BLOCKED_BY_MISSING_POLICY_TELEMETRY", ["missing_policy_telemetry"]
    if not has_verdict_telemetry:
        return "BLOCKED_BY_MISSING_VERDICT_TELEMETRY", ["missing_verdict_telemetry"]
    if not has_shadow_telemetry:
        return "BLOCKED_BY_MISSING_SHADOW_PLAN_TELEMETRY", ["missing_shadow_plan_telemetry"]
    if policy_rows_invalid > 0:
        return "BLOCKED_BY_SCHEMA_FAILURE", [f"policy_rows_invalid={policy_rows_invalid}"]

    join_blockers: list[str] = []
    if policy_to_verdict_join_rate < 100.0:
        join_blockers.append("policy_to_verdict_join_rate_below_100")
    if policy_to_shadow_join_rate < 100.0:
        join_blockers.append("policy_to_shadow_join_rate_below_100")
    if expected_three_tier_ladder_rate < 100.0:
        join_blockers.append("three_tier_ladder_rate_below_100")
    if join_blockers:
        return "BLOCKED_BY_JOIN_FAILURE", join_blockers

    if not shadow_invariants_passed:
        return "BLOCKED_BY_SHADOW_INVARIANT_VIOLATION", ["shadow_only_invariants_failed"]

    residuals: list[str] = []
    if duplicate_policy_cycle_keys > 0:
        residuals.append("duplicate_policy_cycle_keys_detected")
    if duplicate_plan_id_count > 0:
        residuals.append("duplicate_plan_id_values_detected")
    return "COLLECTION_HEALTHY_WITH_RESIDUALS", residuals


def build_threshold_results(
    required_thresholds: Mapping[str, int], observed_metrics: Mapping[str, int]
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "required_min": int(required_min),
            "observed": int(observed_metrics.get(name, 0)),
            "passed": int(observed_metrics.get(name, 0)) >= int(required_min),
        }
        for name, required_min in required_thresholds.items()
    }


def evaluate_readiness(
    *,
    daily_health: Mapping[str, Any] | None,
    required_thresholds: Mapping[str, int],
    outcome_layer_metrics: Mapping[str, Any],
    freeze_marker_path: Path | None,
    manifest_path: Path | None,
    join_policy_audit: Mapping[str, Any],
    comparability: Mapping[str, Any],
    daily_health_path: Path | None = None,
) -> dict[str, Any]:
    if daily_health is None:
        return {
            "verdict": "BLOCKED_BY_MISSING_ARTIFACTS",
            "j6_s17_g_allowed": False,
            "blockers": ["missing_daily_health_artifact"],
            "next_action": "generate_daily_health_artifact_before_readiness_check",
            "health_inputs": {
                "daily_health_path": None,
                "health_verdict": None,
                "schema_validity_passed": False,
                "joins_passed": False,
                "shadow_only_invariants_passed": False,
            },
            "thresholds": build_threshold_results(required_thresholds, {}),
        }

    joins = dict(daily_health.get("joins") or {})
    schema = dict(daily_health.get("schema") or {})
    health_verdict = str(
        (daily_health.get("verdict") or {}).get("health_verdict") or "")
    shadow_only = dict(daily_health.get("shadow_only_invariants") or {})
    coverage = dict(daily_health.get("coverage") or {})
    counts = dict(daily_health.get("counts") or {})

    schema_validity_passed = int(schema.get("policy_rows_invalid", 0)) == 0
    joins_passed = (
        float(joins.get("policy_to_verdict_join_rate", 0.0)) >= 100.0
        and float(joins.get("policy_to_shadow_join_rate", 0.0)) >= 100.0
        and float(joins.get("expected_three_tier_ladder_rate", 0.0)) >= 100.0
    )
    shadow_only_invariants_passed = bool(shadow_only.get("passed"))

    observed_metrics = {
        "forward_days": len(list(coverage.get("dates") or [])),
        "policy_cycles": int(counts.get("unique_policy_cycle_keys", 0)),
        "non_low_outcome_rows": int(outcome_layer_metrics.get("non_low_outcome_rows", 0)),
        "track_only_outcome_rows": int(outcome_layer_metrics.get("track_only_outcome_rows", 0)),
        "dates_with_outcomes": int(outcome_layer_metrics.get("dates_with_outcomes", 0)),
        "symbols_with_outcomes": int(outcome_layer_metrics.get("symbols_with_outcomes", 0)),
        "tf_sec_values_with_outcomes": int(outcome_layer_metrics.get("tf_sec_values_with_outcomes", 0)),
    }
    thresholds = build_threshold_results(required_thresholds, observed_metrics)

    blockers: list[str] = []
    if not outcome_layer_metrics.get("candidate_outcomes_found", False):
        blockers.append("candidate_outcomes_missing")
    if not outcome_layer_metrics.get("candidate_augmented_dataset_found", False):
        blockers.append("candidate_augmented_dataset_missing")
    blockers.extend(list(comparability.get("blockers") or []))
    blockers.extend(list(join_policy_audit.get(
        "blocking_join_findings") or []))
    if freeze_marker_path is None or not freeze_marker_path.exists():
        blockers.append("freeze_marker_missing")
    if manifest_path is None or not manifest_path.exists():
        blockers.append("freeze_manifest_missing")

    comparability_flags = {
        key: value
        for key, value in comparability.items()
        if key != "blockers"
    }
    comparability_passed = all(bool(value)
                               for value in comparability_flags.values())

    all_thresholds_passed = all(item["passed"] for item in thresholds.values())
    freeze_marker_found = freeze_marker_path is not None and freeze_marker_path.exists()
    manifest_found = manifest_path is not None and manifest_path.exists()
    outcomes_present = bool(outcome_layer_metrics.get(
        "candidate_outcomes_found", False))
    plan_id_preferred = bool(join_policy_audit.get(
        "plan_id_preferred_join_detected", False))

    verdict = "WINDOW_NOT_READY"
    j6_s17_g_allowed = False
    if not daily_health_path:
        verdict = "BLOCKED_BY_MISSING_ARTIFACTS"
    elif health_verdict != "COLLECTION_HEALTHY_WITH_RESIDUALS" or not schema_validity_passed or not joins_passed or not shadow_only_invariants_passed:
        verdict = "BLOCKED_BY_DATA_QUALITY"
    elif outcomes_present and plan_id_preferred:
        verdict = "BLOCKED_BY_JOIN_INTEGRITY"
    elif outcomes_present and not comparability_passed:
        verdict = "BLOCKED_BY_COMPARABILITY_DRIFT"
    elif all_thresholds_passed and comparability_passed and not plan_id_preferred:
        if freeze_marker_found and manifest_found:
            verdict = "WINDOW_FROZEN_READY_FOR_J6_S17_G"
            j6_s17_g_allowed = True
        else:
            verdict = "WINDOW_READY_TO_FREEZE"

    next_action = "continue_forward_collection_and_rerun_f1_readiness"
    if verdict == "BLOCKED_BY_MISSING_ARTIFACTS":
        next_action = "generate_missing_f1_artifacts_before_readiness_check"
    elif verdict == "BLOCKED_BY_DATA_QUALITY":
        next_action = "repair_collection_health_before_freeze"
    elif verdict == "BLOCKED_BY_JOIN_INTEGRITY":
        next_action = "isolate_or_patch_legacy_plan_id_preferred_join_before_g_like_rerun"
    elif verdict == "BLOCKED_BY_COMPARABILITY_DRIFT":
        next_action = "resolve_contract_or_semantic_drift_before_freeze"
    elif verdict == "WINDOW_READY_TO_FREEZE":
        next_action = "write_freeze_marker_and_manifest_for_candidate_window"
    elif verdict == "WINDOW_FROZEN_READY_FOR_J6_S17_G":
        next_action = "j6_s17_g_may_run_against_the_frozen_window"

    return {
        "verdict": verdict,
        "j6_s17_g_allowed": j6_s17_g_allowed,
        "blockers": blockers,
        "next_action": next_action,
        "health_inputs": {
            "daily_health_path": daily_health_path.as_posix() if daily_health_path else None,
            "health_verdict": health_verdict,
            "schema_validity_passed": schema_validity_passed,
            "joins_passed": joins_passed,
            "shadow_only_invariants_passed": shadow_only_invariants_passed,
        },
        "thresholds": thresholds,
        "freeze_marker_found": freeze_marker_found,
        "manifest_found": manifest_found,
    }
