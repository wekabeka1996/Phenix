from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_FREEZE_PATH = Path(
    "logs/frozen/nrr062_post_prompt18_capture_20260514_024741"
)
BASE_MANIFEST_PATH = BASE_FREEZE_PATH / "MANIFEST.json"
BASE_CASES_PATH = BASE_FREEZE_PATH / "nrr062_cases_PROMPT19.jsonl"
BASE_SUMMARY_PATH = BASE_FREEZE_PATH / "nrr062_coverage_summary_PROMPT19.json"
BASE_REPORT_PATH = Path(
    "reports/nrr062_post_prompt18_runtime_validation_PROMPT19.md")
PROMPT18_REPORT_PATH = Path(
    "reports/nrr062_ret_observability_patch_PROMPT18.md")
OUTPUT_REPORT_PATH = Path("reports/nrr062_collection_extension_PROMPT20.md")

EXTENSION_PREFIX = "nrr062_post_prompt18_extension_"
PATCH_ANCHOR_TS_MS = 1778508291000  # 2026-05-11T14:44:51+00:00
PROMPT19_START_TS_MS = 1778552591605
PROMPT19_END_TS_MS = 1778716062011
REPLAY_HORIZON_MINUTES = 120
REPLAY_HORIZON_MS = REPLAY_HORIZON_MINUTES * 60 * 1000
REPLAY_HORIZONS = (15, 30, 60, 120)
REPLAY_PREFERRED_TFS = (180, 300, 900)
REPLAY_FINEST_TFS = (180, 300, 900)

TRACKED_FIELD_NAMES = (
    "ret_60s",
    "ret_300s",
    "pm_norm_60s",
    "pm_norm_300s",
    "vol_pct_300s",
    "spread_bps",
    "liquidity_kappa",
    "absorption",
)

RUNTIME_LOG_PATHS = (
    Path("logs/order_log_v1.jsonl"),
    Path("logs/shadow_critical_event_journal_v1.jsonl"),
    Path("logs/regime_confidence_audit_v1.jsonl"),
    Path("logs/trade_lifecycle.jsonl"),
)

VERDICT_NEEDS_MORE_RUNTIME = "NEEDS_MORE_RUNTIME"
VERDICT_EXTENSION_FROZEN_REPLAY_NOT_READY = "EXTENSION_FROZEN_REPLAY_NOT_READY"
VERDICT_EXTENSION_FROZEN_READY_FOR_REPLAY = "EXTENSION_FROZEN_READY_FOR_REPLAY"
VERDICT_REPLAY_COMPLETED_READY_FOR_PROMPT21_SWEEP = (
    "REPLAY_COMPLETED_READY_FOR_PROMPT21_SWEEP"
)
VERDICT_BLOCKED_EXISTING_FREEZE_INVALID = "BLOCKED_EXISTING_FREEZE_INVALID"
VERDICT_BLOCKED_MIXED_PRE_POST_PATCH_ROWS = "BLOCKED_MIXED_PRE_POST_PATCH_ROWS"
VERDICT_BLOCKED_RECORDER_HORIZON_PENDING = "BLOCKED_RECORDER_HORIZON_PENDING"
VERDICT_BLOCKED_RECORDER_COVERAGE = "BLOCKED_RECORDER_COVERAGE"


@dataclass(slots=True)
class RecorderFileInfo:
    path: Path
    symbol: str
    tf_sec: int
    min_ts_ms: int | None
    max_ts_ms: int | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return datetime.now().astimezone()


