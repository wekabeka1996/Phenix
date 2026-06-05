#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REPORT_NAME = "AURORA_TIMER_GOVERNANCE_T5F_POST_FIX_MONITOR_REPORT.md"
ORDER_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5F_ORDER_LIFECYCLES.csv"
WINDOW_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5F_WINDOW_SUMMARY.csv"
FLAGS_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5F_REGRESSION_FLAGS.csv"
CASEBOOK_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5F_REGRESSION_CASEBOOK.csv"
DEF_REPORT_NAME = "DEF_PARTIAL_FILL_OVERRIDE_REARM_REPORT.md"
EXPECTED_GLOBAL_WATCHDOG_TTL_MS = 1800000
EXPECTED_PER_ORDER_OVERRIDE_MS = 1200000
TIMEOUT_TOLERANCE_MS = 120000
WINDOW_MARKER_GAP_MS = 300000
DISCOVERY_MARGIN_MS = 24 * 3600000
MIN_RUNTIME_HOURS = 24.0
MIN_POST_FIX_ORDER_PLACED = 10
PREFERRED_PARTIAL_FILL_POWER = 3
TARGET_JSON_PREFIXES = (
    "order_log_v1.jsonl",
    "trade_lifecycle.jsonl",
    "shadow_critical_event_journal_v1.jsonl",
)
TARGET_TEXT_PREFIXES = (
    "aurora_core.log",
    "domain_execution_position.log",
    "event_chain.log",
    "order_guardian.log",
)
PATCH_WRAPPER_PATHS = (
    "apps/reference/domains/execution_position/watchdog.py",
    "apps/reference/domains/execution_position/event_handlers.py",
)
PATCH_OWNER_PATHS = (
    "apps/reference/domains/execution_position/adapters/watchdog.py",
    "apps/reference/domains/execution_position/orchestration/event_handlers.py",
)


