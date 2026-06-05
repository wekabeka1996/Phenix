#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from apps.reference.domains.alpha_search.judge.config_models import ShadowSimulatorConfig
from apps.reference.domains.alpha_search.judge.contracts import ShadowEntryPlan
from apps.reference.domains.alpha_search.judge.shadow_simulator import ShadowPlanSimulator
from apps.reference.domains.alpha_search.judge.simulation_models import ShadowSimulationResult


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "alpha_search"
LOGS_DIR = REPO_ROOT / "logs" / "judge_experts"
RECORDER_DIR = REPO_ROOT / "data" / "recorder"
BASE_DATASET_CSV = REPORTS_DIR / "j6_s17_b_joined_policy_outcome_dataset.csv"
BASE_DATASET_JSONL = REPORTS_DIR / "j6_s17_b_joined_policy_outcome_dataset.jsonl"


def utc_date_from_ts_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def iso_from_ts_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(
        f"Unsupported value for JSON serialization: {type(value)!r}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2,
                  ensure_ascii=True, default=json_default)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def discover_shadow_plan_files(root: Path) -> list[Path]:
    return sorted((root / "logs" / "judge_experts").glob("shadow_entry_plan_*.jsonl"))


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


def build_contract_audit(root: Path) -> dict[str, Any]:
    shadow_files = discover_shadow_plan_files(root)
    symbols = sorted({path.name.split("_")[3] if path.name.count(
        "_") >= 3 else "" for path in shadow_files})
    symbols = [symbol for symbol in symbols if symbol]
    recorder_sample_dir = root / "data" / "recorder"
    recorder_dates = sorted([path.name for path in recorder_sample_dir.iterdir(
    ) if path.is_dir()]) if recorder_sample_dir.exists() else []
    table = [
        {
            "surface": "Simulator input file",
            "file_or_model": "apps/reference/domains/alpha_search/judge/contracts.py::ShadowEntryPlan",
            "finding": "Input is JSONL of strict ShadowEntryPlan records keyed by plan_id, cycle_key, symbol, tf_sec, ts_ms, and confidence_tier.",
            "join_impact": "Input preserves cycle identity and tier; tf_sec is present only on the plan side."
        },
        {
            "surface": "Simulator output model",
            "file_or_model": "apps/reference/domains/alpha_search/judge/simulation_models.py::ShadowSimulationResult",
            "finding": "Raw output contains plan_id, cycle_key, symbol, ts_ms, entry_side, confidence_tier, fill/exit fields, and pct economics.",
            "join_impact": "Raw engine output preserves plan_id and cycle_key+tier, but not tf_sec; wrapper must carry tf_sec through from input."
        },
        {
            "surface": "Recorder loader",
            "file_or_model": "apps/reference/domains/alpha_search/judge/shadow_simulator.py::_load_bars",
            "finding": "Recorder filename contract is exact UTC-date folder plus SYMBOL_TFSEC.csv, for example BTCUSDT_300.csv.",
            "join_impact": "Simulation availability depends on exact filename match; missing files must stay explicit skipped records."
        },
        {
            "surface": "Batch behavior",
            "file_or_model": "apps/reference/domains/alpha_search/judge/shadow_simulator.py::run_batch",
            "finding": "Engine skips non-actionable and suppressed plans and silently continues when OHLC is missing.",
            "join_impact": "Current CLI cannot explain missing outcome rows; wrapper must emit skipped_reason records for full-row augmentation."
        },
        {
            "surface": "Plan identity",
            "file_or_model": "apps/reference/domains/alpha_search/judge/shadow_entry_plan.py::derive_shadow_entry_plans",
            "finding": "plan_id format is sep_{tier}_{symbol}_{ts_ms}; tf_sec is not encoded in plan_id.",
            "join_impact": "plan_id is not globally unique across timeframes; safe augmentation cannot rely on plan_id alone."
        },
    ]
    answers = {
        "input_format": "JSONL ShadowEntryPlan records validated by the ShadowEntryPlan Pydantic model.",
        "output_format": "JSONL ShadowSimulationResult records from the simulator engine; the C1 wrapper extends them with tf_sec, tier, outcome flags, and skipped/invalid reasons.",
        "result_model": "ShadowSimulationResult",
        "join_keys_available": {
            "plan_id": True,
            "cycle_key": True,
            "tier": True,
            "symbol": True,
            "tf_sec": False,
            "plan_ts_ms": True,
        },
        "preserves_original_identity": True,
        "economics_supported": {
            "gross_pnl_pct": True,
            "net_pnl_pct": True,
            "fees_paid_pct": True,
            "separate_fees": False,
            "separate_slippage": False,
        },
        "behavior_support": {
            "limit_fill": True,
            "tp": True,
            "sl": True,
            "timeout": True,
            "ambiguous_intrabar": True,
            "missing_ohlc_data": "engine skips; wrapper can emit skipped_reason",
        },
        "recorder_filename_contract": "data/recorder/YYYY-MM-DD/SYMBOL_TFSEC.csv",
        "supported_timeframes": [180, 300, 900],
        "supported_symbols_observed": symbols,
        "recorder_date_dirs_observed": {
            "count": len(recorder_dates),
            "first": recorder_dates[0] if recorder_dates else None,
            "last": recorder_dates[-1] if recorder_dates else None,
        },
        "join_key_verdict": "cycle_key+tier is the first globally safe join key on current artifacts because plan_id duplicates across timeframes.",
    }
    return {
        "package": "J6-S17-C1",
        "status": "AUDITED",
        "answers": answers,
        "contract_table": table,
    }


