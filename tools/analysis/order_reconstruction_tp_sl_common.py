from __future__ import annotations

import csv
import json
import re
import sqlite3
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

try:
    import yaml
except Exception:
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "order_reconstruction_tp_sl"
DEFAULT_RECORDER_ROOT = ROOT / "data" / "recorder"

HIGH_CONFIDENCE_TIMESTAMP_QUALITIES = {
    "direct",
    "embedded_id",
    "db_join",
    "cross_log_exact",
}
REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES = HIGH_CONFIDENCE_TIMESTAMP_QUALITIES | {
    "cross_log_bounded"}
ORDER_EVENT_TYPES = {"ORDER_PLACED", "ORDER_FILLED",
                     "ORDER_CANCELLED", "ORDER_TIMEOUT", "ORDER_REJECTED"}
TIMESTAMP_FIELD_NAMES = {
    "ts",
    "ts_ms",
    "timestamp",
    "event_ts_ms",
    "created_at",
    "updated_at",
    "transacttime",
    "time",
    "ordertime",
    "order_time",
    "close_ts_ms",
    "entry_ts_ms",
    "exchange_ts",
    "updatetime",
    "workingtime",
    "bar_close_ts_ms",
    "regime_event_ts_ms",
    "features_ts_ms",
}
IDENTITY_KEYS = [
    "rid",
    "lifecycle_id",
    "order_id",
    "client_order_id",
    "origClientOrderId",
    "orig_client_order_id",
    "trade_id",
    "idempotent_key",
    "reservation_id",
]
TP_ROI_GRID = list(range(4, 14))
SL_ROI_GRID = list(range(2, 9))
REPLAY_RESULT_HEADERS = [
    "entry_id",
    "symbol",
    "side",
    "entry_ts_ms",
    "regime_at_entry",
    "leverage",
    "tp_roi_pct",
    "sl_roi_pct",
    "tp_price",
    "sl_price",
    "result",
    "hit_ts_ms",
    "hit_time_iso",
    "holding_minutes",
    "gross_pnl_roi_pct",
    "net_pnl_roi_pct",
    "fee_model",
    "ambiguous_intrabar",
    "data_quality",
]


@dataclass
class AuthorityRow:
    source_file: str
    source_line: int
    payload: dict[str, Any]
    timestamp_ms: int | None
    timestamp_iso: str | None
    timestamp_quality: str
    timestamp_source: str
    timestamp_support: str | None
    sequence_token: str


@dataclass
class EntryAggregate:
    entry_id: str
    symbol: str = ""
    side: str = ""
    strategy_id: str = ""
    intent_rows: list[AuthorityRow] = field(default_factory=list)
    reservation_rows: list[AuthorityRow] = field(default_factory=list)
    placed_rows: list[AuthorityRow] = field(default_factory=list)
    entry_fill_rows: list[AuthorityRow] = field(default_factory=list)
    close_fill_rows: list[AuthorityRow] = field(default_factory=list)
    position_closed_rows: list[AuthorityRow] = field(default_factory=list)
    timeout_rows: list[AuthorityRow] = field(default_factory=list)
    cancel_rows: list[AuthorityRow] = field(default_factory=list)
    other_rows: list[AuthorityRow] = field(default_factory=list)


def iso_utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def normalize_field_name(name: str) -> str:
    return str(name).strip().lower().replace("-", "_")


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(float(value))
    except Exception:
        return None


def stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_magicmock_text(value: Any) -> bool:
    text = stringify(value)
    return bool(text and "magicmock" in text.lower())


def recursive_walk(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for raw_key, nested in value.items():
            key = str(raw_key)
            next_prefix = f"{prefix}.{key}" if prefix else key
            yield next_prefix, nested
            yield from recursive_walk(nested, next_prefix)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            next_prefix = f"{prefix}[{index}]"
            yield next_prefix, nested
            yield from recursive_walk(nested, next_prefix)


def try_parse_timestamp_ms(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            try:
                candidate = int(stripped)
            except ValueError:
                return None
        else:
            return None
    else:
        return None

    if 1_000_000_000_000 <= candidate <= 4_102_444_800_000:
        return candidate
    if 1_700_000_000 <= candidate <= 4_102_444_800:
        return candidate * 1000
    return None


def extract_embedded_epoch_ms(value: Any) -> int | None:
    text = stringify(value)
    if text is None or text.isdigit():
        return None
    digits = "".join(ch if ch.isdigit() else " " for ch in text)
    for token in digits.split():
        if len(token) < 13:
            continue
        for start in range(0, len(token) - 12):
            candidate = try_parse_timestamp_ms(token[start: start + 13])
            if candidate is not None:
                return candidate
    return None


def write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "")
                            for header in headers})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    ensure_ascii=False), encoding="utf-8")


def resolve_recorder_roots(root: Path, recorder_roots: Iterable[Path | str] | None = None) -> list[Path]:
    candidates = list(recorder_roots or [DEFAULT_RECORDER_ROOT])
    resolved: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = (root / path).resolve(strict=False)
        else:
            path = path.resolve(strict=False)
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def load_yaml_file(path: Path) -> Any:
    if yaml is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield line_no, payload


def collect_candidate_values(payload: dict[str, Any], key_name: str) -> list[Any]:
    normalized_target = normalize_field_name(key_name)
    out: list[Any] = []
    for key_path, nested in recursive_walk(payload):
        field_name = normalize_field_name(key_path.split(".")[-1])
        if field_name == normalize_field_name(normalized_target):
            out.append(nested)
    return out


def payload_get(payload: dict[str, Any], *candidates: str) -> Any:
    for candidate in candidates:
        current: Any = payload
        found = True
        for part in candidate.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found:
            if current is None:
                continue
            if isinstance(current, str) and not current.strip():
                continue
            return current
    return None


def normalize_side(value: Any) -> str:
    text = (stringify(value) or "").upper()
    if text in {"BUY", "LONG"}:
        return "BUY"
    if text in {"SELL", "SHORT"}:
        return "SELL"
    return text


