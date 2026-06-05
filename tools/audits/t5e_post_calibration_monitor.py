#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REPORT_NAME = "AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md"
ORDER_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5E_ORDER_LIFECYCLES.csv"
WINDOW_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5E_WINDOW_SUMMARY.csv"
FLAGS_CSV_NAME = "AURORA_TIMER_GOVERNANCE_T5E_REGRESSION_FLAGS.csv"
T5D_REPORT_NAME = "AURORA_TIMER_GOVERNANCE_T5D_FILL_TTL_CALIBRATION_REPORT.md"
CONFIG_PATH = "config/aurora/trading.yaml"
MIN_RUNTIME_HOURS = 24.0
MIN_POST_T5D_ORDER_PLACED = 30
PREFERRED_RUNTIME_HOURS = 48.0
PREFERRED_AURORA_LIMIT_GTX = 50
EXPECTED_GLOBAL_WATCHDOG_TTL_MS = 1800000
EXPECTED_PER_ORDER_OVERRIDE_MS = 1200000
TIMEOUT_TOLERANCE_MS = 120000
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
WINDOW_MARKER_GAP_MS = 300000


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
    flag_type: str
    severity: str
    status: str
    order_key: str
    symbol: str
    window_id: str
    placed_ts_iso: str
    terminal_ts_iso: str
    observed_value: str
    expected_value: str
    evidence: str
    notes: str


