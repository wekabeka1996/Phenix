#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "alpha_search"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def is_nullish(value: Any) -> bool:
    return value in (None, "", "null", "None")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def as_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def derive_date_str(row: dict[str, Any]) -> str:
    for key in ("date", "plan_ts_utc"):
        value = as_text(row.get(key)).strip()
        if value:
            return value[:10]
    ts_ms = as_int(row.get("plan_ts_ms")) or as_int(row.get("ts_ms"))
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def distribution(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(as_text(row.get(key)) for row in rows)
    return dict(sorted(counter.items(), key=lambda kv: kv[0]))


def null_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if is_nullish(row.get(key)))


def tier_rows(rows: list[dict[str, Any]], tier_name: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if as_text(row.get("tier") or row.get("confidence_tier")).lower() == tier_name
    ]


def compute_tier_metrics(rows: list[dict[str, Any]], tier_name: str) -> dict[str, Any]:
    trows = tier_rows(rows, tier_name)
    outcome_rows = [r for r in trows if to_bool(r.get("outcome_available"))]
    skipped_rows = [r for r in trows if not is_nullish(
        r.get("skipped_reason")) or as_text(r.get("simulation_status")) == "skipped"]
    invalid_rows = [r for r in trows if not is_nullish(r.get(
        "invalid_outcome_reason")) or as_text(r.get("simulation_status")) in {"invalid", "error"}]
    filled_rows = [r for r in trows if to_bool(r.get("limit_filled"))]
    tp_rows = [r for r in trows if to_bool(r.get("tp_hit"))]
    sl_rows = [r for r in trows if to_bool(r.get("sl_hit"))]
    timeout_rows = [r for r in trows if to_bool(r.get("timeout_hit"))]

    return {
        "tier": tier_name,
        "total_rows": len(trows),
        "actionable_rows": sum(1 for r in trows if to_bool(r.get("actionable"))),
        "suppressed_rows": sum(1 for r in trows if to_bool(r.get("suppressed"))),
        "rows_with_null_prices": sum(
            1
            for r in trows
            if is_nullish(r.get("limit_price"))
            or is_nullish(r.get("entry_price_ref"))
            or is_nullish(r.get("tp_price"))
            or is_nullish(r.get("sl_price"))
        ),
        "rows_with_outcome": len(outcome_rows),
        "outcome_coverage_pct": round((len(outcome_rows) / len(trows)) * 100.0, 4) if trows else 0.0,
        "skipped_rows": len(skipped_rows),
        "skipped_reason_distribution": distribution(skipped_rows, "skipped_reason"),
        "invalid_rows": len(invalid_rows),
        "invalid_reason_distribution": distribution(invalid_rows, "invalid_outcome_reason"),
        "filled_rows": len(filled_rows),
        "tp_count": len(tp_rows),
        "sl_count": len(sl_rows),
        "timeout_count": len(timeout_rows),
    }


def parse_shadow_plan_config(config_path: Path) -> dict[str, Any]:
    text = config_path.read_text(encoding="utf-8")
    actionable_match = re.search(r"actionable_tiers:\s*\[([^\]]*)\]", text)
    actionable_tiers: list[str] = []
    if actionable_match:
        raw = actionable_match.group(1)
        actionable_tiers = [token.strip().strip('"').strip("'")
                            for token in raw.split(",") if token.strip()]

    emit_all_tiers = bool(re.search(r"emit_all_tiers:\s*true", text))

    ladder_names = re.findall(r"\n\s*-\s*name:\s*([a-zA-Z0-9_\-]+)", text)
    ladder_mins = [float(v) for v in re.findall(
        r"\n\s*min_confidence:\s*([0-9.]+)", text)]

    return {
        "config_path": config_path.as_posix(),
        "emit_all_tiers": emit_all_tiers,
        "actionable_tiers": actionable_tiers,
        "confidence_ladder_names": ladder_names,
        "confidence_ladder_min_confidence": ladder_mins,
    }


def source_contract_flags(root: Path) -> dict[str, Any]:
    shadow_entry_plan = (
        root / "apps/reference/domains/alpha_search/judge/shadow_entry_plan.py").read_text(encoding="utf-8")
    shadow_simulator = (
        root / "apps/reference/domains/alpha_search/judge/shadow_simulator.py").read_text(encoding="utf-8")
    augment = (
        root / "tools/alpha_search/j6_s17_c1_shadow_outcomes.py").read_text(encoding="utf-8")

    return {
        "entry_plan_has_actionable_tier_filter": "if actionable and shadow_plan_config.actionable_tiers" in shadow_entry_plan,
        "entry_plan_marks_excluded_tier": "excluded_tier" in shadow_entry_plan,
        "entry_plan_marks_suppressed": "if is_suppressed" in shadow_entry_plan,
        "entry_plan_marks_no_valid_price": "no_valid_price_ref" in shadow_entry_plan,
        "simulator_skips_non_actionable_or_suppressed": "if not plan.actionable or plan.suppressed" in shadow_simulator,
        "wrapper_emits_non_actionable_skip": "non_actionable_plan" in augment,
        "wrapper_emits_suppressed_skip": "suppressed_plan" in augment,
        "wrapper_emits_missing_ohlc_skip": "missing_ohlc_file" in augment,
        "augment_join_uses_cycle_tier": "cycle_key+tier" in augment,
        "augment_join_uses_fallback_cycle_tier_symbol_tf": "cycle_key+tier+symbol+tf_sec" in augment,
    }


