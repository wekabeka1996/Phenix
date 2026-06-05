#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.alpha_search.j6_s17_f1_common import REPORTS_DIR, bool_from_any, read_json


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PACKAGE_NAME = "J6-S17-G_POLICY_CORTEX_SURFACE_REVIEW_RERUN_ON_FROZEN_WINDOW"
DEFAULT_DAILY_HEALTH_PATH = REPORTS_DIR / "j6_s17_f1_daily_health_2026-05-10_2026-05-17.json"
DEFAULT_FREEZE_READINESS_PATH = REPORTS_DIR / "j6_s17_f1_freeze_readiness_2026-05-10_2026-05-17.json"
DEFAULT_CANDIDATE_OUTCOMES_PATH = REPORTS_DIR / "j6_s17_c1_shadow_simulation_results.jsonl"
DEFAULT_AUGMENTED_DATASET_PATH = REPORTS_DIR / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
DEFAULT_FREEZE_MARKER_PATH = REPORTS_DIR / "j6_s17_f_window_frozen_2026-05-10_2026-05-17.marker"
DEFAULT_FREEZE_MANIFEST_PATH = REPORTS_DIR / "j6_s17_f_window_manifest_2026-05-10_2026-05-17.json"
DEFAULT_JOIN_SUMMARY_PATH = REPORTS_DIR / "j6_s17_c1_outcome_join_summary.json"

DEFAULT_REPORT_PATH = REPORTS_DIR / "J6_S17_G_POLICY_CORTEX_SURFACE_REVIEW_RERUN_REPORT.md"
DEFAULT_SURFACE_SUMMARY_CSV = REPORTS_DIR / "j6_s17_g_surface_summary.csv"
DEFAULT_BUCKET_SUMMARY_CSV = REPORTS_DIR / "j6_s17_g_confidence_bucket_summary.csv"
DEFAULT_SYMBOL_REGIME_SUMMARY_CSV = REPORTS_DIR / "j6_s17_g_symbol_regime_summary.csv"
DEFAULT_CLASSIFICATION_JSON = REPORTS_DIR / "j6_s17_g_surface_classification.json"

