#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


LOCAL_TZ_NAME = "Europe/Kiev"
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME) if ZoneInfo is not None else UTC
HORIZONS_MIN = [5, 10, 15, 20, 30]
DEFAULT_HOURS = 72
PRICE_NEAR_CANCEL_WINDOW_MS = 60_000
FEATURE_TARGET_MAX_LAG_MS = 120_000
BAR_TARGET_MAX_LAG_MS = 600_000
TIMEOUT_REASON = "CANCEL_TTL_EXPIRED"
UNKNOWN = "unknown"

TEXT_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
)
FILL_RE = re.compile(
    r"POLLING DETECTED FILL: (?P<order_id>\d+) \((?P<symbol>[A-Z0-9]+)\)"
)
TIMEOUT_RE = re.compile(
    r"Order timeout: (?P<order_id>\d+) \((?P<symbol>[A-Z0-9]+)\) - (?P<timeout_type>[^,]+)"
)
MAKER_REJECT_RE = re.compile(
    r"MAKER_ONLY_REJECT: GTX order rejected \(code=(?P<code>-?\d+)\), "
    r"symbol=(?P<symbol>[A-Z0-9]+), side=(?P<side>[A-Z]+)"
)
REGIME_CFG_RE = re.compile(r"basis_tf_sec=(?P<tf>\d+)")
REGIME_RE_ASCII = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] Regime updated: .*?(?:\u2192|->) (?P<regime>[A-Z_]+) "
    r"\(raw=(?P<raw>[^,]+), confidence=(?P<confidence>[^,]+), model=(?P<model>[^)]+)\)"
)
REGIME_RE = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] Regime updated: .* → (?P<regime>[A-Z_]+) "
    r"\(raw=(?P<raw>[^,]+), confidence=(?P<confidence>[^,]+), model=(?P<model>[^)]+)\)"
)
FEATURE_EMIT_RE = re.compile(
    r"on_bar_closed: emitting bar-features for (?P<symbol>[A-Z0-9]+) tf_sec=(?P<tf>\d+)"
)
FEATURE_RE = re.compile(
    r"Calculated features for (?P<symbol>[A-Z0-9]+): (?P<payload>\{.*\})"
)
ADV_ALL_GATES_RE = re.compile(
    r"\[ADV-CANCEL\] (?P<symbol>[A-Z0-9]+)/(?P<order_id>\d+): ALL GATES PASSED "
    r"\(regime=(?P<regime>[^,]+), age=(?P<age_ms>\d+)ms, drift=(?P<drift>[-0-9.]+)\)"
)
RID_SOURCE_RE = re.compile(r"^(?P<source>[a-zA-Z][a-zA-Z0-9_-]+)_[A-Z0-9]+_\d+")


@dataclass
class SourceStats:
    path: str
    fmt: str
    count: int = 0
    min_ts_ms: int | None = None
    max_ts_ms: int | None = None

    def update(self, ts_ms: int | None) -> None:
        if ts_ms is None:
            return
        self.count += 1
        self.min_ts_ms = ts_ms if self.min_ts_ms is None else min(self.min_ts_ms, ts_ms)
        self.max_ts_ms = ts_ms if self.max_ts_ms is None else max(self.max_ts_ms, ts_ms)


@dataclass
class OrderRecord:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    limit_price: float
    placed_at_ms: int
    placed_source_path: str
    rid: str | None
    source_fsm: str | None
    source_hint: str
    strategy_id: str | None
    tf_sec: int | None = None
    filled_at_ms: int | None = None
    canceled_at_ms: int | None = None
    cancel_reason: str | None = None
    cancel_reason_raw: str | None = None
    timeout_type: str | None = None
    cancel_context: str | None = None
    filled_source_path: str | None = None
    canceled_source_path: str | None = None
    price_at_cancel: float | None = None
    price_at_cancel_source: str | None = None
    atr_at_cancel: float | None = None
    regime_change_near_cancel: bool = False
    regime_change_near_cancel_count: int = 0
    regime_change_near_cancel_labels: list[str] = field(default_factory=list)
    adv_gate_logged: bool = False
    adv_gate_age_ms: int | None = None
    adv_gate_drift: float | None = None
    terminal_status: str = "OPEN"


@dataclass
class FeatureSample:
    ts_ms: int
    price: float
    tf_sec: int | None
    atr: float | None
    source: str


@dataclass
class BarSample:
    ts_ms: int
    close: float
    atr: float | None
    source: str


@dataclass
class RegimeEvent:
    ts_ms: int
    regime: str
    confidence: float | None
    raw: str
    model: str
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit pending entry cancels/fills and generate forensics artifacts."
    )
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--bars-file", default="logs/mean_reversion/bars_180s.jsonl")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--out-dir", default="reports/forensics")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    return parser.parse_args()


def rotated_log_files(logs_dir: Path, base_name: str) -> list[Path]:
    matches = []
    for path in logs_dir.glob(f"{base_name}*"):
        if not path.is_file():
            continue
        suffix = None
        extra = path.name[len(base_name) :]
        if extra.startswith(".") and extra[1:].isdigit():
            suffix = int(extra[1:])
        elif extra != "":
            continue
        matches.append((suffix, path))
    matches.sort(key=lambda item: (item[0] is None, -(item[0] or 0), item[1].name))
    return [path for _, path in matches]


def parse_text_ts_to_utc_ms(line: str) -> int | None:
    match = TEXT_TS_RE.match(line)
    if not match:
        return None
    ts = match.group("ts")
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=LOCAL_TZ)
    return int(dt.astimezone(UTC).timestamp() * 1000)


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def format_pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.2f}"


def format_num(value: float | None, digits: int = 2) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.{digits}f}"


def top_counts(counter: Counter[str], limit: int = 10) -> str:
    if not counter:
        return ""
    return "; ".join(f"{key}:{count}" for key, count in counter.most_common(limit))


def safe_median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def derive_source_hint(rid: str | None) -> str:
    if not rid:
        return UNKNOWN
    match = RID_SOURCE_RE.match(rid)
    if match:
        return match.group("source")
    return UNKNOWN


def normalize_cancel_reason(reason: str | None, timeout_type: str | None) -> str:
    if not reason:
        if timeout_type and timeout_type.lower() == "fill_timeout":
            return TIMEOUT_REASON
        return "CANCEL_UNKNOWN"
    if reason == "timeout_cancellation":
        if timeout_type and timeout_type.lower() == "fill_timeout":
            return TIMEOUT_REASON
        return f"CANCEL_TIMEOUT_{(timeout_type or UNKNOWN).upper()}"
    return reason


def reason_bucket(reason: str | None) -> str:
    if not reason:
        return "CANCEL_UNKNOWN"
    return reason


def median_age_sec(records: list[OrderRecord], attr: str) -> float | None:
    ages = []
    for record in records:
        ts_ms = getattr(record, attr)
        if ts_ms is None:
            continue
        ages.append((ts_ms - record.placed_at_ms) / 1000.0)
    return safe_median(ages)


def parse_env_mode(repo_root: Path) -> str | None:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return None
    for line in read_text(env_path).splitlines():
        if line.startswith("TRADING_MODE="):
            return line.split("=", 1)[1].strip() or None
    return None


