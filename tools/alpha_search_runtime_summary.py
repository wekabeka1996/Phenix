#!/usr/bin/env python3
"""
Alpha Search Standalone Runtime Summary
======================================

Builds per-scenario summaries from standalone runtime logs:
  logs/alpha_search_runtime/<session_id>/S*/scores.jsonl

Outputs:
  - Optional global CSV/JSON
  - Optional per-session CSV in <session>/aggregate/scenario_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def _iter_sessions(root: Path, session: Optional[str], all_sessions: bool) -> List[Path]:
    dirs = sorted([d for d in root.iterdir() if d.is_dir()])
    if session:
        match = [d for d in dirs if d.name == session]
        if not match:
            raise FileNotFoundError(f"Session not found: {session}")
        return match
    if all_sessions:
        return dirs
    if not dirs:
        return []
    return [dirs[-1]]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _summarize_scores_file(path: Path) -> Dict[str, object]:
    total = 0
    buy = 0
    sell = 0
    neutral = 0
    score_sum = 0.0
    conf_sum = 0.0
    ts_min: Optional[int] = None
    ts_max: Optional[int] = None
    providers: Counter[str] = Counter()
    symbols: set[str] = set()
    invalid = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue

            total += 1
            side = str(rec.get("side", "NEUTRAL")).upper()
            if side == "BUY":
                buy += 1
            elif side == "SELL":
                sell += 1
            else:
                neutral += 1

            score_sum += _safe_float(rec.get("score", 0.0))
            conf_sum += _safe_float(rec.get("confidence", 0.0))

            ts = _safe_int(rec.get("ts_ms", 0))
            if ts > 0:
                ts_min = ts if ts_min is None else min(ts_min, ts)
                ts_max = ts if ts_max is None else max(ts_max, ts)

            provider = str(rec.get("provider_id", "")).strip()
            if provider:
                providers[provider] += 1

            symbol = str(rec.get("symbol", "")).strip()
            if symbol:
                symbols.add(symbol)

    return {
        "total_scores": total,
        "buy_count": buy,
        "sell_count": sell,
        "neutral_count": neutral,
        "avg_score": round(score_sum / total, 6) if total else 0.0,
        "avg_confidence": round(conf_sum / total, 6) if total else 0.0,
        "ts_min_ms": ts_min or 0,
        "ts_max_ms": ts_max or 0,
        "symbols_count": len(symbols),
        "providers": dict(providers),
        "invalid_lines": invalid,
    }


def summarize_session(session_dir: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    scenario_dirs = sorted(
        [
            d
            for d in session_dir.iterdir()
            if d.is_dir() and d.name != "aggregate" and d.name.startswith("S")
        ]
    )

    for sdir in scenario_dirs:
        score_file = sdir / "scores.jsonl"
        if not score_file.exists():
            rows.append(
                {
                    "session_id": session_dir.name,
                    "scenario_id": sdir.name,
                    "total_scores": 0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "neutral_count": 0,
                    "avg_score": 0.0,
                    "avg_confidence": 0.0,
                    "ts_min_ms": 0,
                    "ts_max_ms": 0,
                    "symbols_count": 0,
                    "providers": "{}",
                    "invalid_lines": 0,
                }
            )
            continue

        stats = _summarize_scores_file(score_file)
        rows.append(
            {
                "session_id": session_dir.name,
                "scenario_id": sdir.name,
                **stats,
                "providers": json.dumps(stats["providers"], ensure_ascii=False),
            }
        )

    return rows


def _write_csv(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "session_id",
        "scenario_id",
        "total_scores",
        "buy_count",
        "sell_count",
        "neutral_count",
        "avg_score",
        "avg_confidence",
        "symbols_count",
        "ts_min_ms",
        "ts_max_ms",
        "invalid_lines",
        "providers",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def _print_table(rows: List[Dict[str, object]]) -> None:
    if not rows:
        print("No scenario data found.")
        return
    print(
        "session_id,scenario_id,total_scores,buy,sell,neutral,avg_score,avg_confidence,symbols"
    )
    for r in rows:
        print(
            f"{r['session_id']},{r['scenario_id']},{r['total_scores']},"
            f"{r['buy_count']},{r['sell_count']},{r['neutral_count']},"
            f"{r['avg_score']},{r['avg_confidence']},{r['symbols_count']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize alpha_search standalone runtime sessions"
    )
    parser.add_argument(
        "--root",
        default="logs/alpha_search_runtime",
        help="Root with runtime sessions (default: logs/alpha_search_runtime)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Specific session id (e.g. 20260226_011222). "
        "If omitted, latest session is used unless --all is set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all sessions under --root",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Write combined CSV to this path",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Write combined JSON to this path",
    )
    parser.add_argument(
        "--write-per-session",
        action="store_true",
        help="Write <session>/aggregate/scenario_summary.csv for each processed session",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"Root not found: {root}")

    sessions = _iter_sessions(root, args.session, args.all)
    all_rows: List[Dict[str, object]] = []

    for session_dir in sessions:
        rows = summarize_session(session_dir)
        all_rows.extend(rows)
        if args.write_per_session:
            out = session_dir / "aggregate" / "scenario_summary.csv"
            _write_csv(out, rows)
            print(f"Wrote: {out}")

    _print_table(all_rows)

    if args.output_csv:
        out_csv = Path(args.output_csv)
        _write_csv(out_csv, all_rows)
        print(f"Wrote: {out_csv}")

    if args.output_json:
        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, indent=2, ensure_ascii=False)
        print(f"Wrote: {out_json}")


if __name__ == "__main__":
    main()
