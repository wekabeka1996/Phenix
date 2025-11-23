#!/usr/bin/env python
"""
Order Trace CLI
===============

Command-line tool for building and rendering trade narratives from logs.

Usage:
    python -m tools.order_trace_cli --trade-id <id> --logs-root ./logs
    python -m tools.order_trace_cli --position-id <id> --from "2025-11-20T00:00:00Z" --to "2025-11-21T00:00:00Z"
"""
from apps.reference.tools.execpos_metrics_aggregator import summarize_trace_metrics
from apps.reference.tools.order_trace import (
    build_trace_for_trade,
    build_trace_for_position,
    TraceSources,
)
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def render_narrative(trace) -> str:
    """Render TradeTrace as human-readable narrative."""
    if not trace:
        return "No trace data found."

    lines = []
    lines.append("=" * 80)
    lines.append(f"TRADE NARRATIVE: {trace.trace_id}")
    lines.append("=" * 80)
    lines.append(f"Symbol: {trace.symbol}")
    lines.append(f"Direction: {trace.direction}")

    if trace.entry_info:
        entry = trace.entry_info
        ts_str = datetime.fromtimestamp(
            entry["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"Entry: {entry['size']} @ {entry['price']} at {ts_str}")
        lines.append(f"  Reason: {entry['reason']}")

    if trace.exit_info:
        exit = trace.exit_info
        ts_str = datetime.fromtimestamp(
            exit["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"Exit: {exit['size']} @ {exit['price']} at {ts_str}")
        lines.append(f"  Reason: {exit['reason']}")
        lines.append(f"  PnL: {exit['pnl']}")

    if trace.gaps:
        lines.append(f"\n⚠️  Missing Data: {', '.join(trace.gaps)}")

    lines.append("\n" + "-" * 80)
    lines.append("EVENT TIMELINE")
    lines.append("-" * 80)

    for i, event in enumerate(trace.events, 1):
        ts_str = datetime.fromtimestamp(
            event.ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        lines.append(f"{i}. [{ts_str}] {event.source}::{event.event_type}")
        if event.why:
            lines.append(f"   Why: {event.why}")
        # Show key payload fields
        if event.event_type == "EXEC_TRADE":
            lines.append(
                f"   Trade: {event.payload.get('side')} {event.payload.get('qty')} @ {event.payload.get('price')}")
        elif event.event_type == "DECISION_INTENT":
            lines.append(
                f"   Signal: {event.payload.get('signal_score')} (threshold: {event.payload.get('signal_threshold')})")

    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Build trade narratives from logs")
    parser.add_argument("--trade-id", help="Trade ID to trace")
    parser.add_argument("--position-id", help="Position ID to trace")
    parser.add_argument(
        "--order-id", help="Order ID to trace (uses WAL correlation)")
    parser.add_argument("--logs-root", default="./logs",
                        help="Root directory for log files")
    parser.add_argument(
        "--output", choices=["text", "json", "metrics"], default="text", help="Output format")
    parser.add_argument("--metrics-format", choices=["dict", "prometheus"],
                        default="dict", help="Metrics output format (when --output=metrics)")
    parser.add_argument("--from", dest="from_time",
                        help="Start time (ISO 8601)")
    parser.add_argument("--to", dest="to_time", help="End time (ISO 8601)")

    args = parser.parse_args()

    # Setup sources
    logs_root = Path(args.logs_root)
    sources = TraceSources(
        decision_log_path=str(logs_root / "domain_decision_making.log"),
        runtime_log_path=str(logs_root / "execpos_v2_runtime.jsonl"),
        wal_dir=str(logs_root),
        exposure_log_path=None,  # Currently inferred from WAL
    )

    # Build trace
    trace = None
    if args.trade_id:
        trace = build_trace_for_trade(args.trade_id, sources)
    elif args.position_id:
        trace = build_trace_for_position(args.position_id, sources)
    elif args.order_id:
        # For order_id, use WAL correlation
        from apps.reference.tools.order_trace.parsers import parse_wal_records
        wal_events = parse_wal_records(str(logs_root), order_id=args.order_id)
        if wal_events:
            # Extract trade_id from first EXEC_TRADE event
            for event in wal_events:
                if event.event_type == "EXEC_TRADE" and event.payload.get("trade_id"):
                    trace = build_trace_for_trade(
                        event.payload["trade_id"], sources)
                    break
    else:
        print(
            "Error: Must specify --trade-id, --position-id, or --order-id", file=sys.stderr)
        sys.exit(1)

    # Output
    if not trace:
        print("No trace found for given ID", file=sys.stderr)
        sys.exit(1)

    if args.output == "metrics":
        # Export canonical metrics
        agg = summarize_trace_metrics(trace)
        if args.metrics_format == "prometheus":
            print(agg.to_prometheus_text())
        else:
            print(json.dumps(agg.to_dict(), indent=2))
    elif args.output == "json":
        print(json.dumps(trace.to_dict(), indent=2))
    else:
        print(render_narrative(trace))

    sys.exit(0)


if __name__ == "__main__":
    main()