def normalize_bool(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = stringify(value)
    if text is None:
        return ""
    lowered = text.lower()
    if lowered in {"true", "1", "yes"}:
        return "true"
    if lowered in {"false", "0", "no"}:
        return "false"
    return text


def extract_order_id(payload: dict[str, Any]) -> str:
    value = payload_get(payload, "order_id",
                        "adapter_response.orderId", "adapter_response.order_id")
    return stringify(value) or ""


def extract_client_order_id(payload: dict[str, Any]) -> str:
    value = payload_get(
        payload,
        "client_order_id",
        "clientOrderId",
        "adapter_response.clientOrderId",
        "origClientOrderId",
        "orig_client_order_id",
        "metadata.close_fill_client_order_id",
    )
    return stringify(value) or ""


def extract_qty(payload: dict[str, Any]) -> float | None:
    return first_non_null(
        to_float(payload_get(payload, "quantity")),
        to_float(payload_get(payload, "qty")),
        to_float(payload_get(payload, "qty_raw")),
        to_float(payload_get(payload, "adapter_response.origQty")),
        to_float(payload_get(payload, "adapter_response.executedQty")),
    )


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def extract_price(payload: dict[str, Any]) -> float | None:
    return first_non_null(
        to_float(payload_get(payload, "price")),
        to_float(payload_get(payload, "adapter_response.price")),
        to_float(payload_get(payload, "metadata.close_price")),
    )


def extract_avg_fill_price(payload: dict[str, Any]) -> float | None:
    return first_non_null(
        to_float(payload_get(payload, "avg_price")),
        to_float(payload_get(payload, "avgPrice")),
        to_float(payload_get(payload, "adapter_response.avgPrice")),
        extract_price(payload),
    )


def extract_executed_qty(payload: dict[str, Any]) -> float | None:
    return first_non_null(
        to_float(payload_get(payload, "executed_qty")),
        to_float(payload_get(payload, "executedQty")),
        to_float(payload_get(payload, "adapter_response.executedQty")),
        extract_qty(payload) if stringify(payload.get(
            "event_type")) == "ORDER_FILLED" else None,
    )


def extract_commission(payload: dict[str, Any]) -> float | None:
    return first_non_null(
        to_float(payload_get(payload, "metadata.commission")),
        to_float(payload_get(payload, "commission")),
        to_float(payload_get(payload, "fill_fees")),
    )


def extract_trade_id(payload: dict[str, Any]) -> str:
    value = payload_get(payload, "trade_id", "metadata.fill_trade_id")
    return stringify(value) or ""


def extract_reason(payload: dict[str, Any]) -> str:
    return stringify(payload_get(payload, "why", "reason", "metadata.reject_reason", "timeout_type")) or ""


def derive_base_chain_from_rid(rid: str | None) -> str | None:
    text = stringify(rid)
    if text is None:
        return None
    if text.startswith("aurora_"):
        return text.split(":", 1)[0]
    return None


def looks_like_entry_chain(value: str | None) -> bool:
    text = stringify(value)
    return bool(text and text.startswith("aurora_"))


def build_bounded_key(payload: dict[str, Any]) -> str | None:
    symbol = stringify(payload_get(
        payload, "symbol", "adapter_response.symbol"))
    side = normalize_side(payload_get(
        payload, "side", "adapter_response.side"))
    qty = extract_qty(payload)
    price = extract_price(payload)
    if symbol is None or not side or qty is None or price is None:
        return None
    return f"{symbol}|{side}|{qty:.8f}|{price:.8f}"


def collect_identity_pairs(payload: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key in IDENTITY_KEYS:
        for value in collect_candidate_values(payload, key):
            text = stringify(value)
            if text is None or is_magicmock_text(text):
                continue
            pairs.append((normalize_field_name(key), text))
    order_id = extract_order_id(payload)
    client_order_id = extract_client_order_id(payload)
    if order_id:
        pairs.append(("order_id", order_id))
    if client_order_id:
        pairs.append(("client_order_id", client_order_id))
    return pairs


def find_direct_timestamp(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    for key_path, nested in recursive_walk(payload):
        field_name = normalize_field_name(key_path.split(".")[-1])
        if field_name not in TIMESTAMP_FIELD_NAMES:
            continue
        candidate = try_parse_timestamp_ms(nested)
        if candidate is not None:
            if field_name in {"time", "transacttime", "workingtime", "updatetime"}:
                return candidate, f"exchange_field:{key_path}"
            return candidate, f"direct_field:{key_path}"
    return None, None


def find_embedded_timestamp(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    for key_path, nested in recursive_walk(payload):
        field_name = normalize_field_name(key_path.split(".")[-1])
        if not field_name.endswith(("rid", "id", "key")):
            continue
        candidate = extract_embedded_epoch_ms(nested)
        if candidate is not None:
            return candidate, f"embedded_id:{key_path}"
    return None, None


def build_cross_log_indices(root: Path) -> tuple[dict[tuple[str, str], list[tuple[int, str, int]]], dict[str, list[tuple[int, str, int]]]]:
    exact_index: dict[tuple[str, str],
                      list[tuple[int, str, int]]] = defaultdict(list)
    bounded_index: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    sources = [
        root / "logs" / "order_log_v1.jsonl",
        root / "logs" / "trade_lifecycle.jsonl",
        root / "logs" / "shadow_critical_event_journal_v1.jsonl",
        root / "logs" / "regime_confidence_audit_v1.jsonl",
    ]
    for path in sources:
        if not path.exists():
            continue
        for line_no, payload in iter_jsonl(path):
            ts_ms, _ = find_direct_timestamp(payload)
            if ts_ms is None:
                continue
            for pair in collect_identity_pairs(payload):
                exact_index[pair].append((ts_ms, relative_path(path), line_no))
            bounded_key = build_bounded_key(payload)
            if bounded_key:
                bounded_index[bounded_key].append(
                    (ts_ms, relative_path(path), line_no))
    return exact_index, bounded_index


def build_db_index(root: Path) -> dict[tuple[str, str], list[tuple[int, str, int | None]]]:
    index: dict[tuple[str, str],
                list[tuple[int, str, int | None]]] = defaultdict(list)
    db_paths = sorted({*root.glob("data/*.db"), *root.glob("ops/**/*.db")})
    for db_path in db_paths:
        try:
            con = sqlite3.connect(str(db_path))
            con.row_factory = sqlite3.Row
        except sqlite3.DatabaseError:
            continue
        try:
            tables = [
                row[0]
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]
            for table in tables:
                try:
                    pragma_rows = con.execute(
                        f"PRAGMA table_info('{table}')").fetchall()
                except sqlite3.DatabaseError:
                    continue
                columns = [str(row[1]) for row in pragma_rows]
                timestamp_columns = [column for column in columns if normalize_field_name(
                    column) in TIMESTAMP_FIELD_NAMES]
                identity_columns = [column for column in columns if normalize_field_name(
                    column) in {normalize_field_name(k) for k in IDENTITY_KEYS}]
                if not timestamp_columns or not identity_columns:
                    continue
                try:
                    rows = con.execute(f"SELECT * FROM '{table}'").fetchall()
                except sqlite3.DatabaseError:
                    continue
                for row in rows:
                    ts_ms = None
                    for column in timestamp_columns:
                        ts_ms = try_parse_timestamp_ms(row[column])
                        if ts_ms is not None:
                            break
                    if ts_ms is None:
                        continue
                    for column in identity_columns:
                        text = stringify(row[column])
                        if text is None or is_magicmock_text(text):
                            continue
                        key = (normalize_field_name(column), text)
                        index[key].append(
                            (ts_ms, f"{relative_path(db_path)}#{table}", None))
        finally:
            con.close()
    return index


def recover_timestamp(
    payload: dict[str, Any],
    exact_index: dict[tuple[str, str], list[tuple[int, str, int]]],
    bounded_index: dict[str, list[tuple[int, str, int]]],
    db_index: dict[tuple[str, str], list[tuple[int, str, int | None]]],
    sequence_token: str,
) -> tuple[int | None, str, str, str | None]:
    direct_ts, direct_source = find_direct_timestamp(payload)
    if direct_ts is not None:
        quality = "direct"
        if direct_source and direct_source.startswith("exchange_field:"):
            quality = "direct"
        return direct_ts, quality, direct_source or "direct", None

    embedded_ts, embedded_source = find_embedded_timestamp(payload)
    if embedded_ts is not None:
        return embedded_ts, "embedded_id", embedded_source or "embedded_id", None

    for pair in collect_identity_pairs(payload):
        matches = exact_index.get(pair) or []
        if not matches:
            continue
        best = sorted(matches)[0]
        return best[0], "cross_log_exact", f"cross_log_exact:{pair[0]}", best[1]

    for pair in collect_identity_pairs(payload):
        matches = db_index.get(pair) or []
        if not matches:
            continue
        best = sorted(matches)[0]
        return best[0], "db_join", f"db_join:{pair[0]}", best[1]

    bounded_key = build_bounded_key(payload)
    if bounded_key:
        matches = bounded_index.get(bounded_key) or []
        if len(matches) == 1:
            best = matches[0]
            return best[0], "cross_log_bounded", "cross_log_bounded:symbol_side_qty_price", best[1]

    return None, "sequence_only", f"sequence_only:{sequence_token}", None


def load_strategy_context(root: Path) -> dict[str, Any]:
    instruments_cfg = load_yaml_file(
        root / "config" / "aurora" / "instruments.yaml") or {}
    domains_cfg = load_yaml_file(
        root / "config" / "aurora" / "domains.yaml") or {}
    aurora_cfg = load_yaml_file(
        root / "config" / "aurora" / "strategies" / "aurora.yaml") or {}
    regime_cfg = load_yaml_file(
        root / "config" / "aurora" / "regime.yaml") or {}

    instrument_map: dict[str, dict[str, Any]] = {}
    for symbol, payload in (instruments_cfg.get("instruments") or {}).items():
        execution = payload.get("execution") or {}
        instrument_map[str(symbol)] = {
            "target_leverage": to_float(execution.get("target_leverage")),
            "margin_mode": stringify(execution.get("margin_mode")) or "",
        }

    fee_context = {
        "open_fee_bps": to_float(payload_get(domains_cfg, "decision_making.low_vol_cost_floor_gate.fee.open_fee_bps")),
        "close_fee_bps": to_float(payload_get(domains_cfg, "decision_making.low_vol_cost_floor_gate.fee.close_fee_bps")),
        "fee_source": stringify(payload_get(domains_cfg, "decision_making.low_vol_cost_floor_gate.fee.fee_source")) or "",
    }

    allowed_regimes: dict[str, list[str]] = {}
    current_exit_context: dict[str, dict[str, Any]] = {}

    def walk(node: Any, ancestry: list[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_ancestry = ancestry + [str(key)]
                if str(key) in instrument_map and isinstance(value, dict):
                    allowed = value.get("allowed_regimes")
                    if isinstance(allowed, list):
                        allowed_regimes[str(key)] = [str(item)
                                                     for item in allowed]
                    exit_cfg = value.get("exit")
                    if isinstance(exit_cfg, dict):
                        current_exit_context[str(key)] = {
                            "sl_pct": to_float(exit_cfg.get("sl_pct")),
                            "tp_rr": to_float(exit_cfg.get("tp_rr")),
                            "regime_tpsl": exit_cfg.get("regime_tpsl"),
                        }
                walk(value, next_ancestry)
        elif isinstance(node, list):
            for item in node:
                walk(item, ancestry)

    walk(aurora_cfg, [])

    return {
        "instruments": instrument_map,
        "fees": fee_context,
        "allowed_regimes": allowed_regimes,
        "current_exit_context": current_exit_context,
        "regime_config": regime_cfg,
    }


def load_authority_rows(root: Path) -> tuple[list[AuthorityRow], dict[str, Any]]:
    exact_index, bounded_index = build_cross_log_indices(root)
    db_index = build_db_index(root)
    rows: list[AuthorityRow] = []
    parse_errors_by_file: Counter[str] = Counter()
    order_files = sorted(root.glob("data/order_log/*.jsonl"),
                         key=lambda path: path.name)
    for file_index, path in enumerate(order_files, start=1):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    parse_errors_by_file[relative_path(path)] += 1
                    continue
                if not isinstance(payload, dict):
                    continue
                timestamp_ms, quality, source, support = recover_timestamp(
                    payload,
                    exact_index,
                    bounded_index,
                    db_index,
                    sequence_token=f"{file_index:04d}:{line_no:08d}",
                )
                rows.append(
                    AuthorityRow(
                        source_file=relative_path(path),
                        source_line=line_no,
                        payload=payload,
                        timestamp_ms=timestamp_ms,
                        timestamp_iso=iso_utc(timestamp_ms),
                        timestamp_quality=quality,
                        timestamp_source=source,
                        timestamp_support=support,
                        sequence_token=f"{file_index:04d}:{line_no:08d}",
                    )
                )
    rows.sort(key=lambda row: (row.timestamp_ms is None,
              row.timestamp_ms or 0, row.sequence_token))
    return rows, {
        "parse_errors_by_file": dict(parse_errors_by_file),
        "cross_log_exact_keys": len(exact_index),
        "cross_log_bounded_keys": len(bounded_index),
        "db_exact_keys": len(db_index),
    }


def build_schema_inventory(rows: list[AuthorityRow], report_root: Path) -> dict[str, Any]:
    per_file: dict[str, dict[str, Any]] = {}
    aggregate_recursive_keys: set[str] = set()
    aggregate_timestamp_fields: set[str] = set()
    aggregate_identity_fields: set[str] = set()
    aggregate_business_fields: set[str] = set()
    aggregate_event_counter: Counter[str] = Counter()
    aggregate_status_counter: Counter[str] = Counter()

    for row in rows:
        bucket = per_file.setdefault(
            row.source_file,
            {
                "path": row.source_file,
                "rows": 0,
                "recursive_keys": set(),
                "event_type_counts": Counter(),
                "status_samples": set(),
                "reason_samples": set(),
                "source_fsm_samples": set(),
                "candidate_timestamp_fields": set(),
                "candidate_identity_fields": set(),
                "detected_business_fields": set(),
            },
        )
        bucket["rows"] += 1
        event_type = stringify(row.payload.get("event_type")) or ""
        if event_type:
            bucket["event_type_counts"][event_type] += 1
            aggregate_event_counter[event_type] += 1
        status = stringify(payload_get(
            row.payload, "status", "adapter_response.status"))
        if status:
            bucket["status_samples"].add(status)
            aggregate_status_counter[status] += 1
        reason = extract_reason(row.payload)
        if reason:
            bucket["reason_samples"].add(reason)
        source_fsm = stringify(row.payload.get("source_fsm"))
        if source_fsm:
            bucket["source_fsm_samples"].add(source_fsm)

        for key_path, _ in recursive_walk(row.payload):
            bucket["recursive_keys"].add(key_path)
            aggregate_recursive_keys.add(key_path)
            field_name = normalize_field_name(key_path.split(".")[-1])
            if field_name in TIMESTAMP_FIELD_NAMES:
                bucket["candidate_timestamp_fields"].add(key_path)
                aggregate_timestamp_fields.add(key_path)
            if field_name in {normalize_field_name(key) for key in IDENTITY_KEYS}:
                bucket["candidate_identity_fields"].add(key_path)
                aggregate_identity_fields.add(key_path)
            if field_name in {
                "symbol",
                "side",
                "positionside",
                "reduceonly",
                "order_type",
                "status",
                "quantity",
                "price",
                "avgprice",
                "executedqty",
                "leverage",
                "strategy_id",
                "reason",
                "source_fsm",
            }:
                bucket["detected_business_fields"].add(key_path)
                aggregate_business_fields.add(key_path)

    file_payloads = []
    for file_path, bucket in sorted(per_file.items()):
        file_payloads.append(
            {
                "path": file_path,
                "rows": bucket["rows"],
                "recursive_keys": sorted(bucket["recursive_keys"]),
                "event_type_counts": dict(sorted(bucket["event_type_counts"].items())),
                "status_samples": sorted(bucket["status_samples"]),
                "reason_samples": sorted(bucket["reason_samples"]),
                "source_fsm_samples": sorted(bucket["source_fsm_samples"]),
                "candidate_timestamp_fields": sorted(bucket["candidate_timestamp_fields"]),
                "candidate_identity_fields": sorted(bucket["candidate_identity_fields"]),
                "detected_business_fields": sorted(bucket["detected_business_fields"]),
            }
        )

    payload = {
        "files": file_payloads,
        "aggregate": {
            "rows": len(rows),
            "recursive_keys": sorted(aggregate_recursive_keys),
            "event_type_counts": dict(sorted(aggregate_event_counter.items())),
            "status_counts": dict(sorted(aggregate_status_counter.items())),
            "candidate_timestamp_fields": sorted(aggregate_timestamp_fields),
            "candidate_identity_fields": sorted(aggregate_identity_fields),
            "detected_business_fields": sorted(aggregate_business_fields),
        },
    }
    write_json(report_root / "order_log_schema_inventory.json", payload)
    return payload


def build_timestamp_recovery(rows: list[AuthorityRow], report_root: Path) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload
        out_rows.append(
            {
                "source_file": row.source_file,
                "source_line": row.source_line,
                "event_type": stringify(payload.get("event_type")) or "",
                "rid": stringify(payload.get("rid")) or "",
                "lifecycle_id": stringify(payload.get("lifecycle_id")) or "",
                "client_order_id": extract_client_order_id(payload),
                "order_id": extract_order_id(payload),
                "symbol": stringify(payload_get(payload, "symbol", "adapter_response.symbol")) or "",
                "timestamp_ms": row.timestamp_ms or "",
                "timestamp_iso": row.timestamp_iso or "",
                "timestamp_quality": row.timestamp_quality,
                "timestamp_source": row.timestamp_source,
                "timestamp_support": row.timestamp_support or "",
                "admissible_for_replay": "true" if row.timestamp_quality in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES else "false",
            }
        )
    headers = list(out_rows[0].keys()) if out_rows else [
        "source_file",
        "source_line",
        "event_type",
        "rid",
        "lifecycle_id",
        "client_order_id",
        "order_id",
        "symbol",
        "timestamp_ms",
        "timestamp_iso",
        "timestamp_quality",
        "timestamp_source",
        "timestamp_support",
        "admissible_for_replay",
    ]
    write_csv(report_root / "order_timestamp_recovery.csv", headers, out_rows)
    return out_rows


def classify_order_role(payload: dict[str, Any]) -> str:
    event_type = stringify(payload.get("event_type")) or ""
    client_order_id = extract_client_order_id(payload)
    order_kind = (stringify(payload_get(payload, "order_kind",
                  "metadata.order_kind")) or "").upper()
    bracket_type = (stringify(payload.get("bracket_type")) or "").upper()
    source_fsm = stringify(payload.get("source_fsm")) or ""
    reason = extract_reason(payload).lower()
    if order_kind == "ENTRY" or client_order_id.startswith("ENTRY-"):
        return "entry"
    if order_kind == "CLOSE" or client_order_id.startswith("CLOSE-") or source_fsm == "CloseExecutor":
        return "close"
    if bracket_type in {"SL", "TP"} or client_order_id.startswith(("SL-", "TP-")):
        return "protective"
    if event_type == "ORDER_REJECTED":
        return "rejected"
    if event_type == "ORDER_TIMEOUT":
        return "expired"
    if "soft_close" in reason or "sidecar" in reason:
        return "sidecar_soft_close"
    return "other"


def resolve_row_leverage(payload: dict[str, Any], strategy_context: dict[str, Any], entry_id: str | None = None) -> tuple[str, str]:
    explicit = first_non_null(
        stringify(payload_get(payload, "leverage",
                  "metadata.leverage", "adapter_response.leverage")),
    )
    if explicit and not is_magicmock_text(explicit):
        return explicit, "row_explicit"
    symbol = stringify(payload_get(payload, "symbol",
                       "adapter_response.symbol")) or ""
    instrument = (strategy_context.get("instruments") or {}).get(symbol) or {}
    leverage = instrument.get("target_leverage")
    if leverage is not None:
        if float(leverage).is_integer():
            return str(int(leverage)), "config_instruments"
        return str(leverage), "config_instruments"
    return "", "missing"


def resolve_margin_mode(payload: dict[str, Any], strategy_context: dict[str, Any]) -> str:
    explicit = stringify(payload_get(
        payload, "margin_mode", "metadata.margin_mode"))
    if explicit:
        return explicit
    symbol = stringify(payload_get(payload, "symbol",
                       "adapter_response.symbol")) or ""
    instrument = (strategy_context.get("instruments") or {}).get(symbol) or {}
    return stringify(instrument.get("margin_mode")) or ""


def build_normalized_orders(rows: list[AuthorityRow], strategy_context: dict[str, Any], report_root: Path) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload
        event_type = stringify(payload.get("event_type")) or ""
        if event_type not in ORDER_EVENT_TYPES:
            continue
        symbol = stringify(payload_get(payload, "symbol",
                           "adapter_response.symbol")) or ""
        side = normalize_side(payload_get(
            payload, "side", "adapter_response.side"))
        order_id = extract_order_id(payload)
        client_order_id = extract_client_order_id(payload)
        qty = extract_qty(payload)
        price = extract_price(payload)
        avg_fill_price = extract_avg_fill_price(payload)
        executed_qty = extract_executed_qty(payload)
        leverage, _ = resolve_row_leverage(payload, strategy_context)
        raw_status = stringify(payload_get(
            payload, "status", "adapter_response.status")) or ""
        status = raw_status
        if not status:
            if event_type == "ORDER_FILLED":
                status = "FILLED"
            elif event_type == "ORDER_CANCELLED":
                status = "CANCELED"
            elif event_type == "ORDER_TIMEOUT":
                status = "TIMEOUT"
        missing_fields = []
        for field_name, value in [
            ("symbol", symbol),
            ("side", side),
            ("timestamp_ms", row.timestamp_ms),
            ("order_id", order_id or client_order_id),
            ("qty", qty),
            ("price", price),
        ]:
            if value in (None, ""):
                missing_fields.append(field_name)
        if is_magicmock_text(order_id) or is_magicmock_text(client_order_id):
            missing_fields.append("identity_magicmock")
        confidence = "high"
        if row.timestamp_quality == "cross_log_bounded" or missing_fields:
            confidence = "medium"
        if row.timestamp_quality not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES:
            confidence = "low"
        normalized_rows.append(
            {
                "source_file": row.source_file,
                "source_line": row.source_line,
                "timestamp_ms": row.timestamp_ms or "",
                "timestamp_iso": row.timestamp_iso or "",
                "timestamp_quality": row.timestamp_quality,
                "symbol": symbol,
                "side": side,
                "position_side": stringify(payload_get(payload, "positionSide", "adapter_response.positionSide")) or "",
                "reduce_only": normalize_bool(payload_get(payload, "reduceOnly", "adapter_response.reduceOnly", "metadata.reduce_only")),
                "order_type": stringify(payload_get(payload, "order_type", "adapter_response.type", "metadata.order_type")) or "",
                "status": status,
                "exchange_order_id": order_id,
                "client_order_id": client_order_id,
                "idempotent_key": stringify(payload_get(payload, "idempotent_key", "metadata.idempotent_key")) or "",
                "rid": stringify(payload.get("rid")) or "",
                "lifecycle_id": stringify(payload.get("lifecycle_id")) or "",
                "trade_id": extract_trade_id(payload),
                "strategy_id": stringify(payload.get("strategy_id")) or "",
                "qty": qty if qty is not None else "",
                "price": price if price is not None else "",
                "avg_fill_price": avg_fill_price if avg_fill_price is not None else "",
                "executed_qty": executed_qty if executed_qty is not None else "",
                "leverage": leverage,
                "margin_mode": resolve_margin_mode(payload, strategy_context),
                "reason": extract_reason(payload),
                "raw_event_type": event_type,
                "raw_status": raw_status,
                "confidence": confidence,
                "missing_fields": "|".join(sorted(set(missing_fields))),
                "order_role": classify_order_role(payload),
            }
        )
    headers = list(normalized_rows[0].keys()) if normalized_rows else []
    write_csv(report_root / "normalized_exchange_orders.csv",
              headers, normalized_rows)
    return normalized_rows


def infer_entry_id_from_payload(
    payload: dict[str, Any],
    reservation_to_entry: dict[str, str],
    close_client_to_entry: dict[str, str],
    close_order_to_entry: dict[str, str],
) -> str | None:
    event_type = stringify(payload.get("event_type")) or ""
    role = classify_order_role(payload)
    rid = stringify(payload.get("rid"))
    lifecycle_id = stringify(payload.get("lifecycle_id"))
    client_order_id = extract_client_order_id(payload)
    order_id = extract_order_id(payload)

    if event_type == "ORDER_INTENT" and stringify(payload.get("source_fsm")) == "DecisionMaking":
        return rid

    if role == "entry":
        if event_type == "ORDER_FILLED" and looks_like_entry_chain(lifecycle_id):
            return lifecycle_id
        if looks_like_entry_chain(rid):
            return rid
        if looks_like_entry_chain(lifecycle_id):
            return lifecycle_id
        if client_order_id.startswith("ENTRY-"):
            return lifecycle_id or rid or client_order_id

    if event_type == "POSITION_CLOSED":
        if looks_like_entry_chain(lifecycle_id):
            return lifecycle_id
        base_rid = derive_base_chain_from_rid(rid)
        if base_rid:
            return base_rid
        close_client = stringify(payload_get(
            payload, "metadata.close_fill_client_order_id"))
        if close_client and close_client in close_client_to_entry:
            return close_client_to_entry[close_client]
        close_order = stringify(payload_get(
            payload, "metadata.close_fill_order_id"))
        if close_order and close_order in close_order_to_entry:
            return close_order_to_entry[close_order]

    if role == "close":
        if looks_like_entry_chain(lifecycle_id):
            return lifecycle_id
        if client_order_id and client_order_id in close_client_to_entry:
            return close_client_to_entry[client_order_id]
        if order_id and order_id in close_order_to_entry:
            return close_order_to_entry[order_id]

    if role == "protective":
        base_rid = derive_base_chain_from_rid(rid)
        if base_rid:
            return base_rid
        if looks_like_entry_chain(lifecycle_id):
            return lifecycle_id

    reservation_id = stringify(payload_get(
        payload, "reservation_id", "metadata.idempotent_key", "lifecycle_id"))
    if reservation_id and reservation_id in reservation_to_entry:
        return reservation_to_entry[reservation_id]
    return None


def aggregate_fill_rows(rows: list[AuthorityRow]) -> tuple[float | None, float | None, float]:
    total_qty = 0.0
    total_px_qty = 0.0
    total_fee = 0.0
    for row in rows:
        qty = extract_qty(row.payload)
        price = extract_price(row.payload)
        fee = extract_commission(row.payload)
        if fee is not None:
            total_fee += fee
        if qty is None or price is None:
            continue
        total_qty += qty
        total_px_qty += qty * price
    avg_price = (total_px_qty / total_qty) if total_qty > 0 else None
    return avg_price, (total_qty if total_qty > 0 else None), total_fee


def choose_best_position_closed(rows: list[AuthorityRow]) -> AuthorityRow | None:
    resolved = [
        row
        for row in rows
        if payload_get(row.payload, "realized_pnl_net") is not None or payload_get(row.payload, "fees") is not None
    ]
    candidates = resolved or rows
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (row.timestamp_ms or 0, row.source_line))[-1]


def reconstruct_entries(
    rows: list[AuthorityRow],
    strategy_context: dict[str, Any],
    report_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, EntryAggregate]]:
    groups: dict[str, EntryAggregate] = {}
    reservation_to_entry: dict[str, str] = {}
    close_client_to_entry: dict[str, str] = {}
    close_order_to_entry: dict[str, str] = {}
    pending_reservations: dict[str, list[AuthorityRow]] = defaultdict(list)

    for row in rows:
        payload = row.payload
        event_type = stringify(payload.get("event_type")) or ""
        source_fsm = stringify(payload.get("source_fsm")) or ""

        if event_type == "ORDER_INTENT" and source_fsm == "ExposureGuard":
            reservation_id = stringify(payload.get("reservation_id"))
            if reservation_id and reservation_id in reservation_to_entry:
                entry_id = reservation_to_entry[reservation_id]
                group = groups.setdefault(
                    entry_id, EntryAggregate(entry_id=entry_id))
                group.reservation_rows.append(row)
            elif reservation_id:
                pending_reservations[reservation_id].append(row)
            continue

        entry_id = infer_entry_id_from_payload(
            payload, reservation_to_entry, close_client_to_entry, close_order_to_entry)
        if entry_id is None:
            continue
        group = groups.setdefault(entry_id, EntryAggregate(entry_id=entry_id))

        symbol = stringify(payload_get(
            payload, "symbol", "adapter_response.symbol"))
        side = normalize_side(payload_get(
            payload, "side", "adapter_response.side"))
        strategy_id = stringify(payload.get("strategy_id"))
        if symbol and not group.symbol:
            group.symbol = symbol
        if side and not group.side:
            group.side = side
        if strategy_id and not group.strategy_id:
            group.strategy_id = strategy_id

        if event_type == "ORDER_INTENT" and source_fsm == "DecisionMaking":
            group.intent_rows.append(row)
            reservation_id = stringify(payload.get("lifecycle_id"))
            if reservation_id:
                reservation_to_entry[reservation_id] = entry_id
                if reservation_id in pending_reservations:
                    group.reservation_rows.extend(
                        pending_reservations.pop(reservation_id))
            continue

        role = classify_order_role(payload)
        if role == "entry":
            if event_type == "ORDER_PLACED":
                group.placed_rows.append(row)
            elif event_type == "ORDER_FILLED":
                group.entry_fill_rows.append(row)
            elif event_type == "ORDER_TIMEOUT":
                group.timeout_rows.append(row)
            elif event_type == "ORDER_CANCELLED":
                group.cancel_rows.append(row)
        elif role == "close":
            if event_type == "ORDER_FILLED":
                group.close_fill_rows.append(row)
                client_order_id = extract_client_order_id(payload)
                order_id = extract_order_id(payload)
                if client_order_id:
                    close_client_to_entry[client_order_id] = entry_id
                if order_id:
                    close_order_to_entry[order_id] = entry_id
            else:
                group.other_rows.append(row)
        elif event_type == "POSITION_CLOSED":
            group.position_closed_rows.append(row)
        elif role == "protective":
            if event_type == "ORDER_CANCELLED":
                group.cancel_rows.append(row)
            else:
                group.other_rows.append(row)
        else:
            group.other_rows.append(row)

    reconstructed_entries: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    for entry_id, group in sorted(groups.items(), key=lambda item: item[0]):
        if not group.entry_fill_rows:
            for row in group.placed_rows + group.timeout_rows + group.cancel_rows + group.intent_rows + group.reservation_rows:
                unresolved_rows.append(
                    {
                        "source_file": row.source_file,
                        "source_line": row.source_line,
                        "entry_id": entry_id,
                        "rid": stringify(row.payload.get("rid")) or "",
                        "event_type": stringify(row.payload.get("event_type")) or "",
                        "symbol": group.symbol,
                        "side": group.side,
                        "reason": "entry_not_filled",
                    }
                )
            continue

        entry_fill_rows = sorted(group.entry_fill_rows, key=lambda row: (
            row.timestamp_ms or 0, row.source_line))
        entry_first = entry_fill_rows[0]
        entry_price, qty, entry_fee_sum = aggregate_fill_rows(entry_fill_rows)
        leverage_value = ""
        leverage_source = "missing"
        for candidate_row in group.reservation_rows + group.intent_rows + group.placed_rows + group.entry_fill_rows:
            leverage_value, leverage_source = resolve_row_leverage(
                candidate_row.payload, strategy_context, entry_id)
            if leverage_value:
                break

        close_fill_price, close_fill_qty, close_fee_sum = aggregate_fill_rows(
            group.close_fill_rows)
        best_position_closed = choose_best_position_closed(
            group.position_closed_rows)
        close_ts_ms = None
        close_price = None
        realized_pnl_net = None
        realized_pnl_gross = None
        fees = None
        actual_outcome_status = "OPEN"

        if best_position_closed is not None:
            close_ts_ms = best_position_closed.timestamp_ms
            close_price = first_non_null(
                to_float(payload_get(best_position_closed.payload,
                         "metadata.close_price")),
                close_fill_price,
            )
            realized_pnl_net = to_float(payload_get(
                best_position_closed.payload, "realized_pnl_net"))
            realized_pnl_gross = to_float(payload_get(
                best_position_closed.payload, "metadata.realized_pnl", "realized_pnl"))
            fees = first_non_null(to_float(payload_get(
                best_position_closed.payload, "fees")), entry_fee_sum + close_fee_sum)
            actual_outcome_status = stringify(payload_get(
                best_position_closed.payload, "close_reason", "why")) or "POSITION_CLOSED"
        elif group.close_fill_rows:
            close_last = sorted(group.close_fill_rows, key=lambda row: (
                row.timestamp_ms or 0, row.source_line))[-1]
            close_ts_ms = close_last.timestamp_ms
            close_price = close_fill_price
            fees = entry_fee_sum + close_fee_sum
            actual_outcome_status = "CLOSE_FILL_ONLY"
        elif group.cancel_rows or group.timeout_rows:
            actual_outcome_status = "OPEN_WITH_CANCEL_TIMEOUT_ARTIFACTS"

        notes = []
        if len(group.entry_fill_rows) > 1:
            notes.append("multi_fill_entry")
        if group.reservation_rows:
            notes.append("reservation_evidence_attached")
        if best_position_closed is None and group.position_closed_rows:
            notes.append("position_closed_without_resolved_pnl")
        if not leverage_value:
            notes.append("missing_leverage")

        reconstruction_confidence = "high"
        if entry_first.timestamp_quality == "cross_log_bounded" or not leverage_value or best_position_closed is None:
            reconstruction_confidence = "medium"
        if entry_first.timestamp_quality not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES:
            reconstruction_confidence = "low"

        trade_id = ""
        if best_position_closed is not None:
            trade_id = stringify(
                best_position_closed.payload.get("trade_id")) or ""
        if not trade_id:
            trade_id = extract_trade_id(entry_first.payload)

        entry_payload_source = group.entry_fill_rows[0].payload
        entry_price_source = "fill_weighted_avg"
        if entry_price is None:
            entry_price = extract_price(entry_payload_source)
            entry_price_source = "fill_price_single"

        reconstructed_entries.append(
            {
                "entry_id": entry_id,
                "symbol": group.symbol,
                "side": group.side,
                "entry_ts_ms": entry_first.timestamp_ms or "",
                "entry_time_iso": entry_first.timestamp_iso or "",
                "entry_price": entry_price if entry_price is not None else "",
                "entry_price_source": entry_price_source,
                "qty": qty if qty is not None else "",
                "leverage": leverage_value,
                "leverage_source": leverage_source,
                "strategy_id": group.strategy_id,
                "lifecycle_id": entry_id,
                "trade_id": trade_id,
                "rid": entry_id,
                "close_ts_ms": close_ts_ms or "",
                "close_price": close_price if close_price is not None else "",
                "realized_pnl_net": realized_pnl_net if realized_pnl_net is not None else "",
                "realized_pnl_gross": realized_pnl_gross if realized_pnl_gross is not None else "",
                "fees": fees if fees is not None else "",
                "actual_outcome_status": actual_outcome_status,
                "reconstruction_confidence": reconstruction_confidence,
                "timestamp_quality": entry_first.timestamp_quality,
                "notes": "|".join(notes),
            }
        )

    write_csv(
        report_root / "reconstructed_entries.csv",
        list(reconstructed_entries[0].keys()) if reconstructed_entries else [
            "entry_id",
            "symbol",
            "side",
            "entry_ts_ms",
            "entry_time_iso",
            "entry_price",
            "entry_price_source",
            "qty",
            "leverage",
            "leverage_source",
            "strategy_id",
            "lifecycle_id",
            "trade_id",
            "rid",
            "close_ts_ms",
            "close_price",
            "realized_pnl_net",
            "realized_pnl_gross",
            "fees",
            "actual_outcome_status",
            "reconstruction_confidence",
            "timestamp_quality",
            "notes",
        ],
        reconstructed_entries,
    )
    write_csv(
        report_root / "unresolved_order_rows.csv",
        list(unresolved_rows[0].keys()) if unresolved_rows else [
            "source_file",
            "source_line",
            "entry_id",
            "rid",
            "event_type",
            "symbol",
            "side",
            "reason",
        ],
        unresolved_rows,
    )
    return reconstructed_entries, unresolved_rows, groups


def scan_candle_file(path: Path) -> tuple[int | None, int | None]:
    first_ts = None
    last_ts = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ts_ms = try_parse_timestamp_ms(row.get("timestamp"))
            if ts_ms is None:
                continue
            if first_ts is None:
                first_ts = ts_ms
            last_ts = ts_ms
    return first_ts, last_ts


def build_candle_coverage(
    reconstructed_entries: list[dict[str, Any]],
    root: Path,
    report_root: Path,
    recorder_roots: Iterable[Path | str] | None = None,
) -> dict[str, Any]:
    resolved_recorder_roots = resolve_recorder_roots(root, recorder_roots)
    entries_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in reconstructed_entries:
        symbol = stringify(entry.get("symbol"))
        if symbol:
            entries_by_symbol[symbol].append(entry)

    rows: list[dict[str, Any]] = []
    strict_1m_ok = True
    usable_1m_symbols: set[str] = set()
    warmup_ms = 3 * 24 * 60 * 60 * 1000
    horizon_ms = 24 * 60 * 60 * 1000

    for symbol, symbol_entries in sorted(entries_by_symbol.items()):
        required_start = min(int(entry["entry_ts_ms"]) for entry in symbol_entries if stringify(
            entry.get("entry_ts_ms"))) - warmup_ms
        required_end = max(
            int(entry["close_ts_ms"]) if stringify(
                entry.get("close_ts_ms")) else int(entry["entry_ts_ms"]) + horizon_ms
            for entry in symbol_entries
        )
        for timeframe in (60, 180, 300, 900):
            matching_files: list[Path] = []
            for recorder_root in resolved_recorder_roots:
                if not recorder_root.exists():
                    continue
                matching_files.extend(
                    path for path in recorder_root.rglob(f"*_{timeframe}.csv") if path.name.startswith(f"{symbol}_")
                )
            available_start = None
            available_end = None
            for file_path in sorted(matching_files):
                file_start, file_end = scan_candle_file(file_path)
                if file_start is None or file_end is None:
                    continue
                if available_start is None or file_start < available_start:
                    available_start = file_start
                if available_end is None or file_end > available_end:
                    available_end = file_end

            usable = False
            coverage_pct = 0.0
            gaps = "missing_timeframe_files"
            if available_start is not None and available_end is not None:
                required_span = max(1, required_end - required_start)
                overlap = max(0, min(required_end, available_end) -
                              max(required_start, available_start))
                coverage_pct = round((overlap / required_span) * 100.0, 2)
                usable = available_start <= required_start and available_end >= required_end
                gaps = "" if usable else "range_incomplete"
            if timeframe == 60 and usable:
                usable_1m_symbols.add(symbol)
            if timeframe == 60 and not usable:
                strict_1m_ok = False
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "required_start": required_start,
                    "required_end": required_end,
                    "available_start": available_start or "",
                    "available_end": available_end or "",
                    "coverage_pct": coverage_pct,
                    "gaps": gaps,
                    "usable": "true" if usable else "false",
                }
            )

    write_csv(
        report_root / "candle_coverage_report.csv",
        [
            "symbol",
            "timeframe",
            "required_start",
            "required_end",
            "available_start",
            "available_end",
            "coverage_pct",
            "gaps",
            "usable",
        ],
        rows,
    )
    return {
        "rows": rows,
        "strict_1m_ok": strict_1m_ok,
        "usable_1m_symbols": sorted(usable_1m_symbols),
        "recorder_roots": [str(path) for path in resolved_recorder_roots],
    }


def parse_regime_labels(root: Path) -> list[str]:
    regime_types_path = root / "apps" / "reference" / \
        "core" / "types" / "regime_types.py"
    if not regime_types_path.exists():
        return [
            "TREND_UP",
            "TREND_DOWN",
            "MEAN_REVERSION",
            "HIGH_VOLATILITY",
            "LOW_VOLATILITY",
            "UNCERTAIN",
        ]
    text = regime_types_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"class\s+RegimeLabel\(.*?\):(?P<body>.*?)(?:\nclass\s|\Z)", text, re.S)
    if not match:
        return []
    labels = []
    for enum_match in re.finditer(r"^\s+([A-Z_]+)\s*=", match.group("body"), re.M):
        labels.append(enum_match.group(1))
    return labels


def build_regime_audit_index(root: Path) -> tuple[dict[str, list[tuple[int, str, float | None, str]]], dict[str, tuple[str, float | None, int]]]:
    by_symbol: dict[str, list[tuple[int, str,
                                    float | None, str]]] = defaultdict(list)
    by_rid: dict[str, tuple[str, float | None, int]] = {}
    path = root / "logs" / "regime_confidence_audit_v1.jsonl"
    if not path.exists():
        return by_symbol, by_rid
    for _, payload in iter_jsonl(path):
        symbol = stringify(payload.get("symbol")) or ""
        ts_ms = try_parse_timestamp_ms(payload_get(
            payload, "ts_ms", "bar_close_ts_ms", "event_ts_ms"))
        regime = stringify(payload_get(
            payload, "regime_used", "regime", "label")) or "UNKNOWN"
        confidence = to_float(payload_get(
            payload, "regime_confidence_used", "confidence"))
        record_type = stringify(payload.get("record_type")) or ""
        if symbol and ts_ms is not None:
            by_symbol[symbol].append((ts_ms, regime, confidence, record_type))
        rid = stringify(payload.get("rid"))
        if rid and ts_ms is not None:
            by_rid[rid] = (regime, confidence, ts_ms)
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda item: item[0])
    return by_symbol, by_rid


