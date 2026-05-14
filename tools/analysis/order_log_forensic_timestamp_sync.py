from __future__ import annotations
from collections import defaultdict
import gzip
import sys
import re
import os

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from order_reconstruction_tp_sl_common import (
    AuthorityRow,
    IDENTITY_KEYS,
    ROOT,
    TIMESTAMP_FIELD_NAMES,
    build_bounded_key,
    build_cross_log_indices,
    build_entries_with_regimes,
    build_normalized_orders,
    extract_avg_fill_price,
    extract_client_order_id,
    extract_commission,
    extract_executed_qty,
    extract_order_id,
    extract_price,
    extract_qty,
    extract_trade_id,
    find_direct_timestamp,
    load_strategy_context,
    normalize_field_name,
    normalize_side,
    payload_get,
    reconstruct_entries,
    recursive_walk,
    relative_path,
    stringify,
    to_float,
    try_parse_timestamp_ms,
    write_csv,
    write_json,
)


FORENSIC_REPORT_ROOT = ROOT / "reports" / "order_log_forensic_sync"
SYNCED_REPORT_ROOT = ROOT / "reports" / "order_reconstruction_tp_sl"
UTC = timezone.utc
VALID_TS_MIN_MS = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1000)
VALID_TS_MAX_MS_FUTURE_SLACK_MS = 2 * 24 * 60 * 60 * 1000
DB_IDENTITY_FIELDS = {
    "order_id",
    "exchange_order_id",
    "client_order_id",
    "clientorderid",
    "origclientorderid",
    "orig_client_order_id",
    "idempotent_key",
    "idempotentkey",
    "rid",
    "lifecycle_id",
    "trade_id",
}
SYMBOL_FIELD_NAMES = {"symbol"}
STATUS_FIELD_NAMES = {"status"}
QTY_FIELD_NAMES = {"quantity", "qty", "origqty", "executedqty"}
PRICE_FIELD_NAMES = {"price", "avgprice",
                     "avg_price", "stopprice", "stop_price"}


@dataclass(frozen=True)
class RawAuthorityRow:
    source_file: str
    source_line: int
    raw_line: str
    payload: dict[str, Any]
    direct_ts_ms: int | None
    direct_ts_source: str | None
    raw_json_hash: str
    sequence_token: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only forensic timestamp sync over data/order_log authority files and emit synced reconstruction artifacts."
    )
    parser.add_argument(
        "--report-root",
        default=str(FORENSIC_REPORT_ROOT),
        help="Output directory for forensic timestamp sync artifacts.",
    )
    parser.add_argument(
        "--synced-report-root",
        default=str(SYNCED_REPORT_ROOT),
        help="Output directory for synced reconstructed entries and replay-facing artifacts.",
    )
    return parser.parse_args()


def iso_utc(ts_ms: int | None) -> str:
    if ts_ms is None:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def order_log_files(root: Path) -> list[Path]:
    base = root / "data" / "order_log"
    if not base.exists():
        return []
    return sorted((path for path in base.iterdir() if path.is_file()), key=lambda path: path.name)


def collect_field_paths(payload: dict[str, Any], field_names: set[str]) -> list[str]:
    paths: set[str] = set()
    for key_path, _ in recursive_walk(payload):
        if normalize_field_name(key_path.split(".")[-1]) in field_names:
            paths.add(key_path)
    return sorted(paths)


def collect_symbols(payload: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key_path, nested in recursive_walk(payload):
        if normalize_field_name(key_path.split(".")[-1]) != "symbol":
            continue
        text = stringify(nested)
        if text:
            values.add(text.upper())
    return sorted(values)


def collect_event_types(payload: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key_path, nested in recursive_walk(payload):
        if normalize_field_name(key_path.split(".")[-1]) != "event_type":
            continue
        text = stringify(nested)
        if text:
            values.add(text)
    return sorted(values)


def collect_recursive_keys(payload: dict[str, Any]) -> list[str]:
    return sorted({key_path for key_path, _ in recursive_walk(payload)})


def extract_identity_values(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "exchange_order_id": extract_order_id(payload),
        "client_order_id": stringify(payload_get(payload, "client_order_id", "clientOrderId", "adapter_response.clientOrderId")) or "",
        "orig_client_order_id": stringify(payload_get(payload, "orig_client_order_id", "origClientOrderId", "adapter_response.origClientOrderId")) or "",
        "idempotent_key": stringify(payload_get(payload, "idempotent_key", "metadata.idempotent_key", "idempotentKey")) or "",
        "rid": stringify(payload_get(payload, "rid", "metadata.rid")) or "",
        "lifecycle_id": stringify(payload_get(payload, "lifecycle_id", "metadata.lifecycle_id")) or "",
        "trade_id": extract_trade_id(payload),
        "strategy_id": stringify(payload_get(payload, "strategy_id", "metadata.strategy_id")) or "",
    }


def raw_order_identity(payload: dict[str, Any]) -> str:
    return compact_json({key: value for key, value in extract_identity_values(payload).items() if value})


def authority_order_key(payload: dict[str, Any], raw_json_hash: str) -> str:
    identities = extract_identity_values(payload)
    for key in (
        "exchange_order_id",
        "client_order_id",
        "orig_client_order_id",
        "idempotent_key",
        "rid",
        "lifecycle_id",
        "trade_id",
    ):
        value = identities.get(key) or ""
        if value:
            return value
    return raw_json_hash[:16]


def parse_numeric_string_candidate(token: str) -> int | None:
    if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
        return int(token)
    return None


def iter_numeric_tokens(text: str) -> Iterable[str]:
    current: list[str] = []
    for char in text:
        if char.isdigit():
            current.append(char)
            continue
        if current:
            yield "".join(current)
            current = []
    if current:
        yield "".join(current)


def classify_candidate_timestamp(ts_ms: int, now_ms: int) -> str:
    if ts_ms < VALID_TS_MIN_MS:
        return "invalid_past"
    if ts_ms > now_ms + VALID_TS_MAX_MS_FUTURE_SLACK_MS:
        return "invalid_future"
    return "valid"


def timestamp_candidates_from_field(field_name: str, field_value: str, now_ms: int) -> list[dict[str, Any]]:
    text = stringify(field_value)
    if text is None:
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def add_candidate(ts_ms: int, quality_label: str, confidence: str, reason: str) -> None:
        validity = classify_candidate_timestamp(ts_ms, now_ms)
        final_quality = quality_label if validity == "valid" else validity
        key = (final_quality, ts_ms)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "field_name": field_name,
                "field_value": text,
                "parsed_ts_ms": ts_ms,
                "parsed_iso": iso_utc(ts_ms),
                "confidence": confidence,
                "reason": reason,
                "quality_label": final_quality,
            }
        )

    aurora_prefix = "aurora_"
    pps_prefix = "ppsreq:"
    if aurora_prefix in text:
        segments = text.split("_")
        for segment in segments:
            if len(segment) == 13 and segment.isdigit():
                add_candidate(int(segment), "embedded_aurora_lifecycle",
                              "medium", f"aurora lifecycle token in {field_name}")
    if pps_prefix in text:
        parts = text.split(":")
        for part in parts:
            if len(part) == 13 and part.isdigit():
                add_candidate(int(part), "embedded_pps_request",
                              "medium", f"pps request token in {field_name}")
    for token in iter_numeric_tokens(text):
        if len(token) >= 13:
            for start in range(0, len(token) - 12):
                candidate = parse_numeric_string_candidate(
                    token[start:start + 13])
                if candidate is None:
                    continue
                add_candidate(candidate, "embedded_epoch_ms", "medium",
                              f"13-digit epoch candidate in {field_name}")
        if len(token) == 10:
            candidate = parse_numeric_string_candidate(token)
            if candidate is None:
                continue
            add_candidate(candidate * 1000, "embedded_epoch_sec",
                          "medium", f"10-digit epoch candidate in {field_name}")
    return candidates


def inventory_and_parse_authority(root: Path, report_root: Path) -> tuple[list[RawAuthorityRow], list[dict[str, Any]], dict[str, Any]]:
    raw_rows: list[RawAuthorityRow] = []
    file_rows: list[dict[str, Any]] = []
    key_inventory_files: list[dict[str, Any]] = []
    aggregate_keys: set[str] = set()
    aggregate_timestamp_fields: set[str] = set()
    aggregate_identity_fields: set[str] = set()
    order_id_field_names = {
        normalize_field_name(name)
        for name in [
            *IDENTITY_KEYS,
            "exchange_order_id",
            "client_order_id",
            "clientOrderId",
            "origClientOrderId",
            "orig_client_order_id",
            "idempotentKey",
            "order_id",
        ]
    }
    now_token = 0

    for file_index, path in enumerate(order_log_files(root), start=1):
        parsed_rows = 0
        parse_errors = 0
        min_direct_ts = None
        max_direct_ts = None
        symbols: set[str] = set()
        event_types: set[str] = set()
        order_id_fields_seen: set[str] = set()
        timestamp_fields_seen: set[str] = set()
        recursive_keys: set[str] = set()

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                text = raw_line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                if not isinstance(payload, dict):
                    parse_errors += 1
                    continue
                parsed_rows += 1
                direct_ts_ms, direct_ts_source = find_direct_timestamp(payload)
                if direct_ts_ms is not None:
                    min_direct_ts = direct_ts_ms if min_direct_ts is None else min(
                        min_direct_ts, direct_ts_ms)
                    max_direct_ts = direct_ts_ms if max_direct_ts is None else max(
                        max_direct_ts, direct_ts_ms)
                symbols.update(collect_symbols(payload))
                event_types.update(collect_event_types(payload))
                for key_path, _ in recursive_walk(payload):
                    recursive_keys.add(key_path)
                    aggregate_keys.add(key_path)
                    field_name = normalize_field_name(key_path.split(".")[-1])
                    if field_name in order_id_field_names:
                        order_id_fields_seen.add(key_path)
                        aggregate_identity_fields.add(key_path)
                    if field_name in TIMESTAMP_FIELD_NAMES:
                        timestamp_fields_seen.add(key_path)
                        aggregate_timestamp_fields.add(key_path)
                now_token += 1
                raw_rows.append(
                    RawAuthorityRow(
                        source_file=relative_path(path),
                        source_line=line_no,
                        raw_line=text,
                        payload=payload,
                        direct_ts_ms=direct_ts_ms,
                        direct_ts_source=direct_ts_source,
                        raw_json_hash=hashlib.sha256(
                            text.encode("utf-8")).hexdigest(),
                        sequence_token=f"{file_index:04d}:{line_no:08d}:{now_token:08d}",
                    )
                )

        file_rows.append(
            {
                "file": relative_path(path),
                "size_bytes": path.stat().st_size,
                "line_count": sum(1 for _ in path.open("r", encoding="utf-8", errors="replace")),
                "parsed_rows": parsed_rows,
                "parse_errors": parse_errors,
                "min_direct_ts": min_direct_ts or "",
                "max_direct_ts": max_direct_ts or "",
                "symbols": "|".join(sorted(symbols)),
                "event_types": "|".join(sorted(event_types)),
                "order_id_fields_seen": "|".join(sorted(order_id_fields_seen)),
                "timestamp_fields_seen": "|".join(sorted(timestamp_fields_seen)),
            }
        )
        key_inventory_files.append(
            {
                "file": relative_path(path),
                "recursive_keys": sorted(recursive_keys),
                "order_id_fields_seen": sorted(order_id_fields_seen),
                "timestamp_fields_seen": sorted(timestamp_fields_seen),
                "symbols": sorted(symbols),
                "event_types": sorted(event_types),
            }
        )

    write_csv(
        report_root / "data_order_log_inventory.csv",
        [
            "file",
            "size_bytes",
            "line_count",
            "parsed_rows",
            "parse_errors",
            "min_direct_ts",
            "max_direct_ts",
            "symbols",
            "event_types",
            "order_id_fields_seen",
            "timestamp_fields_seen",
        ],
        file_rows,
    )
    key_inventory = {
        "files": key_inventory_files,
        "aggregate": {
            "recursive_keys": sorted(aggregate_keys),
            "timestamp_fields_seen": sorted(aggregate_timestamp_fields),
            "order_id_fields_seen": sorted(aggregate_identity_fields),
        },
    }
    write_json(report_root / "data_order_log_key_inventory.json", key_inventory)
    return raw_rows, file_rows, key_inventory


