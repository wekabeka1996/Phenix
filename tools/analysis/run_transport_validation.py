import os
import json
import csv
import glob
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

def parse_log_time_to_ms(time_str: str) -> int:
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
        # Shift to UTC (subtract 3 hours)
        dt_utc = dt - timedelta(hours=3)
        # Convert to epoch ms
        # Epoch of 2026-06-19 00:00:00 UTC is 1781827200000 ms
        base_ts = 1781827200 * 1000
        midnight_utc = datetime(2026, 6, 19, 0, 0, 0, tzinfo=timezone.utc)
        diff = dt_utc.replace(tzinfo=timezone.utc) - midnight_utc
        return base_ts + int(diff.total_seconds() * 1000)
    except Exception as e:
        return 0

def main():
    repo_root = Path("C:/Users/wekab/Music/Phenix")
    trade_log_path = repo_root / "logs/trade_lifecycle.jsonl"
    
    # 1. Target window boundaries
    entry_ts_ms = 1781850380946
    close_ts_ms = 1781854692293
    
    # Parse feature engineering calculations for BNBUSDT around this window
    print("Parsing feature calculations from rotated logs...")
    feature_calcs = []
    
    feature_log_files = glob.glob(str(repo_root / "logs/domain_feature_engineering.log*"))
    for fpath in feature_log_files:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "Calculated features for BNBUSDT" in line:
                    parts = line.split(" - ")
                    if len(parts) >= 4:
                        time_str = parts[0]
                        ts_ms = parse_log_time_to_ms(time_str)
                        if ts_ms > 0:
                            feature_calcs.append(ts_ms)
                            
    feature_calcs.sort()
    print(f"Parsed {len(feature_calcs)} BNBUSDT calculations from logs.")
    
    # Now scan trade_lifecycle.jsonl for sidecar events during the active position window
    sidecar_events = []
    
    with trade_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts = int(obj.get("ts_ms") or 0)
                if entry_ts_ms <= ts <= close_ts_ms and obj.get("symbol") == "BNBUSDT":
                    event_type = obj.get("event_type", "")
                    if event_type.startswith("POSITION_POLICY_SIDECAR"):
                        sidecar_events.append(obj)
            except Exception:
                continue
                
    print(f"Found {len(sidecar_events)} Sidecar events during active position window.")
    
    # Segment by event type
    event_census = Counter(obj.get("event_type") for obj in sidecar_events)
    suppressions = [obj for obj in sidecar_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_SUPPRESSED"]
    evaluations = [obj for obj in sidecar_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_EVALUATED"]
    scores = [obj for obj in sidecar_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_SCORES"]
    recommendations = [obj for obj in sidecar_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED"]
    close_requests = [obj for obj in sidecar_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"]
    
    suppression_reasons = Counter(obj.get("suppression_reason") for obj in suppressions)
    
    # Feature age analysis
    ages = []
    stale_count = 0
    missing_count = 0
    
    for obj in sidecar_events:
        fresh_snap = obj.get("freshness_snapshot") or {}
        age_ms = fresh_snap.get("features_age_ms")
        if age_ms is not None:
            ages.append(age_ms)
            
    ages.sort()
    
    # Output the report metrics
    print("\n--- RESULTS ---")
    print(f"Total Sidecar Events: {len(sidecar_events)}")
    for k, v in sorted(event_census.items()):
        print(f"  {k}: {v}")
        
    print("\nSuppression Reasons:")
    for k, v in sorted(suppression_reasons.items()):
        print(f"  {k}: {v}")
        
    if ages:
        median_age = ages[len(ages) // 2]
        max_age = max(ages)
        min_age = min(ages)
        print(f"\nFeature Age Distribution (ms):")
        print(f"  Min: {min_age}")
        print(f"  Median: {median_age}")
        print(f"  Max: {max_age}")
    else:
        print("\nNo features age data found in events.")
        
    # Analyze soft close pressure during evaluations
    pressures = []
    for ev in evaluations:
        score_snap = ev.get("score_snapshot") or {}
        p = score_snap.get("soft_close_pressure")
        if p is not None:
            pressures.append(float(p))
    if pressures:
        print(f"\nSoft Close Pressure:")
        print(f"  Max: {max(pressures)}")
    else:
        print("\nNo soft close pressure data found in evaluations.")

if __name__ == "__main__":
    main()
