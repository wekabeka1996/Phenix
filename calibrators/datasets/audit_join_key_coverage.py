from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


DIRECT_SOURCE_SPECS = [
    {"logical_name": "authority_request",
        "relative_path": "data/authority_request_journal_v1.jsonl", "format": "jsonl"},
    {"logical_name": "authority_response",
        "relative_path": "data/authority_response_journal_v1.jsonl", "format": "jsonl"},
    {"logical_name": "decision_ledger",
        "relative_path": "logs/shadow_telemetry/decision_ledger_v1.jsonl", "format": "jsonl"},
    {"logical_name": "order_ledger",
        "relative_path": "data/order_ledger.db", "format": "sqlite"},
    {"logical_name": "order_log",
        "relative_path": "logs/order_log_v1.jsonl", "format": "jsonl"},
    {"logical_name": "trade_lifecycle",
        "relative_path": "logs/trade_lifecycle.jsonl", "format": "jsonl"},
    {"logical_name": "regime_confidence_audit",
        "relative_path": "logs/regime_confidence_audit_v1.jsonl", "format": "jsonl"},
    {"logical_name": "executed_trades_master",
        "relative_path": "reports/executed_trades_master.csv", "format": "csv"},
    {"logical_name": "rejected_attempts_master",
        "relative_path": "reports/rejected_attempts_master.csv", "format": "csv"},
    {"logical_name": "order_attempts_master",
        "relative_path": "reports/order_attempts_master.csv", "format": "csv"},
]

GLOB_SOURCE_SPECS = [
    {"logical_name": "ops_wal", "pattern": "ops/wal/*.jsonl", "format": "jsonl"},
    {"logical_name": "reports_trades",
        "pattern": "reports/*trades*.csv", "format": "csv"},
    {"logical_name": "reports_attempts",
        "pattern": "reports/*attempts*.csv", "format": "csv"},
    {"logical_name": "recorder_csv",
        "pattern": "data/recorder/**/*.csv", "format": "csv"},
]

PRIMARY_KEY_FIELDS = [
    "decision_id",
    "request_id",
    "response_id",
    "rid",
    "run_id",
    "authority_request_id",
    "authority_response_id",
    "observation_id",
    "candidate_intent_id",
    "intent_id",
    "event_id",
    "trace_id",
    "order_id",
    "client_order_id",
    "orig_client_order_id",
    "exchange_order_id",
    "position_id",
    "lifecycle_id",
    "entry_order_id",
    "close_order_id",
    "bracket_id",
    "attempt_id",
    "trade_id",
    "fill_id",
    "order_instance_id",
    "synthetic_id",
    "entry_client_id",
]

CONTEXT_FIELDS = [
    "symbol",
    "strategy_id",
    "side",
    "regime",
    "tf_sec",
    "ts_ms",
    "event_ts_ms",
    "decision_basis_ts_ms",
    "entry_ts_ms",
    "exit_ts_ms",
    "created_at",
    "updated_at",
    "intent_ts",
    "exit_ts",
]

OUTCOME_FIELDS = [
    "outcome",
    "realized_pnl_net",
    "realized_pnl",
    "gross_pnl",
    "commission",
    "fees",
    "exact_roundtrip",
    "terminal_status",
    "reject_reason",
    "exit_price",
]

LIFECYCLE_FIELDS = [
    "lifecycle_id",
    "entry_ts_ms",
    "exit_ts_ms",
    "entry_price",
    "exit_price",
    "qty",
    "bars_held",
    "order_instance_id",
]

DECISION_FIELDS = [
    "decision_id",
    "rid",
    "request_id",
    "response_id",
    "authority_request_id",
    "authority_response_id",
    "intent_id",
    "candidate_intent_id",
    "strategy_id",
    "proposed_action",
    "action",
    "apply_result",
    "reason_code",
]

JOIN_MATRIX_FIELDS = PRIMARY_KEY_FIELDS + \
    ["symbol", "strategy_id", "side", "regime"]

TIMESTAMP_FIELDS = [
    "ts_ms",
    "event_ts_ms",
    "decision_basis_ts_ms",
    "request_ts_ms",
    "response_ts_ms",
    "intent_ts_ms",
    "entry_ts_ms",
    "exit_ts_ms",
    "timestamp",
    "created_at",
    "updated_at",
    "intent_ts",
    "exit_ts",
]

EVENT_TYPE_FIELDS = [
    "event_type",
    "event",
    "kind",
    "status",
    "role",
    "op",
    "verb",
]

PAIR_SPECS = [
    ("authority_request", "authority_response"),
    ("authority_request", "decision_ledger"),
    ("authority_response", "decision_ledger"),
    ("decision_ledger", "order_log"),
    ("decision_ledger", "trade_lifecycle"),
    ("decision_ledger", "executed_trades_master"),
    ("order_log", "executed_trades_master"),
    ("order_attempts_master", "executed_trades_master"),
    ("rejected_attempts_master", "decision_ledger"),
    ("trade_lifecycle", "executed_trades_master"),
    ("order_ledger", "order_log"),
    ("order_ledger", "executed_trades_master"),
]

COMPARISON_SPECS = [
    ("decision_ledger", "executed_trades_master"),
    ("order_attempts_master", "executed_trades_master"),
    ("trade_lifecycle", "executed_trades_master"),
    ("decision_ledger", "order_log"),
]