def revalidate_inputs(root: Path) -> dict[str, Any]:
    if not BASE_DATASET_CSV.exists():
        raise FileNotFoundError(f"Missing base dataset: {BASE_DATASET_CSV}")
    if not BASE_DATASET_JSONL.exists():
        raise FileNotFoundError(
            f"Missing base dataset JSONL: {BASE_DATASET_JSONL}")

    dataset_rows = read_csv_rows(BASE_DATASET_CSV)
    shadow_plan_rows = 0
    shadow_cycle_keys: set[str] = set()
    shadow_plan_ids: set[str] = set()
    plan_id_counter: Counter[str] = Counter()
    shadow_symbols: set[str] = set()
    shadow_tf_secs: set[int] = set()
    shadow_dates: set[str] = set()
    null_price_rows = 0
    suppressed_rows = 0
    actionable_true = 0
    actionable_false = 0

    for path in discover_shadow_plan_files(root):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                shadow_plan_rows += 1
                cycle_key = str(record.get("cycle_key") or "")
                if cycle_key:
                    shadow_cycle_keys.add(cycle_key)
                plan_id = str(record.get("plan_id") or "")
                if plan_id:
                    shadow_plan_ids.add(plan_id)
                    plan_id_counter[plan_id] += 1
                symbol = str(record.get("symbol") or "")
                if symbol:
                    shadow_symbols.add(symbol)
                tf_sec = normalize_int(record.get("tf_sec"))
                if tf_sec is not None:
                    shadow_tf_secs.add(tf_sec)
                ts_ms = normalize_int(record.get("ts_ms"))
                if ts_ms is not None:
                    shadow_dates.add(utc_date_from_ts_ms(ts_ms))
                if normalize_float(record.get("limit_price")) is None:
                    null_price_rows += 1
                if bool_from_any(record.get("suppressed")):
                    suppressed_rows += 1
                if bool_from_any(record.get("actionable")):
                    actionable_true += 1
                else:
                    actionable_false += 1

    dataset_cycle_keys = {str(row.get("cycle_key") or "")
                          for row in dataset_rows if row.get("cycle_key")}
    dataset_plan_ids = [str(row.get("plan_id") or "")
                        for row in dataset_rows if row.get("plan_id")]
    dataset_symbols = sorted({str(row.get("symbol") or "")
                             for row in dataset_rows if row.get("symbol")})
    dataset_tf_secs = sorted({normalize_int(row.get(
        "tf_sec")) for row in dataset_rows if normalize_int(row.get("tf_sec")) is not None})
    return {
        "required_inputs": {
            "base_dataset_csv": BASE_DATASET_CSV.exists(),
            "base_dataset_jsonl": BASE_DATASET_JSONL.exists(),
            "shadow_plan_files": len(discover_shadow_plan_files(root)),
            "recorder_root_exists": RECORDER_DIR.exists(),
        },
        "base_dataset": {
            "rows": len(dataset_rows),
            "unique_cycle_keys": len(dataset_cycle_keys),
            "unique_plan_ids": len(set(dataset_plan_ids)),
            "duplicate_plan_id_count": sum(1 for count in Counter(dataset_plan_ids).values() if count > 1),
            "symbols": dataset_symbols,
            "tf_sec_values": dataset_tf_secs,
        },
        "shadow_plans": {
            "rows": shadow_plan_rows,
            "unique_cycle_keys": len(shadow_cycle_keys),
            "unique_plan_ids": len(shadow_plan_ids),
            "duplicate_plan_id_count": sum(1 for count in plan_id_counter.values() if count > 1),
            "symbols": sorted(shadow_symbols),
            "tf_sec_values": sorted(shadow_tf_secs),
            "date_range": {
                "start": min(shadow_dates) if shadow_dates else None,
                "end": max(shadow_dates) if shadow_dates else None,
            },
            "null_limit_price_rows": null_price_rows,
            "suppressed_rows": suppressed_rows,
            "actionable_true": actionable_true,
            "actionable_false": actionable_false,
        },
    }


def _base_record_from_plan(plan: ShadowEntryPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "cycle_key": plan.cycle_key,
        "tier": plan.confidence_tier,
        "symbol": plan.symbol,
        "side": plan.entry_side,
        "tf_sec": plan.tf_sec,
        "plan_ts_ms": plan.ts_ms,
        "plan_ts_utc": iso_from_ts_ms(plan.ts_ms),
        "actionable": plan.actionable,
        "suppressed": plan.suppressed,
        "outcome_available": False,
        "simulation_status": "unknown",
        "limit_filled": False,
        "fill_ts_ms": None,
        "fill_delay_ms": None,
        "entry_fill_price": None,
        "exit_ts_ms": None,
        "exit_price": None,
        "exit_reason": None,
        "terminal_reason": None,
        "gross_pnl_pct": None,
        "gross_pnl_bps": None,
        "fees_paid_pct": None,
        "total_cost_bps": None,
        "fees_bps": None,
        "slippage_bps": None,
        "net_pnl_pct": None,
        "net_pnl_bps": None,
        "win_loss": None,
        "tp_hit": False,
        "sl_hit": False,
        "timeout_hit": False,
        "ambiguous_intrabar": False,
        "invalid_outcome_reason": None,
        "skipped_reason": None,
        "join_key": f"{plan.cycle_key}::{plan.confidence_tier}",
    }