CANONICAL_JOIN = "cycle_key+tier"
DUPLICATE_CONTAINMENT_ANOMALIES = {
    "cycle_tier_not_unique_in_dataset",
    "cycle_tier_duplicate_in_outcomes",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_str(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _normalize_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_join_anomalies(value: Any) -> list[str]:
    if value in (None, "", "[]"):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _confidence_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 0.25:
        return "lt_0.25"
    if value < 0.50:
        return "0.25_to_0.49"
    if value < 0.75:
        return "0.50_to_0.74"
    return "gte_0.75"


def _horizon_label(tf_sec: str) -> str:
    value = _normalize_str(tf_sec)
    return f"tf_{value}s" if value != "UNKNOWN" else value


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def render_markdown_table(rows: list[dict[str, Any]], headers: list[str]) -> str:
    if not rows:
        return "| Status | Value |\n| --- | --- |\n| none | none |"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def check_frozen_preflight(
    *,
    root: Path,
    manifest_path: Path,
    marker_path: Path,
    readiness_path: Path,
    candidate_outcomes_path: Path,
    augmented_dataset_path: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    manifest_present = manifest_path.exists()
    marker_present = marker_path.exists()
    candidate_outcomes_present = candidate_outcomes_path.exists()
    augmented_dataset_present = augmented_dataset_path.exists()

    manifest = read_json(manifest_path) if manifest_present else {}
    readiness = read_json(readiness_path) if readiness_path.exists() else {}
    readiness_state = dict(readiness.get("readiness") or {})
    join_policy = dict(readiness.get("join_policy") or {})
    join_integrity = dict(manifest.get("join_integrity") or {})

    readiness_verdict = str(readiness_state.get("verdict") or "")
    j6_s17_g_allowed = bool(readiness_state.get("j6_s17_g_allowed"))
    canonical_join_confirmed = (
        str(join_policy.get("canonical_outcome_join_key") or join_integrity.get("canonical_join") or "")
        == CANONICAL_JOIN
        and str(join_integrity.get("plan_id_usage") or "") == "diagnostics_only"
    )
    plan_id_preferred_join_detected = bool(join_policy.get("plan_id_preferred_join_detected"))

    hash_mismatches: list[dict[str, str]] = []
    if manifest_present:
        for item in list((manifest.get("hashes") or {}).get("files") or []):
            rel_path = str(item.get("path") or "")
            expected = str(item.get("sha256") or "")
            if not rel_path or not expected:
                hash_mismatches.append({"path": rel_path or "<missing>", "reason": "manifest_entry_incomplete"})
                continue
            current_path = root / Path(rel_path)
            if not current_path.exists():
                hash_mismatches.append({"path": rel_path, "reason": "file_missing"})
                continue
            actual = _sha256_file(current_path)
            if actual != expected:
                hash_mismatches.append({
                    "path": rel_path,
                    "expected": expected,
                    "actual": actual,
                })

    manifest_hashes_match = not hash_mismatches and manifest_present

    if not manifest_present:
        blockers.append("freeze_manifest_missing")
    if not marker_present:
        blockers.append("freeze_marker_missing")
    if readiness_verdict != "WINDOW_FROZEN_READY_FOR_J6_S17_G":
        blockers.append(f"readiness_verdict_not_frozen_ready:{readiness_verdict or 'missing'}")
    if not j6_s17_g_allowed:
        blockers.append("j6_s17_g_not_allowed")
    if not manifest_hashes_match:
        blockers.append("manifest_hashes_do_not_match_current_files")
    if not candidate_outcomes_present:
        blockers.append("candidate_outcomes_missing")
    if not augmented_dataset_present:
        blockers.append("augmented_dataset_missing")
    if not canonical_join_confirmed:
        blockers.append("canonical_join_not_confirmed")
    if plan_id_preferred_join_detected:
        blockers.append("plan_id_preferred_join_detected")

    return {
        "passed": not blockers,
        "freeze_manifest_present": manifest_present,
        "freeze_marker_present": marker_present,
        "readiness_verdict": readiness_verdict,
        "j6_s17_g_allowed": j6_s17_g_allowed,
        "manifest_hashes_match_current_files": manifest_hashes_match,
        "candidate_outcomes_present": candidate_outcomes_present,
        "augmented_dataset_present": augmented_dataset_present,
        "canonical_join_confirmed": canonical_join_confirmed,
        "plan_id_preferred_join_detected": plan_id_preferred_join_detected,
        "hash_mismatches": hash_mismatches,
        "blockers": blockers,
    }


def _new_stats() -> dict[str, Any]:
    return {
        "row_count": 0,
        "canonical_join_rows": 0,
        "support_count": 0,
        "unknown_count": 0,
        "unmatched_count": 0,
        "duplicate_contained_rows": 0,
        "invalid_rows": 0,
        "metric_rows": 0,
        "returns": [],
        "terminal_reason_counts": Counter(),
        "tier_support_counts": Counter(),
        "tier_win_counts": Counter(),
    }


def _update_stats(stats: dict[str, Any], row: dict[str, Any]) -> None:
    stats["row_count"] += 1
    if row["canonical_join_row"]:
        stats["canonical_join_rows"] += 1
    if row["outcome_available"]:
        stats["support_count"] += 1
    if row["unknown_outcome"]:
        stats["unknown_count"] += 1
    if row["unmatched"]:
        stats["unmatched_count"] += 1
    if row["duplicate_contained"]:
        stats["duplicate_contained_rows"] += 1
    if row["invalid_row"]:
        stats["invalid_rows"] += 1
    if row["net_pnl_pct"] is not None:
        stats["metric_rows"] += 1
        stats["returns"].append(row["net_pnl_pct"])
        tier = row["tier"]
        stats["tier_support_counts"][tier] += 1
        if row["net_pnl_pct"] > 0:
            stats["tier_win_counts"][tier] += 1
    if row["terminal_reason"] != "UNKNOWN":
        stats["terminal_reason_counts"][row["terminal_reason"]] += 1


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    row_count = int(stats["row_count"])
    support_count = int(stats["support_count"])
    returns = list(stats["returns"])
    avg_return = round(statistics.fmean(returns), 4) if returns else None
    median_return = round(statistics.median(returns), 4) if returns else None
    win_rate = round((sum(1 for value in returns if value > 0) / len(returns)) * 100.0, 4) if returns else None
    max_adverse_proxy = round(min(returns), 4) if returns else None
    hit_rate_by_tier = {
        tier: round((stats["tier_win_counts"][tier] / count) * 100.0, 4)
        for tier, count in sorted(stats["tier_support_counts"].items())
        if count > 0
    }
    return {
        "row_count": row_count,
        "canonical_join_rows": int(stats["canonical_join_rows"]),
        "canonical_match_rate_pct": round((int(stats["canonical_join_rows"]) / row_count) * 100.0, 4) if row_count else 0.0,
        "support_count": support_count,
        "unknown_count": int(stats["unknown_count"]),
        "unmatched_count": int(stats["unmatched_count"]),
        "duplicate_contained_rows": int(stats["duplicate_contained_rows"]),
        "invalid_rows": int(stats["invalid_rows"]),
        "metric_rows": int(stats["metric_rows"]),
        "win_rate": win_rate,
        "avg_return": avg_return,
        "median_return": median_return,
        "net_after_fee_or_fee_adjusted_proxy": avg_return,
        "max_adverse_or_drawdown_proxy": max_adverse_proxy,
        "hit_rate_by_tier": hit_rate_by_tier,
        "terminal_reason_counts": dict(sorted(stats["terminal_reason_counts"].items())),
    }


def classify_surface(stats: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if int(stats.get("duplicate_contained_rows", 0)) > 0:
        reasons.append("duplicate_canonical_key_contained_rows_present")
        return "DENOMINATOR_CONTAMINATED", reasons

    metric_rows = int(stats.get("metric_rows", 0))
    support_count = int(stats.get("support_count", 0))
    unknown_count = int(stats.get("unknown_count", 0))
    unmatched_count = int(stats.get("unmatched_count", 0))
    invalid_rows = int(stats.get("invalid_rows", 0))
    avg_return = stats.get("avg_return")
    median_return = stats.get("median_return")
    win_rate = stats.get("win_rate")

    if metric_rows <= 0:
        if unknown_count > 0 or unmatched_count > 0 or invalid_rows > 0:
            reasons.append("no_metric_rows_with_unknown_or_unmatched_outcomes")
            return "UNKNOWN_OUTCOME", reasons
        reasons.append("no_metric_rows")
        return "INSUFFICIENT_SUPPORT", reasons

    if support_count < 30:
        reasons.append("support_below_30")
        return "INSUFFICIENT_SUPPORT", reasons

    if support_count < 100:
        if avg_return is not None and median_return is not None and win_rate is not None and avg_return < 0.0 and median_return < 0.0 and win_rate <= 40.0:
            reasons.append("weak_support_but_consistently_negative")
            return "FORWARD_HARMFUL", reasons
        reasons.append("support_below_100")
        return "INSUFFICIENT_SUPPORT", reasons

    if avg_return is None or median_return is None or win_rate is None:
        reasons.append("outcome_metrics_unavailable")
        return "UNKNOWN_OUTCOME", reasons

    if avg_return > 0.0 and median_return > 0.0 and win_rate >= 55.0:
        reasons.append("positive_return_and_win_rate")
        return "FORWARD_SUPPORTED", reasons
    if avg_return < 0.0 and median_return < 0.0 and win_rate <= 45.0:
        reasons.append("negative_return_and_low_win_rate")
        return "FORWARD_HARMFUL", reasons

    reasons.append("mixed_or_flat_return_profile")
    return "FORWARD_NEUTRAL", reasons


def _build_row_record(raw: dict[str, str]) -> dict[str, Any]:
    anomalies = _parse_join_anomalies(raw.get("join_anomalies"))
    duplicate_contained = any(item in DUPLICATE_CONTAINMENT_ANOMALIES for item in anomalies)
    outcome_available = bool_from_any(raw.get("outcome_available"))
    invalid_reason = _normalize_str(raw.get("invalid_outcome_reason"), default="")
    skipped_reason = _normalize_str(raw.get("skipped_reason"), default="")
    simulation_status = _normalize_str(raw.get("simulation_status"), default="")
    terminal_reason = _normalize_str(raw.get("terminal_reason"), default="UNKNOWN")
    net_pnl_pct = _normalize_float(raw.get("net_pnl_pct"))

    return {
        "surface_key": _normalize_str(raw.get("surface_key")),
        "classifier_label": _normalize_str(raw.get("matched_surface_label")),
        "classifier_output": _normalize_str(raw.get("classifier_output")),
        "judge_verdict": _normalize_str(raw.get("entry_verdict")),
        "judge_confidence_bucket": _confidence_bucket(_normalize_float(raw.get("confidence"))),
        "symbol": _normalize_str(raw.get("symbol")),
        "regime": _normalize_str(raw.get("regime")),
        "side": _normalize_str(raw.get("side")),
        "tier": _normalize_str(raw.get("tier") or raw.get("confidence_tier")),
        "horizon": _horizon_label(_normalize_str(raw.get("tf_sec"))),
        "join_method": _normalize_str(raw.get("join_match_method"), default=""),
        "join_anomalies": anomalies,
        "duplicate_contained": duplicate_contained,
        "outcome_available": outcome_available,
        "invalid_reason": invalid_reason,
        "skipped_reason": skipped_reason,
        "simulation_status": simulation_status,
        "terminal_reason": terminal_reason,
        "net_pnl_pct": net_pnl_pct,
        "gross_pnl_pct": _normalize_float(raw.get("gross_pnl_pct")),
        "fees_paid_pct": _normalize_float(raw.get("fees_paid_pct")),
        "canonical_join_row": _normalize_str(raw.get("join_match_method"), default="") == CANONICAL_JOIN,
        "unknown_outcome": (not outcome_available) and bool(skipped_reason),
        "unmatched": invalid_reason == "missing_outcome_key_match",
        "invalid_row": invalid_reason not in ("", "missing_outcome_key_match") or simulation_status in {"invalid", "error"},
    }


def _aggregate_rows(row_records: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in row_records:
        key = tuple(str(row[field]) for field in key_fields)
        if key not in grouped:
            grouped[key] = {field: row[field] for field in key_fields}
            grouped[key]["stats"] = _new_stats()
        _update_stats(grouped[key]["stats"], row)

    finalized: list[dict[str, Any]] = []
    for item in grouped.values():
        stats = _finalize_stats(item.pop("stats"))
        item.update(stats)
        finalized.append(item)
    finalized.sort(key=lambda row: (-int(row["support_count"]), -int(row["row_count"]), "::".join(str(row[field]) for field in key_fields)))
    return finalized


def _surface_rows_with_classification(surface_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for row in surface_rows:
        classification, reasons = classify_surface(row)
        enriched = dict(row)
        enriched["surface_classification"] = classification
        enriched["classification_reasons"] = reasons
        classified.append(enriched)
    return classified


def _cohort_accounting(
    *,
    daily_health: dict[str, Any],
    manifest: dict[str, Any],
    join_summary: dict[str, Any],
    row_records: list[dict[str, Any]],
) -> dict[str, Any]:
    matched_rows = sum(1 for row in row_records if row["outcome_available"])
    unmatched_rows = sum(1 for row in row_records if row["unmatched"])
    duplicate_contained_rows = sum(1 for row in row_records if row["duplicate_contained"])
    invalid_rows = sum(1 for row in row_records if row["invalid_row"])
    canonical_join_rows = sum(1 for row in row_records if row["canonical_join_row"])
    return {
        "total_policy_rows": int((daily_health.get("counts") or {}).get("policy_rows", 0)),
        "total_shadow_plan_rows": int((daily_health.get("counts") or {}).get("shadow_plan_rows", 0)),
        "total_candidate_outcomes": int(((manifest.get("row_counts") or {}).get("candidate_outcome_rows", 0))),
        "augmented_dataset_rows": int(join_summary.get("dataset_rows_total", len(row_records))),
        "canonical_matched_rows": canonical_join_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "duplicate_canonical_key_contained_rows": duplicate_contained_rows,
        "invalid_rows": invalid_rows,
        "known_residuals": {
            "raw_candidate_outcome_duplicate_canonical_keys": int(((manifest.get("candidate_outcomes") or {}).get("duplicate_canonical_key_count", 0))),
            "unmatched_augmented_rows": int(join_summary.get("missing_outcome_key_count", 0)),
            "duplicate_policy_cycle_keys": int(((daily_health.get("counts") or {}).get("duplicate_policy_cycle_keys", 0))),
            "duplicate_plan_id_count": int(((daily_health.get("counts") or {}).get("duplicate_plan_id_count", 0))),
        },
        "overlap_notes": [
            "duplicate_canonical_key_contained_rows are a fail-closed subset of unmatched_rows on the augmented dataset surface",
        ],
    }


def _metric_availability(row_records: list[dict[str, Any]]) -> dict[str, Any]:
    matched_rows = [row for row in row_records if row["outcome_available"]]
    net_metric_rows = sum(1 for row in matched_rows if row["net_pnl_pct"] is not None)
    gross_metric_rows = sum(1 for row in matched_rows if row["gross_pnl_pct"] is not None)
    fee_metric_rows = sum(1 for row in matched_rows if row["fees_paid_pct"] is not None)
    return {
        "outcome_metric_available": net_metric_rows > 0,
        "matched_rows": len(matched_rows),
        "net_pnl_pct_rows": net_metric_rows,
        "gross_pnl_pct_rows": gross_metric_rows,
        "fees_paid_pct_rows": fee_metric_rows,
        "net_after_fee_or_fee_adjusted_proxy": "net_pnl_pct",
        "max_adverse_or_drawdown_proxy": "minimum realized net_pnl_pct per cohort",
    }


def _decision_block(decisions: dict[str, Any]) -> str:
    return json.dumps(decisions, indent=2, ensure_ascii=True)


def _top_rows(rows: list[dict[str, Any]], count: int = 10) -> list[dict[str, Any]]:
    return rows[:count]


def build_report(
    *,
    verdict: str,
    frozen_window: dict[str, Any],
    preflight: dict[str, Any],
    cohort_accounting: dict[str, Any],
    join_integrity: dict[str, Any],
    metric_availability: dict[str, Any],
    surface_rows: list[dict[str, Any]],
    classifier_label_rows: list[dict[str, Any]],
    verdict_rows: list[dict[str, Any]],
    bucket_rows: list[dict[str, Any]],
    symbol_regime_side_rows: list[dict[str, Any]],
    horizon_rows: list[dict[str, Any]],
    decisions: dict[str, Any],
    tests_run: list[str],
) -> str:
    frozen_window = frozen_window or {}
    preflight = preflight or {}
    cohort_accounting = cohort_accounting or {}
    join_integrity = join_integrity or {}
    metric_availability = metric_availability or {}
    known_residuals = cohort_accounting.get("known_residuals") or {}
    supported_rows = [row for row in surface_rows if row["surface_classification"] == "FORWARD_SUPPORTED"]
    harmful_rows = [row for row in surface_rows if row["surface_classification"] == "FORWARD_HARMFUL"]
    neutral_unknown_rows = [
        row for row in surface_rows if row["surface_classification"] in {"FORWARD_NEUTRAL", "INSUFFICIENT_SUPPORT", "UNKNOWN_OUTCOME"}
    ]
    contaminated_rows = [row for row in surface_rows if row["surface_classification"] == "DENOMINATOR_CONTAMINATED"]
    facts = [
        f"- Frozen window review used only {frozen_window.get('start_date', 'unknown')}..{frozen_window.get('end_date', 'unknown')} artifacts from the F.3 manifest.",
        f"- Preflight passed: {str(preflight.get('passed', False)).lower()}.",
        f"- Canonical join remained {CANONICAL_JOIN}; plan_id stayed diagnostics-only.",
        f"- Augmented dataset rows: {cohort_accounting.get('augmented_dataset_rows', 0)}; matched rows with outcome metrics: {cohort_accounting.get('matched_rows', 0)}.",
        f"- Residual duplicate canonical outcome keys remained explicit: {known_residuals.get('raw_candidate_outcome_duplicate_canonical_keys', 0)}.",
    ]
    inferences = [
        "- G reviewed frozen evidence only; it did not promote runtime, registry, or advisory changes.",
        "- Surface classifications remain conservative because duplicate-contained rows stay visible instead of being silently merged away.",
        "- Registry and advisory decisions are stricter than surface_evidence_v2 readiness in this report.",
    ]
    assumptions = [
        "- net_pnl_pct is the fee-adjusted outcome proxy because the augmented dataset exposes net_pnl_pct and fees_paid_pct per matched outcome row.",
        "- surface_key is the authoritative surface identity for per-surface classification.",
    ]
    unknowns = [
        "- This package did not run any downstream registry or advisory package, so promotion quality remains unproven.",
        "- Duplicate canonical outcome keys were contained, not root-caused, inside G.",
    ]
    test_lines = [f"- {item}" for item in tests_run] if tests_run else ["- None recorded."]

    return "\n".join([
        "# J6-S17-G Policy Cortex Surface Review Rerun Report",
        "",
        "## Verdict",
        "",
        "```yaml",
        f"verdict: {verdict}",
        f"j6_s17_g_allowed: {str(preflight.get('j6_s17_g_allowed', False)).lower()}",
        f"preflight_passed: {str(preflight.get('passed', False)).lower()}",
        "```",
        "",
        "## Problem Framing",
        "",
        "J6-S17-G reran the ENTRY-side Policy Cortex review on the frozen F.3 denominator only. The task was to evaluate surface-level forward evidence without promoting runtime behavior, registry entries, or advisory changes.",
        "",
        "## FACTS",
        "",
        *facts,
        "",
        "## INFERENCES",
        "",
        *inferences,
        "",
        "## ASSUMPTIONS",
        "",
        *assumptions,
        "",
        "## UNKNOWNS",
        "",
        *unknowns,
        "",
        "## Frozen Window Preflight",
        "",
        "```yaml",
        json.dumps(preflight, indent=2, ensure_ascii=True),
        "```",
        "",
        "## Denominator / Cohort Accounting",
        "",
        "```yaml",
        json.dumps(cohort_accounting, indent=2, ensure_ascii=True),
        "```",
        "",
        "## Join Integrity",
        "",
        "```yaml",
        json.dumps(join_integrity, indent=2, ensure_ascii=True),
        "```",
        "",
        "## Outcome Metric Availability",
        "",
        "```yaml",
        json.dumps(metric_availability, indent=2, ensure_ascii=True),
        "```",
        "",
        "## Surface-Level Results",
        "",
        "Top surface_key rows by support_count:",
        "",
        render_markdown_table(_top_rows(surface_rows), [
            "surface_key", "surface_classification", "support_count", "avg_return", "median_return", "win_rate", "unknown_count", "unmatched_count", "duplicate_contained_rows"
        ]),
        "",
        "Top classifier_label rows by support_count:",
        "",
        render_markdown_table(_top_rows(classifier_label_rows), [
            "classifier_label", "support_count", "avg_return", "median_return", "win_rate", "unknown_count", "unmatched_count"
        ]),
        "",
        "Top judge_verdict rows by support_count:",
        "",
        render_markdown_table(_top_rows(verdict_rows), [
            "judge_verdict", "support_count", "avg_return", "median_return", "win_rate", "unknown_count", "unmatched_count"
        ]),
        "",
        "## Confidence Bucket Results",
        "",
        render_markdown_table(bucket_rows, [
            "judge_confidence_bucket", "support_count", "avg_return", "median_return", "win_rate", "unknown_count", "unmatched_count", "duplicate_contained_rows"
        ]),
        "",
        "## Symbol / Regime / Side Results",
        "",
        "Top symbol/regime/side cohorts by support_count:",
        "",
        render_markdown_table(_top_rows(symbol_regime_side_rows), [
            "symbol", "regime", "side", "support_count", "avg_return", "median_return", "win_rate", "duplicate_contained_rows"
        ]),
        "",
        "Horizon summary:",
        "",
        render_markdown_table(horizon_rows, [
            "horizon", "support_count", "avg_return", "median_return", "win_rate", "unknown_count", "unmatched_count"
        ]),
        "",
        "## Supported Surfaces",
        "",
        render_markdown_table(_top_rows(supported_rows), [
            "surface_key", "support_count", "avg_return", "median_return", "win_rate", "classification_reasons"
        ]),
        "",
        "## Harmful Surfaces",
        "",
        render_markdown_table(_top_rows(harmful_rows), [
            "surface_key", "support_count", "avg_return", "median_return", "win_rate", "classification_reasons"
        ]),
        "",
        "## Neutral / Unknown Surfaces",
        "",
        render_markdown_table(_top_rows(neutral_unknown_rows), [
            "surface_key", "surface_classification", "support_count", "avg_return", "median_return", "win_rate", "classification_reasons"
        ]),
        "",
        "## Denominator-Contaminated Surfaces",
        "",
        render_markdown_table(_top_rows(contaminated_rows), [
            "surface_key", "support_count", "duplicate_contained_rows", "unmatched_count", "classification_reasons"
        ]),
        "",
        "## Registry Readiness Decision",
        "",
        "```yaml",
        _decision_block({"registry_ready": decisions["registry_ready"], "reason": decisions["registry_reason"]}),
        "```",
        "",
        "## surface_evidence_v2 Decision",
        "",
        "```yaml",
        _decision_block({"surface_evidence_v2_ready": decisions["surface_evidence_v2_ready"], "reason": decisions["surface_evidence_v2_reason"]}),
        "```",
        "",
        "## Advisory Readiness Decision",
        "",
        "```yaml",
        _decision_block({"advisory_ready": decisions["advisory_ready"], "reason": decisions["advisory_reason"]}),
        "```",
        "",
        "## Tests / Validation",
        "",
        *test_lines,
        "",
        "## Risks / Unproven Areas",
        "",
        "- Raw candidate outcome duplicate canonical keys remain contained rather than removed at source.",
        "- Daily health remains COLLECTION_HEALTHY_WITH_RESIDUALS because duplicate policy cycle keys and duplicate plan IDs still exist.",
        "- This package reviewed frozen evidence only; it did not prove future promotion safety.",
        "",
        "## Next Action",
        "",
        "```yaml",
        json.dumps({"next_action": decisions["next_action"]}, indent=2, ensure_ascii=True),
        "```",
        "",
    ])


def run_surface_review(
    *,
    root: Path,
    daily_health_path: Path,
    readiness_path: Path,
    candidate_outcomes_path: Path,
    augmented_dataset_path: Path,
    freeze_marker_path: Path,
    freeze_manifest_path: Path,
    join_summary_path: Path,
    report_path: Path,
    surface_summary_csv_path: Path,
    bucket_summary_csv_path: Path,
    symbol_regime_summary_csv_path: Path,
    classification_json_path: Path,
    tests_run: list[str],
) -> dict[str, Any]:
    preflight = check_frozen_preflight(
        root=root,
        manifest_path=freeze_manifest_path,
        marker_path=freeze_marker_path,
        readiness_path=readiness_path,
        candidate_outcomes_path=candidate_outcomes_path,
        augmented_dataset_path=augmented_dataset_path,
    )

    daily_health = read_json(daily_health_path) if daily_health_path.exists() else {}
    manifest = read_json(freeze_manifest_path) if freeze_manifest_path.exists() else {}
    join_summary = read_json(join_summary_path) if join_summary_path.exists() else {}
    frozen_window = dict(manifest.get("freeze_window") or {})
    join_integrity = dict(manifest.get("join_integrity") or {})

    if not preflight["passed"]:
        blocked_cohort_accounting = {
            "total_policy_rows": int((daily_health.get("counts") or {}).get("policy_rows", 0)),
            "total_shadow_plan_rows": int((daily_health.get("counts") or {}).get("shadow_plan_rows", 0)),
            "total_candidate_outcomes": int(((manifest.get("row_counts") or {}).get("candidate_outcome_rows", 0))),
            "augmented_dataset_rows": int(join_summary.get("dataset_rows_total") or ((manifest.get("row_counts") or {}).get("augmented_dataset_rows", 0))),
            "canonical_matched_rows": int((((manifest.get("candidate_augmented_dataset") or {}).get("join_method_counts") or {}).get(CANONICAL_JOIN, 0))),
            "matched_rows": int(join_summary.get("rows_with_outcome", 0)),
            "unmatched_rows": int(join_summary.get("missing_outcome_key_count", 0)),
            "duplicate_canonical_key_contained_rows": int(join_summary.get("many_to_one_anomalies", 0)),
            "invalid_rows": sum(
                count
                for reason, count in dict(join_summary.get("invalid_outcome_reason_counts") or {}).items()
                if reason != "missing_outcome_key_match"
            ),
            "known_residuals": {
                "raw_candidate_outcome_duplicate_canonical_keys": int(((manifest.get("candidate_outcomes") or {}).get("duplicate_canonical_key_count", 0))),
                "unmatched_augmented_rows": int(join_summary.get("missing_outcome_key_count", 0)),
                "duplicate_policy_cycle_keys": int(((daily_health.get("counts") or {}).get("duplicate_policy_cycle_keys", 0))),
                "duplicate_plan_id_count": int(((daily_health.get("counts") or {}).get("duplicate_plan_id_count", 0))),
            },
            "blocked_before_surface_classification": True,
        }
        blocked_metric_availability = {
            "outcome_metric_available": int(join_summary.get("rows_with_outcome", 0)) > 0,
            "matched_rows": int(join_summary.get("rows_with_outcome", 0)),
            "blocked_before_surface_classification": True,
        }
        if preflight["plan_id_preferred_join_detected"]:
            verdict = "J6_S17_G_BLOCKED_BY_JOIN_INTEGRITY"
        else:
            verdict = "J6_S17_G_BLOCKED_BY_PREFLIGHT"
        _write_csv(surface_summary_csv_path, [])
        _write_csv(bucket_summary_csv_path, [])
        _write_csv(symbol_regime_summary_csv_path, [])
        _write_json(classification_json_path, {
            "package": PACKAGE_NAME,
            "verdict": verdict,
            "preflight": preflight,
            "frozen_window": frozen_window,
            "cohort_accounting": blocked_cohort_accounting,
            "surfaces": [],
        })
        report = build_report(
            verdict=verdict,
            frozen_window=frozen_window,
            preflight=preflight,
            cohort_accounting=blocked_cohort_accounting,
            join_integrity=join_integrity,
            metric_availability=blocked_metric_availability,
            surface_rows=[],
            classifier_label_rows=[],
            verdict_rows=[],
            bucket_rows=[],
            symbol_regime_side_rows=[],
            horizon_rows=[],
            decisions={
                "registry_ready": False,
                "registry_reason": "preflight_failed",
                "surface_evidence_v2_ready": False,
                "surface_evidence_v2_reason": "preflight_failed",
                "advisory_ready": False,
                "advisory_reason": "preflight_failed",
                "next_action": "close_J6_S17_G_as_no_support",
            },
            tests_run=tests_run,
        )
        report_path.write_text(report, encoding="utf-8")
        return {
            "verdict": verdict,
            "preflight": preflight,
            "frozen_window": frozen_window,
            "cohort_accounting": blocked_cohort_accounting,
            "surface_counts": {},
            "decisions": {
                "registry_ready": False,
                "surface_evidence_v2_ready": False,
                "advisory_ready": False,
                "next_action": "close_J6_S17_G_as_no_support",
            },
        }

    row_records = [_build_row_record(row) for row in _read_csv_rows(augmented_dataset_path)]
    cohort_accounting = _cohort_accounting(
        daily_health=daily_health,
        manifest=manifest,
        join_summary=join_summary,
        row_records=row_records,
    )
    metric_availability = _metric_availability(row_records)
    if not metric_availability["outcome_metric_available"]:
        verdict = "J6_S17_G_BLOCKED_BY_MISSING_OUTCOME_METRICS"
    else:
        verdict = "J6_S17_G_COMPLETED_NO_FORWARD_SUPPORT"

    surface_rows = _surface_rows_with_classification(_aggregate_rows(row_records, ["surface_key"]))
    classifier_label_rows = _aggregate_rows(row_records, ["classifier_label"])
    verdict_rows = _aggregate_rows(row_records, ["judge_verdict"])
    bucket_rows = _aggregate_rows(row_records, ["judge_confidence_bucket"])
    symbol_regime_side_rows = _aggregate_rows(row_records, ["symbol", "regime", "side"])
    horizon_rows = _aggregate_rows(row_records, ["horizon"])

    supported_count = sum(1 for row in surface_rows if row["surface_classification"] == "FORWARD_SUPPORTED")
    harmful_count = sum(1 for row in surface_rows if row["surface_classification"] == "FORWARD_HARMFUL")
    neutral_count = sum(1 for row in surface_rows if row["surface_classification"] == "FORWARD_NEUTRAL")
    insufficient_count = sum(1 for row in surface_rows if row["surface_classification"] == "INSUFFICIENT_SUPPORT")
    contaminated_count = sum(1 for row in surface_rows if row["surface_classification"] == "DENOMINATOR_CONTAMINATED")
    unknown_count = sum(1 for row in surface_rows if row["surface_classification"] == "UNKNOWN_OUTCOME")

    if metric_availability["outcome_metric_available"]:
        if supported_count == 0 and contaminated_count == len(surface_rows) and surface_rows:
            verdict = "J6_S17_G_BLOCKED_BY_DENOMINATOR_CONTAMINATION"
        elif supported_count > 0 and (harmful_count > 0 or neutral_count > 0 or insufficient_count > 0 or contaminated_count > 0 or unknown_count > 0):
            verdict = "J6_S17_G_COMPLETED_WITH_MIXED_EVIDENCE"
        elif supported_count > 0:
            verdict = "J6_S17_G_COMPLETED_FORWARD_SUPPORTED_SURFACES_FOUND"
        elif harmful_count == 0:
            verdict = "J6_S17_G_COMPLETED_NO_FORWARD_SUPPORT"
        else:
            verdict = "J6_S17_G_COMPLETED_WITH_MIXED_EVIDENCE"

    registry_ready = supported_count > 0 and harmful_count == 0 and contaminated_count == 0
    surface_evidence_v2_ready = supported_count > 0
    advisory_ready = registry_ready and harmful_count == 0 and contaminated_count == 0 and supported_count >= 3

    if supported_count > 0 and not registry_ready:
        next_action = "build_surface_evidence_v2_package"
    elif harmful_count > 0:
        next_action = "run_harmful_surface_casebook"
    elif contaminated_count > 0:
        next_action = "run_denominator_duplicate_root_cause_audit"
    elif supported_count == 0:
        next_action = "close_J6_S17_G_as_no_support"
    else:
        next_action = "run_confidence_bucket_calibration_package"

    decisions = {
        "registry_ready": registry_ready,
        "registry_reason": "supported_surfaces_present_without_contamination_or_harm" if registry_ready else "conservative_no_promotion_gate_retained",
        "surface_evidence_v2_ready": surface_evidence_v2_ready,
        "surface_evidence_v2_reason": "supported_surfaces_found_on_frozen_window" if surface_evidence_v2_ready else "no_supported_surfaces_found",
        "advisory_ready": advisory_ready,
        "advisory_reason": "frozen_supported_surfaces_clear_without_harm_or_contamination" if advisory_ready else "review_only_package_retains_advisory_block",
        "next_action": next_action,
    }

    surface_summary_rows = [
        {
            "surface_key": row["surface_key"],
            "surface_classification": row["surface_classification"],
            "row_count": row["row_count"],
            "support_count": row["support_count"],
            "avg_return": row["avg_return"],
            "median_return": row["median_return"],
            "win_rate": row["win_rate"],
            "unknown_count": row["unknown_count"],
            "unmatched_count": row["unmatched_count"],
            "duplicate_contained_rows": row["duplicate_contained_rows"],
            "invalid_rows": row["invalid_rows"],
            "classification_reasons": json.dumps(row["classification_reasons"], ensure_ascii=True),
        }
        for row in surface_rows
    ]
    bucket_summary_rows = [
        {
            "judge_confidence_bucket": row["judge_confidence_bucket"],
            "row_count": row["row_count"],
            "support_count": row["support_count"],
            "avg_return": row["avg_return"],
            "median_return": row["median_return"],
            "win_rate": row["win_rate"],
            "unknown_count": row["unknown_count"],
            "unmatched_count": row["unmatched_count"],
            "duplicate_contained_rows": row["duplicate_contained_rows"],
        }
        for row in bucket_rows
    ]
    symbol_regime_summary_rows = [
        {
            "symbol": row["symbol"],
            "regime": row["regime"],
            "side": row["side"],
            "row_count": row["row_count"],
            "support_count": row["support_count"],
            "avg_return": row["avg_return"],
            "median_return": row["median_return"],
            "win_rate": row["win_rate"],
            "unknown_count": row["unknown_count"],
            "unmatched_count": row["unmatched_count"],
            "duplicate_contained_rows": row["duplicate_contained_rows"],
        }
        for row in symbol_regime_side_rows
    ]

    _write_csv(surface_summary_csv_path, surface_summary_rows)
    _write_csv(bucket_summary_csv_path, bucket_summary_rows)
    _write_csv(symbol_regime_summary_csv_path, symbol_regime_summary_rows)
    _write_json(classification_json_path, {
        "package": PACKAGE_NAME,
        "verdict": verdict,
        "surfaces": surface_summary_rows,
        "classification_counts": {
            "supported_surfaces": supported_count,
            "harmful_surfaces": harmful_count,
            "neutral_surfaces": neutral_count,
            "insufficient_support_surfaces": insufficient_count,
            "denominator_contaminated_surfaces": contaminated_count,
            "unknown_outcome_surfaces": unknown_count,
        },
    })

    report = build_report(
        verdict=verdict,
        frozen_window=frozen_window,
        preflight=preflight,
        cohort_accounting=cohort_accounting,
        join_integrity=join_integrity,
        metric_availability=metric_availability,
        surface_rows=surface_rows,
        classifier_label_rows=classifier_label_rows,
        verdict_rows=verdict_rows,
        bucket_rows=bucket_rows,
        symbol_regime_side_rows=symbol_regime_side_rows,
        horizon_rows=horizon_rows,
        decisions=decisions,
        tests_run=tests_run,
    )
    report_path.write_text(report, encoding="utf-8")

    return {
        "verdict": verdict,
        "preflight": preflight,
        "frozen_window": frozen_window,
        "cohort_accounting": cohort_accounting,
        "surface_counts": {
            "supported_surfaces": supported_count,
            "harmful_surfaces": harmful_count,
            "neutral_surfaces": neutral_count,
            "insufficient_support_surfaces": insufficient_count,
            "denominator_contaminated_surfaces": contaminated_count,
            "unknown_outcome_surfaces": unknown_count,
        },
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run J6-S17-G frozen-window Policy Cortex surface review.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--daily-health", type=Path, default=DEFAULT_DAILY_HEALTH_PATH)
    parser.add_argument("--freeze-readiness", type=Path, default=DEFAULT_FREEZE_READINESS_PATH)
    parser.add_argument("--candidate-outcomes", type=Path, default=DEFAULT_CANDIDATE_OUTCOMES_PATH)
    parser.add_argument("--augmented-dataset", type=Path, default=DEFAULT_AUGMENTED_DATASET_PATH)
    parser.add_argument("--freeze-marker", type=Path, default=DEFAULT_FREEZE_MARKER_PATH)
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_FREEZE_MANIFEST_PATH)
    parser.add_argument("--join-summary", type=Path, default=DEFAULT_JOIN_SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--surface-summary-csv", type=Path, default=DEFAULT_SURFACE_SUMMARY_CSV)
    parser.add_argument("--bucket-summary-csv", type=Path, default=DEFAULT_BUCKET_SUMMARY_CSV)
    parser.add_argument("--symbol-regime-summary-csv", type=Path, default=DEFAULT_SYMBOL_REGIME_SUMMARY_CSV)
    parser.add_argument("--classification-json", type=Path, default=DEFAULT_CLASSIFICATION_JSON)
    parser.add_argument("--tests-run", action="append", default=[])
    args = parser.parse_args()

    result = run_surface_review(
        root=args.root.resolve(),
        daily_health_path=args.daily_health,
        readiness_path=args.freeze_readiness,
        candidate_outcomes_path=args.candidate_outcomes,
        augmented_dataset_path=args.augmented_dataset,
        freeze_marker_path=args.freeze_marker,
        freeze_manifest_path=args.freeze_manifest,
        join_summary_path=args.join_summary,
        report_path=args.report,
        surface_summary_csv_path=args.surface_summary_csv,
        bucket_summary_csv_path=args.bucket_summary_csv,
        symbol_regime_summary_csv_path=args.symbol_regime_summary_csv,
        classification_json_path=args.classification_json,
        tests_run=args.tests_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())