"""Alpha Search Factory V1.

Bounded, shadow-only research tooling for building replayable alpha-search
datasets, outcome artifacts, deterministic candidate sweeps, and audit reports.

This module deliberately does not widen Judge authority, does not edit live
configs, and excludes synthetic_stress rows from official performance metrics.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "alpha_search_factory" / "alpha_factory.sqlite"
DEFAULT_DATA_ROOT = ROOT / "data" / "alpha_search_factory"
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "alpha_search_factory"
DEFAULT_JUDGE_LOG_DIR = ROOT / "logs" / "judge_experts"
DEFAULT_RAW_1M_DIR = ROOT / "data" / "raw_binance_klines_1m"
DEFAULT_RECORDER_1M_DIR = ROOT / "data" / "recorder_backfill_1m"
DEFAULT_SIMULATOR_CONFIG = ROOT / "config" / "judge_simulator.yaml"
DEFAULT_REVIEW_CONFIG = ROOT / "config" / "judge_review.yaml"
DEFAULT_CALIBRATION_PATH = ROOT / "artifacts" / "phase5_calibration.jsonl"

DEFAULT_UNIVERSE = (
    "1000PEPEUSDT",
    "BNBUSDT",
    "BTCUSDT",
    "DOGEUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
)

PROVENANCE_CLASSES = (
    "exchange_real",
    "runtime_observed",
    "replay_derived",
    "synthetic_stress",
)
OFFICIAL_PROVENANCE_CLASSES = {
    "exchange_real",
    "runtime_observed",
    "replay_derived",
}
MINUTE_MS = 60_000
DAY_MS = 24 * 60 * MINUTE_MS
ACTIONABLE_VERDICTS = {"OPEN_LONG", "OPEN_SHORT"}
FAILURE_CLASSES = {
    "CORRECT_ENTRY",
    "DATA_GAP",
    "NO_ACTIONABLE_PLAN",
    "NO_FILL",
    "WRONG_DIRECTION",
    "ENTRY_TOO_LATE",
    "ENTRY_TOO_AGGRESSIVE",
    "ENTRY_OK_EXIT_BAD",
    "RAW_RIGHT_NET_WRONG",
    "FEE_SLIPPAGE_KILLED",
    "CONFIDENCE_MISORDERED",
    "REGIME_MISCLASSIFIED",
    "TIMEOUT_WITH_EDGE",
    "TIMEOUT_NO_EDGE",
}
FIXED_CONFIDENCE_BUCKETS = (
    (0.0, 0.25, "[0.00,0.25]"),
    (0.25, 0.50, "[0.25,0.50]"),
    (0.50, 0.75, "[0.50,0.75]"),
    (0.75, 1.01, "[0.75,1.00]"),
)


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def utc_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def floor_to_completed_utc_day(now: datetime | None = None) -> tuple[int, int, str, str]:
    current = now.astimezone(timezone.utc) if now else datetime.now(tz=timezone.utc)
    today_start = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
    completed_start = today_start - timedelta(days=1)
    completed_end_ms = int(today_start.timestamp() * 1000) - 1
    completed_start_ms = int(completed_start.timestamp() * 1000) + MINUTE_MS - 1
    return (
        completed_start_ms,
        completed_end_ms,
        completed_start.date().isoformat(),
        (today_start - timedelta(milliseconds=1)).date().isoformat(),
    )


def completed_utc_window_for_days(days_back: int, now: datetime | None = None) -> dict[str, Any]:
    if days_back <= 0:
        raise ValueError("days_back must be positive for completed UTC day windows")
    _, end_close_ms, _, end_date = floor_to_completed_utc_day(now)
    start_close_ms = end_close_ms - (days_back * 24 * 60 - 1) * MINUTE_MS
    start_date = datetime.fromtimestamp(start_close_ms / 1000.0, tz=timezone.utc).date().isoformat()
    return {
        "days_back": days_back,
        "start_close_ms": start_close_ms,
        "end_close_ms": end_close_ms,
        "start_date": start_date,
        "end_date": end_date,
        "rule": "last_completed_utc_day_inclusive",
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=True) + "\n")
            count += 1
    tmp_path.replace(path)
    return count


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    tmp_path.replace(path)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(payload: Any, *, length: int = 16) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def parse_csv_arg(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_float_csv(value: str | None, default: Sequence[float]) -> list[float]:
    items = parse_csv_arg(value)
    if not items:
        return list(default)
    return [float(item) for item in items]


def parse_int_csv(value: str | None, default: Sequence[int]) -> list[int]:
    items = parse_csv_arg(value)
    if not items:
        return list(default)
    return [int(item) for item in items]


def coerce_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def coerce_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def provenance_is_official(provenance_class: str | None) -> bool:
    normalized = provenance_class or "replay_derived"
    return normalized in OFFICIAL_PROVENANCE_CLASSES


def validate_provenance_class(provenance_class: str) -> str:
    if provenance_class not in PROVENANCE_CLASSES:
        raise ValueError(
            f"Unsupported provenance_class={provenance_class!r}; "
            f"expected one of {sorted(PROVENANCE_CLASSES)}"
        )
    return provenance_class


def assert_official_metric_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    bad = [
        str(row.get("verdict_id") or row.get("row_id") or idx)
        for idx, row in enumerate(rows)
        if not provenance_is_official(str(row.get("provenance_class") or "replay_derived"))
    ]
    if bad:
        raise ValueError(
            "Official performance metrics cannot include non-official provenance rows: "
            + ",".join(bad[:10])
        )


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def ensure_schema(db_path: Path) -> None:
    with connect_db(db_path) as con:
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS dataset_manifest (
              dataset_id TEXT PRIMARY KEY,
              created_at_utc TEXT NOT NULL,
              universe_json TEXT NOT NULL,
              root_path TEXT NOT NULL,
              manifest_path TEXT NOT NULL,
              status TEXT NOT NULL,
              official_provenance_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candle_coverage (
              dataset_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              required_minutes INTEGER NOT NULL,
              present_minutes INTEGER NOT NULL,
              missing_minutes INTEGER NOT NULL,
              raw_cache_files INTEGER NOT NULL,
              first_required_ms INTEGER,
              last_required_ms INTEGER,
              PRIMARY KEY (dataset_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS artifact_index (
              artifact_id TEXT PRIMARY KEY,
              dataset_id TEXT,
              run_id TEXT,
              artifact_type TEXT NOT NULL,
              path TEXT NOT NULL,
              sha256 TEXT,
              provenance_class TEXT NOT NULL CHECK (
                provenance_class IN ('exchange_real','runtime_observed','replay_derived','synthetic_stress')
              ),
              created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outcome_index (
              dataset_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              tf_sec INTEGER NOT NULL,
              bar_close_ts INTEGER NOT NULL,
              matched_trade INTEGER NOT NULL,
              source_path TEXT NOT NULL,
              provenance_class TEXT NOT NULL CHECK (
                provenance_class IN ('exchange_real','runtime_observed','replay_derived','synthetic_stress')
              ),
              PRIMARY KEY (dataset_id, symbol, tf_sec, bar_close_ts)
            );
            CREATE TABLE IF NOT EXISTS search_run (
              run_id TEXT PRIMARY KEY,
              dataset_id TEXT,
              created_at_utc TEXT NOT NULL,
              calibration_path TEXT NOT NULL,
              target_win_rate REAL NOT NULL,
              min_selected INTEGER NOT NULL,
              status TEXT NOT NULL,
              official_provenance_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidate_result (
              run_id TEXT NOT NULL,
              candidate_id TEXT NOT NULL,
              params_json TEXT NOT NULL,
              selected_count INTEGER NOT NULL,
              matched_count INTEGER NOT NULL,
              positive_net_count INTEGER NOT NULL,
              win_rate REAL,
              avg_net_return REAL,
              total_net_return REAL,
              acceptance_status TEXT NOT NULL,
              unsupported_params_json TEXT NOT NULL,
              PRIMARY KEY (run_id, candidate_id)
            );
            CREATE TABLE IF NOT EXISTS provenance_event (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              dataset_id TEXT,
              run_id TEXT,
              artifact_path TEXT,
              provenance_class TEXT NOT NULL CHECK (
                provenance_class IN ('exchange_real','runtime_observed','replay_derived','synthetic_stress')
              ),
              official_eligible INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feature_matrix_index (
              row_id TEXT PRIMARY KEY,
              dataset_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              tf_sec INTEGER NOT NULL,
              bar_close_ts INTEGER NOT NULL,
              feature_path TEXT NOT NULL,
              feature_hash TEXT NOT NULL,
              provenance_class TEXT NOT NULL CHECK (
                provenance_class IN ('exchange_real','runtime_observed','replay_derived','synthetic_stress')
              ),
              quality_status TEXT NOT NULL,
              created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS failure_diagnosis (
              dataset_id TEXT NOT NULL,
              verdict_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              tf_sec INTEGER NOT NULL,
              bar_close_ts INTEGER NOT NULL,
              failure_class TEXT NOT NULL,
              secondary_tags_json TEXT NOT NULL,
              net_return REAL,
              raw_return REAL,
              confidence REAL,
              regime TEXT,
              segment_key TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY (dataset_id, verdict_id, symbol, tf_sec, bar_close_ts)
            );
            CREATE TABLE IF NOT EXISTS ceiling_result (
              run_id TEXT NOT NULL,
              dataset_id TEXT NOT NULL,
              ceiling_name TEXT NOT NULL,
              selected_count INTEGER NOT NULL,
              win_rate REAL,
              avg_net_return REAL,
              status TEXT NOT NULL,
              details_json TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY (run_id, ceiling_name)
            );
            CREATE TABLE IF NOT EXISTS walkforward_split (
              run_id TEXT NOT NULL,
              dataset_id TEXT NOT NULL,
              split_name TEXT NOT NULL,
              start_ts INTEGER,
              end_ts INTEGER,
              row_count INTEGER NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY (run_id, split_name)
            );
            CREATE TABLE IF NOT EXISTS learned_policy_candidate (
              run_id TEXT NOT NULL,
              candidate_id TEXT NOT NULL,
              status TEXT NOT NULL,
              params_json TEXT NOT NULL,
              train_metrics_json TEXT NOT NULL,
              validation_metrics_json TEXT NOT NULL,
              holdout_metrics_json TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY (run_id, candidate_id)
            );
            CREATE TABLE IF NOT EXISTS policy_decision_trace (
              run_id TEXT NOT NULL,
              decision_id TEXT NOT NULL,
              candidate_id TEXT NOT NULL,
              verdict_id TEXT NOT NULL,
              action TEXT NOT NULL,
              reason TEXT NOT NULL,
              features_json TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY (run_id, decision_id)
            );
            """
        )
        migrate_failure_diagnosis_primary_key(con)


def migrate_failure_diagnosis_primary_key(con: sqlite3.Connection) -> None:
    rows = con.execute("PRAGMA table_info(failure_diagnosis)").fetchall()
    pk_cols = [row["name"] for row in sorted(rows, key=lambda item: item["pk"]) if row["pk"]]
    if pk_cols != ["dataset_id", "verdict_id"]:
        return
    con.executescript(
        """
        DROP TABLE failure_diagnosis;
        CREATE TABLE failure_diagnosis (
          dataset_id TEXT NOT NULL,
          verdict_id TEXT NOT NULL,
          symbol TEXT NOT NULL,
          tf_sec INTEGER NOT NULL,
          bar_close_ts INTEGER NOT NULL,
          failure_class TEXT NOT NULL,
          secondary_tags_json TEXT NOT NULL,
          net_return REAL,
          raw_return REAL,
          confidence REAL,
          regime TEXT,
          segment_key TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          PRIMARY KEY (dataset_id, verdict_id, symbol, tf_sec, bar_close_ts)
        );
        """
    )


def record_artifact(
    con: sqlite3.Connection,
    *,
    dataset_id: str | None,
    run_id: str | None,
    artifact_type: str,
    path: Path,
    provenance_class: str,
) -> None:
    provenance_class = validate_provenance_class(provenance_class)
    con.execute(
        """
        INSERT OR REPLACE INTO artifact_index (
          artifact_id, dataset_id, run_id, artifact_type, path, sha256,
          provenance_class, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stable_hash(
                {
                    "dataset_id": dataset_id,
                    "run_id": run_id,
                    "artifact_type": artifact_type,
                    "path": str(path),
                },
                length=24,
            ),
            dataset_id,
            run_id,
            artifact_type,
            str(path),
            sha256_file(path),
            provenance_class,
            utc_now_iso(),
        ),
    )


def record_provenance_event(
    con: sqlite3.Connection,
    *,
    dataset_id: str | None,
    run_id: str | None,
    artifact_path: Path | None,
    provenance_class: str,
    reason: str,
) -> None:
    provenance_class = validate_provenance_class(provenance_class)
    con.execute(
        """
        INSERT INTO provenance_event (
          dataset_id, run_id, artifact_path, provenance_class,
          official_eligible, reason, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            run_id,
            str(artifact_path) if artifact_path is not None else None,
            provenance_class,
            1 if provenance_is_official(provenance_class) else 0,
            reason,
            utc_now_iso(),
        ),
    )


@dataclass(frozen=True)
class CoverageArtifacts:
    coverage_report: Path
    missing_windows_jsonl: Path
    windows_csv: Path


def _coverage_rows_for_report(
    *,
    judge_logs_root: Path,
    raw_cache_root: Path,
    horizon_bars: int,
    symbols: Sequence[str],
    days_back: int | None = None,
) -> tuple[dict[str, Any], list[Any]]:
    from tools.judge import audit_and_backfill_1m_candles as candle_audit

    symbols_filter = {s.upper() for s in symbols if s and s != "*"} or None
    coverage_mode = "completed_utc_days" if days_back and days_back > 0 else "judge_window"
    completed_window = completed_utc_window_for_days(days_back) if days_back and days_back > 0 else None
    if completed_window:
        selected_symbols = sorted(symbols_filter or set(DEFAULT_UNIVERSE))
        start_close = int(completed_window["start_close_ms"])
        end_close = int(completed_window["end_close_ms"])
        date_cursor = datetime.fromtimestamp(start_close / 1000.0, tz=timezone.utc).date()
        end_date = datetime.fromtimestamp(end_close / 1000.0, tz=timezone.utc).date()
        dates: list[str] = []
        while date_cursor <= end_date:
            dates.append(date_cursor.isoformat())
            date_cursor += timedelta(days=1)
        judge_windows = {
            symbol: candle_audit.JudgeWindow(
                symbol=symbol,
                first_verdict_ts_ms=start_close,
                last_verdict_ts_ms=end_close,
                max_tf_sec=60,
                tf_secs=(60,),
                dates=tuple(dates),
                verdict_count=0,
            )
            for symbol in selected_symbols
        }
        effective_horizon_bars = 0
    else:
        judge_windows = candle_audit.scan_judge_windows(judge_logs_root, symbols_filter)
        effective_horizon_bars = horizon_bars
    if not judge_windows:
        return (
            {
                "schema_version": "alpha_factory_coverage_v1",
                "status": "no_judge_windows",
                "coverage_mode": coverage_mode,
                "completed_utc_window": completed_window,
                "judge_logs_root": str(judge_logs_root),
                "raw_cache_root": str(raw_cache_root),
                "horizon_bars": horizon_bars,
                "symbols": {},
                "totals": {
                    "required_minutes": 0,
                    "present_minutes": 0,
                    "missing_minutes": 0,
                    "missing_ranges": 0,
                },
            },
            [],
        )

    coverage = candle_audit.build_coverage_rows(
        judge_windows,
        horizon_bars=effective_horizon_bars,
        raw_cache_root=raw_cache_root,
    )
    missing_ranges = []
    for row in coverage.values():
        missing_ranges.extend(row.missing_ranges)

    payload = {
        "schema_version": "alpha_factory_coverage_v1",
        "status": "complete" if not missing_ranges else "missing_candles",
        "coverage_mode": coverage_mode,
        "completed_utc_window": completed_window,
        "generated_at_utc": utc_now_iso(),
        "judge_logs_root": str(judge_logs_root),
        "raw_cache_root": str(raw_cache_root),
        "horizon_bars": horizon_bars,
        "effective_horizon_bars": effective_horizon_bars,
        "symbols": {
            symbol: {
                "first_verdict_ts_ms": judge_windows[symbol].first_verdict_ts_ms,
                "last_verdict_ts_ms": judge_windows[symbol].last_verdict_ts_ms,
                "tf_secs": list(judge_windows[symbol].tf_secs),
                "dates": list(judge_windows[symbol].dates),
                "verdict_count": judge_windows[symbol].verdict_count,
                "required_minutes": coverage[symbol].required_minutes,
                "present_minutes": coverage[symbol].present_minutes,
                "missing_minutes": coverage[symbol].missing_minutes,
                "raw_cache_files": coverage[symbol].raw_cache_files,
                "first_required_ms": coverage[symbol].first_required_ms,
                "last_required_ms": coverage[symbol].last_required_ms,
                "missing_ranges": [
                    {
                        "start_close_ms": mr.start_close_ms,
                        "end_close_ms": mr.end_close_ms,
                        "missing_minutes": mr.missing_minutes,
                    }
                    for mr in coverage[symbol].missing_ranges
                ],
            }
            for symbol in sorted(judge_windows)
        },
        "totals": {
            "required_minutes": sum(row.required_minutes for row in coverage.values()),
            "present_minutes": sum(row.present_minutes for row in coverage.values()),
            "missing_minutes": sum(row.missing_minutes for row in coverage.values()),
            "missing_ranges": len(missing_ranges),
        },
    }
    return payload, missing_ranges