def _skipped_record(plan: ShadowEntryPlan, reason: str) -> dict[str, Any]:
    record = _base_record_from_plan(plan)
    record["simulation_status"] = "skipped"
    record["skipped_reason"] = reason
    record["terminal_reason"] = reason
    return record


def _invalid_record(plan: ShadowEntryPlan, reason: str) -> dict[str, Any]:
    record = _base_record_from_plan(plan)
    record["simulation_status"] = "invalid"
    record["invalid_outcome_reason"] = reason
    record["terminal_reason"] = reason
    return record


def _success_record(plan: ShadowEntryPlan, result: ShadowSimulationResult) -> dict[str, Any]:
    record = _base_record_from_plan(plan)
    record["simulation_status"] = "success"
    record["terminal_reason"] = result.outcome
    record["exit_reason"] = result.outcome_reason
    record["outcome_available"] = True
    record["limit_filled"] = result.fill_ts_ms is not None
    record["fill_ts_ms"] = result.fill_ts_ms
    record["fill_delay_ms"] = (
        result.fill_ts_ms - plan.ts_ms) if result.fill_ts_ms is not None else None
    record["entry_fill_price"] = result.fill_price
    record["exit_ts_ms"] = result.exit_ts_ms
    record["exit_price"] = result.exit_price
    record["tp_hit"] = result.outcome == "FILLED_TP"
    record["sl_hit"] = result.outcome == "FILLED_SL"
    record["timeout_hit"] = result.outcome in {
        "FILLED_TIMEOUT", "NOT_FILLED_TIMEOUT"}
    record["ambiguous_intrabar"] = result.outcome == "AMBIGUOUS_INTRABAR"
    if result.outcome == "AMBIGUOUS_INTRABAR":
        record["simulation_status"] = "invalid"
        record["outcome_available"] = False
        record["invalid_outcome_reason"] = "ambiguous_intrabar_exit_unresolved"
    elif result.outcome == "ERROR":
        record["simulation_status"] = "error"
        record["outcome_available"] = False
        record["invalid_outcome_reason"] = result.outcome_reason or "simulator_error"
    else:
        if result.gross_pnl_pct is not None:
            record["gross_pnl_pct"] = result.gross_pnl_pct
            record["gross_pnl_bps"] = round(result.gross_pnl_pct * 100.0, 4)
        if result.net_pnl_pct is not None:
            record["net_pnl_pct"] = result.net_pnl_pct
            record["net_pnl_bps"] = round(result.net_pnl_pct * 100.0, 4)
            if result.net_pnl_pct > 0:
                record["win_loss"] = "WIN"
            elif result.net_pnl_pct < 0:
                record["win_loss"] = "LOSS"
            else:
                record["win_loss"] = "FLAT"
        if result.fees_paid_pct is not None:
            record["fees_paid_pct"] = result.fees_paid_pct
            record["total_cost_bps"] = round(result.fees_paid_pct * 100.0, 4)
    return record