def build_authority_order_rows(raw_rows: list[RawAuthorityRow], report_root: Path) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    for raw_row in raw_rows:
        payload = raw_row.payload
        identity = extract_identity_values(payload)
        embedded_candidates: list[dict[str, Any]] = []
        for field_name in (
            "rid",
            "idempotent_key",
            "client_order_id",
            "orig_client_order_id",
            "lifecycle_id",
            "trade_id",
            "exchange_order_id",
        ):
            value = identity.get(field_name) or ""
            if not value:
                continue
            embedded_candidates.extend(
                timestamp_candidates_from_field(field_name, value, now_ms))
        row = {
            "source_file": raw_row.source_file,
            "source_line": raw_row.source_line,
            "raw_event_type": stringify(payload_get(payload, "event_type")) or "",
            "raw_status": stringify(payload_get(payload, "status", "adapter_response.status")) or "",
            "symbol": stringify(payload_get(payload, "symbol", "adapter_response.symbol")) or "",
            "side": normalize_side(payload_get(payload, "side", "adapter_response.side")),
            "position_side": stringify(payload_get(payload, "position_side", "positionSide", "adapter_response.positionSide")) or "",
            "order_type": stringify(payload_get(payload, "order_type", "type", "adapter_response.type", "adapter_response.origType")) or "",
            "reduce_only": stringify(payload_get(payload, "reduce_only", "reduceOnly", "adapter_response.reduceOnly")) or "",
            "quantity": extract_qty(payload) if extract_qty(payload) is not None else "",
            "price": extract_price(payload) if extract_price(payload) is not None else "",
            "stop_price": first_non_blank_number(payload_get(payload, "stop_price", "stopPrice", "adapter_response.stopPrice")),
            "avg_price": extract_avg_fill_price(payload) if extract_avg_fill_price(payload) is not None else "",
            "executed_qty": extract_executed_qty(payload) if extract_executed_qty(payload) is not None else "",
            "exchange_order_id": identity.get("exchange_order_id") or "",
            "client_order_id": identity.get("client_order_id") or "",
            "orig_client_order_id": identity.get("orig_client_order_id") or "",
            "idempotent_key": identity.get("idempotent_key") or "",
            "rid": identity.get("rid") or "",
            "lifecycle_id": identity.get("lifecycle_id") or "",
            "trade_id": identity.get("trade_id") or "",
            "strategy_id": identity.get("strategy_id") or "",
            "direct_ts_ms": raw_row.direct_ts_ms or "",
            "embedded_ts_candidates": compact_json(embedded_candidates),
            "raw_order_identity": raw_order_identity(payload),
            "raw_json_hash": raw_row.raw_json_hash,
        }
        out_rows.append(row)
    write_csv(
        report_root / "authority_order_rows.csv",
        list(out_rows[0].keys()) if out_rows else [
            "source_file",
            "source_line",
            "raw_event_type",
            "raw_status",
            "symbol",
            "side",
            "position_side",
            "order_type",
            "reduce_only",
            "quantity",
            "price",
            "stop_price",
            "avg_price",
            "executed_qty",
            "exchange_order_id",
            "client_order_id",
            "orig_client_order_id",
            "idempotent_key",
            "rid",
            "lifecycle_id",
            "trade_id",
            "strategy_id",
            "direct_ts_ms",
            "embedded_ts_candidates",
            "raw_order_identity",
            "raw_json_hash",
        ],
        out_rows,
    )
    return out_rows


def first_non_blank_number(value: Any) -> float | str:
    number = to_float(value)
    return number if number is not None else ""


def build_timestamp_candidates_from_ids(raw_rows: list[RawAuthorityRow], report_root: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[dict[str, Any]]]]:
    now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    rows: list[dict[str, Any]] = []
    candidates_by_row: dict[tuple[str, int],
                            list[dict[str, Any]]] = defaultdict(list)
    for raw_row in raw_rows:
        payload = raw_row.payload
        identities = extract_identity_values(payload)
        row_key = (raw_row.source_file, raw_row.source_line)
        row_candidates: list[dict[str, Any]] = []
        for field_name in (
            "rid",
            "idempotent_key",
            "client_order_id",
            "orig_client_order_id",
            "lifecycle_id",
            "trade_id",
            "exchange_order_id",
        ):
            value = identities.get(field_name) or ""
            if not value:
                continue
            row_candidates.extend(
                timestamp_candidates_from_field(field_name, value, now_ms))
        if not row_candidates:
            row_candidates.append(
                {
                    "field_name": "",
                    "field_value": "",
                    "parsed_ts_ms": "",
                    "parsed_iso": "",
                    "confidence": "missing",
                    "reason": "no embedded timestamp candidate in authority identifiers",
                    "quality_label": "missing",
                }
            )
        for candidate in row_candidates:
            candidate_row = {
                "source_file": raw_row.source_file,
                "source_line": raw_row.source_line,
                "raw_order_identity": raw_order_identity(payload),
                **candidate,
            }
            rows.append(candidate_row)
            candidates_by_row[row_key].append(candidate_row)
    write_csv(
        report_root / "timestamp_candidates_from_ids.csv",
        list(rows[0].keys()) if rows else [
            "source_file",
            "source_line",
            "raw_order_identity",
            "field_name",
            "field_value",
            "parsed_ts_ms",
            "parsed_iso",
            "confidence",
            "reason",
            "quality_label",
        ],
        rows,
    )
    return rows, candidates_by_row


def db_paths(root: Path) -> list[Path]:
    candidates = {
        *root.glob("*.db"),
        *root.glob("data/**/*.db"),
        *root.glob("ops/**/*.db"),
        *root.glob("logs/**/*.db"),
    }
    return sorted((path for path in candidates if path.is_file()), key=lambda path: path.as_posix())


def sibling_auxiliary_files(path: Path) -> tuple[list[str], list[str]]:
    wal_candidates = []
    shm_candidates = []
    for suffix in (".wal", ".db-wal"):
        candidate = path.with_name(path.name + suffix if suffix.startswith(
            ".") and not path.name.endswith(suffix) else path.name)
        if candidate.exists():
            wal_candidates.append(relative_path(candidate))
    for suffix in (".shm", ".db-shm"):
        candidate = path.with_name(path.name + suffix if suffix.startswith(
            ".") and not path.name.endswith(suffix) else path.name)
        if candidate.exists():
            shm_candidates.append(relative_path(candidate))
    return sorted(set(wal_candidates)), sorted(set(shm_candidates))


def find_first_column(columns: list[str], accepted_normalized_names: set[str]) -> str | None:
    for column in columns:
        if normalize_field_name(column) in accepted_normalized_names:
            return column
    return None