def strip_inline_comment(value: str) -> str:
    if "#" in value:
        value = value.split("#", 1)[0]
    return value.strip()


def parse_inline_list(value: str) -> list[str]:
    value = strip_inline_comment(value)
    if not value.startswith("[") or not value.endswith("]"):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]


def extract_simple_yaml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        return None
    value = strip_inline_comment(match.group(1).strip())
    return value.strip("'\"")


def extract_ttl_map(text: str) -> dict[int, int]:
    lines = text.splitlines()
    ttl_map: dict[int, int] = {}
    inside = False
    base_indent = None
    for line in lines:
        if not inside:
            if re.match(r"^\s*ttl_by_tf_sec:\s*$", line):
                inside = True
                base_indent = len(line) - len(line.lstrip(" "))
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is not None and indent <= base_indent and line.strip():
            break
        match = re.match(r"^\s*(\d+):\s*(\d+)", line)
        if match:
            ttl_map[int(match.group(1))] = int(match.group(2))
    return ttl_map


def extract_list_block(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    values: list[str] = []
    inside = False
    base_indent = None
    for line in lines:
        clean_line = strip_inline_comment(line)
        if not inside:
            inline_match = re.match(rf"^\s*{re.escape(key)}:\s*(\[[^\]]*\])\s*$", clean_line)
            if inline_match:
                return parse_inline_list(inline_match.group(1))
            if re.match(rf"^\s*{re.escape(key)}:\s*$", clean_line):
                inside = True
                base_indent = len(line) - len(line.lstrip(" "))
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is not None and indent <= base_indent and line.strip():
            break
        match = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if match:
            values.append(match.group(1).strip().strip("'\""))
    return values


def extract_side_regimes(text: str) -> dict[str, list[str]]:
    lines = text.splitlines()
    inside = False
    may_indent = None
    result: dict[str, list[str]] = defaultdict(list)
    current_side = None
    current_indent = None
    for line in lines:
        clean_line = strip_inline_comment(line)
        if not inside:
            if re.match(r"^\s*may_cancel_regimes:\s*$", clean_line):
                inside = True
                may_indent = len(line) - len(line.lstrip(" "))
            continue
        indent = len(line) - len(line.lstrip(" "))
        if may_indent is not None and indent <= may_indent and line.strip():
            break
        inline_side_match = re.match(r"^\s*(BUY|SELL):\s*(\[[^\]]*\])\s*$", clean_line)
        if inline_side_match:
            result[inline_side_match.group(1)].extend(parse_inline_list(inline_side_match.group(2)))
            current_side = None
            current_indent = None
            continue
        side_match = re.match(r"^\s*(BUY|SELL):\s*$", clean_line)
        if side_match:
            current_side = side_match.group(1)
            current_indent = indent
            continue
        value_match = re.match(r"^\s*-\s*(.+?)\s*$", clean_line)
        if value_match and current_side is not None and indent > (current_indent or 0):
            result[current_side].append(value_match.group(1).strip().strip("'\""))
    return dict(result)


def compute_window(records: dict[str, OrderRecord], requested_hours: int) -> tuple[int, int, int]:
    relevant_ts = [record.placed_at_ms for record in records.values()]
    relevant_ts.extend(record.filled_at_ms for record in records.values() if record.filled_at_ms is not None)
    relevant_ts.extend(
        record.canceled_at_ms for record in records.values() if record.canceled_at_ms is not None
    )
    if not relevant_ts:
        now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        return now_ms - requested_hours * 3600 * 1000, now_ms, now_ms
    end_ms = max(relevant_ts)
    start_ms = end_ms - requested_hours * 3600 * 1000
    available_start_ms = min(relevant_ts)
    return max(start_ms, available_start_ms), end_ms, available_start_ms


def choose_terminal_status(record: OrderRecord) -> str:
    if record.filled_at_ms is not None and record.canceled_at_ms is not None:
        return "FILLED" if record.filled_at_ms <= record.canceled_at_ms else "CANCELED"
    if record.filled_at_ms is not None:
        return "FILLED"
    if record.canceled_at_ms is not None:
        return "CANCELED"
    return "OPEN"


def update_order_terminal_status(records: dict[str, OrderRecord]) -> None:
    for record in records.values():
        record.terminal_status = choose_terminal_status(record)


def first_after(series_ts: list[int], target_ts: int, max_lag_ms: int | None = None) -> int | None:
    idx = bisect_left(series_ts, target_ts)
    if idx >= len(series_ts):
        return None
    if max_lag_ms is not None and series_ts[idx] - target_ts > max_lag_ms:
        return None
    return idx


def nearest_in_window(series_ts: list[int], target_ts: int, window_ms: int) -> int | None:
    idx = bisect_left(series_ts, target_ts)
    candidates = []
    if idx < len(series_ts):
        candidates.append(idx)
    if idx > 0:
        candidates.append(idx - 1)
    best = None
    best_delta = None
    for cand in candidates:
        delta = abs(series_ts[cand] - target_ts)
        if delta <= window_ms and (best_delta is None or delta < best_delta):
            best = cand
            best_delta = delta
    return best


def closest_config_ttl(age_sec: float, ttl_map: dict[int, int]) -> tuple[int | None, float | None]:
    if not ttl_map:
        return None, None
    best_ttl = None
    best_delta = None
    for ttl_sec in ttl_map.values():
        delta = abs(age_sec - ttl_sec)
        if best_delta is None or delta < best_delta:
            best_ttl = ttl_sec
            best_delta = delta
    return best_ttl, best_delta


def favorable_move(record: OrderRecord, sample_price: float) -> float:
    if record.side == "BUY":
        return sample_price - record.limit_price
    return record.limit_price - sample_price


def favorable_bps(record: OrderRecord, sample_price: float) -> float:
    move = favorable_move(record, sample_price)
    return move / record.limit_price * 10_000.0


def distance_bps_to_limit(record: OrderRecord, price: float | None) -> float | None:
    if price is None:
        return None
    return abs(price - record.limit_price) / record.limit_price * 10_000.0


def parse_order_log(
    path: Path,
    source_stats: dict[str, SourceStats],
) -> tuple[dict[str, OrderRecord], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, OrderRecord] = {}
    by_client_id: dict[str, dict[str, Any]] = {}
    rejects: list[dict[str, Any]] = []
    stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="jsonl"))
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_ms = payload.get("timestamp")
            if isinstance(ts_ms, int):
                stats.update(ts_ms)
            event_type = payload.get("event_type")
            if event_type == "ORDER_PLACED":
                client_order_id = str(payload.get("client_order_id") or "")
                order_id = str(payload.get("order_id") or "")
                adapter = payload.get("adapter_response") or {}
                if not client_order_id.startswith("ENTRY-"):
                    continue
                if adapter.get("type") != "LIMIT":
                    continue
                if not order_id or "<MagicMock" in order_id:
                    continue
                symbol = str(payload.get("symbol") or "")
                if not symbol or "<MagicMock" in symbol:
                    continue
                limit_price = adapter.get("price")
                if limit_price in (None, "", "0", "0.0", "0.00", "0.0000", "0.000000"):
                    continue
                try:
                    limit_price_f = float(limit_price)
                except (TypeError, ValueError):
                    continue
                record = OrderRecord(
                    order_id=order_id,
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=str(payload.get("side") or ""),
                    order_type=str(adapter.get("type") or ""),
                    time_in_force=str(adapter.get("timeInForce") or ""),
                    limit_price=limit_price_f,
                    placed_at_ms=int(ts_ms),
                    placed_source_path=str(path),
                    rid=payload.get("rid"),
                    source_fsm=payload.get("source_fsm"),
                    source_hint=derive_source_hint(payload.get("rid")),
                    strategy_id=str(payload.get("strategy_id"))
                    if payload.get("strategy_id") is not None
                    else None,
                )
                records[order_id] = record
                by_client_id[client_order_id] = {"order_id": order_id}
            elif event_type == "ORDER_CANCELLED":
                if payload.get("bracket_type"):
                    continue
                order_id = str(payload.get("order_id") or "")
                if not order_id or order_id not in records:
                    continue
                record = records[order_id]
                timeout_type = payload.get("timeout_type")
                cancel_ts = int(payload.get("timestamp"))
                if record.canceled_at_ms is None or cancel_ts < record.canceled_at_ms:
                    record.canceled_at_ms = cancel_ts
                    record.cancel_reason = normalize_cancel_reason(payload.get("reason"), timeout_type)
                    record.cancel_reason_raw = payload.get("reason")
                    record.timeout_type = str(timeout_type) if timeout_type is not None else None
                    record.cancel_context = payload.get("context")
                    record.canceled_source_path = str(path)
            elif event_type == "ORDER_TIMEOUT":
                client_order_id = str(payload.get("client_order_id") or "")
                order_id = str(payload.get("order_id") or "")
                metadata = payload.get("metadata")
                timeout_type = metadata.get("timeout_type") if isinstance(metadata, dict) else None
                timeout_type = timeout_type or payload.get("timeout_type")
                resolved_order_id = order_id or str(by_client_id.get(client_order_id, {}).get("order_id") or "")
                record = records.get(resolved_order_id)
                if record is None:
                    continue
                if timeout_type and record.timeout_type is None:
                    record.timeout_type = str(timeout_type)
            elif event_type == "ORDER_REJECTED":
                why = str(payload.get("why") or "")
                metadata = payload.get("metadata") or {}
                if why != "MAKER_ONLY_REJECT" and metadata.get("reason_code") != "MAKER_ONLY_REJECT":
                    continue
                rejects.append(
                    {
                        "ts_ms": int(payload.get("timestamp")),
                        "symbol": str(payload.get("symbol") or ""),
                        "side": str(payload.get("side") or ""),
                        "reason": "MAKER_ONLY_REJECT",
                        "error_code": metadata.get("error_code"),
                        "error_msg": metadata.get("error_msg"),
                        "price": payload.get("price"),
                        "rid": payload.get("rid"),
                        "source_hint": derive_source_hint(payload.get("rid")),
                        "path": str(path),
                    }
                )
    return records, by_client_id, rejects