@dataclass(frozen=True)
class SourceRef:
    logical_name: str
    source_id: str
    relative_path: str
    format: str
    path: Path
    table: str | None = None
    exists: bool = True
    note: str | None = None


@dataclass
class SourceAccumulator:
    ref: SourceRef
    max_samples: int
    rows: int = 0
    scan_notes: list[str] = field(default_factory=list)
    sample_row_keys: list[str] = field(default_factory=list)
    discovered_fields: set[str] = field(default_factory=set)
    field_non_null_counts: Counter = field(default_factory=Counter)
    field_examples: dict[str, list[str]] = field(default_factory=dict)
    join_values: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set))
    timestamp_non_null_counts: Counter = field(default_factory=Counter)
    timestamp_min: dict[str, int] = field(default_factory=dict)
    timestamp_max: dict[str, int] = field(default_factory=dict)
    date_buckets_by_field: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))
    symbol_distribution: Counter = field(default_factory=Counter)
    strategy_distribution: Counter = field(default_factory=Counter)
    side_distribution: Counter = field(default_factory=Counter)
    regime_distribution: Counter = field(default_factory=Counter)
    event_distribution: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        for field_name in set(
            PRIMARY_KEY_FIELDS
            + CONTEXT_FIELDS
            + OUTCOME_FIELDS
            + LIFECYCLE_FIELDS
            + DECISION_FIELDS
            + TIMESTAMP_FIELDS
        ):
            self.field_examples.setdefault(field_name, [])

    def register_known_fields(self, field_names: Iterable[str]) -> None:
        for field_name in field_names:
            self.discovered_fields.add(field_name)
        if not self.sample_row_keys and field_names:
            self.sample_row_keys = list(field_names)

    def ingest_row(self, row: dict[str, Any]) -> None:
        self.rows += 1
        keys = list(row.keys())
        if not self.sample_row_keys:
            self.sample_row_keys = keys
        self.discovered_fields.update(keys)

        for field_name in set(PRIMARY_KEY_FIELDS + CONTEXT_FIELDS + OUTCOME_FIELDS + LIFECYCLE_FIELDS + DECISION_FIELDS + TIMESTAMP_FIELDS):
            raw_value = row.get(field_name)
            normalized = _normalize_scalar(raw_value)
            if normalized is None:
                continue
            self.field_non_null_counts[field_name] += 1
            _append_unique_sample(
                self.field_examples[field_name], normalized, self.max_samples)
            if field_name in JOIN_MATRIX_FIELDS:
                self.join_values[field_name].add(normalized)

        symbol = _normalize_scalar(row.get("symbol"))
        if symbol is not None:
            self.symbol_distribution[symbol] += 1

        strategy = _normalize_scalar(row.get("strategy_id"))
        if strategy is not None:
            self.strategy_distribution[strategy] += 1

        side = _normalize_scalar(row.get("side"))
        if side is not None:
            self.side_distribution[side] += 1

        regime = _normalize_scalar(row.get("regime"))
        if regime is not None:
            self.regime_distribution[regime] += 1

        event_value = _first_present_value(row, EVENT_TYPE_FIELDS)
        if event_value is not None:
            self.event_distribution[event_value] += 1

        for field_name, raw_value in row.items():
            if field_name not in TIMESTAMP_FIELDS and not field_name.endswith("_ts") and not field_name.endswith("_ts_ms"):
                continue
            timestamp_ms = _coerce_timestamp_ms(raw_value)
            if timestamp_ms is None:
                continue
            self.timestamp_non_null_counts[field_name] += 1
            previous_min = self.timestamp_min.get(field_name)
            previous_max = self.timestamp_max.get(field_name)
            self.timestamp_min[field_name] = timestamp_ms if previous_min is None else min(
                previous_min, timestamp_ms)
            self.timestamp_max[field_name] = timestamp_ms if previous_max is None else max(
                previous_max, timestamp_ms)
            self.date_buckets_by_field[field_name][_ts_ms_to_day(
                timestamp_ms)] += 1

    def to_summary(self) -> dict[str, Any]:
        primary_time_field = _choose_primary_timestamp_field(
            self.timestamp_non_null_counts)
        min_ts_ms = self.timestamp_min.get(
            primary_time_field) if primary_time_field else None
        max_ts_ms = self.timestamp_max.get(
            primary_time_field) if primary_time_field else None
        date_buckets = self.date_buckets_by_field.get(
            primary_time_field, Counter()) if primary_time_field else Counter()
        notes: list[str] = list(self.scan_notes)
        if self.rows == 0:
            notes.append("rows=0")
        if self.ref.note:
            notes.append(self.ref.note)
        if self.ref.table:
            notes.append(f"sqlite_table={self.ref.table}")

        return {
            "logical_name": self.ref.logical_name,
            "source": self.ref.source_id,
            "relative_path": self.ref.relative_path,
            "format": self.ref.format,
            "exists": self.ref.exists,
            "rows": self.rows,
            "size_bytes": self.ref.path.stat().st_size if self.ref.exists and self.ref.path.exists() else 0,
            "sample_row_keys": self.sample_row_keys,
            "field_non_null_counts": {
                field_name: count
                for field_name, count in sorted(self.field_non_null_counts.items())
                if count > 0
            },
            "field_examples": {
                field_name: values
                for field_name, values in sorted(self.field_examples.items())
                if values
            },
            "key_fields_present": [
                field_name
                for field_name in PRIMARY_KEY_FIELDS + CONTEXT_FIELDS
                if self.field_non_null_counts.get(field_name, 0) > 0
            ],
            "outcome_fields_present": [
                field_name
                for field_name in OUTCOME_FIELDS
                if self.field_non_null_counts.get(field_name, 0) > 0
            ],
            "lifecycle_fields_present": [
                field_name
                for field_name in LIFECYCLE_FIELDS
                if self.field_non_null_counts.get(field_name, 0) > 0
            ],
            "decision_fields_present": [
                field_name
                for field_name in DECISION_FIELDS
                if self.field_non_null_counts.get(field_name, 0) > 0
            ],
            "primary_time_field": primary_time_field,
            "min_ts_ms": min_ts_ms,
            "max_ts_ms": max_ts_ms,
            "min_time_utc": _ts_ms_to_iso(min_ts_ms),
            "max_time_utc": _ts_ms_to_iso(max_ts_ms),
            "row_counts_by_symbol": dict(self.symbol_distribution.most_common(20)),
            "row_counts_by_strategy": dict(self.strategy_distribution.most_common(20)),
            "row_counts_by_side": dict(self.side_distribution.most_common(20)),
            "row_counts_by_regime": dict(self.regime_distribution.most_common(20)),
            "row_counts_by_day": dict(date_buckets.most_common(20)),
            "event_type_distribution": dict(self.event_distribution.most_common(20)),
            "notes": notes,
        }


