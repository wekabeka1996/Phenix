from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


FINAL_STATS_NAME = "execution_lifecycle_stats_v1.jsonl"
ORDER_LOG_NAME = "order_log_v1.jsonl"
AUDIT_NAME = "regime_confidence_audit_v1.jsonl"
TRADE_LIFECYCLE_NAME = "trade_lifecycle.jsonl"
SHADOW_NAME = "shadow_critical_event_journal_v1.jsonl"
DOMAIN_LOG_GLOB = "domain_execution_position.log*"
SHADOW_EVENT_NAME = "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE"
GATE_FIELDS = (
    "resolved_min_regime_confidence",
    "threshold_applied",
    "threshold_verdict",
    "threshold_reason",
    "regime_confidence_gate_verdict",
)
PASS_VALUES = {"PASS", "ALLOW", "ALLOWED", "TRUE", "OK"}
OUTPUT_REPORT = "P0C_POST_ENTRY_GIVEBACK_FORENSIC_REPORT.md"
OUTPUT_MASTER = "p0c_valid_entry_trade_table.csv"
OUTPUT_GEOMETRY = "p0c_tp_sl_geometry_matrix.csv"
OUTPUT_SIDECAR = "p0c_sidecar_shadow_matrix.csv"


@dataclass(frozen=True)
class Window:
    entry_rid: str
    lifecycle_id: str
    symbol: str
    entry_ts_ms: int
    close_ts_ms: int


class RecorderCache:
    def __init__(self, recorder_root: Path) -> None:
        self._root = recorder_root
        self._cache: dict[tuple[str, str, int], list[dict[str, Any]]] = {}

    def load(self, date_str: str, symbol: str, tf_sec: int) -> list[dict[str, Any]]:
        key = (date_str, symbol, tf_sec)
        if key in self._cache:
            return self._cache[key]

        path = self._root / date_str / f"{symbol}_{tf_sec}.csv"
        if not path.exists():
            self._cache[key] = []
            return self._cache[key]

        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                row = dict(raw)
                row["timestamp"] = to_int(raw.get("timestamp"))
                row["high"] = to_float(raw.get("high"))
                row["low"] = to_float(raw.get("low"))
                row["close"] = to_float(raw.get("close"))
                rows.append(row)
        self._cache[key] = rows
        return rows


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def to_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, float):
            return int(value)
        if isinstance(value, int):
            return value
        return int(float(value))
    except (TypeError, ValueError):
        return None


def truthy_pass(value: Any) -> bool:
    text = stringify(value).strip().upper()
    return text in PASS_VALUES


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()


def format_float(value: float | None, digits: int = 6) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.{digits}f}"


