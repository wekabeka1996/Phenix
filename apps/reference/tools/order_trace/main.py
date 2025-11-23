"""
OrderTrace CLI
==============

Command-line interface for trade timeline reconstruction.

Usage:
    order_trace --rid <RID>
    order_trace --symbol BTCUSDT --from-ts 1700000000 --to-ts 1700010000
    order_trace --position-id pos_456
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import TraceSources, TradeTrace
from .v2_trace_builder import build_timeline_for_rid, build_timeline_for_position
from .engine import build_trace_for_trade, build_trace_for_position as build_trace_for_position_legacy
from apps.reference.tools.execpos_metrics_aggregator import summarize_trace_metrics

logger = logging.getLogger(__name__)


def _format_timestamp(ts: float) -> str:
    """Format Unix timestamp to human-readable string."""
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception:
        return f"{ts:.3f}"


def render_timeline(trace: TradeTrace) -> None:
    """
    Render trade timeline in human-readable format.

    Args:
        trace: TradeTrace object
    """
    print(f"\n{'='*80}")
    print(
        f"RID: {trace.trace_id} | Symbol: {trace.symbol} | Direction: {trace.direction}")
    print(f"{'='*80}\n")

    if trace.entry_info:
        print(
            f"📈 ENTRY: {trace.entry_info['size']} @ {trace.entry_info['price']} (ts: {_format_timestamp(trace.entry_info['ts'])})")

    if trace.exit_info:
        print(
            f"📉 EXIT:  {trace.exit_info['size']} @ {trace.exit_info['price']} | PnL: {trace.exit_info['pnl']} (ts: {_format_timestamp(trace.exit_info['ts'])})")

    if trace.entry_info or trace.exit_info:
        print(f"{'-'*80}\n")

    print("EVENT TIMELINE:\n")

    for event in trace.events:
        ts_str = _format_timestamp(event.ts)
        source_tag = f"[{event.source:8s}]"
        event_type_tag = f"{event.event_type:30s}"

        # Color-code inferred events
        if event.source == "INFERRED":
            print(f"🔍 {ts_str} | {source_tag} {event_type_tag}")
        else:
            print(f"   {ts_str} | {source_tag} {event_type_tag}")

        # Print why if available
        if event.why:
            print(f"      → {event.why}")

        # Print key payload fields for important events
        if event.event_type == "EXEC_TRADE":
            payload = event.payload
            print(
                f"      qty: {payload.get('qty', 'N/A')}, price: {payload.get('price', 'N/A')}, role: {payload.get('role', 'N/A')}")

        elif event.event_type == "EXEC_ORDER":
            payload = event.payload
            order_id = payload.get(
                "order_id", payload.get("client_order_id", "N/A"))
            order_type = payload.get("type", "N/A")
            status = payload.get("status", "N/A")
            print(
                f"      orderId: {order_id}, type: {order_type}, status: {status}")

        elif event.event_type == "BRACKET_ORDERS_PLACED":
            payload = event.payload
            if payload.get("sl_orders"):
                sl_list = ', '.join(
                    [f"{o['orderId']} @ {o['price']}" for o in payload['sl_orders']])
                print(f"      SL orders: {sl_list}")
            if payload.get("tp_orders"):
                tp_list = ', '.join(
                    [f"{o['orderId']} @ {o['price']}" for o in payload['tp_orders']])
                print(f"      TP orders: {tp_list}")

        elif event.event_type == "TRAILING_SL_UPDATED":
            payload = event.payload
            print(
                f"      Old SL: {payload.get('old_stop_price')} → New SL: {payload.get('new_stop_price')} (Δ {payload.get('delta', 0):+.2f})")

        elif event.event_type == "CLOSE_DECISION_INFERRED":
            payload = event.payload
            print(
                f"      reason: {payload.get('reason')}, pnl: {payload.get('realized_pnl')}")

        print()  # Blank line between events

    if trace.gaps:
        print(f"\n⚠️  GAPS DETECTED: {', '.join(trace.gaps)}\n")

    print(f"{'='*80}")
    print(f"Total events: {len(trace.events)}")
    print(f"{'='*80}\n")


def render_json(trace: TradeTrace) -> None:
    """
    Render trade timeline as JSON.

    Args:
        trace: TradeTrace object
    """
    print(json.dumps(trace.to_dict(), indent=2, default=str))


def render_table(trace: TradeTrace) -> None:
    """
    Render trade timeline in tabular format.

    Args:
        trace: TradeTrace object
    """
    print(
        f"\nRID: {trace.trace_id} | Symbol: {trace.symbol} | Direction: {trace.direction}\n")

    # Table header
    header = f"{'Timestamp':20s} | {'Source':8s} | {'Event Type':30s} | {'Why':40s}"
    print(header)
    print("-" * len(header))

    for event in trace.events:
        ts_str = _format_timestamp(event.ts)
        why_short = (event.why[:37] +
                     "...") if len(event.why) > 40 else event.why

        print(
            f"{ts_str:20s} | {event.source:8s} | {event.event_type:30s} | {why_short:40s}")

    print(f"\nTotal events: {len(trace.events)}\n")


def discover_log_files(base_dir: Path) -> TraceSources:
    """
    Auto-discover log files in base directory.

    Args:
        base_dir: Base directory for log files (default: ./logs)

    Returns:
        TraceSources with discovered paths
    """
    sources = TraceSources()

    # Search for decision log
    decision_log_candidates = list(base_dir.glob("**/decision*.log"))
    if decision_log_candidates:
        sources.decision_log_path = str(decision_log_candidates[0])
        logger.info(f"Discovered decision log: {sources.decision_log_path}")

    # Search for runtime log
    runtime_log_candidates = list(base_dir.glob("**/execpos*.jsonl"))
    if runtime_log_candidates:
        sources.runtime_log_path = str(runtime_log_candidates[0])
        logger.info(f"Discovered runtime log: {sources.runtime_log_path}")

    # Search for WAL directory
    wal_dir_candidates = list(base_dir.glob("**/wal"))
    if wal_dir_candidates:
        sources.wal_dir = str(wal_dir_candidates[0])
        logger.info(f"Discovered WAL dir: {sources.wal_dir}")

    # Search for exposure log
    exposure_log_candidates = list(base_dir.glob("**/exposure*.jsonl"))
    if exposure_log_candidates:
        sources.exposure_log_path = str(exposure_log_candidates[0])
        logger.info(f"Discovered exposure log: {sources.exposure_log_path}")

    return sources


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="OrderTrace V2 - Trade timeline reconstruction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # By RID (primary)
  order_trace --rid abc123

  # By symbol + time range (fallback)
  order_trace --symbol BTCUSDT --from-ts 1700000000 --to-ts 1700010000

  # By position_id
  order_trace --position-id pos_456

  # By trade_id (legacy)
  order_trace --trade-id t_789

  # Output formats
  order_trace --rid abc123 --format timeline   # Human-readable (default)
  order_trace --rid abc123 --format json       # Machine-readable JSON
  order_trace --rid abc123 --format table      # Tabular format
        """
    )

    # Correlation keys
    parser.add_argument("--rid", type=str,
                        help="Request ID (primary correlation key)")
    parser.add_argument("--symbol", type=str,
                        help="Trading symbol (fallback correlation)")
    parser.add_argument("--from-ts", type=float,
                        help="Start of time window (Unix seconds)")
    parser.add_argument("--to-ts", type=float,
                        help="End of time window (Unix seconds)")
    parser.add_argument("--position-id", type=str,
                        help="Position ID (alternative correlation)")
    parser.add_argument("--trade-id", type=str,
                        help="Trade ID (legacy correlation)")

    # Output options
    parser.add_argument(
        "--format",
        type=str,
        choices=["timeline", "json", "table"],
        default="timeline",
        help="Output format (default: timeline)"
    )
    parser.add_argument(
        "--sources-dir",
        type=str,
        default="./logs",
        help="Base directory for log files (default: ./logs)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--metrics-summary",
        action="store_true",
        help="Emit canonical execpos_* metrics summary for the built trace and exit"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    # Validate arguments
    if not any([args.rid, args.symbol, args.position_id, args.trade_id]):
        print("ERROR: At least one correlation key required (--rid, --symbol, --position-id, or --trade-id)", file=sys.stderr)
        parser.print_help()
        sys.exit(2)

    # Discover log files
    base_dir = Path(args.sources_dir)
    if not base_dir.exists():
        print(
            f"ERROR: Sources directory not found: {args.sources_dir}", file=sys.stderr)
        sys.exit(2)

    sources = discover_log_files(base_dir)

    # Build trace
    trace: Optional[TradeTrace] = None

    if args.rid:
        logger.info(f"Building trace for RID: {args.rid}")
        trace = build_timeline_for_rid(args.rid, sources)

    elif args.trade_id:
        logger.info(f"Building trace for trade_id: {args.trade_id} (legacy)")
        trace = build_trace_for_trade(args.trade_id, sources)

    elif args.position_id:
        logger.info(f"Building trace for position_id: {args.position_id}")
        # Try V2 builder first (with symbol if provided)
        if args.symbol:
            trace = build_timeline_for_position(
                symbol=args.symbol,
                position_id=args.position_id,
                from_ts=args.from_ts,
                to_ts=args.to_ts,
                sources=sources
            )
        else:
            # Fallback to legacy builder
            trace = build_trace_for_position_legacy(args.position_id, sources)

    elif args.symbol:
        logger.info(
            f"Building trace for symbol: {args.symbol}, window: [{args.from_ts}, {args.to_ts}]")
        trace = build_timeline_for_position(
            symbol=args.symbol,
            position_id=None,
            from_ts=args.from_ts,
            to_ts=args.to_ts,
            sources=sources
        )

    if not trace:
        print("ERROR: No events found for given criteria", file=sys.stderr)
        sys.exit(1)

    if args.metrics_summary:
        agg = summarize_trace_metrics(trace)
        summary = agg.to_dict()
        print(json.dumps(summary, indent=2))
        print("\n# Prometheus\n" + agg.to_prometheus_text())
        sys.exit(0)

    # Render output
    if args.format == "timeline":
        render_timeline(trace)
    elif args.format == "json":
        render_json(trace)
    elif args.format == "table":
        render_table(trace)

    sys.exit(0)


if __name__ == "__main__":
    main()