def _append_unique_sample(values: list[str], candidate: str, max_samples: int) -> None:
    if candidate in values:
        return
    if len(values) >= max_samples:
        return
    values.append(candidate)


def _normalize_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _coerce_timestamp_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            numeric_value = float(value)
        except ValueError:
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
    elif isinstance(value, (int, float)):
        numeric_value = float(value)
    else:
        return None

    absolute_value = abs(numeric_value)
    if absolute_value == 0:
        return 0
    if absolute_value < 10_000_000_000:
        return int(numeric_value * 1000)
    return int(numeric_value)


def _ts_ms_to_iso(ts_ms: Optional[int]) -> Optional[str]:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _ts_ms_to_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _choose_primary_timestamp_field(timestamp_counts: Counter) -> Optional[str]:
    if not timestamp_counts:
        return None
    preferred_order = {field_name: index for index,
                       field_name in enumerate(TIMESTAMP_FIELDS)}
    ranked = sorted(
        timestamp_counts.items(),
        key=lambda item: (
            item[1],
            -preferred_order.get(item[0], len(TIMESTAMP_FIELDS)),
            item[0],
        ),
        reverse=True,
    )
    return ranked[0][0]


def _first_present_value(row: dict[str, Any], fields: Iterable[str]) -> Optional[str]:
    for field_name in fields:
        normalized = _normalize_scalar(row.get(field_name))
        if normalized is not None:
            return f"{field_name}:{normalized}"
    return None


def _parse_date_bound(value: Optional[str], *, inclusive_end: bool = False) -> Optional[int]:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if inclusive_end:
        parsed = parsed.replace(
            hour=23, minute=59, second=59, microsecond=999000)
    return int(parsed.timestamp() * 1000)


def _row_passes_date_filter(row: dict[str, Any], date_start_ms: Optional[int], date_end_ms: Optional[int]) -> bool:
    if date_start_ms is None and date_end_ms is None:
        return True
    row_timestamps: list[int] = []
    for field_name, raw_value in row.items():
        if field_name not in TIMESTAMP_FIELDS and not field_name.endswith("_ts") and not field_name.endswith("_ts_ms"):
            continue
        timestamp_ms = _coerce_timestamp_ms(raw_value)
        if timestamp_ms is not None:
            row_timestamps.append(timestamp_ms)
    if not row_timestamps:
        return True
    for timestamp_ms in row_timestamps:
        if date_start_ms is not None and timestamp_ms < date_start_ms:
            continue
        if date_end_ms is not None and timestamp_ms > date_end_ms:
            continue
        return True
    return False


def _iter_jsonl_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _iter_csv_rows(path: Path) -> tuple[list[str], Iterator[dict[str, Any]]]:
    handle = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.DictReader(handle)
    field_names = reader.fieldnames or []

    def _iterator() -> Iterator[dict[str, Any]]:
        try:
            for row in reader:
                yield row
        finally:
            handle.close()

    return field_names, _iterator()


def _iter_sqlite_rows(path: Path, table: str) -> tuple[list[str], Iterator[dict[str, Any]]]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    columns = [
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]
    cursor = connection.execute(f"SELECT * FROM {table}")

    def _iterator() -> Iterator[dict[str, Any]]:
        try:
            for row in cursor:
                yield dict(row)
        finally:
            cursor.close()
            connection.close()

    return columns, _iterator()


