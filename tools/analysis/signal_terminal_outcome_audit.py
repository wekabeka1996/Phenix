"""Audit strategy-signal terminal coverage across retained order-log rotations."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_REPORT_DIR = ROOT / "reports" / "signal_terminal_outcomes"

OUTCOME_PRECEDENCE = {
    "blocked": 10,
    "shadowed": 20,
    "intent": 30,
    "rejected": 40,
    "expired": 50,
    "filled": 60,
}


def order_log_paths(active: Path) -> list[Path]:
    rotations = sorted(active.parent.glob(f"{active.stem}.*{active.suffix}"))
    return [*rotations, active]


def read_rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw in enumerate(handle, start=1):
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    row["_source_file"] = path.name
                    row["_source_line"] = line_number
                    rows.append(row)
    return rows


def classify_terminal(row: dict[str, Any]) -> str | None:
    event_type = str(row.get("event_type") or "")
    if event_type == "STRATEGY_DECISION_BLOCKED":
        reason_code = str(row.get("reason_code") or "")
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        declared = str(metadata.get("terminal_outcome") or "").lower()
        if declared == "shadowed" or reason_code == "AUTHORITY_MODE_SHADOW":
            return "shadowed"
        return "blocked"
    if event_type in {"INTENT_BUILD_REJECTED", "DECISION_INTENT_REJECTED", "ORDER_REJECTED"}:
        return "rejected"
    if event_type in {"ORDER_TIMEOUT", "ORDER_CANCELLED"}:
        return "expired"
    if event_type == "ORDER_FILLED":
        return "filled"
    if event_type in {"ORDER_INTENT", "ORDER_PLACED"}:
        return "intent"
    return None


def build_audit(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    downstream: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rid = str(row.get("rid") or "").strip()
        if not rid:
            continue
        if row.get("event_type") == "STRATEGY_SIGNAL_PRODUCED":
            signals.setdefault(rid, row)
            continue
        if classify_terminal(row) is not None:
            downstream[rid].append(row)

    audit_rows: list[dict[str, Any]] = []
    attributed = 0
    outcome_counts: dict[str, int] = defaultdict(int)
    for rid, signal in sorted(signals.items()):
        candidates = downstream.get(rid, [])
        classified = [(classify_terminal(row), row) for row in candidates]
        classified = [(outcome, row) for outcome, row in classified if outcome is not None]
        selected = max(
            classified,
            key=lambda item: (
                OUTCOME_PRECEDENCE[item[0]],
                int(item[1].get("timestamp") or 0),
            ),
            default=(None, None),
        )
        outcome, terminal_row = selected
        if outcome is not None:
            outcome_counts[outcome] += 1
        attribution_ok = bool(
            terminal_row
            and terminal_row.get("strategy_id")
            and terminal_row.get("symbol")
        )
        if attribution_ok:
            attributed += 1
        lifecycle = sorted({outcome for outcome, _ in classified})
        audit_rows.append({
            "rid": rid,
            "strategy_id": signal.get("strategy_id"),
            "symbol": signal.get("symbol"),
            "side": signal.get("side"),
            "regime": signal.get("regime"),
            "signal_timestamp": signal.get("timestamp"),
            "terminal_outcome": outcome,
            "terminal_event_type": terminal_row.get("event_type") if terminal_row else None,
            "terminal_timestamp": terminal_row.get("timestamp") if terminal_row else None,
            "lifecycle_outcomes": lifecycle,
            "terminal_rows_seen": len(classified),
            "attribution_ok": attribution_ok,
        })

    signal_count = len(audit_rows)
    terminal_count = sum(1 for row in audit_rows if row["terminal_outcome"] is not None)
    summary = {
        "signals": signal_count,
        "signals_with_terminal_outcome": terminal_count,
        "signals_missing_terminal_outcome": signal_count - terminal_count,
        "terminal_coverage_pct": round(100.0 * terminal_count / signal_count, 4) if signal_count else 100.0,
        "attribution_coverage_pct": round(100.0 * attributed / terminal_count, 4) if terminal_count else 100.0,
        "outcome_counts": dict(sorted(outcome_counts.items())),
    }
    return audit_rows, summary


def write_report(report_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["rid", "terminal_outcome"]
    with (report_dir / "signal_terminal_outcomes.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=True) if isinstance(value, list) else value
                for key, value in row.items()
            })
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-log", type=Path, default=DEFAULT_ORDER_LOG)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    rows = read_rows(order_log_paths(args.order_log))
    audit_rows, summary = build_audit(rows)
    write_report(args.report_dir, audit_rows, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.strict and (
        summary["terminal_coverage_pct"] < 100.0
        or summary["attribution_coverage_pct"] < 99.0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