def build_run_summary(
    *,
    contract_audit: dict[str, Any],
    input_revalidation: dict[str, Any],
    records: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    status_counter = Counter(record["simulation_status"] for record in records)
    reason_counter = Counter(
        record["skipped_reason"] or record["invalid_outcome_reason"] or record["terminal_reason"]
        for record in records
        if record["simulation_status"] in {"skipped", "invalid", "error"}
    )
    outcome_counter = Counter(record["terminal_reason"]
                              for record in records if record["simulation_status"] == "success")
    total_rows = len(records)
    success_count = status_counter.get("success", 0)
    summary = {
        "package": "J6-S17-C1",
        "contract_audit_status": contract_audit["status"],
        "input_revalidation": input_revalidation,
        "simulation_coverage": {
            "total_shadow_plan_rows": total_rows,
            "simulation_records_total": total_rows,
            "simulation_success_count": success_count,
            "simulation_error_count": status_counter.get("error", 0),
            "simulation_skipped_count": status_counter.get("skipped", 0),
            "simulation_invalid_count": status_counter.get("invalid", 0),
            "simulation_success_rate_pct": round((success_count / total_rows) * 100.0, 4) if total_rows else 0.0,
        },
        "outcome_type_distribution": dict(sorted(outcome_counter.items())),
        "missing_or_invalid_reason_counts": dict(sorted(reason_counter.items())),
        "output_artifact": output_path.as_posix(),
    }
    return summary


def run_shadow_simulations(root: Path, output_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    contract_audit = build_contract_audit(root)
    input_revalidation = revalidate_inputs(root)
    simulator = ShadowPlanSimulator(ShadowSimulatorConfig(enabled=True))
    records: list[dict[str, Any]] = []

    for plan_file in discover_shadow_plan_files(root):
        with plan_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw: dict[str, Any] | None = None
                try:
                    raw = json.loads(line)
                    plan = ShadowEntryPlan.model_validate(raw)
                except (json.JSONDecodeError, ValidationError) as exc:
                    records.append(
                        {
                            "plan_id": None,
                            "cycle_key": None,
                            "tier": None,
                            "symbol": raw.get("symbol") if isinstance(raw, dict) else None,
                            "side": raw.get("entry_side") if isinstance(raw, dict) else None,
                            "tf_sec": raw.get("tf_sec") if isinstance(raw, dict) else None,
                            "plan_ts_ms": raw.get("ts_ms") if isinstance(raw, dict) else None,
                            "plan_ts_utc": iso_from_ts_ms(normalize_int(raw.get("ts_ms")) if isinstance(raw, dict) else None),
                            "actionable": False,
                            "suppressed": False,
                            "outcome_available": False,
                            "simulation_status": "invalid",
                            "limit_filled": False,
                            "fill_ts_ms": None,
                            "fill_delay_ms": None,
                            "entry_fill_price": None,
                            "exit_ts_ms": None,
                            "exit_price": None,
                            "exit_reason": None,
                            "terminal_reason": "plan_parse_error",
                            "gross_pnl_pct": None,
                            "gross_pnl_bps": None,
                            "fees_paid_pct": None,
                            "total_cost_bps": None,
                            "fees_bps": None,
                            "slippage_bps": None,
                            "net_pnl_pct": None,
                            "net_pnl_bps": None,
                            "win_loss": None,
                            "tp_hit": False,
                            "sl_hit": False,
                            "timeout_hit": False,
                            "ambiguous_intrabar": False,
                            "invalid_outcome_reason": str(exc),
                            "skipped_reason": None,
                            "join_key": None,
                        }
                    )
                    continue

                if plan.suppressed:
                    records.append(_skipped_record(plan, "suppressed_plan"))
                    continue
                if not plan.actionable:
                    records.append(_skipped_record(
                        plan, "non_actionable_plan"))
                    continue

                recorder_path = root / "data" / "recorder" / \
                    utc_date_from_ts_ms(plan.ts_ms) / \
                    f"{plan.symbol}_{plan.tf_sec}.csv"
                if not recorder_path.exists():
                    records.append(_skipped_record(plan, "missing_ohlc_file"))
                    continue

                bars = simulator._load_bars(
                    root / "data" / "recorder", utc_date_from_ts_ms(plan.ts_ms), plan.symbol, plan.tf_sec)
                if bars.empty:
                    records.append(_invalid_record(
                        plan, "invalid_or_empty_ohlc_data"))
                    continue

                result = simulator.simulate_plan(plan, bars)
                records.append(_success_record(plan, result))

    summary = build_run_summary(
        contract_audit=contract_audit,
        input_revalidation=input_revalidation,
        records=records,
        output_path=output_path,
    )
    return contract_audit, records, summary


def _dataset_join_key_counts(dataset_rows: list[dict[str, str]]) -> dict[str, Counter[str]]:
    plan_id_counts: Counter[str] = Counter()
    cycle_tier_counts: Counter[str] = Counter()
    cycle_tier_symbol_tf_counts: Counter[str] = Counter()
    for row in dataset_rows:
        plan_id = str(row.get("plan_id") or "")
        cycle_key = str(row.get("cycle_key") or "")
        tier = str(row.get("tier") or row.get("confidence_tier") or "")
        symbol = str(row.get("symbol") or "")
        tf_sec = str(row.get("tf_sec") or "")
        if plan_id:
            plan_id_counts[plan_id] += 1
        if cycle_key and tier:
            cycle_tier_counts[f"{cycle_key}::{tier}"] += 1
        if cycle_key and tier and symbol and tf_sec:
            cycle_tier_symbol_tf_counts[f"{cycle_key}::{tier}::{symbol}::{tf_sec}"] += 1
    return {
        "plan_id": plan_id_counts,
        "cycle_tier": cycle_tier_counts,
        "cycle_tier_symbol_tf": cycle_tier_symbol_tf_counts,
    }


def _canonical_outcome_defaults() -> dict[str, Any]:
    return {
        "outcome_available": False,
        "simulation_status": None,
        "limit_filled": False,
        "fill_ts_ms": None,
        "fill_delay_ms": None,
        "entry_fill_price": None,
        "exit_ts_ms": None,
        "exit_price": None,
        "exit_reason": None,
        "terminal_reason": None,
        "gross_pnl_pct": None,
        "gross_pnl_bps": None,
        "fees_paid_pct": None,
        "total_cost_bps": None,
        "fees_bps": None,
        "slippage_bps": None,
        "net_pnl_pct": None,
        "net_pnl_bps": None,
        "win_loss": None,
        "tp_hit": False,
        "sl_hit": False,
        "timeout_hit": False,
        "ambiguous_intrabar": False,
        "invalid_outcome_reason": None,
        "skipped_reason": None,
        "join_match_method": None,
        "join_anomalies": "[]",
    }


def _outcome_indexes(outcome_rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexes = {
        "plan_id": defaultdict(list),
        "cycle_tier": defaultdict(list),
        "cycle_tier_symbol_tf": defaultdict(list),
    }
    for row in outcome_rows:
        plan_id = str(row.get("plan_id") or "")
        cycle_key = str(row.get("cycle_key") or "")
        tier = str(row.get("tier") or row.get("confidence_tier") or "")
        symbol = str(row.get("symbol") or "")
        tf_sec = str(row.get("tf_sec") or "")
        if plan_id:
            indexes["plan_id"][plan_id].append(row)
        if cycle_key and tier:
            indexes["cycle_tier"][f"{cycle_key}::{tier}"].append(row)
        if cycle_key and tier and symbol and tf_sec:
            indexes["cycle_tier_symbol_tf"][f"{cycle_key}::{tier}::{symbol}::{tf_sec}"].append(
                row)
    return {name: dict(index) for name, index in indexes.items()}


def resolve_join_method(
    dataset_row: dict[str, str],
    dataset_counts: dict[str, Counter[str]],
    outcome_indexes: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[str | None, dict[str, Any] | None, list[str]]:
    anomalies: list[str] = []
    plan_id = str(dataset_row.get("plan_id") or "")
    cycle_key = str(dataset_row.get("cycle_key") or "")
    tier = str(dataset_row.get("tier")
               or dataset_row.get("confidence_tier") or "")
    symbol = str(dataset_row.get("symbol") or "")
    tf_sec = str(dataset_row.get("tf_sec") or "")
    cycle_tier_key = f"{cycle_key}::{tier}" if cycle_key and tier else ""
    cycle_tier_symbol_tf_key = f"{cycle_key}::{tier}::{symbol}::{tf_sec}" if cycle_key and tier and symbol and tf_sec else ""

    if plan_id:
        matches = outcome_indexes["plan_id"].get(plan_id, [])
        if dataset_counts["plan_id"][plan_id] > 1 and matches:
            anomalies.append("plan_id_not_unique_in_dataset")
        if len(matches) > 1:
            anomalies.append("plan_id_duplicate_in_outcomes")

    if cycle_tier_symbol_tf_key:
        matches = outcome_indexes["cycle_tier_symbol_tf"].get(
            cycle_tier_symbol_tf_key, [])
        if dataset_counts["cycle_tier_symbol_tf"][cycle_tier_symbol_tf_key] > 1 and matches:
            anomalies.append("cycle_tier_symbol_tf_not_unique_in_dataset")
        if len(matches) > 1:
            anomalies.append("cycle_tier_symbol_tf_duplicate_in_outcomes")

    if not cycle_tier_key:
        anomalies.append("missing_cycle_key_or_tier")
        return None, None, anomalies

    matches = outcome_indexes["cycle_tier"].get(cycle_tier_key, [])
    if dataset_counts["cycle_tier"][cycle_tier_key] > 1 and matches:
        anomalies.append("cycle_tier_not_unique_in_dataset")
    if len(matches) > 1:
        anomalies.append("cycle_tier_duplicate_in_outcomes")
    if dataset_counts["cycle_tier"][cycle_tier_key] == 1 and len(matches) == 1:
        return "cycle_key+tier", matches[0], anomalies

    return None, None, anomalies


def augment_dataset_with_outcomes(base_rows: list[dict[str, str]], outcome_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    dataset_counts = _dataset_join_key_counts(base_rows)
    outcome_indexes = _outcome_indexes(outcome_rows)
    augmented_rows: list[dict[str, Any]] = []
    join_method_counter: Counter[str] = Counter()
    anomaly_counter: Counter[str] = Counter()
    invalid_reason_counter: Counter[str] = Counter()
    skipped_reason_counter: Counter[str] = Counter()
    classifier_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "row_count": 0,
        "rows_with_outcome": 0,
        "simulation_success_rate": 0.0,
        "invalid_outcome_count": 0,
        "skipped_reason_counts": Counter(),
        "invalid_reason_counts": Counter(),
    })
    label_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "row_count": 0,
        "rows_with_outcome": 0,
        "simulation_success_rate": 0.0,
        "invalid_outcome_count": 0,
        "skipped_reason_counts": Counter(),
        "invalid_reason_counts": Counter(),
    })
    dimension_stats: dict[str, dict[str, dict[str, Any]]] = {
        "regime": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
        "symbol": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
        "side": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
        "tf_sec": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
        "tier": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
        "date": defaultdict(lambda: {"count": 0, "rows_with_outcome": 0, "invalid_reason_counts": Counter(), "skipped_reason_counts": Counter()}),
    }
    basic_outcome_distribution: Counter[str] = Counter()

    duplicate_outcome_key_count = sum(
        1 for matches in outcome_indexes["cycle_tier"].values() if len(matches) > 1)

    for base_row in base_rows:
        join_method, outcome_row, anomalies = resolve_join_method(
            base_row, dataset_counts, outcome_indexes)
        augmented = dict(base_row)
        augmented.update(_canonical_outcome_defaults())
        classifier = str(base_row.get("classifier_output") or "UNKNOWN")
        label = str(base_row.get("matched_surface_label") or "UNKNOWN")
        date_value = utc_date_from_ts_ms(normalize_int(base_row.get("plan_ts_ms") or base_row.get("ts_ms")) or normalize_int(outcome_row.get("plan_ts_ms")) or 0) if (
            normalize_int(base_row.get("plan_ts_ms") or base_row.get("ts_ms")) or (outcome_row and normalize_int(outcome_row.get("plan_ts_ms")))) else "UNKNOWN"

        classifier_stats[classifier]["row_count"] += 1
        label_stats[label]["row_count"] += 1
        for dim_name, dim_value in (
            ("regime", str(base_row.get("regime") or "UNKNOWN")),
            ("symbol", str(base_row.get("symbol") or "UNKNOWN")),
            ("side", str(base_row.get("side") or "UNKNOWN")),
            ("tf_sec", str(base_row.get("tf_sec") or "UNKNOWN")),
            ("tier", str(base_row.get("tier") or base_row.get(
                "confidence_tier") or "UNKNOWN")),
            ("date", date_value),
        ):
            dimension_stats[dim_name][dim_value]["count"] += 1

        if anomalies:
            for anomaly in anomalies:
                anomaly_counter[anomaly] += 1

        augmented["join_match_method"] = join_method
        augmented["join_anomalies"] = json.dumps(
            anomalies, ensure_ascii=True) if anomalies else "[]"

        if outcome_row is None:
            augmented["outcome_available"] = False
            augmented["invalid_outcome_reason"] = "missing_outcome_key_match"
            invalid_reason_counter["missing_outcome_key_match"] += 1
            classifier_stats[classifier]["invalid_outcome_count"] += 1
            classifier_stats[classifier]["invalid_reason_counts"]["missing_outcome_key_match"] += 1
            label_stats[label]["invalid_outcome_count"] += 1
            label_stats[label]["invalid_reason_counts"]["missing_outcome_key_match"] += 1
            for dim_name, dim_value in (
                ("regime", str(base_row.get("regime") or "UNKNOWN")),
                ("symbol", str(base_row.get("symbol") or "UNKNOWN")),
                ("side", str(base_row.get("side") or "UNKNOWN")),
                ("tf_sec", str(base_row.get("tf_sec") or "UNKNOWN")),
                ("tier", str(base_row.get("tier") or base_row.get(
                    "confidence_tier") or "UNKNOWN")),
                ("date", date_value),
            ):
                dimension_stats[dim_name][dim_value]["invalid_reason_counts"]["missing_outcome_key_match"] += 1
        else:
            for key, value in outcome_row.items():
                augmented[key] = value
            if outcome_row.get("outcome_available"):
                classifier_stats[classifier]["rows_with_outcome"] += 1
                label_stats[label]["rows_with_outcome"] += 1
                for dim_name, dim_value in (
                    ("regime", str(base_row.get("regime") or "UNKNOWN")),
                    ("symbol", str(base_row.get("symbol") or "UNKNOWN")),
                    ("side", str(base_row.get("side") or "UNKNOWN")),
                    ("tf_sec", str(base_row.get("tf_sec") or "UNKNOWN")),
                    ("tier", str(base_row.get("tier") or base_row.get(
                        "confidence_tier") or "UNKNOWN")),
                    ("date", date_value),
                ):
                    dimension_stats[dim_name][dim_value]["rows_with_outcome"] += 1
            if outcome_row.get("simulation_status") == "success":
                basic_outcome_distribution[outcome_row.get(
                    "terminal_reason") or "UNKNOWN"] += 1
            invalid_reason = outcome_row.get("invalid_outcome_reason")
            skipped_reason = outcome_row.get("skipped_reason")
            if invalid_reason:
                invalid_reason_counter[str(invalid_reason)] += 1
                classifier_stats[classifier]["invalid_outcome_count"] += 1
                classifier_stats[classifier]["invalid_reason_counts"][str(
                    invalid_reason)] += 1
                label_stats[label]["invalid_outcome_count"] += 1
                label_stats[label]["invalid_reason_counts"][str(
                    invalid_reason)] += 1
                for dim_name, dim_value in (
                    ("regime", str(base_row.get("regime") or "UNKNOWN")),
                    ("symbol", str(base_row.get("symbol") or "UNKNOWN")),
                    ("side", str(base_row.get("side") or "UNKNOWN")),
                    ("tf_sec", str(base_row.get("tf_sec") or "UNKNOWN")),
                    ("tier", str(base_row.get("tier") or base_row.get(
                        "confidence_tier") or "UNKNOWN")),
                    ("date", date_value),
                ):
                    dimension_stats[dim_name][dim_value]["invalid_reason_counts"][str(
                        invalid_reason)] += 1
            if skipped_reason:
                skipped_reason_counter[str(skipped_reason)] += 1
                classifier_stats[classifier]["skipped_reason_counts"][str(
                    skipped_reason)] += 1
                label_stats[label]["skipped_reason_counts"][str(
                    skipped_reason)] += 1
                for dim_name, dim_value in (
                    ("regime", str(base_row.get("regime") or "UNKNOWN")),
                    ("symbol", str(base_row.get("symbol") or "UNKNOWN")),
                    ("side", str(base_row.get("side") or "UNKNOWN")),
                    ("tf_sec", str(base_row.get("tf_sec") or "UNKNOWN")),
                    ("tier", str(base_row.get("tier") or base_row.get(
                        "confidence_tier") or "UNKNOWN")),
                    ("date", date_value),
                ):
                    dimension_stats[dim_name][dim_value]["skipped_reason_counts"][str(
                        skipped_reason)] += 1

        if join_method:
            join_method_counter[join_method] += 1
        augmented_rows.append(augmented)

    dataset_total = len(augmented_rows)
    rows_with_outcome = sum(
        1 for row in augmented_rows if bool_from_any(row.get("outcome_available")))
    rows_without_outcome = dataset_total - rows_with_outcome
    for stats in classifier_stats.values():
        stats["outcome_join_rate"] = round(
            (stats["rows_with_outcome"] / stats["row_count"]) * 100.0, 4) if stats["row_count"] else 0.0
        stats["simulation_success_rate"] = stats["outcome_join_rate"]
        stats["skipped_reason_counts"] = dict(
            sorted(stats["skipped_reason_counts"].items()))
        stats["invalid_reason_counts"] = dict(
            sorted(stats["invalid_reason_counts"].items()))
    for stats in label_stats.values():
        stats["outcome_join_rate"] = round(
            (stats["rows_with_outcome"] / stats["row_count"]) * 100.0, 4) if stats["row_count"] else 0.0
        stats["simulation_success_rate"] = stats["outcome_join_rate"]
        stats["skipped_reason_counts"] = dict(
            sorted(stats["skipped_reason_counts"].items()))
        stats["invalid_reason_counts"] = dict(
            sorted(stats["invalid_reason_counts"].items()))
    dimension_json: dict[str, Any] = {}
    for dim_name, values in dimension_stats.items():
        dimension_json[dim_name] = {}
        for dim_value, stats in sorted(values.items()):
            total = stats["count"]
            dimension_json[dim_name][dim_value] = {
                "count": total,
                "rows_with_outcome": stats["rows_with_outcome"],
                "join_rate": round((stats["rows_with_outcome"] / total) * 100.0, 4) if total else 0.0,
                "invalid_reason_counts": dict(sorted(stats["invalid_reason_counts"].items())),
                "skipped_reason_counts": dict(sorted(stats["skipped_reason_counts"].items())),
            }

    join_summary = {
        "dataset_rows_total": dataset_total,
        "rows_with_outcome": rows_with_outcome,
        "rows_without_outcome": rows_without_outcome,
        "outcome_join_rate_pct": round((rows_with_outcome / dataset_total) * 100.0, 4) if dataset_total else 0.0,
        "duplicate_outcome_key_count": duplicate_outcome_key_count,
        "missing_outcome_key_count": invalid_reason_counter.get("missing_outcome_key_match", 0),
        "many_to_one_anomalies": anomaly_counter.get("cycle_tier_not_unique_in_dataset", 0),
        "one_to_many_anomalies": anomaly_counter.get("cycle_tier_duplicate_in_outcomes", 0),
        "diagnostic_anomaly_counts": dict(sorted(anomaly_counter.items())),
        "join_method_counts": dict(sorted(join_method_counter.items())),
        "invalid_outcome_reason_counts": dict(sorted(invalid_reason_counter.items())),
        "skipped_reason_counts": dict(sorted(skipped_reason_counter.items())),
        "basic_outcome_type_distribution": dict(sorted(basic_outcome_distribution.items())),
    }
    return augmented_rows, join_summary, dict(sorted(classifier_stats.items())), dict(sorted(label_stats.items())), dimension_json


def verdict_from_join_summary(join_summary: dict[str, Any], run_summary: dict[str, Any]) -> str:
    total_rows = int(join_summary.get("dataset_rows_total", 0))
    rows_with_outcome = int(join_summary.get("rows_with_outcome", 0))
    success_rate = float(run_summary["simulation_coverage"].get(
        "simulation_success_rate_pct", 0.0))
    if total_rows == 0:
        return "AUDIT_ONLY_NO_SAFE_SIMULATION"
    if rows_with_outcome == 0:
        return "BLOCKED_LOW_OUTCOME_JOIN_RATE"
    if success_rate < 20.0:
        return "PARTIAL_OUTCOMES_NOT_READY_FOR_ANALYSIS"
    if rows_with_outcome < total_rows:
        return "OUTCOMES_COLLECTED_DATASET_AUGMENTED_WITH_RESIDUALS"
    return "OUTCOMES_COLLECTED_DATASET_AUGMENTED_AND_VALIDATED"


def render_markdown_table(rows: list[dict[str, str]], headers: list[str]) -> str:
    output = ["| " + " | ".join(headers) + " |",
              "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        output.append("| " + " | ".join(str(row.get(header, ""))
                      for header in headers) + " |")
    return "\n".join(output)


