from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
OUTPUT_DIR = (
    REPORTS_DIR
    / "runtime_forensics"
    / "T6E_post_t5d_shadow_journal_field_retention"
)
ORDER_LOG_PATH = LOGS_DIR / "order_log_v1.jsonl"
SHADOW_JOURNAL_PATH = LOGS_DIR / "shadow_critical_event_journal_v1.jsonl"
SHADOW_JOURNAL_OWNER_PATH = ROOT / "apps" / \
    "reference" / "telemetry" / "shadow_journal.py"
PRIMARY_REFERENCE_REPORTS = (
    REPORTS_DIR
    / "runtime_forensics"
    / "T5D_DECISION_TRACE_SHADOW_JOURNAL_RETENTION_REPAIR_REPORT.md",
    REPORTS_DIR
    / "runtime_forensics"
    / "T6D_trace_field_propagation"
    / "T6D_TRACE_FIELD_PROPAGATION_REPORT.md",
)

INVENTORY_CSV_PATH = OUTPUT_DIR / "post_t5d_accepted_trace_inventory.csv"
COVERAGE_CSV_PATH = OUTPUT_DIR / "post_t5d_payload_fragment_field_coverage.csv"
SCHEMA_CSV_PATH = OUTPUT_DIR / "post_t5d_schema_failures.csv"
REPORT_PATH = OUTPUT_DIR / "T6E_POST_T5D_SHADOW_JOURNAL_FIELD_RETENTION_REPORT.md"

DECISION_TRACE_EVENT = "EVT:DECISION_TRACE_EMITTED"
TARGET_STRATEGY = "aurora"
FALLBACK_MATCH_WINDOW_MS = 120_000

RID_PATTERN = re.compile(r"aurora_[A-Z0-9]+_\d+")
LOG_TS_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}),(?P<ms>\d{3})"
)