def parse_execution_logs(
    paths: list[Path],
    source_stats: dict[str, SourceStats],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, str]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    fills: dict[str, tuple[int, str]] = {}
    timeouts: dict[str, tuple[int, str]] = {}
    rejects: list[dict[str, Any]] = []
    adv_logs: dict[str, dict[str, Any]] = {}
    for path in paths:
        stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="text"))
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                ts_ms = parse_text_ts_to_utc_ms(line)
                stats.update(ts_ms)
                if ts_ms is None:
                    continue
                fill_match = FILL_RE.search(line)
                if fill_match:
                    order_id = fill_match.group("order_id")
                    current = fills.get(order_id)
                    if current is None or ts_ms < current[0]:
                        fills[order_id] = (ts_ms, str(path))
                    continue
                timeout_match = TIMEOUT_RE.search(line)
                if timeout_match:
                    order_id = timeout_match.group("order_id")
                    current = timeouts.get(order_id)
                    if current is None or ts_ms < current[0]:
                        timeouts[order_id] = (ts_ms, timeout_match.group("timeout_type"))
                    continue
                reject_match = MAKER_REJECT_RE.search(line)
                if reject_match:
                    rejects.append(
                        {
                            "ts_ms": ts_ms,
                            "symbol": reject_match.group("symbol"),
                            "side": reject_match.group("side"),
                            "reason": "MAKER_ONLY_REJECT",
                            "error_code": int(reject_match.group("code")),
                            "error_msg": "",
                            "price": None,
                            "rid": None,
                            "source_hint": UNKNOWN,
                            "path": str(path),
                        }
                    )
                    continue
                adv_match = ADV_ALL_GATES_RE.search(line)
                if adv_match:
                    adv_logs[adv_match.group("order_id")] = {
                        "ts_ms": ts_ms,
                        "symbol": adv_match.group("symbol"),
                        "regime": adv_match.group("regime"),
                        "age_ms": int(adv_match.group("age_ms")),
                        "drift": float(adv_match.group("drift")),
                        "path": str(path),
                    }
    return fills, timeouts, rejects, adv_logs


def parse_feature_logs(
    paths: list[Path],
    source_stats: dict[str, SourceStats],
) -> dict[str, list[FeatureSample]]:
    samples: dict[str, list[FeatureSample]] = defaultdict(list)
    pending_tf: dict[str, deque[tuple[int, int]]] = defaultdict(deque)
    for path in paths:
        stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="text"))
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                ts_ms = parse_text_ts_to_utc_ms(line)
                stats.update(ts_ms)
                if ts_ms is None:
                    continue
                emit_match = FEATURE_EMIT_RE.search(line)
                if emit_match:
                    symbol = emit_match.group("symbol")
                    tf_sec = int(emit_match.group("tf"))
                    pending_tf[symbol].append((ts_ms, tf_sec))
                    while pending_tf[symbol] and ts_ms - pending_tf[symbol][0][0] > 60_000:
                        pending_tf[symbol].popleft()
                    continue
                feature_match = FEATURE_RE.search(line)
                if not feature_match:
                    continue
                symbol = feature_match.group("symbol")
                try:
                    payload = json.loads(feature_match.group("payload"))
                except json.JSONDecodeError:
                    continue
                price_raw = payload.get("price")
                if price_raw is None:
                    continue
                try:
                    price = float(price_raw)
                except (TypeError, ValueError):
                    continue
                atr_raw = payload.get("atr_14")
                atr = None
                if atr_raw not in (None, ""):
                    try:
                        atr = float(atr_raw)
                    except (TypeError, ValueError):
                        atr = None
                queue = pending_tf[symbol]
                while queue and ts_ms - queue[0][0] > 60_000:
                    queue.popleft()
                assigned_tf = queue.popleft()[1] if queue else None
                samples[symbol].append(
                    FeatureSample(
                        ts_ms=ts_ms,
                        price=price,
                        tf_sec=assigned_tf,
                        atr=atr,
                        source=str(path),
                    )
                )
    for symbol in list(samples):
        samples[symbol].sort(key=lambda item: item.ts_ms)
    return samples