def stat_mtime_ms(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(path.stat().st_mtime * 1000)


def discover_json_files(repo_root: Path, boundary_hint_ms: int) -> list[Path]:
    files: list[Path] = []
    cutoff_ms = max(boundary_hint_ms - 12 * 3600000, 0)
    for base in (repo_root / "logs", repo_root / "frozen"):
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
    for path in files:
        rel = path.resolve()
        if rel in seen:
            continue
        seen.add(rel)
        deduped.append(path)
    return deduped


def discover_text_files(repo_root: Path, boundary_hint_ms: int) -> list[Path]:
    files: list[Path] = []
    search_roots = [repo_root / "logs", repo_root /
                    "logs" / "frozen", repo_root / "frozen"]
    cutoff_ms = max(boundary_hint_ms - 12 * 3600000, 0)
    for base in search_roots:
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
        rel = path.resolve()
        if rel in seen:
            continue
        seen.add(rel)
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


def cluster_window_starts(values: list[int]) -> list[int]:
    clustered: list[int] = []
    for value in sorted(set(values)):
        if not clustered or value - clustered[-1] > WINDOW_MARKER_GAP_MS:
            clustered.append(value)
    return clustered


def format_override_check(total_relevant: int, mismatch_count: int, missing_count: int) -> str:
    if total_relevant == 0:
        return "NO_RELEVANT_ROWS"
    if mismatch_count == 0 and missing_count == 0:
        return f"PASS all {total_relevant}/{total_relevant} Aurora LIMIT/GTX rows retained per_order_override=1200000"
    return (
        "FAIL "
        + f"mismatch={mismatch_count} missing_metadata={missing_count} out_of_relevant={total_relevant}"
    )


def build_flag_row(**kwargs) -> FlagRow:
    return FlagRow(
        flag_type=kwargs.get("flag_type", ""),
        severity=kwargs.get("severity", ""),
        status=kwargs.get("status", ""),
        order_key=kwargs.get("order_key", ""),
        symbol=kwargs.get("symbol", ""),
        window_id=kwargs.get("window_id", ""),
        placed_ts_iso=kwargs.get("placed_ts_iso", ""),
        terminal_ts_iso=kwargs.get("terminal_ts_iso", ""),
        observed_value=kwargs.get("observed_value", ""),
        expected_value=kwargs.get("expected_value", ""),
        evidence=kwargs.get("evidence", ""),
        notes=kwargs.get("notes", ""),
    )


def safe_float(value):
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def resolve_terminal_fill(placed_qty: float | None, fill_matches: list[tuple]):
    if not fill_matches:
        return None
    if placed_qty is None or placed_qty <= 0:
        return fill_matches[0]

    seen_fill_keys = set()
    cumulative_qty = 0.0
    for match in fill_matches:
        candidate = match[2]
        fill_key = fill_identity_key(candidate)
        if fill_key in seen_fill_keys:
            continue
        seen_fill_keys.add(fill_key)
        fill_qty = safe_float(candidate.get("quantity"))
        if fill_qty is None or fill_qty <= 0:
            continue
        cumulative_qty += fill_qty
        if cumulative_qty + 1e-9 >= placed_qty:
            return match
    return None


def main():
    repo_root = Path(__file__).resolve().parents[2]
    report_path = repo_root / REPORT_NAME
    order_csv_path = repo_root / ORDER_CSV_NAME
    window_csv_path = repo_root / WINDOW_CSV_NAME
    flags_csv_path = repo_root / FLAGS_CSV_NAME
    logs_dir = repo_root / "logs"
    t5d_report_path = repo_root / T5D_REPORT_NAME
    config_path = repo_root / CONFIG_PATH

    report_mtime_ms = stat_mtime_ms(t5d_report_path)
    config_mtime_ms = stat_mtime_ms(config_path)
    json_files = discover_json_files(repo_root, report_mtime_ms or 0)

    if not logs_dir.exists() or not json_files or report_mtime_ms is None or config_mtime_ms is None:
        order_fields = [
            "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm",
            "side", "order_type", "time_in_force", "placed_ts_ms", "placed_ts_iso", "fill_ttl_source",
            "fill_ttl_override_ms", "terminal_state", "terminal_ts_ms", "terminal_ts_iso",
            "age_to_terminal_ms", "age_to_first_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms",
            "join_method", "join_quality", "notes",
        ]
        window_fields = [
            "window_id", "start_ts_ms", "start_ts_iso", "end_ts_ms", "end_ts_iso",
            "orders_count", "metadata_orders_count", "aurora_limit_gtx_orders", "filled", "timeout",
            "canceled", "unknown", "terminal_join_rate",
        ]
        flag_fields = [field for field in FlagRow.__annotations__]
        for target, fields in (
            (order_csv_path, order_fields),
            (window_csv_path, window_fields),
            (flags_csv_path, flag_fields),
        ):
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                if target == flags_csv_path:
                    writer.writerow(
                        build_flag_row(
                            flag_type="BLOCKED_LOGS_MISSING",
                            severity="high",
                            status="diagnostic",
                            evidence="required log surfaces or T5D report/config path missing",
                            notes="T5E could not inspect post-calibration runtime surfaces",
                        ).__dict__
                    )
        report_path.write_text(
            "\n".join(
                [
                    "AGENT_REPORT_V1",
                    "",
                    "task: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR",
                    "verdict: BLOCKED_LOGS_MISSING",
                    f"report_path: {REPORT_NAME}",
                    "",
                    "facts:",
                    "- post_t5d_boundary: unavailable",
                    "- logs_inspected: missing required paths",
                    "",
                    "runtime_behavior_change:",
                    "- NONE",
                    "",
                    "config_changes:",
                    "- NONE",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print("verdict=BLOCKED_LOGS_MISSING")
        return

    text_files = discover_text_files(repo_root, report_mtime_ms)
    family_bounds: dict[str, list[int]] = {}
    startup_markers = []
    watchdog_text_markers = []
    ttl_markers_1800000 = []
    ttl_markers_3600000 = []
    relevant_events = []
    seen_fingerprints = set()
    scanned_files = set()

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
                if "ExecPosFSM TTL config:" in raw:
                    marker = {
                        "source_file": rel,
                        "line_no": line_no,
                        "ts_ms": ts_ms,
                        "message": raw.strip(),
                    }
                    startup_markers.append(marker)
                    if "fill_ttl_ms=1800000" in raw:
                        ttl_markers_1800000.append(marker)
                    elif "fill_ttl_ms=3600000" in raw:
                        ttl_markers_3600000.append(marker)
                elif any(token in raw for token in T5D.STARTUP_TOKENS):
                    startup_markers.append(
                        {
                            "source_file": rel,
                            "line_no": line_no,
                            "ts_ms": ts_ms,
                            "message": raw.strip(),
                        }
                    )
                if any(token in raw for token in T5D.WATCHDOG_TEXT_TOKENS):
                    watchdog_text_markers.append(
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
    first_order_after_report_ts = min(
        (event["ts_ms"]
         for event in placed_events if event["ts_ms"] >= report_mtime_ms),
        default=None,
    )
    first_runtime_1800000_ts = min(
        (
            marker["ts_ms"]
            for marker in ttl_markers_1800000
            if marker["ts_ms"] is not None and marker["ts_ms"] >= config_mtime_ms
        ),
        default=None,
    )

    boundary_candidates = []
    for label, ts_ms in (
        ("config_mtime", config_mtime_ms),
        ("report_mtime", report_mtime_ms),
        ("runtime_1800000_startup", first_runtime_1800000_ts),
        ("first_order_after_report", first_order_after_report_ts),
    ):
        if ts_ms is not None:
            boundary_candidates.append((label, ts_ms))

    boundary_source, boundary_ts = max(
        boundary_candidates, key=lambda item: item[1])
    post_events = [
        event for event in relevant_events if event["ts_ms"] >= boundary_ts]
    post_placed = [
        event for event in placed_events if event["ts_ms"] >= boundary_ts]

    post_boot_events = [
        event for event in post_events if event["event_type"] == "BOOT"]
    post_startup_markers = [
        marker for marker in startup_markers if marker["ts_ms"] is not None and marker["ts_ms"] >= boundary_ts
    ]
    post_ttl_1800000_markers = [
        marker for marker in ttl_markers_1800000 if marker["ts_ms"] is not None and marker["ts_ms"] >= boundary_ts
    ]
    post_ttl_3600000_markers = [
        marker for marker in ttl_markers_3600000 if marker["ts_ms"] is not None and marker["ts_ms"] >= boundary_ts
    ]

    window_markers = [boundary_ts]
    window_markers.extend(event["ts_ms"] for event in post_boot_events)
    window_markers.extend(marker["ts_ms"] for marker in post_startup_markers)
    window_starts = cluster_window_starts(window_markers)
    max_event_ts = max((event["ts_ms"]
                       for event in post_events), default=boundary_ts)
    window_specs = []
    for index, start_ts in enumerate(window_starts, start=1):
        next_start = window_starts[index] if index < len(
            window_starts) else None
        end_ts = (next_start - 1) if next_start is not None else max_event_ts
        window_specs.append(
            {
                "window_id": f"W{index:02d}",
                "start_ts_ms": start_ts,
                "end_ts_ms": end_ts,
            }
        )
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
        rid = placed["rid"]
        order_id = placed["order_id"]
        client_order_id = placed["client_order_id"]
        placed_qty = safe_float(placed.get("quantity"))

        fill_matches = []
        for method, candidates in (
            ("lifecycle_id", fills_by_lifecycle.get(rid, [])),
            ("client_order_id", fills_by_rid.get(client_order_id, [])),
            ("order_id", fills_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    fill_matches.append(
                        (candidate["ts_ms"], method, candidate))

        trade_matches = []
        for method, candidates in (
            ("trade_lifecycle_id", trades_by_lifecycle.get(rid, [])),
            ("trade_client_order_id", trades_by_rid.get(client_order_id, [])),
            ("trade_order_id", trades_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    trade_matches.append(
                        (candidate["ts_ms"], method, candidate))

        timeout_matches = []
        for method, candidates in (
            ("order_id", timeouts_by_order_id.get(order_id, [])),
            ("client_order_id", timeouts_by_client.get(client_order_id, [])),
            ("rid", timeouts_by_rid.get(rid, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    timeout_matches.append(
                        (candidate["ts_ms"], method, candidate))

        cancel_matches = []
        for method, candidates in (
            ("order_id", cancels_by_order_id.get(order_id, [])),
            ("client_order_id", cancels_by_client.get(client_order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] >= placed_ts:
                    cancel_matches.append(
                        (candidate["ts_ms"], method, candidate))

        position_closed_matches = []
        for candidate in position_closed_by_lifecycle.get(rid, []):
            if candidate["ts_ms"] >= placed_ts:
                position_closed_matches.append(
                    (candidate["ts_ms"], "position_closed.lifecycle_id", candidate))
        if not position_closed_matches:
            for candidate in position_closed_by_symbol.get(placed["symbol"], []):
                if candidate["ts_ms"] >= placed_ts:
                    position_closed_matches.append(
                        (candidate["ts_ms"], "position_closed.symbol", candidate))

        fill_matches.sort(key=lambda item: item[0])
        trade_matches.sort(key=lambda item: item[0])
        timeout_matches.sort(key=lambda item: item[0])
        cancel_matches.sort(key=lambda item: item[0])
        position_closed_matches.sort(key=lambda item: item[0])

        first_fill = fill_matches[0] if fill_matches else None
        terminal_fill = resolve_terminal_fill(placed_qty, fill_matches)
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
        if terminal and terminal[1] == "filled":
            corroborated = []
            if any(match[0] == terminal[0] and match[1] == "lifecycle_id" for match in fill_matches):
                corroborated.append("lifecycle_id")
            if any(match[0] == terminal[0] and match[1] == "client_order_id" for match in fill_matches):
                corroborated.append("client_order_id")
            if any(match[0] == terminal[0] and match[1] == "order_id" for match in fill_matches):
                corroborated.append("order_id")
            if len(corroborated) > 1:
                join_method = "+".join(corroborated)

        join_quality = "NONE"
        if terminal:
            if any(token in join_method for token in ("lifecycle_id", "order_id")) or "+" in join_method:
                join_quality = "HIGH"
            elif join_method:
                join_quality = "MEDIUM"

        notes = []
        if first_fill_like and first_fill_like[1].startswith("trade_"):
            notes.append(f"first_fill_via_{first_fill_like[1]}")
        if first_fill and terminal_fill is None:
            notes.append("non_terminal_fill_observed")
        if terminal and first_fill and terminal[1] != "filled" and first_fill[0] < terminal[0]:
            notes.append("fill_before_terminal")
        if not placed["fill_ttl_source_present"]:
            notes.append("fill_ttl_source_missing")
        if placed["fill_ttl_override_present"] and placed["fill_ttl_override_ms"] is None:
            notes.append("fill_ttl_override_ms_null")

        row = {
            "order_key": order_id or client_order_id or rid,
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
            "fill_ttl_source_present": placed["fill_ttl_source_present"],
            "fill_ttl_source": placed["fill_ttl_source"],
            "fill_ttl_override_present": placed["fill_ttl_override_present"],
            "fill_ttl_override_ms": placed["fill_ttl_override_ms"],
            "terminal_state": terminal[1] if terminal else "unknown",
            "terminal_ts_ms": terminal[0] if terminal else None,
            "terminal_ts_iso": T5D.iso_utc(terminal[0]) if terminal else "",
            "age_to_terminal_ms": (terminal[0] - placed_ts) if terminal else None,
            "age_to_first_fill_ms": (first_fill_like[0] - placed_ts) if first_fill_like else None,
            "age_to_timeout_ms": (first_timeout[0] - placed_ts) if first_timeout else None,
            "age_to_cancel_ms": (first_cancel[0] - placed_ts) if first_cancel else None,
            "join_method": join_method,
            "join_quality": join_quality,
            "notes": "; ".join(notes),
            "client_order_id": client_order_id,
            "order_id": order_id,
            "rid": rid,
            "timeframe_sec": placed["timeframe_sec"],
            "metadata_bearing": placed["fill_ttl_source_present"] and placed["fill_ttl_override_present"],
            "first_fill_ts_ms": first_fill_like[0] if first_fill_like else None,
            "position_closed_ts_ms": position_closed_matches[0][0] if position_closed_matches else None,
            "position_closed_method": position_closed_matches[0][1] if position_closed_matches else "",
        }
        row["is_calibration_relevant"] = T5D.detect_calibration_relevant(row)
        order_rows.append(row)

    order_rows.sort(key=lambda row: (row["placed_ts_ms"], row["order_key"]))
    global_metrics = T5D.compute_metrics(order_rows)
    runtime_span_ms = max(max_event_ts - boundary_ts, 0)
    runtime_hours = runtime_span_ms / 3600000.0
    relevant_rows = [
        row for row in order_rows if row["is_calibration_relevant"]]
    relevant_metadata_rows = [
        row for row in relevant_rows if row["metadata_bearing"]]
    relevant_known_terminal_rows = [
        row for row in relevant_rows if row["terminal_state"] != "unknown"]
    relevant_join_rate = (
        len(relevant_known_terminal_rows) /
        len(relevant_rows) if relevant_rows else 0.0
    )
    close_executor_unknown_rows = [
        row
        for row in order_rows
        if row["terminal_state"] == "unknown" and row["source_fsm"] == "CloseExecutor"
    ]
    relevant_unknown_rows = [
        row for row in relevant_rows if row["terminal_state"] == "unknown"]
    minimum_sample_met = runtime_hours >= MIN_RUNTIME_HOURS and global_metrics[
        "total_order_placed"] >= MIN_POST_T5D_ORDER_PLACED
    preferred_sample_met = runtime_hours >= PREFERRED_RUNTIME_HOURS and global_metrics[
        "aurora_entry_limit_gtx_orders"] >= PREFERRED_AURORA_LIMIT_GTX
    global_watchdog_rows = [
        row for row in order_rows if row["fill_ttl_source"] == "global_watchdog"]
    relevant_override_mismatch_rows = [
        row
        for row in relevant_rows
        if not row["metadata_bearing"]
        or row["fill_ttl_source"] != "per_order_override"
        or row["fill_ttl_override_ms"] != EXPECTED_PER_ORDER_OVERRIDE_MS
    ]
    relevant_missing_metadata_rows = [
        row for row in relevant_rows if not row["metadata_bearing"]]
    relevant_timeout_rows = [
        row for row in relevant_rows if row["age_to_timeout_ms"] is not None]
    relevant_timeout_near_20m_rows = [
        row
        for row in relevant_timeout_rows
        if abs(row["age_to_timeout_ms"] - EXPECTED_PER_ORDER_OVERRIDE_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    relevant_timeout_near_30m_rows = [
        row
        for row in relevant_timeout_rows
        if abs(row["age_to_timeout_ms"] - EXPECTED_GLOBAL_WATCHDOG_TTL_MS) <= TIMEOUT_TOLERANCE_MS
    ]
    relevant_global_backstop_timeout_rows = [
        row
        for row in relevant_timeout_near_30m_rows
        if not row["metadata_bearing"] or row["fill_ttl_source"] == "global_watchdog"
    ]
    relevant_override_timeout_near_30m_rows = [
        row
        for row in relevant_timeout_near_30m_rows
        if row["metadata_bearing"]
        and row["fill_ttl_source"] == "per_order_override"
        and row["fill_ttl_override_ms"] == EXPECTED_PER_ORDER_OVERRIDE_MS
    ]

    stale_suspicions = []
    timeout_rows = [
        row for row in order_rows if row["age_to_timeout_ms"] is not None]
    for row in timeout_rows:
        reasons = []
        timeout_ts = row["placed_ts_ms"] + row["age_to_timeout_ms"]
        if row["terminal_state"] in {"filled", "canceled"} and row["terminal_ts_ms"] and timeout_ts > row["terminal_ts_ms"]:
            reasons.append("timeout_after_known_terminal")
        if row["terminal_state"] == "filled" and row["terminal_ts_ms"] and timeout_ts > row["terminal_ts_ms"]:
            reasons.append("timeout_after_fill")
        if row["position_closed_ts_ms"] and timeout_ts > row["position_closed_ts_ms"]:
            if row["position_closed_method"] == "position_closed.lifecycle_id":
                reasons.append("timeout_after_position_closed_lifecycle_match")
            elif row["position_closed_method"] == "position_closed.symbol":
                reasons.append("timeout_after_position_closed_symbol_only")
        if reasons:
            stale_suspicions.append(
                {
                    "order_key": row["order_key"],
                    "symbol": row["symbol"],
                    "window_id": row["window_id"],
                    "placed_ts_ms": row["placed_ts_ms"],
                    "timeout_ts_ms": timeout_ts,
                    "terminal_ts_ms": row["terminal_ts_ms"],
                    "position_closed_ts_ms": row["position_closed_ts_ms"],
                    "position_closed_method": row["position_closed_method"],
                    "reasons": reasons,
                }
            )

    if not timeout_rows:
        stale_watchdog_verdict = "INSUFFICIENT_EVIDENCE"
    elif any(
        any(
            reason in item["reasons"]
            for reason in (
                "timeout_after_fill",
                "timeout_after_known_terminal",
                "timeout_after_position_closed_lifecycle_match",
            )
        )
        for item in stale_suspicions
    ):
        stale_watchdog_verdict = "STALE_WATCHDOG_CONFIRMED"
    elif stale_suspicions:
        stale_watchdog_verdict = "STALE_WATCHDOG_SUSPECTED"
    else:
        stale_watchdog_verdict = "NO_STALE_WATCHDOG_AFTER_T5D"

    global_watchdog_cases = []
    for row in global_watchdog_rows:
        classification = "safe"
        notes = []
        if row["terminal_state"] == "timeout" and row["age_to_timeout_ms"] is not None:
            if row["age_to_timeout_ms"] < EXPECTED_GLOBAL_WATCHDOG_TTL_MS - TIMEOUT_TOLERANCE_MS:
                classification = "suspicious"
                notes.append("timeout_before_expected_global_backstop")
            elif row["age_to_timeout_ms"] > EXPECTED_GLOBAL_WATCHDOG_TTL_MS + TIMEOUT_TOLERANCE_MS:
                classification = "suspicious"
                notes.append("timeout_after_expected_global_backstop")
            else:
                notes.append("timeout_near_expected_global_backstop")
        elif row["terminal_state"] == "unknown":
            classification = "suspicious"
            notes.append("unknown_terminal_state")
        elif row["terminal_state"] in {"filled", "canceled"}:
            notes.append("terminal_before_or_without_global_timeout")
        global_watchdog_cases.append(
            {
                "row": row,
                "classification": classification,
                "notes": notes,
            }
        )

    flag_rows: list[FlagRow] = []
    if relevant_override_mismatch_rows:
        for row in relevant_override_mismatch_rows:
            observed_bits = []
            if not row["metadata_bearing"]:
                observed_bits.append("metadata_missing")
            else:
                observed_bits.append(
                    f"fill_ttl_source={row['fill_ttl_source']}")
                observed_bits.append(
                    f"fill_ttl_override_ms={row['fill_ttl_override_ms']}")
            flag_rows.append(
                build_flag_row(
                    flag_type="PER_ORDER_OVERRIDE_CONTRACT_MISMATCH",
                    severity="high",
                    status="open",
                    order_key=row["order_key"],
                    symbol=row["symbol"],
                    window_id=row["window_id"],
                    placed_ts_iso=row["placed_ts_iso"],
                    terminal_ts_iso=row["terminal_ts_iso"],
                    observed_value="; ".join(observed_bits),
                    expected_value="fill_ttl_source=per_order_override; fill_ttl_override_ms=1200000",
                    evidence=f"source_file={row['source_file']}",
                    notes="Aurora LIMIT/GTX operative TTL contract diverged post-T5D",
                )
            )

    for row in relevant_global_backstop_timeout_rows:
        flag_rows.append(
            build_flag_row(
                flag_type="OVERRIDE_TIMEOUT_NEAR_30MIN",
                severity="critical",
                status="open",
                order_key=row["order_key"],
                symbol=row["symbol"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=str(row["age_to_timeout_ms"]),
                expected_value=f"near {EXPECTED_PER_ORDER_OVERRIDE_MS}",
                evidence=f"fill_ttl_source={row['fill_ttl_source']} fill_ttl_override_ms={row['fill_ttl_override_ms']}",
                notes="Aurora LIMIT/GTX timeout drifted toward global 30-minute backstop",
            )
        )

    for row in relevant_override_timeout_near_30m_rows:
        notes = "per-order override metadata retained, but timeout still drifted toward global 30-minute backstop"
        if row["age_to_first_fill_ms"] is not None:
            notes += "; non-terminal fill was observed before timeout"
        flag_rows.append(
            build_flag_row(
                flag_type="OVERRIDE_NOT_APPLIED_TIMEOUT_NEAR_30MIN",
                severity="critical",
                status="open",
                order_key=row["order_key"],
                symbol=row["symbol"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=str(row["age_to_timeout_ms"]),
                expected_value=f"near {EXPECTED_PER_ORDER_OVERRIDE_MS}",
                evidence=(
                    f"fill_ttl_source={row['fill_ttl_source']} "
                    + f"fill_ttl_override_ms={row['fill_ttl_override_ms']} "
                    + f"age_to_first_fill_ms={row['age_to_first_fill_ms']}"
                ),
                notes=notes,
            )
        )

    for case in global_watchdog_cases:
        if case["classification"] == "safe":
            status = "observed_safe"
            severity = "low"
        elif case["classification"] == "suspicious":
            status = "open"
            severity = "medium"
        else:
            status = "open"
            severity = "critical"
        row = case["row"]
        flag_rows.append(
            build_flag_row(
                flag_type="GLOBAL_WATCHDOG_CASE",
                severity=severity,
                status=status,
                order_key=row["order_key"],
                symbol=row["symbol"],
                window_id=row["window_id"],
                placed_ts_iso=row["placed_ts_iso"],
                terminal_ts_iso=row["terminal_ts_iso"],
                observed_value=f"terminal_state={row['terminal_state']}; age_to_timeout_ms={row['age_to_timeout_ms']}",
                expected_value=f"global_backstop={EXPECTED_GLOBAL_WATCHDOG_TTL_MS}",
                evidence=f"fill_ttl_source={row['fill_ttl_source']}",
                notes="; ".join(
                    case["notes"]) or "global watchdog path observed",
            )
        )

    for item in stale_suspicions:
        if any(
            reason in item["reasons"]
            for reason in (
                "timeout_after_fill",
                "timeout_after_known_terminal",
                "timeout_after_position_closed_lifecycle_match",
            )
        ):
            severity = "critical"
            status = "open"
        else:
            severity = "low"
            status = "suspected"
        flag_rows.append(
            build_flag_row(
                flag_type="STALE_WATCHDOG_CHECK",
                severity=severity,
                status=status,
                order_key=item["order_key"],
                symbol=item["symbol"],
                window_id=item["window_id"],
                placed_ts_iso=T5D.iso_utc(item["placed_ts_ms"]),
                terminal_ts_iso=T5D.iso_utc(item["timeout_ts_ms"]),
                observed_value=",".join(item["reasons"]),
                expected_value="no timeout after terminal state",
                evidence=(
                    f"timeout={T5D.iso_utc(item['timeout_ts_ms'])}; "
                    + f"position_closed_method={item['position_closed_method']}"
                ),
                notes="symbol-only fallback remains suspected unless lifecycle identity matches",
            )
        )

    if not post_ttl_1800000_markers:
        flag_rows.append(
            build_flag_row(
                flag_type="GLOBAL_BACKSTOP_RUNTIME_MARKER_UNPROVEN",
                severity="low",
                status="residual",
                observed_value="no exact post-boundary ExecPosFSM TTL config line with fill_ttl_ms=1800000 retained",
                expected_value=f"post-boundary runtime marker for {EXPECTED_GLOBAL_WATCHDOG_TTL_MS}",
                evidence=f"text_files_scanned={len(text_files)} post_boundary_markers={len(post_startup_markers)}",
                notes="config truth is 1800000, but retained text runtime proof is absent",
            )
        )

    if not minimum_sample_met:
        flag_rows.append(
            build_flag_row(
                flag_type="NOT_ENOUGH_POST_T5D_RUNTIME",
                severity="low",
                status="diagnostic",
                observed_value=(
                    f"runtime_hours={runtime_hours:.2f}; "
                    + f"post_t5d_order_placed_total={global_metrics['total_order_placed']}"
                ),
                expected_value=(
                    f"runtime_hours>={MIN_RUNTIME_HOURS}; "
                    + f"post_t5d_order_placed_total>={MIN_POST_T5D_ORDER_PLACED}"
                ),
                evidence=f"boundary={T5D.iso_utc(boundary_ts)} source={boundary_source}",
                notes="explicit 1800000 runtime startup was observed, but retained post-boundary order sample is still below minimum",
            )
        )
    elif runtime_hours < PREFERRED_RUNTIME_HOURS or global_metrics["aurora_entry_limit_gtx_orders"] < PREFERRED_AURORA_LIMIT_GTX:
        flag_rows.append(
            build_flag_row(
                flag_type="SAMPLE_BELOW_PREFERRED",
                severity="low",
                status="residual",
                observed_value=(
                    f"runtime_hours={runtime_hours:.2f}; "
                    + f"aurora_limit_gtx_entries={global_metrics['aurora_entry_limit_gtx_orders']}"
                ),
                expected_value=f"runtime_hours>={PREFERRED_RUNTIME_HOURS}; aurora_limit_gtx_entries>={PREFERRED_AURORA_LIMIT_GTX}",
                evidence=f"post_t5d_order_placed_total={global_metrics['total_order_placed']}",
                notes="minimum sample passed, preferred post-calibration sample not yet reached",
            )
        )

    if not flag_rows:
        flag_rows.append(
            build_flag_row(
                flag_type="NO_REGRESSION_FLAGS",
                severity="info",
                status="clear",
                observed_value="none",
                expected_value="none",
                evidence="all focused T5E checks clear",
                notes="no post-calibration regression indicators detected",
            )
        )

    window_rows = []
    order_rows_by_window = defaultdict(list)
    for row in order_rows:
        order_rows_by_window[row["window_id"]].append(row)

    for spec in window_specs:
        window_id = spec["window_id"]
        rows = order_rows_by_window.get(window_id, [])
        metrics = T5D.compute_metrics(rows)
        window_row = {
            "window_id": window_id,
            "start_ts_ms": spec["start_ts_ms"],
            "start_ts_iso": T5D.iso_utc(spec["start_ts_ms"]),
            "end_ts_ms": spec["end_ts_ms"],
            "end_ts_iso": T5D.iso_utc(spec["end_ts_ms"]),
            "orders_count": metrics["total_order_placed"],
            "metadata_orders_count": metrics["metadata_bearing_order_placed"],
            "aurora_limit_gtx_orders": metrics["aurora_entry_limit_gtx_orders"],
            "fill_ttl_source_per_order_override": metrics["fill_ttl_source_per_order_override"],
            "fill_ttl_source_global_watchdog": metrics["fill_ttl_source_global_watchdog"],
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
        add_dist_fields(window_row, "age_to_timeout_ms", [
                        row["age_to_timeout_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_cancel_ms", [
                        row["age_to_cancel_ms"] for row in rows])
        add_dist_fields(window_row, "age_to_terminal_ms", [
                        row["age_to_terminal_ms"] for row in rows])
        window_rows.append(window_row)

    fill_ttl_override_values = sorted(
        {
            row["fill_ttl_override_ms"]
            for row in order_rows
            if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None
        }
    )
    first_fill_summary = T5D.dist_summary(
        [row["age_to_first_fill_ms"] for row in order_rows])
    timeout_summary = T5D.dist_summary(
        [row["age_to_timeout_ms"] for row in order_rows])
    cancel_summary = T5D.dist_summary(
        [row["age_to_cancel_ms"] for row in order_rows])
    terminal_summary = T5D.dist_summary(
        [row["age_to_terminal_ms"] for row in order_rows])

    per_order_override_dominates = not relevant_override_mismatch_rows and bool(
        relevant_rows)
    accidental_30min_timeout = bool(relevant_global_backstop_timeout_rows)
    override_timeout_near_30m = bool(relevant_override_timeout_near_30m_rows)
    runtime_global_marker_confirmed = bool(post_ttl_1800000_markers)
    post_boundary_old_runtime_marker = bool(post_ttl_3600000_markers)
    global_watchdog_regression = any(
        case["classification"] == "regression" for case in global_watchdog_cases)
    global_watchdog_suspicious = any(
        case["classification"] == "suspicious" for case in global_watchdog_cases)
    lifecycle_regression = stale_watchdog_verdict == "STALE_WATCHDOG_CONFIRMED"
    warning_condition = (
        relevant_join_rate < 0.95
        or not relevant_rows
        or not per_order_override_dominates
    )
    residual_condition = (
        not preferred_sample_met
        or not runtime_global_marker_confirmed
        or stale_watchdog_verdict == "STALE_WATCHDOG_SUSPECTED"
        or global_watchdog_suspicious
        or bool(close_executor_unknown_rows)
    )

    if not minimum_sample_met:
        verdict = "NOT_ENOUGH_POST_T5D_RUNTIME"
    elif post_boundary_old_runtime_marker or accidental_30min_timeout or override_timeout_near_30m or lifecycle_regression or global_watchdog_regression:
        verdict = "POST_CALIBRATION_REGRESSION_DETECTED"
    elif warning_condition:
        verdict = "POST_CALIBRATION_WARNING"
    elif residual_condition:
        verdict = "POST_CALIBRATION_HEALTHY_WITH_RESIDUALS"
    else:
        verdict = "POST_CALIBRATION_HEALTHY"

    order_fields = [
        "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm", "side",
        "order_type", "time_in_force", "placed_ts_ms", "placed_ts_iso", "fill_ttl_source",
        "fill_ttl_override_ms", "terminal_state", "terminal_ts_ms", "terminal_ts_iso",
        "age_to_terminal_ms", "age_to_first_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms",
        "join_method", "join_quality", "notes",
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
                {"notes": "diagnostic_only:no_post_t5d_order_rows"})

    window_fields = [
        "window_id", "start_ts_ms", "start_ts_iso", "end_ts_ms", "end_ts_iso", "orders_count",
        "metadata_orders_count", "aurora_limit_gtx_orders", "fill_ttl_source_per_order_override",
        "fill_ttl_source_global_watchdog", "filled", "timeout", "canceled", "unknown",
        "terminal_join_rate", "symbols", "strategies", "source_fsms",
        "age_to_first_fill_ms_count", "age_to_first_fill_ms_min", "age_to_first_fill_ms_p50",
        "age_to_first_fill_ms_p75", "age_to_first_fill_ms_p90", "age_to_first_fill_ms_p95",
        "age_to_first_fill_ms_p99", "age_to_first_fill_ms_max", "age_to_timeout_ms_count",
        "age_to_timeout_ms_min", "age_to_timeout_ms_p50", "age_to_timeout_ms_p75",
        "age_to_timeout_ms_p90", "age_to_timeout_ms_p95", "age_to_timeout_ms_p99",
        "age_to_timeout_ms_max", "age_to_cancel_ms_count", "age_to_cancel_ms_min",
        "age_to_cancel_ms_p50", "age_to_cancel_ms_p75", "age_to_cancel_ms_p90",
        "age_to_cancel_ms_p95", "age_to_cancel_ms_p99", "age_to_cancel_ms_max",
        "age_to_terminal_ms_count", "age_to_terminal_ms_min", "age_to_terminal_ms_p50",
        "age_to_terminal_ms_p75", "age_to_terminal_ms_p90", "age_to_terminal_ms_p95",
        "age_to_terminal_ms_p99", "age_to_terminal_ms_max",
    ]
    with window_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=window_fields)
        writer.writeheader()
        if window_rows:
            for row in window_rows:
                writer.writerow({field: csv_value(row.get(field))
                                for field in window_fields})
        else:
            writer.writerow({"window_id": "W01", "orders_count": 0})

    flag_fields = [field for field in FlagRow.__annotations__]
    with flags_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=flag_fields)
        writer.writeheader()
        for row in flag_rows:
            writer.writerow({field: csv_value(getattr(row, field))
                            for field in flag_fields})

    boundary_lines = [
        f"{label}={T5D.iso_utc(ts_ms)}" for label, ts_ms in boundary_candidates]
    window_lines = [
        "- "
        + f"{row['window_id']} {row['start_ts_iso']} -> {row['end_ts_iso']} orders={row['orders_count']} "
        + f"metadata={row['metadata_orders_count']} aurora_limit_gtx={row['aurora_limit_gtx_orders']} "
        + f"join_rate={row['terminal_join_rate']}"
        for row in window_rows
    ]
    if not window_lines:
        window_lines = ["- none"]

    global_watchdog_lines = []
    for case in global_watchdog_cases[:10]:
        row = case["row"]
        global_watchdog_lines.append(
            "- "
            + f"{row['order_key']} {row['symbol']} classification={case['classification']} "
            + f"terminal={row['terminal_state']} age_to_timeout_ms={row['age_to_timeout_ms']} notes={';'.join(case['notes']) or 'none'}"
        )
    if not global_watchdog_lines:
        global_watchdog_lines.append("- none")

    override_timeout_lines = []
    for row in relevant_override_timeout_near_30m_rows[:10]:
        override_timeout_lines.append(
            "- "
            + f"{row['order_key']} {row['symbol']} terminal={row['terminal_state']} "
            + f"age_to_timeout_ms={row['age_to_timeout_ms']} age_to_first_fill_ms={row['age_to_first_fill_ms']} "
            + f"fill_ttl_source={row['fill_ttl_source']} fill_ttl_override_ms={row['fill_ttl_override_ms']}"
        )
    if not override_timeout_lines:
        override_timeout_lines.append("- none")

    stale_lines = []
    for item in stale_suspicions[:10]:
        stale_lines.append(
            "- "
            + f"{item['order_key']} {item['symbol']} placed={T5D.iso_utc(item['placed_ts_ms'])} "
            + f"timeout={T5D.iso_utc(item['timeout_ts_ms'])} position_closed={T5D.iso_utc(item['position_closed_ts_ms'])} "
            + f"position_closed_method={item['position_closed_method']} reasons={','.join(item['reasons'])}"
        )
    if not stale_lines:
        stale_lines.append("- none")

    config_truth_line = (
        f"SSOT config={EXPECTED_GLOBAL_WATCHDOG_TTL_MS}; runtime_marker_confirmed={len(post_ttl_1800000_markers)}; "
        + f"post_boundary_old_marker={len(post_ttl_3600000_markers)}"
    )
    override_truth_line = (
        f"expected={EXPECTED_PER_ORDER_OVERRIDE_MS}; observed_values={join_list([str(v) for v in fill_ttl_override_values])}; "
        + f"relevant_timeout_near_20m={len(relevant_timeout_near_20m_rows)}/{len(relevant_timeout_rows)}"
    )
    global_watchdog_line = (
        f"observed_cases={len(global_watchdog_cases)}; runtime_ttl_marker={len(post_ttl_1800000_markers)}"
    )

    verdict_rationale = []
    if minimum_sample_met:
        verdict_rationale.append(
            f"minimum post-T5D sample met: runtime_hours={runtime_hours:.2f}, post_t5d_order_placed_total={global_metrics['total_order_placed']}"
        )
    else:
        verdict_rationale.append(
            f"minimum post-T5D sample not met: runtime_hours={runtime_hours:.2f}, post_t5d_order_placed_total={global_metrics['total_order_placed']}"
        )
    verdict_rationale.append(format_override_check(len(relevant_rows), len(
        relevant_override_mismatch_rows), len(relevant_missing_metadata_rows)))
    verdict_rationale.append(
        f"override timeout distribution near 20m: {len(relevant_timeout_near_20m_rows)}/{len(relevant_timeout_rows)} relevant timeout rows"
    )
    verdict_rationale.append(
        f"any 30m global backstop timeout on calibration path: {'YES' if accidental_30min_timeout else 'NO'}"
    )
    verdict_rationale.append(
        f"per-order override timeout still near 30m: {'YES' if override_timeout_near_30m else 'NO'}"
    )
    verdict_rationale.append(
        f"stale watchdog verdict: {stale_watchdog_verdict}"
    )
    if close_executor_unknown_rows and not relevant_unknown_rows:
        verdict_rationale.append(
            "overall unknown joins are isolated to non-calibration CloseExecutor market rows; calibration-relevant join rate remained complete"
        )

    runtime_behavior_lines = []
    if override_timeout_near_30m:
        runtime_behavior_lines.append(
            f"- per_order_override_timeout_near_30m: count={len(relevant_override_timeout_near_30m_rows)}"
        )
    if accidental_30min_timeout:
        runtime_behavior_lines.append(
            f"- global_backstop_timeout_near_30m: count={len(relevant_global_backstop_timeout_rows)}"
        )
    if not runtime_behavior_lines:
        runtime_behavior_lines.append("- NONE")

    risks = []
    if not runtime_global_marker_confirmed:
        risks.append(
            "exact post-boundary runtime proof for global 1800000 backstop is not retained in text logs")
    if not minimum_sample_met:
        risks.append("explicit 1800000 runtime startup is retained, but runtime collected after that boundary is still below the minimum 24h / 30 ORDER_PLACED sample")
    elif not preferred_sample_met:
        risks.append(
            "preferred 48h / 50 metadata-bearing Aurora LIMIT/GTX sample is not yet reached")
    if stale_watchdog_verdict == "STALE_WATCHDOG_SUSPECTED":
        risks.append(
            "symbol-only stale-watchdog suspicion remains unconfirmed at lifecycle identity level")
    if override_timeout_near_30m:
        risks.append(
            "per-order override metadata was retained on at least one Aurora LIMIT/GTX row whose timeout still drifted toward 1800000"
        )
    if global_watchdog_cases:
        risks.append(
            "global_watchdog path exists and should keep being monitored until more cases accumulate")
    if close_executor_unknown_rows and not relevant_unknown_rows:
        risks.append(
            f"overall terminal join rate is diluted by {len(close_executor_unknown_rows)} non-calibration CloseExecutor market rows with no retained terminal join"
        )
    if not risks:
        risks.append("none")

    unproven = []
    if not minimum_sample_met:
        unproven.append(
            "post-boundary order behavior after the explicit 1800000 runtime startup remains unproven")
    if not runtime_global_marker_confirmed:
        unproven.append(
            "post-boundary ExecPosFSM TTL config line with fill_ttl_ms=1800000 was not retained")
    if not global_watchdog_cases:
        unproven.append(
            "global_watchdog order path remains unobserved in post-T5D ORDER_PLACED metadata")
    if stale_watchdog_verdict == "STALE_WATCHDOG_SUSPECTED":
        unproven.append(
            "symbol-only timeout-after-position-closed remains suspected, not lifecycle-confirmed")
    if not unproven:
        unproven.append("none")

    if verdict in {"POST_CALIBRATION_HEALTHY", "POST_CALIBRATION_HEALTHY_WITH_RESIDUALS"}:
        next_package = "close T5 timer-governance line or move to next timer family"
    elif verdict in {"POST_CALIBRATION_WARNING", "POST_CALIBRATION_REGRESSION_DETECTED"}:
        next_package = "create bounded DEF package for the flagged regression surface"
    else:
        next_package = "continue runtime collection until minimum post-T5D sample is met"

    report_lines = [
        "AGENT_REPORT_V1",
        "",
        "task: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR",
        f"verdict: {verdict}",
        f"report_path: {REPORT_NAME}",
        "",
        "facts:",
        f"- post_t5d_boundary: {T5D.iso_utc(boundary_ts)} ({boundary_source}; candidates: {'; '.join(boundary_lines)})",
        f"- logs_inspected: json={len(json_files)} text={len(text_files)} report=1 config=1 scanned_files={len(scanned_files)}",
        f"- runtime_windows: {len(window_rows)}",
        f"- total_order_placed: {global_metrics['total_order_placed']}",
        f"- metadata_order_placed: {global_metrics['metadata_bearing_order_placed']}",
        f"- aurora_limit_gtx_entries: {global_metrics['aurora_entry_limit_gtx_orders']}",
        f"- terminal_joins: filled={global_metrics['filled']} timeout={global_metrics['timeout']} canceled={global_metrics['canceled']} unknown={global_metrics['unknown']} rate={global_metrics['terminal_join_rate']:.3f}",
        f"- calibration_relevant_terminal_join_rate: {relevant_join_rate:.3f} ({len(relevant_known_terminal_rows)}/{len(relevant_rows) if relevant_rows else 0})",
        f"- symbols: {join_list(global_metrics['symbols_observed'])}",
        f"- strategies: {join_list(global_metrics['strategies_observed'])}",
        f"- source_fsms: {join_list(global_metrics['source_fsms_observed'])}",
        f"- post_t5d_runtime_hours: {runtime_hours:.2f}",
        f"- preferred_sample_met: {'YES' if preferred_sample_met else 'NO'}",
        "",
        "config_truth:",
        f"- trading.execution.watchdog.fill_ttl_ms observed/confirmed: {config_truth_line}",
        f"- per_order_override expected: {override_truth_line}",
        f"- global_watchdog observed: {global_watchdog_line}",
        "",
        "runtime_windows:",
        *window_lines,
        "",
        "timing_distributions:",
        f"- age_to_first_fill_ms: {T5D.format_dist(first_fill_summary)}",
        f"- age_to_timeout_ms: {T5D.format_dist(timeout_summary)}",
        f"- age_to_cancel_ms: {T5D.format_dist(cancel_summary)}",
        f"- age_to_terminal_ms: {T5D.format_dist(terminal_summary)}",
        "",
        "regression_checks:",
        f"- per_order_override_dominates: {format_override_check(len(relevant_rows), len(relevant_override_mismatch_rows), len(relevant_missing_metadata_rows))}",
        f"- any_30min_global_backstop_timeout: {'FAIL' if accidental_30min_timeout else 'PASS'} count={len(relevant_global_backstop_timeout_rows)}",
        f"- per_order_override_timeout_near_30m: {'FAIL' if override_timeout_near_30m else 'PASS'} count={len(relevant_override_timeout_near_30m_rows)}",
        *override_timeout_lines,
        f"- global_watchdog_cases: count={len(global_watchdog_cases)}",
        *global_watchdog_lines,
        f"- stale_watchdog_check: {stale_watchdog_verdict}",
        *stale_lines,
        "",
        "verdict_rationale:",
        *[f"- {line}" for line in verdict_rationale],
        "",
        "runtime_behavior_change:",
        *runtime_behavior_lines,
        "",
        "config_changes:",
        "- NONE",
        "",
        "unproven:",
        *[f"- {line}" for line in unproven],
        "",
        "risks:",
        *[f"- {line}" for line in risks],
        "",
        "next_recommended_package:",
        f"- {next_package}",
    ]

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"verdict={verdict}")
    print(f"post_t5d_boundary={T5D.iso_utc(boundary_ts)}")
    print(
        f"post_t5d_order_placed_total={global_metrics['total_order_placed']}")
    print(
        f"metadata_bearing_order_placed={global_metrics['metadata_bearing_order_placed']}")
    print(
        f"aurora_limit_gtx_entries={global_metrics['aurora_entry_limit_gtx_orders']}")
    print(f"terminal_join_rate={global_metrics['terminal_join_rate']:.3f}")
    print(f"runtime_global_marker_confirmed={len(post_ttl_1800000_markers)}")
    print(f"report={REPORT_NAME}")


if __name__ == "__main__":
    main()