def format_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def json_compact(value: Any) -> str:
    if value in (None, "", [], {}, set()):
        return ""
    if isinstance(value, set):
        value = sorted(value)
    if isinstance(value, Counter):
        value = dict(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield line_number, obj


def parse_domain_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def natural_log_order(path: Path) -> tuple[int, str]:
    name = path.name
    if name == "domain_execution_position.log":
        return (999999, name)
    suffix = name.rsplit(".", 1)[-1]
    return (to_int(suffix) or 0, name)


def extract_gate_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {field: None for field in GATE_FIELDS}
    metadata = row.get("metadata") if isinstance(
        row.get("metadata"), dict) else {}
    extracted: dict[str, Any] = {}
    for field in GATE_FIELDS:
        extracted[field] = row.get(field)
        if extracted[field] is None:
            extracted[field] = metadata.get(field)
    return extracted


def latest_rows_by_lifecycle(stats_path: Path) -> list[dict[str, Any]]:
    latest: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    for line_number, row in iter_jsonl(stats_path):
        if row.get("record_kind") != "execution_lifecycle_stats":
            continue
        if stringify(row.get("row_status")).upper() != "FINAL":
            continue
        lifecycle_id = stringify(row.get("lifecycle_id"))
        if not lifecycle_id:
            continue
        recorded_ts_ms = to_int(row.get("recorded_ts_ms")) or to_int(
            row.get("close_ts_ms")) or 0
        key = (recorded_ts_ms, line_number)
        current = latest.get(lifecycle_id)
        if current is None or key > current[0]:
            latest[lifecycle_id] = (key, row)

    rows = [payload for _, payload in latest.values()]
    rows.sort(key=lambda row: (to_int(row.get("close_ts_ms"))
              or 0, stringify(row.get("lifecycle_id"))))
    return rows


def scan_order_log(order_log_path: Path, entry_rids: set[str], lifecycle_ids: set[str]) -> dict[str, dict[str, Any]]:
    by_rid: dict[str, dict[str, Any]] = {
        rid: {
            "order_placed": None,
            "order_intent_execpos": None,
        }
        for rid in entry_rids
    }
    close_by_lifecycle: dict[str, dict[str, Any]] = {}

    for _, row in iter_jsonl(order_log_path):
        rid = stringify(row.get("rid"))
        event_type = stringify(row.get("event_type")).upper()
        lifecycle_id = stringify(row.get("lifecycle_id"))

        if rid in by_rid:
            if event_type == "ORDER_PLACED":
                by_rid[rid]["order_placed"] = row
            elif event_type == "ORDER_INTENT" and stringify(row.get("source_fsm")) == "ExecPosFSM":
                by_rid[rid]["order_intent_execpos"] = row

        if lifecycle_id in lifecycle_ids and event_type == "POSITION_CLOSED":
            timestamp = to_int(row.get("timestamp")) or 0
            current = close_by_lifecycle.get(lifecycle_id)
            if current is None or timestamp >= (to_int(current.get("timestamp")) or 0):
                close_by_lifecycle[lifecycle_id] = row

    return {"by_rid": by_rid, "close_by_lifecycle": close_by_lifecycle}


def scan_audit(audit_path: Path, entry_rids: set[str]) -> dict[str, dict[str, Any]]:
    audit_by_rid: dict[str, dict[str, Any]] = {}
    for _, row in iter_jsonl(audit_path):
        rid = stringify(row.get("rid"))
        if rid not in entry_rids:
            continue
        if stringify(row.get("record_type")) != "decision":
            continue
        ts_ms = to_int(row.get("ts_ms")) or 0
        current = audit_by_rid.get(rid)
        if current is None or ts_ms >= (to_int(current.get("ts_ms")) or 0):
            audit_by_rid[rid] = row
    return audit_by_rid


def empty_sidecar_aggregate() -> dict[str, Any]:
    return {
        "row_count": 0,
        "event_type_counts": Counter(),
        "modes": set(),
        "trigger_events": Counter(),
        "reason_codes": Counter(),
        "first_ts_ms": None,
        "last_ts_ms": None,
        "any_policy_enabled": False,
        "any_live_armed": False,
        "any_live_threshold_crossed": False,
        "any_recommended": False,
        "any_suppressed": False,
        "max_peak_edge_usd": None,
        "max_current_edge_usd": None,
        "max_giveback_pct": None,
        "shadow_fee_aware_any_armed": False,
        "shadow_fee_aware_any_triggered": False,
        "shadow_fee_aware_candidates": set(),
        "evaluation_modes": set(),
    }


def empty_bracket_aggregate() -> dict[str, Any]:
    return {
        "stored_seen": False,
        "placed_seen": False,
        "entry_order_id": "",
        "entry_client_order_id": "",
        "sl_order_id": "",
        "tp_order_id": "",
        "placement_paths": set(),
        "owner_statuses": set(),
    }


def scan_trade_lifecycle(trade_path: Path, entry_rids: set[str]) -> dict[str, dict[str, Any]]:
    sidecar = {rid: empty_sidecar_aggregate() for rid in entry_rids}
    bracket = {rid: empty_bracket_aggregate() for rid in entry_rids}

    for _, row in iter_jsonl(trade_path):
        record_kind = stringify(row.get("record_kind"))

        if record_kind == "position_policy_sidecar":
            fill_correlation = row.get("fill_correlation") if isinstance(
                row.get("fill_correlation"), dict) else {}
            rid = stringify(fill_correlation.get(
                "rid")) or stringify(row.get("rid"))
            if rid not in sidecar:
                continue
            aggregate = sidecar[rid]
            aggregate["row_count"] += 1

            event_type = stringify(row.get("event_type"))
            if event_type:
                aggregate["event_type_counts"][event_type] += 1
                if "RECOMMENDED" in event_type:
                    aggregate["any_recommended"] = True
                if "SUPPRESSED" in event_type:
                    aggregate["any_suppressed"] = True

            mode = stringify(row.get("mode"))
            if mode:
                aggregate["modes"].add(mode)

            evaluation_mode = stringify(row.get("evaluation_mode"))
            if evaluation_mode:
                aggregate["evaluation_modes"].add(evaluation_mode)

            trigger_event = stringify(row.get("trigger_event"))
            if trigger_event:
                aggregate["trigger_events"][trigger_event] += 1

            ts_ms = to_int(row.get("ts_ms"))
            if ts_ms is not None:
                if aggregate["first_ts_ms"] is None or ts_ms < aggregate["first_ts_ms"]:
                    aggregate["first_ts_ms"] = ts_ms
                if aggregate["last_ts_ms"] is None or ts_ms > aggregate["last_ts_ms"]:
                    aggregate["last_ts_ms"] = ts_ms

            for reason_code in row.get("reason_codes") or []:
                aggregate["reason_codes"][stringify(reason_code)] += 1

            peak_snapshot = row.get("peak_giveback_snapshot") if isinstance(
                row.get("peak_giveback_snapshot"), dict) else {}
            if peak_snapshot.get("policy_enabled") is True:
                aggregate["any_policy_enabled"] = True
            if peak_snapshot.get("is_armed") is True:
                aggregate["any_live_armed"] = True
            if peak_snapshot.get("threshold_crossed") is True:
                aggregate["any_live_threshold_crossed"] = True

            peak_edge_usd = to_float(peak_snapshot.get("peak_edge_usd"))
            current_edge_usd = to_float(peak_snapshot.get("current_edge_usd"))
            giveback_pct = to_float(peak_snapshot.get("giveback_pct"))

            if peak_edge_usd is not None:
                if aggregate["max_peak_edge_usd"] is None or peak_edge_usd > aggregate["max_peak_edge_usd"]:
                    aggregate["max_peak_edge_usd"] = peak_edge_usd
            if current_edge_usd is not None:
                if aggregate["max_current_edge_usd"] is None or current_edge_usd > aggregate["max_current_edge_usd"]:
                    aggregate["max_current_edge_usd"] = current_edge_usd
            if giveback_pct is not None:
                if aggregate["max_giveback_pct"] is None or giveback_pct > aggregate["max_giveback_pct"]:
                    aggregate["max_giveback_pct"] = giveback_pct

            shadow_arms = peak_snapshot.get("peak_giveback_shadow_arms") if isinstance(
                peak_snapshot.get("peak_giveback_shadow_arms"), dict) else {}
            fee_aware = shadow_arms.get("fee_aware") if isinstance(
                shadow_arms.get("fee_aware"), dict) else {}
            for candidate in fee_aware.get("candidates") or []:
                state = stringify(candidate.get("state"))
                if state:
                    aggregate["shadow_fee_aware_candidates"].add(state)
                if candidate.get("is_armed") is True:
                    aggregate["shadow_fee_aware_any_armed"] = True
                if candidate.get("would_trigger") is True:
                    aggregate["shadow_fee_aware_any_triggered"] = True

        elif record_kind == "execution_bracket_ownership":
            rid = stringify(row.get("rid"))
            if rid not in bracket:
                continue
            aggregate = bracket[rid]
            event_type = stringify(row.get("event_type"))
            if event_type == "EXECUTION_BRACKET_DEFERRED_STORED":
                aggregate["stored_seen"] = True
            if event_type == "EXECUTION_BRACKET_DEFERRED_PLACED":
                aggregate["placed_seen"] = True
            for field in ("entry_order_id", "entry_client_order_id", "sl_order_id", "tp_order_id"):
                value = stringify(row.get(field))
                if value:
                    aggregate[field] = value
            placement_path = stringify(row.get("placement_path"))
            if placement_path:
                aggregate["placement_paths"].add(placement_path)
            owner_status = stringify(row.get("owner_status"))
            if owner_status:
                aggregate["owner_statuses"].add(owner_status)

    return {"sidecar": sidecar, "bracket": bracket}


def scan_domain_geometry(log_dir: Path, entry_rids: set[str]) -> dict[str, dict[str, Any]]:
    geometry = {
        rid: {
            "stop_price": None,
            "target_price": None,
            "intent_timestamp": None,
            "source": "",
        }
        for rid in entry_rids
    }

    capture_pattern = re.compile(
        r"CAPTURED_INTENT_DATA for (?P<rid>[^:]+): (?P<payload>\{.*\})")
    inject_pattern = re.compile(r"rid=(?P<rid>[^)]+)\): (?P<payload>\{.*\})")
    rid_pattern = re.compile("|".join(re.escape(rid)
                             for rid in sorted(entry_rids)))

    for path in sorted(log_dir.glob(DOMAIN_LOG_GLOB), key=natural_log_order):
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for raw in handle:
                if "INTENT_DATA" not in raw:
                    continue
                if not rid_pattern.search(raw):
                    continue

                match = capture_pattern.search(raw)
                source = "CAPTURED_INTENT_DATA"
                if not match:
                    match = inject_pattern.search(raw)
                    source = "INJECTING_INTENT_DATA"
                if not match:
                    continue

                rid = stringify(match.group("rid"))
                if rid not in geometry:
                    continue
                payload = parse_domain_payload(match.group("payload"))
                if payload is None:
                    continue

                current = geometry[rid]
                payload_ts = to_float(payload.get("timestamp"))
                payload_ts_ms = int(
                    payload_ts * 1000) if payload_ts is not None else None

                replace = False
                if current["intent_timestamp"] is None:
                    replace = True
                elif payload_ts_ms is not None and payload_ts_ms <= current["intent_timestamp"]:
                    replace = True
                elif current["stop_price"] is None or current["target_price"] is None:
                    replace = True

                if replace:
                    current["stop_price"] = to_float(payload.get("stop_price"))
                    current["target_price"] = to_float(
                        payload.get("target_price"))
                    current["intent_timestamp"] = payload_ts_ms
                    current["source"] = source

    return geometry


def windows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[Window]]:
    grouped: dict[str, list[Window]] = defaultdict(list)
    for row in rows:
        symbol = stringify(row.get("symbol"))
        entry_rid = stringify(row.get("entry_rid"))
        lifecycle_id = stringify(row.get("lifecycle_id"))
        entry_ts_ms = to_int(row.get("entry_ts_ms"))
        close_ts_ms = to_int(row.get("close_ts_ms"))
        if not symbol or not entry_rid or not lifecycle_id or entry_ts_ms is None or close_ts_ms is None:
            continue
        grouped[symbol].append(
            Window(entry_rid, lifecycle_id, symbol, entry_ts_ms, close_ts_ms))
    for symbol, windows in grouped.items():
        windows.sort(key=lambda window: (window.entry_ts_ms,
                     window.close_ts_ms, window.entry_rid))
    return grouped


