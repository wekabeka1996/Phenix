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

# Get T_048 lid
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["trade_id"] == "T_048":
            lid = row["lifecycle_id"]
            side = row["side"]
            print(f"T_048 side: {side}, LID: {lid}")
            events = events_by_lid.get(lid, [])
            fills = [e for e in events if e["event_family"] == "ORDER_FILLED"]
            for i, f in enumerate(fills):
                print(f"  Fill {i}: TS={f['ts']}, Side={f['side']}, client_order_id={f['client_order_id']}, Qty={f['qty']}, Price={f['price']}, Fee={f['fee']}")
            break