def build_db_wal_inventory_and_matches(
    root: Path,
    raw_rows: list[RawAuthorityRow],
    report_root: Path,
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    inventory_payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "databases": [],
        "wal_files": [],
        "shm_files": [],
    }
    exact_index: dict[tuple[str, str],
                      list[dict[str, Any]]] = defaultdict(list)
    bounded_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    wal_files: set[str] = set()
    shm_files: set[str] = set()

    for db_path in db_paths(root):
        wal_siblings, shm_siblings = sibling_auxiliary_files(db_path)
        wal_files.update(wal_siblings)
        shm_files.update(shm_siblings)
        db_entry: dict[str, Any] = {
            "path": relative_path(db_path),
            "wal_siblings": wal_siblings,
            "shm_siblings": shm_siblings,
            "tables": [],
        }
        try:
            con = sqlite3.connect(
                f"file:{db_path.as_posix()}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.DatabaseError as exc:
            db_entry["error"] = str(exc)
            inventory_payload["databases"].append(db_entry)
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
                except sqlite3.DatabaseError as exc:
                    db_entry["tables"].append(
                        {"name": table, "error": str(exc)})
                    continue
                columns = [str(row[1]) for row in pragma_rows]
                normalized_columns = {normalize_field_name(
                    column): column for column in columns}
                timestamp_columns = [column for column in columns if normalize_field_name(
                    column) in TIMESTAMP_FIELD_NAMES]
                identity_columns = [column for column in columns if normalize_field_name(
                    column) in DB_IDENTITY_FIELDS]
                symbol_column = find_first_column(columns, SYMBOL_FIELD_NAMES)
                status_column = find_first_column(columns, STATUS_FIELD_NAMES)
                qty_column = find_first_column(columns, QTY_FIELD_NAMES)
                price_column = find_first_column(columns, PRICE_FIELD_NAMES)
                table_entry = {
                    "name": table,
                    "columns": columns,
                    "timestamp_columns": timestamp_columns,
                    "identity_columns": identity_columns,
                    "symbol_column": symbol_column or "",
                    "status_column": status_column or "",
                    "qty_column": qty_column or "",
                    "price_column": price_column or "",
                }
                db_entry["tables"].append(table_entry)
                if not timestamp_columns and not identity_columns:
                    continue
                try:
                    rows = con.execute(f"SELECT * FROM '{table}'").fetchall()
                except sqlite3.DatabaseError as exc:
                    table_entry["scan_error"] = str(exc)
                    continue
                for row in rows:
                    ts_ms = None
                    for column in timestamp_columns:
                        ts_ms = try_parse_timestamp_ms(row[column])
                        if ts_ms is not None:
                            break
                    db_status = stringify(
                        row[status_column]) if status_column else ""
                    db_symbol = stringify(row[symbol_column]).upper(
                    ) if symbol_column and stringify(row[symbol_column]) else ""
                    db_qty = to_float(row[qty_column]) if qty_column else None
                    db_price = to_float(
                        row[price_column]) if price_column else None
                    base_record = {
                        "db_path": relative_path(db_path),
                        "table": table,
                        "db_ts_ms": ts_ms or "",
                        "db_status": db_status or "",
                        "db_price": db_price if db_price is not None else "",
                        "db_qty": db_qty if db_qty is not None else "",
                        "db_symbol": db_symbol or "",
                    }
                    for column in identity_columns:
                        value = stringify(row[column])
                        if not value:
                            continue
                        exact_index[(normalize_field_name(column), value)].append(
                            {
                                **base_record,
                                "match_field": normalize_field_name(column),
                                "match_value": value,
                            }
                        )
                    if db_symbol and db_qty is not None and db_price is not None:
                        key = f"{db_symbol}|{db_qty:.8f}|{db_price:.8f}"
                        bounded_index[key].append(base_record)
        finally:
            con.close()
        inventory_payload["databases"].append(db_entry)

    inventory_payload["wal_files"] = sorted(wal_files)
    inventory_payload["shm_files"] = sorted(shm_files)
    write_json(report_root / "db_wal_inventory.json", inventory_payload)

    match_rows: list[dict[str, Any]] = []
    matches_by_row: dict[tuple[str, int], dict[str, Any]] = {}
    field_priority = [
        ("exchange_order_id", "db_exact_order_id"),
        ("client_order_id", "db_exact_client_id"),
        ("orig_client_order_id", "db_exact_client_id"),
        ("idempotent_key", "db_exact_idempotent_key"),
        ("rid", "db_exact_rid"),
        ("lifecycle_id", "db_exact_lifecycle_id"),
        ("trade_id", "db_exact_trade_id"),
    ]
    for raw_row in raw_rows:
        payload = raw_row.payload
        identities = extract_identity_values(payload)
        best_match = None
        direct_ts_ms = raw_row.direct_ts_ms
        for field_name, match_confidence in field_priority:
            value = identities.get(field_name) or ""
            if not value:
                continue
            exact_matches = exact_index.get(
                (normalize_field_name(field_name), value)) or []
            if not exact_matches:
                continue
            best_match = choose_best_timestamp_match(
                exact_matches, direct_ts_ms)
            best_match = {
                **best_match,
                "match_confidence": match_confidence,
                "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                "match_field": field_name,
                "match_value": value,
            }
            break
        if best_match is None:
            bounded_key = bounded_db_key(payload)
            bounded_matches = bounded_index.get(bounded_key) or []
            filtered_matches = filter_bounded_matches(
                bounded_matches, direct_ts_ms)
            if len(filtered_matches) == 1:
                candidate = filtered_matches[0]
                best_match = {
                    **candidate,
                    "match_confidence": "db_symbol_qty_price_bounded",
                    "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                    "match_field": "symbol_qty_price",
                    "match_value": bounded_key,
                }
        if best_match is None:
            best_match = {
                "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                "db_path": "",
                "table": "",
                "match_field": "",
                "match_value": "",
                "db_ts_ms": "",
                "db_status": "",
                "db_price": "",
                "db_qty": "",
                "db_symbol": "",
                "match_confidence": "no_match",
            }
        row_out = {
            "authority_source_file": raw_row.source_file,
            "authority_source_line": raw_row.source_line,
            **best_match,
        }
        match_rows.append(row_out)
        matches_by_row[(raw_row.source_file, raw_row.source_line)] = row_out

    write_csv(
        report_root / "db_wal_order_matches.csv",
        list(match_rows[0].keys()) if match_rows else [
            "authority_source_file",
            "authority_source_line",
            "authority_order_key",
            "db_path",
            "table",
            "match_field",
            "match_value",
            "db_ts_ms",
            "db_status",
            "db_price",
            "db_qty",
            "db_symbol",
            "match_confidence",
        ],
        match_rows,
    )
    return match_rows, matches_by_row


def bounded_db_key(payload: dict[str, Any]) -> str:
    symbol = stringify(payload_get(payload, "symbol",
                       "adapter_response.symbol")) or ""
    qty = extract_qty(payload)
    price = extract_price(payload)
    if not symbol or qty is None or price is None:
        return ""
    return f"{symbol.upper()}|{qty:.8f}|{price:.8f}"


def choose_best_timestamp_match(matches: list[dict[str, Any]], reference_ts_ms: int | None) -> dict[str, Any]:
    if not matches:
        raise ValueError("matches must not be empty")
    if reference_ts_ms is None:
        return sorted(matches, key=lambda item: (item.get("db_ts_ms") in (None, ""), item.get("db_ts_ms") or 0, item.get("db_path") or "", item.get("table") or ""))[0]
    return sorted(
        matches,
        key=lambda item: (
            item.get("db_ts_ms") in (None, ""),
            abs((item.get("db_ts_ms") or reference_ts_ms) - reference_ts_ms),
            item.get("db_ts_ms") or 0,
            item.get("db_path") or "",
            item.get("table") or "",
        ),
    )[0]


def filter_bounded_matches(matches: list[dict[str, Any]], reference_ts_ms: int | None, max_delta_ms: int = 15 * 60 * 1000) -> list[dict[str, Any]]:
    if reference_ts_ms is None:
        return []
    return [
        match
        for match in matches
        if match.get("db_ts_ms") not in (None, "") and abs(int(match["db_ts_ms"]) - reference_ts_ms) <= max_delta_ms
    ]


def build_local_log_matches(root: Path, raw_rows: list[RawAuthorityRow], report_root: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]], list[str]]:
    exact_index, bounded_index = build_cross_log_indices(root)
    inspected_log_paths = sorted(
        str(path.relative_to(root).as_posix())
        for path in {
            *root.glob("logs/order_log_v1.jsonl"),
            *root.glob("logs/trade_lifecycle.jsonl"),
            *root.glob("logs/shadow_critical_event_journal_v1.jsonl"),
            *root.glob("logs/event_chain.log"),
            *root.glob("logs/aurora_core.log*"),
            *root.glob("logs/domain_execution_position.log*"),
            *root.glob("logs/domain_decision_making.log*"),
            *root.glob("logs/order_guardian.log*"),
        }
        if path.is_file()
    )
    match_rows: list[dict[str, Any]] = []
    matches_by_row: dict[tuple[str, int], dict[str, Any]] = {}
    field_priority = [
        ("order_id", "log_exact_order_id",
         lambda payload: extract_order_id(payload)),
        ("client_order_id", "log_exact_client_id",
         lambda payload: extract_client_order_id(payload)),
        ("orig_client_order_id", "log_exact_client_id", lambda payload: stringify(payload_get(
            payload, "orig_client_order_id", "origClientOrderId", "adapter_response.origClientOrderId")) or ""),
        ("idempotent_key", "log_exact_idempotent_key", lambda payload: stringify(payload_get(
            payload, "idempotent_key", "metadata.idempotent_key", "idempotentKey")) or ""),
        ("rid", "log_exact_rid", lambda payload: stringify(
            payload_get(payload, "rid", "metadata.rid")) or ""),
        ("lifecycle_id", "log_exact_lifecycle", lambda payload: stringify(
            payload_get(payload, "lifecycle_id", "metadata.lifecycle_id")) or ""),
        ("trade_id", "log_exact_trade_id",
         lambda payload: extract_trade_id(payload)),
    ]
    for raw_row in raw_rows:
        payload = raw_row.payload
        reference_ts_ms = raw_row.direct_ts_ms
        best_match = None
        for field_name, match_method, getter in field_priority:
            value = getter(payload)
            if not value:
                continue
            candidates = exact_index.get(
                (normalize_field_name(field_name), value)) or []
            if not candidates:
                continue
            ts_ms, path, line_no = choose_best_log_match(
                candidates, reference_ts_ms)
            best_match = {
                "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                "log_path": path,
                "log_line": line_no,
                "match_field": field_name,
                "match_value": value,
                "log_ts_ms": ts_ms,
                "match_method": match_method,
                "match_confidence": "high",
            }
            break
        if best_match is None:
            bounded_key = build_bounded_key(payload) or ""
            candidates = bounded_index.get(bounded_key) or []
            filtered = [candidate for candidate in candidates if reference_ts_ms is not None and abs(
                candidate[0] - reference_ts_ms) <= 15 * 60 * 1000]
            if len(filtered) == 1:
                ts_ms, path, line_no = filtered[0]
                best_match = {
                    "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                    "log_path": path,
                    "log_line": line_no,
                    "match_field": "symbol_side_qty_price",
                    "match_value": bounded_key,
                    "log_ts_ms": ts_ms,
                    "match_method": "log_bounded_symbol_price_qty",
                    "match_confidence": "medium",
                }
        if best_match is None:
            best_match = {
                "authority_order_key": authority_order_key(payload, raw_row.raw_json_hash),
                "log_path": "",
                "log_line": "",
                "match_field": "",
                "match_value": "",
                "log_ts_ms": "",
                "match_method": "no_match",
                "match_confidence": "missing",
            }
        row_out = {
            "authority_source_file": raw_row.source_file,
            "authority_source_line": raw_row.source_line,
            **best_match,
        }
        match_rows.append(row_out)
        matches_by_row[(raw_row.source_file, raw_row.source_line)] = row_out

    write_csv(
        report_root / "local_log_order_matches.csv",
        list(match_rows[0].keys()) if match_rows else [
            "authority_source_file",
            "authority_source_line",
            "authority_order_key",
            "log_path",
            "log_line",
            "match_field",
            "match_value",
            "log_ts_ms",
            "match_method",
            "match_confidence",
        ],
        match_rows,
    )
    return match_rows, matches_by_row, inspected_log_paths


def choose_best_log_match(matches: list[tuple[int, str, int]], reference_ts_ms: int | None) -> tuple[int, str, int]:
    if reference_ts_ms is None:
        return sorted(matches)[0]
    return sorted(matches, key=lambda item: (abs(item[0] - reference_ts_ms), item[0], item[1], item[2]))[0]


def choose_best_embedded_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("quality_label") in {
            "embedded_aurora_lifecycle",
            "embedded_pps_request",
            "embedded_epoch_ms",
            "embedded_epoch_sec",
        }
    ]
    if not valid_candidates:
        return None
    priority = {
        "embedded_aurora_lifecycle": 0,
        "embedded_pps_request": 1,
        "embedded_epoch_ms": 2,
        "embedded_epoch_sec": 3,
    }
    return sorted(valid_candidates, key=lambda item: (priority.get(item["quality_label"], 99), item.get("parsed_ts_ms") or 0))[0]


