#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


CANDIDATE_TTLS = [60000, 120000, 300000, 600000, 1200000, 1800000, 3600000]
TARGET_EVENT_TYPES = {
    "BOOT",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "ORDER_TIMEOUT",
    "ORDER_CANCELLED",
    "TRADE_EXECUTED",
    "POSITION_CLOSED",
}
TARGET_SUBSTRINGS = (
    '"event_type": "BOOT"',
    '"event_type": "ORDER_PLACED"',
    '"event_type": "ORDER_FILLED"',
    '"event_type": "ORDER_TIMEOUT"',
    '"event_type": "ORDER_CANCELLED"',
    '"event_type": "TRADE_EXECUTED"',
    '"event_type": "POSITION_CLOSED"',
    '"fill_ttl_source"',
    '"fill_ttl_override_ms"',
)
TEXT_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
EMBEDDED_TS_MS_RE = re.compile(r'"ts_ms"\s*:\s*(\d{10,16})')
STARTUP_TOKENS = (
    "STARTUP_BASIS_IMPORTED",
    "STARTUP_BASIS_SEEDED",
    "seed_startup_bars",
    "OrderGuardian startup reconciliation",
    "OrderGuardian startup reconciliation completed",
    "OrderTimeoutWatchdog late-started",
    "ExecPosFSM TTL config:",
)
WATCHDOG_TEXT_TOKENS = (
    "Order timeout:",
    "fill_timeout",
    "WATCHDOG_RECOVERED_FILL_CANONICAL_EMIT",
    "PARTIAL_FILL_WATCHDOG_RETAINED",
)


def safe_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return int(value)
    try:
        text = str(value).strip()
        if not text:
            return None
        if "." in text:
            return int(float(text))
        return int(text)
    except Exception:
        return None


def safe_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def iso_utc(ms):
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_text_datetime(text):
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def family_key(rel_path: str) -> str:
    parts = rel_path.split("/")
    name = parts[-1]
    bundle_prefix = None
    if rel_path.startswith("frozen/") and len(parts) >= 2:
        bundle_prefix = "/".join(parts[:2])
    elif rel_path.startswith("logs/frozen/") and len(parts) >= 3:
        bundle_prefix = "/".join(parts[:3])

    if name.startswith("aurora_core.log"):
        return f"{bundle_prefix}/logs/aurora_core.log*" if bundle_prefix else "logs/aurora_core.log*"
    if name.startswith("domain_execution_position.log"):
        return (
            f"{bundle_prefix}/logs/domain_execution_position.log*"
            if bundle_prefix
            else "logs/domain_execution_position.log*"
        )
    if name.startswith("event_chain.log"):
        return f"{bundle_prefix}/logs/event_chain.log*" if bundle_prefix else "logs/event_chain.log*"
    return rel_path


def update_bounds(bounds_map, key, ts_ms):
    if ts_ms is None:
        return
    current = bounds_map.get(key)
    if current is None:
        bounds_map[key] = [ts_ms, ts_ms]
        return
    if ts_ms < current[0]:
        current[0] = ts_ms
    if ts_ms > current[1]:
        current[1] = ts_ms


def stringify(value):
    if value is None:
        return ""
    return str(value)


def nested_first(obj, keys):
    stack = [obj]
    seen = set()
    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        if isinstance(current, dict):
            for key in keys:
                if key in current and current[key] not in (None, "", [], {}):
                    return current[key]
            for value in current.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            for value in current:
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return None


def extract_timestamp(payload):
    for key in ("timestamp", "ts_ms", "timestamp_ms"):
        value = safe_int(payload.get(key)) if isinstance(
            payload, dict) else None
        if value is not None:
            return value
    return None


def infer_strategy(payload, rid, lifecycle_id, source_fsm):
    explicit = payload.get("strategy_id") if isinstance(
        payload, dict) else None
    if explicit:
        return str(explicit)
    explicit = nested_first(payload, ("strategy_id",))
    if explicit:
        return str(explicit)
    probe = rid or lifecycle_id or ""
    for prefix in ("aurora", "md_amr", "mean_reversion", "llm_microstructure"):
        if probe.startswith(prefix + "_") or probe.startswith(prefix + ":"):
            return prefix
    if source_fsm == "CloseExecutor":
        return "close_executor"
    return "unknown"


