import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

# Group normalized events by lifecycle_id
events_by_lid = {}
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        lid = row["lifecycle_id"]
        if lid not in events_by_lid:
            events_by_lid[lid] = []
        events_by_lid[lid].append(row)

# Get trades
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

replayable = []
missing = []

for t in trades:
    lid = t["lifecycle_id"]
    events = events_by_lid.get(lid, [])
    
    found_intent = None
    for ev in events:
        if ev["event_family"] == "ORDER_INTENT":
            r_conf = ev.get("regime_confidence")
            t_thresh = ev.get("resolved_min_regime_confidence")
            if r_conf and r_conf != "None" and r_conf != "" and t_thresh and t_thresh != "None" and t_thresh != "":
                found_intent = ev
                break
                
    if found_intent:
        replayable.append((t["trade_id"], t["terminal_status"], found_intent))
    else:
        # Check if any event in the group has it (e.g. STRATEGY_SIGNAL_PRODUCED or ORDER_PLACED)
        found_any = None
        for ev in events:
            r_conf = ev.get("regime_confidence")
            t_thresh = ev.get("resolved_min_regime_confidence")
            if r_conf and r_conf != "None" and r_conf != "" and t_thresh and t_thresh != "None" and t_thresh != "":
                found_any = ev
                break
        missing.append((t["trade_id"], t["terminal_status"], found_any))

print(f"Total trades: {len(trades)}")
print(f"Replayable on ORDER_INTENT: {len(replayable)}")
for tid, status, intent in replayable[:5]:
    print(f"  {tid} ({status}): r_conf={intent['regime_confidence']}, threshold={intent['resolved_min_regime_confidence']}, low_vol_present={intent['low_vol_cost_floor_present']}")

print(f"\nMissing on ORDER_INTENT but present on other events: {sum(1 for tid, status, any_ev in missing if any_ev)}")
print(f"Completely missing: {sum(1 for tid, status, any_ev in missing if not any_ev)}")

for tid, status, any_ev in missing:
    if any_ev:
        print(f"  {tid} ({status}): present in {any_ev['source_event_name']} with r_conf={any_ev['regime_confidence']}, threshold={any_ev['resolved_min_regime_confidence']}")
    else:
        print(f"  {tid} ({status}): completely missing")