def build_markdown_report(
    *,
    contract_audit: dict[str, Any],
    run_summary: dict[str, Any],
    join_summary: dict[str, Any],
    classifier_summary: dict[str, Any],
    label_summary: dict[str, Any],
    dimension_summary: dict[str, Any],
    verdict: str,
    files_changed: list[str],
    tests_run: list[str],
) -> str:
    contract_rows = [
        {
            "Surface": row["surface"],
            "File/function/model": row["file_or_model"],
            "Finding": row["finding"],
            "Join impact": row["join_impact"],
        }
        for row in contract_audit["contract_table"]
    ]
    classifier_lines = [f"- {name}: rows={stats['row_count']}, rows_with_outcome={stats['rows_with_outcome']}, join_rate={stats['outcome_join_rate']}%, invalid={stats['invalid_outcome_count']}" for name, stats in classifier_summary.items()]
    label_lines = [f"- {name}: rows={stats['row_count']}, rows_with_outcome={stats['rows_with_outcome']}, join_rate={stats['outcome_join_rate']}%, invalid={stats['invalid_outcome_count']}" for name, stats in label_summary.items()]
    dimension_lines = []
    for dim_name in ["regime", "symbol", "side", "tf_sec", "tier", "date"]:
        values = dimension_summary.get(dim_name, {})
        top_values = list(values.items())[:8]
        dimension_lines.append(f"### {dim_name}")
        for value, stats in top_values:
            dimension_lines.append(
                f"- {value}: count={stats['count']}, rows_with_outcome={stats['rows_with_outcome']}, join_rate={stats['join_rate']}%")
    processed_shadow_rows = run_summary["simulation_coverage"].get(
        "simulation_records_total", 0)
    revalidated_shadow_rows = run_summary["input_revalidation"]["shadow_plans"].get(
        "rows", 0)
    limit_filled_count = (
        join_summary["basic_outcome_type_distribution"].get("FILLED_TP", 0)
        + join_summary["basic_outcome_type_distribution"].get("FILLED_SL", 0)
        + join_summary["basic_outcome_type_distribution"].get("FILLED_TIMEOUT", 0)
    )
    tests_section = [f"- {item}" for item in tests_run] if tests_run else [
        "- None recorded by the augmentation command."]

    lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        f"J6-S17-C1 audited the existing shadow simulator, produced read-only simulation outcome artifacts under reports/alpha_search, and augmented the J6-S17-B dataset with explicit outcome/null-reason fields.",
        "",
        "## Final Verdict",
        verdict,
        "",
        "## Scope",
        "- Contract audit of the existing shadow simulator and CLI surfaces.",
        "- Local revalidation of J6-S17-B joined dataset, shadow plans, and recorder inputs.",
        "- Read-only simulation outcome collection under reports/alpha_search.",
        "- Dataset augmentation with explicit join methods, null-preserving outcome fields, and readiness metrics.",
        "",
        "## Proven Facts",
        f"- Base dataset rows revalidated: {run_summary['input_revalidation']['base_dataset']['rows']}.",
        f"- Unique policy cycles revalidated: {run_summary['input_revalidation']['base_dataset']['unique_cycle_keys']}.",
        f"- Shadow plan rows revalidated: {run_summary['input_revalidation']['shadow_plans']['rows']}.",
        f"- Simulation records emitted: {processed_shadow_rows}.",
        f"- Simulator success count: {run_summary['simulation_coverage']['simulation_success_count']} of {run_summary['simulation_coverage']['total_shadow_plan_rows']}.",
        f"- Outcome join rate: {join_summary['outcome_join_rate_pct']}%.",
        f"- plan_id is not globally unique on current artifacts; duplicate plan_id count in dataset is {run_summary['input_revalidation']['base_dataset']['duplicate_plan_id_count']}.",
        "",
        "## Inferences",
        "- The simulator engine itself is runnable on current shadow-plan and recorder artifacts.",
        "- The existing CLI is insufficient for C1 because it writes under logs/judge_experts and does not preserve skipped rows.",
        "- cycle_key+tier is the first globally safe join key for current artifacts; plan_id alone is unsafe across timeframes.",
        "",
        "## Assumptions",
        "- UTC date folders under data/recorder are authoritative for mapping plan ts_ms to recorder files.",
        "- The simulator engine contract remains the source of truth; the wrapper only records skipped/invalid outcomes and carries missing identity fields through.",
        "- Input shadow-plan logs may still be live while the audit runs; revalidation counts and processed-record counts can drift slightly if new lines arrive during the run.",
        "",
        "## Unknowns",
        "- Whether future runtime windows will preserve richer accepted-intent inputs that allow disabled directional or price-motion gate replay for accepted rows.",
        "- Whether non-actionable tiers should be excluded upstream in C2 rather than carried forward as explicit skipped rows.",
        "",
        "## Simulator Contract Audit",
        render_markdown_table(
            contract_rows, ["Surface", "File/function/model", "Finding", "Join impact"]),
        "",
        "## Input Artifact Revalidation",
        json.dumps(run_summary["input_revalidation"],
                   indent=2, ensure_ascii=True),
        "",
        "## Simulator Execution Summary",
        json.dumps(run_summary["simulation_coverage"],
                   indent=2, ensure_ascii=True),
        "",
        "## Outcome Artifact Summary",
        json.dumps(run_summary["outcome_type_distribution"],
                   indent=2, ensure_ascii=True),
        "",
        "## Outcome Join Summary",
        json.dumps(join_summary, indent=2, ensure_ascii=True),
        "",
        "## Augmented Dataset Schema",
        "- Base J6-S17-B columns are preserved.",
        "- Added outcome fields: join_match_method, join_anomalies, simulation_status, outcome_available, fill/exit fields, PnL fields, terminal_reason, invalid_outcome_reason, skipped_reason, and event flags.",
        "- Missing outcome economics remain null when outcome evidence is absent or invalid.",
        "",
        "## Outcome Availability by Classifier Output",
        *classifier_lines,
        "",
        "## Outcome Availability by Matched Label",
        *label_lines,
        "",
        "## Outcome Availability by Regime/Symbol/Side/TF/Tier",
        *dimension_lines,
        "",
        "## Basic Outcome Type Distribution",
        f"- limit_filled_count: {limit_filled_count}",
        f"- tp_hit_count: {join_summary['basic_outcome_type_distribution'].get('FILLED_TP', 0)}",
        f"- sl_hit_count: {join_summary['basic_outcome_type_distribution'].get('FILLED_SL', 0)}",
        f"- timeout_hit_count: {join_summary['basic_outcome_type_distribution'].get('FILLED_TIMEOUT', 0) + join_summary['basic_outcome_type_distribution'].get('NOT_FILLED_TIMEOUT', 0)}",
        f"- ambiguous_intrabar_count: {run_summary['simulation_coverage']['simulation_invalid_count']}",
        f"- error_or_skipped_count: {run_summary['simulation_coverage']['simulation_error_count'] + run_summary['simulation_coverage']['simulation_skipped_count']}",
        "",
        "## Files Changed",
        *[f"- {path}" for path in files_changed],
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
        *tests_section,
        "",
        "## Residual Risks",
        "- Most rows without outcomes are explicit skipped rows because the tier is non-actionable rather than because the simulator failed.",
        "- The simulator engine reports combined fee/slippage cost only; separate fee and slippage fields remain null in canonical augmentation outputs.",
        *([f"- Input drift observed during the run: revalidated shadow rows={revalidated_shadow_rows}, processed simulation records={processed_shadow_rows}."]
          if revalidated_shadow_rows != processed_shadow_rows else []),
        "",
        "## What Remains Unproven",
        "- Final profitability, alpha quality, or promotion/advisory readiness.",
        "- Whether C2 should analyze all three tiers or only actionable tiers for hit/miss scoring.",
        "",
        "## Recommendation for J6-S17-C2",
        "- Proceed only if C2 explicitly handles non-actionable or skipped tiers as null-outcome rows rather than treating them as failed trades.",
        "- Use cycle_key+tier as the canonical cross-surface join key for this dataset slice.",
    ]
    return "\n".join(lines) + "\n"
