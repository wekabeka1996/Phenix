from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from order_reconstruction_tp_sl_common import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "order_reconstruction_tp_sl"

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

KEY_FIELD_HINTS = {
    "rid",
    "lifecycle_id",
    "trade_id",
    "order_id",
    "client_order_id",
    "origclientorderid",
    "idempotent_key",
    "symbol",
    "side",
    "status",
    "event_type",
    "order_kind",
    "order_type",
    "source_fsm",
    "strategy_id",
}


@dataclass
class SourceInventoryRecord:
    path: str
    exists: bool
    kind: str
    size_bytes: int = 0
    line_count: int | None = None
    table_names: list[str] = field(default_factory=list)
    min_timestamp_ms: int | None = None
    max_timestamp_ms: int | None = None
    min_timestamp_iso: str | None = None
    max_timestamp_iso: str | None = None
    timestamp_fields_detected: list[str] = field(default_factory=list)
    key_fields_detected: list[str] = field(default_factory=list)
    parse_errors: int = 0
    notes: list[str] = field(default_factory=list)


def iso_utc(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def normalize_field_name(name: str) -> str:
    return str(name).strip().lower().replace("-", "_")


def iter_requested_sources(root: Path) -> list[Path]:
    requested: list[Path] = []

    explicit_files = [
        root / "logs" / "order_log_v1.jsonl",
        root / "logs" / "trade_lifecycle.jsonl",
        root / "logs" / "shadow_critical_event_journal_v1.jsonl",
        root / "logs" / "event_chain.log",
        root / "logs" / "regime_confidence_audit_v1.jsonl",
        root / "data" / "order_ledger.db",
    ]
    requested.extend(explicit_files)

    glob_patterns = [
        "data/order_log/*.jsonl",
        "logs/aurora_core.log*",
        "logs/domain_execution_position.log*",
        "logs/domain_decision_making.log*",
        "data/*.db",
        "ops/**/*.db",
        "data/recorder/**/*.csv",
    ]
    for pattern in glob_patterns:
        requested.extend(sorted(root.glob(pattern)))

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in requested:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


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
    if value is None:
        return None
    if isinstance(value, bool):
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
    if 1_000_000_000 <= candidate <= 4_102_444_800:
        return candidate * 1000
    return None


def extract_embedded_epoch_ms(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped.isdigit():
        return None
    digits = "".join(ch if ch.isdigit() else " " for ch in value)
    for token in digits.split():
        if len(token) < 13:
            continue
        for start in range(0, len(token) - 12):
            candidate = try_parse_timestamp_ms(token[start: start + 13])
            if candidate is not None:
                return candidate
    return None


def update_timestamp_bounds(record: SourceInventoryRecord, ts_ms: int | None) -> None:
    if ts_ms is None:
        return
    if record.min_timestamp_ms is None or ts_ms < record.min_timestamp_ms:
        record.min_timestamp_ms = ts_ms
    if record.max_timestamp_ms is None or ts_ms > record.max_timestamp_ms:
        record.max_timestamp_ms = ts_ms


def scan_json_like_text(path: Path, record: SourceInventoryRecord) -> None:
    timestamp_fields: set[str] = set()
    key_fields: set[str] = set()
    line_count = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line_count += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                record.parse_errors += 1
                continue

            if isinstance(payload, dict):
                for key_path, nested in recursive_walk(payload):
                    field_name = normalize_field_name(key_path.split(".")[-1])
                    if field_name in TIMESTAMP_FIELD_NAMES:
                        timestamp_fields.add(key_path)
                        update_timestamp_bounds(
                            record, try_parse_timestamp_ms(nested))
                    elif field_name in KEY_FIELD_HINTS:
                        key_fields.add(key_path)
                    else:
                        embedded = extract_embedded_epoch_ms(nested)
                        if embedded is not None and field_name.endswith(("rid", "id", "key")):
                            timestamp_fields.add(key_path)
                            update_timestamp_bounds(record, embedded)
            else:
                record.notes.append("non_object_jsonl_row_detected")

    record.line_count = line_count
    record.timestamp_fields_detected = sorted(timestamp_fields)
    record.key_fields_detected = sorted(key_fields)


def scan_csv_file(path: Path, record: SourceInventoryRecord) -> None:
    timestamp_fields: set[str] = set()
    line_count = 0

    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        normalized_to_raw = {normalize_field_name(
            name): name for name in fieldnames}
        for normalized, raw in normalized_to_raw.items():
            if normalized in TIMESTAMP_FIELD_NAMES or normalized == "datetime":
                timestamp_fields.add(raw)

        for row in reader:
            line_count += 1
            for raw_name in timestamp_fields:
                update_timestamp_bounds(
                    record, try_parse_timestamp_ms(row.get(raw_name)))

    record.line_count = line_count + \
        (1 if timestamp_fields or path.stat().st_size > 0 else 0)
    record.timestamp_fields_detected = sorted(timestamp_fields)
    record.key_fields_detected = sorted(
        raw for raw in fieldnames if normalize_field_name(raw) in KEY_FIELD_HINTS
    )


def scan_sqlite_db(path: Path, record: SourceInventoryRecord) -> None:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    timestamp_fields: set[str] = set()
    key_fields: set[str] = set()
    try:
        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        record.table_names = tables
        for table in tables:
            pragma_rows = con.execute(
                f"PRAGMA table_info('{table}')").fetchall()
            columns = [str(row[1]) for row in pragma_rows]
            for column in columns:
                normalized = normalize_field_name(column)
                qualified = f"{table}.{column}"
                if normalized in TIMESTAMP_FIELD_NAMES:
                    timestamp_fields.add(qualified)
                    query = (
                        f"SELECT MIN({column}) AS min_value, MAX({column}) AS max_value "
                        f"FROM '{table}'"
                    )
                    try:
                        min_value, max_value = con.execute(query).fetchone()
                    except sqlite3.DatabaseError:
                        record.parse_errors += 1
                        continue
                    update_timestamp_bounds(
                        record, try_parse_timestamp_ms(min_value))
                    update_timestamp_bounds(
                        record, try_parse_timestamp_ms(max_value))
                if normalized in KEY_FIELD_HINTS:
                    key_fields.add(qualified)
    finally:
        con.close()

    record.timestamp_fields_detected = sorted(timestamp_fields)
    record.key_fields_detected = sorted(key_fields)


def scan_plain_text(path: Path, record: SourceInventoryRecord) -> None:
    line_count = 0
    token_counter: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line_count += 1
            lower_line = raw_line.lower()
            for field_name in TIMESTAMP_FIELD_NAMES:
                if field_name in lower_line:
                    token_counter[field_name] += 1
            for key_name in KEY_FIELD_HINTS:
                if key_name in lower_line:
                    token_counter[key_name] += 1

    record.line_count = line_count
    record.timestamp_fields_detected = sorted(
        key for key in token_counter if key in TIMESTAMP_FIELD_NAMES
    )
    record.key_fields_detected = sorted(
        key for key in token_counter if key in KEY_FIELD_HINTS
    )


def inventory_source(path: Path) -> SourceInventoryRecord:
    exists = path.exists()
    suffix = path.suffix.lower()
    kind = "missing"
    if exists:
        if suffix == ".db":
            kind = "sqlite"
        elif suffix == ".csv":
            kind = "csv"
        elif suffix == ".jsonl":
            kind = "jsonl"
        elif suffix.startswith(".log") or path.name.endswith(".log"):
            kind = "log"
        else:
            kind = suffix.lstrip(".") or "file"

    record = SourceInventoryRecord(
        path=str(path.relative_to(ROOT).as_posix()),
        exists=exists,
        kind=kind,
        size_bytes=path.stat().st_size if exists else 0,
    )
    if not exists:
        return record

    try:
        if kind == "sqlite":
            scan_sqlite_db(path, record)
        elif kind == "csv":
            scan_csv_file(path, record)
        elif kind == "jsonl":
            scan_json_like_text(path, record)
        else:
            scan_plain_text(path, record)
    except (OSError, csv.Error, sqlite3.DatabaseError, UnicodeError) as exc:
        record.parse_errors += 1
        record.notes.append(f"scan_failed:{type(exc).__name__}")

    record.min_timestamp_iso = iso_utc(record.min_timestamp_ms)
    record.max_timestamp_iso = iso_utc(record.max_timestamp_ms)
    return record


def build_source_inventory(root: Path, report_root: Path) -> list[dict[str, Any]]:
    report_root.mkdir(parents=True, exist_ok=True)
    records = [inventory_source(path) for path in iter_requested_sources(root)]
    payload = [asdict(record) for record in records]
    out_path = report_root / "source_inventory.json"
    out_path.write_text(json.dumps(payload, indent=2,
                        ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the read-only order reconstruction and TP/SL ROI replay research package."
    )
    parser.add_argument(
        "--phase",
        choices=["inventory", "build"],
        default="build",
        help="Phase to run. 'inventory' writes only source_inventory.json, 'build' runs the full offline research package.",
    )
    parser.add_argument(
        "--report-root",
        default=str(REPORT_ROOT),
        help="Output directory for generated artifacts.",
    )
    parser.add_argument(
        "--extra-recorder-root",
        action="append",
        default=[],
        help="Additional offline recorder root(s) to search alongside data/recorder. Analysis-only; runtime recorder behavior is unchanged.",
    )
    args = parser.parse_args()

    report_root = Path(args.report_root)
    payload = build_source_inventory(ROOT, report_root)
    summary: dict[str, Any] = {
        "phase": args.phase,
        "report_root": str(report_root),
        "sources": len(payload),
    }
    if args.phase == "build":
        pipeline_summary = run_pipeline(
            ROOT,
            report_root,
            source_inventory=payload,
            recorder_roots=[ROOT / "data" / "recorder", *
                            [Path(item) for item in args.extra_recorder_root]],
        )
        summary.update(pipeline_summary)
    print(
        json.dumps(summary, ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