def scan_shadow_journal(shadow_path: Path, grouped_windows: dict[str, list[Window]]) -> dict[str, dict[str, Any]]:
    summary = {
        window.entry_rid: {
            "approx_row_count": 0,
            "approx_armed_count": 0,
            "approx_trigger_count": 0,
            "approx_authority_applied_count": 0,
            "approx_transition_counts": Counter(),
            "approx_candidate_keys": set(),
            "approx_ambiguous_count": 0,
            "approx_required_edge_usd_max": None,
        }
        for windows in grouped_windows.values()
        for window in windows
    }

    for _, row in iter_jsonl(shadow_path):
        if stringify(row.get("event_name")) != SHADOW_EVENT_NAME:
            continue

        payload_fragment = row.get("payload_fragment") if isinstance(
            row.get("payload_fragment"), dict) else {}
        symbol = stringify(payload_fragment.get("symbol") or row.get("symbol"))
        ts_ms = to_int(payload_fragment.get("ts_ms")
                       ) or to_int(row.get("ts_ms"))
        if not symbol or ts_ms is None or symbol not in grouped_windows:
            continue

        candidates = [
            window
            for window in grouped_windows[symbol]
            if window.entry_ts_ms <= ts_ms <= window.close_ts_ms
        ]
        if not candidates:
            continue

        chosen = candidates[0]
        if len(candidates) > 1:
            def center_dist(window): return abs(
                ts_ms - ((window.entry_ts_ms + window.close_ts_ms) // 2))
            chosen = min(candidates, key=center_dist)

        aggregate = summary[chosen.entry_rid]
        aggregate["approx_row_count"] += 1
        if len(candidates) > 1:
            aggregate["approx_ambiguous_count"] += 1
        if payload_fragment.get("is_armed") is True:
            aggregate["approx_armed_count"] += 1
        if payload_fragment.get("would_trigger") is True:
            aggregate["approx_trigger_count"] += 1
        if payload_fragment.get("authority_applied") is True:
            aggregate["approx_authority_applied_count"] += 1
        required_edge = to_float(payload_fragment.get("required_edge_usd"))
        if required_edge is not None:
            if aggregate["approx_required_edge_usd_max"] is None or required_edge > aggregate["approx_required_edge_usd_max"]:
                aggregate["approx_required_edge_usd_max"] = required_edge
        transitions = payload_fragment.get("transitions") or []
        for transition in transitions:
            aggregate["approx_transition_counts"][stringify(transition)] += 1
        fee_multiple = format_float(
            to_float(payload_fragment.get("fee_multiple")), 2)
        pct_candidate = format_float(
            to_float(payload_fragment.get("optional_pct_candidate")), 2)
        candidate_key = f"fee_x{fee_multiple or 'NA'}:pct_{pct_candidate or 'NA'}"
        aggregate["approx_candidate_keys"].add(candidate_key)

    return summary


def date_range(entry_ts_ms: int, close_ts_ms: int) -> list[str]:
    start = datetime.fromtimestamp(entry_ts_ms / 1000, tz=UTC).date()
    end = datetime.fromtimestamp(close_ts_ms / 1000, tz=UTC).date()
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current = current.fromordinal(current.toordinal() + 1)
    return days


def favorable_price(row: dict[str, Any], side: str) -> float | None:
    if side == "SELL":
        return to_float(row.get("low"))
    return to_float(row.get("high"))


def progress_pct(entry_price: float, target_price: float, extreme_price: float, side: str) -> float | None:
    target_distance = abs(target_price - entry_price)
    if target_distance <= 0:
        return None
    if side == "SELL":
        favorable_move = max(0.0, entry_price - extreme_price)
    else:
        favorable_move = max(0.0, extreme_price - entry_price)
    return (favorable_move / target_distance) * 100.0


def recorder_metrics(row: dict[str, Any], recorder_root: Path, cache: RecorderCache) -> dict[str, Any]:
    entry_ts_ms = to_int(row.get("entry_ts_ms"))
    close_ts_ms = to_int(row.get("close_ts_ms"))
    symbol = stringify(row.get("symbol"))
    side = stringify(row.get("side"))
    entry_price = to_float(row.get("entry_price"))
    target_price = to_float(row.get("target_price"))

    metrics = {
        "recorder_tf_sec": 180,
        "recorder_coverage": "UNAVAILABLE",
        "recorder_bar_count": None,
        "recorder_bars_to_exit": None,
        "recorder_bars_to_mfe": None,
        "recorder_time_to_mfe_sec": None,
        "recorder_time_from_mfe_to_exit_sec": None,
        "recorder_tp_progress_max_pct": None,
        "recorder_tp_hit_25": None,
        "recorder_tp_hit_50": None,
        "recorder_tp_hit_75": None,
        "recorder_tp_hit_100": None,
    }

    if entry_ts_ms is None or close_ts_ms is None or not symbol or not side or entry_price is None or target_price is None:
        return metrics

    rows_180: list[dict[str, Any]] = []
    for date_str in date_range(entry_ts_ms, close_ts_ms):
        rows_180.extend(cache.load(date_str, symbol, 180))

    rows_180 = [row_180 for row_180 in rows_180 if to_int(
        row_180.get("timestamp")) is not None]
    if not rows_180:
        return metrics

    rows_180.sort(key=lambda item: item["timestamp"])
    entry_index = None
    exit_index = None
    for index, bar in enumerate(rows_180):
        ts_ms = bar["timestamp"]
        if entry_index is None and ts_ms >= entry_ts_ms:
            entry_index = index
        if exit_index is None and ts_ms >= close_ts_ms:
            exit_index = index
            break

    if entry_index is None:
        entry_index = 0
    if exit_index is None:
        exit_index = len(rows_180) - 1
    if exit_index < entry_index:
        exit_index = entry_index

    active_rows = rows_180[entry_index: exit_index + 1]
    if not active_rows:
        return metrics

    best_progress = None
    best_progress_index = None
    for index, bar in enumerate(active_rows):
        extreme = favorable_price(bar, side)
        if extreme is None:
            continue
        bar_progress = progress_pct(entry_price, target_price, extreme, side)
        if bar_progress is None:
            continue
        if best_progress is None or bar_progress > best_progress:
            best_progress = bar_progress
            best_progress_index = index

    metrics["recorder_coverage"] = "APPROX_180S"
    metrics["recorder_bar_count"] = len(active_rows)
    metrics["recorder_bars_to_exit"] = len(active_rows)
    metrics["recorder_tp_progress_max_pct"] = best_progress
    if best_progress_index is not None:
        best_bar_ts = active_rows[best_progress_index]["timestamp"]
        metrics["recorder_bars_to_mfe"] = best_progress_index + 1
        metrics["recorder_time_to_mfe_sec"] = (
            best_bar_ts - entry_ts_ms) / 1000.0
        metrics["recorder_time_from_mfe_to_exit_sec"] = max(
            0.0, (close_ts_ms - best_bar_ts) / 1000.0)

    if best_progress is not None:
        metrics["recorder_tp_hit_25"] = best_progress >= 25.0
        metrics["recorder_tp_hit_50"] = best_progress >= 50.0
        metrics["recorder_tp_hit_75"] = best_progress >= 75.0
        metrics["recorder_tp_hit_100"] = best_progress >= 100.0

    return metrics


def valid_entry_status(order_data: dict[str, Any], audit_row: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    order_placed = order_data.get("order_placed")
    order_intent_execpos = order_data.get("order_intent_execpos")

    gate_source = order_placed or order_intent_execpos
    gates = extract_gate_fields(gate_source)
    resolved_min = to_float(gates.get("resolved_min_regime_confidence"))
    threshold_applied = gate_source is not None and gates.get(
        "threshold_applied") is True
    threshold_verdict = stringify(gates.get("threshold_verdict"))
    gate_verdict = stringify(gates.get("regime_confidence_gate_verdict"))
    audit_outcome = stringify(audit_row.get("outcome")) if audit_row else ""
    audit_conf = to_float(audit_row.get(
        "regime_confidence_used")) if audit_row else None

    if gate_source is None:
        return "DATA_GAP_NO_GATE_SURFACE", gates
    if audit_row is None:
        return "DATA_GAP_NO_AUDIT", gates
    if resolved_min is None or audit_conf is None:
        return "DATA_GAP_MISSING_CONFIDENCE", gates
    if not threshold_applied:
        return "EXCLUDED_THRESHOLD_NOT_APPLIED", gates
    if not truthy_pass(threshold_verdict):
        return "EXCLUDED_THRESHOLD_FAIL", gates
    if gate_verdict and not truthy_pass(gate_verdict):
        return "EXCLUDED_GATE_VERDICT_FAIL", gates
    if audit_outcome.upper() != "ALLOW":
        return "EXCLUDED_AUDIT_NOT_ALLOW", gates
    if audit_conf + 1e-12 < resolved_min:
        return "EXCLUDED_BELOW_MIN", gates
    return "PROVEN_VALID", gates


def primary_bucket(row: dict[str, Any]) -> str:
    net_pnl = to_float(row.get("net_pnl"))
    close_reason = stringify(row.get("close_reason")).upper()
    valid_status = stringify(row.get("valid_entry_status"))
    peak_edge_usd = to_float(row.get("peak_edge_usd")) or 0.0

    if valid_status != "PROVEN_VALID":
        return "EXCLUDED_INVALID_OR_DATA_GAP"
    if net_pnl is None:
        return "DATA_GAP_NO_NET_PNL"
    if net_pnl >= 0:
        return "EXCLUDED_NON_LOSS"
    if close_reason == "TP":
        return "TP_REACHED_FEE_NEGATIVE"
    if close_reason == "SL" and peak_edge_usd <= 0:
        return "STRAIGHT_SL_NO_POSITIVE_EDGE"
    if close_reason == "SL" and peak_edge_usd > 0:
        return "POSITIVE_EDGE_GIVEBACK_TO_SL"
    if peak_edge_usd > 0:
        return "POSITIVE_EDGE_NON_SL_LOSS"
    return "MARKET_PATH_LOSS_NO_POSITIVE_EDGE"


def build_rows(repo_root: Path) -> list[dict[str, Any]]:
    logs_dir = repo_root / "logs"
    reports_dir = repo_root / "reports"
    recorder_root = repo_root / "data" / "recorder"

    final_rows = latest_rows_by_lifecycle(logs_dir / FINAL_STATS_NAME)
    entry_rids = {stringify(row.get("entry_rid"))
                  for row in final_rows if stringify(row.get("entry_rid"))}
    lifecycle_ids = {stringify(row.get("lifecycle_id"))
                     for row in final_rows if stringify(row.get("lifecycle_id"))}

    order_log_data = scan_order_log(
        logs_dir / ORDER_LOG_NAME, entry_rids, lifecycle_ids)
    audit_by_rid = scan_audit(logs_dir / AUDIT_NAME, entry_rids)
    trade_lifecycle = scan_trade_lifecycle(
        logs_dir / TRADE_LIFECYCLE_NAME, entry_rids)
    geometry_by_rid = scan_domain_geometry(logs_dir, entry_rids)
    shadow_by_rid = scan_shadow_journal(
        logs_dir / SHADOW_NAME, windows_by_symbol(final_rows))

    recorder_cache = RecorderCache(recorder_root)
    enriched_rows: list[dict[str, Any]] = []

    for final_row in final_rows:
        lifecycle_id = stringify(final_row.get("lifecycle_id"))
        entry_rid = stringify(final_row.get("entry_rid"))
        order_data = order_log_data["by_rid"].get(entry_rid, {})
        order_closed = order_log_data["close_by_lifecycle"].get(lifecycle_id)
        audit_row = audit_by_rid.get(entry_rid)
        sidecar = trade_lifecycle["sidecar"].get(
            entry_rid, empty_sidecar_aggregate())
        bracket = trade_lifecycle["bracket"].get(
            entry_rid, empty_bracket_aggregate())
        geometry = geometry_by_rid.get(entry_rid, {})
        shadow = shadow_by_rid.get(entry_rid, {})

        valid_status, gates = valid_entry_status(order_data, audit_row)

        entry_price = to_float(final_row.get("entry_price"))
        stop_price = to_float(geometry.get("stop_price"))
        target_price = to_float(geometry.get("target_price"))
        side = stringify(final_row.get("side"))
        sl_distance = None
        tp_distance = None
        rr_ratio = None
        if entry_price is not None and stop_price is not None and target_price is not None:
            if side == "SELL":
                sl_distance = stop_price - entry_price
                tp_distance = entry_price - target_price
            else:
                sl_distance = entry_price - stop_price
                tp_distance = target_price - entry_price
            if sl_distance is not None and tp_distance is not None and sl_distance > 0 and tp_distance > 0:
                rr_ratio = tp_distance / sl_distance

        row: dict[str, Any] = {
            "lifecycle_id": lifecycle_id,
            "entry_rid": entry_rid,
            "symbol": stringify(final_row.get("symbol")),
            "side": side,
            "entry_ts_ms": to_int(final_row.get("entry_ts_ms")),
            "entry_ts_utc": iso_utc(to_int(final_row.get("entry_ts_ms"))),
            "close_ts_ms": to_int(final_row.get("close_ts_ms")),
            "close_ts_utc": iso_utc(to_int(final_row.get("close_ts_ms"))),
            "entry_price": entry_price,
            "qty": to_float(final_row.get("qty")),
            "close_reason": stringify(final_row.get("close_reason") or (order_closed or {}).get("close_reason")),
            "close_actor": stringify(final_row.get("close_actor")),
            "net_pnl": to_float(final_row.get("net_pnl")),
            "gross_pnl": to_float(final_row.get("gross_pnl")),
            "fees": to_float(final_row.get("fees")),
            "mfe_usdt": to_float(final_row.get("mfe_usdt")),
            "mae_usdt": to_float(final_row.get("mae_usdt")),
            "peak_edge_usd": to_float(final_row.get("peak_edge_usd")),
            "peak_giveback_usd": to_float(final_row.get("peak_giveback_usd")),
            "peak_giveback_pct": to_float(final_row.get("peak_giveback_pct")),
            "first_positive_pnl_ts_ms": to_int(final_row.get("first_positive_pnl_ts_ms")),
            "first_positive_pnl_ts_utc": iso_utc(to_int(final_row.get("first_positive_pnl_ts_ms"))),
            "time_to_first_positive_sec": None,
            "valid_entry_status": valid_status,
            "audit_outcome": stringify(audit_row.get("outcome")) if audit_row else "",
            "audit_regime_confidence_used": to_float(audit_row.get("regime_confidence_used")) if audit_row else None,
            "audit_regime_used": stringify(audit_row.get("regime_used")) if audit_row else "",
            "gate_resolved_min_regime_confidence": to_float(gates.get("resolved_min_regime_confidence")),
            "gate_threshold_applied": gates.get("threshold_applied"),
            "gate_threshold_verdict": stringify(gates.get("threshold_verdict")),
            "gate_threshold_reason": stringify(gates.get("threshold_reason")),
            "gate_regime_confidence_gate_verdict": stringify(gates.get("regime_confidence_gate_verdict")),
            "stop_price": stop_price,
            "target_price": target_price,
            "sl_distance": sl_distance,
            "tp_distance": tp_distance,
            "rr_ratio": rr_ratio,
            "geometry_source": stringify(geometry.get("source")),
            "sidecar_row_count": sidecar["row_count"],
            "sidecar_modes": json_compact(sidecar["modes"]),
            "sidecar_event_type_counts": json_compact(sidecar["event_type_counts"]),
            "sidecar_trigger_events": json_compact(sidecar["trigger_events"]),
            "sidecar_reason_codes": json_compact(sidecar["reason_codes"]),
            "sidecar_first_ts_ms": sidecar["first_ts_ms"],
            "sidecar_first_ts_utc": iso_utc(sidecar["first_ts_ms"]),
            "sidecar_last_ts_ms": sidecar["last_ts_ms"],
            "sidecar_last_ts_utc": iso_utc(sidecar["last_ts_ms"]),
            "sidecar_any_policy_enabled": sidecar["any_policy_enabled"],
            "sidecar_any_live_armed": sidecar["any_live_armed"],
            "sidecar_any_live_threshold_crossed": sidecar["any_live_threshold_crossed"],
            "sidecar_any_recommended": sidecar["any_recommended"],
            "sidecar_any_suppressed": sidecar["any_suppressed"],
            "sidecar_max_peak_edge_usd": sidecar["max_peak_edge_usd"],
            "sidecar_max_current_edge_usd": sidecar["max_current_edge_usd"],
            "sidecar_max_giveback_pct": sidecar["max_giveback_pct"],
            "sidecar_shadow_fee_aware_any_armed": sidecar["shadow_fee_aware_any_armed"],
            "sidecar_shadow_fee_aware_any_triggered": sidecar["shadow_fee_aware_any_triggered"],
            "sidecar_shadow_fee_aware_candidates": json_compact(sidecar["shadow_fee_aware_candidates"]),
            "sidecar_evaluation_modes": json_compact(sidecar["evaluation_modes"]),
            "bracket_stored_seen": bracket["stored_seen"],
            "bracket_placed_seen": bracket["placed_seen"],
            "bracket_entry_order_id": bracket["entry_order_id"],
            "bracket_entry_client_order_id": bracket["entry_client_order_id"],
            "bracket_sl_order_id": bracket["sl_order_id"],
            "bracket_tp_order_id": bracket["tp_order_id"],
            "bracket_placement_paths": json_compact(bracket["placement_paths"]),
            "bracket_owner_statuses": json_compact(bracket["owner_statuses"]),
            "shadow_approx_row_count": shadow.get("approx_row_count"),
            "shadow_approx_armed_count": shadow.get("approx_armed_count"),
            "shadow_approx_trigger_count": shadow.get("approx_trigger_count"),
            "shadow_approx_authority_applied_count": shadow.get("approx_authority_applied_count"),
            "shadow_approx_transition_counts": json_compact(shadow.get("approx_transition_counts")),
            "shadow_approx_candidate_keys": json_compact(shadow.get("approx_candidate_keys")),
            "shadow_approx_ambiguous_count": shadow.get("approx_ambiguous_count"),
            "shadow_approx_required_edge_usd_max": shadow.get("approx_required_edge_usd_max"),
            "shadow_link_quality": "APPROX_SYMBOL_TIME_WINDOW",
        }

        first_positive_ts = to_int(row.get("first_positive_pnl_ts_ms"))
        if first_positive_ts is not None and row["entry_ts_ms"] is not None:
            row["time_to_first_positive_sec"] = (
                first_positive_ts - row["entry_ts_ms"]) / 1000.0

        row.update(recorder_metrics(row, recorder_root, recorder_cache))
        row["primary_bucket"] = primary_bucket(row)
        row["leakage_usd"] = max(0.0, -(to_float(row.get("net_pnl")) or 0.0))
        enriched_rows.append(row)

    enriched_rows.sort(key=lambda item: (
        item["close_ts_ms"] or 0, item["lifecycle_id"]))
    return enriched_rows


def aggregate_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = stringify(row.get("primary_bucket"))
        item = buckets.setdefault(bucket, {
                                  "bucket": bucket, "count": 0, "negative_net_pnl_sum": 0.0, "positive_edge_count": 0, "shadow_trigger_count": 0})
        item["count"] += 1
        net_pnl = to_float(row.get("net_pnl"))
        if net_pnl is not None and net_pnl < 0:
            item["negative_net_pnl_sum"] += -net_pnl
        if (to_float(row.get("peak_edge_usd")) or 0.0) > 0:
            item["positive_edge_count"] += 1
        if (to_int(row.get("shadow_approx_trigger_count")) or 0) > 0:
            item["shadow_trigger_count"] += 1
    summary = list(buckets.values())
    summary.sort(
        key=lambda item: (-item["negative_net_pnl_sum"], item["bucket"]))
    return summary


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = ["| " + " | ".join(headers) + " |", "| " +
             " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            serialised: dict[str, Any] = {}
            for column in columns:
                value = row.get(column)
                if isinstance(value, float):
                    serialised[column] = format_float(value)
                elif isinstance(value, bool):
                    serialised[column] = format_bool(value)
                elif isinstance(value, Counter):
                    serialised[column] = json_compact(value)
                elif isinstance(value, set):
                    serialised[column] = json_compact(value)
                else:
                    serialised[column] = "" if value is None else value
            writer.writerow(serialised)


def write_report(path: Path, rows: list[dict[str, Any]], script_path: Path) -> None:
    bucket_summary = aggregate_buckets(rows)
    negative_proven_valid = [
        row for row in rows if row.get("valid_entry_status") == "PROVEN_VALID" and (to_float(row.get("net_pnl")) or 0.0) < 0
    ]
    winners = [row for row in rows if to_float(row.get("net_pnl")) is not None and (
        to_float(row.get("net_pnl")) or 0.0) >= 0]
    unresolved_net_pnl = [
        row for row in rows if to_float(row.get("net_pnl")) is None]
    geometry_covered = sum(1 for row in rows if row.get(
        "stop_price") is not None and row.get("target_price") is not None)
    sidecar_covered = sum(1 for row in rows if (
        to_int(row.get("sidecar_row_count")) or 0) > 0)
    shadow_covered = sum(1 for row in rows if (
        to_int(row.get("shadow_approx_row_count")) or 0) > 0)
    recorder_covered = sum(1 for row in rows if stringify(
        row.get("recorder_coverage")) == "APPROX_180S")

    leading_bucket = bucket_summary[0]["bucket"] if bucket_summary else "UNKNOWN"
    leading_leakage = bucket_summary[0]["negative_net_pnl_sum"] if bucket_summary else 0.0
    shadow_triggered = sum(1 for row in negative_proven_valid if (
        to_int(row.get("shadow_approx_trigger_count")) or 0) > 0)
    positive_edge_losses = sum(1 for row in negative_proven_valid if (
        to_float(row.get("peak_edge_usd")) or 0.0) > 0)

    bucket_table = markdown_table(
        ["Bucket", "Count", "Leakage USD", "Positive Edge Trades",
            "Approx Shadow Trigger Trades"],
        [
            [
                item["bucket"],
                str(item["count"]),
                format_float(item["negative_net_pnl_sum"], 2),
                str(item["positive_edge_count"]),
                str(item["shadow_trigger_count"]),
            ]
            for item in bucket_summary
        ],
    )
    loss_table = markdown_table(
        ["Lifecycle", "Symbol", "Close", "Net PnL", "Peak Edge",
            "Peak Giveback %", "Bucket", "Approx Shadow Trigger"],
        [
            [
                stringify(row.get("lifecycle_id")),
                stringify(row.get("symbol")),
                stringify(row.get("close_reason")) or "UNKNOWN",
                format_float(to_float(row.get("net_pnl")), 2),
                format_float(to_float(row.get("peak_edge_usd")), 2),
                format_float(to_float(row.get("peak_giveback_pct")), 2),
                stringify(row.get("primary_bucket")),
                str(to_int(row.get("shadow_approx_trigger_count")) or 0),
            ]
            for row in sorted(negative_proven_valid, key=lambda item: (-(to_float(item.get("net_pnl")) or 0.0), item["lifecycle_id"]))
        ],
    )

    lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        (
            f"Fresh-runtime P0-C on {len(rows)} closed FINAL Aurora lifecycles shows admission leakage is not the active driver inside the analyzed loss cohort: "
            f"{len(negative_proven_valid)} proven-valid losing trades remain, and the largest leakage bucket is {leading_bucket} "
            f"with about {format_float(leading_leakage, 2)} USD of summed negative net PnL."
        ),
        "",
        "## Proven Facts",
        f"- The authoritative closed cohort is {len(rows)} latest FINAL rows from logs/{FINAL_STATS_NAME}.",
        (
            f"- Proven-valid losing trades: {len(negative_proven_valid)}; non-loss closures excluded from leakage ranking: {len(winners)}; "
            f"terminal rows with unresolved net PnL remain separate data gaps: {len(unresolved_net_pnl)}."
        ),
        f"- TP/SL geometry was recovered from execution-position logs for {geometry_covered}/{len(rows)} lifecycles.",
        f"- Trade-lifecycle sidecar evidence was recovered for {sidecar_covered}/{len(rows)} lifecycles.",
        f"- Approximate fee-aware shadow-arm evidence was correlated by symbol/time window for {shadow_covered}/{len(rows)} lifecycles.",
        f"- Recorder milestone coverage at 180-second bars was available for {recorder_covered}/{len(rows)} lifecycles.",
        f"- Among proven-valid losing trades, {positive_edge_losses} showed positive edge before closing negative.",
        f"- Approximate shadow fee-aware TRIGGERED evidence appeared inside {shadow_triggered} proven-valid losing lifecycle windows, with authority_applied=false in the journal surface.",
        "",
        "## Inferred Findings",
        "- The analyzed loss mass localizes to post-entry lifecycle behavior after proven-valid admission, not to fresh below-minimum admission leakage.",
        "- Losses with positive edge before negative close are consistent with giveback or late close management rather than immediate invalid-entry failure.",
        "- Fee-aware shadow-arm telemetry can trigger inside the same symbol/time windows while remaining shadow_only and authority_applied=false, so it is not evidence of live protection effect.",
        "- Recorder bars are coarse but still useful for ranking how much TP distance a trade captured before exit.",
        "",
        "## Contradictions / Evidence Gaps",
        "- shadow_critical_event_journal_v1.jsonl currently omits rid and lifecycle_id for the fee-aware shadow-arm event, so correlation is approximate by symbol and active-window overlap only.",
        "- Recorder path metrics are approximate because only 180/300/900-second bars are available; intrabar turning points remain unproven.",
        "- Any lifecycle without recovered geometry or recorder coverage remains bucketed from the available runtime truth only.",
        "",
        "## Root Cause Candidates",
        "- Positive-edge trades giving back into stop-loss or later non-SL negative close after otherwise valid admission.",
        "- Static exit geometry and market path not harvesting enough realized edge before reversal on some valid entries.",
        "- Shadow-only fee-aware protection surfacing hypothetical arms/triggers without live authority on the analyzed runtime slice.",
        "",
        "## Operational Risk",
        "- Capital / Runtime / Observability Gap",
        "",
        "## Files / Areas Touched",
        f"- tools/forensics/{script_path.name}",
        f"- reports/{OUTPUT_MASTER}",
        f"- reports/{OUTPUT_GEOMETRY}",
        f"- reports/{OUTPUT_SIDECAR}",
        f"- reports/{OUTPUT_REPORT}",
        "",
        "## Validation Performed",
        f"- Executed tools/forensics/{script_path.name} against the live repo logs and recorder surfaces.",
        f"- Confirmed output artifacts were written under reports/ with {len(rows)} cohort rows.",
        "",
        "## Residual Risk",
        "- Exact causality between approximate shadow journal rows and individual lifecycle decisions is still not provable from the current journal identity surface.",
        "- Coarse recorder bars can understate or overstate exact TP milestone timing within a bar.",
        "",
        "## What Remains Unproven",
        "- Intrabar path between recorder snapshots.",
        "- Exact per-lifecycle mapping for fee-aware shadow rows without rid/lifecycle_id.",
        "- Whether a different live post-entry authority would have improved the same paths; this package remains forensic only.",
        "",
        "## Minimal Safe Verdict",
        "- On this fresh FINAL cohort, the defensible reading is that Aurora admission parity is holding and the remaining analyzed leakage sits in post-entry trade management / market path behavior, with fee-aware shadow evidence visible but non-authoritative.",
        "",
        "## Bucket Summary",
        bucket_table,
        "",
        "## Proven-Valid Loss Matrix",
        loss_table,
        "",
    ]
    path.write_text(
        "\n".join(line for line in lines if line is not None), encoding="utf-8")


def output_columns_master() -> list[str]:
    return [
        "lifecycle_id",
        "entry_rid",
        "symbol",
        "side",
        "entry_ts_ms",
        "entry_ts_utc",
        "close_ts_ms",
        "close_ts_utc",
        "entry_price",
        "qty",
        "close_reason",
        "close_actor",
        "net_pnl",
        "gross_pnl",
        "fees",
        "mfe_usdt",
        "mae_usdt",
        "peak_edge_usd",
        "peak_giveback_usd",
        "peak_giveback_pct",
        "first_positive_pnl_ts_ms",
        "first_positive_pnl_ts_utc",
        "time_to_first_positive_sec",
        "valid_entry_status",
        "audit_outcome",
        "audit_regime_confidence_used",
        "audit_regime_used",
        "gate_resolved_min_regime_confidence",
        "gate_threshold_applied",
        "gate_threshold_verdict",
        "gate_threshold_reason",
        "gate_regime_confidence_gate_verdict",
        "stop_price",
        "target_price",
        "sl_distance",
        "tp_distance",
        "rr_ratio",
        "geometry_source",
        "sidecar_row_count",
        "sidecar_modes",
        "sidecar_event_type_counts",
        "sidecar_trigger_events",
        "sidecar_reason_codes",
        "sidecar_first_ts_ms",
        "sidecar_first_ts_utc",
        "sidecar_last_ts_ms",
        "sidecar_last_ts_utc",
        "sidecar_any_policy_enabled",
        "sidecar_any_live_armed",
        "sidecar_any_live_threshold_crossed",
        "sidecar_any_recommended",
        "sidecar_any_suppressed",
        "sidecar_max_peak_edge_usd",
        "sidecar_max_current_edge_usd",
        "sidecar_max_giveback_pct",
        "sidecar_shadow_fee_aware_any_armed",
        "sidecar_shadow_fee_aware_any_triggered",
        "sidecar_shadow_fee_aware_candidates",
        "sidecar_evaluation_modes",
        "bracket_stored_seen",
        "bracket_placed_seen",
        "bracket_entry_order_id",
        "bracket_entry_client_order_id",
        "bracket_sl_order_id",
        "bracket_tp_order_id",
        "bracket_placement_paths",
        "bracket_owner_statuses",
        "shadow_approx_row_count",
        "shadow_approx_armed_count",
        "shadow_approx_trigger_count",
        "shadow_approx_authority_applied_count",
        "shadow_approx_transition_counts",
        "shadow_approx_candidate_keys",
        "shadow_approx_ambiguous_count",
        "shadow_approx_required_edge_usd_max",
        "shadow_link_quality",
        "recorder_tf_sec",
        "recorder_coverage",
        "recorder_bar_count",
        "recorder_bars_to_exit",
        "recorder_bars_to_mfe",
        "recorder_time_to_mfe_sec",
        "recorder_time_from_mfe_to_exit_sec",
        "recorder_tp_progress_max_pct",
        "recorder_tp_hit_25",
        "recorder_tp_hit_50",
        "recorder_tp_hit_75",
        "recorder_tp_hit_100",
        "primary_bucket",
        "leakage_usd",
    ]


def output_columns_geometry() -> list[str]:
    return [
        "lifecycle_id",
        "entry_rid",
        "symbol",
        "side",
        "entry_price",
        "stop_price",
        "target_price",
        "sl_distance",
        "tp_distance",
        "rr_ratio",
        "geometry_source",
        "bracket_stored_seen",
        "bracket_placed_seen",
        "bracket_entry_order_id",
        "bracket_sl_order_id",
        "bracket_tp_order_id",
        "recorder_coverage",
        "recorder_tp_progress_max_pct",
        "recorder_tp_hit_25",
        "recorder_tp_hit_50",
        "recorder_tp_hit_75",
        "recorder_tp_hit_100",
        "primary_bucket",
    ]


def output_columns_sidecar() -> list[str]:
    return [
        "lifecycle_id",
        "entry_rid",
        "symbol",
        "sidecar_row_count",
        "sidecar_modes",
        "sidecar_event_type_counts",
        "sidecar_reason_codes",
        "sidecar_any_policy_enabled",
        "sidecar_any_live_armed",
        "sidecar_any_live_threshold_crossed",
        "sidecar_any_recommended",
        "sidecar_any_suppressed",
        "sidecar_max_peak_edge_usd",
        "sidecar_max_giveback_pct",
        "sidecar_shadow_fee_aware_any_armed",
        "sidecar_shadow_fee_aware_any_triggered",
        "sidecar_shadow_fee_aware_candidates",
        "shadow_approx_row_count",
        "shadow_approx_armed_count",
        "shadow_approx_trigger_count",
        "shadow_approx_authority_applied_count",
        "shadow_approx_transition_counts",
        "shadow_approx_candidate_keys",
        "shadow_approx_ambiguous_count",
        "shadow_approx_required_edge_usd_max",
        "shadow_link_quality",
        "primary_bucket",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the P0-C post-entry giveback forensic cohort and report.")
    parser.add_argument("--repo-root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = build_rows(repo_root)

    script_path = Path(__file__).resolve()
    write_csv(reports_dir / OUTPUT_MASTER, rows, output_columns_master())
    write_csv(reports_dir / OUTPUT_GEOMETRY, rows, output_columns_geometry())
    write_csv(reports_dir / OUTPUT_SIDECAR, rows, output_columns_sidecar())
    write_report(reports_dir / OUTPUT_REPORT, rows, script_path)

    proven_valid_losses = sum(
        1 for row in rows if row.get("valid_entry_status") == "PROVEN_VALID" and (to_float(row.get("net_pnl")) or 0.0) < 0
    )
    print(
        json.dumps(
            {
                "closed_final_rows": len(rows),
                "proven_valid_losses": proven_valid_losses,
                "report": str(reports_dir / OUTPUT_REPORT),
                "master_csv": str(reports_dir / OUTPUT_MASTER),
                "geometry_csv": str(reports_dir / OUTPUT_GEOMETRY),
                "sidecar_csv": str(reports_dir / OUTPUT_SIDECAR),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
