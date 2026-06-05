#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.alpha_search.j6_s17_c1_shadow_outcomes import (  # noqa: E402
    REPORTS_DIR,
    load_jsonl,
    read_csv_rows,
    write_csv,
    write_json,
)


C1_DATASET_CSV = REPORTS_DIR / "j6_s17_c1_augmented_policy_outcome_dataset.csv"
C1_DATASET_JSONL = REPORTS_DIR / "j6_s17_c1_augmented_policy_outcome_dataset.jsonl"
C1_JOIN_SUMMARY = REPORTS_DIR / "j6_s17_c1_outcome_join_summary.json"
C1_CLASSIFIER_SUMMARY = REPORTS_DIR / \
    "j6_s17_c1_outcome_availability_by_classifier.json"
C1_LABEL_SUMMARY = REPORTS_DIR / "j6_s17_c1_outcome_availability_by_label.json"
C1_DIMENSION_SUMMARY = REPORTS_DIR / \
    "j6_s17_c1_outcome_availability_by_dimension.json"
C1_REPORT = REPORTS_DIR / "J6_S17_C1_SHADOW_SIMULATOR_OUTCOME_COLLECTION_REPORT.md"
SURFACE_REGISTRY_PATH = REPO_ROOT / "apps" / "reference" / "domains" / \
    "alpha_search" / "judge" / "policy_cortex" / "surface_evidence_v1.json"

ANALYSIS_THRESHOLDS = {
    "min_outcome_rows_for_label_judgment": 100,
    "min_filled_rows_for_pnl_judgment": 50,
    "min_symbols_for_robust_label": 3,
    "min_dates_for_robust_label": 2,
    "dominant_symbol_share_threshold": 0.60,
    "dominant_tf_share_threshold": 0.70,
    "dominant_date_share_threshold": 0.70,
}

REQUIRED_DATASET_COLUMNS = {
    "cycle_key",
    "plan_id",
    "symbol",
    "side",
    "tf_sec",
    "regime",
    "surface_key",
    "matched_surface_label",
    "classifier_output",
    "tier",
    "actionable",
    "outcome_available",
    "simulation_status",
    "limit_filled",
    "terminal_reason",
    "gross_pnl_pct",
    "net_pnl_pct",
    "fees_paid_pct",
    "tp_hit",
    "sl_hit",
    "timeout_hit",
    "invalid_outcome_reason",
    "skipped_reason",
    "join_match_method",
    "suppressed",
    "plan_ts_ms",
}

HIT_MISS_DEFINITIONS = {
    "HIT_TP": "tp_hit == true",
    "MISS_SL": "sl_hit == true",
    "NEUTRAL_TIMEOUT": "limit_filled == true and timeout_hit == true",
    "NO_FILL": "limit_filled == false and terminal_reason == NOT_FILLED_TIMEOUT",
    "INVALID": "invalid_outcome_reason is non-null or simulation_status in {error, invalid}",
    "SKIPPED": "skipped_reason is non-null or simulation_status == skipped",
}