def _resolve_sqlite_refs(repo_root: Path, spec: dict[str, str]) -> list[SourceRef]:
    path = repo_root / spec["relative_path"]
    if not path.exists():
        return [
            SourceRef(
                logical_name=spec["logical_name"],
                source_id=spec["relative_path"],
                relative_path=spec["relative_path"],
                format=spec["format"],
                path=path,
                exists=False,
                note="missing_sqlite_db",
            )
        ]

    connection = sqlite3.connect(path)
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    connection.close()
    if not tables:
        return [
            SourceRef(
                logical_name=spec["logical_name"],
                source_id=spec["relative_path"],
                relative_path=spec["relative_path"],
                format=spec["format"],
                path=path,
                exists=True,
                note="sqlite_has_no_tables",
            )
        ]

    refs: list[SourceRef] = []
    for table in tables:
        refs.append(
            SourceRef(
                logical_name=spec["logical_name"],
                source_id=f"{spec['relative_path']}::{table}",
                relative_path=spec["relative_path"],
                format=spec["format"],
                path=path,
                table=table,
                exists=True,
                note=f"sqlite_table={table}",
            )
        )
    return refs


def resolve_source_refs(repo_root: Path) -> list[SourceRef]:
    refs: list[SourceRef] = []
    seen: set[str] = set()

    for spec in DIRECT_SOURCE_SPECS:
        if spec["format"] == "sqlite":
            for ref in _resolve_sqlite_refs(repo_root, spec):
                if ref.source_id in seen:
                    continue
                seen.add(ref.source_id)
                refs.append(ref)
            continue

        path = repo_root / spec["relative_path"]
        ref = SourceRef(
            logical_name=spec["logical_name"],
            source_id=spec["relative_path"],
            relative_path=spec["relative_path"],
            format=spec["format"],
            path=path,
            exists=path.exists(),
            note=None if path.exists() else "missing_required_source",
        )
        if ref.source_id in seen:
            continue
        seen.add(ref.source_id)
        refs.append(ref)

    for spec in GLOB_SOURCE_SPECS:
        matches = sorted(path for path in repo_root.glob(
            spec["pattern"]) if path.is_file())
        if not matches:
            source_id = f"{spec['pattern']} [pattern]"
            if source_id in seen:
                continue
            seen.add(source_id)
            refs.append(
                SourceRef(
                    logical_name=spec["logical_name"],
                    source_id=source_id,
                    relative_path=spec["pattern"],
                    format=spec["format"],
                    path=repo_root / spec["pattern"],
                    exists=False,
                    note="glob_no_matches",
                )
            )
            continue

        for match in matches:
            relative_path = match.relative_to(repo_root).as_posix()
            if relative_path in seen:
                continue
            seen.add(relative_path)
            refs.append(
                SourceRef(
                    logical_name=f"{spec['logical_name']}::{match.stem}",
                    source_id=relative_path,
                    relative_path=relative_path,
                    format=spec["format"],
                    path=match,
                    exists=True,
                )
            )

    return refs


def scan_sources(
    source_refs: list[SourceRef],
    *,
    date_start_ms: Optional[int],
    date_end_ms: Optional[int],
    max_samples: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, SourceAccumulator], dict[str, str]]:
    summaries: dict[str, dict[str, Any]] = {}
    accumulators: dict[str, SourceAccumulator] = {}
    alias_map: dict[str, str] = {}

    for ref in source_refs:
        accumulator = SourceAccumulator(ref=ref, max_samples=max_samples)
        accumulators[ref.source_id] = accumulator
        alias_map.setdefault(ref.logical_name, ref.source_id)

        if not ref.exists or (ref.format == "sqlite" and ref.table is None):
            summaries[ref.source_id] = accumulator.to_summary()
            continue

        try:
            if ref.format == "jsonl":
                decode_errors = 0
                non_object_rows = 0
                with ref.path.open("r", encoding="utf-8-sig") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            decode_errors += 1
                            continue
                        if not isinstance(row, dict):
                            non_object_rows += 1
                            continue
                        if not _row_passes_date_filter(row, date_start_ms, date_end_ms):
                            continue
                        accumulator.ingest_row(row)
                if decode_errors:
                    accumulator.scan_notes.append(
                        f"json_decode_errors={decode_errors}")
                if non_object_rows:
                    accumulator.scan_notes.append(
                        f"non_object_json_rows={non_object_rows}")
            elif ref.format == "csv":
                field_names, iterator = _iter_csv_rows(ref.path)
                accumulator.register_known_fields(field_names)
                for row in iterator:
                    if not _row_passes_date_filter(row, date_start_ms, date_end_ms):
                        continue
                    accumulator.ingest_row(row)
            elif ref.format == "sqlite":
                field_names, iterator = _iter_sqlite_rows(
                    ref.path, ref.table or "")
                accumulator.register_known_fields(field_names)
                for row in iterator:
                    if not _row_passes_date_filter(row, date_start_ms, date_end_ms):
                        continue
                    accumulator.ingest_row(row)
            else:
                raise ValueError(f"Unsupported format: {ref.format}")
        except Exception as exc:
            accumulator.ref = SourceRef(
                logical_name=ref.logical_name,
                source_id=ref.source_id,
                relative_path=ref.relative_path,
                format=ref.format,
                path=ref.path,
                table=ref.table,
                exists=ref.exists,
                note=f"scan_error={type(exc).__name__}:{exc}",
            )
        summaries[ref.source_id] = accumulator.to_summary()

    return summaries, accumulators, alias_map


