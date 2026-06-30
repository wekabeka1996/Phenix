#!/usr/bin/env python3
import os
import json
import csv
from pathlib import Path
from collections import Counter, defaultdict

def main():
    frozen_dir = Path("C:/Users/wekab/Music/Phenix/frozen/sidecar_current_state_reset_20260618_143111Z")
    output_dir = Path("C:/Users/wekab/Music/Phenix/artifacts/sidecar_current_state_reset")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    trade_log_path = frozen_dir / "logs/trade_lifecycle.jsonl"
    order_log_path = frozen_dir / "logs/order_log_v1.jsonl"
    stats_log_path = frozen_dir / "logs/execution_lifecycle_stats_v1.jsonl"
    
    # -------------------------------------------------------------
    # 1. SCAN trade_lifecycle.jsonl FOR CENSUS AND PEAK-GIVEBACK
    # -------------------------------------------------------------
    event_counts = Counter()
    suppression_reasons = Counter()
    reason_codes_dist = Counter()
    trigger_events_dist = Counter()
    symbols_dist = Counter()
    
    peak_giveback_snapshot_count = 0
    peak_giveback_state_dist = Counter()
    shadow_percent_notional_rows = 0
    fee_aware_shadow_rows = 0
    
    authority_applied_count = 0
    shadow_only_count = 0
    no_effect_count = 0
    
    first_ts = None
    last_ts = None
    
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
            
            # Track timestamps
            ts = obj.get("ts_ms") or obj.get("updated_ts_ms") or obj.get("timestamp")
            if ts:
                ts = int(ts)
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
                
            # Process sidecar events
            event_type = obj.get("event_type", "")
            if event_type.startswith("POSITION_POLICY_SIDECAR"):
                event_counts[event_type] += 1
                
                symbol = obj.get("symbol")
                if symbol:
                    symbols_dist[symbol] += 1
                    
                trigger = obj.get("trigger_event")
                if trigger:
                    trigger_events_dist[trigger] += 1
                    
                rc = obj.get("reason_codes", [])
                if isinstance(rc, list):
                    for r in rc:
                        reason_codes_dist[r] += 1
                elif rc:
                    reason_codes_dist[str(rc)] += 1
                    
                if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
                    suppression_reasons[obj.get("suppression_reason", "UNKNOWN")] += 1
                    
                # Inspect peak_giveback_snapshot
                snapshot = obj.get("peak_giveback_snapshot")
                if snapshot and isinstance(snapshot, dict):
                    peak_giveback_snapshot_count += 1
                    
                    # Check peak_giveback_state
                    pg_state = snapshot.get("peak_giveback_state")
                    if pg_state:
                        peak_giveback_state_dist[pg_state] += 1
                        
                    # Check shadow arm settings
                    shadow_arms = snapshot.get("peak_giveback_shadow_arms") or snapshot.get("shadow_percent_notional_arm")
                    if shadow_arms:
                        shadow_percent_notional_rows += 1
                        
                    # Authority tracking
                    auth = snapshot.get("authority_applied") or snapshot.get("is_live_authority")
                    if auth is True:
                        authority_applied_count += 1
                    elif auth is False:
                        shadow_only_count += 1
                    else:
                        no_effect_count += 1
                        
                # Inspect fee-aware shadow arm state
                if event_type == "POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE":
                    fee_aware_shadow_rows += 1
                    
    # -------------------------------------------------------------
    # 2. RUNTIME SLICE MAP
    # -------------------------------------------------------------
    # We find slices based on MODE_ACTIVE events.
    mode_active_events = [obj for obj in all_rows if obj.get("event_type") == "POSITION_POLICY_SIDECAR_MODE_ACTIVE"]
    slices = []
    
    if mode_active_events:
        # There is exactly 1 active mode event in this run
        evt = mode_active_events[0]
        start_ts = evt.get("ts_ms")
        # Find all sidecar events after this start_ts
        slice_events = [obj for obj in all_rows if (obj.get("ts_ms") or 0) >= start_ts and obj.get("event_type", "").startswith("POSITION_POLICY_SIDECAR")]
        
        recs = sum(1 for obj in slice_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED")
        cls_reqs = sum(1 for obj in slice_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_CLOSE_REQUEST")
        fee_shadow = sum(1 for obj in slice_events if obj.get("event_type") == "POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE")
        
        symbols_seen = set(obj.get("symbol") for obj in slice_events if obj.get("symbol") and obj.get("symbol") != "__DOMAIN__")
        
        slices.append({
            "slice_id": 1,
            "start_ts_ms": start_ts,
            "end_ts_ms": last_ts,
            "duration_sec": round((last_ts - start_ts) / 1000.0, 2) if last_ts else 0.0,
            "confidence": "HIGH",
            "total_sidecar_events": len(slice_events),
            "recommendations": recs,
            "close_requests": cls_reqs,
            "fee_aware_shadow_rows": fee_shadow,
            "symbols_seen": sorted(list(symbols_seen))
        })
    else:
        # Fallback if no active mode event
        slices.append({
            "slice_id": 1,
            "start_ts_ms": first_ts,
            "end_ts_ms": last_ts,
            "duration_sec": round((last_ts - first_ts) / 1000.0, 2) if last_ts and first_ts else 0.0,
            "confidence": "LOW",
            "total_sidecar_events": sum(1 for obj in all_rows if obj.get("event_type", "").startswith("POSITION_POLICY_SIDECAR")),
            "recommendations": 0,
            "close_requests": 0,
            "fee_aware_shadow_rows": 0,
            "symbols_seen": []
        })

    # Write runtime_slice_map.csv
    slice_csv_path = output_dir / "runtime_slice_map.csv"
    with slice_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["slice_id", "start_ts_ms", "end_ts_ms", "duration_sec", "confidence", "total_sidecar_events", "recommendations", "close_requests", "fee_aware_shadow_rows", "symbols_seen"])
        for s in slices:
            writer.writerow([
                s["slice_id"], s["start_ts_ms"], s["end_ts_ms"], s["duration_sec"], s["confidence"],
                s["total_sidecar_events"], s["recommendations"], s["close_requests"], s["fee_aware_shadow_rows"],
                ",".join(s["symbols_seen"])
            ])

    # -------------------------------------------------------------
    # 3. PEAK-GIVEBACK AND NON-PEAK CHECKS
    # -------------------------------------------------------------
    # Indicators search
    containment_breach = False
    breach_evidence = []
    
    # We scan all rows in all_rows (trade lifecycle) and order log for peak_giveback authority signals
    for obj in all_rows:
        et = obj.get("event_type", "")
        # recommendation or close requests
        if et in ["POSITION_POLICY_SIDECAR_RECOMMENDED", "POSITION_POLICY_SIDECAR_CLOSE_REQUEST"]:
            rc = obj.get("reason_codes", [])
            why = obj.get("why", "")
            if "peak_giveback" in str(rc) or "peak_giveback" in str(why):
                containment_breach = True
                breach_evidence.append(f"Trade lifecycle event {et} has reason {rc or why}")
                
        snapshot = obj.get("peak_giveback_snapshot")
        if snapshot and isinstance(snapshot, dict):
            # Check trigger with authority applied
            if snapshot.get("authority_applied") is True or snapshot.get("is_live_authority") is True:
                # If reason is peak_giveback and it is applied live, that is a breach
                pg_state = snapshot.get("peak_giveback_state")
                if pg_state and "disabled" not in pg_state.lower():
                    containment_breach = True
                    breach_evidence.append(f"Peak giveback snapshot has authority_applied=True with state {pg_state}")

    # Scan order_log_v1.jsonl
    with order_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
                why = obj.get("why") or ""
                if "peak_giveback" in str(why):
                    containment_breach = True
                    breach_evidence.append(f"Order log event {obj.get('event_type')} has why='{why}'")
            except Exception:
                continue

    peak_status = "PEAK_GIVEBACK_CONTAINMENT_STILL_HOLDS"
    if containment_breach:
        peak_status = "PEAK_GIVEBACK_CONTAINMENT_BREACH"
    elif event_counts.get("POSITION_POLICY_SIDECAR_SUPPRESSED", 0) == 0:
        peak_status = "PEAK_GIVEBACK_NOT_TESTED_NO_ACTIVITY"

    # Non-peak Sidecar Activity Check
    # non-peak sidecar is active if we see evaluated, scores, recommendations, or close requests (excluding peak giveback)
    non_peak_active = False
    non_peak_status = "NON_PEAK_SIDECAR_NO_POSITION_ACTIVITY"
    
    if event_counts.get("POSITION_POLICY_SIDECAR_EVALUATED", 0) > 0 or event_counts.get("POSITION_POLICY_SIDECAR_SCORES", 0) > 0:
        non_peak_active = True
        non_peak_status = "NON_PEAK_SIDECAR_EVALUATES_ONLY"
        
    if event_counts.get("POSITION_POLICY_SIDECAR_RECOMMENDED", 0) > 0 or event_counts.get("POSITION_POLICY_SIDECAR_CLOSE_REQUEST", 0) > 0:
        non_peak_active = True
        non_peak_status = "NON_PEAK_SIDECAR_ACTIVE"

    # -------------------------------------------------------------
    # 4. LIGHT ECONOMICS SNAPSHOT
    # -------------------------------------------------------------
    closed_positions_count = 0
    gross_pnl = 0.0
    fees = 0.0
    net_pnl = 0.0
    net_pnl_by_symbol = defaultdict(float)
    close_reason_counts = Counter()
    sidecar_close_count = 0
    opened_lifecycles = set()
    closed_lifecycles = set()
    
    # Let's read execution_lifecycle_stats_v1.jsonl
    stats_rows = []
    with stats_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
                stats_rows.append(obj)
                lf_id = obj.get("lifecycle_id")
                if lf_id:
                    opened_lifecycles.add(lf_id)
                if obj.get("row_status") == "FINAL":
                    closed_lifecycles.add(lf_id)
                    closed_positions_count += 1
                    
                    gpnl = obj.get("gross_pnl") or 0.0
                    f_val = obj.get("fees") or 0.0
                    npnl = obj.get("net_pnl") or 0.0
                    
                    gross_pnl += gpnl
                    fees += f_val
                    net_pnl += npnl
                    
                    sym = obj.get("symbol", "UNKNOWN")
                    net_pnl_by_symbol[sym] += npnl
                    
                    reason = obj.get("close_reason")
                    if reason:
                        close_reason_counts[reason] += 1
                        
                    actor = obj.get("close_actor")
                    if actor == "POSITION_POLICY_SIDECAR" or (reason and "sidecar" in reason.lower()):
                        sidecar_close_count += 1
            except Exception:
                continue
                
    residual_open = len(opened_lifecycles - closed_lifecycles)
    
    economics_snapshot = {
        "final_lifecycles_count": len(closed_lifecycles),
        "opened_positions_count": len(opened_lifecycles),
        "closed_positions_count": closed_positions_count,
        "gross_pnl": round(gross_pnl, 6),
        "fees": round(fees, 6),
        "net_pnl": round(net_pnl, 6),
        "net_pnl_by_symbol": {k: round(v, 6) for k, v in net_pnl_by_symbol.items()},
        "close_reason_counts": dict(close_reason_counts),
        "sidecar_related_close_count": sidecar_close_count,
        "residual_open_positions": residual_open
    }
    
    econ_json_path = output_dir / "light_economics_snapshot.json"
    with econ_json_path.open("w", encoding="utf-8") as f:
        json.dump(economics_snapshot, f, indent=2)

    # -------------------------------------------------------------
    # 5. WRITE CENSUS JSON & CSV
    # -------------------------------------------------------------
    census_data = {
        "sidecar_event_types": dict(event_counts),
        "suppression_reason_distribution": dict(suppression_reasons),
        "recommendation_reason_codes_distribution": dict(reason_codes_dist),
        "trigger_event_distribution": dict(trigger_events_dist),
        "symbol_distribution": dict(symbols_dist),
        "peak_giveback_snapshot_count": peak_giveback_snapshot_count,
        "peak_giveback_state_distribution": dict(peak_giveback_state_dist),
        "shadow_percent_notional_telemetry_rows": shadow_percent_notional_rows,
        "fee_aware_shadow_telemetry_rows": fee_aware_shadow_rows,
        "authority_applied_values": {
            "authority_applied": authority_applied_count,
            "shadow_only": shadow_only_count,
            "no_effect": no_effect_count
        }
    }
    
    census_json_path = output_dir / "sidecar_event_census.json"
    with census_json_path.open("w", encoding="utf-8") as f:
        json.dump(census_data, f, indent=2)
        
    census_csv_path = output_dir / "sidecar_event_census.csv"
    with census_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric_category", "metric_name", "count_or_value"])
        for k, v in event_counts.items():
            writer.writerow(["event_type", k, v])
        for k, v in suppression_reasons.items():
            writer.writerow(["suppression_reason", k, v])
        for k, v in symbols_dist.items():
            writer.writerow(["symbol", k, v])
        for k, v in trigger_events_dist.items():
            writer.writerow(["trigger_event", k, v])
        for k, v in peak_giveback_state_dist.items():
            writer.writerow(["peak_giveback_state", k, v])
        writer.writerow(["summary", "peak_giveback_snapshot_count", peak_giveback_snapshot_count])
        writer.writerow(["summary", "shadow_percent_notional_telemetry_rows", shadow_percent_notional_rows])
        writer.writerow(["summary", "fee_aware_shadow_telemetry_rows", fee_aware_shadow_rows])
        writer.writerow(["authority", "authority_applied", authority_applied_count])
        writer.writerow(["authority", "shadow_only", shadow_only_count])
        writer.writerow(["authority", "no_effect", no_effect_count])

    print("Analysis finished successfully.")
    print(f"Output files generated in: {output_dir}")
    print(f"Peak containment status: {peak_status}")
    print(f"Non-peak sidecar status: {non_peak_status}")

if __name__ == "__main__":
    main()
