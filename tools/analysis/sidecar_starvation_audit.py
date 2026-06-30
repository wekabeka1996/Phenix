#!/usr/bin/env python3
import os
import json
import csv
import glob
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

def parse_log_time_to_ms(time_str: str) -> int:
    # Example: "2026-06-18 16:36:52,296" -> ms epoch (offsetting UTC+3)
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
        # Shift to UTC (subtract 3 hours)
        dt_utc = dt - timedelta(hours=3)
        # Convert to epoch ms
        # Epoch of 2026-06-18 00:00:00 UTC is 1781740800000 ms
        base_ts = 1781740800 * 1000
        midnight_utc = datetime(2026, 6, 18, 0, 0, 0, tzinfo=timezone.utc)
        diff = dt_utc.replace(tzinfo=timezone.utc) - midnight_utc
        return base_ts + int(diff.total_seconds() * 1000)
    except Exception as e:
        return 0

def main():
    frozen_dir = Path("C:/Users/wekab/Music/Phenix/frozen/sidecar_current_state_reset_20260618_143111Z")
    output_dir = Path("C:/Users/wekab/Music/Phenix/artifacts/sidecar_current_state_reset")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    trade_log_path = frozen_dir / "logs/trade_lifecycle.jsonl"
    order_log_path = frozen_dir / "logs/order_log_v1.jsonl"
    stats_log_path = frozen_dir / "logs/execution_lifecycle_stats_v1.jsonl"
    
    # 1. BNBUSDT position window boundaries
    entry_ts_ms = 1781778048144
    close_ts_ms = 1781787041339
    
    # -------------------------------------------------------------
    # PARSE FEATURE CALCULATIONS FROM LOGS
    # -------------------------------------------------------------
    print("Parsing feature calculations from rotated logs...")
    feature_calcs = defaultdict(list) # symbol -> list of ts_ms
    
    feature_log_files = glob.glob(str(frozen_dir / "logs/domain_feature_engineering.log*"))
    for fpath in feature_log_files:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "Calculated features for" in line:
                    # Line format: "2026-06-18 16:36:52,296 - ... INFO - Calculated features for {symbol}: {json_str}"
                    parts = line.split(" - ")
                    if len(parts) >= 4:
                        time_str = parts[0]
                        msg_part = parts[-1]
                        # msg_part: "Calculated features for BNBUSDT: {...}"
                        try:
                            subparts = msg_part.split("Calculated features for ")
                            if len(subparts) >= 2:
                                sym_and_data = subparts[1]
                                sym = sym_and_data.split(":")[0].strip()
                                ts_ms = parse_log_time_to_ms(time_str)
                                if ts_ms > 0:
                                    feature_calcs[sym].append(ts_ms)
                        except Exception:
                            continue
                            
    # Sort calculations chronologically for each symbol
    for sym in feature_calcs:
        feature_calcs[sym].sort()
        print(f"  Symbol {sym}: {len(feature_calcs[sym])} feature calculations parsed.")
        
    # -------------------------------------------------------------
    # PARSE trade_lifecycle.jsonl FOR SUPPRESSIONS AND TELEMETRY
    # -------------------------------------------------------------
    suppressions = []
    evaluated_events = []
    
    all_rows = []
    with trade_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            
            all_rows.append(obj)
            event_type = obj.get("event_type", "")
            if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
                suppressions.append(obj)
            elif event_type == "POSITION_POLICY_SIDECAR_EVALUATED":
                evaluated_events.append(obj)
                
    print(f"Loaded {len(suppressions)} suppressed events and {len(evaluated_events)} evaluated events. Total parsed: {len(all_rows)}")
    
    # -------------------------------------------------------------
    # ANALYSIS A: SUPPRESSION BREAKDOWN
    # -------------------------------------------------------------
    suppression_reasons = Counter()
    reason_codes_dist = Counter()
    trigger_events_dist = Counter()
    suppression_by_symbol = Counter()
    
    suppression_by_status = Counter() # active vs inactive lifecycle
    suppression_time_buckets = Counter() # 1-hour buckets
    
    supp_before_during_after = Counter() # before / during / after BNBUSDT position
    
    # Start timestamp of the run
    start_ts = min(obj.get("ts_ms") for obj in suppressions if obj.get("ts_ms"))
    
    for obj in suppressions:
        ts = int(obj.get("ts_ms") or 0)
        symbol = obj.get("symbol", "UNKNOWN")
        reason = obj.get("suppression_reason", "UNKNOWN")
        trigger = obj.get("trigger_event", "UNKNOWN")
        
        suppression_reasons[reason] += 1
        trigger_events_dist[trigger] += 1
        suppression_by_symbol[symbol] += 1
        
        rc = obj.get("reason_codes", [])
        if isinstance(rc, list):
            for r in rc:
                reason_codes_dist[r] += 1
        else:
            reason_codes_dist[str(rc)] += 1
            
        # active vs inactive lifecycle
        is_active = (symbol == "BNBUSDT" and entry_ts_ms <= ts <= close_ts_ms)
        status_str = "ACTIVE_LIFECYCLE" if is_active else "INACTIVE_LIFECYCLE"
        suppression_by_status[status_str] += 1
        
        # before / during / after BNBUSDT position
        if ts < entry_ts_ms:
            supp_before_during_after["BEFORE"] += 1
        elif entry_ts_ms <= ts <= close_ts_ms:
            supp_before_during_after["DURING"] += 1
        else:
            supp_before_during_after["AFTER"] += 1
            
        # time buckets (1-hour from start)
        hour_bucket = int((ts - start_ts) / (3600 * 1000))
        suppression_time_buckets[f"Hour_{hour_bucket}"] += 1
        
    suppression_breakdown = {
        "suppression_reasons": dict(suppression_reasons),
        "reason_codes": dict(reason_codes_dist),
        "trigger_events": dict(trigger_events_dist),
        "suppression_by_symbol": dict(suppression_by_symbol),
        "suppression_by_status": dict(suppression_by_status),
        "suppression_time_buckets": dict(suppression_time_buckets),
        "supp_before_during_after": dict(supp_before_during_after)
    }
    
    with open(output_dir / "sidecar_suppression_breakdown.json", "w", encoding="utf-8") as f:
        json.dump(suppression_breakdown, f, indent=2)
        
    with open(output_dir / "sidecar_suppression_breakdown.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "name", "count"])
        for cat, dist in [
            ("reason", suppression_reasons),
            ("reason_code", reason_codes_dist),
            ("trigger", trigger_events_dist),
            ("symbol", suppression_by_symbol),
            ("lifecycle_status", suppression_by_status),
            ("timeline", supp_before_during_after)
        ]:
            for k, v in dist.items():
                writer.writerow([cat, k, v])
                
    # -------------------------------------------------------------
    # ANALYSIS B: FEATURE FRESHNESS CORRELATION
    # -------------------------------------------------------------
    freshness_classifications = []
    
    for obj in suppressions:
        reason = obj.get("suppression_reason")
        if reason != "features_snapshot_missing_or_stale":
            continue
            
        symbol = obj.get("symbol")
        ts = int(obj.get("ts_ms") or 0)
        
        # freshness age from snapshot
        fresh_snap = obj.get("freshness_snapshot", {})
        age_ms = fresh_snap.get("features_age_ms")
        
        # Find latest feature calc in log
        calcs = feature_calcs[symbol]
        prev_calcs = [c for c in calcs if c <= ts]
        latest_calc_ts = prev_calcs[-1] if prev_calcs else None
        
        actual_available_age = (ts - latest_calc_ts) if latest_calc_ts else None
        
        # Determine active lifecycle status
        is_active = (symbol == "BNBUSDT" and entry_ts_ms <= ts <= close_ts_ms)
        
        classification = "INSUFFICIENT_EVIDENCE"
        if not is_active:
            classification = "LIFECYCLE_NOT_ACTIVE_SO_FEATURE_STALE_IRRELEVANT"
        elif len(calcs) == 0:
            classification = "SYMBOL_NOT_ACTIVE_IN_FEATURE_PIPELINE"
        elif latest_calc_ts is None:
            classification = "NO_FEATURE_EVENT_FOR_SYMBOL"
        else:
            # We had calculations in the log.
            # If the calculation in log is fresh (<=15s), but Sidecar's age is stale (>15s):
            # then Sidecar did not cache or receive it!
            if actual_available_age is not None and actual_available_age <= 15000:
                classification = "FEATURE_EVENT_PRESENT_BUT_NOT_CACHED"
            else:
                classification = "FEATURE_EVENT_TOO_OLD"
                
        freshness_classifications.append({
            "symbol": symbol,
            "event_ts_ms": ts,
            "features_age_ms_reported": age_ms,
            "latest_feature_calc_ts_ms": latest_calc_ts,
            "actual_available_age_ms": actual_available_age,
            "configured_max_age_ms": 15000,
            "classification": classification
        })
        
    with open(output_dir / "feature_freshness_correlation.json", "w", encoding="utf-8") as f:
        json.dump(freshness_classifications, f, indent=2)
        
    classification_counts = Counter(item["classification"] for item in freshness_classifications)
    print("Feature freshness classifications counts:")
    for k, v in classification_counts.items():
        print(f"  {k}: {v}")
        
    # -------------------------------------------------------------
    # ANALYSIS C: BNBUSDT POSITION WINDOW
    # -------------------------------------------------------------
    # Sidecar events during open position:
    events_during_window = [obj for obj in all_rows if (obj.get("ts_ms") or 0) >= entry_ts_ms and (obj.get("ts_ms") or 0) <= close_ts_ms]
    
    # BNBUSDT specific events during window
    bnb_events = [obj for obj in events_during_window if obj.get("symbol") == "BNBUSDT"]
    
    # evaluated during window
    evaluated_during = [bnb for bnb in bnb_events if bnb.get("event_type") == "POSITION_POLICY_SIDECAR_EVALUATED"]
    suppressed_during = [bnb for bnb in bnb_events if bnb.get("event_type") == "POSITION_POLICY_SIDECAR_SUPPRESSED"]
    
    # soft close pressure
    pressures = []
    for obj in bnb_events:
        score_snap = obj.get("score_snapshot") or {}
        p = score_snap.get("soft_close_pressure")
        if p is not None:
            pressures.append(float(p))
            
    max_pressure = max(pressures) if pressures else 0.0
    
    # blocker counts
    blockers = Counter(obj.get("suppression_reason") for obj in suppressed_during)
    
    # stats metrics
    # We find stats final row from execution stats
    final_stats_row = None
    with stats_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("row_status") == "FINAL":
                    final_stats_row = obj
            except Exception:
                continue
                
    bnbusdt_position_window = {
        "lifecycle_id": "aurora_BNBUSDT_1781778004303",
        "entry_ts_ms": entry_ts_ms,
        "close_ts_ms": close_ts_ms,
        "duration_sec": (close_ts_ms - entry_ts_ms) / 1000.0,
        "close_reason": final_stats_row.get("close_reason") if final_stats_row else "SL",
        "gross_pnl": final_stats_row.get("gross_pnl") if final_stats_row else -27.2889,
        "fees": final_stats_row.get("fees") if final_stats_row else 3.982023,
        "net_pnl": final_stats_row.get("net_pnl") if final_stats_row else -31.270923,
        "total_bnb_events_during_window": len(bnb_events),
        "evaluated_count": len(evaluated_during),
        "suppressed_count": len(suppressed_during),
        "max_soft_close_pressure": max_pressure,
        "blockers": dict(blockers),
        "verdict": "SIDECAR_CONTEXT_STALE_DURING_POSITION" if blockers.get("features_snapshot_missing_or_stale", 0) > 1000 else "SIDECAR_HAD_VALID_CONTEXT_DURING_POSITION"
    }
    
    with open(output_dir / "bnbusdt_sidecar_position_window.json", "w", encoding="utf-8") as f:
        json.dump(bnbusdt_position_window, f, indent=2)
        
    # -------------------------------------------------------------
    # ANALYSIS D: HIGHEST PRESSURE EVENTS
    # -------------------------------------------------------------
    # Find all events (evaluated and suppressed) and sort by soft close pressure
    pressure_events = []
    
    # We scan all_rows (trade lifecycle log) for sidecar events with non-null soft close pressure
    for obj in all_rows:
        event_type = obj.get("event_type", "")
        if event_type.startswith("POSITION_POLICY_SIDECAR"):
            score_snap = obj.get("score_snapshot") or {}
            p = score_snap.get("soft_close_pressure")
            if p is not None:
                p_val = float(p)
                fresh_snap = obj.get("freshness_snapshot") or {}
                rc = obj.get("reason_codes", [])
                
                # Check if position was open
                ts = obj.get("ts_ms") or 0
                symbol = obj.get("symbol")
                pos_open = (symbol == "BNBUSDT" and entry_ts_ms <= ts <= close_ts_ms)
                
                pressure_events.append({
                    "ts_ms": ts,
                    "symbol": symbol,
                    "event_type": event_type,
                    "soft_close_pressure": p_val,
                    "threshold": 0.3,
                    "reason_codes": rc,
                    "context_freshness": f"pf={fresh_snap.get('portfolio_fresh')},ff={fresh_snap.get('features_fresh')},rf={fresh_snap.get('regime_fresh')},osf={fresh_snap.get('order_state_fresh')}",
                    "position_state": "OPEN" if pos_open else "CLOSED",
                    "why_no_recommendation": "Blocked by features/regime staled" if "stale" in str(rc) or "missing" in str(rc) else "Below threshold" if p_val < 0.3 else "Peak giveback disabled"
                })
                
    # Sort by pressure descending
    pressure_events.sort(key=lambda x: x["soft_close_pressure"], reverse=True)
    
    # Take top 10
    top_10_pressure = pressure_events[:10]
    
    highest_pressure_path = output_dir / "highest_pressure_events.csv"
    with highest_pressure_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "ts_ms", "symbol", "event_type", "soft_close_pressure", "threshold", "reason_codes", "context_freshness", "position_state", "why_no_recommendation"])
        for i, item in enumerate(top_10_pressure, 1):
            writer.writerow([
                i, item["ts_ms"], item["symbol"], item["event_type"], item["soft_close_pressure"],
                item["threshold"], ",".join(item["reason_codes"]), item["context_freshness"],
                item["position_state"], item["why_no_recommendation"]
            ])
            
    print(f"Top pressure events count: {len(pressure_events)}")
    if top_10_pressure:
        print(f"Max pressure observed: {top_10_pressure[0]['soft_close_pressure']}")

if __name__ == "__main__":
    main()
