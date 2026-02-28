#!/usr/bin/env python3
"""
OBS-01: Live Observability Summary
Analyzes JSONL logs to generate execution metrics summary (Maker Rejects, Fills, TTLs).

USAGE:
    python3 tools/live_observability_summary.py --since 24h
    python3 tools/live_observability_summary.py --inputs "logs/aurora_events.jsonl" "ops/wal/*.jsonl"
"""

import argparse
import glob
import json
import re
import sys
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any
from statistics import mean, median

# Parse timezone if needed (simple approximation)
LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

@dataclass
class LogEvent:
    timestamp: float
    event_type: str
    symbol: str
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    rid: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    filled_qty: Optional[float] = None
    tif: Optional[str] = None
    source_file: str = ""

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

class SummaryStats:
    def __init__(self):
        self.total_events = 0
        self.parsed_events = 0
        self.parse_errors = 0
        
        # Order Counts
        self.total_orders_created = 0
        self.fills = 0
        self.gtx_fills = 0
        self.cancels = 0
        self.rejects = 0
        self.maker_only_rejects = 0
        
        # Breakdowns
        self.cancel_reasons = Counter()
        self.reject_reasons = Counter()
        self.symbol_stats = defaultdict(lambda: Counter())
        
        # Latency tracking: client_order_id -> created_ts
        self.pending_creation = {} 
        self.time_to_fill_samples = []

def parse_time_arg(arg: str) -> float:
    """Parse --since 24h or ISO timestamp."""
    now = time.time()
    if arg.endswith("h"):
        hours = float(arg[:-1])
        return now - (hours * 3600)
    elif arg.endswith("m"):
        minutes = float(arg[:-1])
        return now - (minutes * 60)
    elif arg.endswith("d"):
        days = float(arg[:-1])
        return now - (days * 86400)
    else:
        try:
            dt = datetime.fromisoformat(arg)
            return dt.timestamp()
        except ValueError:
            print(f"Error parsing time: {arg}")
            sys.exit(1)

def normalize_event(data: Dict[str, Any], source: str) -> Optional[LogEvent]:
    """Convert variable JSON schemas to LogEvent."""
    try:
        # 1. Timestamp
        ts = data.get("timestamp") or data.get("ts")
        if not ts:
            ts_ms = data.get("ts_ms") or data.get("T")
            if ts_ms:
                ts = ts_ms / 1000.0
        if not ts:
            return None # Skip if no timestamp

        # 2. Identify Event Type
        evt_type = "UNKNOWN"
        status = None
        reason = None
        sym = data.get("symbol") or "UNKNOWN"
        
        # Schema A: Audit / Aurora Events
        if "event" in data:
            evt_type = data["event"]
            status = data.get("status")
            reason = data.get("why") or data.get("reason")
        
        # Schema B: WAL / Message Payload
        elif "verb" in data:
            evt_type = data["verb"]
            pld = data.get("pld", {})
            if isinstance(pld, dict):
                sym = pld.get("symbol") or sym
                reason = pld.get("reason") or data.get("why")
                status = pld.get("status")
        
        # Refine Status/Type
        if status == "FILLED":
            evt_type = "ORDER_FILLED"
        elif status == "CANCELED":
            evt_type = "ORDER_CANCELED"
        elif status == "EXPIRED":
            # Check for maker reject here too
            evt_type = "ORDER_EXPIRED"
        
        if reason == "MAKER_ONLY_REJECT" or (data.get("why") == "MAKER_ONLY_REJECT"):
            evt_type = "MAKER_ONLY_REJECT"
            reason = "MAKER_ONLY_REJECT"

        if evt_type == "EVT:ORDER_REJECTED":
             evt_type = "ORDER_REJECTED"

        # IDs and Qty
        pld = data.get("pld", data)
        cid = pld.get("clientOrderId") or pld.get("client_order_id")
        oid = pld.get("orderId") or pld.get("order_id")
        rid = pld.get("rid")
        qty = float(pld.get("qty") or pld.get("quantity") or 0)
        filled = float(pld.get("filled_qty") or 0)
        tif = pld.get("time_in_force") or pld.get("tif")

        return LogEvent(
            timestamp=float(ts),
            event_type=evt_type,
            symbol=sym,
            order_id=oid,
            client_order_id=cid,
            rid=rid,
            status=status,
            reason=reason,
            qty=qty,
            filled_qty=filled,
            tif=tif,
            source_file=source
        )
    except Exception:
        return None

