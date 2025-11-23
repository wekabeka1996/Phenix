"""
ExecPos TCA CLI
===============

Command-line interface for running Transaction Cost Analysis on ExecPos WAL logs.

Usage:
    python tools/tca_execpos_cli.py --logs-root <path> --from-ts <iso_ts> --to-ts <iso_ts> [options]

Options:
    --symbol <symbol>       Filter by symbol
    --output-json <path>    Save full report to JSON file
    --output-summary <path> Save human-readable summary to text file
"""
import argparse
import json
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from apps.reference.tools.tca_execpos import compute_tca_for_period

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tca_cli")

def parse_iso_ts(ts_str: str) -> float:
    """Parse ISO timestamp to unix seconds."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        logger.error(f"Invalid timestamp format: {ts_str}. Use ISO 8601 (e.g., 2023-01-01T00:00:00)")
        sys.exit(1)

def format_summary_table(summaries: list) -> str:
    """Format summaries as a text table."""
    if not summaries:
        return "No data found."
        
    lines = []
    lines.append(f"{'SCOPE':<15} {'VOL($)':<12} {'FEES($)':<10} {'COUNT':<6} {'AVG SLIP(bps)':<15} {'P95 SLIP(bps)':<15} {'AVG TIME(ms)':<15}")
    lines.append("-" * 100)
    
    for s in summaries:
        lines.append(
            f"{s['scope']:<15} "
            f"{s['total_volume']:<12.2f} "
            f"{s['total_fees']:<10.4f} "
            f"{s['trade_count']:<6} "
            f"{s['avg_slippage_bps']:<15.2f} "
            f"{s['p95_slippage_bps']:<15.2f} "
            f"{s['avg_time_to_fill_ms']:<15.2f}"
        )
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="ExecPos TCA CLI")
    parser.add_argument("--logs-root", required=True, help="Path to logs directory containing WAL files")
    parser.add_argument("--from-ts", required=True, help="Start timestamp (ISO 8601)")
    parser.add_argument("--to-ts", required=True, help="End timestamp (ISO 8601)")
    parser.add_argument("--symbol", help="Filter by symbol")
    parser.add_argument("--output-json", help="Path to save JSON report")
    parser.add_argument("--output-summary", help="Path to save summary text")
    
    args = parser.parse_args()
    
    from_ts = parse_iso_ts(args.from_ts)
    to_ts = parse_iso_ts(args.to_ts)
    
    logger.info(f"Running TCA from {args.from_ts} to {args.to_ts}...")
    
    try:
        result = compute_tca_for_period(
            logs_root=args.logs_root,
            from_ts=from_ts,
            to_ts=to_ts,
            symbol=args.symbol
        )
        
        summaries = result["summaries"]
        records = result["records"]
        
        logger.info(f"Processed {len(records)} trades.")
        
        # Print summary to stdout
        summary_text = format_summary_table(summaries)
        print("\n" + summary_text + "\n")
        
        # Save JSON
        if args.output_json:
            with open(args.output_json, "w") as f:
                json.dump(result, f, indent=2)
            logger.info(f"Saved JSON report to {args.output_json}")
            
        # Save Summary Text
        if args.output_summary:
            with open(args.output_summary, "w") as f:
                f.write(summary_text)
            logger.info(f"Saved summary text to {args.output_summary}")
            
    except Exception as e:
        logger.error(f"TCA failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