def parse_regime_log(
    path: Path,
    source_stats: dict[str, SourceStats],
) -> tuple[dict[str, list[RegimeEvent]], int]:
    stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="text"))
    regimes: dict[str, list[RegimeEvent]] = defaultdict(list)
    basis_tf_sec = 300
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            ts_ms = parse_text_ts_to_utc_ms(line)
            stats.update(ts_ms)
            if ts_ms is None:
                continue
            cfg_match = REGIME_CFG_RE.search(line)
            if cfg_match:
                basis_tf_sec = int(cfg_match.group("tf"))
            regime_match = REGIME_RE_ASCII.search(line) or REGIME_RE.search(line)
            if not regime_match:
                continue
            try:
                confidence = float(regime_match.group("confidence"))
            except ValueError:
                confidence = None
            regimes[regime_match.group("symbol")].append(
                RegimeEvent(
                    ts_ms=ts_ms,
                    regime=regime_match.group("regime"),
                    confidence=confidence,
                    raw=regime_match.group("raw"),
                    model=regime_match.group("model"),
                    source=str(path),
                )
            )
    for symbol in list(regimes):
        regimes[symbol].sort(key=lambda item: item.ts_ms)
    return regimes, basis_tf_sec


def parse_bars_file(
    path: Path,
    source_stats: dict[str, SourceStats],
) -> dict[str, list[BarSample]]:
    stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="jsonl"))
    bars: dict[str, list[BarSample]] = defaultdict(list)
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_ms = payload.get("ts_ms")
            if not isinstance(ts_ms, int):
                continue
            stats.update(ts_ms)
            symbol = payload.get("symbol")
            if not isinstance(symbol, str):
                continue
            close_raw = (payload.get("ohlcv") or {}).get("c")
            if close_raw is None:
                continue
            try:
                close = float(close_raw)
            except (TypeError, ValueError):
                continue
            atr_raw = (payload.get("indicators") or {}).get("atr")
            atr = None
            if atr_raw not in (None, ""):
                try:
                    atr = float(atr_raw)
                except (TypeError, ValueError):
                    atr = None
            bars[symbol].append(BarSample(ts_ms=ts_ms, close=close, atr=atr, source=str(path)))
    for symbol in list(bars):
        bars[symbol].sort(key=lambda item: item.ts_ms)
    return bars


def parse_guardian_log(
    path: Path | None,
    source_stats: dict[str, SourceStats],
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "cleanup_runs": 0,
            "cleanup_cancelled_total": 0,
            "cleanup_cancelled_nonzero": 0,
            "retries_confirmed_missing": 0,
        }
    stats = source_stats.setdefault(str(path), SourceStats(path=str(path), fmt="text"))
    cleanup_runs = 0
    cancelled_total = 0
    cancelled_nonzero = 0
    confirmed_missing = 0
    cleanup_re = re.compile(r"Orphan cleanup completed: cancelled (?P<count>\d+) brackets")
    confirmed_re = re.compile(r"Position confirmed missing")
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            ts_ms = parse_text_ts_to_utc_ms(line)
            stats.update(ts_ms)
            cleanup_match = cleanup_re.search(line)
            if cleanup_match:
                cleanup_runs += 1
                count = int(cleanup_match.group("count"))
                cancelled_total += count
                if count > 0:
                    cancelled_nonzero += 1
            if confirmed_re.search(line):
                confirmed_missing += 1
    return {
        "cleanup_runs": cleanup_runs,
        "cleanup_cancelled_total": cancelled_total,
        "cleanup_cancelled_nonzero": cancelled_nonzero,
        "retries_confirmed_missing": confirmed_missing,
    }


def apply_execution_events(
    records: dict[str, OrderRecord],
    fills: dict[str, tuple[int, str]],
    timeouts: dict[str, tuple[int, str]],
    adv_logs: dict[str, dict[str, Any]],
) -> None:
    for order_id, record in records.items():
        fill = fills.get(order_id)
        if fill is not None:
            fill_ts, fill_path = fill
            if record.filled_at_ms is None or fill_ts < record.filled_at_ms:
                record.filled_at_ms = fill_ts
                record.filled_source_path = fill_path
        timeout = timeouts.get(order_id)
        if timeout is not None and record.timeout_type is None:
            record.timeout_type = timeout[1]
        adv = adv_logs.get(order_id)
        if adv is not None:
            record.adv_gate_logged = True
            record.adv_gate_age_ms = adv["age_ms"]
            record.adv_gate_drift = adv["drift"]


def annotate_regime_context(
    records: dict[str, OrderRecord],
    regimes: dict[str, list[RegimeEvent]],
    basis_tf_sec: int,
) -> None:
    window_ms = basis_tf_sec * 2 * 1000
    for record in records.values():
        if record.canceled_at_ms is None:
            continue
        symbol_events = regimes.get(record.symbol, [])
        if not symbol_events:
            continue
        near = [
            event
            for event in symbol_events
            if abs(event.ts_ms - record.canceled_at_ms) <= window_ms
        ]
        record.regime_change_near_cancel = bool(near)
        record.regime_change_near_cancel_count = len(near)
        record.regime_change_near_cancel_labels = [event.regime for event in near]


def choose_cancel_price(
    record: OrderRecord,
    feature_series: dict[str, list[FeatureSample]],
    bars: dict[str, list[BarSample]],
) -> tuple[float | None, float | None, str | None]:
    if record.canceled_at_ms is None:
        return None, None, None
    features = feature_series.get(record.symbol, [])
    if features:
        ts_list = [item.ts_ms for item in features]
        idx = nearest_in_window(ts_list, record.canceled_at_ms, PRICE_NEAR_CANCEL_WINDOW_MS)
        if idx is not None:
            sample = features[idx]
            return sample.price, sample.atr, f"feature:{Path(sample.source).name}"
    bar_series = bars.get(record.symbol, [])
    if bar_series:
        ts_list = [item.ts_ms for item in bar_series]
        idx = nearest_in_window(ts_list, record.canceled_at_ms, 180_000)
        if idx is not None:
            sample = bar_series[idx]
            return sample.close, sample.atr, f"bar:{Path(sample.source).name}"
    return None, None, None


def last_non_null_atr_before(
    bars: dict[str, list[BarSample]],
    symbol: str,
    target_ts_ms: int,
) -> float | None:
    series = bars.get(symbol, [])
    if not series:
        return None
    ts_list = [item.ts_ms for item in series]
    idx = bisect_left(ts_list, target_ts_ms)
    idx = min(idx, len(series) - 1)
    if idx < len(series) and series[idx].ts_ms > target_ts_ms:
        idx -= 1
    while idx >= 0:
        atr = series[idx].atr
        if atr is not None and atr > 0:
            return atr
        idx -= 1
    return None


def annotate_cancel_prices(
    records: dict[str, OrderRecord],
    feature_series: dict[str, list[FeatureSample]],
    bars: dict[str, list[BarSample]],
) -> None:
    for record in records.values():
        if record.canceled_at_ms is None:
            continue
        price, atr, source = choose_cancel_price(record, feature_series, bars)
        if price is not None:
            record.price_at_cancel = price
            record.price_at_cancel_source = source
        if atr is None:
            atr = last_non_null_atr_before(bars, record.symbol, record.canceled_at_ms)
        record.atr_at_cancel = atr


