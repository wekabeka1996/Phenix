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

# Get T_003 lid
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["trade_id"] == "T_003":
            lid = row["lifecycle_id"]
            print(f"T_003 (LID: {lid}) events:")
            for ev in events_by_lid.get(lid, []):
                print(f"  TS: {ev['ts']}, Event: {ev['source_event_name']}, Family: {ev['event_family']}, Qty: {ev['qty']}, Price: {ev['price']}, Fee: {ev['fee']}, Realized PnL: {ev['realized_pnl']}")
            break