def analyze(files: List[str], start_ts: float, end_ts: float) -> SummaryStats:
    stats = SummaryStats()
    
    # Process files
    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            continue
            
        with open(path, 'r', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                stats.total_events += 1
                try:
                    data = json.loads(line)
                    evt = normalize_event(data, path.name)
                    
                    if not evt: 
                        stats.parse_errors += 1
                        continue
                        
                    if not (start_ts <= evt.timestamp <= end_ts):
                        continue

                    stats.parsed_events += 1
                    
                    # --- METRICS LOGIC ---
                    
                    # 1. Maker Rejects
                    if evt.event_type == "MAKER_ONLY_REJECT" or evt.reason == "MAKER_ONLY_REJECT":
                        stats.maker_only_rejects += 1
                        stats.rejects += 1
                        stats.reject_reasons["MAKER_ONLY_REJECT"] += 1
                        stats.symbol_stats[evt.symbol]["maker_rejects"] += 1
                        continue

                    # 2. Cancels
                    if evt.event_type in ("ORDER_CANCELED", "EVT:ORDER_CANCELED") or evt.status == "CANCELED":
                        stats.cancels += 1
                        r = evt.reason or "UNKNOWN"
                        stats.cancel_reasons[r] += 1
                        stats.symbol_stats[evt.symbol]["cancels"] += 1
                    
                    # 3. Fills
                    if evt.event_type in ("ORDER_FILLED", "EVT:TRADE_EXECUTED", "TRADE_EXECUTED") or evt.status == "FILLED":
                        stats.fills += 1
                        stats.symbol_stats[evt.symbol]["fills"] += 1
                        if evt.tif == "GTX":
                            stats.gtx_fills += 1
                        
                        # Latency match
                        if evt.client_order_id and evt.client_order_id in stats.pending_creation:
                            start_time = stats.pending_creation.pop(evt.client_order_id)
                            duration = evt.timestamp - start_time
                            if 0 < duration < 600: # sanity filter < 10min
                                stats.time_to_fill_samples.append(duration)
                    
                    # 4. Creations (for latency tracking basics)
                    if evt.status == "NEW" or evt.event_type in ("ORDER_PLACED", "EVT:ORDER_PLACED"):
                        stats.total_orders_created += 1
                        if evt.client_order_id:
                            stats.pending_creation[evt.client_order_id] = evt.timestamp

                except json.JSONDecodeError:
                    stats.parse_errors += 1
    
    return stats

def print_report(stats: SummaryStats, start_ts: float, end_ts: float):
    duration_h = (end_ts - start_ts) / 3600.0
    
    print(f"\n{'='*60}")
    print(f"OBS-01: Live Observability Summary")
    print(f"Window: {duration_h:.1f}h | Events: {stats.parsed_events} parsed ({stats.parse_errors} err)")
    print(f"{'='*60}")
    
    # 1. Execution Health
    print(f"\n[EXECUTION HEALTH]")
    print(f"  Orders Created:       {stats.total_orders_created}")
    print(f"  Fills:                {stats.fills} (GTX: {stats.gtx_fills})")
    print(f"  Cancels:              {stats.cancels}")
    print(f"  Rejects:              {stats.rejects}")
    
    mr_rate = 0
    if stats.total_orders_created > 0:
        mr_rate = (stats.maker_only_rejects / stats.total_orders_created) * 100
    print(f"  Maker-Only Rejects:   {stats.maker_only_rejects} ({mr_rate:.2f}%)")

    # 2. Latency
    if stats.time_to_fill_samples:
        avg_ttf = mean(stats.time_to_fill_samples)
        med_ttf = median(stats.time_to_fill_samples)
        print(f"\n[TIME-TO-FILL] (samples={len(stats.time_to_fill_samples)})")
        print(f"  Avg: {avg_ttf:.3f}s")
        print(f"  Med: {med_ttf:.3f}s")
    else:
        print(f"\n[TIME-TO-FILL] No samples (requires PLACED -> FILLED pairs)")

    # 3. Reasons
    print(f"\n[CANCEL REASONS]")
    for r, c in stats.cancel_reasons.most_common(5):
        print(f"  {r:<25} : {c}")
    
    if stats.reject_reasons:
        print(f"\n[REJECT REASONS]")
        for r, c in stats.reject_reasons.most_common(5):
            print(f"  {r:<25} : {c}")

    # 4. Symbol breakdown
    print(f"\n[SYMBOL STATS (Top 5 active)]")
    # Sort by activity (fills + cancels + rejects)
    active_syms = sorted(
        stats.symbol_stats.items(), 
        key=lambda x: sum(x[1].values()), 
        reverse=True
    )[:5]
    
    print(f"  {'SYMBOL':<10} {'FILLS':<8} {'CANCELS':<8} {'MR_REJ':<8}")
    for sym, data in active_syms:
        print(f"  {sym:<10} {data['fills']:<8} {data['cancels']:<8} {data['maker_rejects']:<8}")
    
    print(f"{'='*60}\n")

    # Save JSON
    out_file = "reports/live_observability_summary.json"
    data = {
        "meta": {
             "start_ts": start_ts,
             "end_ts": end_ts,
             "generated_at": time.time()
        },
        "stats": {
            "fills": stats.fills,
            "cancels": stats.cancels,
            "maker_only_rejects": stats.maker_only_rejects,
            "cancel_reasons": dict(stats.cancel_reasons),
        }
    }
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"JSON report saved to: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Live Observability Summary")
    parser.add_argument("--since", default="24h", help="Time window (e.g. 24h, 30m)")
    parser.add_argument("--inputs", nargs="+", default=None, help="Input file patterns")
    args = parser.parse_args()
    
    # Resolve files
    if args.inputs:
        files = []
        for p in args.inputs:
            files.extend(glob.glob(p, recursive=True))
    else:
        # Defaults
        files = glob.glob("logs/**/*.jsonl", recursive=True) + \
                glob.glob("ops/wal/**/*.jsonl", recursive=True) + \
                glob.glob("reports/**/*.jsonl", recursive=True)
    
    if not files:
        print("No log files found.")
        return

    end_ts = time.time()
    start_ts = parse_time_arg(args.since)
    
    print(f"Analyzing {len(files)} files since {datetime.fromtimestamp(start_ts)}...")
    
    stats = analyze(files, start_ts, end_ts)
    print_report(stats, start_ts, end_ts)

if __name__ == "__main__":
    main()