def build_bar_index(bars: dict[str, list[BarSample]]) -> dict[str, dict[str, list[Any]]]:
    index: dict[str, dict[str, list[Any]]] = {}
    for symbol, series in bars.items():
        index[symbol] = {"ts": [item.ts_ms for item in series], "rows": series}
    return index


def build_feature_index(features: dict[str, list[FeatureSample]]) -> dict[str, dict[str, list[Any]]]:
    index: dict[str, dict[str, list[Any]]] = {}
    for symbol, series in features.items():
        index[symbol] = {"ts": [item.ts_ms for item in series], "rows": series}
    return index


def sample_post_cancel_price(
    symbol: str,
    target_ts_ms: int,
    bar_index: dict[str, dict[str, list[Any]]],
    feature_index: dict[str, dict[str, list[Any]]],
) -> tuple[float | None, int | None, str | None]:
    bar_data = bar_index.get(symbol)
    if bar_data:
        idx = first_after(bar_data["ts"], target_ts_ms, BAR_TARGET_MAX_LAG_MS)
        if idx is not None:
            sample = bar_data["rows"][idx]
            return sample.close, sample.ts_ms, f"bar:{Path(sample.source).name}"
    feature_data = feature_index.get(symbol)
    if feature_data:
        idx = first_after(feature_data["ts"], target_ts_ms, FEATURE_TARGET_MAX_LAG_MS)
        if idx is not None:
            sample = feature_data["rows"][idx]
            return sample.price, sample.ts_ms, f"feature:{Path(sample.source).name}"
    return None, None, None


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No data_\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def dedupe_maker_rejects(rejects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, Any, int], dict[str, Any]] = {}
    for item in sorted(rejects, key=lambda row: int(row.get("ts_ms") or 0)):
        bucket_sec = int(round(int(item.get("ts_ms") or 0) / 1000.0))
        key = (
            str(item.get("symbol") or ""),
            str(item.get("side") or ""),
            item.get("error_code"),
            bucket_sec,
        )
        existing = deduped.get(key)
        if existing is None or existing.get("rid") is None and item.get("rid") is not None:
            deduped[key] = item
    return list(deduped.values())


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    logs_dir = (repo_root / args.logs_dir).resolve()
    bars_file = (repo_root / args.bars_file).resolve()
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    source_stats: dict[str, SourceStats] = {}
    order_log_path = logs_dir / "order_log_v1.jsonl"
    if not order_log_path.exists():
        raise SystemExit(f"Missing order log: {order_log_path}")

    records, _, order_rejects = parse_order_log(order_log_path, source_stats)
    exec_logs = rotated_log_files(logs_dir, "domain_execution_position.log")
    fills, timeouts, exec_rejects, adv_logs = parse_execution_logs(exec_logs, source_stats)
    apply_execution_events(records, fills, timeouts, adv_logs)

    feature_logs = rotated_log_files(logs_dir, "domain_feature_engineering.log")
    feature_series = parse_feature_logs(feature_logs, source_stats)
    regime_log = logs_dir / "domain_regime_detector.log"
    regimes, basis_tf_sec = parse_regime_log(regime_log, source_stats)
    bars = parse_bars_file(bars_file, source_stats) if bars_file.exists() else {}
    guardian_summary = parse_guardian_log(logs_dir / "order_guardian.log", source_stats)

    update_order_terminal_status(records)
    annotate_regime_context(records, regimes, basis_tf_sec)
    annotate_cancel_prices(records, feature_series, bars)

    start_ms, end_ms, available_start_ms = compute_window(records, args.hours)
    window_records = {
        order_id: record
        for order_id, record in records.items()
        if start_ms <= record.placed_at_ms <= end_ms
    }
    update_order_terminal_status(window_records)

    placed_records = list(window_records.values())
    filled_records = [record for record in placed_records if record.terminal_status == "FILLED"]
    canceled_records = [record for record in placed_records if record.terminal_status == "CANCELED"]
    open_records = [record for record in placed_records if record.terminal_status == "OPEN"]

    bar_index = build_bar_index(bars)
    feature_index = build_feature_index(feature_series)

    post_cancel_rows: list[dict[str, Any]] = []
    per_reason_horizon: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for record in canceled_records:
        if record.canceled_at_ms is None:
            continue
        atr_at_cancel = record.atr_at_cancel
        for horizon_min in HORIZONS_MIN:
            target_ts_ms = record.canceled_at_ms + horizon_min * 60_000
            sample_price, sample_ts_ms, sample_source = sample_post_cancel_price(
                record.symbol,
                target_ts_ms,
                bar_index,
                feature_index,
            )
            fav_bps = None
            fav_atr = None
            win = None
            if sample_price is not None:
                fav_bps = favorable_bps(record, sample_price)
                win = fav_bps > 0
                if atr_at_cancel and atr_at_cancel > 0:
                    fav_atr = favorable_move(record, sample_price) / atr_at_cancel
            post_cancel_rows.append(
                {
                    "order_id": record.order_id,
                    "client_order_id": record.client_order_id,
                    "symbol": record.symbol,
                    "side": record.side,
                    "cancel_reason": record.cancel_reason or "CANCEL_UNKNOWN",
                    "cancel_ts_utc": iso_utc(record.canceled_at_ms),
                    "limit_price": f"{record.limit_price:.8f}",
                    "price_at_cancel": format_num(record.price_at_cancel, 8),
                    "atr_at_cancel": format_num(atr_at_cancel, 8),
                    "horizon_min": horizon_min,
                    "target_ts_utc": iso_utc(target_ts_ms),
                    "sample_ts_utc": iso_utc(sample_ts_ms),
                    "sample_price": format_num(sample_price, 8),
                    "sample_source": sample_source or "",
                    "sample_lag_sec": format_num(
                        None if sample_ts_ms is None else (sample_ts_ms - target_ts_ms) / 1000.0,
                        1,
                    ),
                    "win": "" if win is None else str(bool(win)),
                    "potential_bps": format_num(fav_bps, 2),
                    "potential_atr": format_num(fav_atr, 4),
                }
            )
            if sample_price is not None:
                per_reason_horizon[record.cancel_reason or "CANCEL_UNKNOWN"][horizon_min].append(
                    {
                        "order_id": record.order_id,
                        "sample_price": sample_price,
                        "potential_bps": fav_bps,
                        "potential_atr": fav_atr,
                        "win": win,
                    }
                )

    total_placed = len(placed_records)
    total_filled = len(filled_records)
    total_canceled = len(canceled_records)
    fill_rate = (total_filled / total_placed * 100.0) if total_placed else 0.0
    cancel_rate = (total_canceled / total_placed * 100.0) if total_placed else 0.0

    cancel_reason_rows: list[dict[str, Any]] = []
    reason_groups: dict[str, list[OrderRecord]] = defaultdict(list)
    for record in canceled_records:
        reason_groups[reason_bucket(record.cancel_reason)].append(record)
    for reason, items in sorted(reason_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        ages = [(item.canceled_at_ms - item.placed_at_ms) / 1000.0 for item in items if item.canceled_at_ms]
        symbols = Counter(item.symbol for item in items)
        sources = Counter((item.strategy_id or item.source_hint or UNKNOWN) for item in items)
        regime_hits = sum(1 for item in items if item.regime_change_near_cancel)
        horizon15 = per_reason_horizon[reason].get(15, [])
        horizon30 = per_reason_horizon[reason].get(30, [])
        cancel_reason_rows.append(
            {
                "reason": reason,
                "count": len(items),
                "share_pct": round(len(items) / total_canceled * 100.0, 2) if total_canceled else 0.0,
                "median_cancel_age_sec": round(safe_median(ages) or 0.0, 2),
                "symbols_top10": top_counts(symbols),
                "strategies_top10": top_counts(sources),
                "regime_change_within_2bars_count": regime_hits,
                "regime_change_within_2bars_share_pct": round(
                    regime_hits / len(items) * 100.0, 2
                )
                if items
                else 0.0,
                "premature_win_rate_15m_pct": round(
                    sum(1 for row in horizon15 if row["win"]) / len(horizon15) * 100.0, 2
                )
                if horizon15
                else "",
                "avg_potential_bps_15m": round(
                    statistics.mean(row["potential_bps"] for row in horizon15 if row["potential_bps"] is not None),
                    2,
                )
                if horizon15
                else "",
                "premature_win_rate_30m_pct": round(
                    sum(1 for row in horizon30 if row["win"]) / len(horizon30) * 100.0, 2
                )
                if horizon30
                else "",
                "avg_potential_bps_30m": round(
                    statistics.mean(row["potential_bps"] for row in horizon30 if row["potential_bps"] is not None),
                    2,
                )
                if horizon30
                else "",
            }
        )

    symbol_rows: list[dict[str, Any]] = []
    symbol_groups: dict[str, list[OrderRecord]] = defaultdict(list)
    for record in placed_records:
        symbol_groups[record.symbol].append(record)
    for symbol, items in sorted(symbol_groups.items()):
        sym_filled = [item for item in items if item.terminal_status == "FILLED"]
        sym_canceled = [item for item in items if item.terminal_status == "CANCELED"]
        reason_counts = Counter(item.cancel_reason or "CANCEL_UNKNOWN" for item in sym_canceled)
        symbol_rows.append(
            {
                "symbol": symbol,
                "placed": len(items),
                "filled": len(sym_filled),
                "canceled": len(sym_canceled),
                "open": len([item for item in items if item.terminal_status == "OPEN"]),
                "top_cancel_reasons": top_counts(reason_counts),
                "median_cancel_age_sec": round(median_age_sec(sym_canceled, "canceled_at_ms") or 0.0, 2)
                if sym_canceled
                else "",
                "median_fill_age_sec": round(median_age_sec(sym_filled, "filled_at_ms") or 0.0, 2)
                if sym_filled
                else "",
                "cancel_heaviness": "inf"
                if len(sym_filled) == 0 and len(sym_canceled) > 0
                else round(len(sym_canceled) / len(sym_filled), 2)
                if len(sym_filled) > 0
                else "",
            }
        )

    maker_rejects = dedupe_maker_rejects(order_rejects + exec_rejects)
    maker_by_symbol = Counter(item["symbol"] for item in maker_rejects if item.get("symbol"))
    maker_by_side = Counter(item["side"] for item in maker_rejects if item.get("side"))
    maker_by_error = Counter(str(item.get("error_code")) for item in maker_rejects if item.get("error_code") is not None)

    trading_text = read_text(repo_root / "config/aurora/trading.yaml")
    domains_text = read_text(repo_root / "config/aurora/domains.yaml")
    env_mode = parse_env_mode(repo_root)
    configured_mode = extract_simple_yaml_value(trading_text, "mode")
    effective_mode = None
    for path in exec_logs:
        mode_match = re.search(r"domain_mode=([a-zA-Z0-9_]+)", read_text(path))
        if mode_match:
            effective_mode = mode_match.group(1)
            break

    ack_ttl_ms = extract_simple_yaml_value(trading_text, "ack_ttl_ms")
    fill_ttl_ms = extract_simple_yaml_value(trading_text, "fill_ttl_ms")
    orphan_period_sec = extract_simple_yaml_value(trading_text, "periodic_interval_sec")
    orphan_min_age_sec = extract_simple_yaml_value(trading_text, "min_order_age_sec")
    ttl_map = extract_ttl_map(domains_text)
    min_age_before_cancel_sec = extract_simple_yaml_value(domains_text, "min_age_before_cancel_sec")
    atr_mult = extract_simple_yaml_value(domains_text, "atr_mult")
    never_cancel = extract_list_block(domains_text, "never_cancel_regimes")
    may_cancel = extract_side_regimes(domains_text)

    timeout_orders = [record for record in canceled_records if record.cancel_reason == TIMEOUT_REASON]
    timeout_ages = [
        (record.canceled_at_ms - record.placed_at_ms) / 1000.0
        for record in timeout_orders
        if record.canceled_at_ms is not None
    ]
    timeout_clusters = Counter()
    for age_sec in timeout_ages:
        ttl_sec, delta = closest_config_ttl(age_sec, ttl_map)
        if ttl_sec is not None and delta is not None and delta <= 10:
            timeout_clusters[f"{ttl_sec}s"] += 1
        else:
            timeout_clusters[f"{round(age_sec)}s"] += 1

    advanced_orders = [
        record for record in canceled_records if record.cancel_reason == "CANCEL_STALE_REGIME_ADVANCED"
    ]
    advanced_near_fill = [
        record
        for record in advanced_orders
        if (distance_bps := distance_bps_to_limit(record, record.price_at_cancel)) is not None and distance_bps <= 5
    ]
    advanced_median_distance = safe_median(
        [
            distance
            for record in advanced_orders
            if (distance := distance_bps_to_limit(record, record.price_at_cancel)) is not None
        ]
    )

    top_reason_names = [row["reason"] for row in cancel_reason_rows[:3]]
    premature_section_rows: list[list[str]] = []
    for reason in top_reason_names:
        for horizon_min in HORIZONS_MIN:
            rows = per_reason_horizon[reason].get(horizon_min, [])
            if not rows:
                continue
            win_rate = sum(1 for row in rows if row["win"]) / len(rows) * 100.0
            avg_bps = statistics.mean(
                row["potential_bps"] for row in rows if row["potential_bps"] is not None
            )
            avg_atr = (
                statistics.mean(
                    row["potential_atr"] for row in rows if row["potential_atr"] is not None
                )
                if any(row["potential_atr"] is not None for row in rows)
                else None
            )
            premature_section_rows.append(
                [
                    reason,
                    f"T+{horizon_min}m",
                    str(len(rows)),
                    format_pct(win_rate),
                    format_num(avg_bps, 2),
                    format_num(avg_atr, 4),
                ]
            )

    root_cause_rank = []
    for row in cancel_reason_rows[:3]:
        reason = row["reason"]
        horizon15 = per_reason_horizon[reason].get(15, [])
        avg_potential = (
            statistics.mean(item["potential_bps"] for item in horizon15 if item["potential_bps"] is not None)
            if horizon15
            else None
        )
        root_cause_rank.append(
            {
                "reason": reason,
                "count": row["count"],
                "share_pct": row["share_pct"],
                "median_age_sec": row["median_cancel_age_sec"],
                "premature_15m_pct": round(
                    sum(1 for item in horizon15 if item["win"]) / len(horizon15) * 100.0, 2
                )
                if horizon15
                else None,
                "avg_potential_bps_15m": round(avg_potential, 2) if avg_potential is not None else None,
            }
        )
    if maker_rejects:
        root_cause_rank.append(
            {
                "reason": "MAKER_ONLY_REJECT",
                "count": len(maker_rejects),
                "share_pct": None,
                "median_age_sec": None,
                "premature_15m_pct": None,
                "avg_potential_bps_15m": None,
            }
        )

    report_path = out_dir / f"{args.date}_cancel_forensics.md"
    reasons_csv_path = out_dir / f"{args.date}_cancel_reasons.csv"
    symbols_csv_path = out_dir / f"{args.date}_symbol_scoreboard.csv"
    drift_csv_path = out_dir / f"{args.date}_post_cancel_drift.csv"

    write_csv(
        reasons_csv_path,
        cancel_reason_rows,
        [
            "reason",
            "count",
            "share_pct",
            "median_cancel_age_sec",
            "symbols_top10",
            "strategies_top10",
            "regime_change_within_2bars_count",
            "regime_change_within_2bars_share_pct",
            "premature_win_rate_15m_pct",
            "avg_potential_bps_15m",
            "premature_win_rate_30m_pct",
            "avg_potential_bps_30m",
        ],
    )
    write_csv(
        symbols_csv_path,
        symbol_rows,
        [
            "symbol",
            "placed",
            "filled",
            "canceled",
            "open",
            "top_cancel_reasons",
            "median_cancel_age_sec",
            "median_fill_age_sec",
            "cancel_heaviness",
        ],
    )
    write_csv(
        drift_csv_path,
        post_cancel_rows,
        [
            "order_id",
            "client_order_id",
            "symbol",
            "side",
            "cancel_reason",
            "cancel_ts_utc",
            "limit_price",
            "price_at_cancel",
            "atr_at_cancel",
            "horizon_min",
            "target_ts_utc",
            "sample_ts_utc",
            "sample_price",
            "sample_source",
            "sample_lag_sec",
            "win",
            "potential_bps",
            "potential_atr",
        ],
    )

    source_rows = [
        [
            Path(stat.path).as_posix(),
            stat.fmt,
            str(stat.count),
            iso_utc(stat.min_ts_ms),
            iso_utc(stat.max_ts_ms),
        ]
        for stat in sorted(source_stats.values(), key=lambda item: item.path)
    ]
    cancel_breakdown_md_rows = [
        [
            row["reason"],
            str(row["count"]),
            format_pct(row["share_pct"]),
            format_num(row["median_cancel_age_sec"], 1),
            row["symbols_top10"],
            row["strategies_top10"],
            f'{row["regime_change_within_2bars_count"]} ({format_pct(row["regime_change_within_2bars_share_pct"])}%)',
        ]
        for row in cancel_reason_rows
    ]
    symbol_md_rows = [
        [
            row["symbol"],
            str(row["placed"]),
            str(row["filled"]),
            str(row["canceled"]),
            str(row["open"]),
            row["top_cancel_reasons"],
            str(row["median_cancel_age_sec"]),
            str(row["median_fill_age_sec"]),
            str(row["cancel_heaviness"]),
        ]
        for row in symbol_rows
    ]
    root_cause_rows = [
        [
            item["reason"],
            str(item["count"]),
            "" if item["share_pct"] is None else format_pct(item["share_pct"]),
            "" if item["median_age_sec"] is None else format_num(float(item["median_age_sec"]), 1),
            "" if item["premature_15m_pct"] is None else format_pct(item["premature_15m_pct"]),
            "" if item["avg_potential_bps_15m"] is None else format_num(item["avg_potential_bps_15m"], 2),
        ]
        for item in root_cause_rank[:3]
    ]

    available_hours = (end_ms - available_start_ms) / 3_600_000.0 if end_ms >= available_start_ms else 0.0
    requested_start_ms = end_ms - args.hours * 3_600_000
    coverage_shortfall = available_start_ms > requested_start_ms
    matching_notes = [
        "Primary lifecycle key: `order_id` from `logs/order_log_v1.jsonl` `ORDER_PLACED`.",
        "Fallback key: `client_order_id` only when timeout lines carry it but `order_id` is missing.",
        f"Text logs are written in `{LOCAL_TZ_NAME}` and normalized to UTC before matching against JSONL epoch timestamps.",
        "Pending-entry scope = `client_order_id` starts with `ENTRY-` and `adapter_response.type == LIMIT`; market entries and bracket cancels are excluded.",
        "Feature snapshots carry `price`, not `mid_price`; the report uses `price` as the runtime price proxy.",
        "ATR at cancel and post-cancel horizons use `FEATURES_CALCULATED` when available; bar-based fallback comes from `logs/mean_reversion/bars_180s.jsonl`.",
        "Observed limitation: `bars_180s.jsonl` contains only `DOGEUSDT/XRPUSDT` in this runtime snapshot, so `BTCUSDT/ETHUSDT/SOLUSDT` drift samples come from `FEATURES_CALCULATED`.",
    ]

    recommendations: list[str] = []
    if timeout_orders:
        ttl_mode = timeout_clusters.most_common(1)[0][0] if timeout_clusters else ""
        recommendations.append(
            "Priority 1: timeouts are real cancels. Tune `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec` before touching the global watchdog if the age cluster matches per-order TTL overrides."
        )
        if ttl_mode:
            recommendations.append(
                f"Inference: timeout cancels cluster around `{ttl_mode}`; this is consistent with `ttl_by_tf_sec` rather than `trading.execution.watchdog.fill_ttl_ms={fill_ttl_ms}`."
            )
    if reason_groups.get("CANCEL_SUPERSEDED"):
        recommendations.append(
            "Priority 2: `CANCEL_SUPERSEDED` is churn-driven. Add a supersede guard that skips cancel/repost when the new limit is within a small bps/ATR band of the resting order, then verify with the same drift report."
        )
    if maker_rejects:
        recommendations.append(
            "Priority 3: maker rejects are frequent but sit outside the cancel funnel. Reprice GTX entries one tick deeper or add a bounded retry-on-maker-reject path, then track `MAKER_ONLY_REJECT` count separately from cancels."
        )
    if not advanced_orders:
        recommendations.append(
            "No observed `CANCEL_STALE_REGIME_ADVANCED` in the available window. Keep current thresholds unchanged until logs contain real examples or add explicit gate telemetry for age/drift/regime on every advanced-cancel decision."
        )

    lines = [
        f"# Cancel Forensics Report ({args.date})",
        "",
        "## Scope",
        "",
        f"- Requested window: last `{args.hours}h` ending `{iso_utc(end_ms)}`.",
        f"- Available pending-entry lifecycle window: `{iso_utc(available_start_ms)}` -> `{iso_utc(end_ms)}` ({available_hours:.2f}h).",
        "- Time normalization: JSONL timestamps are UTC epoch-ms; text logs are parsed as Europe/Kiev and converted to UTC.",
    ]
    if coverage_shortfall:
        lines.append(
            "- Limitation: `order_log_v1.jsonl` retention is shorter than the requested window, so the audit covers the full available lifecycle window instead of a full 24-72h sample."
        )
    lines.extend(
        [
            "",
            "## Log Sources",
            "",
            f"- `.env` `TRADING_MODE`: `{env_mode or ''}`",
            f"- `config/aurora/trading.yaml` `trading.mode`: `{configured_mode or ''}`",
            f"- Effective runtime mode from execution logs: `{effective_mode or ''}`",
            "",
            markdown_table(["Path", "Format", "Events", "UTC start", "UTC end"], source_rows).rstrip(),
            "",
            "## Matching Policy",
            "",
        ]
    )
    for note in matching_notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Funnel",
            "",
            markdown_table(
                ["Metric", "Value"],
                [
                    ["ORDER_PLACED", str(total_placed)],
                    ["FILLED", str(total_filled)],
                    ["CANCELED", str(total_canceled)],
                    ["OPEN_AT_WINDOW_END", str(len(open_records))],
                    ["fill_rate_pct", format_pct(fill_rate)],
                    ["cancel_rate_pct", format_pct(cancel_rate)],
                    ["median_time_to_fill_sec", format_num(median_age_sec(filled_records, "filled_at_ms"), 1)],
                    ["median_time_to_cancel_sec", format_num(median_age_sec(canceled_records, "canceled_at_ms"), 1)],
                ],
            ).rstrip(),
            "",
            "## Cancel Reasons Breakdown",
            "",
            markdown_table(
                [
                    "reason",
                    "count",
                    "share %",
                    "median age s",
                    "symbols top-10",
                    "strategies top-10",
                    "regime change +/-2 bars",
                ],
                cancel_breakdown_md_rows,
            ).rstrip(),
            "",
            "## Per-Symbol Scoreboard",
            "",
            markdown_table(
                [
                    "symbol",
                    "placed",
                    "filled",
                    "canceled",
                    "open",
                    "top cancel reasons",
                    "median cancel s",
                    "median fill s",
                    "cancel heaviness",
                ],
                symbol_md_rows,
            ).rstrip(),
            "",
            "## Killer Checks",
            "",
            "### Advanced stale cancel",
            "",
            f"- `CANCEL_STALE_REGIME_ADVANCED` count: `{len(advanced_orders)}`.",
        ]
    )
    if advanced_orders:
        lines.extend(
            [
                f"- Logged gate-pass lines: `{sum(1 for record in advanced_orders if record.adv_gate_logged)}` / `{len(advanced_orders)}`.",
                f"- Median distance to limit at cancel: `{format_num(advanced_median_distance, 2)}` bps.",
                f"- Near-fill cancels (<=5 bps from limit): `{len(advanced_near_fill)}` / `{len(advanced_orders)}`.",
            ]
        )
    else:
        lines.append(
            "- No runtime examples in the available window, so effectiveness/prematurity cannot be validated from observed cancels."
        )
    lines.extend(
        [
            "",
            "### Watchdog / TTL / orphan / exchange reject mechanisms",
            "",
            f"- `trading.execution.watchdog.ack_ttl_ms`: `{ack_ttl_ms or ''}`",
            f"- `trading.execution.watchdog.fill_ttl_ms`: `{fill_ttl_ms or ''}`",
            f"- `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec`: `{ttl_map}`",
            f"- `orphan_monitor.periodic_interval_sec`: `{orphan_period_sec or ''}`; `min_order_age_sec`: `{orphan_min_age_sec or ''}`",
            f"- Timeout cancel count (`{TIMEOUT_REASON}`): `{len(timeout_orders)}`; median age `{format_num(safe_median(timeout_ages), 1)}` s; dominant age cluster `{top_counts(timeout_clusters)}`.",
            f"- Orphan cleanup runs: `{guardian_summary['cleanup_runs']}`; total brackets canceled `{guardian_summary['cleanup_cancelled_total']}`; non-zero cleanup runs `{guardian_summary['cleanup_cancelled_nonzero']}`.",
            f"- Maker-only rejects (`MAKER_ONLY_REJECT`): `{len(maker_rejects)}`; by symbol `{top_counts(maker_by_symbol)}`; by side `{top_counts(maker_by_side)}`; error codes `{top_counts(maker_by_error)}`.",
        ]
    )
    if timeout_orders and ttl_map:
        lines.append(
            "- Inference: timeout ages line up with configured per-TF TTL buckets, so the actual killer is the pending-entry TTL override path, not the global 300s watchdog default."
        )
    if guardian_summary["cleanup_cancelled_total"] == 0:
        lines.append(
            "- Orphan monitor is noisy in logs but did not cancel anything in this window, so it is not the #1 killer for pending entries here."
        )
    if maker_rejects:
        lines.append(
            "- Maker rejects are pre-placement failures and should be tracked separately from the pending-entry cancel funnel."
        )
    lines.extend(
        [
            "",
            "## Premature Cancels By Reason",
            "",
            markdown_table(
                ["reason", "horizon", "samples", "win %", "avg potential bps", "avg potential ATR"],
                premature_section_rows,
            ).rstrip(),
            "",
            "## Root-Cause Ranking",
            "",
            markdown_table(
                [
                    "reason",
                    "count",
                    "share %",
                    "median age s",
                    "premature win @15m %",
                    "avg potential @15m bps",
                ],
                root_cause_rows,
            ).rstrip(),
            "",
            "## Recommendations",
            "",
        ]
    )
    for item in recommendations:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Config Snapshot",
            "",
            f"- `advanced_stale_cancel.min_age_before_cancel_sec`: `{min_age_before_cancel_sec or ''}`",
            f"- `advanced_stale_cancel.drift_away.atr_mult`: `{atr_mult or ''}`",
            f"- `advanced_stale_cancel.may_cancel_regimes`: `{may_cancel}`",
            f"- `advanced_stale_cancel.never_cancel_regimes`: `{never_cancel}`",
            "",
            "## Artifacts",
            "",
            f"- `{report_path.as_posix()}`",
            f"- `{reasons_csv_path.as_posix()}`",
            f"- `{symbols_csv_path.as_posix()}`",
            f"- `{drift_csv_path.as_posix()}`",
        ]
    )
    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "report": str(report_path),
                "cancel_reasons_csv": str(reasons_csv_path),
                "symbol_scoreboard_csv": str(symbols_csv_path),
                "post_cancel_drift_csv": str(drift_csv_path),
                "placed": total_placed,
                "filled": total_filled,
                "canceled": total_canceled,
                "open": len(open_records),
                "top_cancel_reasons": cancel_reason_rows[:3],
                "maker_only_rejects": len(maker_rejects),
                "available_hours": round(available_hours, 2),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