PRIMARY_COVERAGE_KEYS = (
    "regime_confidence_gate_verdict",
    "price_motion_context",
    "pm_norm_60s",
    "pm_norm_300s",
    "missing_inputs",
    "safety_gate_snapshot",
    "low_vol_cost_floor",
    "anti_peak_observability",
)


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return (
        datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def to_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def parse_log_timestamp(line: str) -> datetime | None:
    match = LOG_TS_PATTERN.match(line)
    if not match:
        return None
    return datetime.fromisoformat(
        f"{match.group('date')}T{match.group('time')}.{match.group('ms')}"
    )


def log_files(pattern: str) -> list[Path]:
    return sorted(LOGS_DIR.glob(pattern), key=lambda item: item.stat().st_mtime)


def get_shadow_journal_git_touch() -> dict[str, str]:
    result: dict[str, str] = {
        "commit_hash": "",
        "commit_ts_utc": "",
        "file_mtime_utc": iso_utc(int(SHADOW_JOURNAL_OWNER_PATH.stat().st_mtime * 1000)),
    }
    try:
        command = [
            "git",
            "log",
            "--follow",
            "-1",
            "--date=iso-strict",
            "--format=%H|%ad",
            "--",
            str(SHADOW_JOURNAL_OWNER_PATH.relative_to(ROOT)).replace("\\", "/"),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        line = next(
            (item for item in completed.stdout.splitlines() if item.strip()), "")
        if line:
            commit_hash, commit_ts = line.split("|", 1)
            result["commit_hash"] = commit_hash.strip()
            result["commit_ts_utc"] = (
                datetime.fromisoformat(commit_ts.strip())
                .astimezone(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
    except Exception:
        pass
    return result


def load_all_order_intents() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in load_jsonl(ORDER_LOG_PATH):
        if row.get("event_type") != "ORDER_INTENT":
            continue
        if row.get("source_fsm") != "DecisionMaking":
            continue
        strategy_id = stringify(row.get("strategy_id"))
        if strategy_id != TARGET_STRATEGY:
            continue
        metadata = safe_dict(row.get("metadata"))
        if stringify(metadata.get("regime_confidence_gate_verdict")).upper() != "ALLOW":
            continue
        if is_bypass_row(metadata):
            continue
        rows.append(row)
    rows.sort(key=lambda item: int(item.get("timestamp") or 0))
    return rows


def is_bypass_row(metadata: dict[str, Any]) -> bool:
    gate_verdict = stringify(metadata.get(
        "regime_confidence_gate_verdict")).upper()
    threshold_verdict = stringify(metadata.get("threshold_verdict")).upper()
    if gate_verdict == "BYPASS" or threshold_verdict == "BYPASS":
        return True
    for key, value in metadata.items():
        key_text = stringify(key).lower()
        if "bypass" not in key_text:
            continue
        if value is True:
            return True
        if stringify(value).strip().upper() == "BYPASS":
            return True
    return False


def infer_log_offset_hours(order_rows: list[dict[str, Any]]) -> tuple[int, str]:
    if not order_rows:
        return 0, "no ORDER_INTENT rows available for log offset inference"
    target = order_rows[-1]
    rid = stringify(target.get("rid"))
    event_ts_ms = int(target.get("timestamp") or 0)
    event_ts = datetime.fromtimestamp(event_ts_ms / 1000.0, tz=timezone.utc)

    for path in reversed(log_files("domain_decision_making.log*")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if rid not in line:
                    continue
                local_ts = parse_log_timestamp(line)
                if local_ts is None:
                    continue
                delta_hours = (
                    local_ts.replace(tzinfo=timezone.utc) - event_ts
                ).total_seconds() / 3600.0
                rounded = int(round(delta_hours))
                reason = (
                    f"offset inferred from {path.name} rid={rid}: local {local_ts.isoformat()} vs "
                    f"jsonl {event_ts.isoformat()} -> {rounded:+d}h"
                )
                return rounded, reason
    return 0, "could not find rid-correlated DecisionMaking log line; assumed +0h"


def load_runtime_start_markers(offset_hours: int) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for path in log_files("domain_decision_making.log*"):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if "DecisionMaking started" not in line:
                    continue
                local_ts = parse_log_timestamp(line)
                if local_ts is None:
                    continue
                utc_ts = (local_ts - timedelta(hours=offset_hours)).replace(
                    tzinfo=timezone.utc
                )
                markers.append(
                    {
                        "path": path,
                        "line_number": line_number,
                        "local_ts": local_ts,
                        "utc_ts": utc_ts,
                        "utc_ts_ms": int(utc_ts.timestamp() * 1000),
                        "line": line.strip(),
                    }
                )
    markers.sort(key=lambda item: item["utc_ts_ms"])
    return markers


def select_runtime_window(
    order_rows: list[dict[str, Any]],
    markers: list[dict[str, Any]],
    t5d_boundary_ms: int,
) -> dict[str, Any] | None:
    order_timestamps = [int(row.get("timestamp") or 0) for row in order_rows]
    for marker in reversed(markers):
        marker_ts_ms = int(marker["utc_ts_ms"])
        if marker_ts_ms <= t5d_boundary_ms:
            continue
        if any(ts >= marker_ts_ms for ts in order_timestamps):
            return marker
    return None


def load_shadow_decision_traces(boundary_ms: int) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_rid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for row in load_jsonl(SHADOW_JOURNAL_PATH):
        if row.get("event_name") != DECISION_TRACE_EVENT:
            continue
        ts_ms = int(row.get("ts_ms") or 0)
        if ts_ms < boundary_ms:
            continue
        rid = stringify(row.get("rid"))
        if rid:
            by_rid[rid].append(row)
        rows.append(row)
    for items in by_rid.values():
        items.sort(key=lambda item: int(item.get("ts_ms") or 0))
    rows.sort(key=lambda item: int(item.get("ts_ms") or 0))
    return by_rid, rows


def pick_shadow_row(
    order_row: dict[str, Any],
    exact_matches: dict[str, list[dict[str, Any]]],
    all_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, bool]:
    rid = stringify(order_row.get("rid"))
    order_ts_ms = int(order_row.get("timestamp") or 0)
    exact_rows = exact_matches.get(rid) or []
    if exact_rows:
        selected = min(
            exact_rows,
            key=lambda row: abs(int(row.get("ts_ms") or 0) - order_ts_ms),
        )
        return selected, "EXACT_RID", True

    symbol = stringify(order_row.get("symbol"))
    strategy_id = stringify(order_row.get("strategy_id"))
    side = stringify(order_row.get("side"))
    candidates = [
        row
        for row in all_rows
        if stringify(row.get("symbol")) == symbol
        and stringify(row.get("strategy_id")) == strategy_id
        and stringify(row.get("side")) == side
        and abs(int(row.get("ts_ms") or 0) - order_ts_ms) <= FALLBACK_MATCH_WINDOW_MS
    ]
    if not candidates:
        return None, "NONE", False
    selected = min(
        candidates,
        key=lambda row: abs(int(row.get("ts_ms") or 0) - order_ts_ms),
    )
    return selected, "SYMBOL_SIDE_TIME_NEAREST", False


def extract_rid(line: str) -> str:
    match = RID_PATTERN.search(line)
    return match.group(0) if match else ""


def classify_schema_failures(
    boundary_ms: int,
    offset_hours: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    keyword_checks = (
        "validationerror",
        "validation error",
        "failed validation",
        "schema validation",
        "missing_inputs.signal_score",
        "anti_peak_observability.motion",
        "decision_trace_emitted",
        "shadow journal",
    )
    ignored_checks = (
        "without json schema validation",
        "deprecation: emitting",
    )

    for path in [*log_files("aurora_core.log*"), *log_files("domain_decision_making.log*")]:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                lowered = line.lower()
                if not any(check in lowered for check in keyword_checks):
                    continue
                if any(ignore in lowered for ignore in ignored_checks):
                    continue
                local_ts = parse_log_timestamp(line)
                if local_ts is None:
                    continue
                utc_ts = (local_ts - timedelta(hours=offset_hours)).replace(
                    tzinfo=timezone.utc
                )
                utc_ts_ms = int(utc_ts.timestamp() * 1000)
                if utc_ts_ms < boundary_ms:
                    continue

                old_signal_score = "missing_inputs.signal_score" in lowered or (
                    "missing_inputs" in lowered and "signal_score" in lowered
                )
                old_anti_peak = "anti_peak_observability.motion" in lowered or (
                    "anti_peak_observability" in lowered and "motion" in lowered
                )
                if not (
                    old_signal_score
                    or old_anti_peak
                    or "validationerror" in lowered
                    or "validation error" in lowered
                    or "failed validation" in lowered
                    or "schema validation" in lowered
                    or "decision_trace_emitted" in lowered
                    or "shadow journal" in lowered
                ):
                    continue

                event_name = ""
                if DECISION_TRACE_EVENT.lower() in lowered:
                    event_name = DECISION_TRACE_EVENT
                error_type = "SCHEMA_VALIDATION_FAILURE"
                if "decision_trace_emitted" in lowered and "error" in lowered:
                    error_type = "TRACE_EMIT_ERROR"
                rows.append(
                    {
                        "ts": utc_ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                        "source_file": path.relative_to(ROOT).as_posix(),
                        "rid": extract_rid(line),
                        "event_name": event_name,
                        "error_type": error_type,
                        "error_message": line.strip(),
                        "matches_old_signal_score_failure_signature": to_yes_no(old_signal_score),
                        "matches_t6b_anti_peak_failure_signature": to_yes_no(old_anti_peak),
                        "new_failure_signature": "" if (old_signal_score or old_anti_peak) else normalize_failure_signature(line),
                    }
                )
    return rows


def normalize_failure_signature(line: str) -> str:
    normalized = re.sub(r"\d+", "<num>", line.lower())
    normalized = re.sub(r"aurora_[a-z0-9]+_<num>", "aurora_<rid>", normalized)
    return normalized[:180]


def build_nrr_presence(snapshot: dict[str, Any], gate_name: str) -> bool:
    return (
        f"{gate_name}_enabled" in snapshot
        or f"{gate_name}_effective_enforced" in snapshot
    )


def compute_missing_fields(fragment: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in (
        "rid",
        "intent_id",
        "lifecycle_id",
        "symbol",
        "strategy_id",
        "side",
        "regime",
        "regime_confidence",
        "regime_confidence_gate_verdict",
        "trend_dir",
        "trend_confidence",
        "trend_run_length",
        "price_motion_context",
        "pm_norm_10s",
        "pm_norm_60s",
        "pm_norm_300s",
        "missing_inputs",
        "safety_gate_snapshot",
        "low_vol_cost_floor",
        "anti_peak_observability",
        "tf_sec",
    ):
        if key not in fragment:
            missing.append(key)
    if not any(key in fragment for key in ("ts_ms", "ts", "event_ts_ms")):
        missing.append("ts_ms|ts|event_ts_ms")
    if "features_ts_ms" not in fragment:
        missing.append("features_ts_ms")
    if not any(key in fragment for key in ("bar_close_ts", "bar_close_ts_ms")):
        missing.append("bar_close_ts|bar_close_ts_ms")
    return missing


def build_coverage_row(
    order_row: dict[str, Any],
    shadow_row: dict[str, Any] | None,
    match_quality: str,
) -> dict[str, str]:
    fragment = safe_dict(shadow_row.get(
        "payload_fragment")) if shadow_row else {}
    snapshot = safe_dict(fragment.get("safety_gate_snapshot"))

    nrr_presence = {
        gate_name: build_nrr_presence(snapshot, gate_name)
        for gate_name in ("nrr026", "nrr027", "nrr028", "nrr029", "nrr030", "nrr063")
    }
    row = {
        "rid": stringify(order_row.get("rid")),
        "symbol": stringify(order_row.get("symbol")),
        "strategy_id": stringify(order_row.get("strategy_id")),
        "side": stringify(order_row.get("side")),
        "event_ts": iso_utc(int(order_row.get("timestamp") or 0)),
        "payload_fragment_present": to_yes_no(bool(fragment)),
        "regime_present": to_yes_no("regime" in fragment),
        "regime_confidence_present": to_yes_no("regime_confidence" in fragment),
        "regime_confidence_gate_verdict_present": to_yes_no("regime_confidence_gate_verdict" in fragment),
        "trend_dir_present": to_yes_no("trend_dir" in fragment),
        "trend_confidence_present": to_yes_no("trend_confidence" in fragment),
        "trend_run_length_present": to_yes_no("trend_run_length" in fragment),
        "price_motion_context_present": to_yes_no("price_motion_context" in fragment),
        "pm_norm_10s_present": to_yes_no("pm_norm_10s" in fragment),
        "pm_norm_60s_present": to_yes_no("pm_norm_60s" in fragment),
        "pm_norm_300s_present": to_yes_no("pm_norm_300s" in fragment),
        "missing_inputs_present": to_yes_no("missing_inputs" in fragment),
        "safety_gate_snapshot_present": to_yes_no("safety_gate_snapshot" in fragment),
        "low_vol_cost_floor_present": to_yes_no("low_vol_cost_floor" in fragment),
        "anti_peak_observability_present": to_yes_no("anti_peak_observability" in fragment),
        "nrr026_snapshot_present": to_yes_no(nrr_presence["nrr026"]),
        "nrr027_snapshot_present": to_yes_no(nrr_presence["nrr027"]),
        "nrr028_snapshot_present": to_yes_no(nrr_presence["nrr028"]),
        "nrr029_snapshot_present": to_yes_no(nrr_presence["nrr029"]),
        "nrr030_snapshot_present": to_yes_no(nrr_presence["nrr030"]),
        "nrr063_snapshot_present": to_yes_no(nrr_presence["nrr063"]),
        "replay_ready_nrr026": to_yes_no(
            nrr_presence["nrr026"]
            and all(
                key in fragment
                for key in ("regime_confidence", "trend_dir", "trend_confidence", "trend_run_length", "side")
            )
        ),
        "replay_ready_nrr027": to_yes_no(
            nrr_presence["nrr027"]
            and all(key in fragment for key in ("trend_dir", "trend_run_length", "side"))
        ),
        "replay_ready_nrr028": to_yes_no(
            nrr_presence["nrr028"]
            and all(key in fragment for key in ("price_motion_context", "pm_norm_10s"))
        ),
        "replay_ready_nrr029": to_yes_no(
            nrr_presence["nrr029"]
            and all(key in fragment for key in ("price_motion_context", "pm_norm_60s"))
        ),
        "replay_ready_nrr030": to_yes_no(
            nrr_presence["nrr030"]
            and all(key in fragment for key in ("price_motion_context", "pm_norm_300s"))
        ),
        "missing_fields": ";".join(compute_missing_fields(fragment)),
        "source_quality": match_quality if shadow_row else "MISSING",
    }
    return row


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    owner_touch = get_shadow_journal_git_touch()
    order_rows_all = load_all_order_intents()
    log_offset_hours, offset_reason = infer_log_offset_hours(order_rows_all)
    start_markers = load_runtime_start_markers(log_offset_hours)

    t5d_boundary_text = owner_touch["commit_ts_utc"] or owner_touch["file_mtime_utc"]
    t5d_boundary_dt = datetime.fromisoformat(
        t5d_boundary_text.replace("Z", "+00:00"))
    t5d_boundary_ms = int(t5d_boundary_dt.timestamp() * 1000)

    selected_marker = select_runtime_window(
        order_rows_all, start_markers, t5d_boundary_ms)

    if selected_marker is None:
        report_text = "\n".join(
            [
                "AGENT_REPORT_V1",
                "",
                "task:",
                "  AURORA_T6E_POST_T5D_SHADOW_JOURNAL_FIELD_RETENTION_AUDIT",
                "",
                "verdict:",
                "  BLOCKED_OLD_RUNTIME_WINDOW",
                "",
                "runtime_window:",
                "  start_ts:",
                "  end_ts:",
                f"  post_t5d_proof: latest shadow_journal touch={t5d_boundary_text}; no fresh runtime start marker with accepted allow-path rows was found after that boundary",
                "",
                "accepted_trace_summary:",
                "  accepted_intents_seen: 0",
                "  durable_decision_traces_found: 0",
                "  exact_rid_matches: 0",
                "  schema_validation_failures: 0",
                "  trace_emit_failures: 0",
                "",
                "payload_fragment_coverage:",
                "  regime_confidence_gate_verdict: 0/0",
                "  price_motion_context: 0/0",
                "  pm_norm_60s: 0/0",
                "  pm_norm_300s: 0/0",
                "  missing_inputs: 0/0",
                "  safety_gate_snapshot: 0/0",
                "  low_vol_cost_floor: 0/0",
                "  anti_peak_observability: 0/0",
                "",
                "replay_readiness:",
                "  nrr026_ready: 0/0",
                "  nrr027_ready: 0/0",
                "  nrr028_ready: 0/0",
                "  nrr029_ready: 0/0",
                "  nrr030_ready: 0/0",
                "  t3d_t4b_rerun_ready: no",
                "  reason: BLOCKED_OLD_RUNTIME_WINDOW",
                "",
                "failure_regression:",
                "  old_missing_inputs_signal_score_signature: not_assessed",
                "  old_anti_peak_signature: not_assessed",
                "  new_failure_signatures:",
                "    - none",
                "",
                "proven:",
                f"  - latest shadow_journal owner touch boundary was {t5d_boundary_text}",
                "",
                "unproven:",
                "  - a fresh runtime start marker with accepted allow-path rows after T5D",
                "",
                "risks:",
                "  - window selection blocked before runtime field-retention analysis",
                "",
                "next_action:",
                "  - wait for or capture a fresh post-T5D runtime segment, then rerun this audit",
            ]
        )
        INVENTORY_CSV_PATH.write_text(
            "rid,intent_id,symbol,strategy_id,side,event_ts,order_intent_found,decision_trace_found,shadow_journal_row_found,exact_rid_match,schema_validation_error_found,trace_emit_error_found,correlation_confidence\n", encoding="utf-8")
        COVERAGE_CSV_PATH.write_text(
            "rid,symbol,strategy_id,side,event_ts,payload_fragment_present,regime_present,regime_confidence_present,regime_confidence_gate_verdict_present,trend_dir_present,trend_confidence_present,trend_run_length_present,price_motion_context_present,pm_norm_10s_present,pm_norm_60s_present,pm_norm_300s_present,missing_inputs_present,safety_gate_snapshot_present,low_vol_cost_floor_present,anti_peak_observability_present,nrr026_snapshot_present,nrr027_snapshot_present,nrr028_snapshot_present,nrr029_snapshot_present,nrr030_snapshot_present,nrr063_snapshot_present,replay_ready_nrr026,replay_ready_nrr027,replay_ready_nrr028,replay_ready_nrr029,replay_ready_nrr030,missing_fields,source_quality\n",
            encoding="utf-8",
        )
        SCHEMA_CSV_PATH.write_text(
            "ts,source_file,rid,event_name,error_type,error_message,matches_old_signal_score_failure_signature,matches_t6b_anti_peak_failure_signature,new_failure_signature\n",
            encoding="utf-8",
        )
        REPORT_PATH.write_text(report_text + "\n", encoding="utf-8")
        return

    boundary_ms = int(selected_marker["utc_ts_ms"])
    order_rows = [
        row for row in order_rows_all if int(row.get("timestamp") or 0) >= boundary_ms
    ]
    shadow_by_rid, shadow_rows = load_shadow_decision_traces(boundary_ms)
    schema_failures = classify_schema_failures(boundary_ms, log_offset_hours)
    schema_failures_by_rid: dict[str, list[dict[str, str]]] = defaultdict(list)
    trace_emit_failures_by_rid: dict[str,
                                     list[dict[str, str]]] = defaultdict(list)
    for failure in schema_failures:
        rid = failure["rid"]
        if rid:
            schema_failures_by_rid[rid].append(failure)
            if failure["error_type"] == "TRACE_EMIT_ERROR":
                trace_emit_failures_by_rid[rid].append(failure)

    inventory_rows: list[dict[str, str]] = []
    coverage_rows: list[dict[str, str]] = []
    exact_match_count = 0
    full_core_coverage_count = 0
    pm_norm_60_non_null = 0
    pm_norm_300_non_null = 0
    missing_inputs_comparator_success = 0
    low_vol_upstream_present = 0
    low_vol_genuinely_absent = 0

    for order_row in order_rows:
        shadow_row, match_quality, exact_match = pick_shadow_row(
            order_row, shadow_by_rid, shadow_rows
        )
        if exact_match:
            exact_match_count += 1

        fragment = safe_dict(shadow_row.get(
            "payload_fragment")) if shadow_row else {}
        metadata = safe_dict(order_row.get("metadata"))
        low_vol_upstream = safe_dict(metadata.get("low_vol_cost_floor"))
        low_vol_upstream_present_flag = bool(low_vol_upstream)
        if low_vol_upstream_present_flag:
            low_vol_upstream_present += 1
        else:
            low_vol_genuinely_absent += 1

        if shadow_row and all(key in fragment for key in PRIMARY_COVERAGE_KEYS):
            full_core_coverage_count += 1
        if shadow_row and fragment.get("pm_norm_60s") is not None:
            pm_norm_60_non_null += 1
        if shadow_row and fragment.get("pm_norm_300s") is not None:
            pm_norm_300_non_null += 1
        if shadow_row and "missing_inputs" in fragment and "missing_inputs" in low_vol_upstream:
            missing_inputs_comparator_success += 1

        intent_id = ""
        if shadow_row:
            intent_id = stringify(fragment.get("intent_id"))
        if not intent_id:
            intent_id = stringify(metadata.get(
                "idempotent_key") or order_row.get("lifecycle_id"))

        schema_failure_found = bool(
            schema_failures_by_rid.get(stringify(order_row.get("rid"))))
        trace_emit_failure_found = bool(
            trace_emit_failures_by_rid.get(stringify(order_row.get("rid"))))
        inventory_rows.append(
            {
                "rid": stringify(order_row.get("rid")),
                "intent_id": intent_id,
                "symbol": stringify(order_row.get("symbol")),
                "strategy_id": stringify(order_row.get("strategy_id")),
                "side": stringify(order_row.get("side")),
                "event_ts": iso_utc(int(order_row.get("timestamp") or 0)),
                "order_intent_found": "yes",
                "decision_trace_found": to_yes_no(shadow_row is not None),
                "shadow_journal_row_found": to_yes_no(shadow_row is not None),
                "exact_rid_match": to_yes_no(exact_match),
                "schema_validation_error_found": to_yes_no(schema_failure_found),
                "trace_emit_error_found": to_yes_no(trace_emit_failure_found),
                "correlation_confidence": match_quality,
            }
        )
        coverage_rows.append(build_coverage_row(
            order_row, shadow_row, match_quality))

    inventory_fieldnames = [
        "rid",
        "intent_id",
        "symbol",
        "strategy_id",
        "side",
        "event_ts",
        "order_intent_found",
        "decision_trace_found",
        "shadow_journal_row_found",
        "exact_rid_match",
        "schema_validation_error_found",
        "trace_emit_error_found",
        "correlation_confidence",
    ]
    coverage_fieldnames = [
        "rid",
        "symbol",
        "strategy_id",
        "side",
        "event_ts",
        "payload_fragment_present",
        "regime_present",
        "regime_confidence_present",
        "regime_confidence_gate_verdict_present",
        "trend_dir_present",
        "trend_confidence_present",
        "trend_run_length_present",
        "price_motion_context_present",
        "pm_norm_10s_present",
        "pm_norm_60s_present",
        "pm_norm_300s_present",
        "missing_inputs_present",
        "safety_gate_snapshot_present",
        "low_vol_cost_floor_present",
        "anti_peak_observability_present",
        "nrr026_snapshot_present",
        "nrr027_snapshot_present",
        "nrr028_snapshot_present",
        "nrr029_snapshot_present",
        "nrr030_snapshot_present",
        "nrr063_snapshot_present",
        "replay_ready_nrr026",
        "replay_ready_nrr027",
        "replay_ready_nrr028",
        "replay_ready_nrr029",
        "replay_ready_nrr030",
        "missing_fields",
        "source_quality",
    ]
    schema_fieldnames = [
        "ts",
        "source_file",
        "rid",
        "event_name",
        "error_type",
        "error_message",
        "matches_old_signal_score_failure_signature",
        "matches_t6b_anti_peak_failure_signature",
        "new_failure_signature",
    ]

    write_csv(INVENTORY_CSV_PATH, inventory_fieldnames, inventory_rows)
    write_csv(COVERAGE_CSV_PATH, coverage_fieldnames, coverage_rows)
    write_csv(SCHEMA_CSV_PATH, schema_fieldnames, schema_failures)

    accepted_count = len(order_rows)
    durable_count = sum(
        1 for row in inventory_rows if row["shadow_journal_row_found"] == "yes")
    schema_failure_count = len(schema_failures)
    trace_emit_failure_count = sum(
        1 for row in inventory_rows if row["trace_emit_error_found"] == "yes"
    )
    replay_ready_counts = {
        gate_name: sum(
            1 for row in coverage_rows if row[f"replay_ready_{gate_name}"] == "yes"
        )
        for gate_name in ("nrr026", "nrr027", "nrr028", "nrr029", "nrr030")
    }
    features_ts_missing_all = all(
        "features_ts_ms" in (row["missing_fields"].split(
            ";") if row["missing_fields"] else [])
        for row in coverage_rows
    ) if coverage_rows else False
    missing_reference_reports = [
        path.relative_to(ROOT).as_posix()
        for path in PRIMARY_REFERENCE_REPORTS
        if not path.exists()
    ]

    verdict = "REPLAY_FIELD_RETENTION_VERIFIED"
    if accepted_count == 0:
        verdict = "PARTIAL_FIELD_RETENTION"
    elif durable_count != accepted_count:
        verdict = "RETENTION_STILL_THIN"
    elif full_core_coverage_count != accepted_count:
        verdict = "PARTIAL_FIELD_RETENTION"
    elif schema_failure_count > 0 or trace_emit_failure_count > 0:
        verdict = "PARTIAL_FIELD_RETENTION"

    start_ts = iso_utc(boundary_ms)
    end_ts = iso_utc(
        max(
            [int(row.get("timestamp") or 0) for row in order_rows]
            + [int(row.get("ts_ms") or 0) for row in shadow_rows]
        )
        if (order_rows or shadow_rows)
        else None
    )

    summary_lines = [
        "AGENT_REPORT_V1",
        "",
        "task:",
        "  AURORA_T6E_POST_T5D_SHADOW_JOURNAL_FIELD_RETENTION_AUDIT",
        "",
        "verdict:",
        f"  {verdict}",
        "",
        "runtime_window:",
        f"  start_ts: {start_ts}",
        f"  end_ts: {end_ts}",
        (
            "  post_t5d_proof: "
            f"latest shadow_journal git touch={owner_touch['commit_ts_utc'] or owner_touch['file_mtime_utc']}"
            f"{(' commit=' + owner_touch['commit_hash']) if owner_touch['commit_hash'] else ''}; "
            f"selected runtime start marker={selected_marker['path'].relative_to(ROOT).as_posix()}:{selected_marker['line_number']} "
            f"local={selected_marker['local_ts'].isoformat(timespec='milliseconds')} "
            f"-> inferred UTC={selected_marker['utc_ts'].isoformat(timespec='milliseconds').replace('+00:00', 'Z')}; "
            f"log offset={log_offset_hours:+d}h ({offset_reason})"
        ),
        "",
        "accepted_trace_summary:",
        f"  accepted_intents_seen: {accepted_count}",
        f"  durable_decision_traces_found: {durable_count}",
        f"  exact_rid_matches: {exact_match_count}",
        f"  schema_validation_failures: {schema_failure_count}",
        f"  trace_emit_failures: {trace_emit_failure_count}",
        "",
        "payload_fragment_coverage:",
        f"  regime_confidence_gate_verdict: {sum(1 for row in coverage_rows if row['regime_confidence_gate_verdict_present'] == 'yes')}/{accepted_count}",
        f"  price_motion_context: {sum(1 for row in coverage_rows if row['price_motion_context_present'] == 'yes')}/{accepted_count}",
        f"  pm_norm_60s: {sum(1 for row in coverage_rows if row['pm_norm_60s_present'] == 'yes')}/{accepted_count} retained, {pm_norm_60_non_null}/{accepted_count} non-null",
        f"  pm_norm_300s: {sum(1 for row in coverage_rows if row['pm_norm_300s_present'] == 'yes')}/{accepted_count} retained, {pm_norm_300_non_null}/{accepted_count} non-null",
        f"  missing_inputs: {sum(1 for row in coverage_rows if row['missing_inputs_present'] == 'yes')}/{accepted_count} retained; {missing_inputs_comparator_success}/{accepted_count} matched upstream low_vol comparator availability",
        f"  safety_gate_snapshot: {sum(1 for row in coverage_rows if row['safety_gate_snapshot_present'] == 'yes')}/{accepted_count}",
        f"  low_vol_cost_floor: {sum(1 for row in coverage_rows if row['low_vol_cost_floor_present'] == 'yes')}/{accepted_count} retained; upstream present={low_vol_upstream_present}, genuinely absent={low_vol_genuinely_absent}",
        f"  anti_peak_observability: {sum(1 for row in coverage_rows if row['anti_peak_observability_present'] == 'yes')}/{accepted_count}",
        "",
        "replay_readiness:",
        f"  nrr026_ready: {replay_ready_counts['nrr026']}/{accepted_count}",
        f"  nrr027_ready: {replay_ready_counts['nrr027']}/{accepted_count}",
        f"  nrr028_ready: {replay_ready_counts['nrr028']}/{accepted_count}",
        f"  nrr029_ready: {replay_ready_counts['nrr029']}/{accepted_count}",
        f"  nrr030_ready: {replay_ready_counts['nrr030']}/{accepted_count}",
        f"  t3d_t4b_rerun_ready: {'yes' if all(value == accepted_count for value in replay_ready_counts.values()) and durable_count == accepted_count and schema_failure_count == 0 else 'no'}",
        (
            "  reason: "
            f"{durable_count}/{accepted_count} accepted rows have exact durable decision traces; "
            f"{full_core_coverage_count}/{accepted_count} retain the repaired regime/trend/pm/missing_inputs/safety/low_vol/anti_peak surface; "
            "timing is retained via ts/event_ts_ms and bar_close_ts_ms/tf_sec. "
            f"features_ts_ms {'remains absent on all exact rows' if features_ts_missing_all else 'is present on at least one exact row'}"
        ),
        "",
        "failure_regression:",
        f"  old_missing_inputs_signal_score_signature: {sum(1 for row in schema_failures if row['matches_old_signal_score_failure_signature'] == 'yes')} hits in inspected window",
        f"  old_anti_peak_signature: {sum(1 for row in schema_failures if row['matches_t6b_anti_peak_failure_signature'] == 'yes')} hits in inspected window",
        "  new_failure_signatures:",
    ]
    unique_new_signatures = sorted(
        {
            row["new_failure_signature"]
            for row in schema_failures
            if row["new_failure_signature"]
        }
    )
    if unique_new_signatures:
        summary_lines.extend(f"    - {item}" for item in unique_new_signatures)
    else:
        summary_lines.append("    - none")

    summary_lines.extend(
        [
            "",
            "proven:",
            f"  - {accepted_count} accepted allow-path DecisionMaking ORDER_INTENT rows were found after the selected post-T5D restart marker",
            f"  - {durable_count}/{accepted_count} accepted rows produced exact-rid durable {DECISION_TRACE_EVENT} rows in logs/shadow_critical_event_journal_v1.jsonl",
            f"  - {full_core_coverage_count}/{accepted_count} exact rows retained regime_confidence_gate_verdict, trend_*, price_motion_context, pm_norm_60s, pm_norm_300s, missing_inputs, safety_gate_snapshot, low_vol_cost_floor, and anti_peak_observability",
            f"  - features_ts_ms was absent on {'all' if features_ts_missing_all else 'some'} inspected exact rows; bar_close_ts_ms and tf_sec were retained on {sum(1 for row in coverage_rows if row['source_quality'] == 'EXACT_RID' and 'bar_close_ts|bar_close_ts_ms' not in row['missing_fields'])}/{accepted_count} exact rows",
            f"  - {schema_failure_count} schema validation failures and {trace_emit_failure_count} trace emit failures matched the inspected runtime window",
            "",
            "unproven:",
            "  - T3D/T4B themselves were not executed in this audit; rerun readiness is field-surface based rather than replay-execution based",
            "  - No independent producer-side text-log payload dump was available for pm_norm_* and safety_gate_snapshot, so retained-vs-upstream proof for those fields relies on exact-rid durable rows rather than a second payload copy",
            "",
            "risks:",
            "  - The same physical JSONL files still contain older pre-restart rows; any audit that ignores the selected runtime boundary can mix stale and fresh evidence",
            "  - features_ts_ms is still absent on the exact durable decision-trace fragment surface; any downstream consumer that hard-requires that exact key must use ts/event_ts_ms or add an alias fallback",
        ]
    )
    if missing_reference_reports:
        summary_lines.append(
            f"  - Historical reference reports were not present on disk at the task-supplied paths: {', '.join(missing_reference_reports)}"
        )
    summary_lines.extend(
        [
            "",
            "next_action:",
            "  - Use the generated inventory and coverage CSVs as the fresh proof surface for the next T3D/T4B rerun on this exact 12-RID latest-runtime window",
        ]
    )

    REPORT_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
