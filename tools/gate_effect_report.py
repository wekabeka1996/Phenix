#!/usr/bin/env python3
"""
Gate Effect Report - LOW_VOL_COST_SUPPRESS-VERIFY-005

Analyzes decision logs to measure the effectiveness of the LOW_VOL_COST_SUPPRESS gate.

Usage:
    python tools/gate_effect_report.py [--log-dir LOGS_DIR] [--output-dir OUT_DIR]

Metrics:
    - Total BLOCK count by LOW_VOL_COST_SUPPRESS
    - Distribution of rv_bps/cost_bps in blocked trades
    - Top symbols and regimes blocked
    - Percentage of "rv_bps missing" (data gap indicator)
    - Before/after comparison (if historical data available)
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GateEvent:
    """Parsed gate event from logs."""
    ts_ms: int
    ts_human: str
    symbol: str
    regime: str
    result: str  # BLOCK, PASS, PASS:rv_bps_missing, etc.
    rv_bps: Optional[float] = None
    cost_bps: Optional[float] = None
    threshold: Optional[float] = None
    rv_bps_source: str = ""
    cost_source: str = ""
    sanity_fallback_used: bool = False
    raw_details: Dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass
class RejectEvent:
    """Parsed trade intent rejection event."""
    ts_ms: int
    ts_human: str
    symbol: str
    strategy_id: str
    side: str
    reason_code: str
    reason: str
    details: Dict[str, Any] = dataclass_field(default_factory=dict)


# =============================================================================
# LOG PARSING
# =============================================================================

def parse_dm_log_line(line: str) -> Optional[GateEvent]:
    """
    Parse decision_making log line for LOW_VOL_COST_SUPPRESS events.
    
    Expected format:
    [BTCUSDT] LOW_VOL_COST_SUPPRESS: BLOCK - rv_bps=3.00 < 1.5*4.00=6.00 (regime=TREND_UP, blocks_total=5)
    [BTCUSDT] LOW_VOL_COST_SUPPRESS: PASS - rv_bps=10.00 >= 6.00
    [BTCUSDT] LOW_VOL_COST_SUPPRESS: SKIP - rv_bps not available (missing_count=3)
    """
    if "LOW_VOL_COST_SUPPRESS" not in line:
        return None
    
    # Extract timestamp
    ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)', line)
    if ts_match:
        ts_str = ts_match.group(1)
        try:
            dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
            ts_ms = int(dt.timestamp() * 1000)
            ts_human = dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            ts_ms = 0
            ts_human = ""
    else:
        ts_ms = 0
        ts_human = ""
    
    # Extract symbol
    symbol_match = re.search(r'\[(\w+)\]', line)
    symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
    
    # Determine result
    if ": BLOCK -" in line:
        result = "BLOCK"
    elif ": PASS -" in line:
        result = "PASS"
    elif ": SKIP -" in line or "rv_bps not available" in line:
        result = "PASS:rv_bps_missing"
    else:
        result = "UNKNOWN"
    
    # Extract rv_bps
    rv_match = re.search(r'rv_bps=([0-9.]+)', line)
    rv_bps = float(rv_match.group(1)) if rv_match else None
    
    # Extract threshold (from "< X" or ">= X")
    threshold_match = re.search(r'[<>=]+\s*([0-9.]+)(?:\s|$|\))', line)
    threshold = float(threshold_match.group(1)) if threshold_match else None
    
    # Extract regime
    regime_match = re.search(r'regime=(\w+)', line)
    regime = regime_match.group(1) if regime_match else "UNKNOWN"
    
    # Extract missing_count for telemetry
    missing_match = re.search(r'missing_count=(\d+)', line)
    
    return GateEvent(
        ts_ms=ts_ms,
        ts_human=ts_human,
        symbol=symbol,
        regime=regime,
        result=result,
        rv_bps=rv_bps,
        threshold=threshold,
        raw_details={"missing_count": int(missing_match.group(1)) if missing_match else 0},
    )


def parse_reject_event(line: str) -> Optional[RejectEvent]:
    """
    Parse rejection event from event_chain.log or domain_decision_making.log.
    
    Looking for:
    EVT:TRADE_INTENT_REJECTED {..., "reason_code": "LOW_VOL_COST_SUPPRESS", ...}
    """
    if "TRADE_INTENT_REJECTED" not in line or "LOW_VOL_COST_SUPPRESS" not in line:
        return None
    
    # Try to extract JSON payload
    json_match = re.search(r'\{.*\}', line)
    if not json_match:
        return None
    
    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None
    
    # Extract timestamp
    ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)', line)
    if ts_match:
        ts_str = ts_match.group(1)
        try:
            dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
            ts_ms = int(dt.timestamp() * 1000)
            ts_human = dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            ts_ms = 0
            ts_human = ""
    else:
        ts_ms = data.get("ts_ms", 0)
        ts_human = ""
    
    return RejectEvent(
        ts_ms=ts_ms,
        ts_human=ts_human,
        symbol=data.get("symbol", "UNKNOWN"),
        strategy_id=data.get("strategy_id", "unknown"),
        side=data.get("side", "UNKNOWN"),
        reason_code=data.get("reason_code", ""),
        reason=data.get("reason", ""),
        details=data.get("details", {}),
    )


def load_gate_events(log_dir: Path) -> List[GateEvent]:
    """Load gate events from decision_making logs."""
    events = []
    
    log_files = [
        log_dir / 'domain_decision_making.log',
    ]
    # Add rotated logs
    for i in range(1, 10):
        log_files.append(log_dir / f'domain_decision_making.log.{i}')
    
    for log_file in log_files:
        if not log_file.exists():
            continue
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                evt = parse_dm_log_line(line)
                if evt:
                    events.append(evt)
    
    events.sort(key=lambda e: e.ts_ms)
    return events


def load_reject_events(log_dir: Path) -> List[RejectEvent]:
    """Load rejection events from logs."""
    events = []
    
    log_files = [
        log_dir / 'domain_decision_making.log',
        log_dir / 'event_chain.log',
    ]
    for i in range(1, 10):
        log_files.append(log_dir / f'domain_decision_making.log.{i}')
        log_files.append(log_dir / f'event_chain.log.{i}')
    
    for log_file in log_files:
        if not log_file.exists():
            continue
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                evt = parse_reject_event(line)
                if evt:
                    events.append(evt)
    
    events.sort(key=lambda e: e.ts_ms)
    return events


# =============================================================================
# ANALYSIS
# =============================================================================

def analyze_gate_effectiveness(events: List[GateEvent]) -> Dict[str, Any]:
    """Analyze gate effectiveness metrics."""
    
    if not events:
        return {"error": "No gate events found"}
    
    # Count by result
    by_result = defaultdict(int)
    for evt in events:
        by_result[evt.result] += 1
    
    # Count by symbol
    blocks_by_symbol = defaultdict(int)
    for evt in events:
        if evt.result == "BLOCK":
            blocks_by_symbol[evt.symbol] += 1
    
    # Count by regime
    blocks_by_regime = defaultdict(int)
    for evt in events:
        if evt.result == "BLOCK":
            blocks_by_regime[evt.regime] += 1
    
    # RV/Cost distribution for blocks
    rv_values = []
    cost_values = []
    threshold_values = []
    for evt in events:
        if evt.result == "BLOCK":
            if evt.rv_bps is not None:
                rv_values.append(evt.rv_bps)
            if evt.threshold is not None:
                threshold_values.append(evt.threshold)
    
    # Calculate percentages
    total = sum(by_result.values())
    pct_blocks = 100 * by_result.get("BLOCK", 0) / total if total > 0 else 0
    pct_passes = 100 * by_result.get("PASS", 0) / total if total > 0 else 0
    pct_rv_missing = 100 * by_result.get("PASS:rv_bps_missing", 0) / total if total > 0 else 0
    
    # Time range
    first_ts = events[0].ts_human if events else "N/A"
    last_ts = events[-1].ts_human if events else "N/A"
    
    return {
        "time_range": {
            "first": first_ts,
            "last": last_ts,
            "total_events": total,
        },
        "by_result": dict(by_result),
        "percentages": {
            "blocks_pct": round(pct_blocks, 2),
            "passes_pct": round(pct_passes, 2),
            "rv_missing_pct": round(pct_rv_missing, 2),
        },
        "blocks_by_symbol": dict(sorted(blocks_by_symbol.items(), key=lambda x: -x[1])),
        "blocks_by_regime": dict(blocks_by_regime),
        "rv_distribution": {
            "count": len(rv_values),
            "min": round(min(rv_values), 2) if rv_values else None,
            "max": round(max(rv_values), 2) if rv_values else None,
            "mean": round(sum(rv_values) / len(rv_values), 2) if rv_values else None,
        },
        "threshold_distribution": {
            "count": len(threshold_values),
            "min": round(min(threshold_values), 2) if threshold_values else None,
            "max": round(max(threshold_values), 2) if threshold_values else None,
            "mean": round(sum(threshold_values) / len(threshold_values), 2) if threshold_values else None,
        },
    }


def analyze_reject_events(events: List[RejectEvent]) -> Dict[str, Any]:
    """Analyze LOW_VOL_COST_SUPPRESS rejection events."""
    
    lvcs_events = [e for e in events if e.reason_code == "LOW_VOL_COST_SUPPRESS"]
    
    if not lvcs_events:
        return {"error": "No LOW_VOL_COST_SUPPRESS rejections found in events"}
    
    # By symbol
    by_symbol = defaultdict(int)
    for evt in lvcs_events:
        by_symbol[evt.symbol] += 1
    
    # By strategy
    by_strategy = defaultdict(int)
    for evt in lvcs_events:
        by_strategy[evt.strategy_id] += 1
    
    # By side
    by_side = defaultdict(int)
    for evt in lvcs_events:
        by_side[evt.side] += 1
    
    # Extract rv_bps and cost_bps from details
    rv_values = []
    cost_values = []
    for evt in lvcs_events:
        if "rv_bps" in evt.details:
            try:
                rv_values.append(float(evt.details["rv_bps"]))
            except (TypeError, ValueError):
                pass
        if "cost_bps" in evt.details:
            try:
                cost_values.append(float(evt.details["cost_bps"]))
            except (TypeError, ValueError):
                pass
    
    return {
        "total_rejections": len(lvcs_events),
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda x: -x[1])),
        "by_strategy": dict(by_strategy),
        "by_side": dict(by_side),
        "rv_distribution": {
            "count": len(rv_values),
            "min": round(min(rv_values), 2) if rv_values else None,
            "max": round(max(rv_values), 2) if rv_values else None,
            "mean": round(sum(rv_values) / len(rv_values), 2) if rv_values else None,
        },
        "cost_distribution": {
            "count": len(cost_values),
            "min": round(min(cost_values), 2) if cost_values else None,
            "max": round(max(cost_values), 2) if cost_values else None,
            "mean": round(sum(cost_values) / len(cost_values), 2) if cost_values else None,
        },
    }


def generate_hourly_breakdown(events: List[GateEvent]) -> List[Dict[str, Any]]:
    """Generate hourly breakdown of gate activity."""
    
    if not events:
        return []
    
    hourly = defaultdict(lambda: {"blocks": 0, "passes": 0, "rv_missing": 0})
    
    for evt in events:
        if evt.ts_ms <= 0:
            continue
        
        dt = datetime.fromtimestamp(evt.ts_ms / 1000)
        hour_key = dt.strftime('%Y-%m-%d %H:00')
        
        if evt.result == "BLOCK":
            hourly[hour_key]["blocks"] += 1
        elif evt.result == "PASS":
            hourly[hour_key]["passes"] += 1
        elif "rv_bps_missing" in evt.result:
            hourly[hour_key]["rv_missing"] += 1
    
    result = []
    for hour in sorted(hourly.keys()):
        data = hourly[hour]
        total = data["blocks"] + data["passes"] + data["rv_missing"]
        result.append({
            "hour": hour,
            "blocks": data["blocks"],
            "passes": data["passes"],
            "rv_missing": data["rv_missing"],
            "total": total,
            "block_rate_pct": round(100 * data["blocks"] / total, 1) if total > 0 else 0,
        })
    
    return result


# =============================================================================
# OUTPUT
# =============================================================================

def write_summary_report(output_dir: Path, gate_analysis: Dict, reject_analysis: Dict, hourly: List):
    """Write summary report files."""
    
    # YAML summary
    summary = {
        "report_generated": datetime.now().isoformat(),
        "gate_analysis": gate_analysis,
        "reject_analysis": reject_analysis,
    }
    
    yaml_file = output_dir / "gate_effect_summary.yaml"
    with open(yaml_file, 'w', encoding='utf-8') as f:
        yaml.dump(summary, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Written: {yaml_file}")
    
    # Hourly CSV
    if hourly:
        csv_file = output_dir / "gate_hourly_breakdown.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["hour", "blocks", "passes", "rv_missing", "total", "block_rate_pct"])
            writer.writeheader()
            writer.writerows(hourly)
        print(f"Written: {csv_file}")


def print_report(gate_analysis: Dict, reject_analysis: Dict, hourly: List):
    """Print report to console."""
    
    print("\n" + "=" * 60)
    print("LOW_VOL_COST_SUPPRESS GATE EFFECT REPORT")
    print("=" * 60)
    
    if "error" in gate_analysis:
        print(f"\n⚠️  {gate_analysis['error']}")
        print("\nThe gate may not have been triggered yet, or logs are not available.")
        print("Run Aurora in testnet mode to generate data, then re-run this report.")
        return
    
    tr = gate_analysis["time_range"]
    print(f"\n📅 Time Range: {tr['first']} → {tr['last']}")
    print(f"📊 Total Gate Events: {tr['total_events']}")
    
    print("\n--- Results Distribution ---")
    for result, count in gate_analysis["by_result"].items():
        pct = 100 * count / tr['total_events'] if tr['total_events'] > 0 else 0
        print(f"  {result}: {count} ({pct:.1f}%)")
    
    pcts = gate_analysis["percentages"]
    print(f"\n🚫 Block Rate: {pcts['blocks_pct']:.1f}%")
    print(f"⚠️  RV Missing Rate: {pcts['rv_missing_pct']:.1f}%")
    
    if gate_analysis["blocks_by_symbol"]:
        print("\n--- Blocks by Symbol ---")
        for sym, count in list(gate_analysis["blocks_by_symbol"].items())[:5]:
            print(f"  {sym}: {count}")
    
    if gate_analysis["blocks_by_regime"]:
        print("\n--- Blocks by Regime ---")
        for regime, count in gate_analysis["blocks_by_regime"].items():
            print(f"  {regime}: {count}")
    
    rv_dist = gate_analysis["rv_distribution"]
    if rv_dist["count"] > 0:
        print(f"\n--- RV in Blocked Trades ---")
        print(f"  Count: {rv_dist['count']}")
        print(f"  Min: {rv_dist['min']} bps")
        print(f"  Max: {rv_dist['max']} bps")
        print(f"  Mean: {rv_dist['mean']} bps")
    
    if hourly:
        print("\n--- Hourly Block Rate ---")
        for h in hourly[-5:]:  # Last 5 hours
            print(f"  {h['hour']}: {h['blocks']} blocks ({h['block_rate_pct']:.0f}%)")
    
    # Effectiveness assessment
    print("\n" + "=" * 60)
    print("EFFECTIVENESS ASSESSMENT")
    print("=" * 60)
    
    block_count = gate_analysis["by_result"].get("BLOCK", 0)
    rv_missing_pct = pcts['rv_missing_pct']
    
    if block_count > 0:
        print(f"\n✅ Gate is ACTIVE: {block_count} trades blocked")
        print("   → Prevented unprofitable entries in low-volatility conditions")
    else:
        print("\n⚠️  Gate has NOT blocked any trades yet")
        print("   This could mean:")
        print("   - Market volatility is high enough (good)")
        print("   - No TREND regime signals received")
        print("   - rv_bps data is missing (check rv_missing_pct)")
    
    if rv_missing_pct > 50:
        print(f"\n⚠️  HIGH RV_BPS MISSING RATE: {rv_missing_pct:.1f}%")
        print("   → Consider adding rv_bps to feature engineering")
        print("   → Or enable volatility_state proxy (with caution)")
    elif rv_missing_pct > 20:
        print(f"\n📊 Moderate RV missing rate: {rv_missing_pct:.1f}%")
        print("   → Gate is partially effective, but data gaps exist")
    else:
        print(f"\n✅ Low RV missing rate: {rv_missing_pct:.1f}%")
        print("   → Gate has sufficient data to make decisions")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Gate Effect Report for LOW_VOL_COST_SUPPRESS')
    parser.add_argument('--log-dir', type=str, default='logs', help='Logs directory')
    parser.add_argument('--output-dir', type=str, default='reports/gate_effect', help='Output directory')
    args = parser.parse_args()
    
    log_dir = Path(args.log_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"=== Gate Effect Report ===")
    print(f"Log directory: {log_dir}")
    print(f"Output directory: {output_dir}")
    
    # Load events
    print("\nLoading gate events...")
    gate_events = load_gate_events(log_dir)
    print(f"  Found {len(gate_events)} gate events")
    
    print("\nLoading rejection events...")
    reject_events = load_reject_events(log_dir)
    print(f"  Found {len(reject_events)} rejection events")
    
    # Analyze
    gate_analysis = analyze_gate_effectiveness(gate_events)
    reject_analysis = analyze_reject_events(reject_events)
    hourly = generate_hourly_breakdown(gate_events)
    
    # Output
    write_summary_report(output_dir, gate_analysis, reject_analysis, hourly)
    print_report(gate_analysis, reject_analysis, hourly)
    
    print(f"\n📁 Output files in: {output_dir}/")
    print("  - gate_effect_summary.yaml")
    print("  - gate_hourly_breakdown.csv")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