def nearest_regime(points: list[tuple[int, str, float | None, str]], ts_ms: int | None, max_gap_ms: int = 600_000) -> tuple[str, float | None, str]:
    if ts_ms is None or not points:
        return "UNKNOWN", None, "missing"
    arr = [item[0] for item in points]
    idx = bisect_left(arr, ts_ms)
    candidates = []
    if idx < len(points):
        candidates.append(points[idx])
    if idx > 0:
        candidates.append(points[idx - 1])
    if not candidates:
        return "UNKNOWN", None, "missing"
    best = min(candidates, key=lambda item: abs(item[0] - ts_ms))
    if abs(best[0] - ts_ms) > max_gap_ms:
        return "UNKNOWN", None, "gap_exceeded"
    return best[1], best[2], f"nearest_audit:{best[3] or 'bar_close'}"


def build_entries_with_regimes(
    reconstructed_entries: list[dict[str, Any]],
    groups: dict[str, EntryAggregate],
    strategy_context: dict[str, Any],
    root: Path,
    report_root: Path,
) -> list[dict[str, Any]]:
    regime_labels = parse_regime_labels(root)
    audit_by_symbol, audit_by_rid = build_regime_audit_index(root)
    rows: list[dict[str, Any]] = []
    direct_count = 0
    audit_count = 0
    missing_count = 0

    for entry in reconstructed_entries:
        entry_id = stringify(entry.get("entry_id")) or ""
        group = groups.get(entry_id)
        regime = "UNKNOWN"
        regime_conf = None
        regime_source = "missing"
        candidate_scores = {}
        direct_row = None
        if group is not None:
            if group.intent_rows:
                direct_row = sorted(group.intent_rows, key=lambda row: (
                    row.timestamp_ms or 0, row.source_line))[0]
            elif group.placed_rows:
                direct_row = sorted(group.placed_rows, key=lambda row: (
                    row.timestamp_ms or 0, row.source_line))[0]

        if direct_row is not None:
            regime = stringify(payload_get(
                direct_row.payload, "regime")) or "UNKNOWN"
            regime_conf = to_float(payload_get(
                direct_row.payload, "regime_confidence"))
            regime_source = "authority_order_log_direct"
            direct_count += 1
            if regime_conf is not None:
                candidate_scores[regime] = regime_conf
        elif entry_id in audit_by_rid:
            regime, regime_conf, _ = audit_by_rid[entry_id]
            regime_source = "regime_audit_exact_rid"
            audit_count += 1
            if regime_conf is not None:
                candidate_scores[regime] = regime_conf
        else:
            regime, regime_conf, regime_source = nearest_regime(
                audit_by_symbol.get(stringify(entry.get("symbol")) or "", []),
                to_int(entry.get("entry_ts_ms")),
            )
            if regime_source.startswith("nearest_audit"):
                audit_count += 1
                if regime_conf is not None:
                    candidate_scores[regime] = regime_conf
            else:
                missing_count += 1

        allowed = (strategy_context.get("allowed_regimes") or {}).get(
            stringify(entry.get("symbol")) or "") or []
        allowed_current = "" if not allowed else (
            "true" if regime in allowed else "false")
        disabled_flag = "" if not allowed else (
            "false" if regime in allowed else "true")

        row = dict(entry)
        row.update(
            {
                "regime_at_entry": regime,
                "regime_confidence_at_entry": regime_conf if regime_conf is not None else "",
                "regime_source": regime_source,
                "all_candidate_regime_scores": json.dumps(candidate_scores, ensure_ascii=False) if candidate_scores else "",
                "disabled_or_not_allowed_for_strategy": disabled_flag,
                "allowed_for_strategy_current_config": allowed_current,
            }
        )
        rows.append(row)

    headers = list(rows[0].keys()) if rows else []
    write_csv(report_root / "entries_with_regimes.csv", headers, rows)

    coverage_lines = [
        "# Regime Reconstruction Report",
        "",
        "## Recognized regimes",
    ]
    for label in regime_labels:
        coverage_lines.append(f"- {label}")
    coverage_lines.extend(
        [
            "",
            "## Coverage",
            f"- authority_order_log_direct: {direct_count}",
            f"- regime_audit_or_nearest: {audit_count}",
            f"- missing: {missing_count}",
        ]
    )
    (report_root / "regime_reconstruction_report.md").write_text(
        "\n".join(coverage_lines) + "\n", encoding="utf-8")
    return rows


