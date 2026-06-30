import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

# Load trades
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = {t["trade_id"]: t for t in reader}

# Group normalized events by lifecycle_id
events_by_lid = {}
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        lid = row["lifecycle_id"]
        if lid not in events_by_lid:
            events_by_lid[lid] = []
        events_by_lid[lid].append(row)

for tid in ["T_001", "T_002", "T_005", "T_048"]:
    t = trades[tid]
    lid = t["lifecycle_id"]
    print(f"\n==================== {tid} (LID: {lid}) ====================")
    events = events_by_lid.get(lid, [])
    print(f"Total events: {len(events)}")
    for ev in events:
        print(f"  TS: {ev['ts']}, Event: {ev['source_event_name']}, Family: {ev['event_family']}, Status: {ev['status']}, Qty: {ev['qty']}, Price: {ev['price']}, Fee: {ev['fee']}, Realized PnL: {ev['realized_pnl']}, Reject Reason: {ev['reject_reason']}")
