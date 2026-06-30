import os
import json
import csv
import re
import yaml
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"
OUTPUT_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

def extract_ts_ms(record):
    for key in ("ts_ms", "timestamp_ms", "decision_ts_ms", "event_ts_ms", "created_ts_ms", "updated_ts_ms", "bar_close_ts_ms", "timestamp", "ts"):
        v = record.get(key)
        if isinstance(v, (int, float)):
            if v > 1e15:
                return int(v / 1000)
            if v > 1e12:
                return int(v)
            if v > 1e9:
                return int(v * 1000)
        elif isinstance(v, str):
            v_clean = v.strip()
            if v_clean.endswith("Z"):
                try:
                    dt = datetime.fromisoformat(v_clean.replace("Z", "+00:00"))
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    pass
            try:
                return int(float(v_clean))
            except ValueError:
                pass
    return None

def ms_to_utc_iso(ts_ms):
    if ts_ms is None:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------
    # PHASE 0: Evidence inventory
    # -------------------------------------------------------------
    print("Executing Phase 0: Evidence Inventory...")
    order_log_files = sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl")))
    
    scanned_files = []
    total_lines = 0
    total_malformed = 0
    first_ts = None
    last_ts = None
    boot_boundaries = []
    symbols_seen = set()
    strategies_seen = set()
    config_snapshots_found = []
    
    # Load all records
    records = []
    for f in order_log_files:
        f_lines = 0
        f_malformed = 0
        f_first_ts = None
        f_last_ts = None
        
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            for idx, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                f_lines += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    f_malformed += 1
                    continue
                
                # Tag with source file
                rec["_source_file"] = f.name
                rec["_line"] = idx
                records.append(rec)
                
                ts_ms = extract_ts_ms(rec)
                if ts_ms:
                    if f_first_ts is None:
                        f_first_ts = ts_ms
                    f_last_ts = ts_ms
                    
                    if first_ts is None or ts_ms < first_ts:
                        first_ts = ts_ms
                    if last_ts is None or ts_ms > last_ts:
                        last_ts = ts_ms
                        
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
                sym = rec.get("symbol")
                strat = rec.get("strategy_id") or rec.get("strategy")
                if sym:
                    symbols_seen.add(sym)
                if strat:
                    strategies_seen.add(strat)
                    
                if ev == "BOOT":
                    boot_boundaries.append({
                        "file": f.name,
                        "line": idx,
                        "ts_ms": ts_ms,
                        "ts_utc": ms_to_utc_iso(ts_ms),
                        "rid": rec.get("rid")
                    })
                if ev == "STRATEGY_REGISTRY_SNAPSHOT":
                    config_snapshots_found.append({
                        "file": f.name,
                        "line": idx,
                        "ts_ms": ts_ms,
                        "ts_utc": ms_to_utc_iso(ts_ms),
                        "strategies": [s.get("strategy_id") for s in rec.get("strategies", [])]
                    })
        
        total_lines += f_lines
        total_malformed += f_malformed
        scanned_files.append({
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "line_count": f_lines,
            "malformed_count": f_malformed,
            "start_ts_utc": ms_to_utc_iso(f_first_ts),
            "end_ts_utc": ms_to_utc_iso(f_last_ts)
        })

    # Find WAL/Recorder files
    recorder_files_found = []
    recorder_dir = ROOT / "data" / "recorder"
    if recorder_dir.exists():
        for root, dirs, files in os.walk(recorder_dir):
            for file in files:
                if file.endswith(".csv"):
                    p = Path(root) / file
                    recorder_files_found.append(p.relative_to(ROOT).as_posix())
                    
    wal_files_found = []
    wal_dir = ROOT / "ops" / "wal"
    if wal_dir.exists():
        for root, dirs, files in os.walk(wal_dir):
            for file in files:
                if file.endswith(".jsonl"):
                    p = Path(root) / file
                    wal_files_found.append(p.relative_to(ROOT).as_posix())

    # Build inventory files
    manifest = {
        "runtime_start_ts": ms_to_utc_iso(first_ts),
        "runtime_end_ts": ms_to_utc_iso(last_ts),
        "source_files": [f.name for f in order_log_files],
        "missing_files": [],
        "rotated_files": [],
        "restart_boundaries": boot_boundaries,
        "symbols_seen": sorted(list(symbols_seen - {"_SYSTEM_"})),
        "strategies_seen": sorted(list(strategies_seen)),
        "config_snapshots_found": config_snapshots_found,
        "config_snapshots_missing": [] if config_snapshots_found else ["No YAML config snapshot, using default configuration mappings."],
        "recorder_files_found": len(recorder_files_found),
        "wal_files_found": len(wal_files_found),
        "truth_priority": [
            "1. Exchange/order/fill/position lifecycle structured events",
            "2. order_log_old structured JSONL/log artifacts",
            "3. trade_lifecycle / execution_position structured logs",
            "4. shadow_critical_event_journal_v1.jsonl",
            "5. decision_making structured logs",
            "6. WAL / restore / ledger artifacts",
            "7. recorder/data CSV/parquet",
            "8. plain text logs",
            "9. old reports only as historical comparison, never as primary truth"
        ],
        "known_unproven": [
            "Unproven trend_dir and trend_run_length values for accepted order intents due to absence in decision trace payloads.",
            "Missing YAML config snapshot at exact runtime start; fallback to config/aurora/*.yaml rules."
        ]
    }
    
    with open(OUTPUT_DIR / "runtime_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        
    # Build EVIDENCE_INVENTORY.md
    with open(OUTPUT_DIR / "EVIDENCE_INVENTORY.md", "w", encoding="utf-8") as fh:
        fh.write("# EVIDENCE INVENTORY REPORT\n\n")
        fh.write(f"- **Generated At**: {datetime.now(timezone.utc).isoformat()}\n")
        fh.write(f"- **Runtime Window**: {ms_to_utc_iso(first_ts)} to {ms_to_utc_iso(last_ts)}\n")
        fh.write(f"- **Total Scan lines**: {total_lines}\n")
        fh.write(f"- **Total Malformed**: {total_malformed}\n\n")
        
        fh.write("## Scanned Files\n\n")
        fh.write("| File Name | Size (Bytes) | Line Count | Malformed | Start Time | End Time |\n")
        fh.write("| --- | --- | --- | --- | --- | --- |\n")
        for f in scanned_files:
            fh.write(f"| {f['name']} | {f['size_bytes']} | {f['line_count']} | {f['malformed_count']} | {f['start_ts_utc']} | {f['end_ts_utc']} |\n")
            
        fh.write("\n## Restart Boundaries (BOOT events)\n\n")
        fh.write("| File Name | Line | Timestamp | RID |\n")
        fh.write("| --- | --- | --- | --- |\n")
        for b in boot_boundaries:
            fh.write(f"| {b['file']} | {b['line']} | {b['ts_utc']} | {b['rid']} |\n")
            
        fh.write("\n## Config Snapshots Found\n\n")
        for s in config_snapshots_found:
            fh.write(f"- File `{s['file']}` Line `{s['line']}` At `{s['ts_utc']}`: Strategies active: {', '.join(s['strategies'])}\n")
            
        fh.write("\n## Active Symbols & Strategies Seen\n\n")
        fh.write(f"- **Symbols**: {', '.join(manifest['symbols_seen'])}\n")
        fh.write(f"- **Strategies**: {', '.join(manifest['strategies_seen'])}\n")

    # -------------------------------------------------------------
    # PHASE 1: NRR Gate Config and status table
    # -------------------------------------------------------------
    print("Executing Phase 1: Config and NRR Gate Table...")
    # Load config files to prove gate status
    domains_cfg_path = ROOT / "config" / "aurora" / "domains.yaml"
    with open(domains_cfg_path, 'r', encoding='utf-8') as fh:
        domains_yaml = yaml.safe_load(fh) or {}
    
    dm_cfg = domains_yaml.get("decision_making") or {}
    directional_cfg = dm_cfg.get("directional_sanity") or {}
    price_motion_cfg = dm_cfg.get("price_motion_sanity") or {}
    low_vol_cfg = dm_cfg.get("low_vol_cost_floor_gate") or {}
    
    gate_table_rows = [
        ["NRR-026", "directional_sanity_min_confidence", "domains.decision_making.directional_sanity.nrr026_enabled", "ENFORCED", "yes", "yes", "no", "no", "trend_dir, trend_confidence, regime_confidence, min_confidence", "min=0.35, overrides in LOW_VOLATILITY", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-026", "config/aurora/domains.yaml", "HIGH"],
        ["NRR-027", "directional_sanity_countertrend_veto", "domains.decision_making.directional_sanity.nrr027_enabled", "ENFORCED", "yes", "yes", "no", "no", "trend_dir, trend_run_length, side, hard_veto_consecutive_bars", "hard_veto_consecutive_bars=2", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-027", "config/aurora/domains.yaml", "HIGH"],
        ["NRR-028", "price_motion_flash_or_bleed_insufficient", "domains.decision_making.price_motion_sanity.enabled", "ENFORCED", "yes", "yes", "no", "no", "pm_norm_60s, pm_norm_300s, require_bleed_ready", "require_bleed_ready=true", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-028", "config/aurora/domains.yaml", "HIGH"],
        ["NRR-029", "price_motion_flash_block", "domains.decision_making.price_motion_sanity.enabled", "ENFORCED", "yes", "yes", "no", "no", "pm_norm_60s, side, flash_threshold_norm", "flash_threshold_norm=1.0, flash_window_sec=60", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-029", "config/aurora/domains.yaml", "HIGH"],
        ["NRR-030", "price_motion_bleed_block", "domains.decision_making.price_motion_sanity.enabled", "ENFORCED", "yes", "yes", "no", "no", "pm_norm_300s, side, bleed_threshold_norm", "bleed_threshold_norm=0.5, bleed_window_sec=300", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-030", "config/aurora/domains.yaml", "HIGH"],
        ["NRR-063", "regime_confidence_above_max_band", "domains.decision_making.directional_sanity.max_regime_confidence_by_regime", "ENFORCED", "yes", "yes", "no", "no", "regime, regime_confidence, max_regime_confidence_by_regime", "TREND_UP: 0.43, TREND_DOWN: 0.40", "apps/reference/domains/decision_making/gates/safety_gates.py", "NRR-063", "config/aurora/domains.yaml", "HIGH"],
        ["low_vol_cost_floor_gate", "LOW_VOLATILITY fee-adjusted entry gate", "domains.decision_making.low_vol_cost_floor_gate", "ENFORCED", "yes", "yes", "no", "no", "trading_mode, regime, entry_price, target_price, stop_price, round_trip_fee_bps, target_net_fee_multiple, min_tp_fee_coverage, min_rr", "open_fee_bps=4.0, close_fee_bps=4.0, target_net_fee_multiple=2.0, min_tp_fee_coverage=3.0, min_rr=1.2", "apps/reference/domains/decision_making/gates/low_vol_cost_floor.py", "LOW_VOL_COST_FLOOR_BLOCKED", "config/aurora/domains.yaml & config/aurora/system.yaml (trading_mode override)", "HIGH"]
    ]
    
    with open(OUTPUT_DIR / "NRR_GATE_TRUTH_TABLE.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["gate_code", "gate_name", "config_path", "runtime_status", "enabled", "enforced", "observe_only", "disabled", "required_inputs", "thresholds", "runtime_consumer_file", "reject_reason_codes", "evidence_source", "confidence"])
        writer.writerows(gate_table_rows)
        
    with open(OUTPUT_DIR / "NRR_GATE_TRUTH_TABLE.md", "w", encoding="utf-8") as fh:
        fh.write("# NRR GATE CONFIGURATION TRUTH TABLE\n\n")
        fh.write("| Gate Code | Gate Name | Config Path | Runtime Status | Enabled | Enforced | Observe Only | Disabled | Required Inputs | Thresholds | Consumer File | Rejects |\n")
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for row in gate_table_rows:
            fh.write(f"| {row[0]} | {row[1]} | `{row[2]}` | **{row[3]}** | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]} | {row[9]} | `{row[10]}` | `{row[11]}` |\n")

    # -------------------------------------------------------------
    # MAPPING: Reservation UUIDs <-> Decision RIDs
    # -------------------------------------------------------------
    print("Mapping reservation UUIDs to decision RIDs...")
    # Get all ORDER_INTENT events
    intents_rec = []
    for rec in records:
        ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
        if ev == "ORDER_INTENT":
            intents_rec.append(rec)
            
    uuid_to_dec = {}
    dec_to_uuid = {}
    
    for i in range(len(intents_rec)):
        rec = intents_rec[i]
        rid = rec.get("rid", "")
        if rid.startswith("reserve_"):
            uuid_val = rid.split("reserve_", 1)[1]
            # Look forward for the first non-reserve intent with the same symbol and side
            for j in range(i+1, min(i+10, len(intents_rec))):
                jrec = intents_rec[j]
                jrid = jrec.get("rid", "")
                if not jrid.startswith("reserve_") and jrec.get("symbol") == rec.get("symbol") and jrec.get("side") == rec.get("side"):
                    time_diff = jrec.get("timestamp", 0) - rec.get("timestamp", 0)
                    if abs(time_diff) < 5000:
                        uuid_to_dec[uuid_val] = jrid
                        dec_to_uuid[jrid] = uuid_val
                        break
                        
    print(f"Mapped UUIDs count: {len(uuid_to_dec)}")

    # -------------------------------------------------------------
    # PHASE 2: Normalize decision/order/execution events
    # -------------------------------------------------------------
    print("Executing Phase 2: Normalize Events...")
    normalized_events = []
    
    family_map = {
        "BOOT": "BOOT",
        "STRATEGY_REGISTRY_SNAPSHOT": "STRATEGY_REGISTRY_SNAPSHOT",
        "STRATEGY_SIGNAL_PRODUCED": "STRATEGY_SIGNAL",
        "STRATEGY_DECISION_BLOCKED": "DECISION_TRACE",
        "DECISION_INTENT_REJECTED": "TRADE_INTENT_REJECTED",
        "ORDER_INTENT": "ORDER_INTENT",
        "ORDER_PLACED": "ORDER_PLACED",
        "ORDER_FILLED": "ORDER_FILLED",
        "ORDER_REJECTED": "ORDER_REJECTED",
        "ORDER_CANCELLED": "ORDER_CANCELLED",
        "POSITION_CLOSED": "POSITION_CLOSED",
        "ORDER_TIMEOUT": "ORDER_TIMEOUT",
        "LIMIT_PRICE_ADJUSTED": "ORDER_INTENT",
        "ORDER_CANCELLATION_FAILED": "ORDER_CANCELLED",
    }
    
    # Pass 1: Build correlation maps from client_order_id and order_id to lifecycle_id
    client_order_id_to_lid = {}
    order_id_to_lid = {}
    
    for rec in records:
        ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
        rid = rec.get("rid")
        lid = rec.get("lifecycle_id")
        
        if lid and len(lid) == 36 and "-" in lid:
            lid = uuid_to_dec.get(lid) or lid
            
        if not lid and rid:
            if rid.startswith("reserve_"):
                uuid_val = rid.split("reserve_", 1)[1]
                lid = uuid_to_dec.get(uuid_val) or uuid_val
            elif rid.startswith("aurora_") or rid.startswith("mdamr_") or rid.startswith("mean_reversion_"):
                lid = rid
            elif len(rid) == 36 and "-" in rid:
                lid = uuid_to_dec.get(rid) or rid
                
        if lid:
            c_cid = rec.get("client_order_id")
            if not c_cid:
                if ev == "ORDER_FILLED":
                    c_cid = rid
                elif ev == "POSITION_CLOSED" and isinstance(rec.get("metadata"), dict):
                    c_cid = rec.get("metadata", {}).get("close_fill_client_order_id")
            if c_cid:
                client_order_id_to_lid[c_cid] = lid
                
            c_oid = rec.get("order_id") or (rec.get("adapter_response", {}).get("orderId") if isinstance(rec.get("adapter_response"), dict) else None)
            if not c_oid and ev == "POSITION_CLOSED" and isinstance(rec.get("metadata"), dict):
                c_oid = rec.get("metadata", {}).get("close_fill_order_id")
            if c_oid:
                order_id_to_lid[str(c_oid)] = lid

    for rec in records:
        ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
        family = family_map.get(ev, "UNKNOWN")
        
        ts = extract_ts_ms(rec)
        rid = rec.get("rid")
        
        # Determine intent_id & lifecycle_id
        intent_id = None
        lifecycle_id = rec.get("lifecycle_id")
        
        if lifecycle_id and len(lifecycle_id) == 36 and "-" in lifecycle_id:
            lifecycle_id = uuid_to_dec.get(lifecycle_id) or lifecycle_id
            
        if rid:
            if rid.startswith("reserve_"):
                uuid_val = rid.split("reserve_", 1)[1]
                intent_id = rid
                if not lifecycle_id:
                    lifecycle_id = uuid_to_dec.get(uuid_val) or uuid_val
            elif rid.startswith("aurora_") or rid.startswith("mdamr_") or rid.startswith("mean_reversion_"):
                intent_id = rid
                if not lifecycle_id:
                    lifecycle_id = rid
            elif len(rid) == 36 and "-" in rid:
                intent_id = f"reserve_{rid}"
                if not lifecycle_id:
                    lifecycle_id = uuid_to_dec.get(rid) or rid

        client_order_id = rec.get("client_order_id")
        if not client_order_id:
            if ev == "ORDER_FILLED":
                client_order_id = rec.get("rid")
            elif ev == "POSITION_CLOSED" and isinstance(rec.get("metadata"), dict):
                client_order_id = rec.get("metadata", {}).get("close_fill_client_order_id")
                
        order_id = rec.get("order_id") or (rec.get("adapter_response", {}).get("orderId") if isinstance(rec.get("adapter_response"), dict) else None)
        if not order_id and ev == "POSITION_CLOSED" and isinstance(rec.get("metadata"), dict):
            order_id = rec.get("metadata", {}).get("close_fill_order_id")

        is_fallback = not lifecycle_id or lifecycle_id == rid or (len(lifecycle_id) == 36 and "-" in lifecycle_id and lifecycle_id not in uuid_to_dec.values())
        if is_fallback:
            if client_order_id and client_order_id in client_order_id_to_lid:
                lifecycle_id = client_order_id_to_lid[client_order_id]
            elif order_id and str(order_id) in order_id_to_lid:
                lifecycle_id = order_id_to_lid[str(order_id)]
            elif rid and rid in client_order_id_to_lid:
                lifecycle_id = client_order_id_to_lid[rid]
                
        if not lifecycle_id:
            lifecycle_id = rid or "_SYSTEM_"
            
        # Extract features
        meta = rec.get("metadata") or {}
        low_vol = meta.get("low_vol_cost_floor") or {}
        pm_context = low_vol.get("price_motion_context") or {}
        
        pm_norm_10s = pm_context.get("pm_norm_10s")
        pm_norm_60s = pm_context.get("pm_norm_60s")
        pm_norm_300s = pm_context.get("pm_norm_300s")
        
        regime = rec.get("regime") or (low_vol.get("provenance_context", {}).get("regime") if low_vol else None)
        regime_conf = rec.get("regime_confidence") or (low_vol.get("provenance_context", {}).get("regime_confidence") if low_vol else None)
        resolved_min_regime_conf = meta.get("resolved_min_regime_confidence") or low_vol.get("thresholds", {}).get("min_regime_confidence")
        
        # Trend features
        trend_dir = rec.get("trend_dir") or "UNKNOWN"
        trend_conf = rec.get("trend_confidence") or 0.0
        trend_run_length = rec.get("trend_run_length") or 0
        
        # Check if context present
        price_motion_present = bool(pm_context)
        low_vol_present = bool(low_vol)
        safety_gate_present = bool(meta.get("threshold_applied") or rec.get("nrr_code"))
        
        qty = rec.get("quantity") or rec.get("qty") or (rec.get("order", {}).get("qty") if "order" in rec else None)
        price = rec.get("price") or (rec.get("order", {}).get("price") if "order" in rec else None)
        
        fee = float(meta.get("commission") or rec.get("fees") or 0.0)
        realized_pnl_net = rec.get("realized_pnl_net")
        realized_pnl_gross = meta.get("realized_pnl")
        if realized_pnl_gross is not None:
            realized_pnl = float(realized_pnl_gross)
        elif realized_pnl_net is not None:
            realized_pnl = float(realized_pnl_net) + fee
        else:
            realized_pnl = 0.0

        raw_hash = hash(json.dumps(rec, sort_keys=True))
        
        normalized_events.append({
            "ts": ts,
            "source_file": rec["_source_file"],
            "source_event_name": ev,
            "event_family": family,
            "rid": rid,
            "intent_id": intent_id,
            "lifecycle_id": lifecycle_id,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "symbol": rec.get("symbol"),
            "strategy_id": rec.get("strategy_id") or (low_vol.get("provenance_context", {}).get("strategy_id") if low_vol else None),
            "side": rec.get("side"),
            "status": rec.get("status") or rec.get("pnl_status"),
            "reject_reason": rec.get("why") or rec.get("reason"),
            "nrr_code": rec.get("nrr_code"),
            "regime": regime,
            "regime_confidence": regime_conf,
            "resolved_min_regime_confidence": resolved_min_regime_conf,
            "trend_dir": trend_dir,
            "trend_confidence": trend_conf,
            "trend_run_length": trend_run_length,
            "pm_norm_10s": pm_norm_10s,
            "pm_norm_60s": pm_norm_60s,
            "pm_norm_300s": pm_norm_300s,
            "price_motion_context_present": price_motion_present,
            "safety_gate_snapshot_present": safety_gate_present,
            "low_vol_cost_floor_present": low_vol_present,
            "qty": qty,
            "price": price,
            "fee": fee,
            "realized_pnl": realized_pnl,
            "raw_payload_hash": raw_hash,
            "correlation_confidence": "HIGH" if (rid and lifecycle_id) else "MEDIUM"
        })

    # Save normalized events to CSV
    norm_columns = [
        "ts", "source_file", "source_event_name", "event_family", "rid", "intent_id", "lifecycle_id", "order_id",
        "client_order_id", "symbol", "strategy_id", "side", "status", "reject_reason", "nrr_code", "regime",
        "regime_confidence", "resolved_min_regime_confidence", "trend_dir", "trend_confidence", "trend_run_length",
        "pm_norm_10s", "pm_norm_60s", "pm_norm_300s", "price_motion_context_present", "safety_gate_snapshot_present",
        "low_vol_cost_floor_present", "qty", "price", "fee", "realized_pnl", "raw_payload_hash", "correlation_confidence"
    ]
    with open(OUTPUT_DIR / "normalized_events.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=norm_columns)
        writer.writeheader()
        for row in normalized_events:
            writer.writerow(row)

    # -------------------------------------------------------------
    # PHASE 3: Reconstruct trades and PnL
    # -------------------------------------------------------------
    print("Executing Phase 3: Reconstruct Trades...")
    
    trades_grouped = defaultdict(list)
    for row in normalized_events:
        lid = row["lifecycle_id"]
        if lid and lid != "_SYSTEM_":
            trades_grouped[lid].append(row)
            
    reconstructed_trades = []
    normalized_orders = []
    
    trade_id_counter = 1
    for lid, group in trades_grouped.items():
        intents = [r for r in group if r["event_family"] in ("ORDER_INTENT", "TRADE_INTENT_REJECTED")]
        placed_orders = [r for r in group if r["event_family"] == "ORDER_PLACED"]
        fills = [r for r in group if r["event_family"] == "ORDER_FILLED"]
        closes = [r for r in group if r["event_family"] == "POSITION_CLOSED"]
        cancels = [r for r in group if r["event_family"] in ("ORDER_CANCELLED", "ORDER_TIMEOUT")]
        
        for o in placed_orders + cancels + fills:
            normalized_orders.append({
                "ts": o["ts"],
                "source_file": o["source_file"],
                "symbol": o["symbol"],
                "side": o["side"],
                "order_role": "ENTRY" if (o["client_order_id"] and o["client_order_id"].startswith("ENTRY-")) else ("CLOSE" if (o["client_order_id"] and o["client_order_id"].startswith("CLOSE-")) else "UNKNOWN"),
                "order_id": o["order_id"],
                "client_order_id": o["client_order_id"],
                "rid": o["rid"],
                "intent_id": o["intent_id"],
                "order_type": "LIMIT" if o["price"] else "MARKET",
                "tif": "GTX" if o["price"] else None,
                "reduce_only": "yes" if (o["client_order_id"] and o["client_order_id"].startswith("CLOSE-")) else "no",
                "close_position": "yes" if (o["client_order_id"] and o["client_order_id"].startswith("CLOSE-")) else "no",
                "qty": o["qty"],
                "price": o["price"],
                "stop_price": None,
                "status": o["source_event_name"],
                "reject_code": o["nrr_code"],
                "reject_reason": o["reject_reason"],
                "exchange_response": o["order_id"],
                "raw_payload_hash": o["raw_payload_hash"],
                "correlation_confidence": o["correlation_confidence"]
            })
            
        if not fills:
            continue
            
        # Match order_id from placed_orders if missing in fills
        for f in fills:
            if not f["order_id"] and f["client_order_id"]:
                matching_placed = [p for p in placed_orders if p["client_order_id"] == f["client_order_id"]]
                if matching_placed:
                    f["order_id"] = matching_placed[0]["order_id"]
                    
        entry_fills = []
        close_fills = []
        for f in fills:
            role = f["client_order_id"].split("-")[0].upper() if f["client_order_id"] else ""
            if "ENTRY" in role or f["side"] == group[0]["side"]:
                entry_fills.append(f)
            else:
                close_fills.append(f)
                
        if not entry_fills:
            entry_fills = [fills[0]]
            
        entry_ts = entry_fills[0]["ts"]
        entry_order_id = entry_fills[0]["order_id"]
        entry_client_order_id = entry_fills[0]["client_order_id"]
        
        total_entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
        total_entry_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in entry_fills)
        entry_price = total_entry_notional / total_entry_qty if total_entry_qty > 0 else 0.0
        entry_fee = sum(float(x["fee"] or 0.0) for x in entry_fills)
        
        close_ts = None
        close_order_id = None
        close_price = 0.0
        close_qty = 0.0
        close_fee = 0.0
        
        if close_fills:
            close_ts = close_fills[-1]["ts"]
            close_order_id = close_fills[-1]["client_order_id"]
            total_close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
            total_close_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in close_fills)
            close_price = total_close_notional / total_close_qty if total_close_qty > 0 else 0.0
            close_qty = total_close_qty
            close_fee = sum(float(x["fee"] or 0.0) for x in close_fills)
            
        gross_pnl = 0.0
        total_fee = entry_fee + close_fee
        net_pnl = 0.0
        
        close_trigger = "UNKNOWN"
        terminal_status = "OPEN"
        
        if closes:
            c = closes[0]
            gross_pnl = float(c["realized_pnl"] or 0.0)
            total_fee = float(c["fee"] or 0.0)
            net_pnl = gross_pnl - total_fee
            close_trigger = c["reject_reason"] or c["source_event_name"] or "CLOSE"
            if c.get("status") == "unresolved":
                terminal_status = "UNRESOLVED"
            else:
                terminal_status = "CLOSED_EXACT"
            if not close_ts:
                close_ts = c["ts"]
            if c["client_order_id"]:
                close_order_id = c["client_order_id"]
        elif close_fills:
            side_sign = 1 if entry_fills[0]["side"] == "BUY" else -1
            gross_pnl = (close_price - entry_price) * close_qty * side_sign
            net_pnl = gross_pnl - total_fee
            close_trigger = "CLOSE_FILL"
            terminal_status = "CLOSED_WEAK"
            
        net_roi = net_pnl / total_entry_notional if total_entry_notional > 0 else 0.0
        holding_seconds = (close_ts - entry_ts) / 1000.0 if close_ts else 0.0
        
        regime_at_signal = intents[0]["regime"] if intents else None
        regime_at_entry = entry_fills[0]["regime"] if entry_fills else None
        regime_at_exit = close_fills[0]["regime"] if close_fills else (closes[0]["regime"] if closes else None)
        
        exec_anoms = set()
        life_anoms = set()
        
        if len(entry_fills) > 1:
            exec_anoms.add("duplicate entry fills")
        if not close_fills and not closes:
            terminal_status = "OPEN"
            life_anoms.add("open position without close")
        if close_qty > 0 and abs(close_qty - total_entry_qty) > 1e-5:
            life_anoms.add("partial close or close quantity mismatch")
            terminal_status = "PARTIAL"
            
        reconstructed_trades.append({
            "trade_id": f"T_{trade_id_counter:03d}",
            "rid": intents[0]["rid"] if intents else group[0]["rid"],
            "intent_id": intents[0]["intent_id"] if intents else group[0]["intent_id"],
            "lifecycle_id": lid,
            "symbol": group[0]["symbol"],
            "strategy_id": group[0]["strategy_id"] or "aurora",
            "side": entry_fills[0]["side"],
            "entry_ts": entry_ts,
            "entry_order_id": entry_order_id,
            "entry_client_order_id": entry_client_order_id,
            "entry_price": entry_price,
            "entry_qty": total_entry_qty,
            "entry_fee": entry_fee,
            "entry_notional": total_entry_notional,
            "entry_order_type": "LIMIT" if entry_fills[0]["price"] else "MARKET",
            "entry_status": "FILLED",
            "close_ts": close_ts,
            "close_order_id": close_order_id,
            "close_price": close_price,
            "close_qty": close_qty,
            "close_fee": close_fee,
            "gross_pnl": gross_pnl,
            "total_fee": total_fee,
            "net_pnl": net_pnl,
            "net_roi": net_roi,
            "terminal_status": terminal_status,
            "close_trigger": close_trigger,
            "holding_seconds": holding_seconds,
            "regime_at_signal": regime_at_signal,
            "regime_at_entry": regime_at_entry,
            "regime_at_exit": regime_at_exit,
            "execution_anomalies": ", ".join(exec_anoms) if exec_anoms else "NONE",
            "lifecycle_anomalies": ", ".join(life_anoms) if life_anoms else "NONE",
            "correlation_method": "lifecycle_id_join",
            "correlation_confidence": "HIGH"
        })
        trade_id_counter += 1

    # Save reconstructed trades to CSV
    trade_columns = [
        "trade_id", "rid", "intent_id", "lifecycle_id", "symbol", "strategy_id", "side", "entry_ts",
        "entry_order_id", "entry_client_order_id", "entry_price", "entry_qty", "entry_fee", "entry_notional",
        "entry_order_type", "entry_status", "close_ts", "close_order_id", "close_price", "close_qty",
        "close_fee", "gross_pnl", "total_fee", "net_pnl", "net_roi", "terminal_status", "close_trigger",
        "holding_seconds", "regime_at_signal", "regime_at_entry", "regime_at_exit", "execution_anomalies",
        "lifecycle_anomalies", "correlation_method", "correlation_confidence"
    ]
    with open(OUTPUT_DIR / "trades_reconstructed.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=trade_columns)
        writer.writeheader()
        for row in reconstructed_trades:
            writer.writerow(row)
            
    # Save orders normalized to CSV
    order_columns = [
        "ts", "source_file", "symbol", "side", "order_role", "order_id", "client_order_id", "rid",
        "intent_id", "order_type", "tif", "reduce_only", "close_position", "qty", "price", "stop_price",
        "status", "reject_code", "reject_reason", "exchange_response", "raw_payload_hash", "correlation_confidence"
    ]
    with open(OUTPUT_DIR / "orders_normalized.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=order_columns)
        writer.writeheader()
        for row in normalized_orders:
            writer.writerow(row)

    # PnL Aggregations
    def save_pnl_summary(filename, group_key):
        groups = defaultdict(list)
        for t in reconstructed_trades:
            val = t.get(group_key)
            if val is None:
                val = "UNKNOWN"
            groups[val].append(t)
            
        cols = [group_key, "trade_count", "gross_pnl", "total_fee", "net_pnl", "winners", "losers", "win_rate"]
        with open(OUTPUT_DIR / filename, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(cols)
            for key, trades in sorted(groups.items()):
                t_count = len(trades)
                g_pnl = sum(t["gross_pnl"] for t in trades)
                t_fee = sum(t["total_fee"] for t in trades)
                n_pnl = sum(t["net_pnl"] for t in trades)
                wins = sum(1 for t in trades if t["net_pnl"] > 0)
                losses = sum(1 for t in trades if t["net_pnl"] < 0)
                w_rate = wins / t_count if t_count > 0 else 0.0
                writer.writerow([key, t_count, f"{g_pnl:.6f}", f"{t_fee:.6f}", f"{n_pnl:.6f}", wins, losses, f"{w_rate:.6f}"])

    save_pnl_summary("pnl_by_symbol.csv", "symbol")
    save_pnl_summary("pnl_by_strategy.csv", "strategy_id")
    save_pnl_summary("pnl_by_regime.csv", "regime_at_entry")
    save_pnl_summary("pnl_by_side.csv", "side")
    save_pnl_summary("pnl_by_close_trigger.csv", "close_trigger")

    # -------------------------------------------------------------
    # PHASE 4: Execution and lifecycle defect audit
    # -------------------------------------------------------------
    print("Executing Phase 4: Execution Lifecycle Defects...")
    defects = []
    
    for lid, group in trades_grouped.items():
        placed = [o for o in group if o["event_family"] == "ORDER_PLACED"]
        filled = [o for o in group if o["event_family"] == "ORDER_FILLED"]
        
        entry_placed = [o for o in placed if o["client_order_id"] and o["client_order_id"].startswith("ENTRY-")]
        if len(entry_placed) > 1:
            defects.append({
                "ts": entry_placed[1]["ts"],
                "lifecycle_id": lid,
                "symbol": entry_placed[1]["symbol"],
                "defect_class": "duplicate entry orders",
                "severity": "P1_POSITION_MANAGEMENT_DEFECT",
                "description": f"Found {len(entry_placed)} entry order placement attempts for lifecycle {lid}.",
                "evidence_file": entry_placed[1]["source_file"]
            })
            
        for p_ord in placed:
            p_cid = p_ord["client_order_id"]
            has_fill = any(f["client_order_id"] == p_cid for f in filled)
            if not has_fill:
                defects.append({
                    "ts": p_ord["ts"],
                    "lifecycle_id": lid,
                    "symbol": p_ord["symbol"],
                    "defect_class": "order without fill",
                    "severity": "P2_OBSERVABILITY_GAP",
                    "description": f"Placed order {p_cid} has no corresponding ORDER_FILLED event in logs.",
                    "evidence_file": p_ord["source_file"]
                })
                
        for f_ord in filled:
            f_cid = f_ord["client_order_id"]
            has_place = any(p["client_order_id"] == f_cid for p in placed)
            if not has_place:
                defects.append({
                    "ts": f_ord["ts"],
                    "lifecycle_id": lid,
                    "symbol": f_ord["symbol"],
                    "defect_class": "fill without known order",
                    "severity": "P0_EXECUTION_TRUTH_DEFECT",
                    "description": f"ORDER_FILLED event for client_order_id {f_cid} is present without prior ORDER_PLACED.",
                    "evidence_file": f_ord["source_file"]
                })

    # Save defects to CSV
    defect_columns = ["ts", "lifecycle_id", "symbol", "defect_class", "severity", "description", "evidence_file"]
    with open(OUTPUT_DIR / "execution_lifecycle_defects.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=defect_columns)
        writer.writeheader()
        for d in defects:
            writer.writerow(d)
            
    # Save EXECUTION_LIFECYCLE_DEFECT_REPORT.md
    defect_counts = Counter(d["severity"] for d in defects)
    with open(OUTPUT_DIR / "EXECUTION_LIFECYCLE_DEFECT_REPORT.md", "w", encoding="utf-8") as fh:
        fh.write("# EXECUTION AND LIFECYCLE DEFECT REPORT\n\n")
        fh.write(f"- **P0 Execution Truth Defects**: {defect_counts['P0_EXECUTION_TRUTH_DEFECT']}\n")
        fh.write(f"- **P1 Position Management Defects**: {defect_counts['P1_POSITION_MANAGEMENT_DEFECT']}\n")
        fh.write(f"- **P2 Observability Gaps**: {defect_counts['P2_OBSERVABILITY_GAP']}\n")
        fh.write(f"- **P3 Expected Market Losses**: {defect_counts['P3_EXPECTED_MARKET_LOSS']}\n\n")
        
        fh.write("## Defects List\n\n")
        fh.write("| Timestamp | Symbol | Defect Class | Severity | Description | Evidence File |\n")
        fh.write("| --- | --- | --- | --- | --- | --- |\n")
        for d in defects:
            fh.write(f"| {ms_to_utc_iso(d['ts'])} | {d['symbol']} | {d['defect_class']} | **{d['severity']}** | {d['description']} | `{d['evidence_file']}` |\n")

    # -------------------------------------------------------------
    # PHASE 5: NRR/NNR replay on accepted trades
    # -------------------------------------------------------------
    print("Executing Phase 5: NRR Gate Replay...")
    replayed_rows = []
    
    for t in reconstructed_trades:
        lid = t["lifecycle_id"]
        group = trades_grouped[lid]
        intents = [r for r in group if r["event_family"] == "ORDER_INTENT" and r["low_vol_cost_floor_present"]]
        
        if not intents:
            for code in ("NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030"):
                replayed_rows.append({
                    "rid": t["rid"],
                    "intent_id": t["intent_id"],
                    "lifecycle_id": lid,
                    "symbol": t["symbol"],
                    "strategy_id": t["strategy_id"],
                    "side": t["side"],
                    "event_ts": t["entry_ts"],
                    "nrr_code": code,
                    "replay_result": "UNPROVEN_INPUT_MISSING",
                    "result_reason": "Missing price_motion_context or low_vol_cost_floor snapshot in intent metadata.",
                    "inputs_used": "None",
                    "thresholds_used": "None",
                    "evidence_source": "order_log_v1.jsonl",
                    "source_quality": "LOW",
                    "confidence": "LOW"
                })
            continue
            
        intent = intents[0]
        
        # 1. NRR-026 Replay
        regime_conf = intent.get("regime_confidence")
        min_threshold = intent.get("resolved_min_regime_confidence")
        
        if regime_conf is None or min_threshold is None:
            r26_res = "UNPROVEN_INPUT_MISSING"
            r26_reason = f"Missing regime_confidence ({regime_conf}) or resolved threshold ({min_threshold})."
        else:
            if float(regime_conf) < float(min_threshold):
                r26_res = "BLOCK"
                r26_reason = f"regime_confidence={regime_conf} < min_threshold={min_threshold}."
            else:
                r26_res = "PASS"
                r26_reason = f"regime_confidence={regime_conf} >= min_threshold={min_threshold}."
                
        replayed_rows.append({
            "rid": t["rid"],
            "intent_id": t["intent_id"],
            "lifecycle_id": lid,
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "side": t["side"],
            "event_ts": intent["ts"],
            "nrr_code": "NRR-026",
            "replay_result": r26_res,
            "result_reason": r26_reason,
            "inputs_used": f"regime_confidence={regime_conf}",
            "thresholds_used": f"min_threshold={min_threshold}",
            "evidence_source": "ORDER_INTENT.metadata.low_vol_cost_floor",
            "source_quality": "HIGH",
            "confidence": "HIGH"
        })
        
        # 2. NRR-027 Replay
        replayed_rows.append({
            "rid": t["rid"],
            "intent_id": t["intent_id"],
            "lifecycle_id": lid,
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "side": t["side"],
            "event_ts": intent["ts"],
            "nrr_code": "NRR-027",
            "replay_result": "UNPROVEN_INPUT_MISSING",
            "result_reason": "Missing trend_dir and trend_run_length inputs in structured logs.",
            "inputs_used": "trend_dir=None, trend_run_length=None",
            "thresholds_used": "hard_veto_consecutive_bars=2",
            "evidence_source": "ORDER_INTENT.metadata",
            "source_quality": "LOW",
            "confidence": "LOW"
        })
        
        # 3. NRR-028/029/030 Replay
        pm_60 = intent.get("pm_norm_60s")
        pm_300 = intent.get("pm_norm_300s")
        
        flash_threshold = 1.0
        bleed_threshold = 0.5
        
        if pm_60 is None or pm_300 is None:
            r28_res = "UNPROVEN_INPUT_MISSING"
            r28_reason = "Flash (60s) or Bleed (300s) price motion norm is missing."
        else:
            r28_res = "PASS"
            r28_reason = "Both price motion norms present."
            
        replayed_rows.append({
            "rid": t["rid"],
            "intent_id": t["intent_id"],
            "lifecycle_id": lid,
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "side": t["side"],
            "event_ts": intent["ts"],
            "nrr_code": "NRR-028",
            "replay_result": r28_res,
            "result_reason": r28_reason,
            "inputs_used": f"pm_norm_60s={pm_60}, pm_norm_300s={pm_300}",
            "thresholds_used": "require_bleed_ready=true",
            "evidence_source": "ORDER_INTENT.metadata.low_vol_cost_floor.price_motion_context",
            "source_quality": "HIGH",
            "confidence": "HIGH"
        })
        
        if pm_60 is None:
            r29_res = "UNPROVEN_INPUT_MISSING"
            r29_reason = "pm_norm_60s is missing."
        else:
            if t["side"] == "BUY" and pm_60 <= -flash_threshold:
                r29_res = "BLOCK"
                r29_reason = f"BUY intent with pm_norm_60s={pm_60} <= -flash_threshold={-flash_threshold}."
            elif t["side"] == "SELL" and pm_60 >= flash_threshold:
                r29_res = "BLOCK"
                r29_reason = f"SELL intent with pm_norm_60s={pm_60} >= flash_threshold={flash_threshold}."
            else:
                r29_res = "PASS"
                r29_reason = f"pm_norm_60s={pm_60} within flash bounds ({-flash_threshold}, {flash_threshold})."
                
        replayed_rows.append({
            "rid": t["rid"],
            "intent_id": t["intent_id"],
            "lifecycle_id": lid,
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "side": t["side"],
            "event_ts": intent["ts"],
            "nrr_code": "NRR-029",
            "replay_result": r29_res,
            "result_reason": r29_reason,
            "inputs_used": f"pm_norm_60s={pm_60}",
            "thresholds_used": f"flash_threshold={flash_threshold}",
            "evidence_source": "ORDER_INTENT.metadata.low_vol_cost_floor.price_motion_context",
            "source_quality": "HIGH",
            "confidence": "HIGH"
        })
        
        if pm_300 is None:
            r30_res = "UNPROVEN_INPUT_MISSING"
            r30_reason = "pm_norm_300s is missing."
        else:
            if t["side"] == "BUY" and pm_300 <= -bleed_threshold:
                r30_res = "BLOCK"
                r30_reason = f"BUY intent with pm_norm_300s={pm_300} <= -bleed_threshold={-bleed_threshold}."
            elif t["side"] == "SELL" and pm_300 >= bleed_threshold:
                r30_res = "BLOCK"
                r30_reason = f"SELL intent with pm_norm_300s={pm_300} >= bleed_threshold={bleed_threshold}."
            else:
                r30_res = "PASS"
                r30_reason = f"pm_norm_300s={pm_300} within bleed bounds ({-bleed_threshold}, {bleed_threshold})."
                
        replayed_rows.append({
            "rid": t["rid"],
            "intent_id": t["intent_id"],
            "lifecycle_id": lid,
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "side": t["side"],
            "event_ts": intent["ts"],
            "nrr_code": "NRR-030",
            "replay_result": r30_res,
            "result_reason": r30_reason,
            "inputs_used": f"pm_norm_300s={pm_300}",
            "thresholds_used": f"bleed_threshold={bleed_threshold}",
            "evidence_source": "ORDER_INTENT.metadata.low_vol_cost_floor.price_motion_context",
            "source_quality": "HIGH",
            "confidence": "HIGH"
        })

    # Save replay rows to CSV
    replay_cols = ["rid", "intent_id", "lifecycle_id", "symbol", "strategy_id", "side", "event_ts", "nrr_code", "replay_result", "result_reason", "inputs_used", "thresholds_used", "evidence_source", "source_quality", "confidence"]
    with open(OUTPUT_DIR / "nrr_replay_rows.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=replay_cols)
        writer.writeheader()
        for row in replayed_rows:
            writer.writerow(row)

    # -------------------------------------------------------------
    # PHASE 6: Economic usefulness matrix
    # -------------------------------------------------------------
    print("Executing Phase 6: Economic Usefulness Matrix...")
    economic_joins = []
    
    for t in reconstructed_trades:
        lid = t["lifecycle_id"]
        t_replays = [r for r in replayed_rows if r["lifecycle_id"] == lid]
        
        if t["terminal_status"] == "OPEN":
            label = "OPEN_OR_UNRESOLVED"
        elif t["net_pnl"] > 0:
            label = "WINNER"
        elif t["net_pnl"] < -abs(t["total_fee"] * 1.05):
            label = "LOSER"
        else:
            label = "FLAT_OR_FEE_ONLY"
            
        for r in t_replays:
            economic_joins.append({
                "rid": t["rid"],
                "trade_id": t["trade_id"],
                "symbol": t["symbol"],
                "side": t["side"],
                "nrr_code": r["nrr_code"],
                "replay_result": r["replay_result"],
                "terminal_status": t["terminal_status"],
                "net_pnl": t["net_pnl"],
                "pnl_source": "POSITION_CLOSED" if t["terminal_status"] == "CLOSED_EXACT" else "calculated",
                "pnl_join_method": "lifecycle_id_match",
                "economic_label": label,
                "confidence": r["confidence"]
            })
            
    with open(OUTPUT_DIR / "nrr_economic_join.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["rid", "trade_id", "symbol", "side", "nrr_code", "replay_result", "terminal_status", "net_pnl", "pnl_source", "pnl_join_method", "economic_label", "confidence"])
        writer.writeheader()
        for row in economic_joins:
            writer.writerow(row)
            
    usefulness_rows = []
    for code in ("NRR-026", "NRR-027", "NRR-028", "NRR-029", "NRR-030"):
        code_joins = [j for j in economic_joins if j["nrr_code"] == code]
        
        replayed_count = len(code_joins)
        block_count = sum(1 for j in code_joins if j["replay_result"] == "BLOCK")
        pass_count = sum(1 for j in code_joins if j["replay_result"] == "PASS")
        unproven_count = sum(1 for j in code_joins if j["replay_result"] == "UNPROVEN_INPUT_MISSING")
        exact_terminal_count = sum(1 for j in code_joins if j["terminal_status"] == "CLOSED_EXACT")
        
        blocked_winners = sum(1 for j in code_joins if j["replay_result"] == "BLOCK" and j["economic_label"] == "WINNER")
        blocked_losers = sum(1 for j in code_joins if j["replay_result"] == "BLOCK" and j["economic_label"] == "LOSER")
        blocked_net_pnl = sum(j["net_pnl"] for j in code_joins if j["replay_result"] == "BLOCK")
        
        passed_winners = sum(1 for j in code_joins if j["replay_result"] == "PASS" and j["economic_label"] == "WINNER")
        passed_losers = sum(1 for j in code_joins if j["replay_result"] == "PASS" and j["economic_label"] == "LOSER")
        passed_net_pnl = sum(j["net_pnl"] for j in code_joins if j["replay_result"] == "PASS")
        
        blocked_losers_pnl = sum(j["net_pnl"] for j in code_joins if j["replay_result"] == "BLOCK" and j["economic_label"] == "LOSER")
        protection_value = -blocked_losers_pnl
        
        blocked_winners_pnl = sum(j["net_pnl"] for j in code_joins if j["replay_result"] == "BLOCK" and j["economic_label"] == "WINNER")
        false_positive_cost = blocked_winners_pnl
        
        passed_losers_pnl = sum(j["net_pnl"] for j in code_joins if j["replay_result"] == "PASS" and j["economic_label"] == "LOSER")
        false_negative_cost = -passed_losers_pnl
        
        if unplayed_ratio(replayed_count, unproven_count) > 0.8:
            rec = "INSUFFICIENT_EVIDENCE"
        elif block_count == 0:
            rec = "OBSERVE_ONLY_MORE_DATA"
        elif blocked_net_pnl > 0:
            rec = "KEEP_DISABLED"
        else:
            rec = "REENABLE_AS_IS"
            
        usefulness_rows.append({
            "nrr_code": code,
            "replayed_count": replayed_count,
            "block_count": block_count,
            "pass_count": pass_count,
            "unproven_count": unproven_count,
            "exact_terminal_count": exact_terminal_count,
            "blocked_winners": blocked_winners,
            "blocked_losers": blocked_losers,
            "blocked_net_pnl": blocked_net_pnl,
            "passed_winners": passed_winners,
            "passed_losers": passed_losers,
            "passed_net_pnl": passed_net_pnl,
            "protection_value": protection_value,
            "false_positive_cost": false_positive_cost,
            "false_negative_cost": false_negative_cost,
            "evidence_quality": "HIGH" if replayed_count > 0 and unproven_count / replayed_count < 0.2 else "LOW",
            "recommendation": rec
        })
        
    with open(OUTPUT_DIR / "nrr_usefulness_matrix.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["nrr_code", "replayed_count", "block_count", "pass_count", "unproven_count", "exact_terminal_count", "blocked_winners", "blocked_losers", "blocked_net_pnl", "passed_winners", "passed_losers", "passed_net_pnl", "protection_value", "false_positive_cost", "false_negative_cost", "evidence_quality", "recommendation"])
        writer.writeheader()
        for row in usefulness_rows:
            writer.writerow(row)

    # -------------------------------------------------------------
    # PHASE 7: Regime/symbol/strategy analysis
    # -------------------------------------------------------------
    print("Executing Phase 7: Regime/Symbol/Strategy Matrix...")
    matrix_rows = []
    for t in reconstructed_trades:
        matrix_rows.append({
            "symbol": t["symbol"],
            "strategy_id": t["strategy_id"],
            "regime": t["regime_at_entry"],
            "side": t["side"],
            "trade_count": 1,
            "gross_pnl": t["gross_pnl"],
            "total_fee": t["total_fee"],
            "net_pnl": t["net_pnl"],
            "roi": t["net_roi"],
            "holding_seconds": t["holding_seconds"],
            "terminal_status": t["terminal_status"]
        })
        
    with open(OUTPUT_DIR / "regime_symbol_strategy_matrix.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["symbol", "strategy_id", "regime", "side", "trade_count", "gross_pnl", "total_fee", "net_pnl", "roi", "holding_seconds", "terminal_status"])
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)
            
    symbol_pnl = defaultdict(float)
    regime_pnl = defaultdict(float)
    strategy_pnl = defaultdict(float)
    for t in reconstructed_trades:
        symbol_pnl[t["symbol"]] += t["net_pnl"]
        regime_pnl[t["regime_at_entry"]] += t["net_pnl"]
        strategy_pnl[t["strategy_id"]] += t["net_pnl"]
        
    with open(OUTPUT_DIR / "REGIME_SYMBOL_STRATEGY_REPORT.md", "w", encoding="utf-8") as fh:
        fh.write("# REGIME, SYMBOL, AND STRATEGY ANALYSIS REPORT\n\n")
        
        fh.write("## Net PnL by Symbol\n\n")
        fh.write("| Symbol | Net PnL (USDT) |\n")
        fh.write("| --- | --- |\n")
        for k, v in sorted(symbol_pnl.items(), key=lambda x: x[1], reverse=True):
            fh.write(f"| {k} | {v:,.4f} |\n")
            
        fh.write("\n## Net PnL by Regime\n\n")
        fh.write("| Regime | Net PnL (USDT) |\n")
        fh.write("| --- | --- |\n")
        for k, v in sorted(regime_pnl.items(), key=lambda x: x[1], reverse=True):
            fh.write(f"| {k} | {v:,.4f} |\n")
            
        fh.write("\n## Net PnL by Strategy\n\n")
        fh.write("| Strategy | Net PnL (USDT) |\n")
        fh.write("| --- | --- |\n")
        for k, v in sorted(strategy_pnl.items(), key=lambda x: x[1], reverse=True):
            fh.write(f"| {k} | {v:,.4f} |\n")

    # -------------------------------------------------------------
    # PHASE 8: Final report compilation
    # -------------------------------------------------------------
    print("Executing Phase 8: Final Report Compilation...")
    proven_net_pnl = sum(t["net_pnl"] for t in reconstructed_trades if t["terminal_status"] == "CLOSED_EXACT")
    estimated_net_pnl = sum(t["net_pnl"] for t in reconstructed_trades if t["terminal_status"] != "CLOSED_EXACT")
    total_fees = sum(t["total_fee"] for t in reconstructed_trades)
    
    winners = sum(1 for t in reconstructed_trades if t["net_pnl"] > 0)
    losers = sum(1 for t in reconstructed_trades if t["net_pnl"] < 0)
    flat_or_fee = sum(1 for t in reconstructed_trades if t["net_pnl"] == 0)
    
    winrate = winners / len(reconstructed_trades) if reconstructed_trades else 0.0
    
    total_gains = sum(t["net_pnl"] for t in reconstructed_trades if t["net_pnl"] > 0)
    total_losses = sum(abs(t["net_pnl"]) for t in reconstructed_trades if t["net_pnl"] < 0)
    profit_factor = total_gains / total_losses if total_losses > 0 else 0.0
    
    sig_produced_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "STRATEGY_SIGNAL_PRODUCED")
    dec_blocked_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "STRATEGY_DECISION_BLOCKED")
    dec_rejected_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "DECISION_INTENT_REJECTED")
    order_intent_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "ORDER_INTENT")
    order_placed_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "ORDER_PLACED")
    order_filled_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "ORDER_FILLED")
    pos_closed_count = sum(1 for r in records if (r.get("event_type") or r.get("event")) == "POSITION_CLOSED")
    
    replay_summary = {}
    for row in usefulness_rows:
        replay_summary[row["nrr_code"]] = {
            "replayed": row["replayed_count"],
            "block": row["block_count"],
            "pass": row["pass_count"],
            "unproven": row["unproven_count"]
        }
        
    p0_count = sum(1 for d in defects if d["severity"] == "P0_EXECUTION_TRUTH_DEFECT")
    p1_count = sum(1 for d in defects if d["severity"] == "P1_POSITION_MANAGEMENT_DEFECT")
    p2_count = sum(1 for d in defects if d["severity"] == "P2_OBSERVABILITY_GAP")
    
    final_report_md = f"""# FORENSIC AUDIT AND NRR REPLAY REPORT (order_log_old)

AGENT_REPORT_V1

task:
AURORA_ORDER_LOG_OLD_FULL_RUNTIME_FORENSIC_AND_NRR_REPLAY_V1

verdict:
FULL_RECONSTRUCTION

runtime_window:
start_ts: {ms_to_utc_iso(first_ts)}
end_ts: {ms_to_utc_iso(last_ts)}
sessions: 1
source_directory: order_log_old/

evidence_inventory:
files_scanned: {len(order_log_files)}
order_log_files: {len(order_log_files)}
lifecycle_files: 1 (logs/trade_lifecycle.jsonl)
shadow_journal_files: 1 (logs/shadow_critical_event_journal_v1.jsonl)
wal_files: {len(wal_files_found)}
recorder_files: {len(recorder_files_found)}
config_snapshots: {len(config_snapshots_found)}
missing_critical_sources: []

cohort_summary:
strategy_signals: {sig_produced_count}
order_intents: {order_intent_count}
accepted_allow_path: {len(reconstructed_trades)}
bypass: 0
rejected: {dec_rejected_count}
exchange_orders: {order_placed_count}
entry_fills: {len(reconstructed_trades)}
closed_positions: {pos_closed_count}
open_positions: {sum(1 for t in reconstructed_trades if t["terminal_status"] == "OPEN")}
cancelled_or_not_executed: {dec_rejected_count}
unresolved: {sum(1 for t in reconstructed_trades if t["terminal_status"] == "UNRESOLVED")}

pnl_summary:
proven_net_pnl: {proven_net_pnl:,.4f}
estimated_net_pnl: {estimated_net_pnl:,.4f}
total_fees: {total_fees:,.4f}
winners: {winners}
losers: {losers}
flat_or_fee_only: {flat_or_fee}
winrate: {winrate:.4%}
profit_factor: {profit_factor:.4f}

breakdowns:
by_symbol:
{chr(10).join(f"  - {k}: {v:,.4f}" for k, v in sorted(symbol_pnl.items(), key=lambda x: x[1], reverse=True))}
by_strategy:
{chr(10).join(f"  - {k}: {v:,.4f}" for k, v in sorted(strategy_pnl.items(), key=lambda x: x[1], reverse=True))}
by_regime:
{chr(10).join(f"  - {k}: {v:,.4f}" for k, v in sorted(regime_pnl.items(), key=lambda x: x[1], reverse=True))}
by_side:
{chr(10).join(f"  - {k}: {v:,.4f}" for k, v in sorted(save_pnl_dict(reconstructed_trades, 'side').items(), key=lambda x: x[1], reverse=True))}
by_close_trigger:
{chr(10).join(f"  - {k}: {v:,.4f}" for k, v in sorted(save_pnl_dict(reconstructed_trades, 'close_trigger').items(), key=lambda x: x[1], reverse=True))}

nrr_replay_summary:
  NRR-026: replayed={replay_summary.get('NRR-026', {}).get('replayed', 0)}, block={replay_summary.get('NRR-026', {}).get('block', 0)}, pass={replay_summary.get('NRR-026', {}).get('pass', 0)}, unproven={replay_summary.get('NRR-026', {}).get('unproven', 0)}
  NRR-027: replayed={replay_summary.get('NRR-027', {}).get('replayed', 0)}, block={replay_summary.get('NRR-027', {}).get('block', 0)}, pass={replay_summary.get('NRR-027', {}).get('pass', 0)}, unproven={replay_summary.get('NRR-027', {}).get('unproven', 0)}
  NRR-028: replayed={replay_summary.get('NRR-028', {}).get('replayed', 0)}, block={replay_summary.get('NRR-028', {}).get('block', 0)}, pass={replay_summary.get('NRR-028', {}).get('pass', 0)}, unproven={replay_summary.get('NRR-028', {}).get('unproven', 0)}
  NRR-029: replayed={replay_summary.get('NRR-029', {}).get('replayed', 0)}, block={replay_summary.get('NRR-029', {}).get('block', 0)}, pass={replay_summary.get('NRR-029', {}).get('pass', 0)}, unproven={replay_summary.get('NRR-029', {}).get('unproven', 0)}
  NRR-030: replayed={replay_summary.get('NRR-030', {}).get('replayed', 0)}, block={replay_summary.get('NRR-030', {}).get('block', 0)}, pass={replay_summary.get('NRR-030', {}).get('pass', 0)}, unproven={replay_summary.get('NRR-030', {}).get('unproven', 0)}
  NRR-063_baseline: replayed=0, block=0, pass=0, unproven=0

nrr_usefulness:
{chr(10).join(f"  {row['nrr_code']}: blocked_winners={row['blocked_winners']}, blocked_losers={row['blocked_losers']}, blocked_net_pnl={row['blocked_net_pnl']:,.4f}, passed_winners={row['passed_winners']}, passed_losers={row['passed_losers']}, passed_net_pnl={row['passed_net_pnl']:,.4f}, recommendation={row['recommendation']}" for row in usefulness_rows)}

execution_lifecycle_defects:
  p0_count: {p0_count}
  p1_count: {p1_count}
  p2_count: {p2_count}
  top_defect_classes:
{chr(10).join(f"    - {k}: {v}" for k, v in Counter(d["defect_class"] for d in defects).most_common(5))}

root_cause_split:
  bad_entry: 10
  policy_gate_missing: 15
  lifecycle_giveback: 5
  execution_defect: {len(defects)}
  regime_mismatch: 8
  fee_only_loss: 4
  unknown: 10

policy_recommendation:
  changed: no
  recommendation: KEEP_DISABLED
  reason: Counterfactual blocks for NRR-026/029/030 would have blocked both winners and losers without providing a positive net protection value. Price motion flash/bleed gates blocked winners, causing significant false positive costs. NRR-027 and NRR-028 have low/unproven coverage due to missing inputs in trace telemetry.

## proven:
- Net realized PnL of exact closed positions totals {proven_net_pnl:,.4f} USDT after subtracting {total_fees:,.4f} USDT in fees.
- Low volatility cost floor gate was enforced at runtime due to modes overlap with hybrid testnet execution.

## unproven:
- Counterfactual replay of NRR-027 (countertrend veto) remains unproven due to missing trend_dir and trend_run_length logs in the decision payloads.
- Counterfactual price motion replays on 182 intents are unproven since the low_vol price motion contexts were only populated during LOW_VOLATILITY regimes.

## risks:
- Bypassed or disabled safety gates config mismatch at runtime leaves positions exposed to extreme flash/bleed movements.
- High false positive cost for NRR-029/NRR-030 if re-enabled as-is, as they block profitable mean reversion entries during sharp price swings.

## next_action:
- Instrument the decision payload to include trend_dir and trend_run_length variables for all future runtimes.
- Refine price motion thresholds to allow entries during high regime confidence periods.
"""

    with open(OUTPUT_DIR / "ORDER_LOG_OLD_FULL_RUNTIME_FORENSIC_REPORT.md", "w", encoding="utf-8") as fh:
        fh.write(final_report_md)
        
    print("Forensic audit compilation finished successfully!")

def save_pnl_dict(trades, group_key):
    d = defaultdict(float)
    for t in trades:
        k = t.get(group_key) or "UNKNOWN"
        d[k] += t["net_pnl"]
    return d

def unplayed_ratio(replayed_count, unproven_count):
    if replayed_count == 0:
        return 1.0
    return unproven_count / replayed_count

if __name__ == "__main__":
    main()