def write_coverage_artifacts(
    *,
    output_dir: Path,
    coverage_payload: Mapping[str, Any],
    missing_ranges: Sequence[Any],
) -> CoverageArtifacts:
    from tools.judge import audit_and_backfill_1m_candles as candle_audit

    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_report = output_dir / "coverage_report.json"
    missing_jsonl = output_dir / "missing_windows.jsonl"
    windows_csv = output_dir / "backfill_windows.csv"
    write_json(coverage_report, dict(coverage_payload))
    candle_audit.write_missing_jsonl(missing_jsonl, missing_ranges)
    candle_audit.write_windows_csv(windows_csv, missing_ranges)
    return CoverageArtifacts(
        coverage_report=coverage_report,
        missing_windows_jsonl=missing_jsonl,
        windows_csv=windows_csv,
    )


def upsert_coverage(
    con: sqlite3.Connection,
    *,
    dataset_id: str,
    coverage_payload: Mapping[str, Any],
) -> None:
    for symbol, row in dict(coverage_payload.get("symbols") or {}).items():
        con.execute(
            """
            INSERT OR REPLACE INTO candle_coverage (
              dataset_id, symbol, required_minutes, present_minutes,
              missing_minutes, raw_cache_files, first_required_ms, last_required_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                symbol,
                int(row.get("required_minutes") or 0),
                int(row.get("present_minutes") or 0),
                int(row.get("missing_minutes") or 0),
                int(row.get("raw_cache_files") or 0),
                row.get("first_required_ms"),
                row.get("last_required_ms"),
            ),
        )


def run_audit_data(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("audit")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    coverage_payload, missing_ranges = _coverage_rows_for_report(
        judge_logs_root=Path(args.judge_log_dir),
        raw_cache_root=Path(args.raw_1m_dir),
        horizon_bars=args.horizon_bars,
        symbols=parse_csv_arg(args.symbols) or list(DEFAULT_UNIVERSE),
        days_back=int(args.days_back) if args.days_back is not None else None,
    )
    artifacts = write_coverage_artifacts(
        output_dir=output_dir,
        coverage_payload=coverage_payload,
        missing_ranges=missing_ranges,
    )
    with connect_db(db_path) as con:
        for path, artifact_type in [
            (artifacts.coverage_report, "coverage_report"),
            (artifacts.missing_windows_jsonl, "missing_windows_jsonl"),
            (artifacts.windows_csv, "backfill_windows_csv"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=run_id,
                artifact_type=artifact_type,
                path=path,
                provenance_class="exchange_real",
            )
            record_provenance_event(
                con,
                dataset_id=args.dataset_id,
                run_id=run_id,
                artifact_path=path,
                provenance_class="exchange_real",
                reason="binance_usdm_1m_candle_coverage_audit",
            )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": coverage_payload["status"],
                "coverage_mode": coverage_payload.get("coverage_mode"),
                "missing_minutes": coverage_payload["totals"]["missing_minutes"],
                "coverage_report": str(artifacts.coverage_report),
                "windows_csv": str(artifacts.windows_csv),
            },
            sort_keys=True,
        )
    )
    return 0


def run_build_dataset(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    dataset_id = args.dataset_id or utc_run_id("ds")
    dataset_root = Path(args.data_root) / "datasets" / dataset_id
    coverage_payload, missing_ranges = _coverage_rows_for_report(
        judge_logs_root=Path(args.judge_log_dir),
        raw_cache_root=Path(args.raw_1m_dir),
        horizon_bars=args.horizon_bars,
        symbols=parse_csv_arg(args.symbols) or list(DEFAULT_UNIVERSE),
        days_back=int(args.days_back) if args.days_back is not None else None,
    )
    artifacts = write_coverage_artifacts(
        output_dir=dataset_root,
        coverage_payload=coverage_payload,
        missing_ranges=missing_ranges,
    )
    status = "ready" if coverage_payload["totals"]["missing_minutes"] == 0 else "missing_candles"
    manifest = {
        "schema_version": "alpha_factory_dataset_manifest_v1",
        "dataset_id": dataset_id,
        "created_at_utc": utc_now_iso(),
        "status": status,
        "coverage_mode": coverage_payload.get("coverage_mode"),
        "completed_utc_window": coverage_payload.get("completed_utc_window"),
        "official_default_days_back": 90,
        "universe": sorted((coverage_payload.get("symbols") or {}).keys()),
        "source_paths": {
            "judge_log_dir": str(Path(args.judge_log_dir)),
            "raw_1m_dir": str(Path(args.raw_1m_dir)),
            "recorder_1m_dir": str(Path(args.recorder_1m_dir)),
        },
        "provenance_policy": {
            "classes": list(PROVENANCE_CLASSES),
            "official_metric_allowed": sorted(OFFICIAL_PROVENANCE_CLASSES),
            "synthetic_stress_official_metrics": "forbidden",
        },
        "artifacts": {
            "coverage_report": str(artifacts.coverage_report),
            "missing_windows_jsonl": str(artifacts.missing_windows_jsonl),
            "backfill_windows_csv": str(artifacts.windows_csv),
        },
    }
    manifest_path = dataset_root / "dataset_manifest.json"
    write_json(manifest_path, manifest)

    with connect_db(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO dataset_manifest (
              dataset_id, created_at_utc, universe_json, root_path,
              manifest_path, status, official_provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                manifest["created_at_utc"],
                json.dumps(manifest["universe"], sort_keys=True),
                str(dataset_root),
                str(manifest_path),
                status,
                json.dumps(sorted(OFFICIAL_PROVENANCE_CLASSES)),
            ),
        )
        upsert_coverage(con, dataset_id=dataset_id, coverage_payload=coverage_payload)
        for path, artifact_type in [
            (manifest_path, "dataset_manifest"),
            (artifacts.coverage_report, "coverage_report"),
            (artifacts.missing_windows_jsonl, "missing_windows_jsonl"),
            (artifacts.windows_csv, "backfill_windows_csv"),
        ]:
            record_artifact(
                con,
                dataset_id=dataset_id,
                run_id=None,
                artifact_type=artifact_type,
                path=path,
                provenance_class="runtime_observed" if artifact_type == "dataset_manifest" else "exchange_real",
            )
        record_provenance_event(
            con,
            dataset_id=dataset_id,
            run_id=None,
            artifact_path=manifest_path,
            provenance_class="runtime_observed",
            reason="dataset_manifest_created_from_current_judge_window",
        )

    print(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "status": status,
                "manifest": str(manifest_path),
                "missing_minutes": coverage_payload["totals"]["missing_minutes"],
            },
            sort_keys=True,
        )
    )
    return 0


def dataset_root_for(data_root: Path, dataset_id: str) -> Path:
    return data_root / "datasets" / dataset_id


def run_materialize_outcomes(args: argparse.Namespace) -> int:
    from tools.judge import build_outcomes_from_candles as materializer

    db_path = Path(args.db)
    ensure_schema(db_path)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_root / "outcomes"
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / "outcomes.json"
    manifest_path = output_dir / "outcomes_manifest.json"
    skipped_path = output_dir / "outcomes_skipped.jsonl"
    diagnostics_path = output_dir / "outcomes_diagnostics.jsonl"
    report_path = output_dir / "PKG_1_JUDGE_OUTCOMES_MATERIALIZER_REPORT.md"

    rc = materializer.main(
        [
            "--judge-log-dir",
            str(Path(args.judge_log_dir)),
            "--raw-1m-dir",
            str(Path(args.raw_1m_dir)),
            "--recorder-1m-dir",
            str(Path(args.recorder_1m_dir)),
            "--simulator-config",
            str(Path(args.simulator_config)),
            "--outcomes-path",
            str(outcomes_path),
            "--manifest-path",
            str(manifest_path),
            "--skipped-path",
            str(skipped_path),
            "--diagnostics-path",
            str(diagnostics_path),
            "--report-path",
            str(report_path),
            "--horizon-bars",
            str(args.horizon_bars),
            "--write-report",
        ]
    )
    if rc != 0:
        print(json.dumps({"status": "materialize_failed", "returncode": rc}, sort_keys=True))
        return rc

    outcome_count = 0
    payload = json.loads(outcomes_path.read_text(encoding="utf-8"))
    with connect_db(db_path) as con:
        for outcome in payload.get("outcomes", []):
            outcome_count += 1
            con.execute(
                """
                INSERT OR REPLACE INTO outcome_index (
                  dataset_id, symbol, tf_sec, bar_close_ts, matched_trade,
                  source_path, provenance_class
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.dataset_id,
                    str(outcome["symbol"]),
                    int(outcome["tf_sec"]),
                    int(outcome["bar_close_ts"]),
                    1 if outcome.get("matched_trade") else 0,
                    str(outcomes_path),
                    "replay_derived",
                ),
            )
        for path, artifact_type in [
            (outcomes_path, "outcomes_json"),
            (manifest_path, "outcomes_manifest"),
            (skipped_path, "outcomes_skipped"),
            (diagnostics_path, "outcomes_diagnostics"),
            (report_path, "outcomes_report"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=None,
                artifact_type=artifact_type,
                path=path,
                provenance_class="replay_derived",
            )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=None,
            artifact_path=outcomes_path,
            provenance_class="replay_derived",
            reason="outcomes_materialized_from_real_candles_and_shadow_verdicts",
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "dataset_id": args.dataset_id,
                "outcomes": outcome_count,
                "outcomes_path": str(outcomes_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def run_baseline(args: argparse.Namespace) -> int:
    from apps.reference.domains.alpha_search.judge.review import cli as review_cli
    from apps.reference.domains.alpha_search.judge.simulator import cli as simulator_cli

    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("baseline")
    run_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    outcomes_path = Path(args.outcomes_path) if args.outcomes_path else dataset_root / "outcomes" / "outcomes.json"

    sim_yaml = _load_yaml(Path(args.simulator_config))
    sim_section = dict(sim_yaml.get("judge_simulator") or {})
    sim_section["outcome_data_path"] = str(outcomes_path)
    sim_section["calibration_dataset_path"] = str(run_dir / "phase5_calibration.jsonl")
    sim_section["summary_report_path"] = str(run_dir / "phase5_summary_report.json")
    generated_sim_config = run_dir / "judge_simulator.generated.yaml"
    write_json(run_dir / "source_config_manifest.json", {
        "simulator_config_source": str(Path(args.simulator_config)),
        "review_config_source": str(Path(args.review_config)),
        "source_configs_not_modified": True,
    })
    atomic_write_text(
        generated_sim_config,
        yaml.safe_dump({"judge_simulator": sim_section}, sort_keys=False),
    )

    sim_rc = simulator_cli.main(["--config", str(generated_sim_config)])
    review_rc = 0
    generated_review_config = run_dir / "judge_review.generated.yaml"
    if sim_rc == 0:
        review_yaml = _load_yaml(Path(args.review_config))
        review_section = dict(review_yaml.get("judge_review") or {})
        review_section["judge_simulator_config_path"] = str(generated_sim_config)
        review_section["output_dir"] = str(run_dir / "judge_review")
        atomic_write_text(
            generated_review_config,
            yaml.safe_dump({"judge_review": review_section}, sort_keys=False),
        )
        review_rc = review_cli.main(["--config", str(generated_review_config)])

    status = "ok" if sim_rc == 0 and review_rc == 0 else "failed"
    with connect_db(db_path) as con:
        for path, artifact_type in [
            (generated_sim_config, "generated_simulator_config"),
            (generated_review_config, "generated_review_config"),
            (run_dir / "phase5_calibration.jsonl", "phase5_calibration"),
            (run_dir / "phase5_summary_report.json", "phase5_summary"),
            (run_dir / "judge_review" / "review_bundle.json", "review_bundle"),
            (run_dir / "judge_review" / "review_summary.md", "review_summary"),
        ]:
            if path.exists():
                record_artifact(
                    con,
                    dataset_id=args.dataset_id,
                    run_id=run_id,
                    artifact_type=artifact_type,
                    path=path,
                    provenance_class="replay_derived",
                )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=run_dir,
            provenance_class="replay_derived",
            reason="baseline_simulator_and_review_generated_from_run_config_copy",
        )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": status,
                "simulator_returncode": sim_rc,
                "review_returncode": review_rc,
                "output_dir": str(run_dir),
            },
            sort_keys=True,
        )
    )
    return 0 if status == "ok" else 3


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_regime_by_verdict(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    out: dict[str, str] = {}
    for row in read_jsonl(path):
        vid = row.get("verdict_id")
        if vid:
            out[str(vid)] = str(row.get("regime") or "UNKNOWN")
    return out


def load_calibration_rows(calibration_path: Path, path_diagnostics: Path | None = None) -> list[dict[str, Any]]:
    regime_by_verdict = _load_regime_by_verdict(path_diagnostics)
    rows = read_jsonl(calibration_path)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["symbol"] = str(copy.get("symbol") or "").upper()
        copy["tf_sec"] = int(copy.get("tf_sec") or 0)
        copy["bar_close_ts"] = int(copy.get("bar_close_ts") or 0)
        copy["confidence"] = coerce_float(copy.get("confidence")) or 0.0
        copy["net_return"] = coerce_float(copy.get("net_return"))
        copy["provenance_class"] = str(copy.get("provenance_class") or "replay_derived")
        copy["regime"] = str(copy.get("regime") or regime_by_verdict.get(str(copy.get("verdict_id")), "ALL"))
        normalized.append(copy)
    return normalized


def _matches_param(value: Any, selector: str) -> bool:
    return selector == "*" or str(value) == selector


def _apply_min_spacing(rows: Sequence[dict[str, Any]], min_spacing_bars: int) -> list[dict[str, Any]]:
    if min_spacing_bars <= 0:
        return list(rows)
    selected: list[dict[str, Any]] = []
    last_by_key: dict[tuple[str, int], int] = {}
    for row in sorted(rows, key=lambda r: (r["symbol"], r["tf_sec"], r["bar_close_ts"], r.get("verdict_id", ""))):
        key = (str(row["symbol"]), int(row["tf_sec"]))
        last_ts = last_by_key.get(key)
        required_gap_ms = int(row["tf_sec"]) * 1000 * min_spacing_bars
        if last_ts is not None and int(row["bar_close_ts"]) < last_ts + required_gap_ms:
            continue
        selected.append(row)
        last_by_key[key] = int(row["bar_close_ts"])
    return selected


def evaluate_candidate(
    rows: Sequence[dict[str, Any]],
    *,
    params: Mapping[str, Any],
    target_win_rate: float,
    min_selected: int,
) -> dict[str, Any]:
    official_rows = [
        row
        for row in rows
        if provenance_is_official(str(row.get("provenance_class") or "replay_derived"))
    ]
    assert_official_metric_rows(official_rows)
    selected = [
        row
        for row in official_rows
        if row.get("entry_verdict") in ACTIONABLE_VERDICTS
        and (coerce_float(row.get("net_return")) is not None)
        and float(row.get("confidence") or 0.0) >= float(params["confidence_min"])
        and _matches_param(row.get("symbol"), str(params["symbol"]))
        and _matches_param(row.get("tf_sec"), str(params["tf_sec"]))
        and _matches_param(row.get("regime"), str(params["regime"]))
    ]
    selected = _apply_min_spacing(selected, int(params["min_spacing_bars"]))
    net_returns = [float(row["net_return"]) for row in selected if row.get("net_return") is not None]
    positive = sum(1 for value in net_returns if value > 0.0)
    negative = sum(1 for value in net_returns if value < 0.0)
    selected_count = len(net_returns)
    win_rate = positive / selected_count if selected_count else None
    avg_net = sum(net_returns) / selected_count if selected_count else None
    total_net = sum(net_returns) if selected_count else None

    if selected_count < min_selected:
        acceptance_status = "INSUFFICIENT_EVIDENCE"
    elif win_rate is not None and avg_net is not None and win_rate >= target_win_rate and avg_net > 0.0:
        acceptance_status = "PASS_CANDIDATE_SHADOW_ONLY"
    else:
        acceptance_status = "FAIL_CANDIDATE"

    unsupported = []
    if params.get("tp_offset_pct") != "existing":
        unsupported.append("tp_offset_pct_not_recomputed_from_candles")
    if params.get("sl_offset_pct") != "existing":
        unsupported.append("sl_offset_pct_not_recomputed_from_candles")
    if params.get("hold_horizon_bars") != "existing":
        unsupported.append("hold_horizon_bars_not_recomputed_in_search")

    return {
        "candidate_id": stable_hash(params),
        "params": dict(params),
        "selected_count": selected_count,
        "matched_count": selected_count,
        "positive_net_count": positive,
        "negative_net_count": negative,
        "win_rate": win_rate,
        "avg_net_return": avg_net,
        "total_net_return": total_net,
        "acceptance_status": acceptance_status,
        "unsupported_params": unsupported,
        "official_metric_provenance": sorted(OFFICIAL_PROVENANCE_CLASSES),
    }


def generate_candidate_params(
    rows: Sequence[dict[str, Any]],
    *,
    confidence_thresholds: Sequence[float],
    symbols: Sequence[str],
    tf_secs: Sequence[str],
    regimes: Sequence[str],
    min_spacing_bars: Sequence[int],
    tp_offsets: Sequence[str],
    sl_offsets: Sequence[str],
    hold_horizons: Sequence[str],
) -> list[dict[str, Any]]:
    derived_symbols = sorted({str(row["symbol"]) for row in rows if row.get("symbol")})
    derived_tfs = sorted({str(row["tf_sec"]) for row in rows if row.get("tf_sec")})
    derived_regimes = sorted({str(row.get("regime") or "ALL") for row in rows})
    symbols_final = list(symbols) if symbols else ["*", *derived_symbols]
    tf_secs_final = list(tf_secs) if tf_secs else ["*", *derived_tfs]
    regimes_final = list(regimes) if regimes else ["*"] + [r for r in derived_regimes if r != "ALL"]
    params: list[dict[str, Any]] = []
    for confidence_min in confidence_thresholds:
        for symbol in symbols_final:
            for tf_sec in tf_secs_final:
                for regime in regimes_final:
                    for spacing in min_spacing_bars:
                        for tp in tp_offsets:
                            for sl in sl_offsets:
                                for horizon in hold_horizons:
                                    params.append(
                                        {
                                            "confidence_min": float(confidence_min),
                                            "symbol": str(symbol),
                                            "tf_sec": str(tf_sec),
                                            "regime": str(regime),
                                            "min_spacing_bars": int(spacing),
                                            "tp_offset_pct": str(tp),
                                            "sl_offset_pct": str(sl),
                                            "hold_horizon_bars": str(horizon),
                                        }
                                    )
    return params


def _sort_candidate_results(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {
        "PASS_CANDIDATE_SHADOW_ONLY": 0,
        "FAIL_CANDIDATE": 1,
        "INSUFFICIENT_EVIDENCE": 2,
    }
    return sorted(
        rows,
        key=lambda r: (
            status_rank.get(str(r["acceptance_status"]), 99),
            -(r["win_rate"] or 0.0),
            -(r["avg_net_return"] or -999.0),
            -int(r["selected_count"]),
            str(r["candidate_id"]),
        ),
    )


def run_search_candidates(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("search")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_path = Path(args.calibration_path)
    rows = load_calibration_rows(
        calibration_path,
        Path(args.path_diagnostics) if args.path_diagnostics else None,
    )
    params = generate_candidate_params(
        rows,
        confidence_thresholds=parse_float_csv(args.confidence_thresholds, [0.0, 0.25, 0.5, 0.75]),
        symbols=parse_csv_arg(args.symbols),
        tf_secs=parse_csv_arg(args.tf_secs),
        regimes=parse_csv_arg(args.regimes),
        min_spacing_bars=parse_int_csv(args.min_spacing_bars, [0, 3, 6, 12]),
        tp_offsets=parse_csv_arg(args.tp_offsets) or ["existing"],
        sl_offsets=parse_csv_arg(args.sl_offsets) or ["existing"],
        hold_horizons=parse_csv_arg(args.hold_horizons) or ["existing"],
    )
    results = _sort_candidate_results(
        [
            evaluate_candidate(
                rows,
                params=param,
                target_win_rate=float(args.target_win_rate),
                min_selected=int(args.min_selected),
            )
            for param in params
        ]
    )
    results_path = output_dir / "search_results.jsonl"
    leaderboard_path = output_dir / "candidate_leaderboard.csv"
    summary_path = output_dir / "search_summary.json"
    write_jsonl(results_path, results)
    leaderboard_rows = [
        {
            "rank": idx + 1,
            "candidate_id": row["candidate_id"],
            "acceptance_status": row["acceptance_status"],
            "selected_count": row["selected_count"],
            "win_rate": row["win_rate"],
            "avg_net_return": row["avg_net_return"],
            "total_net_return": row["total_net_return"],
            "params_json": json.dumps(row["params"], sort_keys=True),
            "unsupported_params_json": json.dumps(row["unsupported_params"], sort_keys=True),
        }
        for idx, row in enumerate(results)
    ]
    write_csv(
        leaderboard_path,
        leaderboard_rows,
        [
            "rank",
            "candidate_id",
            "acceptance_status",
            "selected_count",
            "win_rate",
            "avg_net_return",
            "total_net_return",
            "params_json",
            "unsupported_params_json",
        ],
    )
    pass_count = sum(1 for row in results if row["acceptance_status"] == "PASS_CANDIDATE_SHADOW_ONLY")
    summary = {
        "schema_version": "alpha_factory_search_summary_v1",
        "run_id": run_id,
        "dataset_id": args.dataset_id,
        "created_at_utc": utc_now_iso(),
        "calibration_path": str(calibration_path),
        "candidate_count": len(results),
        "pass_count": pass_count,
        "target_win_rate": float(args.target_win_rate),
        "min_selected": int(args.min_selected),
        "status": "CANDIDATE_FOUND_SHADOW_ONLY" if pass_count else "INSUFFICIENT_EVIDENCE",
        "top_candidate": results[0] if results else None,
        "official_metric_provenance": sorted(OFFICIAL_PROVENANCE_CLASSES),
        "synthetic_stress_official_metrics": "excluded",
    }
    write_json(summary_path, summary)

    with connect_db(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO search_run (
              run_id, dataset_id, created_at_utc, calibration_path,
              target_win_rate, min_selected, status, official_provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                args.dataset_id,
                summary["created_at_utc"],
                str(calibration_path),
                float(args.target_win_rate),
                int(args.min_selected),
                summary["status"],
                json.dumps(summary["official_metric_provenance"], sort_keys=True),
            ),
        )
        for row in results:
            con.execute(
                """
                INSERT OR REPLACE INTO candidate_result (
                  run_id, candidate_id, params_json, selected_count,
                  matched_count, positive_net_count, win_rate, avg_net_return,
                  total_net_return, acceptance_status, unsupported_params_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row["candidate_id"],
                    json.dumps(row["params"], sort_keys=True),
                    int(row["selected_count"]),
                    int(row["matched_count"]),
                    int(row["positive_net_count"]),
                    row["win_rate"],
                    row["avg_net_return"],
                    row["total_net_return"],
                    row["acceptance_status"],
                    json.dumps(row["unsupported_params"], sort_keys=True),
                ),
            )
        for path, artifact_type in [
            (results_path, "search_results"),
            (leaderboard_path, "candidate_leaderboard"),
            (summary_path, "search_summary"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=run_id,
                artifact_type=artifact_type,
                path=path,
                provenance_class="replay_derived",
            )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=summary_path,
            provenance_class="replay_derived",
            reason="deterministic_candidate_search_excluding_synthetic_stress",
        )

    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": summary["status"],
                "candidate_count": len(results),
                "pass_count": pass_count,
                "leaderboard": str(leaderboard_path),
                "summary": str(summary_path),
            },
            sort_keys=True,
        )
    )
    return 0


def confidence_bucket(confidence: Any) -> str:
    value = coerce_float(confidence)
    if value is None:
        return "UNKNOWN"
    value = _clip(value, 0.0, 1.0)
    for lo, hi, label in FIXED_CONFIDENCE_BUCKETS:
        if lo <= value < hi:
            return label
    return "[0.75,1.00]"


def utc_hour_from_ms(ts_ms: Any) -> int | None:
    ts = coerce_int(ts_ms)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).hour


def _diagnostic_lookup(path: Path | None) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int, int], dict[str, Any]]]:
    by_verdict: dict[str, dict[str, Any]] = {}
    by_key: dict[tuple[str, int, int], dict[str, Any]] = {}
    if path is None or not path.exists():
        return by_verdict, by_key
    for row in read_jsonl(path):
        verdict_id = row.get("verdict_id")
        if verdict_id:
            by_verdict[str(verdict_id)] = row
        corr = row.get("correlation_key") if isinstance(row.get("correlation_key"), dict) else {}
        symbol = str(row.get("symbol") or corr.get("symbol") or "").upper()
        tf_sec = coerce_int(row.get("tf_sec") or corr.get("tf_sec"))
        bar_close_ts = coerce_int(row.get("bar_close_ts") or corr.get("bar_close_ts"))
        if symbol and tf_sec is not None and bar_close_ts is not None:
            by_key[(symbol, tf_sec, bar_close_ts)] = row
    return by_verdict, by_key


def diagnostic_for_row(
    row: Mapping[str, Any],
    by_verdict: Mapping[str, Mapping[str, Any]],
    by_key: Mapping[tuple[str, int, int], Mapping[str, Any]],
) -> dict[str, Any]:
    verdict_id = str(row.get("verdict_id") or "")
    if verdict_id and verdict_id in by_verdict:
        return dict(by_verdict[verdict_id])
    symbol = str(row.get("symbol") or "").upper()
    tf_sec = coerce_int(row.get("tf_sec"))
    bar_close_ts = coerce_int(row.get("bar_close_ts"))
    if symbol and tf_sec is not None and bar_close_ts is not None:
        return dict(by_key.get((symbol, tf_sec, bar_close_ts), {}))
    return {}


def classify_failure(row: Mapping[str, Any], diagnostic: Mapping[str, Any] | None = None) -> tuple[str, list[str]]:
    diagnostic = diagnostic or {}
    tags: list[str] = []
    provenance = str(row.get("provenance_class") or "replay_derived")
    entry_verdict = str(row.get("entry_verdict") or "")
    optimal_action = str(row.get("optimal_action") or "")
    net_return = coerce_float(row.get("net_return"))
    raw_return = coerce_float(row.get("raw_return"))
    fee_cost = coerce_float(row.get("fee_cost")) or 0.0
    slippage_cost = coerce_float(row.get("slippage_cost")) or 0.0
    confidence = coerce_float(row.get("confidence")) or 0.0
    exit_class = str(
        diagnostic.get("exit_classification")
        or diagnostic.get("exit_class")
        or row.get("exit_classification")
        or ""
    ).upper()
    regime = str(diagnostic.get("regime") or row.get("regime") or "")
    stale_bars = coerce_int(diagnostic.get("regime_stale_bars"))

    if not provenance_is_official(provenance):
        return "DATA_GAP", ["NON_OFFICIAL_PROVENANCE"]
    if not regime or regime in {"UNKNOWN", "ALL", "NONE"} or (stale_bars is not None and stale_bars > 3):
        tags.append("REGIME_MISCLASSIFIED")
    if confidence >= 0.75 and net_return is not None and net_return <= 0.0:
        tags.append("CONFIDENCE_MISORDERED")

    if entry_verdict not in ACTIONABLE_VERDICTS:
        return "NO_ACTIONABLE_PLAN", tags
    if net_return is None:
        if exit_class == "NO_FILL":
            return "NO_FILL", tags
        return "DATA_GAP", tags
    if net_return > 0.0:
        return "CORRECT_ENTRY", tags

    total_cost = fee_cost + slippage_cost
    if raw_return is not None and raw_return > 0.0 and raw_return <= total_cost + 1e-12:
        return "FEE_SLIPPAGE_KILLED", tags
    if raw_return is not None and raw_return > 0.0 and net_return <= 0.0:
        return "RAW_RIGHT_NET_WRONG", tags
    if exit_class == "NO_FILL":
        return "NO_FILL", tags
    if exit_class == "TIMEOUT":
        if raw_return is not None and raw_return > 0.0:
            return "TIMEOUT_WITH_EDGE", tags
        return "TIMEOUT_NO_EDGE", tags
    if exit_class == "FILLED_SL":
        entry_price = coerce_float(diagnostic.get("entry_price"))
        mfe = abs(coerce_float(diagnostic.get("mfe")) or 0.0)
        mfe_return = mfe / entry_price if entry_price and entry_price > 0 else 0.0
        if mfe_return > total_cost:
            return "ENTRY_OK_EXIT_BAD", tags
        return "WRONG_DIRECTION", tags
    if optimal_action in ACTIONABLE_VERDICTS and optimal_action != entry_verdict:
        return "WRONG_DIRECTION", tags
    if "CONFIDENCE_MISORDERED" in tags:
        return "CONFIDENCE_MISORDERED", [tag for tag in tags if tag != "CONFIDENCE_MISORDERED"]
    return "WRONG_DIRECTION", tags


def _segment_key(row: Mapping[str, Any], failure_class: str) -> str:
    return "|".join(
        [
            f"symbol={row.get('symbol')}",
            f"tf_sec={row.get('tf_sec')}",
            f"regime={row.get('regime') or 'UNKNOWN'}",
            f"confidence_bucket={row.get('confidence_bucket')}",
            f"failure_class={failure_class}",
        ]
    )


def run_diagnose_failures(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_root
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_path = Path(args.calibration_path)
    diagnostics_path = Path(args.outcomes_diagnostics_path) if args.outcomes_diagnostics_path else dataset_root / "outcomes" / "outcomes_diagnostics.jsonl"
    rows = load_calibration_rows(calibration_path, diagnostics_path if diagnostics_path.exists() else None)
    by_verdict, by_key = _diagnostic_lookup(diagnostics_path if diagnostics_path.exists() else None)

    diagnosis_rows: list[dict[str, Any]] = []
    segment_counts: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        diagnostic = diagnostic_for_row(row, by_verdict, by_key)
        merged_regime = str(row.get("regime") or diagnostic.get("regime") or "UNKNOWN")
        row["regime"] = merged_regime
        failure_class, secondary_tags = classify_failure(row, diagnostic)
        bucket = confidence_bucket(row.get("confidence"))
        hour = utc_hour_from_ms(row.get("bar_close_ts"))
        segment_key = _segment_key(
            {
                "symbol": row.get("symbol"),
                "tf_sec": row.get("tf_sec"),
                "regime": merged_regime,
                "confidence_bucket": bucket,
            },
            failure_class,
        )
        out = {
            "schema_version": "alpha_factory_failure_taxonomy_v1",
            "dataset_id": args.dataset_id,
            "verdict_id": str(row.get("verdict_id") or stable_hash(row)),
            "symbol": row.get("symbol"),
            "tf_sec": row.get("tf_sec"),
            "bar_close_ts": row.get("bar_close_ts"),
            "utc_hour": hour,
            "entry_verdict": row.get("entry_verdict"),
            "optimal_action": row.get("optimal_action"),
            "confidence": row.get("confidence"),
            "confidence_bucket": bucket,
            "regime": merged_regime,
            "exit_classification": diagnostic.get("exit_classification"),
            "matched_trade": row.get("matched_trade"),
            "raw_return": row.get("raw_return"),
            "net_return": row.get("net_return"),
            "failure_class": failure_class,
            "secondary_tags": sorted(set(secondary_tags)),
            "segment_key": segment_key,
            "provenance_class": row.get("provenance_class") or "replay_derived",
        }
        diagnosis_rows.append(out)
        key = (
            str(out["symbol"]),
            str(out["tf_sec"]),
            str(merged_regime),
            str(bucket),
            str(failure_class),
        )
        agg = segment_counts.setdefault(
            key,
            {
                "symbol": out["symbol"],
                "tf_sec": out["tf_sec"],
                "regime": merged_regime,
                "confidence_bucket": bucket,
                "failure_class": failure_class,
                "record_count": 0,
                "positive_net_count": 0,
                "negative_net_count": 0,
                "avg_net_return_sum": 0.0,
                "avg_net_return_n": 0,
            },
        )
        agg["record_count"] += 1
        net = coerce_float(out.get("net_return"))
        if net is not None:
            agg["avg_net_return_sum"] += net
            agg["avg_net_return_n"] += 1
            if net > 0:
                agg["positive_net_count"] += 1
            elif net < 0:
                agg["negative_net_count"] += 1

    failure_path = output_dir / "failure_taxonomy.jsonl"
    segment_path = output_dir / "segment_diagnostics.csv"
    summary_path = output_dir / "failure_diagnostics_summary.json"
    write_jsonl(failure_path, diagnosis_rows)
    segment_rows = []
    for agg in segment_counts.values():
        n = int(agg.pop("avg_net_return_n"))
        total = float(agg.pop("avg_net_return_sum"))
        agg["avg_net_return"] = total / n if n else None
        segment_rows.append(agg)
    segment_rows = sorted(
        segment_rows,
        key=lambda r: (
            str(r["symbol"]),
            int(r["tf_sec"] or 0),
            str(r["regime"]),
            str(r["confidence_bucket"]),
            str(r["failure_class"]),
        ),
    )
    write_csv(
        segment_path,
        segment_rows,
        [
            "symbol",
            "tf_sec",
            "regime",
            "confidence_bucket",
            "failure_class",
            "record_count",
            "positive_net_count",
            "negative_net_count",
            "avg_net_return",
        ],
    )
    failure_counts: dict[str, int] = {}
    for row in diagnosis_rows:
        failure_counts[str(row["failure_class"])] = failure_counts.get(str(row["failure_class"]), 0) + 1
    summary = {
        "schema_version": "alpha_factory_failure_diagnostics_summary_v1",
        "dataset_id": args.dataset_id,
        "calibration_path": str(calibration_path),
        "outcomes_diagnostics_path": str(diagnostics_path),
        "row_count": len(diagnosis_rows),
        "failure_counts": dict(sorted(failure_counts.items())),
        "status": "ok" if diagnosis_rows else "NO_ROWS",
        "artifacts": {
            "failure_taxonomy": str(failure_path),
            "segment_diagnostics": str(segment_path),
        },
    }
    write_json(summary_path, summary)
    with connect_db(db_path) as con:
        for out in diagnosis_rows:
            con.execute(
                """
                INSERT OR REPLACE INTO failure_diagnosis (
                  dataset_id, verdict_id, symbol, tf_sec, bar_close_ts,
                  failure_class, secondary_tags_json, net_return, raw_return,
                  confidence, regime, segment_key, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.dataset_id,
                    out["verdict_id"],
                    out["symbol"],
                    int(out["tf_sec"] or 0),
                    int(out["bar_close_ts"] or 0),
                    out["failure_class"],
                    json.dumps(out["secondary_tags"], sort_keys=True),
                    out["net_return"],
                    out["raw_return"],
                    out["confidence"],
                    out["regime"],
                    out["segment_key"],
                    utc_now_iso(),
                ),
            )
        for path, artifact_type in [
            (failure_path, "failure_taxonomy"),
            (segment_path, "segment_diagnostics"),
            (summary_path, "failure_diagnostics_summary"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=None,
                artifact_type=artifact_type,
                path=path,
                provenance_class="replay_derived",
            )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=None,
            artifact_path=summary_path,
            provenance_class="replay_derived",
            reason="failure_taxonomy_joined_from_calibration_and_path_diagnostics",
        )
    print(json.dumps({"status": summary["status"], "rows": len(diagnosis_rows), "summary": str(summary_path)}, sort_keys=True))
    return 0


def _raw_cache_files(raw_root: Path, symbol: str) -> list[Path]:
    symbol = symbol.upper()
    candidates: list[Path] = []
    direct = raw_root / symbol
    if direct.is_dir():
        candidates.extend(sorted(direct.glob("*.json")))
        candidates.extend(sorted(direct.glob("*.csv")))
    candidates.extend(sorted(raw_root.glob(f"**/{symbol}*.json")))
    candidates.extend(sorted(raw_root.glob(f"**/{symbol}*.csv")))
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen and path.is_file():
            seen.add(resolved)
            out.append(path)
    return out


def load_raw_1m_candles(raw_root: Path, symbol: str) -> list[dict[str, Any]]:
    by_close: dict[int, dict[str, Any]] = {}
    for path in _raw_cache_files(raw_root, symbol):
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            klines = payload.get("klines") if isinstance(payload, dict) else payload
            if not isinstance(klines, list):
                continue
            for kline in klines:
                if not isinstance(kline, list) or len(kline) < 6:
                    continue
                open_ms = coerce_int(kline[0])
                close_ms = coerce_int(kline[6] if len(kline) > 6 else None)
                if open_ms is None:
                    continue
                if close_ms is None:
                    close_ms = open_ms + MINUTE_MS - 1
                by_close[close_ms] = {
                    "timestamp": close_ms,
                    "open_time_ms": open_ms,
                    "symbol": symbol.upper(),
                    "open": coerce_float(kline[1]),
                    "high": coerce_float(kline[2]),
                    "low": coerce_float(kline[3]),
                    "close": coerce_float(kline[4]),
                    "volume": coerce_float(kline[5]),
                    "trade_count": coerce_int(kline[8] if len(kline) > 8 else None),
                    "source_path": str(path),
                }
        elif path.suffix.lower() == ".csv":
            for row in load_rows_any(path):
                close_ms = coerce_int(row.get("timestamp") or row.get("close_time_ms") or row.get("bar_close_ts"))
                if close_ms is None:
                    continue
                by_close[close_ms] = {
                    "timestamp": close_ms,
                    "symbol": str(row.get("symbol") or symbol).upper(),
                    "open": coerce_float(row.get("open")),
                    "high": coerce_float(row.get("high")),
                    "low": coerce_float(row.get("low")),
                    "close": coerce_float(row.get("close")),
                    "volume": coerce_float(row.get("volume")),
                    "trade_count": coerce_int(row.get("trade_count")),
                    "source_path": str(path),
                }
    return [by_close[ts] for ts in sorted(by_close)]


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _ret_between(candles: Sequence[Mapping[str, Any]], idx: int, lookback: int) -> float | None:
    if idx - lookback < 0:
        return None
    current = coerce_float(candles[idx].get("close"))
    previous = coerce_float(candles[idx - lookback].get("close"))
    if current is None or previous is None or previous <= 0:
        return None
    return current / previous - 1.0


def _realized_vol(candles: Sequence[Mapping[str, Any]], idx: int, lookback: int) -> float | None:
    if idx - lookback < 0:
        return None
    returns = []
    start = idx - lookback + 1
    for i in range(start, idx + 1):
        ret = _ret_between(candles, i, 1)
        if ret is not None:
            returns.append(ret)
    return _std(returns)


def _atr_ratio(candles: Sequence[Mapping[str, Any]], idx: int, lookback: int) -> float | None:
    if idx - lookback + 1 < 0:
        return None
    ratios = []
    for candle in candles[idx - lookback + 1 : idx + 1]:
        high = coerce_float(candle.get("high"))
        low = coerce_float(candle.get("low"))
        close = coerce_float(candle.get("close"))
        if high is not None and low is not None and close and close > 0:
            ratios.append((high - low) / close)
    return _mean(ratios)


def _volume_zscore(candles: Sequence[Mapping[str, Any]], idx: int, lookback: int) -> float | None:
    if idx - lookback + 1 < 0:
        return None
    values = [coerce_float(c.get("volume")) for c in candles[idx - lookback + 1 : idx + 1]]
    volumes = [float(v) for v in values if v is not None]
    if len(volumes) < 3:
        return None
    current = volumes[-1]
    prior = volumes[:-1]
    mean = _mean(prior)
    std = _std(prior)
    if mean is None or std is None or std == 0.0:
        return None
    return (current - mean) / std


def _trend_chop_label(ret_15m: float | None, vol_15m: float | None) -> str:
    if ret_15m is None or vol_15m is None or vol_15m <= 0.0:
        return "UNKNOWN"
    if ret_15m > 2.0 * vol_15m:
        return "TREND_UP"
    if ret_15m < -2.0 * vol_15m:
        return "TREND_DOWN"
    return "CHOP"


def _volatility_bucket(vol_15m: float | None) -> str:
    if vol_15m is None:
        return "UNKNOWN"
    if vol_15m < 0.001:
        return "LOW"
    if vol_15m < 0.003:
        return "MID"
    return "HIGH"


def build_feature_row(
    row: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    candles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    bar_close_ts = coerce_int(row.get("bar_close_ts")) or 0
    candle_ts = [int(c["timestamp"]) for c in candles]
    idx = bisect.bisect_right(candle_ts, bar_close_ts) - 1
    latest_close = candle_ts[idx] if idx >= 0 else None
    no_future_leakage = latest_close is None or latest_close <= bar_close_ts
    quality_status = "ok"
    if idx < 0:
        quality_status = "missing_candles"
    elif idx < 20:
        quality_status = "insufficient_candle_history"
    current = candles[idx] if idx >= 0 else {}
    close = coerce_float(current.get("close"))
    open_px = coerce_float(current.get("open"))
    high = coerce_float(current.get("high"))
    low = coerce_float(current.get("low"))
    volume = coerce_float(current.get("volume"))
    one_range = (high - low) if high is not None and low is not None else None
    body_ratio = None
    upper_wick_pct = None
    lower_wick_pct = None
    if open_px is not None and close is not None and high is not None and low is not None and one_range and one_range > 0:
        body_ratio = abs(close - open_px) / one_range
        if close > 0:
            upper_wick_pct = max(0.0, high - max(open_px, close)) / close
            lower_wick_pct = max(0.0, min(open_px, close) - low) / close
    ret_1m = _ret_between(candles, idx, 1) if idx >= 0 else None
    ret_3m = _ret_between(candles, idx, 3) if idx >= 0 else None
    ret_5m = _ret_between(candles, idx, 5) if idx >= 0 else None
    ret_15m = _ret_between(candles, idx, 15) if idx >= 0 else None
    vol_5m = _realized_vol(candles, idx, 5) if idx >= 0 else None
    vol_15m = _realized_vol(candles, idx, 15) if idx >= 0 else None
    atr_14m = _atr_ratio(candles, idx, 14) if idx >= 0 else None
    vol_expansion = vol_5m / vol_15m if vol_5m is not None and vol_15m and vol_15m > 0 else None
    breakout_distance = None
    if idx >= 20 and close is not None and close > 0:
        prior = candles[idx - 20 : idx]
        prior_highs = [coerce_float(c.get("high")) for c in prior]
        prior_lows = [coerce_float(c.get("low")) for c in prior]
        prior_highs = [float(v) for v in prior_highs if v is not None]
        prior_lows = [float(v) for v in prior_lows if v is not None]
        if prior_highs and close > max(prior_highs):
            breakout_distance = close / max(prior_highs) - 1.0
        elif prior_lows and close < min(prior_lows):
            breakout_distance = close / min(prior_lows) - 1.0
        else:
            breakout_distance = 0.0
    fee_cost = coerce_float(row.get("fee_cost")) or 0.0
    slippage_cost = coerce_float(row.get("slippage_cost")) or 0.0
    entry_price = coerce_float(diagnostic.get("entry_price"))
    mfe = abs(coerce_float(diagnostic.get("mfe")) or 0.0)
    mae = abs(coerce_float(diagnostic.get("mae")) or 0.0)
    mfe_return = (mfe / entry_price) if entry_price and entry_price > 0 else None
    mae_return = (mae / entry_price) if entry_price and entry_price > 0 else None
    confidence = coerce_float(row.get("confidence")) or 0.0
    feature_row = {
        "schema_version": "alpha_factory_feature_matrix_v1",
        "row_id": stable_hash(
            {
                "verdict_id": row.get("verdict_id"),
                "symbol": row.get("symbol"),
                "tf_sec": row.get("tf_sec"),
                "bar_close_ts": row.get("bar_close_ts"),
            },
            length=24,
        ),
        "verdict_id": row.get("verdict_id"),
        "symbol": str(row.get("symbol") or "").upper(),
        "tf_sec": int(row.get("tf_sec") or 0),
        "bar_close_ts": bar_close_ts,
        "utc_hour": utc_hour_from_ms(bar_close_ts),
        "entry_verdict": row.get("entry_verdict"),
        "optimal_action": row.get("optimal_action"),
        "cohort": row.get("cohort"),
        "matched_trade": row.get("matched_trade"),
        "confidence": confidence,
        "confidence_bucket": confidence_bucket(confidence),
        "regime": str(row.get("regime") or diagnostic.get("regime") or "UNKNOWN"),
        "regime_confidence": coerce_float(diagnostic.get("regime_confidence")),
        "regime_stale_bars": coerce_int(diagnostic.get("regime_stale_bars")),
        "exit_classification": diagnostic.get("exit_classification"),
        "chosen_tier": diagnostic.get("chosen_tier"),
        "raw_return": coerce_float(row.get("raw_return")),
        "net_return": coerce_float(row.get("net_return")),
        "fee_cost": fee_cost,
        "slippage_cost": slippage_cost,
        "entry_price": entry_price,
        "tp_price": coerce_float(diagnostic.get("tp_price")),
        "sl_price": coerce_float(diagnostic.get("sl_price")),
        "mfe_return": mfe_return,
        "mae_return": mae_return,
        "candle_close_ts": latest_close,
        "candles_available_before_bar": idx + 1 if idx >= 0 else 0,
        "no_future_leakage": no_future_leakage,
        "feature_quality": quality_status,
        "close": close,
        "volume": volume,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_5m": ret_5m,
        "ret_15m": ret_15m,
        "range_pct_1m": (one_range / close) if one_range is not None and close and close > 0 else None,
        "body_ratio_1m": body_ratio,
        "upper_wick_pct_1m": upper_wick_pct,
        "lower_wick_pct_1m": lower_wick_pct,
        "realized_vol_5m": vol_5m,
        "realized_vol_15m": vol_15m,
        "atr_ratio_14m": atr_14m,
        "breakout_distance_20m": breakout_distance,
        "volume_zscore_20m": _volume_zscore(candles, idx, 20) if idx >= 0 else None,
        "volatility_expansion_5m_15m": vol_expansion,
        "trend_chop_label": _trend_chop_label(ret_15m, vol_15m),
        "volatility_bucket": _volatility_bucket(vol_15m),
        "provenance_class": row.get("provenance_class") or "replay_derived",
    }
    return feature_row


def _training_target_row(feature: Mapping[str, Any]) -> dict[str, Any]:
    net = coerce_float(feature.get("net_return"))
    optimal = str(feature.get("optimal_action") or "NO_ENTRY")
    return {
        "schema_version": "alpha_factory_training_targets_v1",
        "row_id": feature.get("row_id"),
        "verdict_id": feature.get("verdict_id"),
        "symbol": feature.get("symbol"),
        "tf_sec": feature.get("tf_sec"),
        "bar_close_ts": feature.get("bar_close_ts"),
        "tradeability": 1 if net is not None and net > 0.0 else 0,
        "direction_target": optimal if optimal in ACTIONABLE_VERDICTS else "NO_ENTRY",
        "exit_template_target": feature.get("exit_classification") or "UNKNOWN",
        "confidence_calibration_target": 1 if net is not None and net > 0.0 else 0,
        "net_return": net,
        "provenance_class": feature.get("provenance_class") or "replay_derived",
    }


def run_build_feature_matrix(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_root
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration_path = Path(args.calibration_path)
    diagnostics_path = Path(args.outcomes_diagnostics_path) if args.outcomes_diagnostics_path else dataset_root / "outcomes" / "outcomes_diagnostics.jsonl"
    raw_root = Path(args.raw_1m_dir)
    rows = load_calibration_rows(calibration_path, diagnostics_path if diagnostics_path.exists() else None)
    by_verdict, by_key = _diagnostic_lookup(diagnostics_path if diagnostics_path.exists() else None)
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
    feature_rows: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        candles = candles_by_symbol.setdefault(symbol, load_raw_1m_candles(raw_root, symbol))
        diagnostic = diagnostic_for_row(row, by_verdict, by_key)
        if diagnostic.get("regime") and not row.get("regime"):
            row["regime"] = diagnostic.get("regime")
        feature_rows.append(build_feature_row(row, diagnostic, candles))
    feature_path = output_dir / "feature_matrix.jsonl"
    targets_path = output_dir / "training_targets.jsonl"
    manifest_path = output_dir / "feature_manifest.json"
    write_jsonl(feature_path, feature_rows)
    write_jsonl(targets_path, [_training_target_row(row) for row in feature_rows])
    quality_counts: dict[str, int] = {}
    for row in feature_rows:
        key = str(row.get("feature_quality"))
        quality_counts[key] = quality_counts.get(key, 0) + 1
    manifest = {
        "schema_version": "alpha_factory_feature_manifest_v1",
        "dataset_id": args.dataset_id,
        "created_at_utc": utc_now_iso(),
        "calibration_path": str(calibration_path),
        "raw_1m_dir": str(raw_root),
        "outcomes_diagnostics_path": str(diagnostics_path),
        "feature_matrix_path": str(feature_path),
        "training_targets_path": str(targets_path),
        "row_count": len(feature_rows),
        "quality_counts": dict(sorted(quality_counts.items())),
        "feature_hash": sha256_file(feature_path),
        "official_metric_provenance": sorted(OFFICIAL_PROVENANCE_CLASSES),
        "synthetic_stress_official_metrics": "excluded",
    }
    write_json(manifest_path, manifest)
    with connect_db(db_path) as con:
        for row in feature_rows:
            con.execute(
                """
                INSERT OR REPLACE INTO feature_matrix_index (
                  row_id, dataset_id, symbol, tf_sec, bar_close_ts,
                  feature_path, feature_hash, provenance_class, quality_status,
                  created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["row_id"],
                    args.dataset_id,
                    row["symbol"],
                    int(row["tf_sec"]),
                    int(row["bar_close_ts"]),
                    str(feature_path),
                    manifest["feature_hash"],
                    row["provenance_class"],
                    row["feature_quality"],
                    utc_now_iso(),
                ),
            )
        for path, artifact_type in [
            (feature_path, "feature_matrix"),
            (targets_path, "training_targets"),
            (manifest_path, "feature_manifest"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=None,
                artifact_type=artifact_type,
                path=path,
                provenance_class="replay_derived",
            )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=None,
            artifact_path=manifest_path,
            provenance_class="replay_derived",
            reason="feature_matrix_built_from_real_candles_and_replay_outcomes",
        )
    print(json.dumps({"status": "ok", "rows": len(feature_rows), "manifest": str(manifest_path)}, sort_keys=True))
    return 0


def _official_feature_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    official_rows = [
        dict(row)
        for row in rows
        if provenance_is_official(str(row.get("provenance_class") or "replay_derived"))
    ]
    assert_official_metric_rows(official_rows)
    return official_rows


def _metrics_from_returns(values: Sequence[float | None], *, min_selected: int, target_win_rate: float) -> dict[str, Any]:
    returns = [float(v) for v in values if v is not None]
    selected = len(returns)
    positive = sum(1 for value in returns if value > 0.0)
    negative = sum(1 for value in returns if value < 0.0)
    win_rate = positive / selected if selected else None
    avg_net = sum(returns) / selected if selected else None
    if selected < min_selected:
        status = "INSUFFICIENT_SAMPLE"
    elif win_rate is not None and avg_net is not None and win_rate >= target_win_rate and avg_net > 0.0:
        status = "CEILING_ABOVE_TARGET"
    else:
        status = "CEILING_BELOW_TARGET"
    return {
        "selected_count": selected,
        "positive_net_count": positive,
        "negative_net_count": negative,
        "win_rate": win_rate,
        "avg_net_return": avg_net,
        "total_net_return": sum(returns) if returns else None,
        "status": status,
    }


def compute_ceiling_rows(
    feature_rows: Sequence[Mapping[str, Any]],
    *,
    min_selected: int,
    target_win_rate: float,
) -> list[dict[str, Any]]:
    rows = _official_feature_rows(feature_rows)
    fee_slip = [
        (coerce_float(row.get("fee_cost")) or 0.0) + (coerce_float(row.get("slippage_cost")) or 0.0)
        for row in rows
    ]
    actual_returns = [coerce_float(row.get("net_return")) for row in rows]
    raw_returns = [coerce_float(row.get("raw_return")) for row in rows]
    direction_returns = [
        (abs(raw) - cost) if raw is not None else None
        for raw, cost in zip(raw_returns, fee_slip)
    ]
    no_entry_returns = [value for value in actual_returns if value is not None and value > 0.0]
    exit_returns = []
    for row, cost in zip(rows, fee_slip):
        mfe = coerce_float(row.get("mfe_return"))
        if mfe is None:
            exit_returns.append(None)
        else:
            exit_returns.append(mfe - cost)
    fee_aware_returns = [
        max([candidate for candidate in [actual, direction, exit_ret] if candidate is not None], default=None)
        for actual, direction, exit_ret in zip(actual_returns, direction_returns, exit_returns)
    ]
    definitions = [
        ("judge_current", actual_returns, "Current Judge selected-entry net returns.", "baseline", True),
        (
            "oracle_no_entry_filter",
            no_entry_returns,
            "Tautology control: keeps only rows already known to be net-positive.",
            "tautology_control",
            False,
        ),
        ("oracle_direction", direction_returns, "Approximation: flip wrong direction using abs(raw_return) minus costs.", "oracle", True),
        ("oracle_tp_sl_horizon", exit_returns, "Approximation: capture path MFE minus costs where path diagnostics exist.", "oracle", True),
        ("fee_aware_oracle", fee_aware_returns, "Best available per-row upper bound after fee/slippage.", "oracle", True),
    ]
    out = []
    for name, values, note, metric_role, acceptance_eligible in definitions:
        metrics = _metrics_from_returns(values, min_selected=min_selected, target_win_rate=target_win_rate)
        if not acceptance_eligible:
            metrics["status"] = "TAUTOLOGY_CONTROL"
        out.append(
            {
                "schema_version": "alpha_factory_ceiling_result_v1",
                "ceiling_name": name,
                "definition": note,
                "metric_role": metric_role,
                "official_acceptance_eligible": acceptance_eligible,
                **metrics,
            }
        )
    return out


def run_compute_ceilings(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("ceiling")
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_root
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_path = Path(args.feature_matrix) if args.feature_matrix else dataset_root / "feature_matrix.jsonl"
    rows = read_jsonl(feature_path)
    ceiling_rows = compute_ceiling_rows(
        rows,
        min_selected=int(args.min_selected),
        target_win_rate=float(args.target_win_rate),
    )
    best_oracle = next((row for row in ceiling_rows if row["ceiling_name"] == "fee_aware_oracle"), None)
    judge = next((row for row in ceiling_rows if row["ceiling_name"] == "judge_current"), None)
    status = "INSUFFICIENT_EVIDENCE"
    if best_oracle and best_oracle["status"] == "CEILING_BELOW_TARGET":
        status = "NO_EDGE_CEILING_BELOW_TARGET"
    elif best_oracle and best_oracle["status"] == "CEILING_ABOVE_TARGET" and judge and judge["status"] != "CEILING_ABOVE_TARGET":
        status = "EDGE_EXISTS_JUDGE_MAPPING_WEAK"
    elif best_oracle and best_oracle["status"] == "CEILING_ABOVE_TARGET":
        status = "EDGE_EXISTS_SHADOW_ONLY"
    report = {
        "schema_version": "alpha_factory_ceiling_report_v1",
        "run_id": run_id,
        "dataset_id": args.dataset_id,
        "created_at_utc": utc_now_iso(),
        "feature_matrix": str(feature_path),
        "target_win_rate": float(args.target_win_rate),
        "min_selected": int(args.min_selected),
        "status": status,
        "ceilings": ceiling_rows,
        "official_metric_provenance": sorted(OFFICIAL_PROVENANCE_CLASSES),
        "synthetic_stress_official_metrics": "excluded",
    }
    report_path = output_dir / "ceiling_report.json"
    write_json(report_path, report)
    with connect_db(db_path) as con:
        for row in ceiling_rows:
            con.execute(
                """
                INSERT OR REPLACE INTO ceiling_result (
                  run_id, dataset_id, ceiling_name, selected_count, win_rate,
                  avg_net_return, status, details_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    args.dataset_id,
                    row["ceiling_name"],
                    int(row["selected_count"]),
                    row["win_rate"],
                    row["avg_net_return"],
                    row["status"],
                    json.dumps(row, sort_keys=True),
                    utc_now_iso(),
                ),
            )
        record_artifact(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_type="ceiling_report",
            path=report_path,
            provenance_class="replay_derived",
        )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=report_path,
            provenance_class="replay_derived",
            reason="oracle_ceilings_computed_from_official_feature_rows",
        )
    print(json.dumps({"run_id": run_id, "status": status, "report": str(report_path)}, sort_keys=True))
    return 0


def _simulate_exit_template_return(row: Mapping[str, Any], tp_pct: float, sl_pct: float) -> float | None:
    mfe = coerce_float(row.get("mfe_return"))
    mae = coerce_float(row.get("mae_return"))
    if mfe is None or mae is None:
        return None
    cost = (coerce_float(row.get("fee_cost")) or 0.0) + (coerce_float(row.get("slippage_cost")) or 0.0)
    hit_tp = mfe >= tp_pct
    hit_sl = mae >= sl_pct
    if hit_tp and hit_sl:
        return -sl_pct - cost
    if hit_tp:
        return tp_pct - cost
    if hit_sl:
        return -sl_pct - cost
    raw = coerce_float(row.get("raw_return"))
    return raw - cost if raw is not None else None


def run_search_exit_templates(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("exit_search")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    feature_path = Path(args.feature_matrix) if args.feature_matrix else dataset_root / "feature_matrix.jsonl"
    rows = _official_feature_rows(read_jsonl(feature_path))
    results = []
    for confidence_min in parse_float_csv(args.confidence_thresholds, [0.0, 0.25, 0.5, 0.75]):
        for tp_pct in parse_float_csv(args.tp_pcts, [0.005, 0.01, 0.015, 0.02]):
            for sl_pct in parse_float_csv(args.sl_pcts, [0.005, 0.01, 0.015, 0.02]):
                selected = [
                    _simulate_exit_template_return(row, tp_pct, sl_pct)
                    for row in rows
                    if row.get("entry_verdict") in ACTIONABLE_VERDICTS
                    and (coerce_float(row.get("confidence")) or 0.0) >= confidence_min
                ]
                metrics = _metrics_from_returns(
                    selected,
                    min_selected=int(args.min_selected),
                    target_win_rate=float(args.target_win_rate),
                )
                params = {
                    "confidence_min": confidence_min,
                    "tp_pct": tp_pct,
                    "sl_pct": sl_pct,
                    "fill_rule": "mfe_mae_worst_case_if_both_hit",
                }
                results.append(
                    {
                        "schema_version": "alpha_factory_exit_template_result_v1",
                        "candidate_id": stable_hash(params),
                        "params": params,
                        **metrics,
                    }
                )
    results = sorted(
        results,
        key=lambda r: (
            0 if r["status"] == "CEILING_ABOVE_TARGET" else 1,
            -(r["win_rate"] or 0.0),
            -(r["avg_net_return"] or -999.0),
            str(r["candidate_id"]),
        ),
    )
    results_path = output_dir / "exit_template_results.jsonl"
    leaderboard_path = output_dir / "exit_template_leaderboard.csv"
    summary_path = output_dir / "exit_template_summary.json"
    write_jsonl(results_path, results)
    write_csv(
        leaderboard_path,
        [
            {
                "rank": idx + 1,
                "candidate_id": row["candidate_id"],
                "status": row["status"],
                "selected_count": row["selected_count"],
                "win_rate": row["win_rate"],
                "avg_net_return": row["avg_net_return"],
                "params_json": json.dumps(row["params"], sort_keys=True),
            }
            for idx, row in enumerate(results)
        ],
        ["rank", "candidate_id", "status", "selected_count", "win_rate", "avg_net_return", "params_json"],
    )
    pass_count = sum(1 for row in results if row["status"] == "CEILING_ABOVE_TARGET")
    summary = {
        "schema_version": "alpha_factory_exit_template_summary_v1",
        "run_id": run_id,
        "dataset_id": args.dataset_id,
        "candidate_count": len(results),
        "pass_count": pass_count,
        "status": "EXIT_TEMPLATE_FOUND_SHADOW_ONLY" if pass_count else "INSUFFICIENT_EVIDENCE",
        "top_candidate": results[0] if results else None,
        "official_metric_provenance": sorted(OFFICIAL_PROVENANCE_CLASSES),
    }
    write_json(summary_path, summary)
    with connect_db(db_path) as con:
        for path, artifact_type in [
            (results_path, "exit_template_results"),
            (leaderboard_path, "exit_template_leaderboard"),
            (summary_path, "exit_template_summary"),
        ]:
            record_artifact(con, dataset_id=args.dataset_id, run_id=run_id, artifact_type=artifact_type, path=path, provenance_class="replay_derived")
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=summary_path,
            provenance_class="replay_derived",
            reason="exit_template_sweep_from_mfe_mae_path_diagnostics",
        )
    print(json.dumps({"run_id": run_id, "status": summary["status"], "summary": str(summary_path)}, sort_keys=True))
    return 0


def run_calibrate_confidence(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("confidence")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    feature_path = Path(args.feature_matrix) if args.feature_matrix else dataset_root / "feature_matrix.jsonl"
    rows = _official_feature_rows(read_jsonl(feature_path))
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        net = coerce_float(row.get("net_return"))
        if net is None:
            continue
        bucket = confidence_bucket(row.get("confidence"))
        agg = buckets.setdefault(
            bucket,
            {"confidence_bucket": bucket, "record_count": 0, "positive_net_count": 0, "negative_net_count": 0, "avg_confidence_sum": 0.0, "avg_net_return_sum": 0.0},
        )
        agg["record_count"] += 1
        agg["avg_confidence_sum"] += coerce_float(row.get("confidence")) or 0.0
        agg["avg_net_return_sum"] += net
        if net > 0:
            agg["positive_net_count"] += 1
        elif net < 0:
            agg["negative_net_count"] += 1
    ordered = []
    for _, _, label in FIXED_CONFIDENCE_BUCKETS:
        agg = buckets.get(label, {"confidence_bucket": label, "record_count": 0, "positive_net_count": 0, "negative_net_count": 0, "avg_confidence_sum": 0.0, "avg_net_return_sum": 0.0})
        count = int(agg["record_count"])
        ordered.append(
            {
                "confidence_bucket": label,
                "record_count": count,
                "positive_net_count": agg["positive_net_count"],
                "negative_net_count": agg["negative_net_count"],
                "win_rate": (agg["positive_net_count"] / count) if count else None,
                "avg_confidence": (agg["avg_confidence_sum"] / count) if count else None,
                "avg_net_return": (agg["avg_net_return_sum"] / count) if count else None,
            }
        )
    win_rates = [row["win_rate"] for row in ordered if row["win_rate"] is not None]
    monotonic = all(win_rates[i] <= win_rates[i + 1] + 1e-12 for i in range(len(win_rates) - 1))
    calibration_path = output_dir / "confidence_calibration.csv"
    summary_path = output_dir / "confidence_calibration_summary.json"
    write_csv(
        calibration_path,
        ordered,
        ["confidence_bucket", "record_count", "positive_net_count", "negative_net_count", "win_rate", "avg_confidence", "avg_net_return"],
    )
    summary = {
        "schema_version": "alpha_factory_confidence_calibration_summary_v1",
        "run_id": run_id,
        "dataset_id": args.dataset_id,
        "feature_matrix": str(feature_path),
        "status": "MONOTONIC_CONFIDENCE" if monotonic else "CONFIDENCE_MISORDERED",
        "monotonic_win_rate": monotonic,
        "buckets": ordered,
    }
    write_json(summary_path, summary)
    with connect_db(db_path) as con:
        for path, artifact_type in [
            (calibration_path, "confidence_calibration"),
            (summary_path, "confidence_calibration_summary"),
        ]:
            record_artifact(con, dataset_id=args.dataset_id, run_id=run_id, artifact_type=artifact_type, path=path, provenance_class="replay_derived")
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=summary_path,
            provenance_class="replay_derived",
            reason="confidence_bucket_calibration_from_official_feature_rows",
        )
    print(json.dumps({"run_id": run_id, "status": summary["status"], "summary": str(summary_path)}, sort_keys=True))
    return 0


def _policy_selected(row: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    if row.get("entry_verdict") not in ACTIONABLE_VERDICTS:
        return False
    if coerce_float(row.get("net_return")) is None:
        return False
    if (coerce_float(row.get("confidence")) or 0.0) < float(params["confidence_min"]):
        return False
    for field in ["symbol", "regime", "trend_chop_label", "volatility_bucket"]:
        selector = str(params.get(field) or "*")
        if selector != "*" and str(row.get(field)) != selector:
            return False
    return True


def _evaluate_policy_candidate(
    rows: Sequence[Mapping[str, Any]],
    params: Mapping[str, Any],
    *,
    min_selected: int,
    target_win_rate: float,
) -> dict[str, Any]:
    returns = [coerce_float(row.get("net_return")) for row in rows if _policy_selected(row, params)]
    return _metrics_from_returns(returns, min_selected=min_selected, target_win_rate=target_win_rate)


def _walkforward_splits(
    rows: Sequence[Mapping[str, Any]],
    *,
    split_mode: str,
    train_days: int,
    validation_days: int,
    holdout_days: int,
) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted([dict(row) for row in rows if coerce_int(row.get("bar_close_ts")) is not None], key=lambda row: int(row["bar_close_ts"]))
    if not ordered:
        return {"train": [], "validation": [], "holdout": []}
    if split_mode == "ratio":
        n = len(ordered)
        train_end = max(1, int(n * 0.60))
        validation_end = max(train_end + 1, int(n * 0.80))
        return {
            "train": ordered[:train_end],
            "validation": ordered[train_end:validation_end],
            "holdout": ordered[validation_end:],
        }
    end_ts = int(ordered[-1]["bar_close_ts"])
    day_ms = 24 * 60 * MINUTE_MS
    holdout_start = end_ts - holdout_days * day_ms
    validation_start = holdout_start - validation_days * day_ms
    train_start = validation_start - train_days * day_ms
    return {
        "train": [row for row in ordered if train_start <= int(row["bar_close_ts"]) < validation_start],
        "validation": [row for row in ordered if validation_start <= int(row["bar_close_ts"]) < holdout_start],
        "holdout": [row for row in ordered if holdout_start <= int(row["bar_close_ts"]) <= end_ts],
    }


def _walkforward_data_window_status(
    splits: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    split_mode: str,
    train_days: int,
    validation_days: int,
    holdout_days: int,
) -> tuple[str, dict[str, Any]]:
    counts = {name: len(splits.get(name, [])) for name in ("train", "validation", "holdout")}
    all_rows = [row for split_rows in splits.values() for row in split_rows]
    start_ts = min((int(row["bar_close_ts"]) for row in all_rows), default=None)
    end_ts = max((int(row["bar_close_ts"]) for row in all_rows), default=None)
    span_ms = (end_ts - start_ts) if start_ts is not None and end_ts is not None else 0
    required_span_ms = (train_days + validation_days + holdout_days) * DAY_MS
    reasons = []
    if counts["train"] == 0:
        reasons.append("empty_train_split")
    if counts["validation"] == 0:
        reasons.append("empty_validation_split")
    if counts["holdout"] == 0:
        reasons.append("empty_holdout_split")
    if split_mode == "fixed-days" and span_ms < required_span_ms:
        reasons.append("dataset_span_shorter_than_requested_fixed_days")
    details = {
        "split_mode": split_mode,
        "split_counts": counts,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "span_ms": span_ms,
        "span_days": span_ms / DAY_MS if span_ms else 0.0,
        "required_span_days": train_days + validation_days + holdout_days,
        "reasons": reasons,
    }
    return ("INSUFFICIENT_DATA_WINDOW" if reasons else "OK", details)


def _policy_candidate_params(rows: Sequence[Mapping[str, Any]], confidence_thresholds: Sequence[float]) -> list[dict[str, Any]]:
    regimes = ["*"] + sorted({str(row.get("regime")) for row in rows if row.get("regime")})
    trends = ["*"] + sorted({str(row.get("trend_chop_label")) for row in rows if row.get("trend_chop_label")})
    vol_buckets = ["*"] + sorted({str(row.get("volatility_bucket")) for row in rows if row.get("volatility_bucket")})
    symbols = ["*"] + sorted({str(row.get("symbol")) for row in rows if row.get("symbol")})
    params = []
    for confidence_min in confidence_thresholds:
        for regime in regimes:
            for trend in trends:
                for vol_bucket in vol_buckets:
                    params.append(
                        {
                            "confidence_min": float(confidence_min),
                            "symbol": "*",
                            "regime": regime,
                            "trend_chop_label": trend,
                            "volatility_bucket": vol_bucket,
                            "action_mode": "filter_existing_judge_entry",
                        }
                    )
        for symbol in symbols:
            if symbol == "*":
                continue
            params.append(
                {
                    "confidence_min": float(confidence_min),
                    "symbol": symbol,
                    "regime": "*",
                    "trend_chop_label": "*",
                    "volatility_bucket": "*",
                    "action_mode": "filter_existing_judge_entry",
                }
            )
    unique = {stable_hash(param): param for param in params}
    return [unique[key] for key in sorted(unique)]


def _walkforward_acceptance(
    train: Mapping[str, Any],
    validation: Mapping[str, Any],
    holdout: Mapping[str, Any],
    *,
    data_window_status: str,
    min_selected: int,
    target_win_rate: float,
    min_validation_win_rate: float,
    max_validation_holdout_drop: float,
) -> str:
    if data_window_status != "OK":
        return data_window_status
    if int(holdout["selected_count"]) < min_selected:
        return "INSUFFICIENT_SAMPLE"
    if holdout["win_rate"] is None or holdout["avg_net_return"] is None:
        return "INSUFFICIENT_EVIDENCE"
    if validation["win_rate"] is None or float(validation["win_rate"]) < min_validation_win_rate:
        return "FAIL_VALIDATION_GUARDRAIL"
    if float(validation["win_rate"]) - float(holdout["win_rate"]) > max_validation_holdout_drop:
        return "FAIL_HOLDOUT_DROP_GUARDRAIL"
    if float(holdout["win_rate"]) >= target_win_rate and float(holdout["avg_net_return"]) > 0.0:
        return "PASS_SHADOW_CANDIDATE"
    return "FAIL_SHADOW_CANDIDATE"


def run_walkforward(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("walkforward")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    feature_path = Path(args.feature_matrix) if args.feature_matrix else dataset_root / "feature_matrix.jsonl"
    rows = _official_feature_rows(read_jsonl(feature_path))
    splits = _walkforward_splits(
        rows,
        split_mode=str(args.split_mode),
        train_days=int(args.train_days),
        validation_days=int(args.validation_days),
        holdout_days=int(args.holdout_days),
    )
    data_window_status, data_window_details = _walkforward_data_window_status(
        splits,
        split_mode=str(args.split_mode),
        train_days=int(args.train_days),
        validation_days=int(args.validation_days),
        holdout_days=int(args.holdout_days),
    )
    candidates = []
    for params in _policy_candidate_params(splits["train"] or rows, parse_float_csv(args.confidence_thresholds, [0.0, 0.25, 0.5, 0.75])):
        train_metrics = _evaluate_policy_candidate(splits["train"], params, min_selected=1, target_win_rate=float(args.target_win_rate))
        validation_metrics = _evaluate_policy_candidate(splits["validation"], params, min_selected=1, target_win_rate=float(args.target_win_rate))
        holdout_metrics = _evaluate_policy_candidate(splits["holdout"], params, min_selected=int(args.min_selected), target_win_rate=float(args.target_win_rate))
        status = _walkforward_acceptance(
            train_metrics,
            validation_metrics,
            holdout_metrics,
            data_window_status=data_window_status,
            min_selected=int(args.min_selected),
            target_win_rate=float(args.target_win_rate),
            min_validation_win_rate=float(args.min_validation_win_rate),
            max_validation_holdout_drop=float(args.max_validation_holdout_drop),
        )
        candidate = {
            "schema_version": "alpha_factory_walkforward_result_v1",
            "candidate_id": stable_hash(params),
            "params": params,
            "status": status,
            "train": train_metrics,
            "validation": validation_metrics,
            "holdout": holdout_metrics,
        }
        candidates.append(candidate)
    status_rank = {
        "PASS_SHADOW_CANDIDATE": 0,
        "FAIL_SHADOW_CANDIDATE": 1,
        "FAIL_VALIDATION_GUARDRAIL": 2,
        "FAIL_HOLDOUT_DROP_GUARDRAIL": 3,
        "INSUFFICIENT_SAMPLE": 4,
        "INSUFFICIENT_DATA_WINDOW": 5,
        "INSUFFICIENT_EVIDENCE": 6,
    }
    candidates = sorted(
        candidates,
        key=lambda row: (
            status_rank.get(row["status"], 99),
            -(row["holdout"]["win_rate"] or 0.0),
            -(row["holdout"]["avg_net_return"] or -999.0),
            str(row["candidate_id"]),
        ),
    )
    best = candidates[0] if candidates else None
    overall_status = "INSUFFICIENT_EVIDENCE"
    if best:
        overall_status = best["status"]
    if data_window_status != "OK":
        overall_status = data_window_status
    results_path = output_dir / "walkforward_results.jsonl"
    learned_policy_path = output_dir / "learned_policy.json"
    casebook_path = output_dir / "candidate_casebook.jsonl"
    trace_path = output_dir / "policy_decision_trace.jsonl"
    write_jsonl(results_path, candidates)
    casebook = candidates[: min(20, len(candidates))]
    write_jsonl(casebook_path, casebook)
    trace_rows = []
    if best:
        for row in splits["holdout"]:
            selected = _policy_selected(row, best["params"])
            action = str(row.get("entry_verdict")) if selected else "NO_ENTRY"
            trace_rows.append(
                {
                    "schema_version": "alpha_factory_policy_decision_trace_v1",
                    "run_id": run_id,
                    "candidate_id": best["candidate_id"],
                    "decision_id": stable_hash({"run_id": run_id, "row_id": row.get("row_id")}, length=24),
                    "row_id": row.get("row_id"),
                    "verdict_id": row.get("verdict_id"),
                    "symbol": row.get("symbol"),
                    "bar_close_ts": row.get("bar_close_ts"),
                    "action": action,
                    "reason": "candidate_gates_passed" if selected else "no_entry_filter_rejected",
                    "features": {
                        "confidence": row.get("confidence"),
                        "regime": row.get("regime"),
                        "trend_chop_label": row.get("trend_chop_label"),
                        "volatility_bucket": row.get("volatility_bucket"),
                        "params": best["params"],
                    },
                }
            )
    write_jsonl(trace_path, trace_rows)
    learned_policy = {
        "schema_version": "alpha_factory_learned_policy_v1",
        "run_id": run_id,
        "dataset_id": args.dataset_id,
        "created_at_utc": utc_now_iso(),
        "status": overall_status,
        "authority": "shadow_only",
        "live_trade_authority": "forbidden",
        "objective": "no_entry_filter_first",
        "feature_matrix": str(feature_path),
        "split_mode": str(args.split_mode),
        "data_window_status": data_window_status,
        "data_window_details": data_window_details,
        "splits": {
            name: {
                "row_count": len(split_rows),
                "start_ts": min((int(row["bar_close_ts"]) for row in split_rows), default=None),
                "end_ts": max((int(row["bar_close_ts"]) for row in split_rows), default=None),
            }
            for name, split_rows in splits.items()
        },
        "target_win_rate": float(args.target_win_rate),
        "min_selected": int(args.min_selected),
        "acceptance_gate": {
            "holdout_win_rate_min": float(args.target_win_rate),
            "holdout_avg_net_return_gt": 0.0,
            "holdout_selected_min": int(args.min_selected),
            "validation_win_rate_min": float(args.min_validation_win_rate),
            "max_validation_holdout_drop": float(args.max_validation_holdout_drop),
        },
        "best_candidate": best,
        "outputs": {
            "walkforward_results": str(results_path),
            "candidate_casebook": str(casebook_path),
            "policy_decision_trace": str(trace_path),
        },
    }
    write_json(learned_policy_path, learned_policy)
    with connect_db(db_path) as con:
        for name, split_rows in splits.items():
            con.execute(
                """
                INSERT OR REPLACE INTO walkforward_split (
                  run_id, dataset_id, split_name, start_ts, end_ts, row_count, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    args.dataset_id,
                    name,
                    min((int(row["bar_close_ts"]) for row in split_rows), default=None),
                    max((int(row["bar_close_ts"]) for row in split_rows), default=None),
                    len(split_rows),
                    utc_now_iso(),
                ),
            )
        for candidate in candidates:
            con.execute(
                """
                INSERT OR REPLACE INTO learned_policy_candidate (
                  run_id, candidate_id, status, params_json, train_metrics_json,
                  validation_metrics_json, holdout_metrics_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    candidate["candidate_id"],
                    candidate["status"],
                    json.dumps(candidate["params"], sort_keys=True),
                    json.dumps(candidate["train"], sort_keys=True),
                    json.dumps(candidate["validation"], sort_keys=True),
                    json.dumps(candidate["holdout"], sort_keys=True),
                    utc_now_iso(),
                ),
            )
        for trace in trace_rows:
            con.execute(
                """
                INSERT OR REPLACE INTO policy_decision_trace (
                  run_id, decision_id, candidate_id, verdict_id, action, reason,
                  features_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trace["decision_id"],
                    trace["candidate_id"],
                    trace["verdict_id"],
                    trace["action"],
                    trace["reason"],
                    json.dumps(trace["features"], sort_keys=True),
                    utc_now_iso(),
                ),
            )
        for path, artifact_type in [
            (results_path, "walkforward_results"),
            (learned_policy_path, "learned_policy"),
            (casebook_path, "candidate_casebook"),
            (trace_path, "policy_decision_trace"),
        ]:
            record_artifact(con, dataset_id=args.dataset_id, run_id=run_id, artifact_type=artifact_type, path=path, provenance_class="replay_derived")
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=learned_policy_path,
            provenance_class="replay_derived",
            reason="walkforward_shadow_policy_search_no_entry_filter_first",
        )
    print(json.dumps({"run_id": run_id, "status": overall_status, "learned_policy": str(learned_policy_path)}, sort_keys=True))
    return 0


def render_learning_report(
    *,
    dataset_manifest: Mapping[str, Any] | None,
    failure_summary: Mapping[str, Any] | None,
    ceiling_report: Mapping[str, Any] | None,
    confidence_summary: Mapping[str, Any] | None,
    learned_policy: Mapping[str, Any] | None,
) -> str:
    policy_status = str((learned_policy or {}).get("status") or "INSUFFICIENT_EVIDENCE")
    if policy_status == "PASS_SHADOW_CANDIDATE":
        verdict = "PASS_SHADOW_CANDIDATE"
    elif policy_status == "INSUFFICIENT_DATA_WINDOW":
        verdict = "INSUFFICIENT_DATA_WINDOW"
    elif policy_status == "INSUFFICIENT_SAMPLE":
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
    lines = [
        "# Alpha Search Learning Report",
        "",
        f"Executive verdict: {verdict}",
        "",
        "This report is shadow-only. It does not authorize live trading, Judge mode widening, or execution changes.",
        "",
        "## FACTS",
        "",
    ]
    if dataset_manifest:
        lines.append(f"- Dataset: {dataset_manifest.get('dataset_id')} status={dataset_manifest.get('status')}")
        lines.append(f"- Universe: {', '.join(dataset_manifest.get('universe') or [])}")
    else:
        lines.append("- Dataset manifest was not supplied.")
    if failure_summary:
        lines.append(f"- Failure diagnosis rows: {failure_summary.get('row_count')}")
        lines.append(f"- Failure counts: {json.dumps(failure_summary.get('failure_counts') or {}, sort_keys=True)}")
    else:
        lines.append("- Failure diagnostics were not supplied.")
    if ceiling_report:
        lines.append(f"- Ceiling status: {ceiling_report.get('status')}")
        ceilings = {str(row.get("ceiling_name")): row for row in ceiling_report.get("ceilings") or []}
        fee_aware = ceilings.get("fee_aware_oracle")
        if fee_aware:
            lines.append(
                f"- Fee-aware oracle: win_rate={fee_aware.get('win_rate')} "
                f"avg_net_return={fee_aware.get('avg_net_return')} "
                f"target_win_rate={ceiling_report.get('target_win_rate')}"
            )
        no_entry = ceilings.get("oracle_no_entry_filter")
        if no_entry:
            lines.append(
                f"- Oracle no-entry filter: status={no_entry.get('status')} "
                f"metric_role={no_entry.get('metric_role')} acceptance_eligible={no_entry.get('official_acceptance_eligible')}"
            )
    else:
        lines.append("- Ceiling report was not supplied.")
    if confidence_summary:
        lines.append(f"- Confidence calibration status: {confidence_summary.get('status')}")
    if learned_policy:
        splits = learned_policy.get("splits") or {}
        lines.append(f"- Walkforward status: {learned_policy.get('status')}")
        if learned_policy.get("data_window_status"):
            lines.append(f"- Walkforward data window status: {learned_policy.get('data_window_status')}")
        lines.append(f"- Walkforward splits: {json.dumps(splits, sort_keys=True)}")
    lines.extend(["", "## INFERENCES", ""])
    if ceiling_report and ceiling_report.get("status") == "EDGE_EXISTS_JUDGE_MAPPING_WEAK":
        lines.append("- The data surface appears to contain an oracle-level edge, but current Judge mapping does not extract it.")
    elif ceiling_report and ceiling_report.get("status") == "NO_EDGE_CEILING_BELOW_TARGET":
        lines.append("- Even oracle-style upper bounds are below target; the current data/action surface is likely insufficient.")
        ceilings = {str(row.get("ceiling_name")): row for row in ceiling_report.get("ceilings") or []}
        fee_aware = ceilings.get("fee_aware_oracle")
        if fee_aware:
            lines.append(
                f"- Fee-aware oracle win_rate={fee_aware.get('win_rate')} is below target={ceiling_report.get('target_win_rate')}; "
                "the dominant problem is before policy mapping: the entry trigger admits non-tradeable market states."
            )
    else:
        lines.append("- Current evidence does not prove a reliable production alpha.")
    if failure_summary:
        counts = failure_summary.get("failure_counts") or {}
        dead_market = int(counts.get("FEE_SLIPPAGE_KILLED") or 0) + int(counts.get("TIMEOUT_NO_EDGE") or 0)
        total = int(failure_summary.get("row_count") or 0)
        if total:
            lines.append(
                f"- FEE_SLIPPAGE_KILLED + TIMEOUT_NO_EDGE = {dead_market}/{total}; "
                "this points to non-tradeable entry timing rather than a simple direction fix."
            )
    if learned_policy and learned_policy.get("status") == "INSUFFICIENT_DATA_WINDOW":
        lines.append("- Walkforward is semantically invalid for promotion because train/validation/holdout windows are not populated.")
    if confidence_summary and confidence_summary.get("status") == "CONFIDENCE_MISORDERED":
        lines.append("- Confidence is not monotonic with realized net-positive outcomes; confidence cannot be trusted as-is.")
    if learned_policy and learned_policy.get("status") != "PASS_SHADOW_CANDIDATE":
        lines.append("- The deterministic no-entry filter did not pass the configured shadow acceptance gate.")
    lines.extend(["", "## ASSUMPTIONS", ""])
    lines.append("- Replay-derived outcomes are treated as official-eligible only when sourced from real candles/runtime artifacts.")
    lines.append("- MFE/MAE exit-template search is an approximation until rematerialized with candle-path TP/SL rules.")
    lines.append("- V1 learning is deterministic rule search; ML rankers remain future challengers.")
    lines.extend(["", "## UNKNOWNS", ""])
    lines.append("- Live execution PnL remains unproven by this shadow report.")
    lines.append("- Incumbent-vs-Judge value remains unproven without an incumbent baseline artifact.")
    lines.append("- Longer real-data windows and completed-day coverage are required before promoting any candidate.")
    lines.append("")
    return "\n".join(lines)


def run_write_learning_report(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    dataset_root = dataset_root_for(Path(args.data_root), args.dataset_id)
    output_path = Path(args.output_path) if args.output_path else DEFAULT_ARTIFACT_ROOT / "ALPHA_SEARCH_LEARNING_REPORT.md"
    dataset_manifest = _load_json_if_exists(Path(args.dataset_manifest)) if args.dataset_manifest else _load_json_if_exists(dataset_root / "dataset_manifest.json")
    failure_summary = _load_json_if_exists(Path(args.failure_summary)) if args.failure_summary else _load_json_if_exists(dataset_root / "failure_diagnostics_summary.json")
    ceiling_report = _load_json_if_exists(Path(args.ceiling_report)) if args.ceiling_report else _load_json_if_exists(dataset_root / "ceiling_report.json")
    confidence_summary = _load_json_if_exists(Path(args.confidence_summary)) if args.confidence_summary else None
    learned_policy = _load_json_if_exists(Path(args.learned_policy)) if args.learned_policy else None
    text = render_learning_report(
        dataset_manifest=dataset_manifest,
        failure_summary=failure_summary,
        ceiling_report=ceiling_report,
        confidence_summary=confidence_summary,
        learned_policy=learned_policy,
    )
    atomic_write_text(output_path, text)
    with connect_db(db_path) as con:
        record_artifact(
            con,
            dataset_id=args.dataset_id,
            run_id=args.run_id,
            artifact_type="alpha_search_learning_report",
            path=output_path,
            provenance_class="replay_derived",
        )
    print(json.dumps({"status": "ok", "report": str(output_path)}, sort_keys=True))
    return 0


def load_rows_any(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    return read_jsonl(path)


def validate_candle_row(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    timestamp = coerce_int(row.get("timestamp") or row.get("close_time_ms") or row.get("bar_close_ts"))
    open_px = coerce_float(row.get("open"))
    high = coerce_float(row.get("high"))
    low = coerce_float(row.get("low"))
    close = coerce_float(row.get("close"))
    volume = coerce_float(row.get("volume"))
    if timestamp is None or timestamp % MINUTE_MS != MINUTE_MS - 1:
        errors.append("bar_close_timestamp_not_1m_close")
    if None in (open_px, high, low, close):
        errors.append("missing_ohlc")
    else:
        assert open_px is not None and high is not None and low is not None and close is not None
        if high < max(open_px, close) or low > min(open_px, close) or high < low:
            errors.append("ohlc_geometry_invalid")
    if volume is not None and volume < 0:
        errors.append("negative_volume")
    return errors


def _return_std(rows: Sequence[Mapping[str, Any]]) -> float | None:
    closes = [coerce_float(row.get("close")) for row in rows]
    closes = [v for v in closes if v is not None and v > 0]
    if len(closes) < 3:
        return None
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    var = sum((x - mean) ** 2 for x in returns) / len(returns)
    return math.sqrt(var)


def run_validate_synthetic(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("synthetic")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_ARTIFACT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    synthetic_path = Path(args.synthetic_path)
    rows = load_rows_any(synthetic_path)
    invalid_rows = []
    missing_tag_count = 0
    for idx, row in enumerate(rows):
        if str(row.get("provenance_class") or "") != "synthetic_stress":
            missing_tag_count += 1
        errors = validate_candle_row(row)
        if errors:
            invalid_rows.append({"row_index": idx, "errors": errors})
    real_std = None
    synthetic_std = _return_std(rows)
    std_ratio = None
    if args.real_reference_path:
        real_rows = load_rows_any(Path(args.real_reference_path))
        real_std = _return_std(real_rows)
        if real_std and synthetic_std is not None:
            std_ratio = synthetic_std / real_std if real_std > 0 else None

    status = "PASS_STRESS_DATASET"
    if missing_tag_count or invalid_rows:
        status = "FAIL_SYNTHETIC_CONTRACT"
    elif std_ratio is not None and not (0.1 <= std_ratio <= 10.0):
        status = "WARN_DISTRIBUTION_OUTSIDE_BROAD_REAL_RANGE"

    report = {
        "schema_version": "alpha_factory_synthetic_validation_v1",
        "run_id": run_id,
        "status": status,
        "synthetic_path": str(synthetic_path),
        "row_count": len(rows),
        "missing_synthetic_stress_tag_count": missing_tag_count,
        "invalid_row_count": len(invalid_rows),
        "invalid_examples": invalid_rows[:20],
        "distribution_checks": {
            "synthetic_return_std": synthetic_std,
            "real_reference_return_std": real_std,
            "std_ratio": std_ratio,
            "broad_acceptance_range": [0.1, 10.0],
        },
        "official_metric_eligibility": "forbidden",
    }
    report_path = output_dir / "synthetic_validation.json"
    write_json(report_path, report)
    with connect_db(db_path) as con:
        record_artifact(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_type="synthetic_validation",
            path=report_path,
            provenance_class="synthetic_stress",
        )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=report_path,
            provenance_class="synthetic_stress",
            reason="synthetic_stress_validation_excluded_from_official_metrics",
        )
    print(json.dumps({"run_id": run_id, "status": status, "report": str(report_path)}, sort_keys=True))
    return 0 if status != "FAIL_SYNTHETIC_CONTRACT" else 2


def _sample_or_default(rng: random.Random, values: Sequence[float], default: float) -> float:
    if not values:
        return default
    return float(values[rng.randrange(0, len(values))])


def _clip(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def generate_synthetic_rows(
    real_rows: Sequence[Mapping[str, Any]],
    *,
    output_rows: int,
    seed: int,
    start_timestamp: int | None = None,
) -> list[dict[str, Any]]:
    ordered = sorted(
        [row for row in real_rows if coerce_float(row.get("close")) is not None],
        key=lambda row: coerce_int(row.get("timestamp") or row.get("close_time_ms") or row.get("bar_close_ts")) or 0,
    )
    if len(ordered) < 3:
        raise ValueError("Synthetic generation requires at least 3 reference OHLCV rows")

    closes = [coerce_float(row.get("close")) for row in ordered]
    opens = [coerce_float(row.get("open")) for row in ordered]
    highs = [coerce_float(row.get("high")) for row in ordered]
    lows = [coerce_float(row.get("low")) for row in ordered]
    volumes = [coerce_float(row.get("volume")) for row in ordered]
    assert all(value is not None for value in closes)

    returns: list[float] = []
    upper_wicks: list[float] = []
    lower_wicks: list[float] = []
    volume_ratios: list[float] = []
    for idx in range(1, len(ordered)):
        prev_close = float(closes[idx - 1] or 0.0)
        cur_close = float(closes[idx] or 0.0)
        if prev_close > 0:
            returns.append(_clip((cur_close / prev_close) - 1.0, -0.25, 0.25))
        open_px = float(opens[idx] or cur_close)
        high = float(highs[idx] or max(open_px, cur_close))
        low = float(lows[idx] or min(open_px, cur_close))
        base_hi = max(open_px, cur_close)
        base_lo = min(open_px, cur_close)
        if base_hi > 0:
            upper_wicks.append(_clip(max(0.0, high / base_hi - 1.0), 0.0, 0.25))
        if base_lo > 0:
            lower_wicks.append(_clip(max(0.0, 1.0 - low / base_lo), 0.0, 0.25))
        prev_vol = float(volumes[idx - 1] or 0.0)
        cur_vol = float(volumes[idx] or 0.0)
        if prev_vol > 0 and cur_vol >= 0:
            volume_ratios.append(_clip(cur_vol / prev_vol, 0.05, 20.0))

    rng = random.Random(seed)
    symbol = str(ordered[0].get("symbol") or "SYNTHUSDT").upper()
    tf_sec = int(coerce_int(ordered[0].get("tf_sec")) or 60)
    ts = start_timestamp
    if ts is None:
        first_ts = coerce_int(ordered[0].get("timestamp") or ordered[0].get("close_time_ms") or ordered[0].get("bar_close_ts"))
        ts = first_ts if first_ts is not None else 59_999
    if ts % MINUTE_MS != MINUTE_MS - 1:
        q, _ = divmod(ts, MINUTE_MS)
        ts = (q + 1) * MINUTE_MS - 1

    price = float(closes[0] or 1.0)
    volume = float(volumes[0] or 1.0)
    source_hash = stable_hash(list(ordered), length=32)
    out: list[dict[str, Any]] = []
    for idx in range(output_rows):
        open_px = max(0.00000001, price)
        ret = _sample_or_default(rng, returns, 0.0)
        close = max(0.00000001, open_px * (1.0 + ret))
        upper = _sample_or_default(rng, upper_wicks, abs(ret) * 0.5)
        lower = _sample_or_default(rng, lower_wicks, abs(ret) * 0.5)
        high = max(open_px, close) * (1.0 + upper)
        low = min(open_px, close) * max(0.00000001, 1.0 - lower)
        volume = max(0.0, volume * _sample_or_default(rng, volume_ratios, 1.0))
        out.append(
            {
                "timestamp": ts + idx * MINUTE_MS,
                "datetime": datetime.fromtimestamp((ts + idx * MINUTE_MS) / 1000.0, tz=timezone.utc).isoformat(),
                "symbol": symbol,
                "tf_sec": tf_sec,
                "open": f"{open_px:.10f}",
                "high": f"{high:.10f}",
                "low": f"{low:.10f}",
                "close": f"{close:.10f}",
                "volume": f"{volume:.10f}",
                "trade_count": int(max(1, round(volume))),
                "provenance_class": "synthetic_stress",
                "source_mode": "synthetic_repair",
                "synthetic_seed": seed,
                "synthetic_source_hash": source_hash,
                "synthetic_generator": "alpha_factory_v1_bootstrap_sampler",
            }
        )
        price = close
    return out


def run_generate_synthetic(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    run_id = args.run_id or utc_run_id("synthetic_gen")
    real_reference_path = Path(args.real_reference_path)
    output_path = Path(args.output_path)
    real_rows = load_rows_any(real_reference_path)
    rows = generate_synthetic_rows(
        real_rows,
        output_rows=int(args.rows),
        seed=int(args.seed),
        start_timestamp=coerce_int(args.start_timestamp),
    )
    if output_path.suffix.lower() == ".csv":
        write_csv(output_path, rows, list(rows[0].keys()))
    else:
        write_jsonl(output_path, rows)
    invalid = [
        {"row_index": idx, "errors": validate_candle_row(row)}
        for idx, row in enumerate(rows)
        if validate_candle_row(row)
    ]
    manifest = {
        "schema_version": "alpha_factory_synthetic_generation_v1",
        "run_id": run_id,
        "created_at_utc": utc_now_iso(),
        "real_reference_path": str(real_reference_path),
        "output_path": str(output_path),
        "rows": len(rows),
        "seed": int(args.seed),
        "provenance_class": "synthetic_stress",
        "official_metric_eligibility": "forbidden",
        "invalid_row_count": len(invalid),
        "invalid_examples": invalid[:20],
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    write_json(manifest_path, manifest)
    with connect_db(db_path) as con:
        for path, artifact_type in [
            (output_path, "synthetic_stress_dataset"),
            (manifest_path, "synthetic_generation_manifest"),
        ]:
            record_artifact(
                con,
                dataset_id=args.dataset_id,
                run_id=run_id,
                artifact_type=artifact_type,
                path=path,
                provenance_class="synthetic_stress",
            )
        record_provenance_event(
            con,
            dataset_id=args.dataset_id,
            run_id=run_id,
            artifact_path=output_path,
            provenance_class="synthetic_stress",
            reason="synthetic_stress_generated_from_real_distribution_bootstrap",
        )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": "ok" if not invalid else "generated_with_invalid_rows",
                "output_path": str(output_path),
                "manifest": str(manifest_path),
            },
            sort_keys=True,
        )
    )
    return 0 if not invalid else 2


def _load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_factory_report(
    *,
    dataset_manifest: Mapping[str, Any] | None,
    coverage_report: Mapping[str, Any] | None,
    search_summary: Mapping[str, Any] | None,
) -> str:
    status = "INSUFFICIENT_EVIDENCE"
    if search_summary and search_summary.get("status") == "CANDIDATE_FOUND_SHADOW_ONLY":
        status = "CANDIDATE_FOUND_SHADOW_ONLY"
    missing_minutes = None
    if coverage_report:
        missing_minutes = (coverage_report.get("totals") or {}).get("missing_minutes")
    top = search_summary.get("top_candidate") if search_summary else None
    lines = [
        "# Alpha Search Factory Report",
        "",
        f"Executive verdict: {status}",
        "",
        "This report is shadow-only evidence. It does not authorize live admission,",
        "Judge mode widening, decision_making changes, or execution_position changes.",
        "",
        "## FACTS",
        "",
    ]
    if dataset_manifest:
        lines.append(f"- Dataset: {dataset_manifest.get('dataset_id')} status={dataset_manifest.get('status')}")
        lines.append(f"- Universe: {', '.join(dataset_manifest.get('universe') or [])}")
    else:
        lines.append("- Dataset manifest was not supplied.")
    if coverage_report:
        totals = coverage_report.get("totals") or {}
        lines.append(
            f"- Candle coverage: required={totals.get('required_minutes')} "
            f"present={totals.get('present_minutes')} missing={totals.get('missing_minutes')}"
        )
    else:
        lines.append("- Candle coverage report was not supplied.")
    if search_summary:
        lines.append(
            f"- Search candidates: total={search_summary.get('candidate_count')} "
            f"pass={search_summary.get('pass_count')} target_win_rate={search_summary.get('target_win_rate')}"
        )
    else:
        lines.append("- Search summary was not supplied.")

    lines.extend(["", "## INFERENCES", ""])
    if top:
        lines.append(
            f"- Top candidate status={top.get('acceptance_status')} "
            f"selected={top.get('selected_count')} win_rate={top.get('win_rate')} "
            f"avg_net_return={top.get('avg_net_return')}"
        )
    if missing_minutes not in (None, 0):
        lines.append("- Incomplete candle coverage weakens any economic conclusion.")
    if status == "INSUFFICIENT_EVIDENCE":
        lines.append("- Current evidence is not sufficient to claim a production alpha.")
    else:
        lines.append("- A shadow-only candidate exists and still requires out-of-sample review.")

    lines.extend(["", "## ASSUMPTIONS", ""])
    lines.append("- Calibration outcomes are assumed correct beyond schema and provenance checks.")
    lines.append("- `replay_derived` rows are official-eligible only when produced from real candles/runtime artifacts.")
    lines.append("- Synthetic stress data is useful for robustness testing but excluded from official metrics.")

    lines.extend(["", "## UNKNOWNS", ""])
    lines.append("- Out-of-sample profitability is not proven by this V1 report.")
    lines.append("- Incumbent-vs-judge value remains unproven unless a baseline artifact is supplied.")
    lines.append("- TP/SL and hold-horizon candidates require rematerialized outcomes before official comparison.")
    lines.append("")
    return "\n".join(lines)


def run_write_report(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ensure_schema(db_path)
    output_path = Path(args.output_path)
    dataset_manifest = _load_json_if_exists(Path(args.dataset_manifest)) if args.dataset_manifest else None
    coverage_report = _load_json_if_exists(Path(args.coverage_report)) if args.coverage_report else None
    search_summary = _load_json_if_exists(Path(args.search_summary)) if args.search_summary else None
    text = render_factory_report(
        dataset_manifest=dataset_manifest,
        coverage_report=coverage_report,
        search_summary=search_summary,
    )
    atomic_write_text(output_path, text)
    with connect_db(db_path) as con:
        record_artifact(
            con,
            dataset_id=args.dataset_id,
            run_id=args.run_id,
            artifact_type="alpha_factory_report",
            path=output_path,
            provenance_class="replay_derived",
        )
    print(json.dumps({"status": "ok", "report": str(output_path)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit-data")
    audit.add_argument("--run-id", default=None)
    audit.add_argument("--dataset-id", default=None)
    audit.add_argument("--judge-log-dir", default=str(DEFAULT_JUDGE_LOG_DIR))
    audit.add_argument("--raw-1m-dir", default=str(DEFAULT_RAW_1M_DIR))
    audit.add_argument("--horizon-bars", type=int, default=12)
    audit.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    audit.add_argument("--days-back", type=int, default=90, help="Completed UTC days to audit; use 0 for current Judge window.")
    audit.add_argument("--output-dir", default=None)
    audit.set_defaults(func=run_audit_data)

    build = sub.add_parser("build-dataset")
    build.add_argument("--dataset-id", default=None)
    build.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    build.add_argument("--judge-log-dir", default=str(DEFAULT_JUDGE_LOG_DIR))
    build.add_argument("--raw-1m-dir", default=str(DEFAULT_RAW_1M_DIR))
    build.add_argument("--recorder-1m-dir", default=str(DEFAULT_RECORDER_1M_DIR))
    build.add_argument("--horizon-bars", type=int, default=12)
    build.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    build.add_argument("--days-back", type=int, default=90, help="Completed UTC days to build; use 0 for current Judge window.")
    build.set_defaults(func=run_build_dataset)

    mat = sub.add_parser("materialize-outcomes")
    mat.add_argument("--dataset-id", required=True)
    mat.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    mat.add_argument("--judge-log-dir", default=str(DEFAULT_JUDGE_LOG_DIR))
    mat.add_argument("--raw-1m-dir", default=str(DEFAULT_RAW_1M_DIR))
    mat.add_argument("--recorder-1m-dir", default=str(DEFAULT_RECORDER_1M_DIR))
    mat.add_argument("--simulator-config", default=str(DEFAULT_SIMULATOR_CONFIG))
    mat.add_argument("--horizon-bars", type=int, default=12)
    mat.add_argument("--output-dir", default=None)
    mat.set_defaults(func=run_materialize_outcomes)

    baseline = sub.add_parser("run-baseline")
    baseline.add_argument("--dataset-id", required=True)
    baseline.add_argument("--run-id", default=None)
    baseline.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    baseline.add_argument("--outcomes-path", default=None)
    baseline.add_argument("--simulator-config", default=str(DEFAULT_SIMULATOR_CONFIG))
    baseline.add_argument("--review-config", default=str(DEFAULT_REVIEW_CONFIG))
    baseline.add_argument("--output-dir", default=None)
    baseline.set_defaults(func=run_baseline)

    search = sub.add_parser("search-candidates")
    search.add_argument("--dataset-id", default=None)
    search.add_argument("--run-id", default=None)
    search.add_argument("--calibration-path", default=str(DEFAULT_CALIBRATION_PATH))
    search.add_argument("--path-diagnostics", default=None)
    search.add_argument("--output-dir", default=None)
    search.add_argument("--target-win-rate", type=float, default=0.70)
    search.add_argument("--min-selected", type=int, default=30)
    search.add_argument("--confidence-thresholds", default=None)
    search.add_argument("--symbols", default="*")
    search.add_argument("--tf-secs", default="*")
    search.add_argument("--regimes", default="*")
    search.add_argument("--min-spacing-bars", default=None)
    search.add_argument("--tp-offsets", default="existing")
    search.add_argument("--sl-offsets", default="existing")
    search.add_argument("--hold-horizons", default="existing")
    search.set_defaults(func=run_search_candidates)

    diag = sub.add_parser("diagnose-failures")
    diag.add_argument("--dataset-id", required=True)
    diag.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    diag.add_argument("--calibration-path", default=str(DEFAULT_CALIBRATION_PATH))
    diag.add_argument("--outcomes-diagnostics-path", default=None)
    diag.add_argument("--output-dir", default=None)
    diag.set_defaults(func=run_diagnose_failures)

    features = sub.add_parser("build-feature-matrix")
    features.add_argument("--dataset-id", required=True)
    features.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    features.add_argument("--calibration-path", default=str(DEFAULT_CALIBRATION_PATH))
    features.add_argument("--outcomes-diagnostics-path", default=None)
    features.add_argument("--raw-1m-dir", default=str(DEFAULT_RAW_1M_DIR))
    features.add_argument("--output-dir", default=None)
    features.set_defaults(func=run_build_feature_matrix)

    ceilings = sub.add_parser("compute-ceilings")
    ceilings.add_argument("--dataset-id", required=True)
    ceilings.add_argument("--run-id", default=None)
    ceilings.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    ceilings.add_argument("--feature-matrix", default=None)
    ceilings.add_argument("--target-win-rate", type=float, default=0.70)
    ceilings.add_argument("--min-selected", type=int, default=100)
    ceilings.add_argument("--output-dir", default=None)
    ceilings.set_defaults(func=run_compute_ceilings)

    exits = sub.add_parser("search-exit-templates")
    exits.add_argument("--dataset-id", required=True)
    exits.add_argument("--run-id", default=None)
    exits.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    exits.add_argument("--feature-matrix", default=None)
    exits.add_argument("--target-win-rate", type=float, default=0.70)
    exits.add_argument("--min-selected", type=int, default=100)
    exits.add_argument("--confidence-thresholds", default=None)
    exits.add_argument("--tp-pcts", default=None)
    exits.add_argument("--sl-pcts", default=None)
    exits.add_argument("--output-dir", default=None)
    exits.set_defaults(func=run_search_exit_templates)

    confidence = sub.add_parser("calibrate-confidence")
    confidence.add_argument("--dataset-id", required=True)
    confidence.add_argument("--run-id", default=None)
    confidence.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    confidence.add_argument("--feature-matrix", default=None)
    confidence.add_argument("--output-dir", default=None)
    confidence.set_defaults(func=run_calibrate_confidence)

    walk = sub.add_parser("run-walkforward")
    walk.add_argument("--dataset-id", required=True)
    walk.add_argument("--run-id", default=None)
    walk.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    walk.add_argument("--feature-matrix", default=None)
    walk.add_argument("--split-mode", choices=["fixed-days", "ratio"], default="fixed-days")
    walk.add_argument("--train-days", type=int, default=60)
    walk.add_argument("--validation-days", type=int, default=15)
    walk.add_argument("--holdout-days", type=int, default=15)
    walk.add_argument("--target-win-rate", type=float, default=0.70)
    walk.add_argument("--min-selected", type=int, default=100)
    walk.add_argument("--min-validation-win-rate", type=float, default=0.65)
    walk.add_argument("--max-validation-holdout-drop", type=float, default=0.15)
    walk.add_argument("--confidence-thresholds", default=None)
    walk.add_argument("--output-dir", default=None)
    walk.set_defaults(func=run_walkforward)

    synth = sub.add_parser("validate-synthetic")
    synth.add_argument("--dataset-id", default=None)
    synth.add_argument("--run-id", default=None)
    synth.add_argument("--synthetic-path", required=True)
    synth.add_argument("--real-reference-path", default=None)
    synth.add_argument("--output-dir", default=None)
    synth.set_defaults(func=run_validate_synthetic)

    gen = sub.add_parser("generate-synthetic")
    gen.add_argument("--dataset-id", default=None)
    gen.add_argument("--run-id", default=None)
    gen.add_argument("--real-reference-path", required=True)
    gen.add_argument("--output-path", required=True)
    gen.add_argument("--rows", type=int, default=500)
    gen.add_argument("--seed", type=int, default=7)
    gen.add_argument("--start-timestamp", default=None)
    gen.set_defaults(func=run_generate_synthetic)

    report = sub.add_parser("write-report")
    report.add_argument("--dataset-id", default=None)
    report.add_argument("--run-id", default=None)
    report.add_argument("--dataset-manifest", default=None)
    report.add_argument("--coverage-report", default=None)
    report.add_argument("--search-summary", default=None)
    report.add_argument("--output-path", default=str(DEFAULT_ARTIFACT_ROOT / "ALPHA_SEARCH_FACTORY_REPORT.md"))
    report.set_defaults(func=run_write_report)

    learning = sub.add_parser("write-learning-report")
    learning.add_argument("--dataset-id", required=True)
    learning.add_argument("--run-id", default=None)
    learning.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    learning.add_argument("--dataset-manifest", default=None)
    learning.add_argument("--failure-summary", default=None)
    learning.add_argument("--ceiling-report", default=None)
    learning.add_argument("--confidence-summary", default=None)
    learning.add_argument("--learned-policy", default=None)
    learning.add_argument("--output-path", default=str(DEFAULT_ARTIFACT_ROOT / "ALPHA_SEARCH_LEARNING_REPORT.md"))
    learning.set_defaults(func=run_write_learning_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
