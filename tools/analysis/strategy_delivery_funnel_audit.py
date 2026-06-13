#!/usr/bin/env python3
"""Audit whether configured strategy signals can reach the order log."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from tools.analysis.market_opportunity_funnel_audit import (
    core_log_paths,
    iso_utc,
    parse_strategy_traces,
    prefix_ts_ms,
    read_jsonl,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = ROOT / "reports" / "nrr_runtime_research_20260613"
KELLY_BLOCK_RE = re.compile(
    r"\[(?P<symbol>[A-Z0-9]+)\] Kelly metadata config block: "
    r"Missing decision(?:\.kelly)? config for strategy: (?P<strategy>[a-z0-9_]+)"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit strategy signal delivery to decision and execution")
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_RESEARCH_ROOT / "source_snapshot")
    parser.add_argument("--logs-root", type=Path, default=ROOT / "logs")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_RESEARCH_ROOT / "strategy_delivery_funnel")
    return parser.parse_args(argv)


def parse_core_delivery_events(logs_root: Path, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in core_log_paths(logs_root):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                observed_ms = prefix_ts_ms(raw)
                if observed_ms is None or not (start_ms <= observed_ms <= end_ms):
                    continue
                if "MD_AMR_SIGNAL_EMITTED " in raw:
                    try:
                        payload = json.loads(raw.split("MD_AMR_SIGNAL_EMITTED ", 1)[1])
                    except json.JSONDecodeError:
                        continue
                    events.append(
                        {
                            "timestamp_ms": observed_ms,
                            "event": "SIGNAL_EMITTED",
                            "strategy_id": "md_amr",
                            "symbol": str(payload.get("symbol") or "").upper(),
                            "side": str(payload.get("side") or "").upper(),
                            "rid": payload.get("rid"),
                            "source_file": path.name,
                        }
                    )
                match = KELLY_BLOCK_RE.search(raw)
                if match:
                    events.append(
                        {
                            "timestamp_ms": observed_ms,
                            "event": "KELLY_CONFIG_BLOCK",
                            "strategy_id": match.group("strategy"),
                            "symbol": match.group("symbol"),
                            "side": None,
                            "rid": None,
                            "source_file": path.name,
                        }
                    )
    return events


def load_registry_rows(snapshot_root: Path) -> list[dict[str, Any]]:
    config_root = snapshot_root / "config" / "aurora"
    registry = yaml.safe_load((config_root / "strategies.yaml").read_text(encoding="utf-8")) or {}
    assignments = registry.get("assignments") or {}
    symbols_by_strategy: dict[str, list[str]] = defaultdict(list)
    for symbol, strategies in assignments.items():
        for strategy_id in strategies or []:
            symbols_by_strategy[str(strategy_id)].append(str(symbol))

    rows: list[dict[str, Any]] = []
    for strategy_id, symbols in sorted(symbols_by_strategy.items()):
        profile_path = config_root / "strategies" / f"{strategy_id}.yaml"
        profile_exists = profile_path.exists()
        strategy_cfg: dict[str, Any] = {}
        if profile_exists:
            payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            candidate = payload.get(strategy_id) if isinstance(payload, dict) else None
            strategy_cfg = candidate if isinstance(candidate, dict) else {}
        decision = strategy_cfg.get("decision") if isinstance(strategy_cfg.get("decision"), dict) else {}
        rows.append(
            {
                "strategy_id": strategy_id,
                "assigned_symbols": sorted(symbols),
                "assigned_symbol_count": len(symbols),
                "profile_exists": profile_exists,
                "profile_enabled": strategy_cfg.get("enabled"),
                "decision_config_present": bool(decision),
                "decision_kelly_present": isinstance(decision.get("kelly"), dict),
                "profile_path": profile_path.relative_to(snapshot_root).as_posix(),
            }
        )
    return rows


def build_funnel_rows(
    traces: list[dict[str, Any]],
    delivery_events: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = {
        (str(row.get("strategy_id") or "unknown"), str(row.get("symbol") or "").upper())
        for row in traces + delivery_events + order_rows
        if row.get("symbol") and str(row.get("symbol")) != "_SYSTEM_"
    }
    results: list[dict[str, Any]] = []
    for strategy_id, symbol in sorted(keys):
        strategy_traces = [row for row in traces if row["strategy_id"] == strategy_id and row["symbol"] == symbol]
        core_signals = [row for row in strategy_traces if row["outcome"] == "SIGNAL"]
        emitted = [row for row in delivery_events if row["event"] == "SIGNAL_EMITTED" and row["strategy_id"] == strategy_id and row["symbol"] == symbol]
        kelly_blocks = [row for row in delivery_events if row["event"] == "KELLY_CONFIG_BLOCK" and row["strategy_id"] == strategy_id and row["symbol"] == symbol]
        strategy_orders = [
            row for row in order_rows
            if str(row.get("strategy_id") or "unknown") == strategy_id
            and str(row.get("symbol") or "").upper() == symbol
        ]
        trace_start_ms = min((row["timestamp_ms"] for row in strategy_traces), default=None)
        trace_end_ms = max((row["timestamp_ms"] for row in strategy_traces), default=None)
        visible_orders = [
            row for row in strategy_orders
            if trace_start_ms is not None
            and trace_end_ms is not None
            and trace_start_ms <= int(row.get("timestamp") or -1) <= trace_end_ms
        ]
        event_counts = Counter(str(row.get("event_type") or "") for row in visible_orders)
        runtime_event_counts = Counter(str(row.get("event_type") or "") for row in strategy_orders)
        nrr_counts = Counter(str(row.get("nrr_code") or "") for row in strategy_orders if row.get("event_type") == "DECISION_INTENT_REJECTED")
        results.append(
            {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "trace_rows": len(strategy_traces),
                "trace_start_utc": iso_utc(trace_start_ms),
                "trace_end_utc": iso_utc(trace_end_ms),
                "core_signals": len(core_signals),
                "neutral_or_suppressed": len(strategy_traces) - len(core_signals),
                "regime_blocked_core_signals": sum(
                    1 for row in core_signals
                    if strategy_id == "md_amr" and row.get("allowed_regime") is False
                ),
                "regime_allowed_core_signals": sum(
                    1 for row in core_signals
                    if strategy_id != "md_amr" or row.get("allowed_regime") is not False
                ),
                "mapping_shaped_regime_suppressions": sum(
                    1 for row in strategy_traces
                    if str(row.get("reason") or "").startswith("regime_not_allowed")
                    and str(row.get("regime") or "").lstrip().startswith("{")
                ),
                "signal_emitted": len(emitted),
                "kelly_config_blocks": len(kelly_blocks),
                "decision_rejects": event_counts["DECISION_INTENT_REJECTED"],
                "runtime_decision_rejects": runtime_event_counts["DECISION_INTENT_REJECTED"],
                "order_intents": event_counts["ORDER_INTENT"],
                "orders_placed": event_counts["ORDER_PLACED"],
                "orders_filled": event_counts["ORDER_FILLED"],
                "nrr_codes": dict(sorted(nrr_counts.items())),
            }
        )
    return [row for row in results if any(row[field] for field in (
        "trace_rows", "signal_emitted", "kelly_config_blocks", "decision_rejects", "order_intents", "orders_placed", "orders_filled"
    ))]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=True, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def render_report(summary: dict[str, Any], registry_rows: list[dict[str, Any]], funnel_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Strategy Delivery Funnel Audit",
        "",
        f"- Runtime order window: `{summary['start_utc']}` to `{summary['end_utc']}`",
        f"- Available strategy telemetry: `{summary['trace_start_utc']}` to `{summary['trace_end_utc']}`",
        "- Counts before the telemetry start are intentionally not inferred.",
        "",
        "## Configuration Reachability",
        "",
        "| Strategy | Assigned symbols | Profile enabled | decision | decision.kelly |",
        "|---|---|---:|---:|---:|",
    ]
    for row in registry_rows:
        lines.append(
            f"| {row['strategy_id']} | {', '.join(row['assigned_symbols'])} | {row['profile_enabled']} | "
            f"{row['decision_config_present']} | {row['decision_kelly_present']} |"
        )
    lines.extend([
        "",
        "## Observed Delivery",
        "",
        "| Strategy | Symbol | Core signals | Regime blocked | Emitted | Kelly blocked | Decision rejected in trace/full runtime | Intent | Placed | Filled |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in funnel_rows:
        if not any(row[field] for field in ("core_signals", "signal_emitted", "kelly_config_blocks", "decision_rejects", "order_intents", "orders_placed", "orders_filled")):
            continue
        lines.append(
            f"| {row['strategy_id']} | {row['symbol']} | {row['core_signals']} | "
            f"{row['regime_blocked_core_signals']} | {row['signal_emitted']} | {row['kelly_config_blocks']} | "
            f"{row['decision_rejects']}/{row['runtime_decision_rejects']} | {row['order_intents']} | {row['orders_placed']} | {row['orders_filled']} |"
        )
    lines.extend([
        "",
        "## Findings",
        "",
        f"- Missing `decision.kelly` was observed blocking `{summary['kelly_config_blocks']}` produced signals.",
        f"- MD-AMR produced `{summary['md_amr_core_signals']}` core signals; `{summary['md_amr_regime_blocked_signals']}` were stopped by its asset regime allowlists before emission.",
        f"- Mean reversion produced `{summary['mean_reversion_signals']}` logged signals and hit `{summary['mean_reversion_kelly_blocks']}` Kelly metadata blocks.",
        f"- Alpha handlers recorded `{summary['mapping_shaped_regime_suppressions']}` `regime_not_allowed` suppressions while receiving a mapping-shaped regime payload instead of a canonical label.",
        "- A strategy being assigned and enabled therefore does not imply it is financially reachable.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    order_path = args.snapshot_root / "logs" / "order_log_v1.jsonl"
    order_rows = read_jsonl(order_path)
    timestamps = [int(row["timestamp"]) for row in order_rows if row.get("timestamp") is not None]
    start_ms, end_ms = min(timestamps), max(timestamps)
    traces = parse_strategy_traces(args.logs_root, start_ms, end_ms)
    delivery_events = parse_core_delivery_events(args.logs_root, start_ms, end_ms)
    registry_rows = load_registry_rows(args.snapshot_root)
    funnel_rows = build_funnel_rows(traces, delivery_events, order_rows)

    md_rows = [row for row in funnel_rows if row["strategy_id"] == "md_amr"]
    mr_rows = [row for row in funnel_rows if row["strategy_id"] == "mean_reversion"]
    summary = {
        "start_utc": iso_utc(start_ms),
        "end_utc": iso_utc(end_ms),
        "trace_start_utc": iso_utc(min((row["timestamp_ms"] for row in traces), default=None)),
        "trace_end_utc": iso_utc(max((row["timestamp_ms"] for row in traces), default=None)),
        "trace_rows": len(traces),
        "delivery_events": len(delivery_events),
        "kelly_config_blocks": sum(row["kelly_config_blocks"] for row in funnel_rows),
        "md_amr_core_signals": sum(row["core_signals"] for row in md_rows),
        "md_amr_regime_blocked_signals": sum(row["regime_blocked_core_signals"] for row in md_rows),
        "mean_reversion_signals": sum(row["core_signals"] for row in mr_rows),
        "mean_reversion_kelly_blocks": sum(row["kelly_config_blocks"] for row in mr_rows),
        "mapping_shaped_regime_suppressions": sum(
            row["mapping_shaped_regime_suppressions"] for row in funnel_rows
        ),
    }

    args.report_root.mkdir(parents=True, exist_ok=True)
    write_csv(args.report_root / "strategy_registry_reachability.csv", registry_rows)
    write_csv(args.report_root / "strategy_delivery_funnel.csv", funnel_rows)
    (args.report_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.report_root / "STRATEGY_DELIVERY_FUNNEL_AUDIT.md").write_text(
        render_report(summary, registry_rows, funnel_rows), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