def standardize_event(payload, rel_path, line_no):
    adapter = payload.get("adapter_response") if isinstance(
        payload.get("adapter_response"), dict) else {}
    metadata = payload.get("metadata") if isinstance(
        payload.get("metadata"), dict) else {}
    timestamp = extract_timestamp(payload)
    rid = stringify(payload.get("rid") or nested_first(
        payload, ("rid", "trace_id")))
    lifecycle_id = stringify(payload.get("lifecycle_id")
                             or nested_first(payload, ("lifecycle_id",)))
    order_id = stringify(
        payload.get("order_id")
        or adapter.get("orderId")
        or nested_first(payload, ("order_id", "orderId"))
    )
    client_order_id = stringify(
        payload.get("client_order_id")
        or adapter.get("clientOrderId")
        or nested_first(payload, ("client_order_id", "clientOrderId"))
    )
    symbol = stringify(payload.get("symbol")
                       or nested_first(payload, ("symbol",)))
    side = stringify(payload.get("side") or nested_first(payload, ("side",)))
    source_fsm = stringify(payload.get("source_fsm")
                           or nested_first(payload, ("source_fsm",)))
    quantity = stringify(payload.get("quantity") or nested_first(
        payload, ("quantity", "qty", "origQty")))
    price = stringify(payload.get("price") or nested_first(
        payload, ("price", "avgPrice")))
    time_in_force = stringify(
        adapter.get("timeInForce")
        or payload.get("time_in_force")
        or nested_first(payload, ("timeInForce", "time_in_force", "tif"))
    )
    order_type = stringify(
        adapter.get("type")
        or payload.get("order_type")
        or nested_first(payload, ("type", "origType", "order_type"))
    )
    timeframe_sec = safe_int(nested_first(
        payload, ("basis_tf_sec", "tf_sec", "timeframe_sec")))
    fill_ttl_source_present = "fill_ttl_source" in metadata
    fill_ttl_override_present = "fill_ttl_override_ms" in metadata
    return {
        "event_type": stringify(payload.get("event_type")),
        "ts_ms": timestamp,
        "rid": rid,
        "lifecycle_id": lifecycle_id,
        "order_id": order_id,
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
        "source_fsm": source_fsm,
        "strategy_id": infer_strategy(payload, rid, lifecycle_id, source_fsm),
        "quantity": quantity,
        "price": price,
        "time_in_force": time_in_force,
        "order_type": order_type,
        "timeframe_sec": timeframe_sec,
        "fill_ttl_source_present": fill_ttl_source_present,
        "fill_ttl_source": stringify(metadata.get("fill_ttl_source")) if fill_ttl_source_present else "",
        "fill_ttl_override_present": fill_ttl_override_present,
        "fill_ttl_override_ms": safe_int(metadata.get("fill_ttl_override_ms")) if fill_ttl_override_present else None,
        "source_file": rel_path,
        "line_no": line_no,
        "payload": payload,
    }


def event_fingerprint(event):
    return (
        event["event_type"],
        event["ts_ms"],
        event["rid"],
        event["lifecycle_id"],
        event["order_id"],
        event["client_order_id"],
        event["symbol"],
        event["side"],
        event["source_fsm"],
        event["quantity"],
        event["price"],
    )


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * (pct / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    lower_val = sorted_values[lower]
    upper_val = sorted_values[upper]
    ratio = position - lower
    return lower_val + (upper_val - lower_val) * ratio


def dist_summary(values):
    clean = sorted(
        value for value in values if value is not None and value >= 0)
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": len(clean),
        "min": clean[0],
        "p50": percentile(clean, 50),
        "p75": percentile(clean, 75),
        "p90": percentile(clean, 90),
        "p95": percentile(clean, 95),
        "p99": percentile(clean, 99),
        "max": clean[-1],
    }


def format_dist(summary):
    if not summary["count"]:
        return "count=0"
    return (
        f"count={summary['count']} min={int(summary['min'])} p50={int(summary['p50'])} "
        f"p75={int(summary['p75'])} p90={int(summary['p90'])} p95={int(summary['p95'])} "
        f"p99={int(summary['p99'])} max={int(summary['max'])}"
    )


def csv_value(value):
    return "" if value is None else value


def detect_calibration_relevant(order_row):
    client_order_id = order_row.get("client_order_id") or ""
    return (
        order_row.get("strategy_id") == "aurora"
        and order_row.get("source_fsm") == "ExecPosFSM"
        and order_row.get("order_type") == "LIMIT"
        and order_row.get("time_in_force") == "GTX"
        and client_order_id.startswith("ENTRY-")
    )


def compute_metrics(order_rows):
    total = len(order_rows)
    metadata_rows = [row for row in order_rows if row["metadata_bearing"]]
    relevant_rows = [
        row for row in order_rows if row["is_calibration_relevant"]]
    filled = sum(1 for row in order_rows if row["terminal_state"] == "filled")
    timeout = sum(
        1 for row in order_rows if row["terminal_state"] == "timeout")
    canceled = sum(
        1 for row in order_rows if row["terminal_state"] == "canceled")
    unknown = sum(
        1 for row in order_rows if row["terminal_state"] == "unknown")
    join_rate = ((total - unknown) / total) if total else 0.0
    return {
        "total_order_placed": total,
        "metadata_bearing_order_placed": len(metadata_rows),
        "metadata_missing_order_placed": total - len(metadata_rows),
        "aurora_entry_limit_gtx_orders": len(relevant_rows),
        "close_market_orders": sum(1 for row in order_rows if row["order_type"] == "MARKET" or row["source_fsm"] == "CloseExecutor"),
        "fill_ttl_source_per_order_override": sum(1 for row in order_rows if row["fill_ttl_source"] == "per_order_override"),
        "fill_ttl_source_global_watchdog": sum(1 for row in order_rows if row["fill_ttl_source"] == "global_watchdog"),
        "fill_ttl_source_missing": sum(1 for row in order_rows if not row["fill_ttl_source"]),
        "fill_ttl_override_ms_present": sum(1 for row in order_rows if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None),
        "fill_ttl_override_ms_null": sum(1 for row in order_rows if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is None),
        "filled": filled,
        "timeout": timeout,
        "canceled": canceled,
        "unknown": unknown,
        "terminal_join_rate": join_rate,
        "symbols_observed": sorted({row["symbol"] for row in order_rows if row["symbol"]}),
        "strategies_observed": sorted({row["strategy_id"] for row in order_rows if row["strategy_id"]}),
        "source_fsms_observed": sorted({row["source_fsm"] for row in order_rows if row["source_fsm"]}),
    }