def _evaluate_pair_key(
    left_summary: dict[str, Any],
    right_summary: dict[str, Any],
    left_accumulator: SourceAccumulator,
    right_accumulator: SourceAccumulator,
    key: str,
    max_samples: int,
) -> dict[str, Any]:
    left_values = left_accumulator.join_values.get(key, set())
    right_values = right_accumulator.join_values.get(key, set())
    overlap_values = sorted(left_values & right_values)
    left_only_values = sorted(left_values - right_values)
    right_only_values = sorted(right_values - left_values)
    left_non_null = len(left_values)
    right_non_null = len(right_values)
    overlap_count = len(overlap_values)
    overlap_pct_left = round(
        (overlap_count / left_non_null) * 100.0, 4) if left_non_null else 0.0
    overlap_pct_right = round(
        (overlap_count / right_non_null) * 100.0, 4) if right_non_null else 0.0
    appears_canonical = key in PRIMARY_KEY_FIELDS
    if overlap_count > 0 and appears_canonical:
        grade = "EXACT_PROMOTION_GRADE_POSSIBLE"
    elif overlap_count > 0:
        grade = "DIAGNOSTICS_ONLY_CONTEXT_MATCH"
    elif left_non_null == 0 or right_non_null == 0:
        grade = "NO_SHARED_POPULATED_KEY"
    else:
        grade = "NO_EXACT_OVERLAP"

    return {
        "key": key,
        "left_non_null_count": left_non_null,
        "right_non_null_count": right_non_null,
        "exact_overlap_count": overlap_count,
        "overlap_pct_left": overlap_pct_left,
        "overlap_pct_right": overlap_pct_right,
        "example_matched_values": overlap_values[:max_samples],
        "example_left_only_values": left_only_values[:max_samples],
        "example_right_only_values": right_only_values[:max_samples],
        "appears_canonical": appears_canonical,
        "grade": grade,
        "left_source_rows": left_summary["rows"],
        "right_source_rows": right_summary["rows"],
    }


def _select_best_pair_key(evaluated: list[dict[str, Any]]) -> dict[str, Any]:
    def _rank(entry: dict[str, Any]) -> tuple[int, int, int, int, str]:
        overlap_bonus = 2 if entry["exact_overlap_count"] > 0 else 0
        canonical_bonus = 1 if entry["appears_canonical"] else 0
        bilateral_presence = min(
            entry["left_non_null_count"], entry["right_non_null_count"])
        overlap_count = entry["exact_overlap_count"]
        return (
            overlap_bonus,
            canonical_bonus,
            overlap_count,
            bilateral_presence,
            entry["key"],
        )

    return max(evaluated, key=_rank)