def bool_from_any(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def normalize_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_div(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def percentiles(values: Sequence[float], points: Sequence[int] = (10, 25, 75, 90)) -> dict[str, float | None]:
    if not values:
        return {f"p{point}": None for point in points}
    sorted_values = sorted(values)
    output: dict[str, float | None] = {}
    last_index = len(sorted_values) - 1
    for point in points:
        if last_index == 0:
            output[f"p{point}"] = sorted_values[0]
            continue
        position = (point / 100.0) * last_index
        lower_index = int(position)
        upper_index = min(lower_index + 1, last_index)
        weight = position - lower_index
        lower = sorted_values[lower_index]
        upper = sorted_values[upper_index]
        output[f"p{point}"] = lower + (upper - lower) * weight
    return output


def dominant_share(values: Iterable[str]) -> float:
    counter = Counter(value for value in values if value)
    total = sum(counter.values())
    if total == 0:
        return 0.0
    return max(counter.values()) / total


def unique_nonempty(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def load_surface_registry(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {str(record.get("surface_key")): record for record in payload.get("surfaces", [])}


def normalize_dataset_row(row: dict[str, str]) -> dict[str, Any]:
    plan_ts_ms = normalize_int(row.get("plan_ts_ms"))
    plan_ts_utc = str(row.get("plan_ts_utc") or "")
    derived_date = plan_ts_utc[:10] if plan_ts_utc else None
    if derived_date is None and plan_ts_ms is not None:
        derived_date = str(plan_ts_ms)
    actionable = bool_from_any(row.get("actionable"))
    suppressed = bool_from_any(row.get("suppressed"))
    outcome_available = bool_from_any(row.get("outcome_available"))
    limit_filled = bool_from_any(row.get("limit_filled"))
    skipped_reason = str(row.get("skipped_reason") or "").strip() or None
    invalid_outcome_reason = str(
        row.get("invalid_outcome_reason") or "").strip() or None
    simulation_status = str(row.get("simulation_status") or "").strip() or None
    terminal_reason = str(row.get("terminal_reason")
                          or row.get("outcome") or "").strip() or None
    normalized = {
        "cycle_key": str(row.get("cycle_key") or "").strip(),
        "plan_id": str(row.get("plan_id") or "").strip(),
        "symbol": str(row.get("symbol") or "").strip(),
        "side": str(row.get("side") or "UNKNOWN").strip() or "UNKNOWN",
        "tf_sec": normalize_int(row.get("tf_sec")),
        "regime": str(row.get("regime") or "UNKNOWN").strip() or "UNKNOWN",
        "surface_key": str(row.get("surface_key") or "").strip(),
        "matched_surface_label": str(row.get("matched_surface_label") or "UNKNOWN").strip() or "UNKNOWN",
        "classifier_output": str(row.get("classifier_output") or "UNKNOWN").strip() or "UNKNOWN",
        "tier": str(row.get("tier") or "UNKNOWN").strip() or "UNKNOWN",
        "actionable": actionable,
        "suppressed": suppressed,
        "outcome_available": outcome_available,
        "simulation_status": simulation_status,
        "limit_filled": limit_filled,
        "terminal_reason": terminal_reason,
        "gross_pnl_pct": normalize_float(row.get("gross_pnl_pct")),
        "net_pnl_pct": normalize_float(row.get("net_pnl_pct")),
        "fees_paid_pct": normalize_float(row.get("fees_paid_pct")),
        "gross_pnl_bps": normalize_float(row.get("gross_pnl_bps")),
        "net_pnl_bps": normalize_float(row.get("net_pnl_bps")),
        "total_cost_bps": normalize_float(row.get("total_cost_bps")),
        "tp_hit": bool_from_any(row.get("tp_hit")),
        "sl_hit": bool_from_any(row.get("sl_hit")),
        "timeout_hit": bool_from_any(row.get("timeout_hit")),
        "invalid_outcome_reason": invalid_outcome_reason,
        "skipped_reason": skipped_reason,
        "join_match_method": str(row.get("join_match_method") or "").strip() or None,
        "join_anomalies": str(row.get("join_anomalies") or "[]"),
        "plan_ts_ms": plan_ts_ms,
        "date": derived_date or "UNKNOWN",
        "row": row,
    }
    normalized["cohort_actionable"] = actionable and not suppressed
    normalized["cohort_outcome_available"] = outcome_available
    normalized["cohort_filled"] = outcome_available and limit_filled
    normalized["cohort_non_filled_timeout"] = outcome_available and (
        not limit_filled) and terminal_reason == "NOT_FILLED_TIMEOUT"
    normalized["cohort_skipped"] = skipped_reason is not None or simulation_status == "skipped"
    normalized["cohort_invalid"] = invalid_outcome_reason is not None or simulation_status in {
        "error", "invalid"}
    return normalized


def classify_hit_miss_bucket(row: dict[str, Any]) -> str:
    if row["cohort_skipped"]:
        return "SKIPPED"
    if row["cohort_invalid"]:
        return "INVALID"
    if row["cohort_non_filled_timeout"]:
        return "NO_FILL"
    if row["cohort_filled"] and row["tp_hit"]:
        return "HIT_TP"
    if row["cohort_filled"] and row["sl_hit"]:
        return "MISS_SL"
    if row["cohort_filled"] and row["timeout_hit"]:
        return "NEUTRAL_TIMEOUT"
    if row["cohort_outcome_available"]:
        return "OTHER_OUTCOME"
    return "NO_OUTCOME"


def metrics_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = len(rows)
    actionable_rows = [row for row in rows if row["cohort_actionable"]]
    outcome_rows = [row for row in rows if row["cohort_outcome_available"]]
    filled_rows = [row for row in rows if row["cohort_filled"]]
    non_filled_timeout_rows = [
        row for row in rows if row["cohort_non_filled_timeout"]]
    skipped_rows = [row for row in rows if row["cohort_skipped"]]
    invalid_rows = [row for row in rows if row["cohort_invalid"]]
    tp_rows = [row for row in filled_rows if row["tp_hit"]]
    sl_rows = [row for row in filled_rows if row["sl_hit"]]
    filled_timeout_rows = [row for row in filled_rows if row["timeout_hit"]
                           and row["terminal_reason"] == "FILLED_TIMEOUT"]
    net_values = [row["net_pnl_pct"]
                  for row in filled_rows if row["net_pnl_pct"] is not None]
    gross_values = [row["gross_pnl_pct"]
                    for row in filled_rows if row["gross_pnl_pct"] is not None]
    net_bps_values = [row["net_pnl_bps"]
                      for row in filled_rows if row["net_pnl_bps"] is not None]
    fee_values = [row["fees_paid_pct"]
                  for row in filled_rows if row["fees_paid_pct"] is not None]
    total_cost_bps_values = [row["total_cost_bps"]
                             for row in filled_rows if row["total_cost_bps"] is not None]
    hit_miss = Counter(classify_hit_miss_bucket(row) for row in rows)
    win_count = sum(1 for value in net_values if value > 0)
    loss_count = sum(1 for value in net_values if value < 0)
    flat_count = sum(1 for value in net_values if value == 0)
    unique_symbols_outcome = unique_nonempty(
        row["symbol"] for row in outcome_rows)
    unique_dates_outcome = unique_nonempty(row["date"] for row in outcome_rows)
    symbol_share = dominant_share(row["symbol"] for row in outcome_rows)
    tf_share = dominant_share(
        str(row["tf_sec"]) for row in outcome_rows if row["tf_sec"] is not None)
    date_share = dominant_share(row["date"] for row in outcome_rows)
    sample_sufficient = len(outcome_rows) >= ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"] and len(
        filled_rows) >= ANALYSIS_THRESHOLDS["min_filled_rows_for_pnl_judgment"]
    concentration_flag = (
        symbol_share >= ANALYSIS_THRESHOLDS["dominant_symbol_share_threshold"]
        or tf_share >= ANALYSIS_THRESHOLDS["dominant_tf_share_threshold"]
        or date_share >= ANALYSIS_THRESHOLDS["dominant_date_share_threshold"]
        or len(unique_symbols_outcome) < ANALYSIS_THRESHOLDS["min_symbols_for_robust_label"]
        or len(unique_dates_outcome) < ANALYSIS_THRESHOLDS["min_dates_for_robust_label"]
    )
    net_percentiles = percentiles(net_values)
    metrics = {
        "row_count": total_rows,
        "unique_cycles": len({row["cycle_key"] for row in rows if row["cycle_key"]}),
        "actionable_rows": len(actionable_rows),
        "outcome_available_rows": len(outcome_rows),
        "filled_rows": len(filled_rows),
        "non_filled_timeout_rows": len(non_filled_timeout_rows),
        "skipped_rows": len(skipped_rows),
        "invalid_rows": len(invalid_rows),
        "tp_count": len(tp_rows),
        "sl_count": len(sl_rows),
        "filled_timeout_count": len(filled_timeout_rows),
        "limit_fill_rate": safe_div(len(filled_rows), len(actionable_rows)),
        "not_filled_timeout_rate": safe_div(len(non_filled_timeout_rows), len(actionable_rows)),
        "filled_timeout_rate": safe_div(len(filled_timeout_rows), len(actionable_rows)),
        "tp_rate_among_filled": safe_div(len(tp_rows), len(filled_rows)),
        "sl_rate_among_filled": safe_div(len(sl_rows), len(filled_rows)),
        "timeout_rate_among_filled": safe_div(len(filled_timeout_rows), len(filled_rows)),
        "invalid_rate": safe_div(len(invalid_rows), total_rows),
        "avg_gross_pnl": statistics.fmean(gross_values) if gross_values else None,
        "median_gross_pnl": statistics.median(gross_values) if gross_values else None,
        "avg_net_pnl": statistics.fmean(net_values) if net_values else None,
        "median_net_pnl": statistics.median(net_values) if net_values else None,
        "avg_net_pnl_bps": statistics.fmean(net_bps_values) if net_bps_values else None,
        "median_net_pnl_bps": statistics.median(net_bps_values) if net_bps_values else None,
        "win_rate_net_positive": safe_div(win_count, len(net_values)),
        "loss_rate_net_negative": safe_div(loss_count, len(net_values)),
        "breakeven_rate": safe_div(flat_count, len(net_values)),
        "p10_net_pnl": net_percentiles["p10"],
        "p25_net_pnl": net_percentiles["p25"],
        "p75_net_pnl": net_percentiles["p75"],
        "p90_net_pnl": net_percentiles["p90"],
        "total_net_pnl": sum(net_values) if net_values else None,
        "total_gross_pnl": sum(gross_values) if gross_values else None,
        "avg_fee_slippage_cost": statistics.fmean(fee_values) if fee_values else None,
        "avg_total_cost_bps": statistics.fmean(total_cost_bps_values) if total_cost_bps_values else None,
        "count_with_null_economics": len(filled_rows) - len(net_values),
        "hit_miss_counts": dict(sorted(hit_miss.items())),
        "sample_sufficiency_flag": sample_sufficient,
        "concentration_flag": concentration_flag,
        "dominant_symbol_share": symbol_share,
        "dominant_tf_share": tf_share,
        "dominant_date_share": date_share,
        "unique_symbols_outcome": len(unique_symbols_outcome),
        "unique_dates_outcome": len(unique_dates_outcome),
    }
    return metrics


def flatten_for_csv(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                item[key] = json.dumps(
                    value, ensure_ascii=True, sort_keys=True)
            else:
                item[key] = value
        flattened.append(item)
    return flattened


def write_union_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_dataset_contract_revalidation(root: Path, dataset_csv: Path, dataset_jsonl: Path) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    required_inputs = {
        str(C1_DATASET_CSV.relative_to(root)): C1_DATASET_CSV.exists(),
        str(C1_DATASET_JSONL.relative_to(root)): C1_DATASET_JSONL.exists(),
        str(C1_JOIN_SUMMARY.relative_to(root)): C1_JOIN_SUMMARY.exists(),
        str(C1_CLASSIFIER_SUMMARY.relative_to(root)): C1_CLASSIFIER_SUMMARY.exists(),
        str(C1_LABEL_SUMMARY.relative_to(root)): C1_LABEL_SUMMARY.exists(),
        str(C1_DIMENSION_SUMMARY.relative_to(root)): C1_DIMENSION_SUMMARY.exists(),
        str(C1_REPORT.relative_to(root)): C1_REPORT.exists(),
    }
    missing = [path for path, exists in required_inputs.items() if not exists]
    if missing:
        return {
            "status": "BLOCKED_AUGMENTED_DATASET_MISSING",
            "missing_inputs": missing,
            "required_inputs": required_inputs,
        }, None

    raw_rows = read_csv_rows(dataset_csv)
    jsonl_rows = load_jsonl(dataset_jsonl)
    header = list(raw_rows[0].keys()) if raw_rows else []
    missing_columns = sorted(REQUIRED_DATASET_COLUMNS - set(header))
    normalized_rows = [normalize_dataset_row(row) for row in raw_rows]

    cycle_tier_counter = Counter(
        f"{row['cycle_key']}::{row['tier']}" for row in normalized_rows if row["cycle_key"] and row["tier"])
    plan_id_counter = Counter(row["plan_id"]
                              for row in normalized_rows if row["plan_id"])
    join_key_counter = Counter(row["surface_key"]
                               for row in normalized_rows if row["surface_key"])

    structural_valid = len(raw_rows) == len(jsonl_rows) and not missing_columns
    status = "OK" if structural_valid else "BLOCKED_DATASET_CONTRACT_INVALID"
    payload = {
        "status": status,
        "required_inputs": required_inputs,
        "dataset_rows_total": len(raw_rows),
        "jsonl_rows_total": len(jsonl_rows),
        "unique_cycle_keys": len({row["cycle_key"] for row in normalized_rows if row["cycle_key"]}),
        "rows_with_outcome": sum(1 for row in normalized_rows if row["cohort_outcome_available"]),
        "rows_without_outcome": sum(1 for row in normalized_rows if not row["cohort_outcome_available"]),
        "outcome_join_rate_pct": round((sum(1 for row in normalized_rows if row["cohort_outcome_available"]) / len(normalized_rows)) * 100.0, 4) if normalized_rows else 0.0,
        "outcome_available_distribution": dict(sorted(Counter(str(row["outcome_available"]) for row in normalized_rows).items())),
        "classifier_output_values": dict(sorted(Counter(row["classifier_output"] for row in normalized_rows).items())),
        "matched_surface_label_values": dict(sorted(Counter(row["matched_surface_label"] for row in normalized_rows).items())),
        "tier_values": dict(sorted(Counter(row["tier"] for row in normalized_rows).items())),
        "join_match_method_values": dict(sorted(Counter(str(row["join_match_method"] or "") for row in normalized_rows).items())),
        "skipped_reason_values": dict(sorted(Counter(str(row["skipped_reason"] or "") for row in normalized_rows).items())),
        "invalid_outcome_reason_values": dict(sorted(Counter(str(row["invalid_outcome_reason"] or "") for row in normalized_rows).items())),
        "duplicate_key_conditions": {
            "duplicate_cycle_tier_key_count": sum(1 for count in cycle_tier_counter.values() if count > 1),
            "duplicate_plan_id_key_count": sum(1 for count in plan_id_counter.values() if count > 1),
            "duplicate_surface_key_count": sum(1 for count in join_key_counter.values() if count > 1),
            "blank_join_method_rows": sum(1 for row in normalized_rows if row["join_match_method"] is None),
            "blank_surface_key_rows": sum(1 for row in normalized_rows if not row["surface_key"]),
        },
        "null_handling": {
            "rows_with_null_net_pnl": sum(1 for row in normalized_rows if row["net_pnl_pct"] is None),
            "filled_rows_with_null_net_pnl": sum(1 for row in normalized_rows if row["cohort_filled"] and row["net_pnl_pct"] is None),
            "outcome_rows_with_null_net_pnl": sum(1 for row in normalized_rows if row["cohort_outcome_available"] and row["net_pnl_pct"] is None),
        },
        "expected_baseline_comparison": {
            "dataset_rows_total_matches": len(raw_rows) == 46443,
            "rows_with_outcome_matches": sum(1 for row in normalized_rows if row["cohort_outcome_available"]) == 14003,
            "outcome_join_rate_pct_matches": round((sum(1 for row in normalized_rows if row["cohort_outcome_available"]) / len(normalized_rows)) * 100.0, 4) == 30.1509 if normalized_rows else False,
            "track_only_rows_matches": sum(1 for row in normalized_rows if row["classifier_output"] == "TRACK_ONLY") == 2757,
            "track_only_rows_with_outcome_matches": sum(1 for row in normalized_rows if row["classifier_output"] == "TRACK_ONLY" and row["cohort_outcome_available"]) == 1016,
            "unknown_rows_matches": sum(1 for row in normalized_rows if row["classifier_output"] == "UNKNOWN") == 43686,
            "unknown_rows_with_outcome_matches": sum(1 for row in normalized_rows if row["classifier_output"] == "UNKNOWN" and row["cohort_outcome_available"]) == 12987,
        },
        "missing_columns": missing_columns,
    }
    return payload, normalized_rows


def build_cohort_definitions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "all_rows": len(rows),
        "actionable_rows": sum(1 for row in rows if row["cohort_actionable"]),
        "outcome_available_rows": sum(1 for row in rows if row["cohort_outcome_available"]),
        "filled_rows": sum(1 for row in rows if row["cohort_filled"]),
        "non_filled_timeout_rows": sum(1 for row in rows if row["cohort_non_filled_timeout"]),
        "skipped_rows": sum(1 for row in rows if row["cohort_skipped"]),
        "invalid_outcome_rows": sum(1 for row in rows if row["cohort_invalid"]),
    }
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "cohorts": {
            "A_all_rows": {
                "definition": "All rows in the C1 augmented dataset. Coverage/readiness only.",
                "count": counts["all_rows"],
            },
            "B_actionable_rows": {
                "definition": "Rows where actionable == true and suppressed != true.",
                "count": counts["actionable_rows"],
            },
            "C_outcome_available_rows": {
                "definition": "Rows where outcome_available == true.",
                "count": counts["outcome_available_rows"],
            },
            "D_filled_rows": {
                "definition": "Rows where outcome_available == true and limit_filled == true.",
                "count": counts["filled_rows"],
            },
            "E_non_filled_timeout_rows": {
                "definition": "Rows where outcome_available == true, limit_filled == false, and terminal_reason == NOT_FILLED_TIMEOUT.",
                "count": counts["non_filled_timeout_rows"],
            },
            "F_skipped_rows": {
                "definition": "Rows with skipped_reason present or simulation_status == skipped. Excluded from trade-performance denominators.",
                "count": counts["skipped_rows"],
            },
            "G_invalid_outcome_rows": {
                "definition": "Rows with invalid_outcome_reason present or simulation_status in {error, invalid}. Data-quality only.",
                "count": counts["invalid_outcome_rows"],
            },
        },
    }


def build_group_summary(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)
    summaries: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items(), key=lambda item: tuple(str(part) for part in item[0])):
        summary = {field: value for field, value in zip(group_fields, key)}
        summary.update(metrics_for_rows(group_rows))
        summaries.append(summary)
    return summaries


def compare_against_unknown(metrics: dict[str, Any], unknown_baseline: dict[str, Any]) -> dict[str, Any]:
    avg_net = metrics.get("avg_net_pnl")
    unknown_avg_net = unknown_baseline.get("avg_net_pnl")
    tp_rate = metrics.get("tp_rate_among_filled")
    unknown_tp_rate = unknown_baseline.get("tp_rate_among_filled")
    sl_rate = metrics.get("sl_rate_among_filled")
    unknown_sl_rate = unknown_baseline.get("sl_rate_among_filled")
    positive_vs_unknown = bool(
        avg_net is not None
        and unknown_avg_net is not None
        and avg_net > unknown_avg_net
        and (tp_rate is None or unknown_tp_rate is None or tp_rate >= unknown_tp_rate)
        and (sl_rate is None or unknown_sl_rate is None or sl_rate <= unknown_sl_rate)
    )
    negative_vs_unknown = bool(
        avg_net is not None
        and unknown_avg_net is not None
        and avg_net < unknown_avg_net
        and (sl_rate is None or unknown_sl_rate is None or sl_rate >= unknown_sl_rate)
    )
    return {
        "positive_vs_unknown": positive_vs_unknown,
        "negative_vs_unknown": negative_vs_unknown,
        "avg_net_pnl_delta_vs_unknown": (avg_net - unknown_avg_net) if avg_net is not None and unknown_avg_net is not None else None,
        "tp_rate_delta_vs_unknown": (tp_rate - unknown_tp_rate) if tp_rate is not None and unknown_tp_rate is not None else None,
        "sl_rate_delta_vs_unknown": (sl_rate - unknown_sl_rate) if sl_rate is not None and unknown_sl_rate is not None else None,
    }


def classify_label_survival(metrics: dict[str, Any], unknown_baseline: dict[str, Any], *, label: str) -> str:
    if metrics["invalid_rows"] > 0 and metrics["outcome_available_rows"] == 0:
        return "DATA_QUALITY_BLOCKED"
    if metrics["outcome_available_rows"] < ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"] or metrics["filled_rows"] < ANALYSIS_THRESHOLDS["min_filled_rows_for_pnl_judgment"]:
        return "INSUFFICIENT_OUTCOME_SAMPLE"
    comparison = compare_against_unknown(metrics, unknown_baseline)
    if label == "UNKNOWN":
        return "MIXED_OR_CONCENTRATED"
    if comparison["negative_vs_unknown"]:
        return "FORWARD_CONTRADICTED"
    if comparison["positive_vs_unknown"] and not metrics["concentration_flag"]:
        return "FORWARD_SUPPORTED"
    return "MIXED_OR_CONCENTRATED"


def tier_coverage_status(metrics: dict[str, Any]) -> str:
    if metrics["actionable_rows"] == 0 and metrics["outcome_available_rows"] == 0:
        return "NON_ACTIONABLE_BY_DESIGN"
    if metrics["outcome_available_rows"] == 0:
        return "NO_OUTCOME_COVERAGE"
    return "OUTCOME_COVERAGE_PRESENT"


def classify_unknown_candidate(metrics: dict[str, Any], unknown_baseline: dict[str, Any]) -> str:
    if metrics["invalid_rows"] > 0 and metrics["outcome_available_rows"] == 0:
        return "DATA_QUALITY_BLOCKED"
    if metrics["outcome_available_rows"] < ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"] or metrics["filled_rows"] < ANALYSIS_THRESHOLDS["min_filled_rows_for_pnl_judgment"]:
        return "NEEDS_MORE_SAMPLE"
    comparison = compare_against_unknown(metrics, unknown_baseline)
    hit_miss = metrics["hit_miss_counts"]
    no_fill_count = int(hit_miss.get("NO_FILL", 0))
    if comparison["negative_vs_unknown"] or int(hit_miss.get("MISS_SL", 0)) > int(hit_miss.get("HIT_TP", 0)):
        return "DO_NOT_ADD"
    if no_fill_count > int(hit_miss.get("HIT_TP", 0)) and not comparison["positive_vs_unknown"]:
        return "NEEDS_MORE_SAMPLE"
    if comparison["positive_vs_unknown"] and not metrics["concentration_flag"]:
        return "CANDIDATE_FOR_REGISTRY_REVIEW"
    if comparison["positive_vs_unknown"]:
        return "WATCHLIST_ONLY"
    return "DO_NOT_ADD"


def evidence_quality(metrics: dict[str, Any]) -> str:
    if metrics["invalid_rows"] > 0 and metrics["outcome_available_rows"] == 0:
        return "DATA_QUALITY_BLOCKED"
    if not metrics["sample_sufficiency_flag"]:
        return "LOW"
    if metrics["concentration_flag"]:
        return "MEDIUM"
    return "HIGH"


def classify_registry_action(metrics: dict[str, Any], current_registry_status: str, unknown_baseline: dict[str, Any]) -> str:
    survival = classify_label_survival(
        metrics, unknown_baseline, label=current_registry_status)
    quality = evidence_quality(metrics)
    if current_registry_status != "UNKNOWN":
        if metrics["outcome_available_rows"] < ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"]:
            return "REQUIRES_MORE_FORWARD_DATA"
        if survival == "FORWARD_CONTRADICTED":
            return "DOWNGRADE_LABEL_IN_REVIEW"
        if survival == "FORWARD_SUPPORTED":
            return "KEEP_CURRENT_LABEL"
        return "NO_REGISTRY_UPDATE"
    if quality == "DATA_QUALITY_BLOCKED":
        return "NO_REGISTRY_UPDATE"
    candidate = classify_unknown_candidate(metrics, unknown_baseline)
    if candidate == "CANDIDATE_FOR_REGISTRY_REVIEW":
        return "CANDIDATE_FOR_SURFACE_EVIDENCE_V2_REVIEW"
    if candidate == "WATCHLIST_ONLY":
        return "PROMOTE_TO_WATCHLIST"
    if candidate == "DO_NOT_ADD":
        return "REJECT_EXPANSION"
    if candidate == "NEEDS_MORE_SAMPLE":
        return "REQUIRES_MORE_FORWARD_DATA"
    return "NO_REGISTRY_UPDATE"


def build_classifier_hit_miss_summary(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary_rows = build_group_summary(rows, ("classifier_output",))
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "hit_miss_definitions": HIT_MISS_DEFINITIONS,
        "rows": summary_rows,
    }, flatten_for_csv(summary_rows)


def build_surface_label_survival(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary_rows = build_group_summary(rows, ("matched_surface_label",))
    summary_by_label = {row["matched_surface_label"]                        : row for row in summary_rows}
    unknown_baseline = summary_by_label.get("UNKNOWN", metrics_for_rows([]))
    for row in summary_rows:
        row.update(compare_against_unknown(row, unknown_baseline))
        row["label_survival_status"] = classify_label_survival(
            row, unknown_baseline, label=row["matched_surface_label"])
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "rows": summary_rows,
    }, flatten_for_csv(summary_rows)


def build_tier_analysis(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary_rows = build_group_summary(rows, ("tier",))
    for row in summary_rows:
        row["tier_coverage_status"] = tier_coverage_status(row)
        row["classifier_output_distribution"] = dict(sorted(Counter(
            item["classifier_output"] for item in rows if item["tier"] == row["tier"]).items()))
        row["matched_label_distribution"] = dict(sorted(Counter(
            item["matched_surface_label"] for item in rows if item["tier"] == row["tier"]).items()))
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "rows": summary_rows,
    }, flatten_for_csv(summary_rows)


def build_dimension_analysis(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    definitions = {
        "regime": ("regime",),
        "symbol": ("symbol",),
        "side": ("side",),
        "tf_sec": ("tf_sec",),
        "date": ("date",),
        "tier": ("tier",),
        "classifier_output_x_tier": ("classifier_output", "tier"),
        "classifier_output_x_regime": ("classifier_output", "regime"),
        "classifier_output_x_symbol": ("classifier_output", "symbol"),
        "matched_label_x_regime": ("matched_surface_label", "regime"),
        "matched_label_x_symbol": ("matched_surface_label", "symbol"),
    }
    payload_rows: list[dict[str, Any]] = []
    payload_json: dict[str, Any] = {
        "analysis_thresholds": ANALYSIS_THRESHOLDS, "dimensions": {}}
    for name, fields in definitions.items():
        summary_rows = build_group_summary(rows, fields)
        for row in summary_rows:
            row["dimension_name"] = name
            row["sample_sufficiency_flag"] = row["sample_sufficiency_flag"]
            row["concentration_flag"] = row["concentration_flag"]
        payload_json["dimensions"][name] = summary_rows
        payload_rows.extend(summary_rows)
    return payload_json, flatten_for_csv(payload_rows)


def build_unknown_opportunity_diagnosis(rows: list[dict[str, Any]], registry_index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    unknown_rows = [
        row for row in rows if row["classifier_output"] == "UNKNOWN"]
    unknown_baseline = metrics_for_rows([row for row in unknown_rows if row["cohort_outcome_available"]
                                        or row["cohort_actionable"] or row["cohort_skipped"] or row["cohort_invalid"]])
    grouped = build_group_summary(
        unknown_rows, ("surface_key", "regime", "side", "symbol", "tf_sec", "tier"))
    for row in grouped:
        row["current_registry_status"] = str(registry_index.get(
            row["surface_key"], {}).get("label", "UNKNOWN"))
        row.update(compare_against_unknown(row, unknown_baseline))
        row["recommendation"] = classify_unknown_candidate(
            row, unknown_baseline)
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "rows": grouped,
    }, flatten_for_csv(grouped)


def build_registry_expansion_readiness(rows: list[dict[str, Any]], registry_index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    unknown_baseline = metrics_for_rows(
        [row for row in rows if row["classifier_output"] == "UNKNOWN"])
    grouped = build_group_summary(rows, ("surface_key",))
    for row in grouped:
        surface_key = row["surface_key"]
        registry_record = registry_index.get(surface_key, {})
        row["current_registry_status"] = str(
            registry_record.get("label", "UNKNOWN"))
        row["current_registry_sample_size"] = registry_record.get(
            "sample_size")
        row["dominant_classifier_output"] = Counter(
            item["classifier_output"] for item in rows if item["surface_key"] == surface_key).most_common(1)[0][0]
        row["dominant_matched_label"] = Counter(
            item["matched_surface_label"] for item in rows if item["surface_key"] == surface_key).most_common(1)[0][0]
        row["forward_outcome_support"] = classify_label_survival(
            row, unknown_baseline, label=row["current_registry_status"])
        row["evidence_quality"] = evidence_quality(row)
        row["recommended_action"] = classify_registry_action(
            row, row["current_registry_status"], unknown_baseline)
    return {
        "analysis_thresholds": ANALYSIS_THRESHOLDS,
        "rows": grouped,
    }, flatten_for_csv(grouped)


def report_verdict(classifier_summary: dict[str, Any], label_survival: dict[str, Any], registry_readiness: dict[str, Any]) -> str:
    classifier_rows = {row["classifier_output"]                       : row for row in classifier_summary["rows"]}
    track_only = classifier_rows.get("TRACK_ONLY")
    unknown = classifier_rows.get("UNKNOWN")
    if track_only is None or unknown is None:
        return "BLOCKED_METRIC_DENOMINATOR_AMBIGUITY"
    if unknown["outcome_available_rows"] < ANALYSIS_THRESHOLDS["min_outcome_rows_for_label_judgment"]:
        return "BLOCKED_TOO_FEW_OUTCOME_ROWS"
    label_rows = {row["matched_surface_label"]                  : row for row in label_survival["rows"]}
    promising = label_rows.get("PROMISING_BUT_CONCENTRATED")
    if promising is None:
        return "CLASSIFIER_ANALYSIS_COMPLETED_INSUFFICIENT_EVIDENCE"
    readiness_rows = registry_readiness["rows"]
    has_candidate = any(row["recommended_action"] ==
                        "CANDIDATE_FOR_SURFACE_EVIDENCE_V2_REVIEW" for row in readiness_rows)
    if promising["label_survival_status"] == "FORWARD_SUPPORTED" and has_candidate:
        return "CLASSIFIER_ANALYSIS_COMPLETED_FORWARD_SUPPORTED"
    if promising["label_survival_status"] == "FORWARD_CONTRADICTED" and track_only.get("avg_net_pnl") is not None and unknown.get("avg_net_pnl") is not None and track_only["avg_net_pnl"] < unknown["avg_net_pnl"]:
        return "CLASSIFIER_ANALYSIS_COMPLETED_FORWARD_CONTRADICTED"
    if promising["label_survival_status"] == "INSUFFICIENT_OUTCOME_SAMPLE":
        return "CLASSIFIER_ANALYSIS_COMPLETED_INSUFFICIENT_EVIDENCE"
    if has_candidate:
        return "PARTIAL_ANALYSIS_NOT_READY_FOR_REGISTRY_REVIEW"
    return "CLASSIFIER_ANALYSIS_COMPLETED_MIXED_OR_CONCENTRATED"


def build_markdown_report(
    *,
    verdict: str,
    revalidation: dict[str, Any],
    cohort_definitions: dict[str, Any],
    classifier_summary: dict[str, Any],
    label_survival: dict[str, Any],
    tier_analysis: dict[str, Any],
    dimension_analysis: dict[str, Any],
    unknown_diagnosis: dict[str, Any],
    registry_readiness: dict[str, Any],
    files_changed: list[str],
    tests_run: list[str],
) -> str:
    classifier_rows = {row["classifier_output"]                       : row for row in classifier_summary["rows"]}
    track_only = classifier_rows.get("TRACK_ONLY", {})
    unknown = classifier_rows.get("UNKNOWN", {})
    promising = next(
        (row for row in label_survival["rows"] if row["matched_surface_label"] == "PROMISING_BUT_CONCENTRATED"), None)
    candidate_count = sum(
        1 for row in registry_readiness["rows"] if row["recommended_action"] == "CANDIDATE_FOR_SURFACE_EVIDENCE_V2_REVIEW")
    watchlist_count = sum(
        1 for row in registry_readiness["rows"] if row["recommended_action"] == "PROMOTE_TO_WATCHLIST")
    lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        "J6-S17-C2 revalidated the C1 augmented dataset, separated trade-performance cohorts from skipped and invalid rows, and measured classifier hit/miss and surface survival without changing runtime behavior or the surface registry.",
        "",
        "## Final Verdict",
        verdict,
        "",
        "## Scope",
        "- Read-only analysis of the C1 augmented policy outcome dataset.",
        "- Explicit cohort handling for actionable, outcome-available, filled, non-filled timeout, skipped, and invalid rows.",
        "- Classifier hit/miss, surface label survival, tier splits, dimension splits, UNKNOWN opportunity diagnosis, and registry expansion readiness reporting.",
        "",
        "## Proven Facts",
        f"- Revalidated dataset rows: {revalidation['dataset_rows_total']}.",
        f"- Revalidated rows with outcome: {revalidation['rows_with_outcome']}.",
        f"- Revalidated rows without outcome: {revalidation['rows_without_outcome']}.",
        f"- TRACK_ONLY rows / rows_with_outcome: {track_only.get('row_count')} / {track_only.get('outcome_available_rows')}.",
        f"- UNKNOWN rows / rows_with_outcome: {unknown.get('row_count')} / {unknown.get('outcome_available_rows')}.",
        f"- Filled rows available for PnL analysis: {cohort_definitions['cohorts']['D_filled_rows']['count']}.",
        f"- Candidate registry-review surfaces found: {candidate_count}.",
        f"- Watchlist-only surfaces found: {watchlist_count}.",
        "",
        "## Inferences",
        "- C2 trade-quality conclusions are valid only on outcome_available and filled denominators, not on all rows.",
        "- Skipped rows remain a coverage/readiness signal and are not evidence of trade failure.",
        "- Registry expansion should remain conservative when positive signals are concentrated or sample-limited.",
        "",
        "## Assumptions",
        "- cycle_key+tier remains the canonical identity when plan_id is not unique, as established by C1.",
        "- Analysis thresholds are package-local constants for transparency, not runtime business logic.",
        "",
        "## Unknowns",
        "- Whether more forward windows will materially change the UNKNOWN baseline or reduce concentration in promising cohorts.",
        "- Whether future outcome coverage improvements will convert currently skipped cohorts into actionable evidence.",
        "",
        "## Dataset Contract Revalidation",
        json.dumps(revalidation, indent=2, ensure_ascii=True),
        "",
        "## Cohort Definitions",
        json.dumps(cohort_definitions, indent=2, ensure_ascii=True),
        "",
        "## Classifier Hit/Miss Summary",
        json.dumps(classifier_summary, indent=2, ensure_ascii=True),
        "",
        "## Matched Surface Label Survival",
        json.dumps(label_survival, indent=2, ensure_ascii=True),
        "",
        "## Tier-Specific Analysis",
        json.dumps(tier_analysis, indent=2, ensure_ascii=True),
        "",
        "## Dimension Analysis",
        json.dumps(dimension_analysis, indent=2, ensure_ascii=True),
        "",
        "## UNKNOWN Opportunity Diagnosis",
        json.dumps(unknown_diagnosis, indent=2, ensure_ascii=True),
        "",
        "## Surface Registry Expansion Readiness",
        json.dumps(registry_readiness, indent=2, ensure_ascii=True),
        "",
        "## Files Changed",
        *[f"- {item}" for item in files_changed],
        "",
        "## Runtime Behavior Changed",
        "- No.",
        "",
        "## Authority Changed",
        "- No.",
        "",
        "## Order Behavior Changed",
        "- No.",
        "",
        "## Tests Run",
        *([f"- {item}" for item in tests_run]
          if tests_run else ["- None recorded."]),
        "",
        "## Residual Risks",
        "- The all_rows denominator is dominated by skipped rows, so any naive conversion to trade performance would be invalid.",
        "- Positive forward signals can still be concentration-driven by symbol, timeframe, or date.",
        "- Only 14,003 of 46,443 rows have simulator outcomes, so registry conclusions remain partial.",
        "",
        "## What Remains Unproven",
        "- Production alpha, advisory readiness, or promotion readiness.",
        "- Whether any suggested watchlist or review candidate survives additional forward data collection.",
        "",
        "## Recommendation for J6-S17-D",
        f"- PROMISING_BUT_CONCENTRATED current status: {promising['label_survival_status'] if promising else 'UNRESOLVED'}.",
        f"- Registry-ready candidates in this pass: {candidate_count}; watchlist-only candidates: {watchlist_count}.",
        "- Keep surface_evidence_v1.json unchanged in this package and move to decision review only on the evidence artifacts generated here.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run J6-S17-C2 classifier hit/miss and surface survival analysis.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dataset-csv", type=Path, default=C1_DATASET_CSV)
    parser.add_argument("--dataset-jsonl", type=Path, default=C1_DATASET_JSONL)
    parser.add_argument("--output-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--tests-run", action="append", default=[])
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    revalidation, rows = build_dataset_contract_revalidation(
        args.root, args.dataset_csv, args.dataset_jsonl)
    write_json(
        output_dir / "j6_s17_c2_dataset_contract_revalidation.json", revalidation)
    if rows is None:
        return 1
    if revalidation["status"] != "OK":
        return 1

    cohort_definitions = build_cohort_definitions(rows)
    registry_index = load_surface_registry(SURFACE_REGISTRY_PATH)
    classifier_summary, classifier_csv = build_classifier_hit_miss_summary(
        rows)
    label_survival, label_csv = build_surface_label_survival(rows)
    tier_analysis, tier_csv = build_tier_analysis(rows)
    dimension_analysis, dimension_csv = build_dimension_analysis(rows)
    unknown_diagnosis, unknown_csv = build_unknown_opportunity_diagnosis(
        rows, registry_index)
    registry_readiness, registry_csv = build_registry_expansion_readiness(
        rows, registry_index)
    verdict = report_verdict(
        classifier_summary, label_survival, registry_readiness)

    write_json(output_dir / "j6_s17_c2_cohort_definitions.json",
               cohort_definitions)
    write_json(
        output_dir / "j6_s17_c2_classifier_hit_miss_summary.json", classifier_summary)
    write_union_csv(
        output_dir / "j6_s17_c2_classifier_hit_miss_summary.csv", classifier_csv)
    write_json(output_dir / "j6_s17_c2_surface_label_survival.json",
               label_survival)
    write_union_csv(
        output_dir / "j6_s17_c2_surface_label_survival.csv", label_csv)
    write_json(output_dir / "j6_s17_c2_tier_analysis.json", tier_analysis)
    write_union_csv(output_dir / "j6_s17_c2_tier_analysis.csv", tier_csv)
    write_json(output_dir / "j6_s17_c2_dimension_analysis.json",
               dimension_analysis)
    write_union_csv(
        output_dir / "j6_s17_c2_dimension_analysis.csv", dimension_csv)
    write_json(
        output_dir / "j6_s17_c2_unknown_opportunity_diagnosis.json", unknown_diagnosis)
    write_union_csv(
        output_dir / "j6_s17_c2_unknown_opportunity_diagnosis.csv", unknown_csv)
    write_json(
        output_dir / "j6_s17_c2_registry_expansion_readiness.json", registry_readiness)
    write_union_csv(
        output_dir / "j6_s17_c2_registry_expansion_readiness.csv", registry_csv)

    report = build_markdown_report(
        verdict=verdict,
        revalidation=revalidation,
        cohort_definitions=cohort_definitions,
        classifier_summary=classifier_summary,
        label_survival=label_survival,
        tier_analysis=tier_analysis,
        dimension_analysis=dimension_analysis,
        unknown_diagnosis=unknown_diagnosis,
        registry_readiness=registry_readiness,
        files_changed=[
            "tools/alpha_search/j6_s17_c2_classifier_hit_miss.py",
            "tests/domains/alpha_search/judge/test_j6_s17_c2_classifier_hit_miss.py",
        ],
        tests_run=args.tests_run,
    )
    (output_dir / "J6_S17_C2_CLASSIFIER_HIT_MISS_SURFACE_SURVIVAL_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