def load_candles_1m(root: Path, recorder_roots: Iterable[Path | str] | None = None) -> dict[str, list[dict[str, Any]]]:
    resolved_recorder_roots = resolve_recorder_roots(root, recorder_roots)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recorder_root in resolved_recorder_roots:
        if not recorder_root.exists():
            continue
        for path in sorted(recorder_root.rglob("*_60.csv")):
            symbol = path.name.split("_", 1)[0]
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    ts_ms = try_parse_timestamp_ms(row.get("timestamp"))
                    high = to_float(row.get("high"))
                    low = to_float(row.get("low"))
                    close = to_float(row.get("close"))
                    if ts_ms is None or high is None or low is None or close is None:
                        continue
                    by_symbol[symbol].append(
                        {
                            "timestamp": ts_ms,
                            "high": high,
                            "low": low,
                            "close": close,
                        }
                    )
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda item: item["timestamp"])
    return by_symbol


def run_replay(
    root: Path,
    report_root: Path,
    entries_with_regimes: list[dict[str, Any]] | None = None,
    strategy_context: dict[str, Any] | None = None,
    recorder_roots: Iterable[Path | str] | None = None,
    coverage_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    entries = entries_with_regimes or read_csv_rows(
        report_root / "entries_with_regimes.csv")
    strategy_context = strategy_context or load_strategy_context(root)
    resolved_recorder_roots = resolve_recorder_roots(root, recorder_roots)
    coverage_result = coverage_result or build_candle_coverage(
        entries, root, report_root, resolved_recorder_roots)
    strict_1m_available = bool(coverage_result.get("strict_1m_ok"))
    candles_by_symbol = load_candles_1m(
        root, resolved_recorder_roots) if strict_1m_available else {}

    result_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    summary_by_symbol_rows: list[dict[str, Any]] = []
    summary_by_regime_rows: list[dict[str, Any]] = []
    replay_run = False

    if strict_1m_available:
        replay_run = True
        open_fee_bps = to_float((strategy_context.get(
            "fees") or {}).get("open_fee_bps")) or 0.0
        close_fee_bps = to_float((strategy_context.get(
            "fees") or {}).get("close_fee_bps")) or 0.0
        fee_model = "explicit_config_assumption"
        round_trip_fee_bps = open_fee_bps + close_fee_bps
        for entry in entries:
            timestamp_quality = stringify(entry.get("timestamp_quality")) or ""
            if timestamp_quality not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES:
                continue
            symbol = stringify(entry.get("symbol")) or ""
            candles = candles_by_symbol.get(symbol) or []
            if not candles:
                continue
            side = normalize_side(entry.get("side"))
            entry_ts_ms = to_int(entry.get("entry_ts_ms"))
            entry_price = to_float(entry.get("entry_price"))
            leverage = to_float(entry.get("leverage"))
            if entry_ts_ms is None or entry_price is None or leverage is None or leverage <= 0:
                continue
            horizon_end = to_int(entry.get("close_ts_ms")) or (
                entry_ts_ms + 24 * 60 * 60 * 1000)
            for tp_roi_pct in TP_ROI_GRID:
                for sl_roi_pct in SL_ROI_GRID:
                    tp_move_pct = tp_roi_pct / leverage
                    sl_move_pct = sl_roi_pct / leverage
                    if side == "BUY":
                        tp_price = entry_price * (1.0 + tp_move_pct / 100.0)
                        sl_price = entry_price * (1.0 - sl_move_pct / 100.0)
                    else:
                        tp_price = entry_price * (1.0 - tp_move_pct / 100.0)
                        sl_price = entry_price * (1.0 + sl_move_pct / 100.0)

                    result = "no_hit_horizon"
                    hit_ts_ms = horizon_end
                    ambiguous_intrabar = False
                    exit_price = None
                    last_close = entry_price
                    for candle in candles:
                        ts_ms = candle["timestamp"]
                        if ts_ms < entry_ts_ms:
                            continue
                        if ts_ms > horizon_end:
                            break
                        last_close = candle["close"]
                        if side == "BUY":
                            hit_tp = candle["high"] >= tp_price
                            hit_sl = candle["low"] <= sl_price
                        else:
                            hit_tp = candle["low"] <= tp_price
                            hit_sl = candle["high"] >= sl_price
                        if hit_tp and hit_sl:
                            result = "ambiguous_intrabar"
                            hit_ts_ms = ts_ms
                            exit_price = sl_price
                            ambiguous_intrabar = True
                            break
                        if hit_tp:
                            result = "tp_hit"
                            hit_ts_ms = ts_ms
                            exit_price = tp_price
                            break
                        if hit_sl:
                            result = "sl_hit"
                            hit_ts_ms = ts_ms
                            exit_price = sl_price
                            break

                    if exit_price is None:
                        if to_float(entry.get("close_price")) is not None and to_int(entry.get("close_ts_ms")) is not None:
                            result = "actual_close"
                            exit_price = to_float(entry.get("close_price"))
                            hit_ts_ms = to_int(
                                entry.get("close_ts_ms")) or horizon_end
                        else:
                            exit_price = last_close
                            result = "horizon_exit"

                    if side == "BUY":
                        gross_price_move_pct = (
                            exit_price - entry_price) / entry_price * 100.0
                    else:
                        gross_price_move_pct = (
                            entry_price - exit_price) / entry_price * 100.0
                    gross_pnl_roi_pct = gross_price_move_pct * leverage
                    fee_roi_pct = round_trip_fee_bps * leverage / 100.0
                    net_pnl_roi_pct = gross_pnl_roi_pct - fee_roi_pct
                    holding_minutes = round(
                        (hit_ts_ms - entry_ts_ms) / 60000.0, 6)

                    result_rows.append(
                        {
                            "entry_id": stringify(entry.get("entry_id")) or "",
                            "symbol": symbol,
                            "side": side,
                            "entry_ts_ms": entry_ts_ms,
                            "regime_at_entry": stringify(entry.get("regime_at_entry")) or "",
                            "leverage": leverage,
                            "tp_roi_pct": tp_roi_pct,
                            "sl_roi_pct": sl_roi_pct,
                            "tp_price": round(tp_price, 8),
                            "sl_price": round(sl_price, 8),
                            "result": result,
                            "hit_ts_ms": hit_ts_ms,
                            "hit_time_iso": iso_utc(hit_ts_ms) or "",
                            "holding_minutes": holding_minutes,
                            "gross_pnl_roi_pct": round(gross_pnl_roi_pct, 8),
                            "net_pnl_roi_pct": round(net_pnl_roi_pct, 8),
                            "fee_model": fee_model,
                            "ambiguous_intrabar": "true" if ambiguous_intrabar else "false",
                            "data_quality": "high" if timestamp_quality in HIGH_CONFIDENCE_TIMESTAMP_QUALITIES else "medium",
                        }
                    )

        grouped: dict[tuple[Any, ...],
                      list[dict[str, Any]]] = defaultdict(list)
        grouped_by_symbol: dict[tuple[Any, ...],
                                list[dict[str, Any]]] = defaultdict(list)
        grouped_by_regime: dict[tuple[Any, ...],
                                list[dict[str, Any]]] = defaultdict(list)
        for row in result_rows:
            grouped[(row["tp_roi_pct"], row["sl_roi_pct"])].append(row)
            grouped_by_symbol[(row["symbol"], row["tp_roi_pct"],
                               row["sl_roi_pct"])].append(row)
            grouped_by_regime[(row["regime_at_entry"],
                               row["tp_roi_pct"], row["sl_roi_pct"])].append(row)

        def summarize(group_key: tuple[Any, ...], rows_for_group: list[dict[str, Any]], label_names: list[str]) -> dict[str, Any]:
            net_values = [float(row["net_pnl_roi_pct"])
                          for row in rows_for_group]
            gross_profit = sum(value for value in net_values if value > 0)
            gross_loss = abs(sum(value for value in net_values if value < 0))
            trade_count = len(rows_for_group)
            wins = sum(1 for value in net_values if value > 0)
            losses = sum(1 for value in net_values if value < 0)
            ambiguous = sum(
                1 for row in rows_for_group if row["ambiguous_intrabar"] == "true")
            payload = {
                "trades_count": trade_count,
                "win_count": wins,
                "loss_count": losses,
                "ambiguous_count": ambiguous,
                "win_rate": round(wins / trade_count, 6) if trade_count else 0.0,
                "avg_net_roi": round(sum(net_values) / trade_count, 8) if trade_count else 0.0,
                "median_net_roi": round(median(net_values), 8) if trade_count else 0.0,
                "total_net_roi": round(sum(net_values), 8),
                "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else "",
                "max_loss_roi": round(min(net_values), 8) if net_values else 0.0,
                "avg_holding_minutes": round(sum(float(row["holding_minutes"]) for row in rows_for_group) / trade_count, 8) if trade_count else 0.0,
                "false_win_due_to_intrabar_ambiguity_count": ambiguous,
                "data_quality_count": json.dumps(dict(Counter(row["data_quality"] for row in rows_for_group)), ensure_ascii=False),
            }
            for name, value in zip(label_names, group_key):
                payload[name] = value
            return payload

        summary_rows = [summarize(key, value, ["tp_roi_pct", "sl_roi_pct"])
                        for key, value in sorted(grouped.items())]
        summary_by_symbol_rows = [summarize(key, value, [
                                            "symbol", "tp_roi_pct", "sl_roi_pct"]) for key, value in sorted(grouped_by_symbol.items())]
        summary_by_regime_rows = [summarize(key, value, [
                                            "regime_at_entry", "tp_roi_pct", "sl_roi_pct"]) for key, value in sorted(grouped_by_regime.items())]

    write_csv(report_root / "tp_sl_roi_scenario_results.csv",
              REPLAY_RESULT_HEADERS, result_rows)
    write_csv(
        report_root / "tp_sl_roi_scenario_summary.csv",
        [
            "tp_roi_pct",
            "sl_roi_pct",
            "trades_count",
            "win_count",
            "loss_count",
            "ambiguous_count",
            "win_rate",
            "avg_net_roi",
            "median_net_roi",
            "total_net_roi",
            "profit_factor",
            "max_loss_roi",
            "avg_holding_minutes",
            "false_win_due_to_intrabar_ambiguity_count",
            "data_quality_count",
        ],
        summary_rows,
    )
    write_csv(
        report_root / "tp_sl_roi_scenario_summary_by_symbol.csv",
        [
            "symbol",
            "tp_roi_pct",
            "sl_roi_pct",
            "trades_count",
            "win_count",
            "loss_count",
            "ambiguous_count",
            "win_rate",
            "avg_net_roi",
            "median_net_roi",
            "total_net_roi",
            "profit_factor",
            "max_loss_roi",
            "avg_holding_minutes",
            "false_win_due_to_intrabar_ambiguity_count",
            "data_quality_count",
        ],
        summary_by_symbol_rows,
    )
    write_csv(
        report_root / "tp_sl_roi_scenario_summary_by_regime.csv",
        [
            "regime_at_entry",
            "tp_roi_pct",
            "sl_roi_pct",
            "trades_count",
            "win_count",
            "loss_count",
            "ambiguous_count",
            "win_rate",
            "avg_net_roi",
            "median_net_roi",
            "total_net_roi",
            "profit_factor",
            "max_loss_roi",
            "avg_holding_minutes",
            "false_win_due_to_intrabar_ambiguity_count",
            "data_quality_count",
        ],
        summary_by_regime_rows,
    )
    return {
        "replay_run": replay_run,
        "strict_1m_available": strict_1m_available,
        "results_count": len(result_rows),
        "summary_rows": summary_rows,
        "summary_by_symbol_rows": summary_by_symbol_rows,
        "summary_by_regime_rows": summary_by_regime_rows,
        "recorder_roots": [str(path) for path in resolved_recorder_roots],
    }


def render_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " +
           " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(out)


def determine_verdict(
    reconstructed_entries: list[dict[str, Any]],
    coverage_result: dict[str, Any],
    regime_rows: list[dict[str, Any]],
    replay_result: dict[str, Any],
) -> str:
    if not reconstructed_entries:
        return "ORDER_TIMESTAMPS_INSUFFICIENT"
    if not regime_rows:
        return "REGIME_RECONSTRUCTION_INSUFFICIENT"
    if not coverage_result.get("strict_1m_ok"):
        return "CANDLE_COVERAGE_INSUFFICIENT"
    if not replay_result.get("replay_run"):
        return "SCRIPT_CREATED_BUT_REPLAY_NOT_RUN"
    medium_rows = [entry for entry in reconstructed_entries if entry.get(
        "timestamp_quality") == "cross_log_bounded"]
    return "REPLAY_COMPLETE_WITH_DATA_GAPS" if medium_rows else "REPLAY_COMPLETE_HIGH_CONFIDENCE"


def build_final_report(
    root: Path,
    report_root: Path,
    source_inventory: list[dict[str, Any]],
    schema_inventory: dict[str, Any],
    timestamp_rows: list[dict[str, Any]],
    normalized_rows: list[dict[str, Any]],
    reconstructed_entries: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    coverage_result: dict[str, Any],
    regime_rows: list[dict[str, Any]],
    replay_result: dict[str, Any],
    strategy_context: dict[str, Any],
    authority_meta: dict[str, Any],
) -> str:
    verdict = determine_verdict(
        reconstructed_entries, coverage_result, regime_rows, replay_result)
    timestamp_quality_counts = Counter(
        row["timestamp_quality"] for row in timestamp_rows)
    quality_table_rows = [
        [quality, count, "true" if quality in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES else "false"]
        for quality, count in sorted(timestamp_quality_counts.items())
    ]

    entry_orders = sum(1 for row in normalized_rows if row.get(
        "order_role") == "entry" and row.get("raw_event_type") == "ORDER_PLACED")
    protective_orders = sum(
        1 for row in normalized_rows if row.get("order_role") == "protective")
    close_orders = sum(1 for row in normalized_rows if row.get(
        "order_role") == "close" and row.get("raw_event_type") == "ORDER_PLACED")
    high_conf_entries = sum(1 for row in reconstructed_entries if row.get(
        "reconstruction_confidence") == "high")
    medium_conf_entries = sum(1 for row in reconstructed_entries if row.get(
        "reconstruction_confidence") == "medium")
    excluded_entries = sum(1 for row in reconstructed_entries if row.get(
        "timestamp_quality") not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES)

    recognized_regimes = parse_regime_labels(root)
    allowed_regimes = strategy_context.get("allowed_regimes") or {}
    current_exit_context = strategy_context.get("current_exit_context") or {}
    fee_context = strategy_context.get("fees") or {}
    current_config_lines = []
    if current_exit_context:
        for symbol, payload in sorted(current_exit_context.items()):
            current_config_lines.append(
                f"- {symbol}: sl_pct={payload.get('sl_pct')} tp_rr={payload.get('tp_rr')} regime_tpsl={'present' if payload.get('regime_tpsl') else 'missing'}"
            )
    else:
        current_config_lines.append(
            "- Current exit config could not be recovered deterministically.")
    current_config_lines.append(
        "- Current exit surface is pct/RR-based with regime multipliers, not a native ROI-on-margin TP grid, so direct one-to-one comparison to the requested 4..13 ROI grid remains partial.")

    tp_table_rows = []
    for summary_row in replay_result.get("summary_rows", [])[:15]:
        tp_table_rows.append(
            [
                summary_row.get("tp_roi_pct"),
                summary_row.get("sl_roi_pct"),
                summary_row.get("trades_count"),
                summary_row.get("win_rate"),
                summary_row.get("avg_net_roi"),
                summary_row.get("total_net_roi"),
                summary_row.get("profit_factor"),
                summary_row.get("ambiguous_count"),
            ]
        )

    if not tp_table_rows:
        tp_table_rows.append(["not_run", "not_run", 0, 0, 0, 0, "", 0])

    facts = [
        f"Authority source for normalized exchange orders was restricted to data/order_log/*.jsonl; enrichment sources were used only for joins, validation, and context.",
        f"Source inventory scanned {len(source_inventory)} paths and loaded {len(reconstructed_entries)} reconstructed opened entries from restored authority logs.",
        f"Timestamp recovery qualities observed: {dict(sorted(timestamp_quality_counts.items()))}.",
        f"Local recorder scan found strict 1m coverage status = {coverage_result.get('strict_1m_ok')}.",
        f"Recognized regime labels from code: {', '.join(recognized_regimes) if recognized_regimes else 'unavailable'}.",
        f"Explicit fee assumption recovered from config: open_fee_bps={fee_context.get('open_fee_bps')} close_fee_bps={fee_context.get('close_fee_bps')} fee_source={fee_context.get('fee_source')}.",
    ]
    inferences = [
        "Because the operator required local 1m candles as a hard gate, absence of usable 1m coverage makes TP/SL scenario replay non-authoritative and blocks the main verdict from tuning conclusions.",
        "Restored numbered order logs are sufficiently rich to reconstruct many entry and close chains directly from authority data without mutating runtime or YAML.",
        "Current config comparison is only partial because runtime exit policy is RR/pct-based and symbol/regime specific rather than expressed directly as ROI-on-margin targets.",
    ]
    assumptions = [
        "When leverage was absent on authority rows, instrument target_leverage from config/aurora/instruments.yaml was used with leverage_source=config_instruments.",
        "When fees were needed for hypothetical replay outputs, explicit config assumptions from config/aurora/domains.yaml were preferred over silent defaults.",
        "Replay outputs remain empty when strict 1m coverage is not available locally, per operator instruction.",
    ]
    unknowns = [
        "Funding remains unknown unless it is present in retained logs or downstream datasets.",
        "Some POSITION_CLOSED rows remain unresolved because close-fill truth is missing or detached from lifecycle evidence.",
        "Historical regime audit coverage can still diverge from runtime truth when retained audit rows are absent or sparse.",
    ]

    report_lines = [
        "# ORDER_RECONSTRUCTION_TP_SL_ROI_REPLAY_REPORT",
        "",
        "## Verdict",
        verdict,
        "",
        "## Problem framing",
        "This package is historical scenario replay and forensic reconstruction only. It does not change live runtime, YAML, thresholds, gates, logs, or DB state, and it does not claim production improvement from simulation alone.",
        "",
        "## FACTS",
    ]
    report_lines.extend(f"- {line}" for line in facts)
    report_lines.extend(["", "## INFERENCES"])
    report_lines.extend(f"- {line}" for line in inferences)
    report_lines.extend(["", "## ASSUMPTIONS"])
    report_lines.extend(f"- {line}" for line in assumptions)
    report_lines.extend(["", "## UNKNOWNS"])
    report_lines.extend(f"- {line}" for line in unknowns)
    report_lines.extend(
        [
            "",
            "## Source inventory",
            f"- inspected_paths: {len(source_inventory)}",
            f"- authority_order_log_files: {len(list(root.glob('data/order_log/*.jsonl')))}",
            f"- parse_errors_by_file: {json.dumps(authority_meta.get('parse_errors_by_file') or {}, ensure_ascii=False)}",
            "",
            "## Timestamp recovery",
            render_markdown_table(
                ["quality", "count", "usable_for_replay"], quality_table_rows),
            "",
            "## Reconstructed orders",
            f"- total rows parsed: {len(timestamp_rows)}",
            f"- exchange-submitted orders: {len(normalized_rows)}",
            f"- entry orders: {entry_orders}",
            f"- protective orders: {protective_orders}",
            f"- close orders: {close_orders}",
            f"- unresolved rows: {len(unresolved_rows)}",
            "",
            "## Reconstructed entries",
            f"- total entries: {len(reconstructed_entries)}",
            f"- high-confidence entries: {high_conf_entries}",
            f"- medium-confidence entries: {medium_conf_entries}",
            f"- excluded entries: {excluded_entries}",
            "",
            "## Candle coverage",
            f"- strict_local_1m_required: true",
            f"- strict_1m_ok: {coverage_result.get('strict_1m_ok')}",
            f"- usable_1m_symbols: {', '.join(coverage_result.get('usable_1m_symbols') or []) or 'none'}",
            "",
            "## Regime reconstruction",
            f"- recognized_regimes: {', '.join(recognized_regimes) if recognized_regimes else 'none'}",
            f"- entries_with_regimes: {len(regime_rows)}",
            f"- current_allowed_regimes_by_symbol: {json.dumps(allowed_regimes, ensure_ascii=False)}",
            "",
            "## TP/SL ROI scenario results",
            render_markdown_table(
                ["TP ROI", "best SL ROI", "trades", "win_rate", "avg_net_roi",
                    "total_net_roi", "profit_factor", "ambiguous"],
                tp_table_rows,
            ),
        ]
    )
    if not replay_result.get("replay_run"):
        report_lines.extend(
            [
                "",
                "Replay was not run against admissible market-path evidence because strict local 1m candle coverage was not available for the required windows.",
            ]
        )
    report_lines.extend(["", "## Current config comparison"])
    report_lines.extend(current_config_lines)
    report_lines.extend(
        [
            "",
            "State whether current TP appears too high, too low, or inconclusive.",
            "- inconclusive: strict local 1m replay gate failed, and current runtime exit surface is not expressed natively in the requested ROI grid.",
            "",
            "## Risks",
            "- timestamp reconstruction errors;",
            "- candle granularity ambiguity;",
            "- intrabar TP/SL ordering uncertainty;",
            "- fees/funding uncertainty;",
            "- reconstructed regime may differ from runtime regime;",
            "- order logs may include rejected/cancelled orders that are not positions;",
            "- ROI on margin must not be confused with raw price percent.",
            "",
            "## Recommended next step",
            "rerun with 1m candles",
        ]
    )
    final_report = "\n".join(report_lines) + "\n"
    (root / "reports" / "ORDER_RECONSTRUCTION_TP_SL_ROI_REPLAY_REPORT.md").write_text(final_report, encoding="utf-8")
    return verdict


def run_regime_reconstruction(root: Path = ROOT, report_root: Path = REPORT_ROOT) -> dict[str, Any]:
    strategy_context = load_strategy_context(root)
    authority_rows, _ = load_authority_rows(root)
    reconstructed_entries, _, groups = reconstruct_entries(
        authority_rows, strategy_context, report_root)
    regime_rows = build_entries_with_regimes(
        reconstructed_entries, groups, strategy_context, root, report_root)
    return {"entries_with_regimes": len(regime_rows)}


def run_pipeline(
    root: Path = ROOT,
    report_root: Path = REPORT_ROOT,
    source_inventory: list[dict[str, Any]] | None = None,
    recorder_roots: Iterable[Path | str] | None = None,
) -> dict[str, Any]:
    resolved_recorder_roots = resolve_recorder_roots(root, recorder_roots)
    strategy_context = load_strategy_context(root)
    authority_rows, authority_meta = load_authority_rows(root)
    schema_inventory = build_schema_inventory(authority_rows, report_root)
    timestamp_rows = build_timestamp_recovery(authority_rows, report_root)
    normalized_rows = build_normalized_orders(
        authority_rows, strategy_context, report_root)
    reconstructed_entries, unresolved_rows, groups = reconstruct_entries(
        authority_rows, strategy_context, report_root)
    coverage_result = build_candle_coverage(
        reconstructed_entries, root, report_root, resolved_recorder_roots)
    regime_rows = build_entries_with_regimes(
        reconstructed_entries, groups, strategy_context, root, report_root)
    replay_result = run_replay(
        root,
        report_root,
        regime_rows,
        strategy_context,
        resolved_recorder_roots,
        coverage_result,
    )
    verdict = build_final_report(
        root,
        report_root,
        source_inventory or [],
        schema_inventory,
        timestamp_rows,
        normalized_rows,
        reconstructed_entries,
        unresolved_rows,
        coverage_result,
        regime_rows,
        replay_result,
        strategy_context,
        authority_meta,
    )
    return {
        "verdict": verdict,
        "authority_rows": len(authority_rows),
        "normalized_orders": len(normalized_rows),
        "reconstructed_entries": len(reconstructed_entries),
        "strict_1m_ok": coverage_result.get("strict_1m_ok"),
        "replay_run": replay_result.get("replay_run"),
        "recorder_roots": [str(path) for path in resolved_recorder_roots],
    }