def build_join_coverage_matrix(
    summaries: dict[str, dict[str, Any]],
    accumulators: dict[str, SourceAccumulator],
    alias_map: dict[str, str],
    *,
    max_samples: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    csv_rows: list[dict[str, Any]] = []
    json_rows: list[dict[str, Any]] = []

    for left_alias, right_alias in PAIR_SPECS:
        left_source_id = alias_map.get(left_alias)
        right_source_id = alias_map.get(right_alias)
        if left_source_id is None or right_source_id is None:
            continue
        left_summary = summaries[left_source_id]
        right_summary = summaries[right_source_id]
        left_accumulator = accumulators[left_source_id]
        right_accumulator = accumulators[right_source_id]
        evaluated = [
            _evaluate_pair_key(
                left_summary,
                right_summary,
                left_accumulator,
                right_accumulator,
                key,
                max_samples,
            )
            for key in JOIN_MATRIX_FIELDS
        ]
        best = _select_best_pair_key(evaluated)
        csv_rows.append(
            {
                "left": left_summary["source"],
                "right": right_summary["source"],
                "candidate_key": best["key"],
                "left_non_null_count": best["left_non_null_count"],
                "right_non_null_count": best["right_non_null_count"],
                "exact_overlap_count": best["exact_overlap_count"],
                "overlap_pct_left": best["overlap_pct_left"],
                "overlap_pct_right": best["overlap_pct_right"],
                "example_matched_values": json.dumps(best["example_matched_values"], ensure_ascii=True),
                "example_left_only_values": json.dumps(best["example_left_only_values"], ensure_ascii=True),
                "example_right_only_values": json.dumps(best["example_right_only_values"], ensure_ascii=True),
                "appears_canonical": best["appears_canonical"],
                "grade": best["grade"],
            }
        )
        json_rows.append(
            {
                "left": left_summary["source"],
                "right": right_summary["source"],
                "best_candidate": best,
                "evaluated_keys": evaluated,
            }
        )

    return csv_rows, json_rows


def build_time_alignment(
    summaries: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> dict[str, Any]:
    per_source = []
    for source_id, summary in summaries.items():
        per_source.append(
            {
                "source": source_id,
                "logical_name": summary["logical_name"],
                "min_ts_ms": summary["min_ts_ms"],
                "max_ts_ms": summary["max_ts_ms"],
                "min_time_utc": summary["min_time_utc"],
                "max_time_utc": summary["max_time_utc"],
                "symbols": list(summary["row_counts_by_symbol"].keys()),
                "row_counts_by_symbol": summary["row_counts_by_symbol"],
                "row_counts_by_day": summary["row_counts_by_day"],
                "event_type_distribution": summary["event_type_distribution"],
                "primary_time_field": summary["primary_time_field"],
                "rows": summary["rows"],
                "notes": summary["notes"],
            }
        )

    comparisons = []
    for left_alias, right_alias in COMPARISON_SPECS:
        left_source_id = alias_map.get(left_alias)
        right_source_id = alias_map.get(right_alias)
        if left_source_id is None or right_source_id is None:
            continue
        left = summaries[left_source_id]
        right = summaries[right_source_id]
        symbol_overlap = sorted(
            set(left["row_counts_by_symbol"].keys()) & set(
                right["row_counts_by_symbol"].keys())
        )
        time_overlap = None
        if left["min_ts_ms"] is not None and left["max_ts_ms"] is not None and right["min_ts_ms"] is not None and right["max_ts_ms"] is not None:
            time_overlap = not (
                left["max_ts_ms"] < right["min_ts_ms"] or right["max_ts_ms"] < left["min_ts_ms"])
        comparisons.append(
            {
                "left": left_source_id,
                "right": right_source_id,
                "left_min_time_utc": left["min_time_utc"],
                "left_max_time_utc": left["max_time_utc"],
                "right_min_time_utc": right["min_time_utc"],
                "right_max_time_utc": right["max_time_utc"],
                "symbol_overlap": symbol_overlap,
                "symbol_overlap_count": len(symbol_overlap),
                "time_overlap": time_overlap,
                "left_rows": left["rows"],
                "right_rows": right["rows"],
            }
        )

    return {
        "per_source": per_source,
        "comparisons": comparisons,
    }


def build_builder_logic_audit(
    out_dir: Path,
    summaries: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
    join_matrix_rows: list[dict[str, Any]],
) -> None:
    executed = summaries[alias_map["executed_trades_master"]]
    decision_ledger = summaries[alias_map["decision_ledger"]]
    order_log = summaries[alias_map["order_log"]]
    trade_lifecycle = summaries[alias_map["trade_lifecycle"]]
    attempts = summaries[alias_map["order_attempts_master"]]
    decision_vs_executed = next(
        row for row in join_matrix_rows
        if row["left"] == decision_ledger["source"] and row["right"] == executed["source"]
    )

    lines = [
        "# BUILDER_JOIN_LOGIC_AUDIT",
        "",
        "## Objective builder current logic",
        "- Reads decision rows from authority_request_journal_v1.jsonl, authority_response_journal_v1.jsonl, and decision_ledger_v1.jsonl.",
        "- Reads realized rows only from reports/executed_trades_master.csv.",
        "- Keys executed-trade rows by attempt_id before any realized row is emitted.",
        "- Copies decision_id from executed_trades_master when present, but does not require a matched decision row overlap to emit a realized row.",
        "- Ignores order_log_v1.jsonl, trade_lifecycle.jsonl, order_attempts_master.csv, and order_ledger.db when building objective realized rows.",
        "",
        "## Answers",
        "1. Which fields does the builder currently use to join decisions to realized trades?",
        "   - It does not perform a strict decision↔realized exact join. The realized path is driven by executed_trades_master rows keyed by attempt_id, with optional decision_id lookup back into the decision ledger.",
        "2. Are those fields actually present in the source rows?",
        f"   - executed_trades_master current header fields: {', '.join(executed['sample_row_keys']) if executed['sample_row_keys'] else 'none'}.",
        f"   - decision_ledger key fields present: {', '.join(decision_ledger['key_fields_present']) if decision_ledger['key_fields_present'] else 'none'}.",
        "3. Are they populated?",
        f"   - executed_trades_master rows={executed['rows']}; attempt_id non-null count={executed['field_non_null_counts'].get('attempt_id', 0)}; decision_id non-null count={executed['field_non_null_counts'].get('decision_id', 0)}.",
        "4. Do the values overlap?",
        f"   - Best current exact pair result for decision_ledger ↔ executed_trades_master is key={decision_vs_executed['candidate_key']} overlap={decision_vs_executed['exact_overlap_count']} grade={decision_vs_executed['grade']}.",
        "5. Does builder ignore a better available key?",
        f"   - It ignores order_log lifecycle/order identifiers and trade_lifecycle runtime identities; order_log key fields present: {', '.join(order_log['key_fields_present']) if order_log['key_fields_present'] else 'none'}; trade_lifecycle key fields present: {', '.join(trade_lifecycle['key_fields_present']) if trade_lifecycle['key_fields_present'] else 'none'}.",
        "6. Does builder use a key that exists only in synthetic tests?",
        "   - Synthetic tests assume a populated executed_trades_master surface with attempt_id, decision_id, rid, lifecycle_id, strategy_id, and *_ts_ms fields. The live master report currently has zero rows and its header does not contain several of those columns.",
        "7. Does builder filter out valid rows accidentally?",
        f"   - Current evidence does not prove accidental filtering inside the realized loop; the dominant fact is that executed_trades_master contributes zero rows before row-level validation even begins.",
        "8. Does it require exact fields that reports do not contain?",
        "   - Yes. The builder expects decision_id, rid, lifecycle_id, strategy_id, intent_ts_ms, entry_ts_ms, exit_ts_ms, gross_pnl, fees, mfe, mae, bars_held, and terminal_status. The current executed_trades_master header uses intent_ts, exit_ts, realized_pnl, order_instance_id, and does not expose several expected fields.",
        "9. Does it lose identity during normalization?",
        "   - No direct proof of identity loss from normalize_symbol/normalize_side. The main loss is upstream: realized identity is absent or not surfaced in the chosen report.",
        "10. Does it conflate decision row and realized trade row identity?",
        "   - Yes. The realized row identity is driven by whatever executed_trades_master exposes, while decision identity stays on decision_id/rid. There is no enforced canonical bridge proving that emitted realized rows belong to emitted decision rows.",
        "",
        "## Audit conclusion",
        f"- Current executed_trades_master rows={executed['rows']} is the immediate reason objective_stack emits zero realized rows.",
        f"- order_attempts_master rows={attempts['rows']} shows at least one alternate attempt surface exists, but objective_stack does not consume it.",
        "- The objective builder therefore exhibits a builder-logic gap relative to available runtime surfaces, but the first blocking fact is an empty chosen realized-outcome report.",
    ]
    (out_dir / "BUILDER_JOIN_LOGIC_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")


def build_low_vol_zero_row_audit(
    out_dir: Path,
    summaries: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> None:
    executed = summaries[alias_map["executed_trades_master"]]
    regime = summaries[alias_map["regime_confidence_audit"]]
    attempts = summaries[alias_map["order_attempts_master"]]
    low_regime_values = [
        value
        for value in regime["row_counts_by_regime"].keys()
        if "low" in value.lower()
    ]
    lines = [
        "# LOW_VOL_ZERO_ROW_AUDIT",
        "",
        f"- executed_trades_master rows: {executed['rows']}",
        f"- order_attempts_master rows: {attempts['rows']}",
        f"- regime_confidence_audit rows: {regime['rows']}",
        f"- regime values containing 'low': {', '.join(low_regime_values) if low_regime_values else 'none'}",
        "",
        "## Findings",
        "- The low_vol builder begins from executed_trades_master. With zero executed-trade rows, it cannot emit any gate rows regardless of regime availability.",
        "- The low_vol filter checks for substring 'low' in regime values, so LOW_VOLATILITY vs low_vol spelling is not the current primary blocker if regime rows exist.",
        f"- regime_confidence_audit currently exposes regime distribution: {json.dumps(regime['row_counts_by_regime'], ensure_ascii=False)}.",
        "- Because order_attempts_master has rows while executed_trades_master is empty, low-vol zero rows are not explained by missing attempt metadata alone.",
        "",
        "## Conclusion",
        "- Current low-vol zero-row output is primarily explained by the empty executed_trades_master surface, not by a proven low-vol regime spelling defect.",
        "- Any stronger conclusion about low-vol outcome joins would require either a populated realized-outcome surface or an alternate exact-identity bridge from order/trade logs.",
    ]
    (out_dir / "LOW_VOL_ZERO_ROW_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_source_inventory_markdown(out_dir: Path, summaries: dict[str, dict[str, Any]]) -> None:
    rows = []
    for source_id, summary in sorted(summaries.items()):
        time_range = "n/a"
        if summary["min_time_utc"] or summary["max_time_utc"]:
            time_range = f"{summary['min_time_utc']} -> {summary['max_time_utc']}"
        rows.append([
            source_id,
            str(summary["exists"]),
            str(summary["rows"]),
            time_range,
            ", ".join(summary["key_fields_present"][:8]) or "none",
            ", ".join(summary["outcome_fields_present"][:8]) or "none",
            "; ".join(summary["notes"]) or "",
        ])
    content = "# SOURCE_INVENTORY\n\n" + _markdown_table(
        ["Source", "Exists", "Rows", "Time Range",
            "Key Fields", "Outcome Fields", "Notes"],
        rows,
    )
    (out_dir / "SOURCE_INVENTORY.md").write_text(content, encoding="utf-8")


def write_join_key_census_markdown(out_dir: Path, summaries: dict[str, dict[str, Any]], max_samples: int) -> None:
    rows = []
    for source_id, summary in sorted(summaries.items()):
        for field_name in PRIMARY_KEY_FIELDS + CONTEXT_FIELDS:
            count = summary["field_non_null_counts"].get(field_name, 0)
            if count == 0:
                continue
            examples = ", ".join(summary["field_examples"].get(
                field_name, [])[:max_samples]) or "none"
            rows.append([
                source_id,
                field_name,
                str(count),
                examples,
                "canonical" if field_name in PRIMARY_KEY_FIELDS else "context",
            ])
    content = "# JOIN_KEY_CENSUS\n\n" + _markdown_table(
        ["Source", "Field", "Non-null Count", "Example Values", "Notes"],
        rows,
    )
    (out_dir / "JOIN_KEY_CENSUS.md").write_text(content, encoding="utf-8")


def write_join_coverage_matrix_markdown(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    table_rows = []
    for row in rows:
        table_rows.append([
            row["left"],
            row["right"],
            row["candidate_key"],
            str(row["exact_overlap_count"]),
            str(row["overlap_pct_left"]),
            str(row["overlap_pct_right"]),
            row["grade"],
        ])
    content = "# JOIN_COVERAGE_MATRIX\n\n" + _markdown_table(
        ["Left", "Right", "Key", "Overlap Count",
            "Left Coverage", "Right Coverage", "Grade"],
        table_rows,
    )
    (out_dir / "JOIN_COVERAGE_MATRIX.md").write_text(content, encoding="utf-8")


def write_time_window_alignment_markdown(out_dir: Path, alignment: dict[str, Any]) -> None:
    source_rows = []
    for entry in alignment["per_source"]:
        source_rows.append([
            entry["source"],
            entry["min_time_utc"] or "n/a",
            entry["max_time_utc"] or "n/a",
            ", ".join(entry["symbols"][:8]) or "none",
            "; ".join(entry["notes"]) or "",
        ])
    comparison_rows = []
    for entry in alignment["comparisons"]:
        comparison_rows.append([
            entry["left"],
            entry["right"],
            str(entry["time_overlap"]),
            ", ".join(entry["symbol_overlap"][:8]) or "none",
            f"left_rows={entry['left_rows']} right_rows={entry['right_rows']}",
        ])
    content = "# TIME_WINDOW_ALIGNMENT\n\n## Sources\n\n"
    content += _markdown_table(["Source", "Min Time",
                               "Max Time", "Symbols", "Notes"], source_rows)
    content += "\n\n## Comparisons\n\n"
    content += _markdown_table(["Left", "Right", "Time Overlap",
                               "Symbol Overlap", "Notes"], comparison_rows)
    (out_dir / "TIME_WINDOW_ALIGNMENT.md").write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                    indent=2), encoding="utf-8")


def write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "left",
        "right",
        "candidate_key",
        "left_non_null_count",
        "right_non_null_count",
        "exact_overlap_count",
        "overlap_pct_left",
        "overlap_pct_right",
        "example_matched_values",
        "example_left_only_values",
        "example_right_only_values",
        "appears_canonical",
        "grade",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_report_payload(
    summaries: dict[str, dict[str, Any]],
    join_matrix_json: list[dict[str, Any]],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_inventory": summaries,
        "join_coverage_matrix": join_matrix_json,
        "time_window_alignment": alignment,
    }


def run_audit(
    repo_root: Path,
    out_dir: Path,
    *,
    date_start: Optional[str],
    date_end: Optional[str],
    max_samples: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    source_refs = resolve_source_refs(repo_root)
    date_start_ms = _parse_date_bound(date_start)
    date_end_ms = _parse_date_bound(date_end, inclusive_end=True)
    summaries, accumulators, alias_map = scan_sources(
        source_refs,
        date_start_ms=date_start_ms,
        date_end_ms=date_end_ms,
        max_samples=max_samples,
    )
    join_matrix_csv, join_matrix_json = build_join_coverage_matrix(
        summaries,
        accumulators,
        alias_map,
        max_samples=max_samples,
    )
    alignment = build_time_alignment(summaries, alias_map)

    write_json(out_dir / "source_inventory.json", summaries)
    write_source_inventory_markdown(out_dir, summaries)

    join_key_census = {
        source_id: {
            field_name: summary["field_non_null_counts"].get(field_name, 0)
            for field_name in PRIMARY_KEY_FIELDS + CONTEXT_FIELDS
            if summary["field_non_null_counts"].get(field_name, 0) > 0
        }
        for source_id, summary in summaries.items()
    }
    write_json(out_dir / "join_key_census.json", join_key_census)
    write_join_key_census_markdown(out_dir, summaries, max_samples)

    write_csv_rows(out_dir / "join_coverage_matrix.csv", join_matrix_csv)
    write_json(out_dir / "join_coverage_matrix.json", join_matrix_json)
    write_join_coverage_matrix_markdown(out_dir, join_matrix_csv)

    write_json(out_dir / "time_window_alignment.json", alignment)
    write_time_window_alignment_markdown(out_dir, alignment)

    build_builder_logic_audit(out_dir, summaries, alias_map, join_matrix_csv)
    build_low_vol_zero_row_audit(out_dir, summaries, alias_map)

    report_payload = build_report_payload(
        summaries, join_matrix_json, alignment)
    write_json(out_dir / "audit_summary.json", report_payload)
    return {
        "sources": summaries,
        "join_matrix_csv": join_matrix_csv,
        "join_matrix_json": join_matrix_json,
        "alignment": alignment,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only join-key coverage audit for calibration datasets")
    parser.add_argument("--repo-root", default=".",
                        help="Repository root path")
    parser.add_argument(
        "--out-dir",
        default="calibrators/datasets/join_key_coverage",
        help="Output directory for audit artifacts",
    )
    parser.add_argument("--date-start", default=None,
                        help="Optional inclusive ISO start date (YYYY-MM-DD)")
    parser.add_argument("--date-end", default=None,
                        help="Optional inclusive ISO end date (YYYY-MM-DD)")
    parser.add_argument("--max-samples", type=int, default=5,
                        help="Maximum sample values per field")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    payload = run_audit(
        repo_root,
        out_dir,
        date_start=args.date_start,
        date_end=args.date_end,
        max_samples=args.max_samples,
    )
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "sources": len(payload["sources"]),
                "join_pairs": len(payload["join_matrix_csv"]),
                "comparisons": len(payload["alignment"]["comparisons"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