def iso_from_ts_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def duration_string(start_ts_ms: int | None, end_ts_ms: int | None) -> str | None:
    if start_ts_ms is None or end_ts_ms is None or end_ts_ms < start_ts_ms:
        return None
    delta = timedelta(milliseconds=end_ts_ms - start_ts_ms)
    total_seconds = delta.total_seconds()
    days = delta.days
    remainder = total_seconds - days * 86400
    hours = int(remainder // 3600)
    remainder -= hours * 3600
    minutes = int(remainder // 60)
    seconds = remainder - minutes * 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds:.3f}s")
    return " ".join(parts)


def safe_json(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def get_nested(container: Any, *keys: str) -> Any:
    current = container
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    malformed = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            payload = safe_json(line)
            if payload is None:
                malformed += 1
                continue
            rows.append(payload)
    return rows, malformed


def detect_timestamp_ms(row: dict[str, Any]) -> int | None:
    candidates = (
        row.get("ts_ms"),
        row.get("timestamp"),
        row.get("ts"),
        row.get("event_ts_ms"),
        get_nested(row, "metadata", "ts_ms"),
        get_nested(row, "payload", "ts_ms"),
    )
    for candidate in candidates:
        value = as_int(candidate)
        if value is not None:
            return value
    return None


def low_vol_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    candidates = (
        get_nested(row, "metadata", "low_vol_cost_floor"),
        row.get("low_vol_cost_floor"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def low_vol_missing_map(section: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(section, dict):
        return {}
    missing_map = first_non_none(section.get(
        "missing_inputs"), section.get("missing"))
    return dict(missing_map) if isinstance(missing_map, dict) else {}


def extract_field_status(payload: dict[str, Any] | None, field_name: str) -> dict[str, bool]:
    if not isinstance(payload, dict):
        return {
            "present_non_null": False,
            "present_null": False,
            "missing_key": True,
            "explicit_missing": False,
        }
    missing_map = low_vol_missing_map(payload)
    if field_name not in payload:
        return {
            "present_non_null": False,
            "present_null": False,
            "missing_key": True,
            "explicit_missing": bool(missing_map.get(field_name)),
        }
    value = payload.get(field_name)
    return {
        "present_non_null": value is not None,
        "present_null": value is None,
        "missing_key": False,
        "explicit_missing": bool(missing_map.get(field_name)),
    }


def price_motion_payload(low_vol: dict[str, Any]) -> dict[str, Any]:
    payload = low_vol.get("price_motion_context")
    return dict(payload) if isinstance(payload, dict) else {}


def liquidity_payload(low_vol: dict[str, Any]) -> dict[str, Any]:
    payload = low_vol.get("liquidity_context")
    return dict(payload) if isinstance(payload, dict) else {}


def regime_value(low_vol: dict[str, Any]) -> Any:
    return first_non_none(low_vol.get("regime"), get_nested(low_vol, "provenance_context", "regime"))


def canonical_reason(row: dict[str, Any], low_vol: dict[str, Any]) -> str | None:
    return first_non_none(
        low_vol.get("reason"),
        row.get("why"),
        get_nested(row, "metadata", "reject_reason"),
    )


def canonical_subreason(low_vol: dict[str, Any]) -> str | None:
    return first_non_none(
        low_vol.get("direction_confidence_failure_reason"),
        low_vol.get("original_low_vol_reason"),
        low_vol.get("gate_reason"),
    )


def is_nrr062_deny_row(row: dict[str, Any], low_vol: dict[str, Any] | None) -> bool:
    return (
        row.get("event_type") == "DECISION_INTENT_REJECTED"
        and row.get("nrr_code") == "NRR-062"
        and isinstance(low_vol, dict)
    )


def is_low_vol_allow_row(row: dict[str, Any], low_vol: dict[str, Any] | None) -> bool:
    if row.get("event_type") != "ORDER_INTENT" or not isinstance(low_vol, dict):
        return False
    if low_vol.get("gate_reason") == "LOW_VOL_COST_FLOOR_PASS":
        return True
    if low_vol.get("reason") == "LOW_VOL_COST_FLOOR_SEGMENT_OVERRIDE_ALLOW":
        return True
    return bool(low_vol.get("nrr062_segment_override_applied"))


def inferred_nrr_code(row: dict[str, Any], low_vol: dict[str, Any]) -> str | None:
    direct = row.get("nrr_code")
    if isinstance(direct, str):
        return direct
    if low_vol.get("original_nrr062_reason") == "LOW_VOL_COST_FLOOR_BLOCKED":
        return "NRR-062"
    if low_vol.get("nrr062_segment_override_applied"):
        return "NRR-062"
    return None


def final_gate_verdict(row: dict[str, Any], low_vol: dict[str, Any]) -> dict[str, bool]:
    if is_nrr062_deny_row(row, low_vol):
        return {"allowed": False, "denied": True}
    if is_low_vol_allow_row(row, low_vol):
        return {"allowed": True, "denied": False}
    gate_reason = low_vol.get("gate_reason")
    if gate_reason == "LOW_VOL_COST_FLOOR_BLOCKED":
        return {"allowed": False, "denied": True}
    if gate_reason == "LOW_VOL_COST_FLOOR_PASS":
        return {"allowed": True, "denied": False}
    return {"allowed": False, "denied": False}


def total_cost_bps_for_row(row: dict[str, Any]) -> float:
    economics = get_nested(row, "low_vol_cost_floor", "economics")
    geometry = get_nested(row, "low_vol_cost_floor", "geometry")
    if isinstance(economics, dict) and isinstance(geometry, dict):
        actual_tp_bps = as_float(geometry.get("actual_tp_bps"))
        expected_tp = as_float(economics.get("expected_net_if_tp_bps"))
        if actual_tp_bps is not None and expected_tp is not None:
            diff = actual_tp_bps - expected_tp
            if diff >= 0:
                return diff
        actual_sl_bps = as_float(geometry.get("actual_sl_bps"))
        expected_sl = as_float(economics.get("expected_net_if_sl_bps"))
        if actual_sl_bps is not None and expected_sl is not None:
            diff = abs(expected_sl) - actual_sl_bps
            if diff >= 0:
                return diff
        round_trip_fee_bps = as_float(economics.get("round_trip_fee_bps"))
        if round_trip_fee_bps is not None:
            return round_trip_fee_bps
    return 0.0


def load_base_validation(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    for required in (BASE_MANIFEST_PATH, BASE_CASES_PATH, BASE_SUMMARY_PATH, BASE_REPORT_PATH, PROMPT18_REPORT_PATH):
        if not (root / required).exists():
            errors.append(f"missing:{required.as_posix()}")
    if errors:
        return {}, [], errors

    manifest = read_json(root / BASE_MANIFEST_PATH)
    summary = read_json(root / BASE_SUMMARY_PATH)
    base_rows, base_malformed = load_jsonl(root / BASE_CASES_PATH)

    if base_malformed:
        errors.append(f"base_cases_malformed:{base_malformed}")
    if len(base_rows) != 128:
        errors.append(f"base_row_count:{len(base_rows)}")

    if summary.get("field_coverage", {}).get("ret_60s", {}).get("non_null_pct") != 100.0:
        errors.append("base_ret_60s_non_null_not_100")
    if summary.get("field_coverage", {}).get("ret_300s", {}).get("non_null_pct") != 100.0:
        errors.append("base_ret_300s_non_null_not_100")

    computed_ret_60s = 0
    computed_ret_300s = 0
    for row in base_rows:
        pm = get_nested(row, "low_vol_cost_floor", "price_motion_context")
        if isinstance(pm, dict) and pm.get("ret_60s") is not None:
            computed_ret_60s += 1
        if isinstance(pm, dict) and pm.get("ret_300s") is not None:
            computed_ret_300s += 1

    if computed_ret_60s != 128:
        errors.append(f"base_ret_60s_count:{computed_ret_60s}")
    if computed_ret_300s != 128:
        errors.append(f"base_ret_300s_count:{computed_ret_300s}")

    return {"manifest": manifest, "summary": summary}, base_rows, errors


def scan_recorder_file(path: Path) -> RecorderFileInfo | None:
    symbol, tf = parse_symbol_tf(path)
    if symbol is None or tf is None:
        return None

    min_ts: int | None = None
    max_ts: int | None = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        header = handle.readline().strip().split(",")
        if not header:
            return RecorderFileInfo(path=path, symbol=symbol, tf_sec=tf, min_ts_ms=None, max_ts_ms=None)
        try:
            ts_index = header.index("timestamp")
        except ValueError:
            try:
                ts_index = header.index("open_time")
            except ValueError:
                return RecorderFileInfo(path=path, symbol=symbol, tf_sec=tf, min_ts_ms=None, max_ts_ms=None)

        for line in handle:
            parts = line.strip().split(",")
            if len(parts) <= ts_index:
                continue
            ts_ms = as_int(parts[ts_index])
            if ts_ms is None:
                continue
            min_ts = ts_ms if min_ts is None else min(min_ts, ts_ms)
            max_ts = ts_ms if max_ts is None else max(max_ts, ts_ms)
    return RecorderFileInfo(path=path, symbol=symbol, tf_sec=tf, min_ts_ms=min_ts, max_ts_ms=max_ts)


def parse_symbol_tf(path: Path) -> tuple[str | None, int | None]:
    parts = path.stem.split("_")
    if len(parts) < 2:
        return None, None
    symbol = parts[0].upper()
    tf = as_int(parts[-1])
    return symbol, tf


def recorder_dates_for_rows(rows: list[dict[str, Any]]) -> set[str]:
    dates: set[str] = set()
    for row in rows:
        ts_ms = as_int(row.get("ts_ms"))
        if ts_ms is None:
            continue
        start = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(
            (ts_ms + REPLAY_HORIZON_MS) / 1000, tz=timezone.utc)
        cursor = datetime(start.year, start.month,
                          start.day, tzinfo=timezone.utc)
        while cursor.date() <= end.date():
            dates.add(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
    return dates


def build_workspace_recorder_index(root: Path, dates: set[str], symbols: set[str] | None = None) -> dict[str, dict[int, list[RecorderFileInfo]]]:
    by_symbol: dict[str, dict[int, list[RecorderFileInfo]]
                    ] = defaultdict(lambda: defaultdict(list))
    recorder_root = root / "data" / "recorder"
    if not recorder_root.exists():
        return {}
    for date_str in sorted(dates):
        day_dir = recorder_root / date_str
        if not day_dir.exists():
            continue
        for csv_path in sorted(day_dir.glob("*.csv")):
            info = scan_recorder_file(csv_path)
            if info is None:
                continue
            if symbols and info.symbol not in symbols:
                continue
            by_symbol[info.symbol][info.tf_sec].append(info)
    return by_symbol


def recorder_file_count(index: dict[str, dict[int, list[RecorderFileInfo]]]) -> int:
    return sum(len(files) for tf_map in index.values() for files in tf_map.values())


def aggregated_recorder_max(index: dict[str, dict[int, list[RecorderFileInfo]]]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for symbol, tf_map in index.items():
        max_ts: int | None = None
        for files in tf_map.values():
            for file_info in files:
                if file_info.max_ts_ms is None:
                    continue
                max_ts = file_info.max_ts_ms if max_ts is None else max(
                    max_ts, file_info.max_ts_ms)
        result[symbol] = max_ts
    return result


def row_timeframe_coverage(row: dict[str, Any], recorder_index: dict[str, dict[int, list[RecorderFileInfo]]]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    ts_ms = as_int(row.get("ts_ms"))
    if not symbol or ts_ms is None:
        return {
            "has_symbol_recorder": False,
            "15m": False,
            "30m": False,
            "60m": False,
            "120m": False,
            "best_timeframe_sec": None,
            "latest_available_ts_ms": None,
        }

    tf_map = recorder_index.get(symbol, {})
    if not tf_map:
        return {
            "has_symbol_recorder": False,
            "15m": False,
            "30m": False,
            "60m": False,
            "120m": False,
            "best_timeframe_sec": None,
            "latest_available_ts_ms": None,
        }

    max_ts_by_tf: dict[int, int] = {}
    for tf_sec, files in tf_map.items():
        max_ts = max((file.max_ts_ms or -1) for file in files)
        if max_ts >= 0:
            max_ts_by_tf[tf_sec] = max_ts

    horizons = {
        15: False,
        30: False,
        60: False,
        120: False,
    }
    best_timeframe_sec: int | None = None
    for tf_sec in sorted(max_ts_by_tf):
        max_ts = max_ts_by_tf[tf_sec]
        for minutes in REPLAY_HORIZONS:
            if max_ts >= ts_ms + minutes * 60 * 1000:
                horizons[minutes] = True
        if best_timeframe_sec is None and max_ts >= ts_ms + REPLAY_HORIZON_MS:
            best_timeframe_sec = tf_sec

    latest_available_ts_ms = max(
        max_ts_by_tf.values()) if max_ts_by_tf else None
    return {
        "has_symbol_recorder": True,
        "15m": horizons[15],
        "30m": horizons[30],
        "60m": horizons[60],
        "120m": horizons[120],
        "best_timeframe_sec": best_timeframe_sec,
        "latest_available_ts_ms": latest_available_ts_ms,
    }


def relevant_row_from_runtime(
    row: dict[str, Any],
    line_no: int,
    source_file: str,
    recorder_index: dict[str, dict[int, list[RecorderFileInfo]]],
) -> dict[str, Any] | None:
    ts_ms = detect_timestamp_ms(row)
    if ts_ms is None or ts_ms <= PROMPT19_END_TS_MS:
        return None
    low_vol = low_vol_payload(row)
    if not isinstance(low_vol, dict):
        return None
    if not (is_nrr062_deny_row(row, low_vol) or is_low_vol_allow_row(row, low_vol)):
        return None

    price_motion = price_motion_payload(low_vol)
    liquidity = liquidity_payload(low_vol)
    evidence_refs = {
        "order_log_line": line_no,
        "shadow_line": None,
        "regime_audit_line": None,
        "trade_lifecycle_line": None,
        "core_log_line": None,
    }
    replay_ready = row_timeframe_coverage(
        {"symbol": row.get("symbol"), "ts_ms": ts_ms}, recorder_index
    )

    result: dict[str, Any] = {
        "rid": row.get("rid"),
        "lifecycle_id": row.get("lifecycle_id"),
        "ts_ms": ts_ms,
        "ts_iso": iso_from_ts_ms(ts_ms),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "strategy_id": row.get("strategy_id"),
        "source_file": source_file,
        "source_line": line_no,
        "event_type": row.get("event_type"),
        "nrr_code": inferred_nrr_code(row, low_vol),
        "reason": canonical_reason(row, low_vol),
        "subreason": canonical_subreason(low_vol),
        "final_gate_verdict": final_gate_verdict(row, low_vol),
        "low_vol_cost_floor": {
            "verdict": "ALLOW"
            if is_low_vol_allow_row(row, low_vol)
            else "DENY",
            "regime": regime_value(low_vol),
            "score_context": low_vol.get("score_context") if isinstance(low_vol.get("score_context"), dict) else {},
            "direction_confidence": as_float(low_vol.get("direction_confidence")),
            "geometry": {
                "entry_price": as_float(low_vol.get("entry_price")),
                "target_price": as_float(low_vol.get("target_price")),
                "stop_price": as_float(low_vol.get("stop_price")),
                "actual_tp_bps": as_float(low_vol.get("actual_tp_bps")),
                "actual_sl_bps": as_float(low_vol.get("actual_sl_bps")),
                "geometry_available": bool(low_vol.get("geometry_available")),
                "geometry_valid": bool(low_vol.get("geometry_valid")),
            },
            "economics": {
                "round_trip_fee_bps": as_float(low_vol.get("round_trip_fee_bps")),
                "required_gross_tp_bps": as_float(low_vol.get("required_gross_tp_bps")),
                "target_net_fee_multiple": as_float(low_vol.get("target_net_fee_multiple")),
                "tp_fee_coverage_ratio": as_float(low_vol.get("tp_fee_coverage_ratio")),
                "rr_ratio": as_float(low_vol.get("rr_ratio")),
                "expected_net_if_tp_bps": as_float(low_vol.get("expected_net_if_tp_bps")),
                "expected_net_if_sl_bps": as_float(low_vol.get("expected_net_if_sl_bps")),
            },
            "price_motion_context": {
                "ret_60s": as_float(price_motion.get("ret_60s")),
                "ret_300s": as_float(price_motion.get("ret_300s")),
                "pm_norm_60s": as_float(price_motion.get("pm_norm_60s")),
                "pm_norm_300s": as_float(price_motion.get("pm_norm_300s")),
                "vol_pct_300s": as_float(price_motion.get("vol_pct_300s")),
                "missing_inputs": low_vol_missing_map(price_motion),
            },
            "liquidity_context": {
                "spread_bps": as_float(liquidity.get("spread_bps")),
                "liquidity_kappa": as_float(liquidity.get("liquidity_kappa")),
                "absorption": as_float(liquidity.get("absorption")),
                "missing_inputs": low_vol_missing_map(liquidity),
            },
            "violations": list(low_vol.get("violations")) if isinstance(low_vol.get("violations"), list) else [],
            "provenance": {
                "source_fsm": row.get("source_fsm"),
                "origin_class": row.get("origin_class"),
                "alias_of": get_nested(row, "metadata", "alias_of"),
                "canonical_event_family": get_nested(row, "metadata", "canonical_event_family"),
                "evaluation_stage": low_vol.get("evaluation_stage"),
                "nrr062_segment_override_applied": bool(low_vol.get("nrr062_segment_override_applied")),
            },
        },
        "post_prompt18_field_status": {
            "ret_60s": extract_field_status(result_low_vol_section := {
                "ret_60s": as_float(price_motion.get("ret_60s")),
                "ret_300s": as_float(price_motion.get("ret_300s")),
                "pm_norm_60s": as_float(price_motion.get("pm_norm_60s")),
                "pm_norm_300s": as_float(price_motion.get("pm_norm_300s")),
                "vol_pct_300s": as_float(price_motion.get("vol_pct_300s")),
                **({"missing_inputs": low_vol_missing_map(price_motion)}),
            }, "ret_60s"),
            "ret_300s": extract_field_status(result_low_vol_section, "ret_300s"),
            "pm_norm_60s": extract_field_status(result_low_vol_section, "pm_norm_60s"),
            "pm_norm_300s": extract_field_status(result_low_vol_section, "pm_norm_300s"),
            "vol_pct_300s": extract_field_status(result_low_vol_section, "vol_pct_300s"),
            "spread_bps": extract_field_status({
                "spread_bps": as_float(liquidity.get("spread_bps")),
                "liquidity_kappa": as_float(liquidity.get("liquidity_kappa")),
                "absorption": as_float(liquidity.get("absorption")),
                "missing_inputs": low_vol_missing_map(liquidity),
            }, "spread_bps"),
            "liquidity_kappa": extract_field_status({
                "spread_bps": as_float(liquidity.get("spread_bps")),
                "liquidity_kappa": as_float(liquidity.get("liquidity_kappa")),
                "absorption": as_float(liquidity.get("absorption")),
                "missing_inputs": low_vol_missing_map(liquidity),
            }, "liquidity_kappa"),
            "absorption": extract_field_status({
                "spread_bps": as_float(liquidity.get("spread_bps")),
                "liquidity_kappa": as_float(liquidity.get("liquidity_kappa")),
                "absorption": as_float(liquidity.get("absorption")),
                "missing_inputs": low_vol_missing_map(liquidity),
            }, "absorption"),
        },
        "recorder_replay_ready": {
            "15m": replay_ready["15m"],
            "30m": replay_ready["30m"],
            "60m": replay_ready["60m"],
            "120m": replay_ready["120m"],
        },
        "recorder_meta": {
            "has_symbol_recorder": replay_ready["has_symbol_recorder"],
            "best_timeframe_sec": replay_ready["best_timeframe_sec"],
            "latest_available_ts_ms": replay_ready["latest_available_ts_ms"],
        },
        "evidence_refs": evidence_refs,
        "identity": {
            "rid": row.get("rid"),
            "lifecycle_id": row.get("lifecycle_id"),
        },
    }
    return result


def scan_runtime_extension_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    order_log = root / "logs" / "order_log_v1.jsonl"
    all_rows, malformed = load_jsonl(order_log)
    all_ts = [detect_timestamp_ms(row) for row in all_rows]
    latest_order_log_ts = max(
        (ts for ts in all_ts if ts is not None), default=None)

    relevant_order_rows = [row for row in all_rows if detect_timestamp_ms(
        row) and detect_timestamp_ms(row) > PROMPT19_END_TS_MS]
    relevant_symbols = {
        str(row.get("symbol")).upper()
        for row in relevant_order_rows
        if row.get("symbol")
    }
    recorder_dates = recorder_dates_for_rows(
        [{"ts_ms": detect_timestamp_ms(
            row)} for row in relevant_order_rows if detect_timestamp_ms(row) is not None]
    )
    recorder_index = build_workspace_recorder_index(
        root, recorder_dates, relevant_symbols)

    rows: list[dict[str, Any]] = []
    for line_no, row in enumerate(all_rows, start=1):
        extracted = relevant_row_from_runtime(
            row,
            line_no,
            "logs/order_log_v1.jsonl",
            recorder_index,
        )
        if extracted is not None:
            rows.append(extracted)

    field_coverage = compute_field_coverage(rows)
    latest_case_ts = max((as_int(row.get("ts_ms")) for row in rows if as_int(
        row.get("ts_ms")) is not None), default=None)
    recorder_max_by_symbol = aggregated_recorder_max(recorder_index)
    latest_case_symbol = None
    if latest_case_ts is not None:
        for row in reversed(rows):
            if as_int(row.get("ts_ms")) == latest_case_ts:
                latest_case_symbol = str(row.get("symbol") or "").upper()
                break
    latest_symbol_max = recorder_max_by_symbol.get(
        latest_case_symbol) if latest_case_symbol else None
    horizon_complete = (
        latest_case_ts is not None
        and latest_symbol_max is not None
        and latest_symbol_max >= latest_case_ts + REPLAY_HORIZON_MS
    )

    probe = {
        "scan_ts": utc_now().isoformat(),
        "post_prompt19_window": {
            "start_ts": PROMPT19_END_TS_MS + 1,
            "end_ts": latest_order_log_ts,
            "duration": duration_string(PROMPT19_END_TS_MS + 1, latest_order_log_ts),
        },
        "new_low_vol_cost_floor_rows": len(rows),
        "new_nrr062_denies": sum(
            1
            for row in rows
            if row.get("final_gate_verdict", {}).get("denied")
            and row.get("nrr_code") == "NRR-062"
        ),
        "new_low_vol_allows": sum(
            1 for row in rows if row.get("final_gate_verdict", {}).get("allowed")
        ),
        "symbols": sorted({str(row.get("symbol")) for row in rows if row.get("symbol")}),
        "strategies": sorted({str(row.get("strategy_id")) for row in rows if row.get("strategy_id")}),
        "ret_60s_non_null_pct": field_coverage["ret_60s_non_null_pct"],
        "ret_300s_non_null_pct": field_coverage["ret_300s_non_null_pct"],
        "recorder_files_available": recorder_file_count(recorder_index),
        "recorder_horizon_ready_for_latest_case": horizon_complete,
        "row_level_cohort_present": bool(rows),
        "order_log_malformed_rows": malformed,
        "latest_case_symbol": latest_case_symbol,
        "recorder_dates_considered": sorted(recorder_dates),
    }
    return rows, {
        "probe": probe,
        "field_coverage": field_coverage,
        "recorder_index": recorder_index,
        "recorder_max_by_symbol": recorder_max_by_symbol,
        "latest_case_ts": latest_case_ts,
        "latest_case_symbol": latest_case_symbol,
        "latest_order_log_ts": latest_order_log_ts,
    }


def compute_field_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    counters = {
        field: {"present_non_null": 0, "present_null": 0,
                "missing_key": 0, "explicit_missing": 0}
        for field in TRACKED_FIELD_NAMES
    }
    geometry_complete = 0
    economics_complete = 0
    score_context_complete = 0
    direction_confidence_complete = 0
    price_motion_complete = 0
    liquidity_complete = 0
    explicit_missing_count = 0
    explicit_missing_denominator = 0

    for row in rows:
        low_vol = get_nested(row, "low_vol_cost_floor")
        price_motion = get_nested(
            low_vol, "price_motion_context") if isinstance(low_vol, dict) else {}
        liquidity = get_nested(low_vol, "liquidity_context") if isinstance(
            low_vol, dict) else {}
        price_motion_missing = low_vol_missing_map(
            price_motion if isinstance(price_motion, dict) else None)
        liquidity_missing = low_vol_missing_map(
            liquidity if isinstance(liquidity, dict) else None)
        row_sections = {
            "ret_60s": price_motion,
            "ret_300s": price_motion,
            "pm_norm_60s": price_motion,
            "pm_norm_300s": price_motion,
            "vol_pct_300s": price_motion,
            "spread_bps": liquidity,
            "liquidity_kappa": liquidity,
            "absorption": liquidity,
        }
        for field in TRACKED_FIELD_NAMES:
            status = extract_field_status(row_sections[field] if isinstance(
                row_sections[field], dict) else None, field)
            for key in ("present_non_null", "present_null", "missing_key"):
                counters[field][key] += 1 if status[key] else 0
            counters[field]["explicit_missing"] += 1 if status["explicit_missing"] else 0
            explicit_missing_denominator += 1
            explicit_missing_count += 1 if status["explicit_missing"] else 0

        geometry = get_nested(low_vol, "geometry") if isinstance(
            low_vol, dict) else {}
        economics = get_nested(low_vol, "economics") if isinstance(
            low_vol, dict) else {}
        score_context = get_nested(
            low_vol, "score_context") if isinstance(low_vol, dict) else {}
        if isinstance(geometry, dict) and all(
            geometry.get(name) is not None
            for name in ("entry_price", "target_price", "stop_price", "actual_tp_bps", "actual_sl_bps")
        ):
            geometry_complete += 1
        if isinstance(economics, dict) and all(
            economics.get(name) is not None
            for name in (
                "round_trip_fee_bps",
                "required_gross_tp_bps",
                "target_net_fee_multiple",
                "tp_fee_coverage_ratio",
                "rr_ratio",
                "expected_net_if_tp_bps",
                "expected_net_if_sl_bps",
            )
        ):
            economics_complete += 1
        if isinstance(score_context, dict) and score_context:
            score_context_complete += 1
        if get_nested(low_vol, "direction_confidence") is not None:
            direction_confidence_complete += 1
        if isinstance(price_motion, dict) and all(
            key in price_motion for key in ("ret_60s", "ret_300s", "pm_norm_60s", "pm_norm_300s", "vol_pct_300s")
        ):
            price_motion_complete += 1
        if isinstance(liquidity, dict) and all(
            key in liquidity for key in ("spread_bps", "liquidity_kappa", "absorption")
        ):
            liquidity_complete += 1

    result: dict[str, Any] = {}
    for field in TRACKED_FIELD_NAMES:
        field_total = counters[field]["present_non_null"] + \
            counters[field]["present_null"] + counters[field]["missing_key"]
        result[f"{field}_non_null_pct"] = round(
            100 * counters[field]["present_non_null"] / field_total, 3
        ) if field_total else 0.0
        result[field] = {
            **counters[field],
            "non_null_pct": round(
                100 * counters[field]["present_non_null"] / field_total, 3
            ) if field_total else 0.0,
        }
    result["geometry_complete_pct"] = round(
        100 * geometry_complete / total, 3) if total else 0.0
    result["economics_complete_pct"] = round(
        100 * economics_complete / total, 3) if total else 0.0
    result["geometry_economics_complete_pct"] = round(
        100 * min(geometry_complete, economics_complete) / total, 3
    ) if total else 0.0
    result["score_context_complete_pct"] = round(
        100 * score_context_complete / total, 3) if total else 0.0
    result["direction_confidence_complete_pct"] = round(
        100 * direction_confidence_complete / total, 3
    ) if total else 0.0
    result["price_motion_context_complete_pct"] = round(
        100 * price_motion_complete / total, 3
    ) if total else 0.0
    result["liquidity_context_complete_pct"] = round(
        100 * liquidity_complete / total, 3
    ) if total else 0.0
    result["explicit_missing_flags_pct"] = round(
        100 * explicit_missing_count / explicit_missing_denominator, 3
    ) if explicit_missing_denominator else 0.0
    return result


def required_runtime_paths(root: Path) -> tuple[list[Path], list[str]]:
    resolved = [root / path for path in RUNTIME_LOG_PATHS]
    missing = [repo_relative(path, root)
               for path in resolved if not path.exists()]
    return resolved, missing


def current_aurora_core_logs(root: Path) -> list[Path]:
    return sorted((root / "logs").glob("aurora_core.log*"))


def copy_with_manifest(
    root: Path,
    source: Path,
    destination_root: Path,
    evidence_role: str,
    notes: str,
) -> dict[str, Any]:
    relative_source = repo_relative(source, root)
    frozen_path = destination_root / relative_source
    entry = {
        "source_path": relative_source,
        "frozen_path": repo_relative(frozen_path, root),
        "file_exists": source.exists(),
        "size_bytes": None,
        "mtime": None,
        "sha256": None,
        "copied_successfully": False,
        "evidence_role": evidence_role,
        "notes": notes,
    }
    if source.exists() and source.is_file():
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, frozen_path)
        stat = source.stat()
        entry["size_bytes"] = stat.st_size
        entry["mtime"] = datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc).isoformat()
        entry["sha256"] = sha256_file(frozen_path)
        entry["copied_successfully"] = True
    else:
        entry["notes"] = notes or "source_missing_or_not_file"
    return entry


def create_extension_freeze(
    root: Path,
    runtime_rows: list[dict[str, Any]],
    scan_context: dict[str, Any],
) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    tag = local_now().strftime("%Y%m%d_%H%M%S")
    extension_root = root / "logs" / "frozen" / f"{EXTENSION_PREFIX}{tag}"
    extension_root.mkdir(parents=True, exist_ok=False)

    runtime_paths, _ = required_runtime_paths(root)
    copy_entries: list[dict[str, Any]] = []
    for path in runtime_paths:
        copy_entries.append(
            copy_with_manifest(
                root,
                path,
                extension_root,
                "primary_runtime_log",
                "prompt20_extension_runtime_snapshot",
            )
        )

    for path in current_aurora_core_logs(root):
        copy_entries.append(
            copy_with_manifest(
                root,
                path,
                extension_root,
                "primary_runtime_log",
                "prompt20_extension_runtime_snapshot",
            )
        )

    recorder_dates = recorder_dates_for_rows(runtime_rows)
    symbols = sorted({str(row.get("symbol")).upper()
                     for row in runtime_rows if row.get("symbol")})
    for date_str in sorted(recorder_dates):
        day_dir = root / "data" / "recorder" / date_str
        if not day_dir.exists():
            continue
        for csv_path in sorted(day_dir.glob("*.csv")):
            copy_entries.append(
                copy_with_manifest(
                    root,
                    csv_path,
                    extension_root,
                    "recorder_market_data",
                    "relevant_prompt20_recorder_surface",
                )
            )

    for reference_path, note in (
        (root / BASE_REPORT_PATH, "prompt19_reference_report"),
        (root / BASE_SUMMARY_PATH, "prompt19_reference_summary"),
    ):
        copy_entries.append(
            copy_with_manifest(
                root,
                reference_path,
                extension_root,
                "reference_report",
                note,
            )
        )

    manifest = {
        "created_at_local": local_now().isoformat(),
        "created_at_utc": utc_now().isoformat(),
        "freeze_root": repo_relative(extension_root, root),
        "base_freeze_root": BASE_FREEZE_PATH.as_posix(),
        "prompt19_window_end_ts": PROMPT19_END_TS_MS,
        "probe": scan_context["probe"],
        "relevant_recorder_dates": sorted(recorder_dates),
        "symbols": symbols,
        "entry_count": len(copy_entries),
        "entries": copy_entries,
    }
    write_json(extension_root / "MANIFEST.json", manifest)
    return extension_root, manifest, copy_entries


def build_rid_line_index(path: Path) -> dict[str, int]:
    index: dict[str, int] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if '"rid"' not in line:
                continue
            payload = safe_json(line)
            if payload is None:
                continue
            rid = payload.get("rid")
            if isinstance(rid, str) and rid not in index:
                index[rid] = line_no
    return index


def build_extension_dataset(root: Path, extension_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frozen_order_log = extension_root / "logs" / "order_log_v1.jsonl"
    rows: list[dict[str, Any]] = []
    all_rows, malformed = load_jsonl(frozen_order_log)
    candidate_rows = [row for row in all_rows if detect_timestamp_ms(
        row) and detect_timestamp_ms(row) > PROMPT19_END_TS_MS]
    symbols = {str(row.get("symbol")).upper()
               for row in candidate_rows if row.get("symbol")}
    dates = recorder_dates_for_rows(
        [{"ts_ms": detect_timestamp_ms(
            row)} for row in candidate_rows if detect_timestamp_ms(row) is not None]
    )
    recorder_index = build_workspace_recorder_index(
        extension_root, dates, symbols)

    shadow_index = build_rid_line_index(
        extension_root / "logs" / "shadow_critical_event_journal_v1.jsonl")
    regime_index = build_rid_line_index(
        extension_root / "logs" / "regime_confidence_audit_v1.jsonl")
    trade_index = build_rid_line_index(
        extension_root / "logs" / "trade_lifecycle.jsonl")

    for line_no, row in enumerate(all_rows, start=1):
        extracted = relevant_row_from_runtime(
            row,
            line_no,
            repo_relative(frozen_order_log, root),
            recorder_index,
        )
        if extracted is None:
            continue
        rid = extracted.get("rid")
        if isinstance(rid, str):
            extracted["evidence_refs"]["shadow_line"] = shadow_index.get(rid)
            extracted["evidence_refs"]["regime_audit_line"] = regime_index.get(
                rid)
            extracted["evidence_refs"]["trade_lifecycle_line"] = trade_index.get(
                rid)
        rows.append(extracted)

    dataset_path = extension_root / "nrr062_cases_PROMPT20_EXTENSION.jsonl"
    write_jsonl(dataset_path, rows)
    return rows, {
        "dataset_path": repo_relative(dataset_path, root),
        "malformed_rows": malformed,
        "recorder_index": recorder_index,
        "shadow_index_size": len(shadow_index),
        "regime_index_size": len(regime_index),
        "trade_index_size": len(trade_index),
    }


def base_row_recorder_replay_ready(row: dict[str, Any]) -> dict[str, bool]:
    payload = row.get("recorder_replay_ready")
    if isinstance(payload, dict):
        if "15m" in payload:
            return {
                "15m": bool(payload.get("15m")),
                "30m": bool(payload.get("30m")),
                "60m": bool(payload.get("60m")),
                "120m": bool(payload.get("120m")),
            }
        return {
            "15m": bool(payload.get("has_forward_data_15m")),
            "30m": bool(payload.get("has_forward_data_30m")),
            "60m": bool(payload.get("has_forward_data_60m")),
            "120m": bool(payload.get("has_forward_data_120m")),
        }
    return {"15m": False, "30m": False, "60m": False, "120m": False}


def normalize_base_row_for_merge(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    merged["recorder_replay_ready"] = base_row_recorder_replay_ready(row)
    merged["identity"] = {
        "rid": row.get("rid"),
        "lifecycle_id": row.get("lifecycle_id"),
    }
    merged["source_freeze_path"] = BASE_FREEZE_PATH.as_posix()
    merged["source_dataset_path"] = BASE_CASES_PATH.as_posix()
    return merged


def dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("rid"),
        as_int(row.get("ts_ms")),
        row.get("symbol"),
        row.get("side"),
    )


def merge_rows(
    base_rows: list[dict[str, Any]],
    extension_rows: list[dict[str, Any]],
    extension_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    duplicates_removed = 0

    for row in base_rows:
        normalized = normalize_base_row_for_merge(row)
        key = dedupe_key(normalized)
        if key in seen:
            duplicates_removed += 1
            continue
        seen.add(key)
        merged_rows.append(normalized)

    for row in extension_rows:
        normalized = dict(row)
        normalized["source_freeze_path"] = repo_relative(
            extension_root, extension_root.parent.parent.parent)
        normalized["source_dataset_path"] = repo_relative(
            extension_root / "nrr062_cases_PROMPT20_EXTENSION.jsonl",
            extension_root.parent.parent.parent,
        )
        key = dedupe_key(normalized)
        if key in seen:
            duplicates_removed += 1
            continue
        seen.add(key)
        merged_rows.append(normalized)

    symbols = sorted({str(row.get("symbol"))
                     for row in merged_rows if row.get("symbol")})
    strategies = sorted({str(row.get("strategy_id"))
                        for row in merged_rows if row.get("strategy_id")})
    summary = {
        "base_rows": len(base_rows),
        "extension_rows": len(extension_rows),
        "duplicates_removed": duplicates_removed,
        "merged_total_rows": len(merged_rows),
        "merged_nrr062_denies": sum(
            1
            for row in merged_rows
            if row.get("final_gate_verdict", {}).get("denied") and row.get("nrr_code") == "NRR-062"
        ),
        "merged_low_vol_allows": sum(
            1 for row in merged_rows if row.get("final_gate_verdict", {}).get("allowed")
        ),
        "symbols": symbols,
        "strategies": strategies,
    }
    return merged_rows, summary


def write_merged_dataset(root: Path, extension_root: Path, merged_rows: list[dict[str, Any]]) -> str:
    merged_path = extension_root / "nrr062_merged_cases_PROMPT20.jsonl"
    write_jsonl(merged_path, merged_rows)
    return repo_relative(merged_path, root)


def merged_recorder_coverage(
    merged_rows: list[dict[str, Any]],
    extension_root: Path,
    root: Path,
) -> dict[str, Any]:
    base_recorder_dates = recorder_dates_for_rows(
        base_rows_as_ts_only(merged_rows, BASE_FREEZE_PATH.as_posix()))
    extension_recorder_dates = recorder_dates_for_rows(
        base_rows_as_ts_only(merged_rows, repo_relative(extension_root, root)))

    base_index = build_workspace_recorder_index(
        root / BASE_FREEZE_PATH, base_recorder_dates, None)
    ext_index = build_workspace_recorder_index(
        extension_root, extension_recorder_dates, None)
    # build_workspace_recorder_index expects root with data/recorder. The freeze roots already contain data/recorder.
    # Rebuild using freeze-local helper for correctness.
    base_index = build_freeze_recorder_index(
        root / BASE_FREEZE_PATH, base_recorder_dates)
    ext_index = build_freeze_recorder_index(
        extension_root, extension_recorder_dates)

    total_cases = len(merged_rows)
    counts = {15: 0, 30: 0, 60: 0, 120: 0}
    missing_symbol_recorder = 0
    late_window_pending_horizon = 0
    insufficient_forward_data = 0
    best_timeframe_per_symbol: dict[str, int] = {}

    extension_recorder_max = aggregated_recorder_max(ext_index)
    base_recorder_max = aggregated_recorder_max(base_index)

    for row in merged_rows:
        source_freeze_path = row.get("source_freeze_path")
        active_index = base_index if source_freeze_path == BASE_FREEZE_PATH.as_posix() else ext_index
        coverage = row_timeframe_coverage(row, active_index)
        row["recorder_replay_ready"] = {
            "15m": coverage["15m"],
            "30m": coverage["30m"],
            "60m": coverage["60m"],
            "120m": coverage["120m"],
        }
        row["recorder_meta"] = {
            "has_symbol_recorder": coverage["has_symbol_recorder"],
            "best_timeframe_sec": coverage["best_timeframe_sec"],
            "latest_available_ts_ms": coverage["latest_available_ts_ms"],
        }

        for minutes in REPLAY_HORIZONS:
            if coverage[f"{minutes}m"] if isinstance(coverage.get(f"{minutes}m"), bool) else coverage[str(minutes)]:
                counts[minutes] += 1

        symbol = str(row.get("symbol") or "").upper()
        if coverage["best_timeframe_sec"] is not None and symbol:
            current_best = best_timeframe_per_symbol.get(symbol)
            if current_best is None or coverage["best_timeframe_sec"] < current_best:
                best_timeframe_per_symbol[symbol] = coverage["best_timeframe_sec"]

        if not coverage["has_symbol_recorder"]:
            missing_symbol_recorder += 1
            continue

        if not coverage["120m"]:
            ts_ms = as_int(row.get("ts_ms"))
            recorder_max_ts = coverage["latest_available_ts_ms"]
            if ts_ms is not None and recorder_max_ts is not None and recorder_max_ts < ts_ms + REPLAY_HORIZON_MS:
                if (
                    row.get("source_freeze_path") != BASE_FREEZE_PATH.as_posix()
                    and recorder_max_ts >= ts_ms
                ):
                    late_window_pending_horizon += 1
                else:
                    insufficient_forward_data += 1
            else:
                insufficient_forward_data += 1

    return {
        "total_cases": total_cases,
        "replay_ready_15m": counts[15],
        "replay_ready_30m": counts[30],
        "replay_ready_60m": counts[60],
        "replay_ready_120m": counts[120],
        "replay_ready_120m_pct": round(100 * counts[120] / total_cases, 3) if total_cases else 0.0,
        "insufficient_forward_data": insufficient_forward_data,
        "missing_symbol_recorder": missing_symbol_recorder,
        "late_window_pending_horizon": late_window_pending_horizon,
        "best_timeframe_per_symbol": best_timeframe_per_symbol,
        "base_recorder_max_ts_by_symbol": base_recorder_max,
        "extension_recorder_max_ts_by_symbol": extension_recorder_max,
    }


def base_rows_as_ts_only(rows: list[dict[str, Any]], source_freeze_path: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if row.get("source_freeze_path") != source_freeze_path:
            continue
        ts_ms = as_int(row.get("ts_ms"))
        if ts_ms is not None:
            result.append({"ts_ms": ts_ms})
    return result


def build_freeze_recorder_index(freeze_root: Path, dates: set[str]) -> dict[str, dict[int, list[RecorderFileInfo]]]:
    by_symbol: dict[str, dict[int, list[RecorderFileInfo]]
                    ] = defaultdict(lambda: defaultdict(list))
    recorder_root = freeze_root / "data" / "recorder"
    if not recorder_root.exists():
        return {}
    for date_str in sorted(dates):
        day_dir = recorder_root / date_str
        if not day_dir.exists():
            continue
        for csv_path in sorted(day_dir.glob("*.csv")):
            info = scan_recorder_file(csv_path)
            if info is None:
                continue
            by_symbol[info.symbol][info.tf_sec].append(info)
    return by_symbol


def replay_bars_for_row(
    row: dict[str, Any],
    recorder_index: dict[str, dict[int, list[RecorderFileInfo]]],
) -> tuple[list[dict[str, Any]], int | None, str | None]:
    symbol = str(row.get("symbol") or "").upper()
    ts_ms = as_int(row.get("ts_ms"))
    if not symbol or ts_ms is None:
        return [], None, None
    tf_map = recorder_index.get(symbol, {})
    chosen_tf: int | None = None
    chosen_files: list[RecorderFileInfo] = []
    for tf_sec in REPLAY_FINEST_TFS:
        files = tf_map.get(tf_sec, [])
        max_ts = max((file.max_ts_ms or -1) for file in files) if files else -1
        min_ts = min((file.min_ts_ms or sys.maxsize)
                     for file in files) if files else sys.maxsize
        if files and min_ts <= ts_ms and max_ts >= ts_ms + REPLAY_HORIZON_MS:
            chosen_tf = tf_sec
            chosen_files = sorted(files, key=lambda item: item.path.as_posix())
            break
    if chosen_tf is None:
        return [], None, None

    bars: list[dict[str, Any]] = []
    for file_info in chosen_files:
        with file_info.path.open("r", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                bar_ts = as_int(raw.get("timestamp") or raw.get("open_time"))
                if bar_ts is None or bar_ts <= ts_ms:
                    continue
                bars.append(
                    {
                        "ts_ms": bar_ts,
                        "open": as_float(raw.get("open")),
                        "high": as_float(raw.get("high")),
                        "low": as_float(raw.get("low")),
                        "close": as_float(raw.get("close")),
                        "path": file_info.path.as_posix(),
                    }
                )
    bars.sort(key=lambda item: item["ts_ms"])
    return bars, chosen_tf, chosen_files[0].path.as_posix() if chosen_files else None


def close_at_horizon(bars: list[dict[str, Any]], target_ts_ms: int) -> float | None:
    for bar in bars:
        if bar["ts_ms"] >= target_ts_ms:
            return as_float(bar.get("close"))
    return None


def replay_row(
    row: dict[str, Any],
    recorder_index: dict[str, dict[int, list[RecorderFileInfo]]],
) -> dict[str, Any]:
    ts_ms = as_int(row.get("ts_ms"))
    side = row.get("side")
    geometry = get_nested(row, "low_vol_cost_floor", "geometry")
    if ts_ms is None or side not in {"BUY", "SELL"} or not isinstance(geometry, dict):
        return {
            "rid": row.get("rid"),
            "ts_ms": ts_ms,
            "symbol": row.get("symbol"),
            "side": side,
            "classification": "ambiguous",
            "path_outcome": "TIMESTAMP_FAILURE",
            "AMBIGUOUS_SAME_BAR": False,
            "INSUFFICIENT_FORWARD_DATA": False,
            "TP_FIRST": False,
            "SL_FIRST": False,
            "HORIZON_CLOSE_120M": False,
            "notes": "timestamp_or_side_invalid",
        }

    entry_price = as_float(geometry.get("entry_price"))
    target_price = as_float(geometry.get("target_price"))
    stop_price = as_float(geometry.get("stop_price"))
    if entry_price is None or target_price is None or stop_price is None:
        return {
            "rid": row.get("rid"),
            "ts_ms": ts_ms,
            "symbol": row.get("symbol"),
            "side": side,
            "classification": "ambiguous",
            "path_outcome": "TIMESTAMP_FAILURE",
            "AMBIGUOUS_SAME_BAR": False,
            "INSUFFICIENT_FORWARD_DATA": False,
            "TP_FIRST": False,
            "SL_FIRST": False,
            "HORIZON_CLOSE_120M": False,
            "notes": "geometry_missing",
        }

    bars, timeframe_sec, recorder_path = replay_bars_for_row(
        row, recorder_index)
    if not bars:
        return {
            "rid": row.get("rid"),
            "ts_ms": ts_ms,
            "symbol": row.get("symbol"),
            "side": side,
            "classification": "ambiguous",
            "path_outcome": "INSUFFICIENT_FORWARD_DATA",
            "AMBIGUOUS_SAME_BAR": False,
            "INSUFFICIENT_FORWARD_DATA": True,
            "TP_FIRST": False,
            "SL_FIRST": False,
            "HORIZON_CLOSE_120M": False,
            "notes": "no_recorder_path_covering_120m",
        }

    total_cost_bps = total_cost_bps_for_row(row)
    horizon_end_ts = ts_ms + REPLAY_HORIZON_MS
    bars_to_horizon = [bar for bar in bars if bar["ts_ms"] <= horizon_end_ts]
    if not bars_to_horizon:
        return {
            "rid": row.get("rid"),
            "ts_ms": ts_ms,
            "symbol": row.get("symbol"),
            "side": side,
            "classification": "ambiguous",
            "path_outcome": "INSUFFICIENT_FORWARD_DATA",
            "AMBIGUOUS_SAME_BAR": False,
            "INSUFFICIENT_FORWARD_DATA": True,
            "TP_FIRST": False,
            "SL_FIRST": False,
            "HORIZON_CLOSE_120M": False,
            "notes": "no_bars_before_horizon",
        }

    high_after_entry = max(as_float(bar.get("high"))
                           or entry_price for bar in bars_to_horizon)
    low_after_entry = min(as_float(bar.get("low"))
                          or entry_price for bar in bars_to_horizon)
    close_15m = close_at_horizon(bars, ts_ms + 15 * 60 * 1000)
    close_30m = close_at_horizon(bars, ts_ms + 30 * 60 * 1000)
    close_60m = close_at_horizon(bars, ts_ms + 60 * 60 * 1000)
    close_120m = close_at_horizon(bars, horizon_end_ts)

    if side == "BUY":
        mfe_bps = max(((as_float(bar.get("high")) or entry_price) -
                      entry_price) / entry_price * 10000 for bar in bars_to_horizon)
        mae_bps = max((entry_price - (as_float(bar.get("low")) or entry_price)
                       ) / entry_price * 10000 for bar in bars_to_horizon)
    else:
        mfe_bps = max((entry_price - (as_float(bar.get("low")) or entry_price)
                       ) / entry_price * 10000 for bar in bars_to_horizon)
        mae_bps = max(((as_float(bar.get("high")) or entry_price) -
                      entry_price) / entry_price * 10000 for bar in bars_to_horizon)

    outcome = "HORIZON_CLOSE_120M"
    classification = "ambiguous"
    ambiguous_same_bar = False
    tp_first = False
    sl_first = False
    insufficient_forward = False
    net_bps: float | None = None

    for bar in bars_to_horizon:
        high = as_float(bar.get("high"))
        low = as_float(bar.get("low"))
        if high is None or low is None:
            continue
        if side == "BUY":
            tp_hit = high >= target_price
            sl_hit = low <= stop_price
        else:
            tp_hit = low <= target_price
            sl_hit = high >= stop_price

        if tp_hit and sl_hit:
            outcome = "AMBIGUOUS_SAME_BAR"
            classification = "ambiguous"
            ambiguous_same_bar = True
            break
        if tp_hit:
            tp_first = True
            outcome = "TP_FIRST"
            classification = "missed_positive"
            actual_tp_bps = abs(target_price - entry_price) / \
                entry_price * 10000
            net_bps = actual_tp_bps - total_cost_bps
            break
        if sl_hit:
            sl_first = True
            outcome = "SL_FIRST"
            classification = "correct_block"
            actual_sl_bps = abs(stop_price - entry_price) / entry_price * 10000
            net_bps = -(actual_sl_bps + total_cost_bps)
            break

    if outcome == "HORIZON_CLOSE_120M":
        if close_120m is None:
            outcome = "INSUFFICIENT_FORWARD_DATA"
            insufficient_forward = True
            classification = "ambiguous"
        else:
            if side == "BUY":
                gross_bps = (close_120m - entry_price) / entry_price * 10000
            else:
                gross_bps = (entry_price - close_120m) / entry_price * 10000
            net_bps = gross_bps - total_cost_bps
            classification = "missed_positive" if net_bps > 0 else "correct_block"

    return {
        "rid": row.get("rid"),
        "ts_ms": ts_ms,
        "ts_iso": iso_from_ts_ms(ts_ms),
        "symbol": row.get("symbol"),
        "side": side,
        "source_freeze_path": row.get("source_freeze_path"),
        "source_line": row.get("source_line"),
        "chosen_timeframe_sec": timeframe_sec,
        "recorder_path": recorder_path,
        "first_bar_after_signal": iso_from_ts_ms(bars[0]["ts_ms"]) if bars else None,
        "high_after_entry": high_after_entry,
        "low_after_entry": low_after_entry,
        "close_15m": close_15m,
        "close_30m": close_30m,
        "close_60m": close_60m,
        "close_120m": close_120m,
        "MFE_bps": round(mfe_bps, 6),
        "MAE_bps": round(mae_bps, 6),
        "TP_FIRST": tp_first,
        "SL_FIRST": sl_first,
        "HORIZON_CLOSE_120M": outcome == "HORIZON_CLOSE_120M",
        "AMBIGUOUS_SAME_BAR": ambiguous_same_bar,
        "INSUFFICIENT_FORWARD_DATA": insufficient_forward,
        "path_outcome": outcome,
        "classification": classification,
        "net_bps": round(net_bps, 6) if net_bps is not None else None,
    }


def replay_merged_rows(root: Path, extension_root: Path, merged_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_index = build_freeze_recorder_index(root / BASE_FREEZE_PATH, recorder_dates_for_rows(
        base_rows_as_ts_only(merged_rows, BASE_FREEZE_PATH.as_posix())))
    ext_index = build_freeze_recorder_index(extension_root, recorder_dates_for_rows(
        base_rows_as_ts_only(merged_rows, repo_relative(extension_root, root))))
    replay_rows: list[dict[str, Any]] = []
    for row in merged_rows:
        if not row.get("recorder_replay_ready", {}).get("120m"):
            continue
        active_index = base_index if row.get(
            "source_freeze_path") == BASE_FREEZE_PATH.as_posix() else ext_index
        replay_rows.append(replay_row(row, active_index))

    summary = {
        "replayable_cases": len(replay_rows),
        "missed_positive": sum(1 for row in replay_rows if row.get("classification") == "missed_positive"),
        "correct_blocks": sum(1 for row in replay_rows if row.get("classification") == "correct_block"),
        "ambiguous": sum(1 for row in replay_rows if row.get("classification") == "ambiguous"),
        "path_outcomes": dict(Counter(str(row.get("path_outcome")) for row in replay_rows)),
    }
    return replay_rows, summary


def replay_gate_failures(merged_summary: dict[str, Any], field_coverage: dict[str, Any], recorder_coverage: dict[str, Any], mixed_rows_detected: bool) -> list[str]:
    failures: list[str] = []
    if merged_summary["merged_nrr062_denies"] < 200:
        failures.append(
            f"merged_nrr062_denies<{200}:{merged_summary['merged_nrr062_denies']}")
    if recorder_coverage["replay_ready_120m_pct"] < 90:
        failures.append(
            f"replay_ready_120m_pct<90:{recorder_coverage['replay_ready_120m_pct']}")
    if field_coverage["ret_60s_non_null_pct"] < 95:
        failures.append(
            f"ret_60s_non_null_pct<95:{field_coverage['ret_60s_non_null_pct']}")
    if field_coverage["ret_300s_non_null_pct"] < 95:
        failures.append(
            f"ret_300s_non_null_pct<95:{field_coverage['ret_300s_non_null_pct']}")
    for field in ("spread_bps_non_null_pct", "liquidity_kappa_non_null_pct", "absorption_non_null_pct"):
        if field_coverage[field] < 95:
            failures.append(f"{field}<95:{field_coverage[field]}")
    if field_coverage["geometry_economics_complete_pct"] < 95:
        failures.append(
            f"geometry_economics_complete_pct<95:{field_coverage['geometry_economics_complete_pct']}"
        )
    if mixed_rows_detected:
        failures.append("mixed_pre_prompt18_rows_detected")
    return failures


def mixed_pre_post_rows_detected(merged_rows: list[dict[str, Any]]) -> bool:
    return any(as_int(row.get("ts_ms")) is not None and as_int(row.get("ts_ms")) < PATCH_ANCHOR_TS_MS for row in merged_rows)


def choose_final_verdict(
    base_errors: list[str],
    probe: dict[str, Any],
    horizon_complete: bool,
    recorder_coverage: dict[str, Any] | None,
    replay_failures: list[str] | None,
    replay_summary: dict[str, Any] | None,
    replay_run: bool,
    mixed_rows_detected: bool,
) -> str:
    if base_errors:
        return VERDICT_BLOCKED_EXISTING_FREEZE_INVALID
    if mixed_rows_detected:
        return VERDICT_BLOCKED_MIXED_PRE_POST_PATCH_ROWS
    if probe["new_low_vol_cost_floor_rows"] == 0:
        return VERDICT_NEEDS_MORE_RUNTIME
    if not horizon_complete:
        return VERDICT_BLOCKED_RECORDER_HORIZON_PENDING
    if replay_failures:
        if recorder_coverage and recorder_coverage["replay_ready_120m_pct"] < 90:
            return VERDICT_BLOCKED_RECORDER_COVERAGE
        return VERDICT_EXTENSION_FROZEN_REPLAY_NOT_READY
    if replay_run and replay_summary is not None:
        return VERDICT_REPLAY_COMPLETED_READY_FOR_PROMPT21_SWEEP
    return VERDICT_EXTENSION_FROZEN_READY_FOR_REPLAY


def facts_section(
    base_errors: list[str],
    probe: dict[str, Any],
    horizon: dict[str, Any],
    merged_summary: dict[str, Any] | None,
    field_coverage: dict[str, Any] | None,
    recorder_coverage: dict[str, Any] | None,
    replay_summary: dict[str, Any] | None,
) -> list[str]:
    facts: list[str] = []
    if not base_errors:
        facts.append(
            "Base Prompt-19 freeze artifacts exist and validated against manifest, summary, and row-level count.")
    facts.append(
        f"Post-Prompt-19 probe found {probe['new_nrr062_denies']} new NRR-062 denies and {probe['new_low_vol_allows']} low_vol allow rows."
    )
    if horizon.get("latest_case_ts") is not None:
        facts.append(
            f"Latest captured case ts is {horizon['latest_case_ts']} with required 120m horizon ending at {horizon['required_horizon_end']}."
        )
    if merged_summary is not None:
        facts.append(
            f"Merged dataset totals {merged_summary['merged_total_rows']} rows with {merged_summary['merged_nrr062_denies']} denies and {merged_summary['merged_low_vol_allows']} allows."
        )
    if field_coverage is not None:
        facts.append(
            f"Merged field coverage: ret_60s={field_coverage['ret_60s_non_null_pct']}%, ret_300s={field_coverage['ret_300s_non_null_pct']}%, spread_bps={field_coverage['spread_bps_non_null_pct']}%."
        )
    if recorder_coverage is not None:
        facts.append(
            f"Merged recorder 120m readiness is {recorder_coverage['replay_ready_120m_pct']}% across {recorder_coverage['total_cases']} rows."
        )
    if replay_summary is not None:
        facts.append(
            f"Corrected replay processed {replay_summary['replayable_cases']} rows: missed_positive={replay_summary['missed_positive']}, correct_blocks={replay_summary['correct_blocks']}, ambiguous={replay_summary['ambiguous']}."
        )
    return facts


def inferences_section(
    probe: dict[str, Any],
    horizon_complete: bool,
    replay_failures: list[str],
    replay_ready_for_prompt21: bool,
) -> list[str]:
    inferences: list[str] = []
    if probe["new_low_vol_cost_floor_rows"] > 0:
        inferences.append(
            "The post-Prompt-19 cohort has extended beyond the Prompt-19 frozen boundary on authoritative and override-retained surfaces.")
    if not horizon_complete:
        inferences.append(
            "Late rows are pending recorder horizon completion rather than ambiguous by evidence loss.")
    if replay_failures:
        inferences.append(
            "Replay readiness remains gated by explicit coverage thresholds rather than by missing NRR-062 signal surfaces.")
    if replay_ready_for_prompt21:
        inferences.append(
            "Replay gates and replay diversity gates are satisfied, so Prompt-21 variant sweep can be recommended without changing live policy.")
    return inferences


def assumptions_section() -> list[str]:
    return [
        "Recorder CSV timestamp is treated as bar-close/open_time-equivalent and bars are evaluated in timestamp order.",
        "Same-bar TP/SL dual touches remain ambiguous because retained recorder bars do not preserve intrabar order.",
        "For allow rows, NRR-062 membership is inferred only when the retained low_vol payload explicitly marks nrr062_segment_override_applied or original_nrr062_reason.",
    ]


def unknowns_section(probe: dict[str, Any], replay_run: bool) -> list[str]:
    unknowns: list[str] = []
    if probe["new_low_vol_allows"] == 0:
        unknowns.append(
            "No new low_vol allow rows were present in the scanned post-Prompt-19 window.")
    if not replay_run:
        unknowns.append(
            "Corrected path replay was skipped because replay readiness gates did not pass in this prompt.")
    unknowns.append(
        "Shadow same-RID fragments remain a secondary corroboration surface and not the authoritative numeric ret source.")
    return unknowns


def markdown_bullets(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def format_json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def build_report(
    verdict: str,
    base_errors: list[str],
    probe: dict[str, Any],
    horizon: dict[str, Any],
    extension_root: Path | None,
    extension_manifest_path: str | None,
    extension_dataset_path: str | None,
    merged_dataset_path: str | None,
    merged_summary: dict[str, Any] | None,
    field_coverage: dict[str, Any] | None,
    recorder_coverage: dict[str, Any] | None,
    replay_failures: list[str],
    replay_results_path: str | None,
    replay_summary_path: str | None,
    replay_summary: dict[str, Any] | None,
    replay_run: bool,
    ready_for_prompt21_variant_sweep: bool,
    validation: dict[str, Any],
) -> str:
    facts = facts_section(
        base_errors,
        probe,
        horizon,
        merged_summary,
        field_coverage,
        recorder_coverage,
        replay_summary,
    )
    inferences = inferences_section(
        probe,
        bool(horizon.get("horizon_complete")),
        replay_failures,
        ready_for_prompt21_variant_sweep,
    )
    assumptions = assumptions_section()
    unknowns = unknowns_section(probe, replay_run)

    next_prompt = choose_next_prompt(
        verdict,
        ready_for_prompt21_variant_sweep,
        recorder_coverage,
        replay_failures,
        merged_summary,
    )

    sections = [
        "# NRR-062 POST-PROMPT18 COLLECTION EXTENSION — PROMPT 20",
        "",
        "## Verdict",
        verdict,
        "",
        "## Problem Framing",
        "Extend the post-Prompt-18 frozen NRR-062 cohort using only retained runtime evidence, freeze raw artifacts before derived analysis, and run corrected replay only if replay-readiness gates pass.",
        "",
        "## FACTS",
        markdown_bullets(facts),
        "",
        "## INFERENCES",
        markdown_bullets(inferences),
        "",
        "## ASSUMPTIONS",
        markdown_bullets(assumptions),
        "",
        "## UNKNOWNS",
        markdown_bullets(unknowns),
        "",
        "## Existing Prompt-19 Freeze Check",
        markdown_bullets(base_errors or ["MANIFEST.json present", "nrr062_cases_PROMPT19.jsonl present",
                         "nrr062_coverage_summary_PROMPT19.json present", "row count = 128", "ret_60s and ret_300s remain 100% non-null in frozen dataset"]),
        "",
        "## Current Runtime Probe",
        format_json_block(probe),
        "",
        "## Horizon Readiness",
        format_json_block(horizon),
        "",
        "## Extension Freeze",
        format_json_block(
            {
                "extension_freeze_path": repo_relative(extension_root, extension_root.parent.parent.parent) if extension_root else None,
                "extension_manifest_path": extension_manifest_path,
            }
        ),
        "",
        "## Extension Dataset",
        format_json_block({"extension_dataset_path": extension_dataset_path}),
        "",
        "## Merged Dataset",
        format_json_block(
            {
                "merged_dataset_path": merged_dataset_path,
                "merged_dataset_summary": merged_summary,
            }
        ),
        "",
        "## Field Coverage",
        format_json_block(field_coverage),
        "",
        "## Recorder Coverage",
        format_json_block(recorder_coverage),
        "",
        "## Corrected Path Replay",
        format_json_block(
            {
                "replay_run": replay_run,
                "replay_failures": replay_failures,
                "replay_results_path": replay_results_path,
                "replay_summary_path": replay_summary_path,
                "replay_summary": replay_summary,
            }
        ),
        "",
        "## Replay / Sweep Readiness",
        format_json_block(
            {
                "replay_failures": replay_failures,
                "ready_for_prompt21_variant_sweep": ready_for_prompt21_variant_sweep,
            }
        ),
        "",
        "## Runtime Behavior Impact",
        format_json_block(
            {
                "config_changed": False,
                "thresholds_changed": False,
                "live_behavior_changed": False,
                "order_behavior_changed": False,
                "nrr062_semantics_changed": False,
                "strategy_score_changed": False,
            }
        ),
        "",
        "## Risks / Residuals",
        markdown_bullets(residual_risks(
            verdict, replay_failures, probe, recorder_coverage)),
        "",
        "## Next Prompt Recommendation",
        next_prompt,
        "",
        "## Validation",
        format_json_block(validation),
        "",
    ]
    return "\n".join(sections)


def residual_risks(
    verdict: str,
    replay_failures: list[str],
    probe: dict[str, Any],
    recorder_coverage: dict[str, Any] | None,
) -> list[str]:
    risks: list[str] = []
    if probe["new_low_vol_cost_floor_rows"] == 0:
        risks.append(
            "No new retained post-Prompt-19 rows were available, so replay readiness cannot improve in this prompt.")
    if verdict == VERDICT_BLOCKED_RECORDER_HORIZON_PENDING:
        risks.append(
            "Latest captured rows are still within the unresolved 120m forward horizon window.")
    if replay_failures:
        risks.extend(
            f"Replay gate failed: {failure}" for failure in replay_failures)
    if recorder_coverage and recorder_coverage.get("missing_symbol_recorder"):
        risks.append(
            "Some rows lack symbol-level recorder coverage in the frozen evidence set.")
    risks.append(
        "Allow-surface results still depend on retained ORDER_INTENT observability rather than a dedicated shadow evaluator surface.")
    return risks


def choose_next_prompt(
    verdict: str,
    ready_for_prompt21_variant_sweep: bool,
    recorder_coverage: dict[str, Any] | None,
    replay_failures: list[str],
    merged_summary: dict[str, Any] | None,
) -> str:
    if ready_for_prompt21_variant_sweep:
        return "run Prompt-21 corrected variant sweep"
    if verdict == VERDICT_BLOCKED_RECORDER_HORIZON_PENDING:
        return "wait for 120m recorder horizon and rerun Prompt-20"
    if verdict == VERDICT_NEEDS_MORE_RUNTIME:
        return "continue runtime collection"
    if merged_summary and merged_summary.get("merged_nrr062_denies", 0) < 200:
        return "rerun Prompt-20 after more rows"
    if recorder_coverage and recorder_coverage.get("replay_ready_120m_pct", 0) < 90:
        return "fix recorder coverage"
    if replay_failures:
        return "rerun Prompt-20 after more rows"
    return "rerun Prompt-20 after more rows"


def main() -> int:
    root = Path.cwd().resolve()

    base_validation, base_rows, base_errors = load_base_validation(root)
    probe_rows, scan_context = scan_runtime_extension_rows(root)

    latest_case_ts = scan_context["latest_case_ts"]
    latest_case_symbol = scan_context["latest_case_symbol"]
    recorder_max_by_symbol = scan_context["recorder_max_by_symbol"]
    latest_symbol_max = recorder_max_by_symbol.get(
        latest_case_symbol) if latest_case_symbol else None
    horizon = {
        "latest_case_ts": latest_case_ts,
        "latest_case_ts_iso": iso_from_ts_ms(latest_case_ts),
        "required_horizon_end": latest_case_ts + REPLAY_HORIZON_MS if latest_case_ts is not None else None,
        "required_horizon_end_iso": iso_from_ts_ms(latest_case_ts + REPLAY_HORIZON_MS) if latest_case_ts is not None else None,
        "recorder_max_ts_by_symbol": recorder_max_by_symbol,
        "horizon_complete": (
            latest_case_ts is not None
            and latest_symbol_max is not None
            and latest_symbol_max >= latest_case_ts + REPLAY_HORIZON_MS
        ),
        "pending_duration_if_any": duration_string(
            latest_symbol_max,
            latest_case_ts + REPLAY_HORIZON_MS,
        ) if latest_case_ts is not None and latest_symbol_max is not None and latest_symbol_max < latest_case_ts + REPLAY_HORIZON_MS else None,
    }

    extension_root: Path | None = None
    extension_manifest: dict[str, Any] | None = None
    extension_entries: list[dict[str, Any]] = []
    extension_rows: list[dict[str, Any]] = []
    extension_dataset_info: dict[str, Any] | None = None
    merged_rows: list[dict[str, Any]] = []
    merged_summary: dict[str, Any] | None = None
    merged_dataset_path: str | None = None
    field_coverage: dict[str, Any] | None = None
    recorder_coverage: dict[str, Any] | None = None
    replay_failures: list[str] = []
    replay_rows: list[dict[str, Any]] = []
    replay_summary: dict[str, Any] | None = None
    replay_results_path: str | None = None
    replay_summary_path: str | None = None
    ready_for_prompt21_variant_sweep = False
    replay_run = False

    if not base_errors and probe_rows:
        extension_root, extension_manifest, extension_entries = create_extension_freeze(
            root,
            probe_rows,
            scan_context,
        )
        extension_rows, extension_dataset_info = build_extension_dataset(
            root, extension_root)
        merged_rows, merged_summary = merge_rows(
            base_rows, extension_rows, extension_root)
        merged_dataset_path = write_merged_dataset(
            root, extension_root, merged_rows)
        field_coverage = compute_field_coverage(merged_rows)
        recorder_coverage = merged_recorder_coverage(
            merged_rows, extension_root, root)
        mixed_rows = mixed_pre_post_rows_detected(merged_rows)
        replay_failures = replay_gate_failures(
            merged_summary,
            field_coverage,
            recorder_coverage,
            mixed_rows,
        )
        if not replay_failures and horizon["horizon_complete"]:
            replay_rows, replay_summary = replay_merged_rows(
                root, extension_root, merged_rows)
            replay_results_file = extension_root / \
                "nrr062_merged_recorder_path_replay_PROMPT20.jsonl"
            replay_summary_file = extension_root / \
                "nrr062_merged_recorder_path_replay_summary_PROMPT20.json"
            write_jsonl(replay_results_file, replay_rows)
            write_json(replay_summary_file, replay_summary)
            replay_results_path = repo_relative(replay_results_file, root)
            replay_summary_path = repo_relative(replay_summary_file, root)
            replay_run = True
            if replay_summary["missed_positive"] > 0 and replay_summary["correct_blocks"] > 0:
                timestamps = sorted(as_int(row.get("ts_ms")) for row in replay_rows if as_int(
                    row.get("ts_ms")) is not None)
                spread_ok = bool(
                    timestamps) and timestamps[-1] - timestamps[0] >= 6 * 60 * 60 * 1000
                ready_for_prompt21_variant_sweep = (
                    replay_summary["replayable_cases"] >= 200 and spread_ok
                )
        else:
            mixed_rows = mixed_pre_post_rows_detected(merged_rows)
    else:
        mixed_rows = False

    verdict = choose_final_verdict(
        base_errors,
        scan_context["probe"],
        bool(horizon["horizon_complete"]),
        recorder_coverage,
        replay_failures,
        replay_summary,
        replay_run,
        mixed_rows,
    )

    validation = {
        "commands_run": ["python tools/analysis/nrr062_collection_extension_PROMPT20.py"],
        "frozen_files_read": [
            BASE_MANIFEST_PATH.as_posix(),
            BASE_CASES_PATH.as_posix(),
            BASE_SUMMARY_PATH.as_posix(),
            BASE_REPORT_PATH.as_posix(),
            PROMPT18_REPORT_PATH.as_posix(),
        ],
        "files_copied": len(extension_entries),
        "manifest_checks": base_errors or ["manifest_present", "cases_present", "summary_present", "row_count_128", "ret_60s_ret_300s_100pct_non_null"],
        "rows_parsed": {
            "probe_rows": len(probe_rows),
            "extension_rows": len(extension_rows),
            "base_rows": len(base_rows),
            "merged_rows": len(merged_rows),
        },
        "duplicates_removed": merged_summary["duplicates_removed"] if merged_summary else 0,
        "counts_cross_checked": {
            "base_row_count": len(base_rows),
            "probe_new_nrr062_denies": scan_context["probe"]["new_nrr062_denies"],
            "probe_new_low_vol_allows": scan_context["probe"]["new_low_vol_allows"],
            "merged_nrr062_denies": merged_summary["merged_nrr062_denies"] if merged_summary else None,
            "merged_low_vol_allows": merged_summary["merged_low_vol_allows"] if merged_summary else None,
        },
        "replay_readiness_gates": replay_failures or ["passed"],
        "parsing_failures": {
            "base_errors": base_errors,
            "extension_order_log_malformed_rows": extension_dataset_info["malformed_rows"] if extension_dataset_info else 0,
            "probe_order_log_malformed_rows": scan_context["probe"]["order_log_malformed_rows"],
        },
        "assumptions_used": assumptions_section(),
    }

    report_text = build_report(
        verdict,
        base_errors,
        scan_context["probe"],
        horizon,
        extension_root,
        repo_relative(extension_root / "MANIFEST.json",
                      root) if extension_root else None,
        extension_dataset_info["dataset_path"] if extension_dataset_info else None,
        merged_dataset_path,
        merged_summary,
        field_coverage,
        recorder_coverage,
        replay_failures,
        replay_results_path,
        replay_summary_path,
        replay_summary,
        replay_run,
        ready_for_prompt21_variant_sweep,
        validation,
    )
    (root / OUTPUT_REPORT_PATH).write_text(report_text, encoding="utf-8")

    final_payload = {
        "AGENT_REPORT_V1": {
            "verdict": verdict,
            "report_path": OUTPUT_REPORT_PATH.as_posix(),
            "base_freeze_path": BASE_FREEZE_PATH.as_posix(),
            "extension_freeze_path": repo_relative(extension_root, root) if extension_root else None,
            "extension_manifest_path": repo_relative(extension_root / "MANIFEST.json", root) if extension_root else None,
            "extension_dataset_path": extension_dataset_info["dataset_path"] if extension_dataset_info else None,
            "merged_dataset_path": merged_dataset_path,
            "replay_results_path": replay_results_path,
            "replay_summary_path": replay_summary_path,
            "current_probe": {
                "new_nrr062_denies": scan_context["probe"]["new_nrr062_denies"],
                "new_low_vol_allows": scan_context["probe"]["new_low_vol_allows"],
            },
            "merged_counts": {
                "base_rows": merged_summary["base_rows"] if merged_summary else len(base_rows),
                "extension_rows": merged_summary["extension_rows"] if merged_summary else len(extension_rows),
                "duplicates_removed": merged_summary["duplicates_removed"] if merged_summary else 0,
                "merged_total_rows": merged_summary["merged_total_rows"] if merged_summary else len(merged_rows),
            },
            "field_coverage": {
                "ret_60s_non_null_pct": field_coverage["ret_60s_non_null_pct"] if field_coverage else None,
                "ret_300s_non_null_pct": field_coverage["ret_300s_non_null_pct"] if field_coverage else None,
                "pm_norm_60s_non_null_pct": field_coverage["pm_norm_60s_non_null_pct"] if field_coverage else None,
                "pm_norm_300s_non_null_pct": field_coverage["pm_norm_300s_non_null_pct"] if field_coverage else None,
                "vol_pct_300s_non_null_pct": field_coverage["vol_pct_300s_non_null_pct"] if field_coverage else None,
                "spread_bps_non_null_pct": field_coverage["spread_bps_non_null_pct"] if field_coverage else None,
                "liquidity_kappa_non_null_pct": field_coverage["liquidity_kappa_non_null_pct"] if field_coverage else None,
                "absorption_non_null_pct": field_coverage["absorption_non_null_pct"] if field_coverage else None,
            },
            "recorder_coverage": {
                "replay_ready_120m_pct": recorder_coverage["replay_ready_120m_pct"] if recorder_coverage else None,
                "insufficient_forward_data": recorder_coverage["insufficient_forward_data"] if recorder_coverage else None,
                "late_window_pending_horizon": recorder_coverage["late_window_pending_horizon"] if recorder_coverage else None,
            },
            "replay_run": replay_run,
            "replayable_cases": replay_summary["replayable_cases"] if replay_summary else 0,
            "missed_positive": replay_summary["missed_positive"] if replay_summary else 0,
            "correct_blocks": replay_summary["correct_blocks"] if replay_summary else 0,
            "ambiguous": replay_summary["ambiguous"] if replay_summary else 0,
            "ready_for_prompt21_variant_sweep": ready_for_prompt21_variant_sweep,
            "config_changed": False,
            "thresholds_changed": False,
            "live_behavior_changed": False,
            "order_behavior_changed": False,
            "nrr062_semantics_changed": False,
            "strategy_score_changed": False,
            "next_prompt": choose_next_prompt(
                verdict,
                ready_for_prompt21_variant_sweep,
                recorder_coverage,
                replay_failures,
                merged_summary,
            ),
            "residual_risks": residual_risks(verdict, replay_failures, scan_context["probe"], recorder_coverage),
        }
    }
    print(json.dumps(final_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
