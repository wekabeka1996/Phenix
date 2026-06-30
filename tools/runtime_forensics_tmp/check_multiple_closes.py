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

# Load trades
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

multiple_closes = 0
for t in trades:
    lid = t["lifecycle_id"]
    events = events_by_lid.get(lid, [])
    closes = [e for e in events if e["source_event_name"] == "POSITION_CLOSED"]
    if len(closes) > 1:
        multiple_closes += 1
        print(f"Trade: {t['trade_id']}, LID: {lid}, Closes Count: {len(closes)}")
        for i, c in enumerate(closes):
            print(f"  Close {i}: TS={c['ts']}, Status={c['status']}, PnL={c['realized_pnl']}, Fee={c['fee']}, Trigger={c['reject_reason']}")

print(f"Total trades with multiple closes: {multiple_closes}")
