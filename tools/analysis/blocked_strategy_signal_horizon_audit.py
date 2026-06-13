#!/usr/bin/env python3
"""Replay blocked strategy signals on fixed 15-minute horizons."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from pathlib import Path
from typing import Any

from tools.analysis.market_opportunity_funnel_audit import parse_strategy_traces, read_jsonl
from tools.analysis.nrr_rejected_horizon_audit import (
    assign_episodes,
    iso_utc,
    load_bars,
    replay_row,
    summarize,
    write_csv,
    write_json,
    write_jsonl,
)
from tools.analysis.strategy_delivery_funnel_audit import parse_core_delivery_events


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = ROOT / "reports" / "nrr_runtime_research_20260613"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay blocked strategy signals on 15-minute bars")
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_RESEARCH_ROOT / "source_snapshot")
    parser.add_argument("--logs-root", type=Path, default=ROOT / "logs")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_RESEARCH_ROOT / "blocked_signal_horizon")
    parser.add_argument("--horizons", default="1,2,4,8")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--episode-gap-min", type=int, default=60)
    return parser.parse_args(argv)


def _nearest_event(
    signal: dict[str, Any],
    events: list[dict[str, Any]],
    event_name: str,
    consumed: set[int],
    tolerance_ms: int = 10_000,
) -> tuple[int, dict[str, Any]] | None:
    observed = signal.get("observed_at_ms")
    if observed is None:
        return None
    candidates = [
        (index, event)
        for index, event in enumerate(events)
        if index not in consumed
        and event.get("event") == event_name
        and event.get("strategy_id") == signal.get("strategy_id")
        and event.get("symbol") == signal.get("symbol")
        and abs(int(event.get("timestamp_ms") or 0) - int(observed)) <= tolerance_ms
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(int(item[1]["timestamp_ms"]) - int(observed)))


def classify_signals(
    traces: list[dict[str, Any]],
    delivery_events: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signals = [
        row for row in traces
        if row.get("outcome") == "SIGNAL" and row.get("strategy_id") in {"md_amr", "mean_reversion"}
    ]
    rejects = [
        row for row in order_rows
        if row.get("event_type") == "DECISION_INTENT_REJECTED"
        and row.get("strategy_id") in {"md_amr", "mean_reversion"}
    ]
    rejects.sort(key=lambda row: int(row.get("timestamp") or 0))
    reject_times = [int(row.get("timestamp") or 0) for row in rejects]
    consumed_delivery: set[int] = set()
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for signal in sorted(signals, key=lambda row: int(row["timestamp_ms"])):
        key = (signal["strategy_id"], signal["symbol"], signal["side"], signal["timestamp_ms"])
        if key in seen:
            continue
        seen.add(key)
        ts_ms = int(signal["timestamp_ms"])
        matched_reject = None
        index = bisect_right(reject_times, ts_ms - 1)
        for candidate in rejects[index:]:
            candidate_ts = int(candidate.get("timestamp") or 0)
            if candidate_ts > ts_ms + 120_000:
                break
            if (
                str(candidate.get("strategy_id")) == signal["strategy_id"]
                and str(candidate.get("symbol") or "").upper() == signal["symbol"]
                and str(candidate.get("side") or "").upper() == signal["side"]
            ):
                matched_reject = candidate
                break

        kelly_match = _nearest_event(signal, delivery_events, "KELLY_CONFIG_BLOCK", consumed_delivery)
        emitted_match = _nearest_event(signal, delivery_events, "SIGNAL_EMITTED", consumed_delivery)
        if matched_reject is not None:
            category = "DECISION_NRR_REJECTED"
        elif kelly_match is not None:
            category = "KELLY_CONFIG_BLOCKED"
            consumed_delivery.add(kelly_match[0])
        elif signal["strategy_id"] == "md_amr" and signal.get("allowed_regime") is False and emitted_match is None:
            category = "REGIME_ALLOWLIST_BLOCKED"
        elif emitted_match is not None:
            category = "EMITTED_WITHOUT_ORDER_LOG_OUTCOME"
            consumed_delivery.add(emitted_match[0])
        else:
            category = "UNRESOLVED_POST_SIGNAL"

        output.append(
            {
                "timestamp_ms": ts_ms,
                "timestamp_utc": iso_utc(ts_ms),
                "observed_at_ms": signal.get("observed_at_ms"),
                "strategy_id": signal["strategy_id"],
                "symbol": signal["symbol"],
                "side": signal["side"],
                "regime": signal.get("regime"),
                "allowed_regime": signal.get("allowed_regime"),
                "block_category": category,
                "nrr_code": matched_reject.get("nrr_code") if matched_reject else None,
                "rid": matched_reject.get("rid") if matched_reject else None,
            }
        )
    return output


def build_report(summary: dict[str, Any], category_episode: list[dict[str, Any]], horizons: tuple[int, ...]) -> str:
    lines = [
        "# Blocked Strategy Signal 15m Horizon Audit",
        "",
        f"- Signals classified: `{summary['signals']}`",
        f"- Signals replayed: `{summary['replayed']}`",
        f"- Round-trip cost: `{summary['cost_bps']}` bps",
        "- Entry: open of the first full 15-minute bar starting after the signal timestamp.",
        "",
        "## Episode-Level Results",
        "",
    ]
    for row in category_episode:
        parts = [f"{row['block_category']}: episodes={row['rows']}"]
        for horizon in horizons:
            value = row.get(f"h{horizon}_mean_net_bps")
            if value is not None:
                parts.append(
                    f"{horizon}b={value:+.2f}bps, positive={row[f'h{horizon}_positive_rate_pct']:.1f}% (n={row[f'h{horizon}_n']})"
                )
        lines.append("- " + "; ".join(parts))
    lines.extend([
        "",
        "## Guardrails",
        "",
        "- These are signal-following counterfactuals, not an optimized portfolio backtest.",
        "- Episode-level rows reduce repeated-signal correlation and are the primary comparison.",
        "- A profitable blocked bucket warrants recalibration and forward validation, not blind gate removal.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    horizons = tuple(sorted({int(value) for value in args.horizons.split(",") if int(value) > 0}))
    order_rows = read_jsonl(args.snapshot_root / "logs" / "order_log_v1.jsonl")
    timestamps = [int(row["timestamp"]) for row in order_rows if row.get("timestamp") is not None]
    start_ms, end_ms = min(timestamps), max(timestamps)
    traces = parse_strategy_traces(args.logs_root, start_ms, end_ms)
    delivery_events = parse_core_delivery_events(args.logs_root, start_ms, end_ms)
    classified = classify_signals(traces, delivery_events, order_rows)
    bars_by_symbol, coverage = load_bars(
        args.snapshot_root / "data" / "recorder", {row["symbol"] for row in classified}
    )
    replayed = [
        replay_row(row, bars_by_symbol.get(row["symbol"], []), horizons, args.cost_bps)
        for row in classified
    ]
    for row in replayed:
        row["nrr_code"] = row["block_category"]
    assign_episodes(replayed, args.episode_gap_min)
    for row in replayed:
        row.pop("nrr_code", None)

    summaries: dict[str, list[dict[str, Any]]] = {}
    for name, fields in {
        "by_category": ("block_category",),
        "by_strategy_category": ("strategy_id", "block_category"),
        "by_symbol_category": ("symbol", "block_category"),
    }.items():
        summaries[name] = summarize(replayed, fields, horizons, False) + summarize(replayed, fields, horizons, True)

    summary = {
        "start_utc": iso_utc(start_ms),
        "end_utc": iso_utc(end_ms),
        "signals": len(classified),
        "replayed": sum(row.get("replay_status") == "REPLAYED" for row in replayed),
        "episodes": len({row["episode_id"] for row in replayed}),
        "cost_bps": args.cost_bps,
        "horizons_15m_bars": horizons,
        "category_counts": {},
    }
    for row in classified:
        summary["category_counts"][row["block_category"]] = summary["category_counts"].get(row["block_category"], 0) + 1

    args.report_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.report_root / "blocked_signal_outcomes.jsonl", replayed)
    write_csv(args.report_root / "blocked_signal_outcomes.csv", replayed)
    write_json(args.report_root / "bar_coverage_900s.json", coverage)
    for name, rows in summaries.items():
        write_csv(args.report_root / f"summary_{name}.csv", rows)
        write_json(args.report_root / f"summary_{name}.json", rows)
    write_json(args.report_root / "summary.json", summary)
    category_episode = [row for row in summaries["by_category"] if row["level"] == "episode"]
    (args.report_root / "BLOCKED_STRATEGY_SIGNAL_15M_HORIZON_AUDIT.md").write_text(
        build_report(summary, category_episode, horizons), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