def load_t5d_module():
    module_path = Path(__file__).with_name("t5d_gate_rerun_analysis.py")
    spec = importlib.util.spec_from_file_location(
        "t5d_gate_rerun_analysis", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T5D = load_t5d_module()


@dataclass
class FlagRow:
    flag_id: str
    flag_type: str
    severity: str
    status: str
    case_id: str
    symbol: str
    strategy_id: str
    source_fsm: str
    order_key: str
    order_id: str
    client_order_id: str
    rid: str
    window_id: str
    placed_ts_iso: str
    partial_fill_ts_iso: str
    terminal_ts_iso: str
    observed_value: str
    expected_value: str
    evidence: str
    notes: str


def stat_mtime_ms(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(path.stat().st_mtime * 1000)


def git_last_commit_ms(repo_root: Path, paths: tuple[str, ...]) -> int | None:
    if not paths:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-n", "1", "--format=%ct", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value:
        return None
    seconds = T5D.safe_int(value)
    if seconds is None:
        return None
    return seconds * 1000


def discover_json_files(repo_root: Path, boundary_hint_ms: int) -> list[Path]:
    files: list[Path] = []
    cutoff_ms = max(boundary_hint_ms - DISCOVERY_MARGIN_MS, 0)
    for base in (repo_root / "logs", repo_root / "logs" / "frozen", repo_root / "frozen"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if not path.name.startswith(TARGET_JSON_PREFIXES):
                continue
            mtime_ms = stat_mtime_ms(path)
            if mtime_ms is not None and mtime_ms < cutoff_ms:
                continue
            files.append(path)
    deduped: list[Path] = []
    seen = set()
    for path in sorted(files):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def discover_text_files(repo_root: Path, boundary_hint_ms: int) -> list[Path]:
    files: list[Path] = []
    cutoff_ms = max(boundary_hint_ms - DISCOVERY_MARGIN_MS, 0)
    for base in (repo_root / "logs", repo_root / "logs" / "frozen", repo_root / "frozen"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if not path.name.startswith(TARGET_TEXT_PREFIXES):
                continue
            mtime_ms = stat_mtime_ms(path)
            if mtime_ms is not None and mtime_ms < cutoff_ms:
                continue
            files.append(path)
    deduped: list[Path] = []
    seen = set()
    for path in sorted(files):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def csv_value(value):
    if value is None:
        return ""
    return value


def add_dist_fields(row: dict, prefix: str, values: list[int | None]):
    summary = T5D.dist_summary(values)
    row[f"{prefix}_count"] = summary["count"]
    row[f"{prefix}_min"] = csv_value(
        int(summary["min"]) if summary["min"] is not None else None)
    row[f"{prefix}_p50"] = csv_value(
        int(summary["p50"]) if summary["p50"] is not None else None)
    row[f"{prefix}_p75"] = csv_value(
        int(summary["p75"]) if summary["p75"] is not None else None)
    row[f"{prefix}_p90"] = csv_value(
        int(summary["p90"]) if summary["p90"] is not None else None)
    row[f"{prefix}_p95"] = csv_value(
        int(summary["p95"]) if summary["p95"] is not None else None)
    row[f"{prefix}_p99"] = csv_value(
        int(summary["p99"]) if summary["p99"] is not None else None)
    row[f"{prefix}_max"] = csv_value(
        int(summary["max"]) if summary["max"] is not None else None)


def join_list(values: list[str]) -> str:
    clean = [value for value in values if value]
    return ", ".join(clean) if clean else "none"


def summarize_scanned_surfaces(paths: set[str]) -> list[str]:
    buckets = set()
    for rel in paths:
        name = rel.split("/")[-1]
        if name.startswith("order_log_v1.jsonl"):
            buckets.add("logs/order_log_v1.jsonl*")
        elif name.startswith("trade_lifecycle.jsonl"):
            buckets.add("logs/trade_lifecycle.jsonl*")
        elif name.startswith("shadow_critical_event_journal_v1.jsonl"):
            buckets.add("logs/shadow_critical_event_journal_v1.jsonl*")
        elif name.startswith("aurora_core.log"):
            buckets.add("logs/aurora_core.log*")
        elif name.startswith("domain_execution_position.log"):
            buckets.add("logs/domain_execution_position.log*")
        elif name.startswith("event_chain.log"):
            buckets.add("logs/event_chain.log*")
        elif name.startswith("order_guardian.log"):
            buckets.add("logs/order_guardian.log*")
        else:
            buckets.add(T5D.family_key(rel))
    return sorted(buckets)


def cluster_window_starts(values: list[int]) -> list[int]:
    clustered: list[int] = []
    for value in sorted(set(values)):
        if not clustered or value - clustered[-1] > WINDOW_MARKER_GAP_MS:
            clustered.append(value)
    return clustered


def fill_identity_key(event: dict) -> tuple:
    payload = event.get("payload") if isinstance(event, dict) else None
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    fill_trade_id = ""
    if isinstance(metadata, dict):
        fill_trade_id = T5D.stringify(metadata.get("fill_trade_id"))
    if fill_trade_id:
        return ("trade_id", fill_trade_id)
    return (
        "event",
        event.get("ts_ms"),
        event.get("order_id"),
        event.get("client_order_id"),
        event.get("quantity"),
        event.get("price"),
    )


def generic_identity_key(event: dict) -> tuple:
    return T5D.event_fingerprint(event)


def dedupe_matches(matches: list[tuple], identity_fn) -> list[tuple]:
    deduped: list[tuple] = []
    seen = set()
    for item in sorted(matches, key=lambda record: (record[0], record[1])):
        key = identity_fn(item[2])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def summarize_fill_progress(placed_qty: float | None, fill_matches: list[tuple]) -> tuple[list[tuple], tuple | None, tuple | None]:
    progress: list[tuple] = []
    cumulative_qty = 0.0
    first_partial = None
    terminal_fill = None
    for ts_ms, method, candidate in dedupe_matches(fill_matches, fill_identity_key):
        fill_qty = T5D.safe_float(candidate.get("quantity"))
        if fill_qty is None or fill_qty <= 0:
            continue
        before_qty = cumulative_qty
        cumulative_qty += fill_qty
        record = (ts_ms, method, candidate, before_qty, cumulative_qty)
        progress.append(record)
        if placed_qty is None or placed_qty <= 0:
            continue
        if first_partial is None and cumulative_qty + 1e-9 < placed_qty:
            first_partial = record
        if terminal_fill is None and cumulative_qty + 1e-9 >= placed_qty:
            terminal_fill = record
    if terminal_fill is None and (placed_qty is None or placed_qty <= 0) and progress:
        terminal_fill = progress[0]
    return progress, first_partial, terminal_fill


def build_flag_row(**kwargs) -> FlagRow:
    return FlagRow(
        flag_id=kwargs.get("flag_id", ""),
        flag_type=kwargs.get("flag_type", ""),
        severity=kwargs.get("severity", ""),
        status=kwargs.get("status", ""),
        case_id=kwargs.get("case_id", ""),
        symbol=kwargs.get("symbol", ""),
        strategy_id=kwargs.get("strategy_id", ""),
        source_fsm=kwargs.get("source_fsm", ""),
        order_key=kwargs.get("order_key", ""),
        order_id=kwargs.get("order_id", ""),
        client_order_id=kwargs.get("client_order_id", ""),
        rid=kwargs.get("rid", ""),
        window_id=kwargs.get("window_id", ""),
        placed_ts_iso=kwargs.get("placed_ts_iso", ""),
        partial_fill_ts_iso=kwargs.get("partial_fill_ts_iso", ""),
        terminal_ts_iso=kwargs.get("terminal_ts_iso", ""),
        observed_value=kwargs.get("observed_value", ""),
        expected_value=kwargs.get("expected_value", ""),
        evidence=kwargs.get("evidence", ""),
        notes=kwargs.get("notes", ""),
    )


def make_empty_outputs(order_csv_path: Path, window_csv_path: Path, flags_csv_path: Path):
    order_fields = [
        "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm", "side",
        "order_type", "time_in_force", "placed_ts_ms", "placed_ts_iso", "fill_ttl_source",
        "fill_ttl_override_ms", "partial_fill_ts_ms", "partial_fill_ts_iso", "partial_fill_count",
        "terminal_state", "terminal_ts_ms", "terminal_ts_iso", "age_to_terminal_ms",
        "age_to_first_fill_ms", "age_to_partial_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms",
        "partial_fill_to_timeout_ms", "join_method", "identity_match_level", "notes",
    ]
    window_fields = [
        "window_id", "start_ts_ms", "start_ts_iso", "end_ts_ms", "end_ts_iso", "post_fix_order_placed_total",
        "metadata_bearing_order_placed", "aurora_limit_gtx_entries", "orders_with_partial_fill",
        "partial_fill_with_per_order_override", "partial_fill_with_timeout", "partial_fill_filled_terminal",
        "partial_fill_unknown_terminal", "fill_ttl_source_per_order_override", "fill_ttl_source_global_watchdog",
        "fill_ttl_override_ms_values", "filled", "timeout", "canceled", "unknown", "terminal_join_rate",
        "symbols", "strategies", "source_fsms", "age_to_first_fill_ms_count", "age_to_first_fill_ms_min",
        "age_to_first_fill_ms_p50", "age_to_first_fill_ms_p75", "age_to_first_fill_ms_p90", "age_to_first_fill_ms_p95",
        "age_to_first_fill_ms_p99", "age_to_first_fill_ms_max", "age_to_partial_fill_ms_count",
        "age_to_partial_fill_ms_min", "age_to_partial_fill_ms_p50", "age_to_partial_fill_ms_p75",
        "age_to_partial_fill_ms_p90", "age_to_partial_fill_ms_p95", "age_to_partial_fill_ms_p99",
        "age_to_partial_fill_ms_max", "age_to_timeout_ms_count", "age_to_timeout_ms_min", "age_to_timeout_ms_p50",
        "age_to_timeout_ms_p75", "age_to_timeout_ms_p90", "age_to_timeout_ms_p95", "age_to_timeout_ms_p99",
        "age_to_timeout_ms_max", "age_to_cancel_ms_count", "age_to_cancel_ms_min", "age_to_cancel_ms_p50",
        "age_to_cancel_ms_p75", "age_to_cancel_ms_p90", "age_to_cancel_ms_p95", "age_to_cancel_ms_p99",
        "age_to_cancel_ms_max", "age_to_terminal_ms_count", "age_to_terminal_ms_min", "age_to_terminal_ms_p50",
        "age_to_terminal_ms_p75", "age_to_terminal_ms_p90", "age_to_terminal_ms_p95", "age_to_terminal_ms_p99",
        "age_to_terminal_ms_max", "partial_fill_to_timeout_ms_count", "partial_fill_to_timeout_ms_min",
        "partial_fill_to_timeout_ms_p50", "partial_fill_to_timeout_ms_p75", "partial_fill_to_timeout_ms_p90",
        "partial_fill_to_timeout_ms_p95", "partial_fill_to_timeout_ms_p99", "partial_fill_to_timeout_ms_max",
    ]
    flag_fields = [field for field in FlagRow.__annotations__]
    with order_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=order_fields)
        writer.writeheader()
        writer.writerow({"notes": "diagnostic_only:no_post_fix_order_rows"})
    with window_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=window_fields)
        writer.writeheader()
        writer.writerow({"window_id": "W01", "post_fix_order_placed_total": 0})
    with flags_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=flag_fields)
        writer.writeheader()
        writer.writerow(
            build_flag_row(
                flag_id="F001",
                flag_type="BLOCKED_LOGS_MISSING",
                severity="high",
                status="diagnostic",
                observed_value="required runtime surfaces missing",
                expected_value="order_log_v1.jsonl + trade_lifecycle.jsonl + text log families present",
                evidence="log inventory incomplete",
                notes="T5F could not inspect fresh post-fix runtime surfaces",
            ).__dict__
        )


def write_casebook(casebook_path: Path, rows: list[dict]):
    fields = [
        "case_id", "regression_type", "symbol", "strategy_id", "source_fsm", "order_id", "client_order_id", "rid",
        "lifecycle_id", "side", "order_type", "time_in_force", "placed_ts", "partial_fill_ts", "fill_ttl_source",
        "fill_ttl_override_ms", "expected_effective_ttl_ms", "actual_timeout_ts", "actual_timeout_age_from_placement_ms",
        "actual_timeout_age_from_partial_fill_ms", "filled_ts", "canceled_ts", "position_closed_ts", "terminal_state",
        "join_method", "identity_match_level", "evidence_files", "notes",
    ]
    with casebook_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if rows:
            for row in rows:
                writer.writerow({field: csv_value(row.get(field))
                                for field in fields})
        else:
            writer.writerow(
                {"case_id": "diagnostic", "notes": "no_regression_cases"})


def main():
    repo_root = Path(__file__).resolve().parents[2]
    report_path = repo_root / REPORT_NAME
    order_csv_path = repo_root / ORDER_CSV_NAME
    window_csv_path = repo_root / WINDOW_CSV_NAME
    flags_csv_path = repo_root / FLAGS_CSV_NAME
    casebook_path = repo_root / CASEBOOK_CSV_NAME
    logs_dir = repo_root / "logs"

    wrapper_mtimes = {
        rel: stat_mtime_ms(repo_root / rel) for rel in PATCH_WRAPPER_PATHS
    }
    owner_mtimes = {
        rel: stat_mtime_ms(repo_root / rel) for rel in PATCH_OWNER_PATHS
    }
    def_report_mtime_ms = stat_mtime_ms(repo_root / DEF_REPORT_NAME)
    git_commit_ms = git_last_commit_ms(
        repo_root, PATCH_OWNER_PATHS + (DEF_REPORT_NAME,))

    change_candidates: list[tuple[str, int]] = []
    for rel, ts_ms in owner_mtimes.items():
        if ts_ms is not None:
            change_candidates.append((f"owner_mtime:{rel}", ts_ms))
    for rel, ts_ms in wrapper_mtimes.items():
        if ts_ms is not None:
            change_candidates.append((f"wrapper_mtime:{rel}", ts_ms))
    if def_report_mtime_ms is not None:
        change_candidates.append(
            (f"report_mtime:{DEF_REPORT_NAME}", def_report_mtime_ms))
    if git_commit_ms is not None:
        change_candidates.append(
            ("git_commit_ts:last_touch_patch_or_report", git_commit_ms))

    boundary_hint_ms = max(
        (ts_ms for _, ts_ms in change_candidates), default=0)
    json_files = discover_json_files(repo_root, boundary_hint_ms)
    text_files = discover_text_files(repo_root, boundary_hint_ms)

    required_json_present = any(path.name == "order_log_v1.jsonl" for path in json_files) and any(
        path.name == "trade_lifecycle.jsonl" for path in json_files
    )
    if not logs_dir.exists() or not required_json_present:
        make_empty_outputs(order_csv_path, window_csv_path, flags_csv_path)
        if casebook_path.exists():
            casebook_path.unlink()
        report_path.write_text(
            "\n".join(
                [
                    "AGENT_REPORT_V1",
                    "",
                    "task: AURORA_TIMER_GOVERNANCE_T5F_POST_FIX_MONITOR",
                    "verdict: BLOCKED_LOGS_MISSING",
                    f"report_path: {REPORT_NAME}",
                    "",
                    "facts:",
                    "- post_fix_boundary: unavailable",
                    "- boundary_basis: required runtime surfaces missing",
                    "- logs_inspected: missing required order_log_v1.jsonl or trade_lifecycle.jsonl",
                    "- runtime_windows: none",
                    "- total_order_placed: 0",
                    "- metadata_order_placed: 0",
                    "- aurora_limit_gtx_entries: 0",
                    "- partial_fill_cases: 0",
                    "- terminal_joins: 0/0",
                    "- symbols: none",
                    "- strategies: none",
                    "",
                    "override_preservation:",
                    "- partial_fill_with_override: 0",
                    "- timeout_near_30m_after_partial_fill: 0",
                    "- timeout_near_20m_or_effective_override: 0",
                    "- override_not_applied_flags: 0",
                    "",
                    "timing_distributions:",
                    "- age_to_first_fill_ms: count=0",
                    "- age_to_partial_fill_ms: count=0",
                    "- age_to_timeout_ms: count=0",
                    "- partial_fill_to_timeout_ms: count=0",
                    "",
                    "regression_checks:",
                    "- override_rearm_regression: BLOCKED_LOGS_MISSING",
                    "- global_watchdog_cases: BLOCKED_LOGS_MISSING",
                    "- stale_watchdog_check: INSUFFICIENT_EVIDENCE",
                    "",
                    "runtime_behavior_change:",
                    "- NONE",
                    "",
                    "config_changes:",
                    "- NONE",
                    "",
                    "unproven:",
                    "- fresh post-fix runtime not available on disk",
                    "",
                    "risks:",
                    "- cannot verify partial-fill override retention without required logs",
                    "",
                    "next_recommended_package:",
                    "- restore required log surfaces, then rerun T5F",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print("verdict=BLOCKED_LOGS_MISSING")
        return

    scanned_files = set()
    family_bounds: dict[str, list[int]] = {}
    startup_markers = []
    relevant_events = []
    seen_fingerprints = set()

    for path in text_files:
        rel = path.relative_to(repo_root).as_posix()
        scanned_files.add(rel)
        family = T5D.family_key(rel)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                raw = line.rstrip("\n")
                match = T5D.TEXT_TS_RE.match(raw)
                ts_ms = T5D.parse_text_datetime(
                    match.group(1)) if match else None
                embedded = T5D.EMBEDDED_TS_MS_RE.search(raw)
                if embedded:
                    ts_ms = T5D.safe_int(embedded.group(1)) or ts_ms
                T5D.update_bounds(family_bounds, family, ts_ms)
                if "ExecPosFSM TTL config:" in raw or any(token in raw for token in T5D.STARTUP_TOKENS):
                    startup_markers.append(
                        {
                            "source_file": rel,
                            "line_no": line_no,
                            "ts_ms": ts_ms,
                            "message": raw.strip(),
                        }
                    )

    for path in json_files:
        rel = path.relative_to(repo_root).as_posix()
        scanned_files.add(rel)
        family = T5D.family_key(rel)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw or not raw.startswith("{"):
                    continue
                if not any(token in raw for token in T5D.TARGET_SUBSTRINGS):
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                event_type = T5D.stringify(payload.get("event_type"))
                if event_type not in T5D.TARGET_EVENT_TYPES:
                    continue
                event = T5D.standardize_event(payload, rel, line_no)
                if event["ts_ms"] is None:
                    continue
                T5D.update_bounds(family_bounds, family, event["ts_ms"])
                fingerprint = T5D.event_fingerprint(event)
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                relevant_events.append(event)

    relevant_events.sort(key=lambda item: (
        item["ts_ms"], item["event_type"], item["source_file"], item["line_no"]))
    placed_events = [
        event for event in relevant_events if event["event_type"] == "ORDER_PLACED"]
    boot_events = [
        event for event in relevant_events if event["event_type"] == "BOOT"]

    latest_change_label, latest_change_ts = max(
        change_candidates, key=lambda item: item[1]) if change_candidates else ("no_change_evidence", 0)

    startup_candidates = []
    for marker in startup_markers:
        if marker["ts_ms"] is not None and marker["ts_ms"] >= latest_change_ts:
            startup_candidates.append(
                ("text_startup", marker["ts_ms"], marker))
    for event in boot_events:
        if event["ts_ms"] >= latest_change_ts:
            startup_candidates.append(("boot_event", event["ts_ms"], event))
    startup_candidates.sort(key=lambda item: item[1])
    first_startup_after_change = startup_candidates[0] if startup_candidates else None

    first_order_after_startup_ts = None
    if first_startup_after_change is not None:
        first_order_after_startup_ts = min(
            (event["ts_ms"] for event in placed_events if event["ts_ms"]
             >= first_startup_after_change[1]),
            default=None,
        )
    first_order_after_change_ts = min(
        (event["ts_ms"] for event in placed_events if event["ts_ms"] >= latest_change_ts), default=None)

    boundary_candidates = [(latest_change_label, latest_change_ts)]
    if first_startup_after_change is not None:
        boundary_candidates.append(
            (f"first_runtime_startup_after_change:{first_startup_after_change[0]}", first_startup_after_change[1]))
    if first_order_after_startup_ts is not None:
        boundary_candidates.append(
            ("first_order_placed_after_post_fix_startup", first_order_after_startup_ts))
    elif first_order_after_change_ts is not None:
        boundary_candidates.append(
            ("first_order_placed_after_change", first_order_after_change_ts))

    boundary_source, boundary_ts = max(
        boundary_candidates, key=lambda item: item[1])

    post_events = [
        event for event in relevant_events if event["ts_ms"] >= boundary_ts]
    post_placed = [
        event for event in placed_events if event["ts_ms"] >= boundary_ts]
    post_boot_events = [
        event for event in boot_events if event["ts_ms"] >= boundary_ts]
    post_startup_markers = [
        marker for marker in startup_markers if marker["ts_ms"] is not None and marker["ts_ms"] >= boundary_ts
    ]

    window_markers = [boundary_ts]
    window_markers.extend(event["ts_ms"] for event in post_boot_events)
    window_markers.extend(marker["ts_ms"] for marker in post_startup_markers)
    window_starts = cluster_window_starts(window_markers)
    max_event_ts = max(
        [boundary_ts]
        + [event["ts_ms"] for event in post_events]
        + [marker["ts_ms"] for marker in post_startup_markers],
    )
    window_specs = []
    for index, start_ts in enumerate(window_starts, start=1):
        next_start = window_starts[index] if index < len(
            window_starts) else None
        end_ts = (next_start - 1) if next_start is not None else max_event_ts
        window_specs.append({"window_id": f"W{index:02d}",
                            "start_ts_ms": start_ts, "end_ts_ms": end_ts})
    if not window_specs:
        window_specs.append(
            {"window_id": "W01", "start_ts_ms": boundary_ts, "end_ts_ms": max_event_ts})

    window_lookup = [spec["start_ts_ms"] for spec in window_specs]

    def assign_window(ts_ms: int) -> str:
        index = bisect_right(window_lookup, ts_ms) - 1
        if index < 0:
            return window_specs[0]["window_id"]
        return window_specs[index]["window_id"]

    fills_by_lifecycle = defaultdict(list)
    fills_by_rid = defaultdict(list)
    fills_by_order_id = defaultdict(list)
    trades_by_lifecycle = defaultdict(list)
    trades_by_rid = defaultdict(list)
    trades_by_order_id = defaultdict(list)
    timeouts_by_order_id = defaultdict(list)
    timeouts_by_client = defaultdict(list)
    timeouts_by_rid = defaultdict(list)
    cancels_by_order_id = defaultdict(list)
    cancels_by_client = defaultdict(list)
    position_closed_by_lifecycle = defaultdict(list)
    position_closed_by_symbol = defaultdict(list)

    for event in post_events:
        event_type = event["event_type"]
        if event_type == "ORDER_FILLED":
            if event["lifecycle_id"]:
                fills_by_lifecycle[event["lifecycle_id"]].append(event)
            if event["rid"]:
                fills_by_rid[event["rid"]].append(event)
            if event["order_id"]:
                fills_by_order_id[event["order_id"]].append(event)
        elif event_type == "TRADE_EXECUTED":
            if event["lifecycle_id"]:
                trades_by_lifecycle[event["lifecycle_id"]].append(event)
            if event["rid"]:
                trades_by_rid[event["rid"]].append(event)
            if event["order_id"]:
                trades_by_order_id[event["order_id"]].append(event)
        elif event_type == "ORDER_TIMEOUT":
            if event["order_id"]:
                timeouts_by_order_id[event["order_id"]].append(event)
            if event["client_order_id"]:
                timeouts_by_client[event["client_order_id"]].append(event)
            if event["rid"]:
                timeouts_by_rid[event["rid"]].append(event)
        elif event_type == "ORDER_CANCELLED":
            if event["order_id"]:
                cancels_by_order_id[event["order_id"]].append(event)
            if event["client_order_id"]:
                cancels_by_client[event["client_order_id"]].append(event)
        elif event_type == "POSITION_CLOSED":
            if event["lifecycle_id"]:
                position_closed_by_lifecycle[event["lifecycle_id"]].append(
                    event)
            if event["symbol"]:
                position_closed_by_symbol[event["symbol"]].append(event)

    order_rows = []
    for placed in post_placed:
        placed_ts = placed["ts_ms"]
        lifecycle_id = placed["rid"]
        order_id = placed["order_id"]
        client_order_id = placed["client_order_id"]
        placed_qty = T5D.safe_float(placed.get("quantity"))

        fill_matches = []
        for method, candidates in (
            ("lifecycle_id", fills_by_lifecycle.get(lifecycle_id, [])),
            ("client_order_id", fills_by_rid.get(client_order_id, [])),
            ("order_id", fills_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    fill_matches.append(
                        (candidate["ts_ms"], method, candidate))

        trade_matches = []
        for method, candidates in (
            ("trade_lifecycle_id", trades_by_lifecycle.get(lifecycle_id, [])),
            ("trade_client_order_id", trades_by_rid.get(client_order_id, [])),
            ("trade_order_id", trades_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    trade_matches.append(
                        (candidate["ts_ms"], method, candidate))
        trade_matches = dedupe_matches(trade_matches, generic_identity_key)

        timeout_matches = []
        for method, candidates in (
            ("order_id", timeouts_by_order_id.get(order_id, [])),
            ("client_order_id", timeouts_by_client.get(client_order_id, [])),
            ("rid", timeouts_by_rid.get(lifecycle_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    timeout_matches.append(
                        (candidate["ts_ms"], method, candidate))
        timeout_matches = dedupe_matches(timeout_matches, generic_identity_key)

        cancel_matches = []
        for method, candidates in (
            ("order_id", cancels_by_order_id.get(order_id, [])),
            ("client_order_id", cancels_by_client.get(client_order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    cancel_matches.append(
                        (candidate["ts_ms"], method, candidate))
        cancel_matches = dedupe_matches(cancel_matches, generic_identity_key)

        position_closed_matches = []
        for candidate in position_closed_by_lifecycle.get(lifecycle_id, []):
            if candidate["ts_ms"] >= placed_ts:
                position_closed_matches.append(
                    (candidate["ts_ms"], "position_closed.lifecycle_id", candidate))
        if not position_closed_matches:
            for candidate in position_closed_by_symbol.get(placed["symbol"], []):
                if candidate["ts_ms"] >= placed_ts:
                    position_closed_matches.append(
                        (candidate["ts_ms"], "position_closed.symbol", candidate))
        position_closed_matches.sort(key=lambda item: item[0])

        fill_progress, first_partial_fill, terminal_fill = summarize_fill_progress(
            placed_qty, fill_matches)
        partial_fill_events = []
        if fill_progress and placed_qty is not None and placed_qty > 0:
            partial_fill_events = [
                record for record in fill_progress if record[4] + 1e-9 < placed_qty]

        first_fill = fill_progress[0] if fill_progress else None
        first_trade = trade_matches[0] if trade_matches else None
        if first_fill and first_trade:
            first_fill_like = first_fill if first_fill[0] <= first_trade[0] else first_trade
        else:
            first_fill_like = first_fill or first_trade
        first_timeout = timeout_matches[0] if timeout_matches else None
        first_cancel = cancel_matches[0] if cancel_matches else None

        terminal_candidates = []
        if terminal_fill:
            terminal_candidates.append(
                (terminal_fill[0], "filled", terminal_fill[1], terminal_fill[2]))
        if first_timeout:
            terminal_candidates.append(
                (first_timeout[0], "timeout", first_timeout[1], first_timeout[2]))
        if first_cancel:
            terminal_candidates.append(
                (first_cancel[0], "canceled", first_cancel[1], first_cancel[2]))
        terminal_candidates.sort(key=lambda item: item[0])
        terminal = terminal_candidates[0] if terminal_candidates else None

        join_method = terminal[2] if terminal else ""
        identity_match_level = "NONE"
        if terminal:
            if any(token in join_method for token in ("lifecycle_id", "order_id")):
                identity_match_level = "HIGH"
            elif join_method:
                identity_match_level = "MEDIUM"

        notes = []
        if first_fill_like and isinstance(first_fill_like, tuple) and len(first_fill_like) > 1 and str(first_fill_like[1]).startswith("trade_"):
            notes.append(f"first_fill_via_{first_fill_like[1]}")
        if first_fill and terminal_fill is None:
            notes.append("non_terminal_fill_observed")
        if first_partial_fill:
            notes.append("partial_fill_observed")
        if terminal and first_fill and terminal[1] != "filled" and first_fill[0] < terminal[0]:
            notes.append("fill_before_terminal")
        if not placed["fill_ttl_source_present"]:
            notes.append("fill_ttl_source_missing")
        if placed["fill_ttl_override_present"] and placed["fill_ttl_override_ms"] is None:
            notes.append("fill_ttl_override_ms_null")

        timeout_ts_ms = first_timeout[0] if first_timeout else None
        cancel_ts_ms = first_cancel[0] if first_cancel else None
        partial_fill_ts_ms = first_partial_fill[0] if first_partial_fill else None
        partial_fill_to_timeout_ms = (
            timeout_ts_ms - partial_fill_ts_ms) if timeout_ts_ms is not None and partial_fill_ts_ms is not None else None

        row = {
            "order_key": order_id or client_order_id or lifecycle_id,
            "window_id": assign_window(placed_ts),
            "source_file": placed["source_file"],
            "symbol": placed["symbol"],
            "strategy_id": placed["strategy_id"],
            "source_fsm": placed["source_fsm"],
            "side": placed["side"],
            "order_type": placed["order_type"],
            "time_in_force": placed["time_in_force"],
            "placed_ts_ms": placed_ts,
            "placed_ts_iso": T5D.iso_utc(placed_ts),
            "order_id": order_id,
            "client_order_id": client_order_id,
            "rid": lifecycle_id,
            "lifecycle_id": lifecycle_id,
            "fill_ttl_source_present": placed["fill_ttl_source_present"],
            "fill_ttl_source": placed["fill_ttl_source"],
            "fill_ttl_override_present": placed["fill_ttl_override_present"],
            "fill_ttl_override_ms": placed["fill_ttl_override_ms"],
            "metadata_bearing": placed["fill_ttl_source_present"] and placed["fill_ttl_override_present"],
            "terminal_state": terminal[1] if terminal else "unknown",
            "terminal_ts_ms": terminal[0] if terminal else None,
            "terminal_ts_iso": T5D.iso_utc(terminal[0]) if terminal else "",
            "age_to_terminal_ms": (terminal[0] - placed_ts) if terminal else None,
            "age_to_first_fill_ms": (first_fill_like[0] - placed_ts) if first_fill_like else None,
            "age_to_partial_fill_ms": (partial_fill_ts_ms - placed_ts) if partial_fill_ts_ms is not None else None,
            "age_to_timeout_ms": (timeout_ts_ms - placed_ts) if timeout_ts_ms is not None else None,
            "age_to_cancel_ms": (cancel_ts_ms - placed_ts) if cancel_ts_ms is not None else None,
            "partial_fill_ts_ms": partial_fill_ts_ms,
            "partial_fill_ts_iso": T5D.iso_utc(partial_fill_ts_ms) if partial_fill_ts_ms is not None else "",
            "partial_fill_count": len(partial_fill_events),
            "partial_fill_to_timeout_ms": partial_fill_to_timeout_ms,
            "join_method": join_method,
            "identity_match_level": identity_match_level,
            "notes": "; ".join(notes),
            "first_fill_ts_ms": first_fill_like[0] if first_fill_like else None,
            "filled_ts_ms": terminal_fill[0] if terminal_fill else None,
            "timeout_ts_ms": timeout_ts_ms,
            "canceled_ts_ms": cancel_ts_ms,
            "position_closed_ts_ms": position_closed_matches[0][0] if position_closed_matches else None,
            "position_closed_method": position_closed_matches[0][1] if position_closed_matches else "",
            "timeframe_sec": placed["timeframe_sec"],
        }
        row["is_calibration_relevant"] = T5D.detect_calibration_relevant(row)
        order_rows.append(row)

    order_rows.sort(key=lambda row: (row["placed_ts_ms"], row["order_key"]))

    global_metrics = T5D.compute_metrics(order_rows)
    runtime_span_ms = max(max_event_ts - boundary_ts, 0)
    runtime_hours = runtime_span_ms / 3600000.0
    partial_fill_rows = [
        row for row in order_rows if row["partial_fill_ts_ms"] is not None]
    partial_fill_override_rows = [
        row for row in partial_fill_rows if row["fill_ttl_source"] == "per_order_override" and row["fill_ttl_override_ms"] == EXPECTED_PER_ORDER_OVERRIDE_MS
    ]
    partial_fill_timeout_rows = [
        row for row in partial_fill_rows if row["terminal_state"] == "timeout"]
    partial_fill_filled_rows = [
        row for row in partial_fill_rows if row["terminal_state"] == "filled"]
    partial_fill_unknown_rows = [
        row for row in partial_fill_rows if row["terminal_state"] == "unknown"]
    override_timeout_rows = [
        row for row in order_rows if row["fill_ttl_source"] == "per_order_override" and row["fill_ttl_override_ms"] == EXPECTED_PER_ORDER_OVERRIDE_MS and row["age_to_timeout_ms"] is not None
    ]
    partial_fill_override_timeout_rows = [
        row for row in override_timeout_rows if row["partial_fill_to_timeout_ms"] is not None]
    partial_fill_override_timeout_near_30m_rows = [
        row for row in partial_fill_override_timeout_rows if abs(row["partial_fill_to_timeout_ms"] - EXPECTED_GLOBAL_WATCHDOG_TTL_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    partial_fill_override_timeout_near_20m_rows = [
        row for row in partial_fill_override_timeout_rows if abs(row["partial_fill_to_timeout_ms"] - EXPECTED_PER_ORDER_OVERRIDE_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    non_partial_override_timeout_near_20m_rows = [
        row for row in override_timeout_rows if row["partial_fill_to_timeout_ms"] is None and abs(row["age_to_timeout_ms"] - EXPECTED_PER_ORDER_OVERRIDE_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    non_partial_override_timeout_near_30m_rows = [
        row for row in override_timeout_rows if row["partial_fill_to_timeout_ms"] is None and abs(row["age_to_timeout_ms"] - EXPECTED_GLOBAL_WATCHDOG_TTL_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    override_timeout_near_effective_rows = partial_fill_override_timeout_near_20m_rows + \
        non_partial_override_timeout_near_20m_rows
    global_watchdog_rows = [
        row for row in order_rows if row["fill_ttl_source"] == "global_watchdog"]

    stale_suspicions = []
    for row in [candidate for candidate in order_rows if candidate["age_to_timeout_ms"] is not None]:
        reasons = []
        timeout_ts = row["timeout_ts_ms"]
        if row["terminal_state"] in {"filled", "canceled"} and row["terminal_ts_ms"] and timeout_ts and timeout_ts > row["terminal_ts_ms"]:
            reasons.append("timeout_after_known_terminal")
        if row["filled_ts_ms"] and timeout_ts and timeout_ts > row["filled_ts_ms"]:
            reasons.append("timeout_after_fill")
        if row["position_closed_ts_ms"] and timeout_ts and timeout_ts > row["position_closed_ts_ms"]:
            if row["position_closed_method"] == "position_closed.lifecycle_id":
                reasons.append("timeout_after_position_closed_lifecycle_match")
            elif row["position_closed_method"] == "position_closed.symbol":
                reasons.append("timeout_after_position_closed_symbol_only")
        if reasons:
            stale_suspicions.append(
                {
                    "row": row,
                    "reasons": reasons,
                }
            )

    if not any(row["age_to_timeout_ms"] is not None for row in order_rows):
        stale_watchdog_verdict = "INSUFFICIENT_EVIDENCE"
    elif any(
        any(reason in item["reasons"] for reason in ("timeout_after_fill",
            "timeout_after_known_terminal", "timeout_after_position_closed_lifecycle_match"))
        for item in stale_suspicions
    ):
        stale_watchdog_verdict = "STALE_WATCHDOG_CONFIRMED"
    elif stale_suspicions:
        stale_watchdog_verdict = "STALE_WATCHDOG_SUSPECTED"
    else:
        stale_watchdog_verdict = "NO_STALE_WATCHDOG_AFTER_FIX"

    global_watchdog_cases = []
    for row in global_watchdog_rows:
        classification = "expected"
        notes = []
        if row["terminal_state"] == "timeout" and row["age_to_timeout_ms"] is not None:
            if abs(row["age_to_timeout_ms"] - EXPECTED_GLOBAL_WATCHDOG_TTL_MS) <= TIMEOUT_TOLERANCE_MS:
                notes.append("timeout_near_expected_global_backstop")
            elif row["age_to_timeout_ms"] < EXPECTED_GLOBAL_WATCHDOG_TTL_MS - TIMEOUT_TOLERANCE_MS:
                classification = "suspicious"
                notes.append("timeout_before_expected_global_backstop")
            else:
                classification = "suspicious"
                notes.append("timeout_after_expected_global_backstop")
        elif row["terminal_state"] in {"filled", "canceled"}:
            notes.append("terminal_before_or_without_global_timeout")
        else:
            classification = "suspicious"
            notes.append(f"terminal_state={row['terminal_state']}")
        if row["partial_fill_ts_ms"] is not None:
            notes.append("partial_fill_observed_on_global_path")
        global_watchdog_cases.append(
            {"row": row, "classification": classification, "notes": notes})

    flag_rows: list[FlagRow] = []
    casebook_rows: list[dict] = []
    flag_counter = 0
    case_counter = 0

    def next_flag_id() -> str:
        nonlocal flag_counter
        flag_counter += 1
        return f"F{flag_counter:03d}"

    def next_case_id() -> str:
        nonlocal case_counter
        case_counter += 1
        return f"RG-{case_counter:03d}"

    for row in partial_fill_override_timeout_near_30m_rows:
        case_id = next_case_id()
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="OVERRIDE_NOT_APPLIED_TIMEOUT_NEAR_30MIN",
                severity="critical",
                status="open",
                case_id=case_id,
                symbol=row["symbol"],
                strategy_id=row["strategy_id"],
                source_fsm=row["source_fsm"],
                order_key=row["order_key"],
                order_id=row["order_id"],
                client_order_id=row["client_order_id"],
                rid=row["rid"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                partial_fill_ts_iso=row["partial_fill_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=f"partial_fill_to_timeout_ms={row['partial_fill_to_timeout_ms']} age_to_timeout_ms={row['age_to_timeout_ms']}",
                expected_value=f"partial_fill_to_timeout_ms near {EXPECTED_PER_ORDER_OVERRIDE_MS}",
                evidence=f"fill_ttl_source={row['fill_ttl_source']} fill_ttl_override_ms={row['fill_ttl_override_ms']}",
                notes="partial-fill re-arm appears to have fallen back to the global 30-minute backstop",
            )
        )
        casebook_rows.append(
            {
                "case_id": case_id,
                "regression_type": "OVERRIDE_NOT_APPLIED_TIMEOUT_NEAR_30MIN",
                "symbol": row["symbol"],
                "strategy_id": row["strategy_id"],
                "source_fsm": row["source_fsm"],
                "order_id": row["order_id"],
                "client_order_id": row["client_order_id"],
                "rid": row["rid"],
                "lifecycle_id": row["lifecycle_id"],
                "side": row["side"],
                "order_type": row["order_type"],
                "time_in_force": row["time_in_force"],
                "placed_ts": row["placed_ts_iso"],
                "partial_fill_ts": row["partial_fill_ts_iso"],
                "fill_ttl_source": row["fill_ttl_source"],
                "fill_ttl_override_ms": row["fill_ttl_override_ms"],
                "expected_effective_ttl_ms": EXPECTED_PER_ORDER_OVERRIDE_MS,
                "actual_timeout_ts": row["terminal_ts_iso"],
                "actual_timeout_age_from_placement_ms": row["age_to_timeout_ms"],
                "actual_timeout_age_from_partial_fill_ms": row["partial_fill_to_timeout_ms"],
                "filled_ts": T5D.iso_utc(row["filled_ts_ms"]),
                "canceled_ts": T5D.iso_utc(row["canceled_ts_ms"]),
                "position_closed_ts": T5D.iso_utc(row["position_closed_ts_ms"]),
                "terminal_state": row["terminal_state"],
                "join_method": row["join_method"],
                "identity_match_level": row["identity_match_level"],
                "evidence_files": row["source_file"],
                "notes": "partial fill observed before timeout near global backstop",
            }
        )

    for row in non_partial_override_timeout_near_30m_rows:
        case_id = next_case_id()
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="PER_ORDER_OVERRIDE_TIMEOUT_NEAR_30MIN",
                severity="high",
                status="open",
                case_id=case_id,
                symbol=row["symbol"],
                strategy_id=row["strategy_id"],
                source_fsm=row["source_fsm"],
                order_key=row["order_key"],
                order_id=row["order_id"],
                client_order_id=row["client_order_id"],
                rid=row["rid"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                partial_fill_ts_iso=row["partial_fill_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=f"age_to_timeout_ms={row['age_to_timeout_ms']}",
                expected_value=f"age_to_timeout_ms near {EXPECTED_PER_ORDER_OVERRIDE_MS}",
                evidence=f"fill_ttl_source={row['fill_ttl_source']} fill_ttl_override_ms={row['fill_ttl_override_ms']}",
                notes="per-order override timed out near global backstop without proven partial-fill re-arm context",
            )
        )
        casebook_rows.append(
            {
                "case_id": case_id,
                "regression_type": "PER_ORDER_OVERRIDE_TIMEOUT_NEAR_30MIN",
                "symbol": row["symbol"],
                "strategy_id": row["strategy_id"],
                "source_fsm": row["source_fsm"],
                "order_id": row["order_id"],
                "client_order_id": row["client_order_id"],
                "rid": row["rid"],
                "lifecycle_id": row["lifecycle_id"],
                "side": row["side"],
                "order_type": row["order_type"],
                "time_in_force": row["time_in_force"],
                "placed_ts": row["placed_ts_iso"],
                "partial_fill_ts": row["partial_fill_ts_iso"],
                "fill_ttl_source": row["fill_ttl_source"],
                "fill_ttl_override_ms": row["fill_ttl_override_ms"],
                "expected_effective_ttl_ms": EXPECTED_PER_ORDER_OVERRIDE_MS,
                "actual_timeout_ts": row["terminal_ts_iso"],
                "actual_timeout_age_from_placement_ms": row["age_to_timeout_ms"],
                "actual_timeout_age_from_partial_fill_ms": row["partial_fill_to_timeout_ms"],
                "filled_ts": T5D.iso_utc(row["filled_ts_ms"]),
                "canceled_ts": T5D.iso_utc(row["canceled_ts_ms"]),
                "position_closed_ts": T5D.iso_utc(row["position_closed_ts_ms"]),
                "terminal_state": row["terminal_state"],
                "join_method": row["join_method"],
                "identity_match_level": row["identity_match_level"],
                "evidence_files": row["source_file"],
                "notes": "override timed out near 30m with no proven partial-fill retention path",
            }
        )

    for item in stale_suspicions:
        row = item["row"]
        reasons = item["reasons"]
        confirmed = any(reason in reasons for reason in ("timeout_after_fill",
                        "timeout_after_known_terminal", "timeout_after_position_closed_lifecycle_match"))
        if not confirmed and all(reason == "timeout_after_position_closed_symbol_only" for reason in reasons):
            continue
        case_id = next_case_id()
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="STALE_WATCHDOG_CHECK",
                severity="critical" if confirmed else "medium",
                status="open" if confirmed else "suspected",
                case_id=case_id,
                symbol=row["symbol"],
                strategy_id=row["strategy_id"],
                source_fsm=row["source_fsm"],
                order_key=row["order_key"],
                order_id=row["order_id"],
                client_order_id=row["client_order_id"],
                rid=row["rid"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                partial_fill_ts_iso=row["partial_fill_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=",".join(reasons),
                expected_value="no timeout after terminal fill/cancel/position close",
                evidence=f"position_closed_method={row['position_closed_method']} timeout_ts={T5D.iso_utc(row['timeout_ts_ms'])}",
                notes="stale watchdog candidate detected",
            )
        )
        casebook_rows.append(
            {
                "case_id": case_id,
                "regression_type": "STALE_WATCHDOG_CONFIRMED" if confirmed else "STALE_WATCHDOG_SUSPECTED",
                "symbol": row["symbol"],
                "strategy_id": row["strategy_id"],
                "source_fsm": row["source_fsm"],
                "order_id": row["order_id"],
                "client_order_id": row["client_order_id"],
                "rid": row["rid"],
                "lifecycle_id": row["lifecycle_id"],
                "side": row["side"],
                "order_type": row["order_type"],
                "time_in_force": row["time_in_force"],
                "placed_ts": row["placed_ts_iso"],
                "partial_fill_ts": row["partial_fill_ts_iso"],
                "fill_ttl_source": row["fill_ttl_source"],
                "fill_ttl_override_ms": row["fill_ttl_override_ms"],
                "expected_effective_ttl_ms": row["fill_ttl_override_ms"] or EXPECTED_GLOBAL_WATCHDOG_TTL_MS,
                "actual_timeout_ts": T5D.iso_utc(row["timeout_ts_ms"]),
                "actual_timeout_age_from_placement_ms": row["age_to_timeout_ms"],
                "actual_timeout_age_from_partial_fill_ms": row["partial_fill_to_timeout_ms"],
                "filled_ts": T5D.iso_utc(row["filled_ts_ms"]),
                "canceled_ts": T5D.iso_utc(row["canceled_ts_ms"]),
                "position_closed_ts": T5D.iso_utc(row["position_closed_ts_ms"]),
                "terminal_state": row["terminal_state"],
                "join_method": row["join_method"],
                "identity_match_level": row["identity_match_level"],
                "evidence_files": row["source_file"],
                "notes": ",".join(reasons),
            }
        )

    for case in global_watchdog_cases:
        row = case["row"]
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="GLOBAL_WATCHDOG_CASE",
                severity="medium" if case["classification"] == "suspicious" else "low",
                status="open" if case["classification"] == "suspicious" else "observed_safe",
                case_id="",
                symbol=row["symbol"],
                strategy_id=row["strategy_id"],
                source_fsm=row["source_fsm"],
                order_key=row["order_key"],
                order_id=row["order_id"],
                client_order_id=row["client_order_id"],
                rid=row["rid"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                partial_fill_ts_iso=row["partial_fill_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=f"terminal_state={row['terminal_state']} age_to_timeout_ms={row['age_to_timeout_ms']}",
                expected_value=f"global_backstop={EXPECTED_GLOBAL_WATCHDOG_TTL_MS}",
                evidence=f"fill_ttl_source={row['fill_ttl_source']}",
                notes="; ".join(
                    case["notes"]) or "global watchdog path observed",
            )
        )

    if not post_placed:
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="NOT_ENOUGH_POST_FIX_RUNTIME",
                severity="low",
                status="diagnostic",
                case_id="",
                observed_value=f"boundary={T5D.iso_utc(boundary_ts)} post_fix_order_placed_total=0",
                expected_value="at least one ORDER_PLACED after post-fix startup boundary",
                evidence=f"boundary_source={boundary_source}",
                notes="no post-fix ORDER_PLACED rows retained after conservative boundary",
            )
        )
    elif runtime_hours < MIN_RUNTIME_HOURS and len(post_placed) < MIN_POST_FIX_ORDER_PLACED:
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="NOT_ENOUGH_POST_FIX_RUNTIME",
                severity="low",
                status="diagnostic",
                case_id="",
                observed_value=f"runtime_hours={runtime_hours:.2f} post_fix_order_placed_total={len(post_placed)}",
                expected_value=f"runtime_hours>={MIN_RUNTIME_HOURS:.0f} or post_fix_order_placed_total>={MIN_POST_FIX_ORDER_PLACED}",
                evidence=f"boundary={T5D.iso_utc(boundary_ts)} source={boundary_source}",
                notes="fresh runtime exists but remains thin after conservative post-fix boundary",
            )
        )
    elif not partial_fill_override_rows:
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="NOT_ENOUGH_PARTIAL_FILL_EVIDENCE",
                severity="low",
                status="diagnostic",
                case_id="",
                observed_value=f"partial_fill_with_per_order_override={len(partial_fill_override_rows)}",
                expected_value=">=1 post-fix partial-fill override case",
                evidence=f"post_fix_order_placed_total={len(post_placed)} runtime_hours={runtime_hours:.2f}",
                notes="runtime window is usable, but no qualifying partial-fill override rows were retained",
            )
        )
    elif len(partial_fill_override_rows) < PREFERRED_PARTIAL_FILL_POWER:
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="LOW_PARTIAL_FILL_POWER",
                severity="low",
                status="residual",
                case_id="",
                observed_value=f"partial_fill_with_per_order_override={len(partial_fill_override_rows)}",
                expected_value=f">={PREFERRED_PARTIAL_FILL_POWER}",
                evidence=f"post_fix_order_placed_total={len(post_placed)} runtime_hours={runtime_hours:.2f}",
                notes="healthy sample exists, but partial-fill power remains limited",
            )
        )

    if not flag_rows:
        flag_rows.append(
            build_flag_row(
                flag_id=next_flag_id(),
                flag_type="NO_REGRESSION_FLAGS",
                severity="info",
                status="clear",
                case_id="",
                observed_value="none",
                expected_value="none",
                evidence="all focused T5F checks clear",
                notes="post-fix runtime shows no T5F regression indicators",
            )
        )

    order_rows_by_window = defaultdict(list)
    for row in order_rows:
        order_rows_by_window[row["window_id"]].append(row)

    def compute_partial_metrics(rows: list[dict]) -> dict:
        partial_rows = [
            row for row in rows if row["partial_fill_ts_ms"] is not None]
        partial_override = [
            row for row in partial_rows if row["fill_ttl_source"] == "per_order_override" and row["fill_ttl_override_ms"] == EXPECTED_PER_ORDER_OVERRIDE_MS
        ]
        override_values = sorted(
            {
                row["fill_ttl_override_ms"]
                for row in rows
                if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None
            }
        )
        return {
            "orders_with_partial_fill": len(partial_rows),
            "partial_fill_with_per_order_override": len(partial_override),
            "partial_fill_with_timeout": sum(1 for row in partial_rows if row["terminal_state"] == "timeout"),
            "partial_fill_filled_terminal": sum(1 for row in partial_rows if row["terminal_state"] == "filled"),
            "partial_fill_unknown_terminal": sum(1 for row in partial_rows if row["terminal_state"] == "unknown"),
            "fill_ttl_override_ms_values": join_list([str(value) for value in override_values]),
        }

    window_rows = []
    for spec in window_specs:
        rows = order_rows_by_window.get(spec["window_id"], [])
        metrics = T5D.compute_metrics(rows)
        partial_metrics = compute_partial_metrics(rows)
        window_row = {
            "window_id": spec["window_id"],
            "start_ts_ms": spec["start_ts_ms"],
            "start_ts_iso": T5D.iso_utc(spec["start_ts_ms"]),
            "end_ts_ms": spec["end_ts_ms"],
            "end_ts_iso": T5D.iso_utc(spec["end_ts_ms"]),
            "post_fix_order_placed_total": metrics["total_order_placed"],
            "metadata_bearing_order_placed": metrics["metadata_bearing_order_placed"],
            "aurora_limit_gtx_entries": metrics["aurora_entry_limit_gtx_orders"],
            "orders_with_partial_fill": partial_metrics["orders_with_partial_fill"],
            "partial_fill_with_per_order_override": partial_metrics["partial_fill_with_per_order_override"],
            "partial_fill_with_timeout": partial_metrics["partial_fill_with_timeout"],
            "partial_fill_filled_terminal": partial_metrics["partial_fill_filled_terminal"],
            "partial_fill_unknown_terminal": partial_metrics["partial_fill_unknown_terminal"],
            "fill_ttl_source_per_order_override": metrics["fill_ttl_source_per_order_override"],
            "fill_ttl_source_global_watchdog": metrics["fill_ttl_source_global_watchdog"],
            "fill_ttl_override_ms_values": partial_metrics["fill_ttl_override_ms_values"],
            "filled": metrics["filled"],
            "timeout": metrics["timeout"],
            "canceled": metrics["canceled"],
            "unknown": metrics["unknown"],
            "terminal_join_rate": f"{metrics['terminal_join_rate']:.3f}",
            "symbols": join_list(metrics["symbols_observed"]),
            "strategies": join_list(metrics["strategies_observed"]),
            "source_fsms": join_list(metrics["source_fsms_observed"]),
        }
        add_dist_fields(window_row, "age_to_first_fill_ms", [
                        row["age_to_first_fill_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_partial_fill_ms", [
                        row["age_to_partial_fill_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_timeout_ms", [
                        row["age_to_timeout_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_cancel_ms", [
                        row["age_to_cancel_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_terminal_ms", [
                        row["age_to_terminal_ms"] for row in rows])
        add_dist_fields(window_row, "partial_fill_to_timeout_ms", [
                        row["partial_fill_to_timeout_ms"] for row in rows])
        window_rows.append(window_row)

    global_partial_metrics = compute_partial_metrics(order_rows)
    fill_ttl_override_values = sorted(
        {
            row["fill_ttl_override_ms"]
            for row in order_rows
            if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None
        }
    )
    timing_first_fill = T5D.dist_summary(
        [row["age_to_first_fill_ms"] for row in order_rows])
    timing_partial_fill = T5D.dist_summary(
        [row["age_to_partial_fill_ms"] for row in order_rows])
    timing_timeout = T5D.dist_summary(
        [row["age_to_timeout_ms"] for row in order_rows])
    timing_cancel = T5D.dist_summary(
        [row["age_to_cancel_ms"] for row in order_rows])
    timing_terminal = T5D.dist_summary(
        [row["age_to_terminal_ms"] for row in order_rows])
    timing_partial_timeout = T5D.dist_summary(
        [row["partial_fill_to_timeout_ms"] for row in order_rows])

    regression_detected = bool(casebook_rows)
    low_runtime = runtime_hours < MIN_RUNTIME_HOURS and len(
        post_placed) < MIN_POST_FIX_ORDER_PLACED
    low_partial_power = 0 < len(
        partial_fill_override_rows) < PREFERRED_PARTIAL_FILL_POWER
    no_partial_evidence = not partial_fill_override_rows

    if regression_detected:
        verdict = "POST_FIX_REGRESSION_DETECTED"
    elif not post_placed or low_runtime:
        verdict = "POST_FIX_NOT_ENOUGH_RUNTIME"
    elif no_partial_evidence:
        verdict = "POST_FIX_NOT_ENOUGH_PARTIAL_FILL_EVIDENCE"
    elif low_partial_power:
        verdict = "POST_FIX_HEALTHY_WITH_LOW_PARTIAL_FILL_POWER"
    else:
        verdict = "POST_FIX_HEALTHY"

    order_fields = [
        "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm", "side",
        "order_type", "time_in_force", "placed_ts_ms", "placed_ts_iso", "fill_ttl_source",
        "fill_ttl_override_ms", "partial_fill_ts_ms", "partial_fill_ts_iso", "partial_fill_count",
        "terminal_state", "terminal_ts_ms", "terminal_ts_iso", "age_to_terminal_ms", "age_to_first_fill_ms",
        "age_to_partial_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms", "partial_fill_to_timeout_ms",
        "join_method", "identity_match_level", "notes",
    ]
    with order_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=order_fields)
        writer.writeheader()
        if order_rows:
            for row in order_rows:
                writer.writerow({field: csv_value(row.get(field))
                                for field in order_fields})
        else:
            writer.writerow(
                {"notes": "diagnostic_only:no_post_fix_order_rows"})

    window_fields = [
        "window_id", "start_ts_ms", "start_ts_iso", "end_ts_ms", "end_ts_iso", "post_fix_order_placed_total",
        "metadata_bearing_order_placed", "aurora_limit_gtx_entries", "orders_with_partial_fill",
        "partial_fill_with_per_order_override", "partial_fill_with_timeout", "partial_fill_filled_terminal",
        "partial_fill_unknown_terminal", "fill_ttl_source_per_order_override", "fill_ttl_source_global_watchdog",
        "fill_ttl_override_ms_values", "filled", "timeout", "canceled", "unknown", "terminal_join_rate",
        "symbols", "strategies", "source_fsms", "age_to_first_fill_ms_count", "age_to_first_fill_ms_min",
        "age_to_first_fill_ms_p50", "age_to_first_fill_ms_p75", "age_to_first_fill_ms_p90", "age_to_first_fill_ms_p95",
        "age_to_first_fill_ms_p99", "age_to_first_fill_ms_max", "age_to_partial_fill_ms_count",
        "age_to_partial_fill_ms_min", "age_to_partial_fill_ms_p50", "age_to_partial_fill_ms_p75",
        "age_to_partial_fill_ms_p90", "age_to_partial_fill_ms_p95", "age_to_partial_fill_ms_p99",
        "age_to_partial_fill_ms_max", "age_to_timeout_ms_count", "age_to_timeout_ms_min", "age_to_timeout_ms_p50",
        "age_to_timeout_ms_p75", "age_to_timeout_ms_p90", "age_to_timeout_ms_p95", "age_to_timeout_ms_p99",
        "age_to_timeout_ms_max", "age_to_cancel_ms_count", "age_to_cancel_ms_min", "age_to_cancel_ms_p50",
        "age_to_cancel_ms_p75", "age_to_cancel_ms_p90", "age_to_cancel_ms_p95", "age_to_cancel_ms_p99",
        "age_to_cancel_ms_max", "age_to_terminal_ms_count", "age_to_terminal_ms_min", "age_to_terminal_ms_p50",
        "age_to_terminal_ms_p75", "age_to_terminal_ms_p90", "age_to_terminal_ms_p95", "age_to_terminal_ms_p99",
        "age_to_terminal_ms_max", "partial_fill_to_timeout_ms_count", "partial_fill_to_timeout_ms_min",
        "partial_fill_to_timeout_ms_p50", "partial_fill_to_timeout_ms_p75", "partial_fill_to_timeout_ms_p90",
        "partial_fill_to_timeout_ms_p95", "partial_fill_to_timeout_ms_p99", "partial_fill_to_timeout_ms_max",
    ]
    with window_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=window_fields)
        writer.writeheader()
        if window_rows:
            for row in window_rows:
                writer.writerow({field: csv_value(row.get(field))
                                for field in window_fields})
        else:
            writer.writerow(
                {"window_id": "W01", "post_fix_order_placed_total": 0})

    flag_fields = [field for field in FlagRow.__annotations__]
    with flags_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=flag_fields)
        writer.writeheader()
        for row in flag_rows:
            writer.writerow({field: csv_value(getattr(row, field))
                            for field in flag_fields})

    if casebook_rows:
        write_casebook(casebook_path, casebook_rows)
    elif casebook_path.exists():
        casebook_path.unlink()

    boundary_basis_bits = [
        f"latest_change_evidence={latest_change_label}:{T5D.iso_utc(latest_change_ts)}",
        "wrapper_paths_are_forwarders_to_owner_files",
        f"owner_mtimes={join_list([f'{rel}={T5D.iso_utc(ts)}' for rel,
                                  ts in owner_mtimes.items() if ts is not None])}",
        f"wrapper_mtimes={join_list([f'{rel}={T5D.iso_utc(ts)}' for rel,
                                    ts in wrapper_mtimes.items() if ts is not None])}",
        f"git_commit_ts={T5D.iso_utc(git_commit_ms)}" if git_commit_ms is not None else "git_commit_ts=unavailable",
        f"def_report_mtime={T5D.iso_utc(def_report_mtime_ms)}" if def_report_mtime_ms is not None else "def_report_mtime=unavailable_in_worktree",
        f"first_runtime_startup_after_change={T5D.iso_utc(first_startup_after_change[1])}" if first_startup_after_change is not None else "first_runtime_startup_after_change=unavailable",
        f"first_order_after_startup={T5D.iso_utc(first_order_after_startup_ts)}" if first_order_after_startup_ts is not None else "first_order_after_startup=unavailable",
        f"chosen_boundary_source={boundary_source}",
    ]
    log_families = summarize_scanned_surfaces(scanned_files)
    runtime_window_lines = [
        f"{row['window_id']} {row['start_ts_iso']} -> {row['end_ts_iso']} orders={row['post_fix_order_placed_total']} partial_fill={row['orders_with_partial_fill']} joins={row['terminal_join_rate']}"
        for row in window_rows
    ]
    if not runtime_window_lines:
        runtime_window_lines = ["none"]

    override_rearm_regression = "PASS"
    if partial_fill_override_timeout_near_30m_rows:
        override_rearm_regression = f"FAIL cases={len(partial_fill_override_timeout_near_30m_rows)}"
    elif partial_fill_override_rows:
        override_rearm_regression = f"PASS partial_fill_override_cases={len(partial_fill_override_rows)} near_effective={len(partial_fill_override_timeout_near_20m_rows)}/{len(partial_fill_override_timeout_rows)}"
    else:
        override_rearm_regression = "UNPROVEN no_post_fix_partial_fill_override_cases"

    global_watchdog_summary = f"total={len(global_watchdog_cases)} suspicious={sum(1 for case in global_watchdog_cases if case['classification'] == 'suspicious')}"
    terminal_join_rate_text = f"{global_metrics['total_order_placed'] - global_metrics['unknown']}/{global_metrics['total_order_placed']} rate={global_metrics['terminal_join_rate']:.3f}" if global_metrics["total_order_placed"] else "0/0 rate=0.000"
    logs_inspected_text = f"{len(scanned_files)} files across {join_list(log_families)}"
    override_not_applied_flags = sum(
        1 for row in flag_rows if row.flag_type == "OVERRIDE_NOT_APPLIED_TIMEOUT_NEAR_30MIN")
    timeout_near_effective = len(override_timeout_near_effective_rows)
    timeout_near_30m_after_partial_fill = len(
        partial_fill_override_timeout_near_30m_rows)

    unproven_lines = []
    if def_report_mtime_ms is None:
        unproven_lines.append(
            "DEF report file is absent in the worktree, so report filesystem timestamp could not be used directly")
    if not partial_fill_override_rows:
        unproven_lines.append(
            "no post-fix partial-fill + per_order_override rows were retained after the conservative boundary")
    if not post_startup_markers and not post_boot_events:
        unproven_lines.append(
            "no retained BOOT/startup marker remained after the chosen boundary; first ORDER_PLACED was used as the last conservative boundary hop")
    if not unproven_lines:
        unproven_lines.append("none")

    risk_lines = []
    if low_runtime:
        risk_lines.append(
            "fresh runtime remains thin after the conservative post-fix boundary")
    if low_partial_power:
        risk_lines.append(
            "partial-fill power is low, so a rare override-loss regression could still hide outside the retained sample")
    if stale_watchdog_verdict == "STALE_WATCHDOG_SUSPECTED":
        risk_lines.append(
            "symbol-only timeout-after-close hints remain suspicious but not confirmed")
    if not risk_lines:
        risk_lines.append(
            "no material residual runtime risk surfaced in retained T5F evidence")

    if verdict == "POST_FIX_REGRESSION_DETECTED":
        next_package = "bounded DEF package for the exact regression rows in the T5F casebook"
    elif verdict == "POST_FIX_HEALTHY":
        next_package = "close the T5 timer-governance line or move to the next timer family"
    elif verdict == "POST_FIX_HEALTHY_WITH_LOW_PARTIAL_FILL_POWER":
        next_package = "continue runtime collection until partial-fill power reaches a stronger sample"
    elif verdict == "POST_FIX_NOT_ENOUGH_PARTIAL_FILL_EVIDENCE":
        next_package = "continue runtime collection specifically until a post-fix partial-fill override case is retained"
    elif verdict == "POST_FIX_NOT_ENOUGH_RUNTIME":
        next_package = "continue fresh runtime collection after the conservative post-fix boundary"
    else:
        next_package = "restore missing logs and rerun T5F"

    report_lines = [
        "AGENT_REPORT_V1",
        "",
        "task: AURORA_TIMER_GOVERNANCE_T5F_POST_FIX_MONITOR",
        f"verdict: {verdict}",
        f"report_path: {REPORT_NAME}",
        "",
        "facts:",
        f"- post_fix_boundary: {T5D.iso_utc(boundary_ts)}",
        f"- boundary_basis: {'; '.join(boundary_basis_bits)}",
        f"- logs_inspected: {logs_inspected_text}",
        f"- runtime_windows: {' | '.join(runtime_window_lines)}",
        f"- total_order_placed: {global_metrics['total_order_placed']}",
        f"- metadata_order_placed: {global_metrics['metadata_bearing_order_placed']}",
        f"- aurora_limit_gtx_entries: {global_metrics['aurora_entry_limit_gtx_orders']}",
        f"- partial_fill_cases: {global_partial_metrics['orders_with_partial_fill']}",
        f"- terminal_joins: {terminal_join_rate_text}",
        f"- symbols: {join_list(global_metrics['symbols_observed'])}",
        f"- strategies: {join_list(global_metrics['strategies_observed'])}",
        "",
        "override_preservation:",
        f"- partial_fill_with_override: {len(partial_fill_override_rows)}",
        f"- timeout_near_30m_after_partial_fill: {timeout_near_30m_after_partial_fill}",
        f"- timeout_near_20m_or_effective_override: {timeout_near_effective}",
        f"- override_not_applied_flags: {override_not_applied_flags}",
        "",
        "timing_distributions:",
        f"- age_to_first_fill_ms: {T5D.format_dist(timing_first_fill)}",
        f"- age_to_partial_fill_ms: {T5D.format_dist(timing_partial_fill)}",
        f"- age_to_timeout_ms: {T5D.format_dist(timing_timeout)}",
        f"- partial_fill_to_timeout_ms: {T5D.format_dist(timing_partial_timeout)}",
        "",
        "regression_checks:",
        f"- override_rearm_regression: {override_rearm_regression}",
        f"- global_watchdog_cases: {global_watchdog_summary}",
        f"- stale_watchdog_check: {stale_watchdog_verdict}",
        "",
        "runtime_behavior_change:",
        "- NONE",
        "",
        "config_changes:",
        "- NONE",
        "",
        "unproven:",
    ]
    report_lines.extend(f"- {line}" for line in unproven_lines)
    report_lines.extend([
        "",
        "risks:",
    ])
    report_lines.extend(f"- {line}" for line in risk_lines)
    report_lines.extend([
        "",
        "next_recommended_package:",
        f"- {next_package}",
    ])
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"verdict={verdict}")
    print(f"boundary={T5D.iso_utc(boundary_ts)} source={boundary_source}")
    print(
        f"post_fix_order_placed_total={global_metrics['total_order_placed']}")
    print(
        f"partial_fill_with_per_order_override={len(partial_fill_override_rows)}")
    print(f"override_not_applied_flags={override_not_applied_flags}")
    print(f"stale_watchdog_check={stale_watchdog_verdict}")


if __name__ == "__main__":
    main()