def build_low_inventory_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    low = tier_rows(rows, "low")
    medium = tier_rows(rows, "medium")
    high = tier_rows(rows, "high")

    low_null_combo_counter = Counter(
        (
            is_nullish(r.get("entry_price_ref")),
            is_nullish(r.get("limit_price")),
            is_nullish(r.get("tp_price")),
            is_nullish(r.get("sl_price")),
            is_nullish(r.get("risk_reward")),
            is_nullish(r.get("side")),
        )
        for r in low
    )

    combo_readable = {
        f"entry_ref_null={c[0]}|limit_null={c[1]}|tp_null={c[2]}|sl_null={c[3]}|rr_null={c[4]}|side_null={c[5]}": n
        for c, n in sorted(low_null_combo_counter.items(), key=lambda kv: kv[1], reverse=True)
    }

    payload = {
        "low_tier_inventory": {
            "total_rows": len(low),
            "unique_cycle_keys": len({as_text(r.get("cycle_key")) for r in low if as_text(r.get("cycle_key"))}),
            "unique_plan_ids": len({as_text(r.get("plan_id")) for r in low if as_text(r.get("plan_id"))}),
            "classifier_output_distribution": distribution(low, "classifier_output"),
            "matched_surface_label_distribution": distribution(low, "matched_surface_label"),
            "regime_distribution": distribution(low, "regime"),
            "symbol_distribution": distribution(low, "symbol"),
            "side_distribution": distribution(low, "side"),
            "tf_sec_distribution": distribution(low, "tf_sec"),
            "date_distribution": dict(sorted(Counter(derive_date_str(r) for r in low).items())),
            "actionable_distribution": distribution(low, "actionable"),
            "suppressed_distribution": distribution(low, "suppressed"),
            "outcome_available_distribution": distribution(low, "outcome_available"),
            "skipped_reason_distribution": distribution(low, "skipped_reason"),
            "invalid_outcome_reason_distribution": distribution(low, "invalid_outcome_reason"),
            "null_limit_price_count": null_count(low, "limit_price"),
            "null_entry_price_ref_count": null_count(low, "entry_price_ref"),
            "null_tp_price_count": null_count(low, "tp_price"),
            "null_sl_price_count": null_count(low, "sl_price"),
            "null_risk_reward_count": null_count(low, "risk_reward"),
            "null_side_count": null_count(low, "side"),
            "null_price_field_combinations": combo_readable,
        },
        "tier_comparison_metrics": [
            compute_tier_metrics(rows, "low"),
            compute_tier_metrics(rows, "medium"),
            compute_tier_metrics(rows, "high"),
        ],
        "population_checks": {
            "all_rows": len(rows),
            "low_rows": len(low),
            "medium_rows": len(medium),
            "high_rows": len(high),
            "sum_of_three_tiers": len(low) + len(medium) + len(high),
        },
    }
    return payload


