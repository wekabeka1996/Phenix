import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["trade_id"] == "T_046":
            lid = row["lifecycle_id"]
            print(f"T_046 lifecycle_id: {lid}")
            break

found = 0
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if row["lifecycle_id"] == lid:
            print(f"Row {i}: TS={row['ts']}, Event={row['source_event_name']}, Family={row['event_family']}, Qty={row['qty']}, Price={row['price']}, Fee={row['fee']}, Realized PnL={row['realized_pnl']}")
            found += 1
print(f"Found {found} events for T_046")