def final_timestamp_assignment(
    raw_rows: list[RawAuthorityRow],
    id_candidates_by_row: dict[tuple[str, int], list[dict[str, Any]]],
    db_matches_by_row: dict[tuple[str, int], dict[str, Any]],
    log_matches_by_row: dict[tuple[str, int], dict[str, Any]],
    report_root: Path,
) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        payload = raw_row.payload
        row_key = (raw_row.source_file, raw_row.source_line)
        db_match = db_matches_by_row.get(row_key) or {}
        log_match = log_matches_by_row.get(row_key) or {}
        embedded_candidate = choose_best_embedded_candidate(
            id_candidates_by_row.get(row_key) or [])

        recovered_ts_ms: int | None = None
        recovered_source = ""
        timestamp_quality = "missing"
        match_confidence = "missing"
        join_source = ""
        missing_reason = ""
        pipeline_timestamp_quality = "sequence_only"

        if raw_row.direct_ts_ms is not None:
            recovered_ts_ms = raw_row.direct_ts_ms
            recovered_source = raw_row.direct_ts_source or "direct_field"
            timestamp_quality = "high"
            match_confidence = "high"
            join_source = "authority_row"
            pipeline_timestamp_quality = "direct"
        elif (db_match.get("match_confidence") or "").startswith("db_exact") and db_match.get("db_ts_ms") not in (None, ""):
            recovered_ts_ms = int(db_match["db_ts_ms"])
            recovered_source = str(db_match.get(
                "match_confidence") or "db_join")
            timestamp_quality = "high"
            match_confidence = "high"
            join_source = f"{db_match.get('db_path', '')}#{db_match.get('table', '')}"
            pipeline_timestamp_quality = "db_join"
        elif (log_match.get("match_method") or "").startswith("log_exact") and log_match.get("log_ts_ms") not in (None, ""):
            recovered_ts_ms = int(log_match["log_ts_ms"])
            recovered_source = str(log_match.get(
                "match_method") or "cross_log_exact")
            timestamp_quality = "high"
            match_confidence = "high"
            join_source = f"{log_match.get('log_path', '')}:{log_match.get('log_line', '')}"
            pipeline_timestamp_quality = "cross_log_exact"
        elif embedded_candidate is not None and embedded_candidate.get("parsed_ts_ms") not in (None, ""):
            recovered_ts_ms = int(embedded_candidate["parsed_ts_ms"])
            recovered_source = str(embedded_candidate.get(
                "quality_label") or "embedded_id")
            timestamp_quality = "medium"
            match_confidence = "medium"
            join_source = f"embedded:{embedded_candidate.get('field_name', '')}"
            pipeline_timestamp_quality = "embedded_id"
        elif db_match.get("match_confidence") == "db_symbol_qty_price_bounded" and db_match.get("db_ts_ms") not in (None, ""):
            recovered_ts_ms = int(db_match["db_ts_ms"])
            recovered_source = "db_symbol_qty_price_bounded"
            timestamp_quality = "medium"
            match_confidence = "medium"
            join_source = f"{db_match.get('db_path', '')}#{db_match.get('table', '')}"
            pipeline_timestamp_quality = "cross_log_bounded"
        elif log_match.get("match_method") == "log_bounded_symbol_price_qty" and log_match.get("log_ts_ms") not in (None, ""):
            recovered_ts_ms = int(log_match["log_ts_ms"])
            recovered_source = "log_bounded_symbol_price_qty"
            timestamp_quality = "medium"
            match_confidence = "medium"
            join_source = f"{log_match.get('log_path', '')}:{log_match.get('log_line', '')}"
            pipeline_timestamp_quality = "cross_log_bounded"
        else:
            missing_reason = "no direct/exact/embedded/bounded timestamp evidence"

        out_rows.append(
            {
                "source_file": raw_row.source_file,
                "source_line": raw_row.source_line,
                "raw_event_type": stringify(payload_get(payload, "event_type")) or "",
                "raw_status": stringify(payload_get(payload, "status", "adapter_response.status")) or "",
                "symbol": stringify(payload_get(payload, "symbol", "adapter_response.symbol")) or "",
                "side": normalize_side(payload_get(payload, "side", "adapter_response.side")),
                "position_side": stringify(payload_get(payload, "position_side", "positionSide", "adapter_response.positionSide")) or "",
                "order_type": stringify(payload_get(payload, "order_type", "type", "adapter_response.type", "adapter_response.origType")) or "",
                "reduce_only": stringify(payload_get(payload, "reduce_only", "reduceOnly", "adapter_response.reduceOnly")) or "",
                "quantity": extract_qty(payload) if extract_qty(payload) is not None else "",
                "price": extract_price(payload) if extract_price(payload) is not None else "",
                "stop_price": first_non_blank_number(payload_get(payload, "stop_price", "stopPrice", "adapter_response.stopPrice")),
                "avg_price": extract_avg_fill_price(payload) if extract_avg_fill_price(payload) is not None else "",
                "executed_qty": extract_executed_qty(payload) if extract_executed_qty(payload) is not None else "",
                "exchange_order_id": extract_order_id(payload),
                "client_order_id": stringify(payload_get(payload, "client_order_id", "clientOrderId", "adapter_response.clientOrderId")) or "",
                "orig_client_order_id": stringify(payload_get(payload, "orig_client_order_id", "origClientOrderId", "adapter_response.origClientOrderId")) or "",
                "idempotent_key": stringify(payload_get(payload, "idempotent_key", "metadata.idempotent_key", "idempotentKey")) or "",
                "rid": stringify(payload_get(payload, "rid", "metadata.rid")) or "",
                "lifecycle_id": stringify(payload_get(payload, "lifecycle_id", "metadata.lifecycle_id")) or "",
                "trade_id": extract_trade_id(payload),
                "strategy_id": stringify(payload_get(payload, "strategy_id", "metadata.strategy_id")) or "",
                "raw_order_identity": raw_order_identity(payload),
                "raw_json_hash": raw_row.raw_json_hash,
                "recovered_ts_ms": recovered_ts_ms or "",
                "recovered_time_iso": iso_utc(recovered_ts_ms),
                "timestamp_source": recovered_source,
                "timestamp_quality": timestamp_quality,
                "match_confidence": match_confidence,
                "join_source": join_source,
                "pipeline_timestamp_quality": pipeline_timestamp_quality,
                "missing_reason": missing_reason,
            }
        )
    write_csv(
        report_root / "authority_orders_with_recovered_time.csv",
        list(out_rows[0].keys()) if out_rows else [
            "source_file",
            "source_line",
            "raw_event_type",
            "raw_status",
            "symbol",
            "side",
            "position_side",
            "order_type",
            "reduce_only",
            "quantity",
            "price",
            "stop_price",
            "avg_price",
            "executed_qty",
            "exchange_order_id",
            "client_order_id",
            "orig_client_order_id",
            "idempotent_key",
            "rid",
            "lifecycle_id",
            "trade_id",
            "strategy_id",
            "raw_order_identity",
            "raw_json_hash",
            "recovered_ts_ms",
            "recovered_time_iso",
            "timestamp_source",
            "timestamp_quality",
            "match_confidence",
            "join_source",
            "pipeline_timestamp_quality",
            "missing_reason",
        ],
        out_rows,
    )
    return out_rows


def write_timestamp_recovery_summary(
    raw_rows: list[RawAuthorityRow],
    id_candidates_by_row: dict[tuple[str, int], list[dict[str, Any]]],
    db_matches_by_row: dict[tuple[str, int], dict[str, Any]],
    log_matches_by_row: dict[tuple[str, int], dict[str, Any]],
    recovered_rows: list[dict[str, Any]],
    report_root: Path,
) -> dict[str, Any]:
    rows_with_direct_ts = sum(
        1 for row in raw_rows if row.direct_ts_ms is not None)
    rows_with_embedded_ts = sum(
        1
        for candidates in id_candidates_by_row.values()
        if any(candidate.get("quality_label") in {"embedded_aurora_lifecycle", "embedded_pps_request", "embedded_epoch_ms", "embedded_epoch_sec"} for candidate in candidates)
    )
    rows_matched_db_wal = sum(1 for match in db_matches_by_row.values(
    ) if match.get("match_confidence") not in {"", "no_match"})
    rows_matched_local_logs = sum(1 for match in log_matches_by_row.values(
    ) if match.get("match_method") not in {"", "no_match"})
    high_confidence_timestamp_rows = sum(
        1 for row in recovered_rows if row.get("timestamp_quality") == "high")
    medium_confidence_timestamp_rows = sum(
        1 for row in recovered_rows if row.get("timestamp_quality") == "medium")
    unusable_timestamp_rows = sum(1 for row in recovered_rows if row.get(
        "timestamp_quality") in {"low", "missing"})
    rows_still_missing_ts = sum(
        1 for row in recovered_rows if not row.get("recovered_ts_ms"))
    source_counts = Counter(row.get("timestamp_source")
                            or "missing" for row in recovered_rows)
    summary = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "total_authority_rows": len(raw_rows),
        "rows_with_direct_ts": rows_with_direct_ts,
        "rows_with_embedded_ts": rows_with_embedded_ts,
        "rows_matched_db_wal": rows_matched_db_wal,
        "rows_matched_local_logs": rows_matched_local_logs,
        "rows_still_missing_ts": rows_still_missing_ts,
        "high_confidence_timestamp_rows": high_confidence_timestamp_rows,
        "medium_confidence_timestamp_rows": medium_confidence_timestamp_rows,
        "unusable_timestamp_rows": unusable_timestamp_rows,
        "timestamp_source_counts": dict(sorted(source_counts.items())),
    }
    write_json(report_root / "timestamp_recovery_summary.json", summary)
    return summary


def build_synced_authority_objects(recovered_rows: list[dict[str, Any]], raw_rows: list[RawAuthorityRow]) -> list[AuthorityRow]:
    payload_by_key = {(row.source_file, row.source_line)                      : row for row in raw_rows}
    synced_rows: list[AuthorityRow] = []
    for recovered in recovered_rows:
        if recovered.get("timestamp_quality") not in {"high", "medium"}:
            continue
        source_file = str(recovered["source_file"])
        source_line = int(recovered["source_line"])
        payload_row = payload_by_key[(source_file, source_line)]
        recovered_ts_ms = int(recovered["recovered_ts_ms"])
        synced_rows.append(
            AuthorityRow(
                source_file=source_file,
                source_line=source_line,
                payload=payload_row.payload,
                timestamp_ms=recovered_ts_ms,
                timestamp_iso=iso_utc(recovered_ts_ms),
                timestamp_quality=str(recovered.get(
                    "pipeline_timestamp_quality") or "direct"),
                timestamp_source=str(recovered.get(
                    "timestamp_source") or "direct_field"),
                timestamp_support=str(recovered.get(
                    "join_source") or "") or None,
                sequence_token=payload_row.sequence_token,
            )
        )
    synced_rows.sort(key=lambda row: (row.timestamp_ms is None,
                     row.timestamp_ms or 0, row.sequence_token))
    return synced_rows


def build_required_windows(entries: list[dict[str, Any]], output_path: Path) -> list[dict[str, Any]]:
    warmup_ms = 3 * 24 * 60 * 60 * 1000
    horizon_ms = 24 * 60 * 60 * 1000
    windows_by_symbol: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for entry in entries:
        symbol = stringify(entry.get("symbol")) or ""
        entry_ts_ms = try_parse_timestamp_ms(entry.get("entry_ts_ms"))
        if not symbol or entry_ts_ms is None:
            continue
        close_ts_ms = try_parse_timestamp_ms(
            entry.get("close_ts_ms")) or (entry_ts_ms + horizon_ms)
        windows_by_symbol[symbol].append(
            (entry_ts_ms - warmup_ms, close_ts_ms))
    rows: list[dict[str, Any]] = []
    for symbol, spans in sorted(windows_by_symbol.items()):
        merged: list[list[int]] = []
        for start_ms, end_ms in sorted(spans):
            if not merged or start_ms > merged[-1][1]:
                merged.append([start_ms, end_ms, 1])
            else:
                merged[-1][1] = max(merged[-1][1], end_ms)
                merged[-1][2] += 1
        for start_ms, end_ms, entries_covered in merged:
            rows.append(
                {
                    "symbol": symbol,
                    "required_start_ms": start_ms,
                    "required_start_iso": iso_utc(start_ms),
                    "required_end_ms": end_ms,
                    "required_end_iso": iso_utc(end_ms),
                    "entries_covered": entries_covered,
                    "reason": "synced_replay_window",
                }
            )
    write_csv(
        output_path,
        [
            "symbol",
            "required_start_ms",
            "required_start_iso",
            "required_end_ms",
            "required_end_iso",
            "entries_covered",
            "reason",
        ],
        rows,
    )
    return rows