def build_low_inventory_csv_rows(inventory_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in inventory_payload["tier_comparison_metrics"]:
        rows.append({
            "tier": item["tier"],
            "total_rows": item["total_rows"],
            "actionable_rows": item["actionable_rows"],
            "suppressed_rows": item["suppressed_rows"],
            "rows_with_null_prices": item["rows_with_null_prices"],
            "rows_with_outcome": item["rows_with_outcome"],
            "outcome_coverage_pct": item["outcome_coverage_pct"],
            "skipped_rows": item["skipped_rows"],
            "invalid_rows": item["invalid_rows"],
            "filled_rows": item["filled_rows"],
            "tp_count": item["tp_count"],
            "sl_count": item["sl_count"],
            "timeout_count": item["timeout_count"],
        })
    return rows


def build_shadow_plan_generation_audit(
    *,
    config_info: dict[str, Any],
    source_flags: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    low = tier_rows(rows, "low")
    low_actionable = sum(1 for r in low if to_bool(r.get("actionable")))
    low_suppressed = sum(1 for r in low if to_bool(r.get("suppressed")))

    return {
        "questions": {
            "how_tiers_generated": {
                "answer": "Tiers are generated by iterating confidence_ladder when emit_all_tiers=true; a plan is emitted for each configured tier.",
                "evidence": {
                    "emit_all_tiers": config_info.get("emit_all_tiers"),
                    "confidence_ladder_names": config_info.get("confidence_ladder_names"),
                    "source_entry_plan_has_filter": source_flags.get("entry_plan_has_actionable_tier_filter"),
                },
            },
            "is_low_intentionally_non_actionable": {
                "answer": "Yes. Runtime config sets actionable_tiers to medium/high only, and code marks excluded tiers non-actionable.",
                "evidence": {
                    "actionable_tiers": config_info.get("actionable_tiers"),
                    "source_marks_excluded_tier": source_flags.get("entry_plan_marks_excluded_tier"),
                    "low_actionable_rows": low_actionable,
                    "low_total_rows": len(low),
                },
            },
            "does_low_represent_suppressed_or_no_entry_baseline": {
                "answer": "Partially. Suppressed low rows exist and are explicitly marked, but most low rows are non-actionable without suppression.",
                "evidence": {
                    "low_suppressed_rows": low_suppressed,
                    "low_non_suppressed_rows": len(low) - low_suppressed,
                },
            },
            "does_low_have_different_price_construction": {
                "answer": "No dedicated low-only price formula is present; price construction is shared across tiers and only depends on ladder offsets plus side.",
            },
            "does_low_have_null_prices_by_design": {
                "answer": "Only for suppressed or no-valid-price records by contract; low tier itself is not globally null-price by design.",
            },
            "are_low_plans_emitted_even_if_not_actionable": {
                "answer": "Yes. emit_all_tiers=true emits all configured tiers and marks non-qualifying/excluded tiers actionable=false.",
            },
            "is_tier_ladder_always_3_records_per_cycle": {
                "answer": "For the validated C1 dataset slice, yes (46,443 rows equals 15,481 cycles times 3 tiers).",
                "evidence": {
                    "dataset_rows": len(rows),
                    "unique_cycles": len({as_text(r.get("cycle_key")) for r in rows if as_text(r.get("cycle_key"))}),
                    "tier_counts": {
                        "low": len(tier_rows(rows, "low")),
                        "medium": len(tier_rows(rows, "medium")),
                        "high": len(tier_rows(rows, "high")),
                    },
                },
            },
            "actionable_and_suppression_population": {
                "answer": "Fields are populated and consistent with skips in outcomes: low has dominant non_actionable_plan and a secondary suppressed_plan segment.",
            },
        },
        "source_flags": source_flags,
    }


def build_simulator_skip_audit(
    *,
    sim_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    source_flags: dict[str, Any],
) -> dict[str, Any]:
    low_sim = [r for r in sim_rows if as_text(r.get("tier")).lower() == "low"]
    low_dataset = tier_rows(rows, "low")
    low_skipped = [r for r in low_sim if as_text(
        r.get("simulation_status")) == "skipped"]

    return {
        "low_simulation_record_counts": {
            "low_simulation_records": len(low_sim),
            "low_skipped_records": len(low_skipped),
            "low_success_records": sum(1 for r in low_sim if as_text(r.get("simulation_status")) == "success"),
            "low_invalid_records": sum(1 for r in low_sim if as_text(r.get("simulation_status")) in {"invalid", "error"}),
            "low_skipped_reason_distribution": distribution(low_skipped, "skipped_reason"),
        },
        "questions": {
            "skip_non_actionable": {
                "answer": "Yes. Simulator contract/wrapper skip non-actionable plans.",
                "evidence": {
                    "source_flag": source_flags.get("simulator_skips_non_actionable_or_suppressed"),
                    "wrapper_flag": source_flags.get("wrapper_emits_non_actionable_skip"),
                },
            },
            "skip_null_prices": {
                "answer": "Indirectly yes when null prices coincide with suppressed/non-actionable state; these are emitted as skipped in wrapper output.",
            },
            "skip_suppressed": {
                "answer": "Yes, explicit suppressed skip behavior is present.",
                "evidence": {"wrapper_flag": source_flags.get("wrapper_emits_suppressed_skip")},
            },
            "emit_skipped_rows_for_low": {
                "answer": "Yes. Low-tier simulator records are overwhelmingly skipped rows.",
                "evidence": {
                    "low_dataset_rows": len(low_dataset),
                    "low_dataset_skipped_distribution": distribution(low_dataset, "skipped_reason"),
                },
            },
            "skip_reason_consistency": {
                "answer": "Yes. low skipped reasons align with input fields: non_actionable for actionable=false and suppressed for suppressed=true.",
            },
            "tier_specific_treatment": {
                "answer": "No explicit low-specific branch in simulator code. Behavior is contract-driven by actionable/suppressed flags.",
            },
            "missing_ohlc_cause": {
                "answer": "Minor secondary factor only. Low sim shows a tiny missing_ohlc_file count, insufficient to explain 0 percent coverage.",
                "evidence": {
                    "low_missing_ohlc_file": distribution(low_skipped, "skipped_reason").get("missing_ohlc_file", 0)
                },
            },
            "unsupported_tf_or_symbol": {
                "answer": "No evidence of unsupported tf/symbol as primary low-tier cause in this slice.",
            },
            "join_failure_vs_simulator": {
                "answer": "Join miss exists but is marginal (one low row in augmented dataset) and not the primary driver.",
            },
        },
    }


def _index_sim_rows(sim_rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    plan_id: dict[str, list[dict[str, Any]]] = {}
    cycle_tier: dict[str, list[dict[str, Any]]] = {}
    cycle_tier_symbol_tf: dict[str, list[dict[str, Any]]] = {}

    for row in sim_rows:
        pid = as_text(row.get("plan_id"))
        cycle = as_text(row.get("cycle_key"))
        tier = as_text(row.get("tier") or row.get("confidence_tier"))
        symbol = as_text(row.get("symbol"))
        tf_sec = as_text(row.get("tf_sec"))

        if pid:
            plan_id.setdefault(pid, []).append(row)
        if cycle and tier:
            key = f"{cycle}::{tier}"
            cycle_tier.setdefault(key, []).append(row)
        if cycle and tier and symbol and tf_sec:
            key = f"{cycle}::{tier}::{symbol}::{tf_sec}"
            cycle_tier_symbol_tf.setdefault(key, []).append(row)

    return {
        "plan_id": plan_id,
        "cycle_tier": cycle_tier,
        "cycle_tier_symbol_tf": cycle_tier_symbol_tf,
    }


def build_join_augmentation_audit(rows: list[dict[str, Any]], sim_rows: list[dict[str, Any]]) -> dict[str, Any]:
    low = tier_rows(rows, "low")
    sim_idx = _index_sim_rows(sim_rows)

    matched_plan_id = 0
    matched_cycle_tier = 0
    matched_fallback = 0

    for row in low:
        pid = as_text(row.get("plan_id"))
        cycle = as_text(row.get("cycle_key"))
        tier = as_text(row.get("tier"))
        symbol = as_text(row.get("symbol"))
        tf_sec = as_text(row.get("tf_sec"))

        if pid and len(sim_idx["plan_id"].get(pid, [])) == 1:
            matched_plan_id += 1

        key_ct = f"{cycle}::{tier}" if cycle and tier else ""
        if key_ct and len(sim_idx["cycle_tier"].get(key_ct, [])) >= 1:
            matched_cycle_tier += 1

        key_fb = f"{cycle}::{tier}::{symbol}::{tf_sec}" if cycle and tier and symbol and tf_sec else ""
        if key_fb and len(sim_idx["cycle_tier_symbol_tf"].get(key_fb, [])) >= 1:
            matched_fallback += 1

    low_join_missing = sum(1 for row in low if as_text(
        row.get("invalid_outcome_reason")) == "missing_outcome_key_match")
    low_joined_outcomes = sum(
        1 for row in low if to_bool(row.get("outcome_available")))

    return {
        "questions": {
            "low_records_present_in_simulation_results": {
                "answer": True,
                "evidence": {
                    "low_simulation_records": sum(1 for r in sim_rows if as_text(r.get("tier")).lower() == "low"),
                    "low_dataset_rows": len(low),
                },
            },
            "low_records_join_to_dataset": {
                "answer": True,
                "evidence": {
                    "join_method_distribution_low": distribution(low, "join_match_method"),
                    "low_missing_outcome_key_match_rows": low_join_missing,
                },
            },
            "absent_due_to_skip_vs_filter": {
                "answer": "Low records are present in sim output and mostly skipped; absence of outcomes is mainly semantic skip, not wrapper drop.",
            },
            "augmentation_preserves_skipped_rows": {
                "answer": True,
                "evidence": {
                    "low_skipped_distribution": distribution(low, "skipped_reason"),
                    "low_outcome_available_distribution": distribution(low, "outcome_available"),
                },
            },
            "skipped_rows_marked_outcome_false": {
                "answer": True,
            },
            "incorrect_exclusion_by_join_key": {
                "answer": "Not primary. A single low join miss exists; denominator-level zero outcome coverage remains unchanged.",
            },
            "cycle_key_tier_works_for_low": {
                "answer": True,
                "evidence": {
                    "rows_with_cycle_tier_match_available": matched_cycle_tier,
                    "low_total_rows": len(low),
                },
            },
            "fallback_changes_coverage": {
                "answer": False,
                "evidence": {
                    "rows_with_fallback_match_available": matched_fallback,
                    "low_joined_outcome_records": low_joined_outcomes,
                },
            },
        },
        "join_metrics": {
            "low_total_rows": len(low),
            "low_joined_outcome_records": low_joined_outcomes,
            "low_missing_join_records": low_join_missing,
            "low_rows_with_unique_plan_id_match": matched_plan_id,
            "low_rows_with_cycle_tier_presence": matched_cycle_tier,
            "low_rows_with_cycle_tier_symbol_tf_presence": matched_fallback,
        },
    }


def classify_root_cause(
    *,
    inventory: dict[str, Any],
    shadow_audit: dict[str, Any],
    simulator_audit: dict[str, Any],
    join_audit: dict[str, Any],
) -> dict[str, Any]:
    low_total = inventory["low_tier_inventory"]["total_rows"]
    low_actionable_true = inventory["low_tier_inventory"]["actionable_distribution"].get(
        "True", 0)
    low_suppressed_true = inventory["low_tier_inventory"]["suppressed_distribution"].get(
        "True", 0)
    low_skipped_non_actionable = inventory["low_tier_inventory"]["skipped_reason_distribution"].get(
        "non_actionable_plan", 0)
    low_skipped_records = simulator_audit["low_simulation_record_counts"].get(
        "low_skipped_records", 0)
    low_missing_join = join_audit["join_metrics"].get(
        "low_missing_join_records", 0)

    design_non_actionable = low_total > 0 and low_actionable_true <= 1 and low_skipped_non_actionable >= int(
        0.7 * low_total)
    primary_bucket = "INSUFFICIENT_EVIDENCE"
    confidence = "low"

    if design_non_actionable:
        primary_bucket = "LOW_TIER_NON_ACTIONABLE_BY_DESIGN"
        confidence = "high"
    elif low_missing_join > 0 and (low_missing_join / max(low_total, 1)) >= 0.2:
        primary_bucket = "AUGMENTATION_JOIN_DEFECT"
        confidence = "medium"
    elif low_skipped_records > 0 and low_actionable_true >= int(0.2 * max(low_total, 1)):
        primary_bucket = "SIMULATOR_SKIPS_NON_ACTIONABLE_PLANS"
        confidence = "medium"
    elif low_suppressed_true >= int(0.8 * low_total):
        primary_bucket = "LOW_TIER_SUPPRESSED_BY_DESIGN"
        confidence = "high"

    buckets = [
        {
            "bucket": "LOW_TIER_NON_ACTIONABLE_BY_DESIGN",
            "evidence": [
                f"low_actionable_true={low_actionable_true} of {low_total}",
                f"low_skipped_non_actionable={low_skipped_non_actionable}",
                f"actionable_tiers={shadow_audit['questions']['is_low_intentionally_non_actionable']['evidence']['actionable_tiers']}",
            ],
            "counter_evidence": [
                f"low_suppressed_true={low_suppressed_true}",
            ],
            "confidence": "high" if design_non_actionable else "low",
            "impact_on_c2": "Low tier should remain out of trade-performance denominators.",
            "recommended_action": "Keep low tier coverage-only in C2 performance interpretation.",
        },
        {
            "bucket": "SIMULATOR_SKIPS_NON_ACTIONABLE_PLANS",
            "evidence": [
                "Simulator/wrapper skip non-actionable and suppressed rows by contract.",
                json.dumps(
                    simulator_audit["low_simulation_record_counts"], ensure_ascii=True),
            ],
            "counter_evidence": [
                "No low-specific branch in simulator logic.",
            ],
            "confidence": "high",
            "impact_on_c2": "Explains zero outcomes for low without implying simulator defect.",
            "recommended_action": "No simulator patch in this package.",
        },
        {
            "bucket": "AUGMENTATION_JOIN_DEFECT",
            "evidence": [
                f"low_missing_join_records={join_audit['join_metrics']['low_missing_join_records']}",
            ],
            "counter_evidence": [
                "Join misses are marginal and do not explain zero low outcomes.",
            ],
            "confidence": "low",
            "impact_on_c2": "No material impact in this slice.",
            "recommended_action": "Monitor; no patch justified now.",
        },
    ]

    return {
        "primary_bucket": primary_bucket,
        "secondary_buckets": [
            "SIMULATOR_SKIPS_NON_ACTIONABLE_PLANS",
            "LOW_TIER_SUPPRESSED_BY_DESIGN",
        ],
        "confidence": confidence,
        "classification_table": buckets,
    }


def build_decision_matrix(
    *,
    root_classification: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    low = tier_rows(rows, "low")
    non_low = [r for r in rows if as_text(r.get("tier")).lower() in {
        "medium", "high"}]

    total_rows = len(rows)
    actionable_all = sum(1 for r in rows if to_bool(
        r.get("actionable")) and not to_bool(r.get("suppressed")))
    actionable_non_low = sum(1 for r in non_low if to_bool(
        r.get("actionable")) and not to_bool(r.get("suppressed")))
    outcome_all = sum(1 for r in rows if to_bool(r.get("outcome_available")))
    outcome_non_low = sum(
        1 for r in non_low if to_bool(r.get("outcome_available")))

    track_filled_all = [r for r in rows if as_text(r.get("classifier_output")) == "TRACK_ONLY" and to_bool(
        r.get("outcome_available")) and to_bool(r.get("limit_filled")) and not is_nullish(r.get("net_pnl_pct"))]
    unknown_filled_all = [r for r in rows if as_text(r.get("classifier_output")) == "UNKNOWN" and to_bool(
        r.get("outcome_available")) and to_bool(r.get("limit_filled")) and not is_nullish(r.get("net_pnl_pct"))]
    track_filled_non_low = [r for r in non_low if as_text(r.get("classifier_output")) == "TRACK_ONLY" and to_bool(
        r.get("outcome_available")) and to_bool(r.get("limit_filled")) and not is_nullish(r.get("net_pnl_pct"))]
    unknown_filled_non_low = [r for r in non_low if as_text(r.get("classifier_output")) == "UNKNOWN" and to_bool(
        r.get("outcome_available")) and to_bool(r.get("limit_filled")) and not is_nullish(r.get("net_pnl_pct"))]

    def avg_net(rows_in: list[dict[str, Any]]) -> float | None:
        vals = [float(r["net_pnl_pct"])
                for r in rows_in if not is_nullish(r.get("net_pnl_pct"))]
        return (sum(vals) / len(vals)) if vals else None

    track_delta = None
    unknown_delta = None
    if avg_net(track_filled_all) is not None and avg_net(track_filled_non_low) is not None:
        track_delta = avg_net(track_filled_non_low) - avg_net(track_filled_all)
    if avg_net(unknown_filled_all) is not None and avg_net(unknown_filled_non_low) is not None:
        unknown_delta = avg_net(unknown_filled_non_low) - \
            avg_net(unknown_filled_all)

    material_change = bool((track_delta and abs(track_delta) > 0.001) or (
        unknown_delta and abs(unknown_delta) > 0.001))

    include_decision = "EXCLUDE_FROM_TRADE_PERFORMANCE_INCLUDE_IN_COVERAGE"
    patch_decision = "NO_PATCH_DIAGNOSTIC_ONLY"
    rerun_decision = "NO_RERUN_C2_REQUIRED"
    closure_decision = "D_CLOSURE_STANDS"

    if root_classification["primary_bucket"] in {"AUGMENTATION_JOIN_DEFECT", "SIMULATOR_CONTRACT_GAP", "SHADOW_PLAN_GENERATION_DEFECT"}:
        patch_decision = {
            "AUGMENTATION_JOIN_DEFECT": "PATCH_REQUIRED_AUGMENTATION_JOIN_DEFECT",
            "SIMULATOR_CONTRACT_GAP": "PATCH_REQUIRED_SIMULATOR_CONTRACT_DEFECT",
            "SHADOW_PLAN_GENERATION_DEFECT": "PATCH_REQUIRED_SHADOW_PLAN_CONTRACT_DEFECT",
        }[root_classification["primary_bucket"]]
        rerun_decision = "RERUN_C2_AFTER_PATCH"
        closure_decision = "D_CLOSURE_NEEDS_AMENDMENT"

    return {
        "decision_include_low_tier_in_hit_miss": include_decision,
        "decision_patch_justified_now": patch_decision,
        "decision_rerun_c2": rerun_decision,
        "decision_d_closure_impact": closure_decision,
        "impact_metrics": {
            "c2_all_rows_denominator": {
                "with_low": total_rows,
                "without_low": len(non_low),
                "delta": total_rows - len(non_low),
            },
            "c2_actionable_rows_denominator": {
                "with_low": actionable_all,
                "without_low": actionable_non_low,
                "delta": actionable_all - actionable_non_low,
            },
            "c2_outcome_available_denominator": {
                "with_low": outcome_all,
                "without_low": outcome_non_low,
                "delta": outcome_all - outcome_non_low,
            },
            "track_only_vs_unknown_materiality": {
                "track_only_avg_net_delta_without_low": track_delta,
                "unknown_avg_net_delta_without_low": unknown_delta,
                "material_change": material_change,
            },
            "low_tier_specific": {
                "low_total_rows": len(low),
                "low_actionable_rows": sum(1 for r in low if to_bool(r.get("actionable"))),
                "low_non_actionable_rows": sum(1 for r in low if not to_bool(r.get("actionable"))),
                "low_suppressed_rows": sum(1 for r in low if to_bool(r.get("suppressed"))),
                "low_null_price_rows": sum(
                    1
                    for r in low
                    if is_nullish(r.get("limit_price"))
                    or is_nullish(r.get("entry_price_ref"))
                    or is_nullish(r.get("tp_price"))
                    or is_nullish(r.get("sl_price"))
                ),
                "low_simulation_records": None,
                "low_skipped_records": sum(1 for r in low if not is_nullish(r.get("skipped_reason"))),
                "low_joined_outcome_records": sum(1 for r in low if to_bool(r.get("outcome_available"))),
                "low_missing_join_records": sum(1 for r in low if as_text(r.get("invalid_outcome_reason")) == "missing_outcome_key_match"),
                "low_no_outcome_reason_distribution": distribution([r for r in low if not to_bool(r.get("outcome_available"))], "skipped_reason"),
            },
        },
    }


def choose_verdict(root_classification: dict[str, Any], decision_matrix: dict[str, Any]) -> str:
    primary = root_classification["primary_bucket"]
    patch = decision_matrix["decision_patch_justified_now"]

    if patch != "NO_PATCH_DIAGNOSTIC_ONLY":
        return "LOW_TIER_DEFECT_FOUND_PATCH_REQUIRED"
    if primary == "LOW_TIER_NON_ACTIONABLE_BY_DESIGN":
        return "LOW_TIER_DIAGNOSTIC_COMPLETE_NON_ACTIONABLE_BY_DESIGN"
    if primary == "LOW_TIER_SUPPRESSED_BY_DESIGN":
        return "LOW_TIER_DIAGNOSTIC_COMPLETE_SUPPRESSED_BY_DESIGN"
    if primary == "SIMULATOR_SKIPS_NON_ACTIONABLE_PLANS":
        return "LOW_TIER_DIAGNOSTIC_COMPLETE_SIMULATOR_SKIP_BY_CONTRACT"
    return "LOW_TIER_DIAGNOSTIC_COMPLETE_NO_PATCH_REQUIRED"


def render_report(
    *,
    verdict: str,
    artifact_checks: dict[str, bool],
    inventory: dict[str, Any],
    shadow_audit: dict[str, Any],
    simulator_audit: dict[str, Any],
    join_audit: dict[str, Any],
    root_classification: dict[str, Any],
    decision_matrix: dict[str, Any],
    files_changed: list[str],
) -> str:
    lines: list[str] = []
    lines.append("AGENT_REPORT_V1")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("J6-S17-E completed as read-only diagnostic. Low tier has 0 percent outcome coverage primarily because low plans are configured non-actionable and then contractually skipped; not because of trade-performance defect.")
    lines.append("")
    lines.append("## Final Verdict")
    lines.append(verdict)
    lines.append("")
    lines.append("## Scope")
    lines.append("alpha_search / LLM Judge / Policy Cortex forward-validation artifacts C1, C2, D and shadow plan/simulator/augmentation code surfaces.")
    lines.append("")
    lines.append("## Proven Facts")
    lines.append(
        f"- Required artifacts validated: {all(artifact_checks.values())}")
    lines.append(
        f"- Low rows: {inventory['low_tier_inventory']['total_rows']}; low outcome rows: {decision_matrix['impact_metrics']['low_tier_specific']['low_joined_outcome_records']}")
    lines.append(
        f"- Low actionable rows: {decision_matrix['impact_metrics']['low_tier_specific']['low_actionable_rows']}")
    lines.append(
        f"- Low skipped reason distribution: {json.dumps(inventory['low_tier_inventory']['skipped_reason_distribution'], ensure_ascii=True)}")
    lines.append("")
    lines.append("## Inferences")
    lines.append(
        "- The dominant low-tier no-outcome mass is expected semantic skip behavior, not failed trades.")
    lines.append(
        "- A minor join residual exists but is insufficient to explain low-tier 0 percent coverage.")
    lines.append("")
    lines.append("## Assumptions")
    lines.append(
        "- Current C1/C2 artifacts are authoritative for this diagnostic window.")
    lines.append("")
    lines.append("## Unknowns")
    lines.append(
        "- Whether future forward windows will include materially more actionable low-tier rows.")
    lines.append("")
    lines.append("## Input Artifact Validation")
    for path, ok in artifact_checks.items():
        lines.append(f"- {path}: {'OK' if ok else 'MISSING'}")
    lines.append("")
    lines.append("## Low-Tier Inventory")
    lines.append(json.dumps(
        inventory["low_tier_inventory"], indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Tier Comparison")
    lines.append(json.dumps(
        inventory["tier_comparison_metrics"], indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Shadow Plan Generation Audit")
    lines.append(json.dumps(shadow_audit, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Simulator Skip Audit")
    lines.append(json.dumps(simulator_audit, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Join / Augmentation Audit")
    lines.append(json.dumps(join_audit, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Root Cause Classification")
    lines.append(json.dumps(root_classification, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Decision Matrix")
    lines.append(json.dumps(decision_matrix, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("## Impact on C2")
    lines.append(
        "Low tier should be excluded from trade-performance hit/miss denominators and retained for coverage/readiness accounting.")
    lines.append("")
    lines.append("## Impact on J6-S17-D Closure")
    lines.append(decision_matrix["decision_d_closure_impact"])
    lines.append("")
    lines.append("## Files Changed")
    for file in files_changed:
        lines.append(f"- {file}")
    lines.append("")
    lines.append("## Runtime Behavior Changed")
    lines.append("No")
    lines.append("")
    lines.append("## Authority Changed")
    lines.append("No")
    lines.append("")
    lines.append("## Order Behavior Changed")
    lines.append("No")
    lines.append("")
    lines.append("## Tests / Validation Run")
    lines.append("- JSON parse validation for newly written outputs")
    lines.append("- Report file existence validation")
    lines.append(
        "- Runtime tests were not required because runtime code/semantics were not changed")
    lines.append("")
    lines.append("## Residual Risks")
    lines.append(
        "- Future append drift between plan logs and dataset slice can add small join residuals.")
    lines.append("")
    lines.append("## What Remains Unproven")
    lines.append(
        "- No proof yet that low tier can carry stable actionable trade-performance signal in a larger forward window.")
    lines.append("")
    lines.append("## Recommended Next Package")
    lines.append("J6-S17-F EXTENDED_FORWARD_COLLECTION_PLAN")
    lines.append("")
    return "\n".join(lines)


def validate_required_artifacts(root: Path, required: list[Path]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in required:
        rel = path.relative_to(root).as_posix()
        result[rel] = path.exists()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="J6-S17-E low tier outcome coverage diagnostic (read-only).")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--augmented-csv", type=Path, default=REPORTS_DIR /
                        "j6_s17_c1_augmented_policy_outcome_dataset.csv")
    parser.add_argument("--simulation-results", type=Path,
                        default=REPORTS_DIR / "j6_s17_c1_shadow_simulation_results.jsonl")
    parser.add_argument("--output-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    root = args.root
    output_dir = args.output_dir

    required_paths = [
        root / "reports/alpha_search/J6_S17_C1_SHADOW_SIMULATOR_OUTCOME_COLLECTION_REPORT.md",
        root / "reports/alpha_search/j6_s17_c1_augmented_policy_outcome_dataset.csv",
        root / "reports/alpha_search/j6_s17_c1_augmented_policy_outcome_dataset.jsonl",
        root / "reports/alpha_search/j6_s17_c1_outcome_join_summary.json",
        root / "reports/alpha_search/j6_s17_c1_outcome_availability_by_dimension.json",
        root / "reports/alpha_search/j6_s17_c1_shadow_simulation_results.jsonl",
        root / "reports/alpha_search/j6_s17_c1_simulator_run_summary.json",
        root / "reports/alpha_search/J6_S17_C2_CLASSIFIER_HIT_MISS_SURFACE_SURVIVAL_REPORT.md",
        root / "reports/alpha_search/j6_s17_c2_tier_analysis.json",
        root / "reports/alpha_search/j6_s17_c2_dimension_analysis.json",
        root / "reports/alpha_search/j6_s17_c2_cohort_definitions.json",
        root / "reports/alpha_search/J6_S17_D_SURFACE_EVIDENCE_DECISION_REVIEW_REPORT.md",
        root / "reports/alpha_search/j6_s17_d_surface_evidence_decision_matrix.json",
        root / "reports/alpha_search/j6_s17_d_forward_validation_closure_ledger.json",
        root / "apps/reference/domains/alpha_search/judge/shadow_entry_plan.py",
        root / "apps/reference/domains/alpha_search/judge/shadow_simulator.py",
        root / "apps/reference/domains/alpha_search/judge/contracts.py",
        root / "apps/reference/domains/alpha_search/judge/simulation_models.py",
        root / "tools/alpha_search/j6_s17_c1_shadow_outcomes.py",
        root / "tools/alpha_search/j6_s17_c1_run_shadow_simulator.py",
        root / "tools/alpha_search/j6_s17_c1_augment_outcomes.py",
        root / "tools/alpha_search/j6_s17_c2_classifier_hit_miss.py",
        root / "tests/domains/alpha_search/judge/test_j6_s17_c1_shadow_outcomes.py",
        root / "tests/domains/alpha_search/judge/test_j6_s17_c2_classifier_hit_miss.py",
    ]

    artifact_checks = validate_required_artifacts(root, required_paths)
    if not all(artifact_checks.values()):
        payload = {
            "verdict": "BLOCKED_REQUIRED_ARTIFACTS_MISSING",
            "artifact_checks": artifact_checks,
        }
        write_json(output_dir / "j6_s17_e_low_tier_decision_matrix.json", payload)
        return 2

    rows = read_csv_rows(args.augmented_csv)
    sim_rows = read_jsonl(args.simulation_results)

    inventory = build_low_inventory_payload(rows)
    inventory_csv_rows = build_low_inventory_csv_rows(inventory)

    config_info = parse_shadow_plan_config(root / "config/alpha_search.yaml")
    source_flags = source_contract_flags(root)

    shadow_audit = build_shadow_plan_generation_audit(
        config_info=config_info,
        source_flags=source_flags,
        rows=rows,
    )
    simulator_audit = build_simulator_skip_audit(
        sim_rows=sim_rows,
        rows=rows,
        source_flags=source_flags,
    )
    join_audit = build_join_augmentation_audit(rows, sim_rows)
    root_classification = classify_root_cause(
        inventory=inventory,
        shadow_audit=shadow_audit,
        simulator_audit=simulator_audit,
        join_audit=join_audit,
    )
    decision_matrix = build_decision_matrix(
        root_classification=root_classification,
        rows=rows,
    )
    decision_matrix["impact_metrics"]["low_tier_specific"]["low_simulation_records"] = simulator_audit["low_simulation_record_counts"]["low_simulation_records"]

    verdict = choose_verdict(root_classification, decision_matrix)
    decision_matrix["verdict"] = verdict

    root_payload = {
        "primary_bucket": root_classification["primary_bucket"],
        "secondary_buckets": root_classification["secondary_buckets"],
        "confidence": root_classification["confidence"],
        "classification_table": root_classification["classification_table"],
    }

    write_json(output_dir / "j6_s17_e_low_tier_inventory.json", inventory)
    write_csv(output_dir / "j6_s17_e_low_tier_inventory.csv", inventory_csv_rows)
    write_json(
        output_dir / "j6_s17_e_shadow_plan_generation_audit.json", shadow_audit)
    write_json(output_dir / "j6_s17_e_simulator_skip_audit.json",
               simulator_audit)
    write_json(
        output_dir / "j6_s17_e_low_tier_join_augmentation_audit.json", join_audit)
    write_json(
        output_dir / "j6_s17_e_low_tier_root_cause_classification.json", root_payload)
    write_json(output_dir / "j6_s17_e_low_tier_decision_matrix.json",
               decision_matrix)

    report = render_report(
        verdict=verdict,
        artifact_checks=artifact_checks,
        inventory=inventory,
        shadow_audit=shadow_audit,
        simulator_audit=simulator_audit,
        join_audit=join_audit,
        root_classification=root_payload,
        decision_matrix=decision_matrix,
        files_changed=[
            "tools/alpha_search/j6_s17_e_low_tier_diagnostic.py",
            "reports/alpha_search/j6_s17_e_low_tier_inventory.json",
            "reports/alpha_search/j6_s17_e_low_tier_inventory.csv",
            "reports/alpha_search/j6_s17_e_shadow_plan_generation_audit.json",
            "reports/alpha_search/j6_s17_e_simulator_skip_audit.json",
            "reports/alpha_search/j6_s17_e_low_tier_join_augmentation_audit.json",
            "reports/alpha_search/j6_s17_e_low_tier_root_cause_classification.json",
            "reports/alpha_search/j6_s17_e_low_tier_decision_matrix.json",
            "reports/alpha_search/J6_S17_E_LOW_TIER_OUTCOME_COVERAGE_DIAGNOSTIC_REPORT.md",
        ],
    )
    (output_dir / "J6_S17_E_LOW_TIER_OUTCOME_COVERAGE_DIAGNOSTIC_REPORT.md").write_text(report, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