def main():
    repo_root = Path(__file__).resolve().parents[2]
    report_path = repo_root / "AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN_REPORT.md"
    order_csv_path = repo_root / "AURORA_TIMER_GOVERNANCE_T5D_GATE_ORDER_LIFECYCLES.csv"
    window_csv_path = repo_root / "AURORA_TIMER_GOVERNANCE_T5D_GATE_WINDOW_SUMMARY.csv"
    simulation_csv_path = repo_root / \
        "AURORA_TIMER_GOVERNANCE_T5D_GATE_CANDIDATE_SIMULATION.csv"

    logs_dir = repo_root / "logs"
    frozen_dir = repo_root / "frozen"
    reports_dir = repo_root / "reports"

    json_files = []
    text_files = []
    report_files = []
    for base in (logs_dir, frozen_dir):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".jsonl":
                json_files.append(path)
            if path.name.startswith(("aurora_core.log", "domain_execution_position.log", "event_chain.log")):
                text_files.append(path)
    if reports_dir.exists():
        for path in reports_dir.rglob("*"):
            if path.is_file():
                report_files.append(path)

    if not logs_dir.exists() or not any(path.name == "order_log_v1.jsonl" for path in json_files):
        verdict = "BLOCKED_LOGS_MISSING"
        for path in (order_csv_path, window_csv_path, simulation_csv_path):
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if path == order_csv_path:
                    writer.writerow([
                        "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm",
                        "side", "order_type", "time_in_force", "placed_ts_ms", "fill_ttl_source",
                        "fill_ttl_override_ms", "terminal_state", "terminal_ts_ms", "age_to_terminal_ms",
                        "age_to_first_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms", "join_method",
                        "join_quality", "notes",
                    ])
                elif path == window_csv_path:
                    writer.writerow([
                        "window_id", "start_ts_ms", "end_ts_ms", "source_files", "restart_marker_found",
                        "orders_count", "metadata_orders_count", "terminal_join_quality",
                    ])
                else:
                    writer.writerow([
                        "candidate_fill_ttl_ms", "orders_considered", "would_timeout_before_fill",
                        "would_timeout_before_cancel", "would_timeout_before_known_terminal", "unaffected",
                        "max_legitimate_fill_age_ms", "p95_fill_age_ms", "p99_fill_age_ms", "risk_label", "notes",
                    ])
        report_path.write_text(
            "\n".join([
                "AGENT_REPORT_V1",
                "",
                "task: AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN",
                f"verdict: {verdict}",
                f"report_path: {report_path.name}",
                "",
                "problem:",
                "- Required runtime log surfaces are missing; rerun analysis cannot proceed.",
                "",
                "runtime_behavior_change:",
                "- NONE",
                "",
                "config_changes:",
                "- NONE",
            ]),
            encoding="utf-8",
        )
        print(verdict)
        return

    json_files = sorted(set(json_files))
    text_files = sorted(set(text_files))
    report_files = sorted(set(report_files))

    family_bounds = {}
    startup_markers = []
    watchdog_text_markers = []
    scanned_files = set()
    relevant_events = []
    seen_fingerprints = set()

    full_timestamp_json_names = {"order_log_v1.jsonl", "trade_lifecycle.jsonl"}

    for path in text_files:
        rel = path.relative_to(repo_root).as_posix()
        family = family_key(rel)
        scanned_files.add(rel)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                raw = line.rstrip("\n")
                match = TEXT_TS_RE.match(raw)
                ts_ms = parse_text_datetime(match.group(1)) if match else None
                embedded = EMBEDDED_TS_MS_RE.search(raw)
                if embedded:
                    ts_ms = safe_int(embedded.group(1)) or ts_ms
                update_bounds(family_bounds, family, ts_ms)
                if any(token in raw for token in STARTUP_TOKENS):
                    startup_markers.append(
                        {
                            "source_file": rel,
                            "line_no": line_no,
                            "ts_ms": ts_ms,
                            "message": raw.strip(),
                        }
                    )
                if any(token in raw for token in WATCHDOG_TEXT_TOKENS):
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
        family = family_key(rel)
        scanned_files.add(rel)
        full_time_scan = path.name in full_timestamp_json_names
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw or not raw.startswith("{"):
                    continue
                should_parse = full_time_scan or any(
                    token in raw for token in TARGET_SUBSTRINGS)
                if not should_parse:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                ts_ms = extract_timestamp(payload)
                if full_time_scan:
                    update_bounds(family_bounds, family, ts_ms)
                event_type = stringify(payload.get("event_type"))
                if event_type not in TARGET_EVENT_TYPES:
                    continue
                event = standardize_event(payload, rel, line_no)
                update_bounds(family_bounds, family, event["ts_ms"])
                fingerprint = event_fingerprint(event)
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                relevant_events.append(event)

    relevant_events.sort(key=lambda item: (
        item["ts_ms"] or 0, item["event_type"], item["source_file"], item["line_no"]))

    placed_events = [
        event for event in relevant_events if event["event_type"] == "ORDER_PLACED"]
    if not placed_events:
        verdict = "BLOCKED_WITH_EVIDENCE"
        report_path.write_text(
            "\n".join([
                "AGENT_REPORT_V1",
                "",
                "task: AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN",
                f"verdict: {verdict}",
                f"report_path: {report_path.name}",
                "",
                "problem:",
                "- No ORDER_PLACED records were found across the retained log surfaces.",
                "",
                "runtime_behavior_change:",
                "- NONE",
                "",
                "config_changes:",
                "- NONE",
            ]),
            encoding="utf-8",
        )
        print(verdict)
        return

    first_metadata_event = next(
        (
            event
            for event in placed_events
            if event["fill_ttl_source_present"] and event["fill_ttl_override_present"]
        ),
        None,
    )

    if first_metadata_event is None:
        boundary_ts = placed_events[0]["ts_ms"]
    else:
        boundary_ts = first_metadata_event["ts_ms"]

    post_t5c_placed = [event for event in placed_events if (
        event["ts_ms"] or 0) >= boundary_ts]
    post_t5c_events = [event for event in relevant_events if (
        event["ts_ms"] or 0) >= boundary_ts]
    if not post_t5c_placed:
        post_t5c_placed = placed_events
        post_t5c_events = relevant_events

    boot_events = [
        event for event in relevant_events if event["event_type"] == "BOOT"]
    boot_ts_sorted = sorted(
        {event["ts_ms"] for event in boot_events if event["ts_ms"] is not None})
    start_boot_ts = None
    for ts_ms in boot_ts_sorted:
        if ts_ms <= boundary_ts:
            start_boot_ts = ts_ms
        else:
            break
    if start_boot_ts is None:
        start_boot_ts = boundary_ts
    window_starts = [
        ts_ms for ts_ms in boot_ts_sorted if ts_ms >= start_boot_ts]
    if not window_starts:
        window_starts = [start_boot_ts]
    max_event_ts = max((event["ts_ms"] or 0) for event in post_t5c_events)

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

    window_lookup = [spec["start_ts_ms"] for spec in window_specs]

    def assign_window(ts_ms):
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

    for event in relevant_events:
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
    for placed in post_t5c_placed:
        placed_ts = placed["ts_ms"]
        rid = placed["rid"]
        order_id = placed["order_id"]
        client_order_id = placed["client_order_id"]

        fill_matches = []
        for method, candidates in (
            ("lifecycle_id", fills_by_lifecycle.get(rid, [])),
            ("client_order_id", fills_by_rid.get(client_order_id, [])),
            ("order_id", fills_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                    fill_matches.append(
                        (candidate["ts_ms"], method, candidate))

        trade_matches = []
        for method, candidates in (
            ("trade_lifecycle_id", trades_by_lifecycle.get(rid, [])),
            ("trade_client_order_id", trades_by_rid.get(client_order_id, [])),
            ("trade_order_id", trades_by_order_id.get(order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                    trade_matches.append(
                        (candidate["ts_ms"], method, candidate))

        timeout_matches = []
        for method, candidates in (
            ("order_id", timeouts_by_order_id.get(order_id, [])),
            ("client_order_id", timeouts_by_client.get(client_order_id, [])),
            ("rid", timeouts_by_rid.get(rid, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                    timeout_matches.append(
                        (candidate["ts_ms"], method, candidate))

        cancel_matches = []
        for method, candidates in (
            ("order_id", cancels_by_order_id.get(order_id, [])),
            ("client_order_id", cancels_by_client.get(client_order_id, [])),
        ):
            for candidate in candidates:
                if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                    cancel_matches.append(
                        (candidate["ts_ms"], method, candidate))

        position_closed_matches = []
        for candidate in position_closed_by_lifecycle.get(rid, []):
            if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                position_closed_matches.append(
                    (candidate["ts_ms"], "position_closed.lifecycle_id", candidate))
        if not position_closed_matches:
            for candidate in position_closed_by_symbol.get(placed["symbol"], []):
                if candidate["ts_ms"] is not None and candidate["ts_ms"] >= placed_ts:
                    position_closed_matches.append(
                        (candidate["ts_ms"], "position_closed.symbol", candidate))

        fill_matches.sort(key=lambda item: item[0])
        trade_matches.sort(key=lambda item: item[0])
        timeout_matches.sort(key=lambda item: item[0])
        cancel_matches.sort(key=lambda item: item[0])
        position_closed_matches.sort(key=lambda item: item[0])

        first_fill = fill_matches[0] if fill_matches else None
        first_trade = trade_matches[0] if trade_matches else None
        first_fill_like = None
        if first_fill and first_trade:
            first_fill_like = first_fill if first_fill[0] <= first_trade[0] else first_trade
        else:
            first_fill_like = first_fill or first_trade

        first_timeout = timeout_matches[0] if timeout_matches else None
        first_cancel = cancel_matches[0] if cancel_matches else None

        terminal_candidates = []
        if first_fill:
            terminal_candidates.append(
                (first_fill[0], "filled", first_fill[1], first_fill[2]))
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
        if terminal and first_fill and terminal[1] != "filled" and first_fill[0] < terminal[0]:
            notes.append("fill_before_terminal")
        if not placed["fill_ttl_source_present"]:
            notes.append("fill_ttl_source_missing")
        if placed["fill_ttl_override_present"] and placed["fill_ttl_override_ms"] is None:
            notes.append("fill_ttl_override_ms_null")

        order_row = {
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
            "placed_ts_iso": iso_utc(placed_ts),
            "fill_ttl_source_present": placed["fill_ttl_source_present"],
            "fill_ttl_source": placed["fill_ttl_source"],
            "fill_ttl_override_present": placed["fill_ttl_override_present"],
            "fill_ttl_override_ms": placed["fill_ttl_override_ms"],
            "terminal_state": terminal[1] if terminal else "unknown",
            "terminal_ts_ms": terminal[0] if terminal else None,
            "terminal_ts_iso": iso_utc(terminal[0]) if terminal else "",
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
        }
        order_row["is_calibration_relevant"] = detect_calibration_relevant(
            order_row)
        order_row["first_fill_ts_ms"] = first_fill_like[0] if first_fill_like else None
        order_row["position_closed_ts_ms"] = position_closed_matches[0][0] if position_closed_matches else None
        order_row["position_closed_method"] = position_closed_matches[0][1] if position_closed_matches else ""
        order_rows.append(order_row)

    order_rows.sort(key=lambda row: (row["placed_ts_ms"], row["order_key"]))

    window_rows = []
    order_rows_by_window = defaultdict(list)
    for row in order_rows:
        order_rows_by_window[row["window_id"]].append(row)

    startup_markers.sort(key=lambda item: (
        item["ts_ms"] or 0, item["source_file"], item["line_no"]))
    markers_by_window = defaultdict(list)
    for marker in startup_markers:
        if marker["ts_ms"] is None:
            continue
        markers_by_window[assign_window(marker["ts_ms"])] .append(marker)

    for spec in window_specs:
        window_id = spec["window_id"]
        rows = order_rows_by_window.get(window_id, [])
        metrics = compute_metrics(rows)
        source_files = sorted({row["source_file"] for row in rows} | {
                              marker["source_file"] for marker in markers_by_window.get(window_id, [])})
        first_order = min((row["placed_ts_ms"] for row in rows), default=None)
        first_metadata = min(
            (row["placed_ts_ms"] for row in rows if row["metadata_bearing"]), default=None)
        join_quality = f"{metrics['filled']}/{metrics['timeout']}/{metrics['canceled']}/{metrics['unknown']} rate={metrics['terminal_join_rate']:.3f}"
        window_rows.append(
            {
                "window_id": window_id,
                "start_ts_ms": spec["start_ts_ms"],
                "start_ts_iso": iso_utc(spec["start_ts_ms"]),
                "end_ts_ms": spec["end_ts_ms"],
                "end_ts_iso": iso_utc(spec["end_ts_ms"]),
                "source_files": "; ".join(source_files),
                "restart_marker_found": True,
                "first_order_placed_ts_ms": first_order,
                "first_order_placed_ts_iso": iso_utc(first_order),
                "first_metadata_order_placed_ts_ms": first_metadata,
                "first_metadata_order_placed_ts_iso": iso_utc(first_metadata),
                "orders_count": metrics["total_order_placed"],
                "metadata_orders_count": metrics["metadata_bearing_order_placed"],
                "aurora_entry_limit_gtx_orders": metrics["aurora_entry_limit_gtx_orders"],
                "filled": metrics["filled"],
                "timeout": metrics["timeout"],
                "canceled": metrics["canceled"],
                "unknown": metrics["unknown"],
                "terminal_join_rate": metrics["terminal_join_rate"],
                "terminal_join_quality": join_quality,
            }
        )

    global_metrics = compute_metrics(order_rows)
    calibration_rows = [
        row for row in order_rows if row["is_calibration_relevant"]]
    calibration_known_terminal_rows = [
        row for row in calibration_rows if row["terminal_state"] != "unknown"]

    first_metadata_iso = iso_utc(
        first_metadata_event["ts_ms"]) if first_metadata_event else ""

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
        if row["age_to_timeout_ms"] is not None and abs(row["age_to_timeout_ms"] - 3600000) <= 120000:
            reasons.append("timeout_near_global_3600000")
        if reasons:
            stale_suspicions.append(
                {
                    "order_key": row["order_key"],
                    "symbol": row["symbol"],
                    "placed_ts_ms": row["placed_ts_ms"],
                    "terminal_ts_ms": row["terminal_ts_ms"],
                    "timeout_ts_ms": timeout_ts,
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
                "timeout_after_position_closed_lifecycle_match",
                "timeout_after_known_terminal",
            )
        )
        for item in stale_suspicions
    ):
        stale_watchdog_verdict = "STALE_WATCHDOG_CONFIRMED"
    elif stale_suspicions:
        stale_watchdog_verdict = "STALE_WATCHDOG_SUSPECTED"
    else:
        stale_watchdog_verdict = "NO_STALE_WATCHDOG_AFTER_FIX_OBSERVED"

    additional_total_needed = max(0, 50 - global_metrics["total_order_placed"])
    additional_relevant_needed = max(
        0, 50 - global_metrics["aurora_entry_limit_gtx_orders"])
    runtime_span_ms = max((order_rows[-1]["placed_ts_ms"] - boundary_ts), 1)
    runtime_hours = runtime_span_ms / 3600000.0
    total_rate = global_metrics["total_order_placed"] / \
        runtime_hours if runtime_hours > 0 else 0.0
    relevant_rate = global_metrics["aurora_entry_limit_gtx_orders"] / \
        runtime_hours if runtime_hours > 0 else 0.0
    min_hours_for_total = (additional_total_needed /
                           total_rate) if total_rate > 0 else None
    min_hours_for_relevant = (
        additional_relevant_needed / relevant_rate) if relevant_rate > 0 else None

    if first_metadata_event is None:
        verdict = "NOT_READY_METADATA_NOT_OBSERVED"
    elif global_metrics["total_order_placed"] < 50:
        verdict = "NOT_READY_INSUFFICIENT_POST_T5C_ORDERS"
    elif global_metrics["metadata_bearing_order_placed"] == 0:
        verdict = "NOT_READY_METADATA_NOT_OBSERVED"
    elif not calibration_known_terminal_rows or (len(calibration_known_terminal_rows) / max(len(calibration_rows), 1)) < 0.5:
        verdict = "NOT_READY_TERMINAL_JOINS_INCOMPLETE"
    else:
        verdict = "READY_FOR_T5D_CALIBRATION"

    useful_simulation_sample = len(calibration_known_terminal_rows) >= 20
    fill_ages = [row["age_to_first_fill_ms"]
                 for row in calibration_known_terminal_rows if row["age_to_first_fill_ms"] is not None]
    fill_ages_sorted = sorted(age for age in fill_ages if age >= 0)
    simulation_rows = []
    for candidate in CANDIDATE_TTLS:
        if useful_simulation_sample:
            orders_considered = len(calibration_known_terminal_rows)
            would_timeout_before_fill = sum(
                1
                for row in calibration_known_terminal_rows
                if row["age_to_first_fill_ms"] is not None and row["age_to_first_fill_ms"] > candidate
            )
            would_timeout_before_cancel = sum(
                1
                for row in calibration_known_terminal_rows
                if row["terminal_state"] == "canceled"
                and row["age_to_cancel_ms"] is not None
                and row["age_to_cancel_ms"] > candidate
            )
            would_timeout_before_known_terminal = sum(
                1
                for row in calibration_known_terminal_rows
                if row["age_to_terminal_ms"] is not None and row["age_to_terminal_ms"] > candidate
            )
            unaffected = orders_considered - would_timeout_before_known_terminal
            if would_timeout_before_fill > 0:
                risk_label = "HIGH"
            elif would_timeout_before_known_terminal > 0:
                risk_label = "MEDIUM"
            elif candidate < 1200000:
                risk_label = "LOW"
            else:
                risk_label = "BACKSTOP_ONLY"
            notes = f"subset=aurora_limit_gtx_known_terminal count={orders_considered}"
        else:
            orders_considered = len(calibration_known_terminal_rows)
            would_timeout_before_fill = 0
            would_timeout_before_cancel = 0
            would_timeout_before_known_terminal = 0
            unaffected = orders_considered
            risk_label = "INSUFFICIENT_SAMPLE"
            notes = "diagnostic_only: calibration-relevant known-terminal sample below useful threshold"
        simulation_rows.append(
            {
                "candidate_fill_ttl_ms": candidate,
                "orders_considered": orders_considered,
                "would_timeout_before_fill": would_timeout_before_fill,
                "would_timeout_before_cancel": would_timeout_before_cancel,
                "would_timeout_before_known_terminal": would_timeout_before_known_terminal,
                "unaffected": unaffected,
                "max_legitimate_fill_age_ms": fill_ages_sorted[-1] if fill_ages_sorted else None,
                "p95_fill_age_ms": percentile(fill_ages_sorted, 95) if fill_ages_sorted else None,
                "p99_fill_age_ms": percentile(fill_ages_sorted, 99) if fill_ages_sorted else None,
                "risk_label": risk_label,
                "notes": notes,
            }
        )

    fill_ttl_values = [row["fill_ttl_override_ms"]
                       for row in order_rows if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None]
    fill_ttl_values_sorted = sorted(fill_ttl_values)
    by_symbol_override = defaultdict(list)
    by_strategy_override = defaultdict(list)
    by_timeframe_override = defaultdict(list)
    for row in order_rows:
        if row["fill_ttl_override_present"] and row["fill_ttl_override_ms"] is not None:
            by_symbol_override[row["symbol"]].append(
                row["fill_ttl_override_ms"])
            by_strategy_override[row["strategy_id"]].append(
                row["fill_ttl_override_ms"])
            timeframe_key = f"{row['timeframe_sec']}s" if row["timeframe_sec"] else "unknown"
            by_timeframe_override[timeframe_key].append(
                row["fill_ttl_override_ms"])

    order_csv_fields = [
        "order_key", "window_id", "source_file", "symbol", "strategy_id", "source_fsm", "side",
        "order_type", "time_in_force", "placed_ts_ms", "placed_ts_iso", "fill_ttl_source",
        "fill_ttl_override_ms", "terminal_state", "terminal_ts_ms", "terminal_ts_iso",
        "age_to_terminal_ms", "age_to_first_fill_ms", "age_to_timeout_ms", "age_to_cancel_ms",
        "join_method", "join_quality", "notes",
    ]
    with order_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=order_csv_fields)
        writer.writeheader()
        for row in order_rows:
            writer.writerow({field: csv_value(row.get(field))
                            for field in order_csv_fields})

    window_csv_fields = [
        "window_id", "start_ts_ms", "start_ts_iso", "end_ts_ms", "end_ts_iso", "source_files",
        "restart_marker_found", "first_order_placed_ts_ms", "first_order_placed_ts_iso",
        "first_metadata_order_placed_ts_ms", "first_metadata_order_placed_ts_iso", "orders_count",
        "metadata_orders_count", "aurora_entry_limit_gtx_orders", "filled", "timeout", "canceled",
        "unknown", "terminal_join_rate", "terminal_join_quality",
    ]
    with window_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=window_csv_fields)
        writer.writeheader()
        for row in window_rows:
            writer.writerow({field: csv_value(row.get(field))
                            for field in window_csv_fields})

    simulation_csv_fields = [
        "candidate_fill_ttl_ms", "orders_considered", "would_timeout_before_fill",
        "would_timeout_before_cancel", "would_timeout_before_known_terminal", "unaffected",
        "max_legitimate_fill_age_ms", "p95_fill_age_ms", "p99_fill_age_ms", "risk_label", "notes",
    ]
    with simulation_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=simulation_csv_fields)
        writer.writeheader()
        for row in simulation_rows:
            writer.writerow({field: csv_value(row.get(field))
                            for field in simulation_csv_fields})

    stale_timeline_lines = []
    for item in stale_suspicions[:10]:
        stale_timeline_lines.append(
            "- "
            + f"{item['order_key']} {item['symbol']} placed={iso_utc(item['placed_ts_ms'])} "
            + f"timeout={iso_utc(item['timeout_ts_ms'])} terminal={iso_utc(item['terminal_ts_ms'])} "
            + f"position_closed={iso_utc(item['position_closed_ts_ms'])} position_closed_method={item['position_closed_method']} reasons={','.join(item['reasons'])}"
        )
    if not stale_timeline_lines:
        stale_timeline_lines.append("- none")

    window_summary_lines = []
    for row in window_rows:
        window_summary_lines.append(
            "- "
            + f"{row['window_id']} {row['start_ts_iso']} -> {row['end_ts_iso']} "
            + f"orders={row['orders_count']} metadata={row['metadata_orders_count']} "
            + f"aurora_limit_gtx={row['aurora_entry_limit_gtx_orders']} join_rate={row['terminal_join_rate']:.3f}"
        )

    file_bounds_lines = []
    for key in sorted(family_bounds):
        start_ts, end_ts = family_bounds[key]
        file_bounds_lines.append(
            f"- {key}: {iso_utc(start_ts)} -> {iso_utc(end_ts)}")

    candidate_lines = []
    for row in simulation_rows:
        candidate_lines.append(
            "- "
            + f"ttl={row['candidate_fill_ttl_ms']} orders={row['orders_considered']} before_fill={row['would_timeout_before_fill']} "
            + f"before_cancel={row['would_timeout_before_cancel']} before_known_terminal={row['would_timeout_before_known_terminal']} "
            + f"risk={row['risk_label']}"
        )

    readiness_lines = []
    if verdict == "READY_FOR_T5D_CALIBRATION":
        if global_metrics["aurora_entry_limit_gtx_orders"] < 50:
            readiness_lines.append(
                "- Minimum gate passed on total post-T5C ORDER_PLACED volume, but preferred 50 metadata-bearing Aurora LIMIT/GTX entries was not reached; calibration is possible but weak."
            )
        else:
            readiness_lines.append(
                "- Minimum gate passed and preferred calibration subset threshold was reached.")
    elif verdict == "NOT_READY_INSUFFICIENT_POST_T5C_ORDERS":
        readiness_lines.append(
            "- Total post-T5C ORDER_PLACED remains below the minimum gate of 50.")
    elif verdict == "NOT_READY_METADATA_NOT_OBSERVED":
        readiness_lines.append(
            "- Required T5C metadata fields were not observed on retained ORDER_PLACED records.")
    elif verdict == "NOT_READY_TERMINAL_JOINS_INCOMPLETE":
        readiness_lines.append(
            "- Terminal joins on the calibration-relevant subset remain too incomplete for a defensible timing study.")

    if min_hours_for_total is not None or min_hours_for_relevant is not None:
        min_duration_hours = max(value for value in (
            min_hours_for_total, min_hours_for_relevant) if value is not None)
        min_duration_line = f"- minimum runtime duration: about {min_duration_hours:.2f} additional hours at current observed rates."
    else:
        min_duration_line = "- minimum runtime duration: insufficient rate evidence to project remaining collection time."

    report_lines = [
        "AGENT_REPORT_V1",
        "",
        "task: AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN",
        f"verdict: {verdict}",
        f"report_path: {report_path.name}",
        "",
        "problem:",
        "- Re-run the T5D gate on fresh retained runtime evidence, segmented by restart windows, without changing runtime behavior or configuration.",
        "",
        "facts:",
        f"- logs inspected: {len(scanned_files)} files across current logs, logs/frozen bundles, root frozen bundles, and reports inventory.",
        f"- file time bounds detected:",
        *file_bounds_lines,
        f"- runtime windows detected: {len(window_rows)}",
        f"- first metadata ORDER_PLACED: {first_metadata_iso} in {first_metadata_event['source_file'] if first_metadata_event else 'N/A'}",
        f"- total post-T5C ORDER_PLACED: {global_metrics['total_order_placed']}",
        f"- metadata-bearing ORDER_PLACED: {global_metrics['metadata_bearing_order_placed']}",
        f"- calibration-relevant Aurora LIMIT/GTX entries: {global_metrics['aurora_entry_limit_gtx_orders']}",
        f"- terminal joins: filled={global_metrics['filled']} timeout={global_metrics['timeout']} canceled={global_metrics['canceled']} unknown={global_metrics['unknown']}",
        f"- symbols: {', '.join(global_metrics['symbols_observed']) if global_metrics['symbols_observed'] else 'none'}",
        f"- strategies: {', '.join(global_metrics['strategies_observed']) if global_metrics['strategies_observed'] else 'none'}",
        f"- source FSMs: {', '.join(global_metrics['source_fsms_observed']) if global_metrics['source_fsms_observed'] else 'none'}",
        "",
        "window_summary:",
        *window_summary_lines,
        "",
        "metadata_coverage:",
        f"- fill_ttl_source present: {global_metrics['total_order_placed'] - global_metrics['fill_ttl_source_missing']}/{global_metrics['total_order_placed']}",
        f"- fill_ttl_override_ms present/null: present={global_metrics['fill_ttl_override_ms_present']} null={global_metrics['fill_ttl_override_ms_null']}",
        f"- per_order_override: {global_metrics['fill_ttl_source_per_order_override']}",
        f"- global_watchdog: {global_metrics['fill_ttl_source_global_watchdog']}",
        f"- missing metadata: {global_metrics['metadata_missing_order_placed']}",
        "",
        "terminal_join_quality:",
        f"- filled: {global_metrics['filled']}",
        f"- timeout: {global_metrics['timeout']}",
        f"- canceled: {global_metrics['canceled']}",
        f"- unknown: {global_metrics['unknown']}",
        f"- join rate: {global_metrics['terminal_join_rate']:.3f}",
        f"- join methods: {', '.join(sorted({row['join_method'] for row in order_rows if row['join_method']})) if any(row['join_method'] for row in order_rows) else 'none'}",
        "",
        "timing_distributions:",
        f"- age_to_first_fill_ms: {format_dist(dist_summary([row['age_to_first_fill_ms'] for row in order_rows]))}",
        f"- age_to_timeout_ms: {format_dist(dist_summary([row['age_to_timeout_ms'] for row in order_rows]))}",
        f"- age_to_cancel_ms: {format_dist(dist_summary([row['age_to_cancel_ms'] for row in order_rows]))}",
        "",
        "fill_ttl_override_ms_distribution:",
        f"- count: {len(fill_ttl_values_sorted)}",
        f"- unique_values: {', '.join(str(value) for value in sorted(set(fill_ttl_values_sorted)))}",
        f"- min/p50/p95/max: {fill_ttl_values_sorted[0] if fill_ttl_values_sorted else 'N/A'} / {int(percentile(fill_ttl_values_sorted, 50)) if fill_ttl_values_sorted else 'N/A'} / {int(percentile(fill_ttl_values_sorted, 95)) if fill_ttl_values_sorted else 'N/A'} / {fill_ttl_values_sorted[-1] if fill_ttl_values_sorted else 'N/A'}",
        f"- by_symbol: {'; '.join(f'{key}={sorted(set(values))}' for key, values in sorted(
            by_symbol_override.items())) if by_symbol_override else 'none'}",
        f"- by_strategy: {'; '.join(f'{key}={sorted(set(values))}' for key, values in sorted(
            by_strategy_override.items())) if by_strategy_override else 'none'}",
        f"- by_timeframe_if_available: {'; '.join(f'{key}={sorted(set(values))}' for key, values in sorted(
            by_timeframe_override.items())) if by_timeframe_override else 'none'}",
        "",
        "stale_watchdog_regression_check:",
        f"- verdict: {stale_watchdog_verdict}",
        f"- evidence: timeout_rows={len(timeout_rows)} suspicious_cases={len(stale_suspicions)} text_watchdog_markers={len(watchdog_text_markers)}",
        "- suspicious timelines:",
        *stale_timeline_lines,
        "",
        "candidate_simulation:",
        *candidate_lines,
        "",
        "readiness_decision:",
        f"- verdict: {verdict}",
        *readiness_lines,
        f"- threshold passed/failed: minimum_total_50={'PASS' if global_metrics['total_order_placed'] >= 50 else 'FAIL'} preferred_aurora_limit_gtx_50={'PASS' if global_metrics['aurora_entry_limit_gtx_orders'] >= 50 else 'FAIL'} metadata_present={'PASS' if first_metadata_event is not None else 'FAIL'} joins_possible={'PASS' if calibration_known_terminal_rows else 'FAIL'}",
        "",
        "if_ready_next_package:",
        "- T5D calibration study / patch proposal prompt",
        "",
        "if_not_ready_collection_plan:",
        min_duration_line,
        f"- minimum additional ORDER_PLACED: total={additional_total_needed} calibration_relevant_preferred={additional_relevant_needed}",
        "- required fields: ORDER_PLACED.fill_ttl_source and ORDER_PLACED.fill_ttl_override_ms present or explicit null, plus joinable terminal events.",
        "- rerun command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/audits/t5d_gate_rerun_analysis.py",
        "",
        "runtime_behavior_change:",
        "- NONE",
        "",
        "config_changes:",
        "- NONE",
        "",
        "unproven:",
        f"- global_watchdog fill_ttl_source observations remain sparse: {global_metrics['fill_ttl_source_global_watchdog']}",
        f"- explicit null fill_ttl_override_ms observations: {global_metrics['fill_ttl_override_ms_null']}",
        "- root frozen sidecar captures overlap and were deduplicated by event fingerprint rather than file identity.",
        "",
        "next_recommended_package:",
        "- T5D calibration study if verdict is READY_FOR_T5D_CALIBRATION; otherwise continue runtime collection and rerun this package.",
    ]

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"verdict={verdict}")
    print(
        f"post_t5c_total_order_placed={global_metrics['total_order_placed']}")
    print(
        f"metadata_bearing_order_placed={global_metrics['metadata_bearing_order_placed']}")
    print(
        f"aurora_limit_gtx_orders={global_metrics['aurora_entry_limit_gtx_orders']}")
    print(f"terminal_join_rate={global_metrics['terminal_join_rate']:.3f}")
    print(f"stale_watchdog_verdict={stale_watchdog_verdict}")
    print(f"report={report_path.name}")


if __name__ == "__main__":
    main()