def copy_contract(report_root: Path) -> Path:
    source = SYNCED_REPORT_ROOT / "recorder_1m_format_contract.json"
    target = report_root / "recorder_1m_format_contract.json"
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return target


def build_synced_reconstruction(
    root: Path,
    report_root: Path,
    synced_report_root: Path,
    recovered_rows: list[dict[str, Any]],
    raw_rows: list[RawAuthorityRow],
) -> dict[str, Any]:
    synced_authority_rows = build_synced_authority_objects(
        recovered_rows, raw_rows)
    strategy_context = load_strategy_context(root)
    normalized_rows = build_normalized_orders(
        synced_authority_rows, strategy_context, report_root)
    reconstructed_entries, unresolved_rows, groups = reconstruct_entries(
        synced_authority_rows,
        strategy_context,
        report_root,
    )
    regime_rows = build_entries_with_regimes(
        reconstructed_entries,
        groups,
        strategy_context,
        root,
        report_root,
    )
    synced_report_root.mkdir(parents=True, exist_ok=True)
    reconstructed_entries_path = synced_report_root / \
        "reconstructed_entries_from_synced_order_log.csv"
    write_csv(
        reconstructed_entries_path,
        list(reconstructed_entries[0].keys()) if reconstructed_entries else [
            "entry_id",
            "source_file",
            "source_line",
            "symbol",
            "side",
            "entry_ts_ms",
            "entry_time_iso",
            "entry_price",
            "price_source",
            "qty",
            "leverage",
            "leverage_source",
            "client_order_id",
            "exchange_order_id",
            "idempotent_key",
            "rid",
            "lifecycle_id",
            "close_ts_ms",
            "close_price",
            "realized_pnl_net",
            "timestamp_quality",
            "reconstruction_confidence",
            "excluded_reason",
        ],
        reconstructed_entries,
    )
    synced_windows_path = report_root / \
        "required_1m_candle_windows_from_synced_order_log.csv"
    windows = build_required_windows(
        reconstructed_entries, synced_windows_path)
    contract_path = copy_contract(report_root)
    high_conf_entries = sum(1 for row in reconstructed_entries if row.get(
        "reconstruction_confidence") == "high")
    medium_conf_entries = sum(1 for row in reconstructed_entries if row.get(
        "reconstruction_confidence") == "medium")
    excluded_entries = sum(1 for row in reconstructed_entries if row.get("timestamp_quality") not in {
                           "direct", "embedded_id", "db_join", "cross_log_exact", "cross_log_bounded"})
    return {
        "normalized_rows": len(normalized_rows),
        "reconstructed_entries": len(reconstructed_entries),
        "high_conf_entries": high_conf_entries,
        "medium_conf_entries": medium_conf_entries,
        "excluded_entries": excluded_entries,
        "regime_rows": len(regime_rows),
        "unresolved_rows": len(unresolved_rows),
        "synced_entries_path": str(reconstructed_entries_path),
        "synced_windows_path": str(synced_windows_path),
        "contract_path": str(contract_path),
    }


def write_run_summary(
    report_root: Path,
    inventory_rows: list[dict[str, Any]],
    timestamp_summary: dict[str, Any],
    db_match_rows: list[dict[str, Any]],
    log_match_rows: list[dict[str, Any]],
    reconstruction_summary: dict[str, Any],
    inspected_log_paths: list[str],
) -> None:
    payload = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "authority_files_accounted_for": len(inventory_rows),
        "timestamp_recovery_summary": timestamp_summary,
        "db_match_counts": dict(Counter(row.get("match_confidence") or "missing" for row in db_match_rows)),
        "local_log_match_counts": dict(Counter(row.get("match_method") or "missing" for row in log_match_rows)),
        "inspected_log_paths": inspected_log_paths,
        "reconstruction_summary": reconstruction_summary,
    }
    write_json(report_root / "order_log_timestamp_sync_run_summary.json", payload)


