#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.telemetry.trade_lifecycle_logger import (
    POSITION_POLICY_SIDECAR_RECORD_KIND,
    iter_trade_lifecycle_records,
)


DEFAULT_WAL_GLOB = "ops/wal/*.jsonl"
DEFAULT_ORDER_LOG = "logs/order_log_v1.jsonl"
DEFAULT_TRADE_LIFECYCLE = "logs/trade_lifecycle.jsonl"
INGRESS_EVENT_NAMES = (
    "PORTFOLIO_STATE_UPDATED",
    "ORDER_FILL",
    "TRADE_EXECUTED",
    "ORDER_STATE_CHANGED",
    "EXECUTION_CLOSE_RECONCILED",
    "FEATURES_CALCULATED",
    "REGIME_DETECTED",
)


def _load_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _policy_rows(path: Path) -> List[Dict[str, Any]]:
    return [
        record
        for record in iter_trade_lifecycle_records(
            log_file=str(path),
            include_policy_records=True,
        )
        if record.get("record_kind") == POSITION_POLICY_SIDECAR_RECORD_KIND
    ]


def _ingress_event_counts(rows: Iterable[Dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for record in rows:
        raw_name = str(
            record.get("verb")
            or record.get("event_type")
            or record.get("event")
            or record.get("type")
            or ""
        ).strip()
        normalized = raw_name[4:] if raw_name.startswith("EVT:") else raw_name
        if normalized in INGRESS_EVENT_NAMES:
            counts[normalized] += 1
    return counts


def _close_rows(order_log_path: Path, trade_lifecycle_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in _load_jsonl(order_log_path):
        event_type = record.get("event_type")
        if event_type in {"ORDER_FILLED", "ORDER_REJECTED", "ORDER_STATE_CHANGED"}:
            rows.append(
                {
                    "source": "order_log",
                    "event_type": event_type,
                    "symbol": record.get("symbol"),
                    "ts_ms": record.get("timestamp") or record.get("ts_ms") or 0,
                    "rid": record.get("rid"),
                }
            )
    for record in iter_trade_lifecycle_records(log_file=str(trade_lifecycle_path)):
        rows.append(
            {
                "source": "trade_lifecycle",
                "event_type": record.get("status") or record.get("event_type"),
                "symbol": record.get("symbol"),
                "ts_ms": record.get("close_ts_ms") or record.get("updated_ts_ms") or 0,
                "rid": record.get("rid"),
            }
        )
    return rows


def build_report(
    *,
    wal_glob: str,
    order_log_path: Path,
    trade_lifecycle_path: Path,
    overlap_window_ms: int,
) -> Dict[str, Any]:
    wal_files = [Path(path) for path in glob.glob(wal_glob)]
    wal_event_count = 0
    wal_ingress_counts: Counter = Counter()
    for wal_file in wal_files:
        wal_rows = list(_load_jsonl(wal_file))
        wal_event_count += len(wal_rows)
        wal_ingress_counts.update(_ingress_event_counts(wal_rows))

    policy_rows = _policy_rows(trade_lifecycle_path)
    close_rows = _close_rows(order_log_path, trade_lifecycle_path)

    suppression_counts = Counter()
    event_type_counts = Counter()
    trigger_event_counts = Counter()
    explainable_rows = 0
    recommendations = []
    overlaps = []
    by_symbol = defaultdict(Counter)

    for row in policy_rows:
        event_type = row.get("event_type", "UNKNOWN")
        symbol = row.get("symbol", "__UNKNOWN__")
        event_type_counts[event_type] += 1
        by_symbol[symbol][event_type] += 1
        trigger_event = str(row.get("trigger_event") or "").strip()
        if trigger_event:
            trigger_event_counts[trigger_event] += 1

        if row.get("trace_id") and row.get("reason_codes") is not None and row.get("freshness_snapshot") is not None:
            explainable_rows += 1

        if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
            suppression_counts[row.get("suppression_reason", "UNKNOWN")] += 1

        if event_type == "POSITION_POLICY_SIDECAR_RECOMMENDED":
            recommendations.append(row)
            row_ts = int(row.get("ts_ms") or 0)
            row_symbol = row.get("symbol")
            candidate_closes = [
                close
                for close in close_rows
                if close.get("symbol") == row_symbol
                and abs(int(close.get("ts_ms") or 0) - row_ts) <= overlap_window_ms
            ]
            if candidate_closes:
                closest = min(
                    candidate_closes,
                    key=lambda close: abs(int(close.get("ts_ms") or 0) - row_ts),
                )
                overlaps.append(
                    {
                        "trace_id": row.get("trace_id"),
                        "symbol": row_symbol,
                        "recommendation_ts_ms": row_ts,
                        "close_source": closest["source"],
                        "close_event_type": closest["event_type"],
                        "close_ts_ms": closest["ts_ms"],
                        "delta_ms": int(closest["ts_ms"] or 0) - row_ts,
                    }
                )

    timing_deltas = [item["delta_ms"] for item in overlaps]
    mode_active_count = event_type_counts.get("POSITION_POLICY_SIDECAR_MODE_ACTIVE", 0)
    return {
        "wal": {
            "glob": wal_glob,
            "files_scanned": len(wal_files),
            "event_count": wal_event_count,
            "ingress_event_counts": {
                event_name: wal_ingress_counts.get(event_name, 0)
                for event_name in INGRESS_EVENT_NAMES
            },
        },
        "policy_rows": {
            "total": len(policy_rows),
            "event_type_counts": dict(event_type_counts),
            "observed_trigger_event_counts": dict(trigger_event_counts),
            "suppression_count_by_reason": dict(suppression_counts),
            "recommendation_count": event_type_counts.get("POSITION_POLICY_SIDECAR_RECOMMENDED", 0),
            "action_skipped_count": event_type_counts.get("POSITION_POLICY_SIDECAR_ACTION_SKIPPED", 0),
            "explainability_completeness": (
                explainable_rows / len(policy_rows) if policy_rows else 0.0
            ),
        },
        "overlap": {
            "window_ms": overlap_window_ms,
            "matched_recommendations": len(overlaps),
            "mean_delta_ms": mean(timing_deltas) if timing_deltas else None,
            "samples": overlaps[:20],
        },
        "bootstrap": {
            "mode_active_count": mode_active_count,
            "mode_active_present": mode_active_count > 0,
            "signal": None if mode_active_count > 0 else "missing_mode_active_row",
        },
        "slices": {
            "by_symbol": {symbol: dict(counts) for symbol, counts in by_symbol.items()},
        },
        "paths": {
            "order_log": str(order_log_path),
            "order_log_exists": order_log_path.exists(),
            "trade_lifecycle": str(trade_lifecycle_path),
            "trade_lifecycle_exists": trade_lifecycle_path.exists(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Position Policy Sidecar shadow outputs.")
    parser.add_argument("--wal-glob", default=DEFAULT_WAL_GLOB)
    parser.add_argument("--order-log", default=DEFAULT_ORDER_LOG)
    parser.add_argument("--trade-lifecycle", default=DEFAULT_TRADE_LIFECYCLE)
    parser.add_argument("--overlap-window-ms", type=int, default=15 * 60 * 1000)
    parser.add_argument("--output-json", default="artifacts/position_policy_sidecar/package4_validation_summary.json")
    args = parser.parse_args()

    report = build_report(
        wal_glob=args.wal_glob,
        order_log_path=Path(args.order_log),
        trade_lifecycle_path=Path(args.trade_lifecycle),
        overlap_window_ms=args.overlap_window_ms,
    )

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