def main() -> int:
    args = parse_args()
    report_root = Path(args.report_root)
    synced_report_root = Path(args.synced_report_root)
    report_root.mkdir(parents=True, exist_ok=True)

    raw_rows, inventory_rows, _ = inventory_and_parse_authority(
        ROOT, report_root)
    build_authority_order_rows(raw_rows, report_root)
    _, id_candidates_by_row = build_timestamp_candidates_from_ids(
        raw_rows, report_root)
    db_match_rows, db_matches_by_row = build_db_wal_inventory_and_matches(
        ROOT, raw_rows, report_root)
    log_match_rows, log_matches_by_row, inspected_log_paths = build_local_log_matches(
        ROOT, raw_rows, report_root)
    recovered_rows = final_timestamp_assignment(
        raw_rows, id_candidates_by_row, db_matches_by_row, log_matches_by_row, report_root)
    timestamp_summary = write_timestamp_recovery_summary(
        raw_rows, id_candidates_by_row, db_matches_by_row, log_matches_by_row, recovered_rows, report_root)
    reconstruction_summary = build_synced_reconstruction(
        ROOT, report_root, synced_report_root, recovered_rows, raw_rows)
    write_run_summary(report_root, inventory_rows, timestamp_summary, db_match_rows,
                      log_match_rows, reconstruction_summary, inspected_log_paths)
    print(
        json.dumps(
            {
                "authority_files": len(inventory_rows),
                "total_authority_rows": timestamp_summary["total_authority_rows"],
                "high_confidence_timestamp_rows": timestamp_summary["high_confidence_timestamp_rows"],
                "rows_still_missing_ts": timestamp_summary["rows_still_missing_ts"],
                "reconstructed_entries": reconstruction_summary["reconstructed_entries"],
                "synced_entries_path": reconstruction_summary["synced_entries_path"],
                "synced_windows_path": reconstruction_summary["synced_windows_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())  # !/usr/bin/env python3
"""
ORDER_LOG_FORENSIC_TIMESTAMP_SYNC
Phases 1-6 + 9: Inventory, parse, timestamp recovery, DB match, log match, final assignment.
Read-only. Does not mutate runtime code or YAML.
"""


# ── Root and I/O paths ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
ORDER_LOG_DIR = ROOT / "data" / "order_log"
REPORTS_DIR = ROOT / "reports" / "order_log_forensic_sync"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Timestamp plausibility window ─────────────────────────────────────────────
# System appears active from ~2026-04 onward; allow ±30 days of slack
TS_MIN_MS = 1_700_000_000_000   # 2023-11-14 — absolute floor
TS_MAX_MS = 1_800_000_000_000   # 2027-01-14 — absolute ceiling

# 13-digit epoch ms regex
RE_13_DIGIT = re.compile(r'\b(1[6-9]\d{11})\b')
# 10-digit epoch sec regex
RE_10_DIGIT = re.compile(r'\b(1[6-9]\d{8})\b')
# aurora_SYMBOL_ts pattern
RE_AURORA_LC = re.compile(r'aurora_[A-Z]+USDT_(\d{13})')
# ppsreq:* key
RE_PPSREQ = re.compile(r'ppsreq[_:](\d{13})')
# ENTRY-hex  (no embedded ts)
RE_ENTRY_HEX = re.compile(r'^ENTRY-[0-9a-f]+$')


def ms_to_iso(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return "INVALID"


def ts_quality(ms: int | None) -> str:
    if ms is None:
        return "missing"
    if not isinstance(ms, (int, float)):
        return "invalid"
    ms = int(ms)
    if ms < TS_MIN_MS:
        return "invalid_past"
    if ms > TS_MAX_MS:
        return "invalid_future"
    return "ok"


def row_hash(raw: str) -> str:
    return hashlib.md5(raw.encode()).hexdigest()


# ==============================================================================
# PHASE 1 — Inventory data/order_log
# ==============================================================================

def phase1_inventory() -> list[dict]:
    print("\n=== PHASE 1: Inventory data/order_log ===")

    files = sorted(ORDER_LOG_DIR.iterdir(), key=lambda p: p.name)
    inventory = []
    key_inventory = {}

    for fpath in files:
        if not fpath.is_file():
            continue
        size = fpath.stat().st_size
        rows = []
        errors = 0
        symbols = set()
        event_types = set()
        order_id_fields = set()
        ts_fields = set()
        ts_values = []

        try:
            opener = gzip.open if fpath.suffix == ".gz" else open
            with opener(fpath, "rt", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        rows.append(obj)
                        et = obj.get("event_type", "")
                        event_types.add(et)
                        sym = obj.get("symbol", "")
                        if sym:
                            symbols.add(sym)
                        # collect order id fields
                        for k in ("order_id", "exchange_order_id", "client_order_id",
                                  "orig_client_order_id", "idempotent_key", "rid",
                                  "lifecycle_id", "trade_id", "fill_trade_id", "reservation_id"):
                            if k in obj and obj[k] is not None:
                                order_id_fields.add(k)
                        # collect ts fields
                        for k in ("timestamp", "ts_ms", "created_time", "update_time",
                                  "trade_time", "fill_time"):
                            if k in obj and obj[k] is not None:
                                ts_fields.add(k)
                                try:
                                    ts_values.append(int(obj[k]))
                                except Exception:
                                    pass
                        # nested key scan for unique keys

                        def collect_keys(d, prefix=""):
                            if isinstance(d, dict):
                                for k, v in d.items():
                                    full = f"{prefix}.{k}" if prefix else k
                                    key_inventory.setdefault(full, 0)
                                    key_inventory[full] += 1
                                    collect_keys(v, full)
                            elif isinstance(d, list):
                                for item in d:
                                    collect_keys(item, prefix)
                        collect_keys(obj)
                    except json.JSONDecodeError:
                        errors += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR reading {fpath.name}: {e}")

        valid_ts = [t for t in ts_values if TS_MIN_MS <= t <= TS_MAX_MS]
        inventory.append({
            "file": fpath.name,
            "size_bytes": size,
            "line_count": len(rows) + errors,
            "parsed_rows": len(rows),
            "parse_errors": errors,
            "min_direct_ts": min(valid_ts) if valid_ts else None,
            "max_direct_ts": max(valid_ts) if valid_ts else None,
            "symbols": "|".join(sorted(symbols)),
            "event_types": "|".join(sorted(event_types)),
            "order_id_fields_seen": "|".join(sorted(order_id_fields)),
            "timestamp_fields_seen": "|".join(sorted(ts_fields)),
        })
        print(
            f"  {fpath.name}: {len(rows)} rows, {errors} errors, events={sorted(event_types)}")

    # Write CSV
    inv_csv = REPORTS_DIR / "data_order_log_inventory.csv"
    with open(inv_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(
            inventory[0].keys()) if inventory else [])
        w.writeheader()
        w.writerows(inventory)
    print(f"  -> {inv_csv}")

    # Write key inventory JSON
    key_json = REPORTS_DIR / "data_order_log_key_inventory.json"
    with open(key_json, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(key_inventory.items(),
                  key=lambda x: -x[1])), f, indent=2)
    print(f"  -> {key_json}")

    return inventory


# ==============================================================================
# PHASE 2 — Parse authority order rows
# ==============================================================================

def phase2_parse_rows() -> list[dict]:
    print("\n=== PHASE 2: Parse authority order rows ===")
    files = sorted(ORDER_LOG_DIR.iterdir(), key=lambda p: p.name)

    authority_rows = []

    for fpath in files:
        if not fpath.is_file():
            continue
        opener = gzip.open if fpath.suffix == ".gz" else open
        try:
            with opener(fpath, "rt", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # direct ts candidates from top-level
                    embedded_ts = []
                    raw_str = json.dumps(obj)
                    for m in RE_13_DIGIT.finditer(raw_str):
                        cand = int(m.group(1))
                        if TS_MIN_MS <= cand <= TS_MAX_MS:
                            embedded_ts.append(cand)
                    embedded_ts_str = "|".join(str(t)
                                               for t in sorted(set(embedded_ts)))

                    # direct timestamp field
                    direct_ts = None
                    for tf in ("timestamp", "ts_ms", "created_time", "update_time",
                               "trade_time", "fill_time"):
                        v = obj.get(tf)
                        if v is not None:
                            try:
                                vi = int(v)
                                if TS_MIN_MS <= vi <= TS_MAX_MS:
                                    direct_ts = vi
                                    break
                            except Exception:
                                pass

                    # extract nested fill fields
                    meta = obj.get("metadata", {}) or {}
                    order_meta = obj.get("order_metadata", {}) or {}

                    def get_nested(obj, *keys):
                        cur = obj
                        for k in keys:
                            if isinstance(cur, dict):
                                cur = cur.get(k)
                            else:
                                return None
                        return cur

                    row = {
                        "source_file": fpath.name,
                        "source_line": lineno,
                        "raw_event_type": obj.get("event_type", ""),
                        "raw_status": obj.get("status", obj.get("order_status", "")),
                        "symbol": obj.get("symbol", ""),
                        "side": obj.get("side", ""),
                        "position_side": obj.get("position_side", obj.get("positionSide", "")),
                        "order_type": obj.get("order_type", obj.get("type", "")),
                        "reduce_only": obj.get("reduce_only", obj.get("reduceOnly", "")),
                        "quantity": obj.get("quantity", obj.get("qty", obj.get("origQty", ""))),
                        "price": obj.get("price", ""),
                        "stop_price": obj.get("stop_price", obj.get("stopPrice", "")),
                        "avg_price": obj.get("avg_price", obj.get("avgPrice", "")),
                        "executed_qty": obj.get("executed_qty", obj.get("executedQty", "")),
                        "exchange_order_id": obj.get("order_id", obj.get("exchange_order_id", "")),
                        "client_order_id": obj.get("client_order_id", obj.get("clientOrderId", "")),
                        "orig_client_order_id": obj.get("orig_client_order_id", obj.get("origClientOrderId", "")),
                        "idempotent_key": (meta.get("idempotent_key") or obj.get("idempotent_key", "")),
                        "rid": obj.get("rid", ""),
                        "lifecycle_id": obj.get("lifecycle_id", ""),
                        "trade_id": (obj.get("trade_id") or meta.get("fill_trade_id") or ""),
                        "strategy_id": obj.get("strategy_id", ""),
                        "direct_ts_ms": direct_ts,
                        "embedded_ts_candidates": embedded_ts_str,
                        "raw_json_hash": row_hash(line),
                    }
                    authority_rows.append(row)
        except Exception as e:
            print(f"  ERROR reading {fpath.name}: {e}")

    # Write CSV
    out_csv = REPORTS_DIR / "authority_order_rows.csv"
    if authority_rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(authority_rows[0].keys()))
            w.writeheader()
            w.writerows(authority_rows)
    print(f"  Total authority rows: {len(authority_rows)}")
    print(f"  -> {out_csv}")
    return authority_rows


# ==============================================================================
# PHASE 3 — Timestamp extraction from IDs
# ==============================================================================

def _extract_ts_from_str(s: str) -> list[dict]:
    """Extract timestamp candidates from a string value."""
    candidates = []
    if not s or not isinstance(s, str):
        return candidates

    # aurora_SYMBOL_ts
    for m in RE_AURORA_LC.finditer(s):
        ms = int(m.group(1))
        if TS_MIN_MS <= ms <= TS_MAX_MS:
            candidates.append({
                "parsed_ts_ms": ms,
                "parsed_iso": ms_to_iso(ms),
                "confidence": "high",
                "reason": "embedded_aurora_lifecycle",
            })

    # ppsreq:ts
    for m in RE_PPSREQ.finditer(s):
        ms = int(m.group(1))
        if TS_MIN_MS <= ms <= TS_MAX_MS:
            candidates.append({
                "parsed_ts_ms": ms,
                "parsed_iso": ms_to_iso(ms),
                "confidence": "medium",
                "reason": "embedded_pps_request",
            })

    # boot-ts pattern
    if s.startswith("boot-"):
        try:
            ms = int(s[5:])
            if TS_MIN_MS <= ms <= TS_MAX_MS:
                candidates.append({
                    "parsed_ts_ms": ms,
                    "parsed_iso": ms_to_iso(ms),
                    "confidence": "high",
                    "reason": "boot_rid",
                })
        except ValueError:
            pass

    # ENTRY-hex: no embedded ts
    if RE_ENTRY_HEX.match(s):
        return candidates  # no ts extractable

    # 13-digit epochs
    for m in RE_13_DIGIT.finditer(s):
        ms = int(m.group(1))
        if TS_MIN_MS <= ms <= TS_MAX_MS:
            # avoid double-counting aurora lifecycle already captured
            already = any(c["parsed_ts_ms"] == ms for c in candidates)
            if not already:
                candidates.append({
                    "parsed_ts_ms": ms,
                    "parsed_iso": ms_to_iso(ms),
                    "confidence": "medium",
                    "reason": "embedded_epoch_ms",
                })

    # 10-digit epochs in non-aurora context
    for m in RE_10_DIGIT.finditer(s):
        sec = int(m.group(1))
        ms = sec * 1000
        if TS_MIN_MS <= ms <= TS_MAX_MS:
            already = any(abs(c["parsed_ts_ms"] - ms)
                          < 2000 for c in candidates)
            if not already:
                candidates.append({
                    "parsed_ts_ms": ms,
                    "parsed_iso": ms_to_iso(ms),
                    "confidence": "low",
                    "reason": "embedded_epoch_sec",
                })
    return candidates


def phase3_id_timestamps(authority_rows: list[dict]) -> list[dict]:
    print("\n=== PHASE 3: Timestamp extraction from IDs ===")
    out_rows = []

    id_fields = ["rid", "idempotent_key", "client_order_id", "orig_client_order_id",
                 "lifecycle_id", "trade_id", "exchange_order_id"]

    for row in authority_rows:
        source_file = row["source_file"]
        source_line = row["source_line"]

        # First: direct timestamp already known
        if row["direct_ts_ms"]:
            out_rows.append({
                "source_file": source_file,
                "source_line": source_line,
                "field_name": "direct_ts_field",
                "field_value": str(row["direct_ts_ms"]),
                "parsed_ts_ms": row["direct_ts_ms"],
                "parsed_iso": ms_to_iso(row["direct_ts_ms"]),
                "confidence": "high",
                "reason": "direct_field",
            })
            continue

        # Otherwise scan ID fields
        found_any = False
        for fld in id_fields:
            val = row.get(fld, "")
            if not val:
                continue
            candidates = _extract_ts_from_str(str(val))
            for c in candidates:
                out_rows.append({
                    "source_file": source_file,
                    "source_line": source_line,
                    "field_name": fld,
                    "field_value": str(val)[:120],
                    **c,
                })
                found_any = True

        if not found_any:
            out_rows.append({
                "source_file": source_file,
                "source_line": source_line,
                "field_name": "none",
                "field_value": "",
                "parsed_ts_ms": None,
                "parsed_iso": None,
                "confidence": "none",
                "reason": "missing",
            })

    out_csv = REPORTS_DIR / "timestamp_candidates_from_ids.csv"
    if out_rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            w.writerows(out_rows)
    print(f"  Timestamp candidate rows: {len(out_rows)}")
    print(f"  -> {out_csv}")
    return out_rows


# ==============================================================================
# PHASE 4 — SQLite DB / WAL search
# ==============================================================================

def _find_db_files() -> list[Path]:
    dbs = []
    for pattern in ["**/*.db", "**/*.sqlite", "**/*.sqlite3"]:
        for p in ROOT.glob(pattern):
            if ".git" not in str(p) and "__pycache__" not in str(p):
                dbs.append(p)
    return dbs


def _find_wal_files() -> list[Path]:
    wals = []
    for pattern in ["**/*.wal", "ops/**/*.wal", "logs/**/*.wal", "data/**/*.wal"]:
        for p in ROOT.glob(pattern):
            wals.append(p)
    return wals


def _db_schema(conn) -> dict[str, list[str]]:
    """Return {table: [col, ...]} for all tables."""
    schema = {}
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    for t in tables:
        try:
            cursor2 = conn.execute(f"PRAGMA table_info({t})")
            cols = [r[1] for r in cursor2.fetchall()]
            schema[t] = cols
        except Exception:
            schema[t] = []
    return schema


def phase4_db_wal(authority_rows: list[dict]) -> tuple[dict, list[dict]]:
    print("\n=== PHASE 4: SQLite DB/WAL search ===")

    db_files = _find_db_files()
    wal_files = _find_wal_files()
    print(f"  DB files found: {[str(p.relative_to(ROOT)) for p in db_files]}")
    print(
        f"  WAL files found: {[str(p.relative_to(ROOT)) for p in wal_files]}")

    inv = {
        "db_files": [str(p.relative_to(ROOT)) for p in db_files],
        "wal_files": [str(p.relative_to(ROOT)) for p in wal_files],
        "db_schemas": {},
    }

    # Build lookup sets from authority rows
    exchange_ids = {str(r["exchange_order_id"])
                    for r in authority_rows if r.get("exchange_order_id")}
    client_ids = {str(r["client_order_id"])
                  for r in authority_rows if r.get("client_order_id")}
    rids = {str(r["rid"]) for r in authority_rows if r.get("rid")}
    lifecycle_ids = {str(r["lifecycle_id"])
                     for r in authority_rows if r.get("lifecycle_id")}
    idempotent_keys = {str(r["idempotent_key"])
                       for r in authority_rows if r.get("idempotent_key")}

    match_rows = []

    ORDER_LIKE_COLS = {
        "order_id", "exchange_order_id", "orderId", "client_order_id",
        "clientOrderId", "orig_client_order_id", "origClientOrderId",
        "idempotent_key", "rid", "lifecycle_id", "trade_id",
        "symbol", "price", "qty", "quantity", "side", "status",
        "created_at", "updated_at", "timestamp", "ts_ms", "time",
        "realized_pnl", "commission", "avg_price", "avgPrice",
    }

    TS_COLS = {"created_at", "updated_at", "timestamp", "ts_ms", "time",
               "trade_time", "fill_time", "update_time", "transact_time"}

    for db_path in db_files:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            schema = _db_schema(conn)
            inv["db_schemas"][str(db_path.relative_to(ROOT))] = schema

            for table, cols in schema.items():
                col_set = set(cols)
                search_cols = col_set & ORDER_LIKE_COLS
                if not search_cols:
                    continue

                ts_col = next((c for c in cols if c in TS_COLS), None)

                # Search for matching authority IDs
                for col in search_cols:
                    if col in ("symbol", "price", "qty", "quantity", "side",
                               "status", "realized_pnl", "commission"):
                        continue  # skip non-ID columns for exact search
                    all_vals = set()
                    if col in {"order_id", "exchange_order_id", "orderId"}:
                        all_vals = exchange_ids
                    elif col in {"client_order_id", "clientOrderId"}:
                        all_vals = client_ids
                    elif col in {"orig_client_order_id", "origClientOrderId"}:
                        all_vals = client_ids
                    elif col == "idempotent_key":
                        all_vals = idempotent_keys
                    elif col == "rid":
                        all_vals = rids
                    elif col == "lifecycle_id":
                        all_vals = lifecycle_ids
                    else:
                        continue

                    if not all_vals:
                        continue

                    for val in all_vals:
                        if not val or val == "None":
                            continue
                        try:
                            cursor = conn.execute(
                                f'SELECT * FROM "{table}" WHERE "{col}"=? LIMIT 10', (
                                    val,)
                            )
                            for db_row in cursor.fetchall():
                                db_dict = dict(db_row)
                                db_ts = None
                                if ts_col and ts_col in db_dict:
                                    try:
                                        db_ts = int(db_dict[ts_col])
                                        if db_ts < TS_MIN_MS:
                                            db_ts = None
                                    except Exception:
                                        pass

                                # Find authority row match
                                auth_matches = []
                                for r in authority_rows:
                                    if (col in {"order_id", "exchange_order_id", "orderId"}
                                            and str(r.get("exchange_order_id", "")) == val):
                                        auth_matches.append(r)
                                    elif (col in {"client_order_id", "clientOrderId"}
                                          and str(r.get("client_order_id", "")) == val):
                                        auth_matches.append(r)
                                    elif col == "idempotent_key" and str(r.get("idempotent_key", "")) == val:
                                        auth_matches.append(r)
                                    elif col == "rid" and str(r.get("rid", "")) == val:
                                        auth_matches.append(r)
                                    elif col == "lifecycle_id" and str(r.get("lifecycle_id", "")) == val:
                                        auth_matches.append(r)

                                for auth_r in (auth_matches or [{"source_file": "?", "source_line": "?"}]):
                                    match_rows.append({
                                        "authority_source_file": auth_r.get("source_file", "?"),
                                        "authority_source_line": auth_r.get("source_line", "?"),
                                        "authority_order_key": val,
                                        "db_path": str(db_path.relative_to(ROOT)),
                                        "table": table,
                                        "match_field": col,
                                        "match_value": val,
                                        "db_ts_ms": db_ts,
                                        "db_status": db_dict.get("status", db_dict.get("order_status", "")),
                                        "db_price": db_dict.get("price", db_dict.get("avg_price", "")),
                                        "db_qty": db_dict.get("qty", db_dict.get("quantity", db_dict.get("origQty", ""))),
                                        "db_symbol": db_dict.get("symbol", ""),
                                        "match_confidence": f"db_exact_{col}",
                                    })
                        except sqlite3.Error as e:
                            pass  # column type mismatch etc.
            conn.close()
        except Exception as e:
            print(f"  ERROR opening {db_path}: {e}")

    # Write inventory
    inv_json = REPORTS_DIR / "db_wal_inventory.json"
    with open(inv_json, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, default=str)

    # Write matches
    match_csv = REPORTS_DIR / "db_wal_order_matches.csv"
    if match_rows:
        with open(match_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(match_rows[0].keys()))
            w.writeheader()
            w.writerows(match_rows)
    else:
        with open(match_csv, "w", newline="", encoding="utf-8") as f:
            f.write("authority_source_file,authority_source_line,authority_order_key,db_path,table,match_field,match_value,db_ts_ms,db_status,db_price,db_qty,db_symbol,match_confidence\n")

    print(f"  DB matches: {len(match_rows)}")
    print(f"  -> {inv_json}")
    print(f"  -> {match_csv}")
    return inv, match_rows


# ==============================================================================
# PHASE 5 — Local log cross-match
# ==============================================================================

LOG_PATHS = [
    "logs/order_log_v1.jsonl",
    "logs/trade_lifecycle.jsonl",
    "logs/shadow_critical_event_journal_v1.jsonl",
    "logs/event_chain.log",
    "logs/aurora_core.log",
    "logs/aurora_core.log.1",
    "logs/aurora_core.log.2",
    "logs/domain_execution_position.log",
    "logs/domain_decision_making.log",
    "logs/domain_decision_making.log.2",
    "logs/order_guardian.log",
    "logs/aurora_trades.log",
    "logs/execution_lifecycle_stats_v1.jsonl",
]


def _scan_log_for_ids(log_path: Path, exchange_ids, client_ids, rids, lifecycle_ids) -> list[dict]:
    """Scan a log file line by line, match known IDs, return timestamped matches."""
    hits = []
    if not log_path.exists():
        return hits

    file_size = log_path.stat().st_size
    # Skip files >100MB per scan to stay within time budget
    if file_size > 100 * 1024 * 1024:
        print(
            f"    SKIP (too large {file_size//1024//1024}MB): {log_path.name}")
        return hits

    # Build combined search strings for fast line-level filtering
    all_ids = exchange_ids | client_ids | rids | lifecycle_ids
    # Take short prefix sets for fast substring check
    id_prefixes = set()
    for i in all_ids:
        if i and i != "None" and len(i) >= 6:
            id_prefixes.add(i[:12])

    try:
        opener = gzip.open if str(log_path).endswith(".gz") else open
        with opener(log_path, "rt", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                # Fast pre-filter
                if not any(pf in line for pf in id_prefixes):
                    continue

                ts_found = None
                match_method = "no_match"
                match_val = ""

                # Try JSON parse
                line_stripped = line.strip()
                try:
                    obj = json.loads(line_stripped)
                    # Extract ts
                    for tf in ("timestamp", "ts_ms", "created_time", "trade_time", "update_time"):
                        v = obj.get(tf)
                        if v is not None:
                            try:
                                vi = int(v)
                                if TS_MIN_MS <= vi <= TS_MAX_MS:
                                    ts_found = vi
                                    break
                            except Exception:
                                pass
                    if ts_found is None:
                        for m in RE_13_DIGIT.finditer(line):
                            ms = int(m.group(1))
                            if TS_MIN_MS <= ms <= TS_MAX_MS:
                                ts_found = ms
                                break

                    # ID matching priority
                    for fld in ("order_id", "exchange_order_id"):
                        v = str(obj.get(fld, ""))
                        if v and v in exchange_ids:
                            match_method = "log_exact_order_id"
                            match_val = v
                            break
                    if match_method == "no_match":
                        for fld in ("client_order_id", "clientOrderId", "orig_client_order_id"):
                            v = str(obj.get(fld, ""))
                            if v and v in client_ids:
                                match_method = "log_exact_client_id"
                                match_val = v
                                break
                    if match_method == "no_match":
                        v = str(obj.get("rid", ""))
                        if v and v in rids:
                            match_method = "log_exact_rid"
                            match_val = v
                    if match_method == "no_match":
                        v = str(obj.get("lifecycle_id", ""))
                        if v and v in lifecycle_ids:
                            match_method = "log_exact_lifecycle"
                            match_val = v

                except json.JSONDecodeError:
                    # Plain text — just check for IDs and 13-digit ts
                    for i in all_ids:
                        if i and i != "None" and i in line:
                            match_method = "log_exact_rid"  # best label for text match
                            match_val = i
                            break
                    for m in RE_13_DIGIT.finditer(line):
                        ms = int(m.group(1))
                        if TS_MIN_MS <= ms <= TS_MAX_MS:
                            ts_found = ms
                            break

                if match_method != "no_match":
                    hits.append({
                        "log_file": log_path.name,
                        "log_line": lineno,
                        "match_method": match_method,
                        "match_value": match_val,
                        "log_ts_ms": ts_found,
                        "log_ts_iso": ms_to_iso(ts_found) if ts_found else None,
                    })
    except Exception as e:
        print(f"    ERROR scanning {log_path}: {e}")
    return hits


def phase5_log_match(authority_rows: list[dict]) -> list[dict]:
    print("\n=== PHASE 5: Local log cross-match ===")

    exchange_ids = {str(r["exchange_order_id"]) for r in authority_rows if r.get(
        "exchange_order_id") and r["exchange_order_id"] != ""}
    client_ids = {str(r["client_order_id"]) for r in authority_rows if r.get(
        "client_order_id") and r["client_order_id"] != ""}
    rids = {str(r["rid"])
            for r in authority_rows if r.get("rid") and r["rid"] != ""}
    lifecycle_ids = {str(r["lifecycle_id"]) for r in authority_rows if r.get(
        "lifecycle_id") and r["lifecycle_id"] != ""}

    # Remove empty/None
    for s in [exchange_ids, client_ids, rids, lifecycle_ids]:
        s.discard("")
        s.discard("None")
        s.discard("none")

    print(f"  Exchange IDs to match: {len(exchange_ids)}")
    print(f"  Client IDs to match: {len(client_ids)}")
    print(f"  RIDs to match: {len(rids)}")
    print(f"  Lifecycle IDs to match: {len(lifecycle_ids)}")

    all_hits = []
    for log_rel in LOG_PATHS:
        log_path = ROOT / log_rel
        hits = _scan_log_for_ids(
            log_path, exchange_ids, client_ids, rids, lifecycle_ids)
        if hits:
            print(f"  {log_path.name}: {len(hits)} matches")
        all_hits.extend(hits)

    # Now map hits back to authority rows
    match_rows = []

    # Build lookup for authority rows
    auth_by_oid = defaultdict(list)
    auth_by_cid = defaultdict(list)
    auth_by_rid = defaultdict(list)
    auth_by_lcid = defaultdict(list)
    for r in authority_rows:
        if r.get("exchange_order_id"):
            auth_by_oid[str(r["exchange_order_id"])].append(r)
        if r.get("client_order_id"):
            auth_by_cid[str(r["client_order_id"])].append(r)
        if r.get("rid"):
            auth_by_rid[str(r["rid"])].append(r)
        if r.get("lifecycle_id"):
            auth_by_lcid[str(r["lifecycle_id"])].append(r)

    for hit in all_hits:
        mval = hit["match_value"]
        meth = hit["match_method"]

        auth_matches = []
        if meth == "log_exact_order_id":
            auth_matches = auth_by_oid.get(mval, [])
        elif meth == "log_exact_client_id":
            auth_matches = auth_by_cid.get(mval, [])
        elif meth == "log_exact_rid":
            auth_matches = auth_by_rid.get(mval, []) or auth_by_oid.get(
                mval, []) or auth_by_cid.get(mval, [])
        elif meth == "log_exact_lifecycle":
            auth_matches = auth_by_lcid.get(mval, [])

        if not auth_matches:
            match_rows.append({
                "authority_source_file": "unmatched",
                "authority_source_line": "unmatched",
                "authority_order_key": mval,
                **hit,
            })
        else:
            for ar in auth_matches:
                match_rows.append({
                    "authority_source_file": ar["source_file"],
                    "authority_source_line": ar["source_line"],
                    "authority_order_key": mval,
                    **hit,
                })

    out_csv = REPORTS_DIR / "local_log_order_matches.csv"
    if match_rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(match_rows[0].keys()))
            w.writeheader()
            w.writerows(match_rows)
    else:
        with open(out_csv, "w", encoding="utf-8") as f:
            f.write("authority_source_file,authority_source_line,authority_order_key,log_file,log_line,match_method,match_value,log_ts_ms,log_ts_iso\n")

    print(f"  Total log matches: {len(match_rows)}")
    print(f"  -> {out_csv}")
    return match_rows


# ==============================================================================
# PHASE 6 — Timestamp recovery decision
# ==============================================================================

def phase6_recovery_decision(authority_rows, ts_candidates, db_matches, log_matches) -> dict:
    print("\n=== PHASE 6: Timestamp recovery decision ===")

    total = len(authority_rows)

    rows_with_direct = sum(1 for r in authority_rows if r.get("direct_ts_ms"))

    # Embedded ts from non-direct sources
    rows_with_embedded = sum(
        1 for r in authority_rows
        if not r.get("direct_ts_ms") and r.get("embedded_ts_candidates")
    )

    db_matched = {(m["authority_source_file"], m["authority_source_line"]) for m in db_matches
                  if m.get("db_ts_ms")}
    log_matched = {(m["authority_source_file"], m["authority_source_line"]) for m in log_matches
                   if m.get("log_ts_ms")}

    rows_matched_db = len(db_matched)
    rows_matched_logs = len(log_matched)

    rows_still_missing = 0
    high_conf = 0
    medium_conf = 0
    unusable = 0

    for r in authority_rows:
        sf = r["source_file"]
        sl = r["source_line"]
        has_direct = bool(r.get("direct_ts_ms"))
        has_db = (sf, sl) in db_matched
        has_log = (sf, sl) in log_matched
        has_embedded = bool(r.get("embedded_ts_candidates"))

        if has_direct or has_db:
            high_conf += 1
        elif has_log or has_embedded:
            medium_conf += 1
        else:
            unusable += 1
            rows_still_missing += 1

    summary = {
        "total_authority_rows": total,
        "rows_with_direct_ts": rows_with_direct,
        "rows_with_embedded_ts": rows_with_embedded,
        "rows_matched_db_wal": rows_matched_db,
        "rows_matched_local_logs": rows_matched_logs,
        "rows_still_missing_ts": rows_still_missing,
        "high_confidence_timestamp_rows": high_conf,
        "medium_confidence_timestamp_rows": medium_conf,
        "unusable_timestamp_rows": unusable,
        "verdict": "",
    }

    # Decision rule
    total_usable = high_conf + medium_conf
    pct_usable = total_usable / total if total else 0

    if high_conf >= total * 0.8:
        summary["verdict"] = "LOCAL_RECOVERY_SUFFICIENT_HIGH_CONFIDENCE"
    elif total_usable >= total * 0.6:
        summary["verdict"] = "LOCAL_RECOVERY_SUFFICIENT_MIXED"
    else:
        summary["verdict"] = "LOCAL_RECOVERY_INSUFFICIENT_EXCHANGE_SYNC_NEEDED"

    out_json = REPORTS_DIR / "timestamp_recovery_summary.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"  Total rows: {total}")
    print(f"  High confidence: {high_conf} ({high_conf/total*100:.1f}%)")
    print(f"  Medium confidence: {medium_conf} ({medium_conf/total*100:.1f}%)")
    print(f"  Unusable: {unusable}")
    print(f"  Verdict: {summary['verdict']}")
    print(f"  -> {out_json}")
    return summary


# ==============================================================================
# PHASE 9 — Final timestamp assignment
# ==============================================================================

def phase9_final_assignment(authority_rows, db_matches, log_matches) -> list[dict]:
    print("\n=== PHASE 9: Final timestamp assignment ===")

    # Build lookup tables
    db_ts_by_key = {}  # (source_file, source_line) -> (ts_ms, confidence)
    for m in db_matches:
        if m.get("db_ts_ms"):
            key = (m["authority_source_file"], str(m["authority_source_line"]))
            if key not in db_ts_by_key:
                db_ts_by_key[key] = (int(m["db_ts_ms"]), "db_exact_match")

    log_ts_by_key = {}
    for m in log_matches:
        if m.get("log_ts_ms"):
            key = (m["authority_source_file"], str(m["authority_source_line"]))
            if key not in log_ts_by_key:
                log_ts_by_key[key] = (int(m["log_ts_ms"]), m.get(
                    "match_method", "log_match"))

    # Build embedded ts lookup (best candidate per row)
    embed_ts_by_key = {}
    # Use pre-computed embedded_ts_candidates from authority rows
    for r in authority_rows:
        key = (r["source_file"], str(r["source_line"]))
        if r.get("embedded_ts_candidates"):
            cands = [int(t)
                     for t in r["embedded_ts_candidates"].split("|") if t]
            if cands:
                # take first (from ts field parsing order)
                embed_ts_by_key[key] = cands[0]

    out_rows = []
    missing_count = 0
    high_count = 0
    medium_count = 0

    for r in authority_rows:
        sf = r["source_file"]
        sl = str(r["source_line"])
        key = (sf, sl)

        recovered_ts = None
        ts_source = "missing"
        ts_quality = "missing"
        match_confidence = "none"
        join_source = "none"
        missing_reason = ""

        # Priority 1: direct authoritative ts in row
        if r.get("direct_ts_ms"):
            recovered_ts = int(r["direct_ts_ms"])
            ts_source = "direct_field"
            ts_quality = "high"
            match_confidence = "direct"
            join_source = "authority_row"
            high_count += 1

        # Priority 2: exact DB match
        elif key in db_ts_by_key:
            recovered_ts, conf = db_ts_by_key[key]
            ts_source = "db_wal_exact"
            ts_quality = "high"
            match_confidence = conf
            join_source = "order_ledger_db"
            high_count += 1

        # Priority 3: exact log match
        elif key in log_ts_by_key:
            recovered_ts, meth = log_ts_by_key[key]
            ts_source = f"local_log_{meth}"
            ts_quality = "high" if "exact" in meth else "medium"
            match_confidence = meth
            join_source = "local_logs"
            if ts_quality == "high":
                high_count += 1
            else:
                medium_count += 1

        # Priority 4: embedded ID timestamp
        elif key in embed_ts_by_key:
            recovered_ts = embed_ts_by_key[key]
            ts_source = "embedded_id_ts"
            ts_quality = "medium"
            match_confidence = "embedded"
            join_source = "id_field_extraction"
            medium_count += 1

        else:
            ts_quality = "missing"
            ts_source = "missing"
            missing_reason = "no_ts_in_row_no_db_match_no_log_match_no_embedded"
            missing_count += 1

        out_rows.append({
            # All authority fields
            **r,
            # Recovered time
            "recovered_ts_ms": recovered_ts,
            "recovered_time_iso": ms_to_iso(recovered_ts) if recovered_ts else None,
            "timestamp_source": ts_source,
            "timestamp_quality": ts_quality,
            "match_confidence": match_confidence,
            "join_source": join_source,
            "missing_reason": missing_reason,
        })

    out_csv = REPORTS_DIR / "authority_orders_with_recovered_time.csv"
    if out_rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            w.writerows(out_rows)

    print(f"  High confidence: {high_count}")
    print(f"  Medium confidence: {medium_count}")
    print(f"  Missing: {missing_count}")
    print(f"  -> {out_csv}")
    return out_rows


# ==============================================================================
# PHASE 10 — Rebuild entries from synced authority rows
# ==============================================================================

TRADE_EVENT_TYPES = {
    "ORDER_PLACED", "ORDER_FILLED", "ORDER_INTENT", "POSITION_CLOSED",
    "LIMIT_PRICE_ADJUSTED",
}


def phase10_rebuild_entries(synced_rows: list[dict]) -> list[dict]:
    print("\n=== PHASE 10: Rebuild entries from synced authority rows ===")

    entries = []
    excluded = []
    entry_id = 0

    for r in synced_rows:
        et = r.get("raw_event_type", "")
        ts_q = r.get("timestamp_quality", "missing")

        # Only include actual trade events, high/medium quality timestamps
        if et not in TRADE_EVENT_TYPES:
            continue

        if ts_q in ("missing", "low"):
            excluded.append(
                {**r, "excluded_reason": f"timestamp_quality_{ts_q}"})
            continue

        entry_id += 1
        entries.append({
            "entry_id": entry_id,
            "source_file": r["source_file"],
            "source_line": r["source_line"],
            "symbol": r["symbol"],
            "side": r["side"],
            "entry_ts_ms": r["recovered_ts_ms"],
            "entry_time_iso": r["recovered_time_iso"],
            "entry_price": r.get("price") or r.get("avg_price", ""),
            "price_source": "direct_field" if r.get("price") else "avg_price_field",
            "qty": r.get("quantity") or r.get("executed_qty", ""),
            "leverage": "",
            "leverage_source": "unknown",
            "client_order_id": r.get("client_order_id", ""),
            "exchange_order_id": r.get("exchange_order_id", ""),
            "idempotent_key": r.get("idempotent_key", ""),
            "rid": r.get("rid", ""),
            "lifecycle_id": r.get("lifecycle_id", ""),
            "close_ts_ms": "",
            "close_price": "",
            "realized_pnl": "",
            "timestamp_quality": ts_q,
            "reconstruction_confidence": r.get("match_confidence", ""),
            "excluded_reason": "",
        })

    out_csv = REPORTS_DIR.parent / "order_reconstruction_tp_sl" / \
        "reconstructed_entries_from_synced_order_log.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if entries:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(entries[0].keys()))
            w.writeheader()
            w.writerows(entries)

    excl_csv = REPORTS_DIR / "excluded_entries.csv"
    if excluded:
        with open(excl_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(
                excluded[0].keys()) if excluded else [])
            w.writeheader()
            w.writerows(excluded)

    print(f"  Usable entries: {len(entries)}")
    print(f"  Excluded entries: {len(excluded)}")
    print(f"  -> {out_csv}")
    return entries


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 70)
    print("ORDER_LOG_FORENSIC_TIMESTAMP_SYNC")
    print(f"Root: {ROOT}")
    print(f"Reports: {REPORTS_DIR}")
    print("=" * 70)

    inv = phase1_inventory()
    auth_rows = phase2_parse_rows()
    ts_cands = phase3_id_timestamps(auth_rows)
    db_inv, db_matches = phase4_db_wal(auth_rows)
    log_matches = phase5_log_match(auth_rows)
    summary = phase6_recovery_decision(
        auth_rows, ts_cands, db_matches, log_matches)
    synced_rows = phase9_final_assignment(auth_rows, db_matches, log_matches)
    entries = phase10_rebuild_entries(synced_rows)

    print("\n=== DONE ===")
    print(f"Reports written to: {REPORTS_DIR}")
    print(f"Summary verdict: {summary['verdict']}")
    return summary, synced_rows, entries


if __name__ == "__main__":
    summary, synced_rows, entries = main()
